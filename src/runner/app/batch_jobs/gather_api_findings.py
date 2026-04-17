import aiohttp
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import os

from .api_vendors import BaseAPIVendor, ThreatStreamAdapter, RecordedFutureAdapter, vendor_config

logger = logging.getLogger(__name__)

class GatherApiFindingsTask:
    """Task for gathering typosquat domain findings from vendor APIs"""

    def __init__(self, job_id: str, program_name: str, user_id: str, api_vendor: str = "threatstream", date_range_hours: Optional[int] = None, custom_query: Optional[str] = None):
        self.job_id = job_id
        self.program_name = program_name
        self.user_id = user_id
        self.api_vendor = api_vendor
        self.date_range_hours = date_range_hours
        self.custom_query = custom_query
        self.existing_domains_cache = set()  # Cache existing domains for the single program
        self.results = {
            "success_count": 0,
            "error_count": 0,
            "errors": [],
            "processed_domains": [],
            "updated_domains": [],  # Track domains that were updated (existing findings)
            "skipped_domains": [],  # Track domains skipped for other reasons
            "api_stats": {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_domains_found": 0,
                "duplicate_domains_skipped": 0
            }
        }

        # API configuration
        self.api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
        self.api_token = os.getenv("INTERNAL_SERVICE_API_KEY", "")
        self.timeout = aiohttp.ClientTimeout(total=120)  # Extended timeout for batch operations
        
        # Initialize vendor adapter with configuration
        self.vendor_adapter = self._create_vendor_adapter(api_vendor)
        
        # Apply any runtime configuration updates
        self._apply_vendor_configuration()
        
        # Connection pool for HTTP requests - will be created when needed
        self.connector = None
        self.session = None

        logger.info(f"GatherApiFindingsTask initialized with API_BASE_URL: {self.api_base_url}")
        logger.info(f"API token configured: {'Yes' if self.api_token else 'No'}")
        logger.info(f"Full endpoint URL will be: {self.api_base_url}/findings/typosquat")
        logger.info(f"Target API vendor: {api_vendor}")
        logger.info(f"Target program: {program_name}")
        if date_range_hours is not None:
            if date_range_hours == 0:
                logger.info("Date range filter: 0 hours (no date filtering - fetch all available data)")
            else:
                logger.info(f"Date range filter: {date_range_hours} hours (applies to RecordedFuture only)")
        else:
            logger.info("Date range filter: None (fetch all available data)")

        if custom_query:
            logger.info(f"Custom query (ThreatStream only): {custom_query}")
        else:
            logger.info("Custom query: None (using default vendor configuration)")

    async def execute(self):
        """Main execution method for single program processing"""
        try:
            # Update job status to running
            await self.update_job_status("running", 0, f"Starting {self.api_vendor} API gathering for program {self.program_name}...")

            # Test API connectivity first
            await self.test_api_connectivity()

            # Pre-fetch existing domains for the program
            await self.fetch_existing_domains_for_program(self.program_name)

            # Update progress and process the program
            await self.update_job_status("running", 50, f"Processing program {self.program_name}...")
            await self.process_program_findings(self.program_name)

            # Aggregate vendor stats
            vendor_stats = self.vendor_adapter.get_stats()
            self.results['api_stats'].update(vendor_stats)

            # Final status update
            message = f"Completed: {self.results['success_count']} successful, {self.results['error_count']} errors"
            if len(self.results['updated_domains']) > 0:
                message += f", {len(self.results['updated_domains'])} updated (existing findings)"
            if self.results['api_stats']['duplicate_domains_skipped'] > 0:
                message += f", {self.results['api_stats']['duplicate_domains_skipped']} skipped"
            if self.results['api_stats']['total_domains_found'] > 0:
                message += f". Found {self.results['api_stats']['total_domains_found']} domains"

            logger.info(f"Job {self.job_id} final results for program {self.program_name}: {self.results}")
            await self.update_job_status("completed", 100, message, self.results)

        except Exception as e:
            logger.error(f"Error in gather API findings job {self.job_id}: {str(e)}")
            await self.update_job_status("failed", 0, f"Job failed: {str(e)}")
        finally:
            # Clean up connection pool and session
            await self._cleanup_session()

    def _create_vendor_adapter(self, api_vendor: str) -> BaseAPIVendor:
        """Create appropriate vendor adapter based on vendor name"""
        vendor_map = {
            "threatstream": ThreatStreamAdapter,
            "recordedfuture": RecordedFutureAdapter
        }
        
        adapter_class = vendor_map.get(api_vendor.lower())
        if not adapter_class:
            raise ValueError(f"Unsupported API vendor: {api_vendor}")
            
        return adapter_class(self.timeout)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a shared HTTP session with connection pooling"""
        if self.session is None or self.session.closed:
            if self.connector is None or self.connector.closed:
                self.connector = aiohttp.TCPConnector(
                    limit=10,  # Total connection pool size
                    limit_per_host=5,  # Max connections per host
                    keepalive_timeout=30,
                    enable_cleanup_closed=True
                )
            
            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=self.timeout
            )
            logger.debug("Created new HTTP session with connection pooling")
        
        return self.session
    
    async def _cleanup_session(self):
        """Clean up HTTP session and connector"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("Closed HTTP session")
        
        if self.connector and not self.connector.closed:
            await self.connector.close()
            logger.debug("Closed HTTP connector")
    
    def _apply_vendor_configuration(self):
        """Apply any runtime configuration updates to the vendor adapter"""
        # Check for program-specific or job-specific configuration overrides
        config_override = os.getenv(f"{self.api_vendor.upper()}_CONFIG_OVERRIDE")
        if config_override:
            try:
                import json
                override_config = json.loads(config_override)
                vendor_config.update_vendor_config(self.api_vendor, override_config)
                logger.info(f"Applied configuration override for {self.api_vendor}: {override_config}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse configuration override for {self.api_vendor}: {e}")
        
        # Apply any adapter-specific configuration updates
        if hasattr(self.vendor_adapter, 'update_config'):
            runtime_config = vendor_config.get_vendor_config(self.api_vendor)
            if runtime_config:
                self.vendor_adapter.update_config(runtime_config)
                logger.info(f"Updated {self.api_vendor} adapter configuration")
    

    async def process_program_findings(self, program_name: str):
        """Process findings for a specific program using vendor adapter"""
        logger.info(f"Processing program: {program_name}")

        try:
            # Get API credentials for this program
            api_credentials = await self.get_program_api_credentials(program_name)
            if not api_credentials:
                logger.error(f"No API credentials found for program {program_name}")
                self.results["error_count"] += 1
                self.results["errors"].append({
                    "program": program_name,
                    "error": f"No {self.api_vendor} API credentials configured for this program"
                })
                return

            # Validate credentials for the vendor
            if not self.vendor_adapter.validate_credentials(api_credentials):
                required_fields = self.vendor_adapter.get_required_credentials()
                logger.error(f"Invalid credentials for program {program_name}. Required: {required_fields}")
                self.results["error_count"] += 1
                self.results["errors"].append({
                    "program": program_name,
                    "error": f"Invalid {self.api_vendor} API credentials. Required fields: {required_fields}"
                })
                return

            # Use the date range parameter if provided
            date_range_hours = self.date_range_hours

            # Gather domains from the API using vendor adapter with shared session
            session = await self._get_session()
            domains = await self.vendor_adapter.gather_domains(api_credentials, program_name, session, date_range_hours, self.custom_query)
            if not domains:
                logger.info(f"No domains found for program {program_name}")
                return

            logger.info(f"Found {len(domains)} domains from {self.api_vendor} API for program {program_name}")

            # Convert domains to TyposquatDomain objects and send to API
            await self.process_and_store_domains(domains, program_name)

        except Exception as e:
            logger.error(f"Error processing program {program_name}: {str(e)}")
            self.results["error_count"] += 1
            self.results["errors"].append({
                "program": program_name,
                "error": str(e)
            })

    def _is_using_mock_data(self) -> bool:
        """Check if we're using mock data instead of real API calls"""
        # Set to False to use real API calls
        # Set to True for testing with mock data (no API credentials required)
        return False


    async def process_and_store_domains(self, domains: List[Dict[str, Any]], program_name: str):
        """Process domains and store them as TyposquatDomain findings - sends all at once for single workflow"""
        logger.info(f"Processing and storing {len(domains)} domains for program {program_name}")

        # Fetch existing domains for this program to avoid duplicates
        existing_domains = await self.fetch_existing_domains_for_program(program_name)
        logger.info(f"Found {len(existing_domains)} existing domains for program {program_name}")

        # Separate new domains from existing ones for different processing
        new_domains = []
        existing_domains_to_update = []

        for domain_data in domains:
            domain_name = domain_data.get("typo_domain", "").strip()
            if domain_name in existing_domains:
                logger.debug(f"Found existing domain to update: {domain_name}")
                existing_domains_to_update.append(domain_data)
            else:
                new_domains.append(domain_data)

        logger.info(f"Domain processing plan: {len(new_domains)} new to create, {len(existing_domains_to_update)} existing to update")

        # --- Pre-flight filtering for RecordedFuture: remove domains that won't pass the API gate ---
        if self.api_vendor == "recordedfuture" and new_domains:
            try:
                domain_names = [d.get("typo_domain", "").strip() for d in new_domains if d.get("typo_domain")]
                filter_result = await self._check_domain_filtering(domain_names, program_name)
                filtered_set = set(filter_result.get("filtered", []))
                if filtered_set:
                    filtered_domains = [d for d in new_domains if d.get("typo_domain", "").strip() in filtered_set]
                    new_domains = [d for d in new_domains if d.get("typo_domain", "").strip() not in filtered_set]
                    logger.info(
                        f"Pre-flight filter: {len(filtered_domains)} domains filtered out, "
                        f"{len(new_domains)} remaining"
                    )

                    # For RecordedFuture, resolve alerts for filtered domains
                    if self.api_vendor == "recordedfuture" and filtered_domains:
                        await self._resolve_filtered_rf_alerts(filtered_domains, program_name)

                    for fd in filtered_domains:
                        self.results["skipped_domains"].append({
                            "domain": fd.get("typo_domain"),
                            "program": program_name,
                            "source": self.api_vendor,
                            "reason": "filtered_by_pre_flight_check",
                        })
            except Exception as e:
                logger.warning(f"Pre-flight filter check failed ({e}), proceeding with all new domains")

        if not new_domains and not existing_domains_to_update:
            logger.info(f"No domains to process for program {program_name}")
            return

        # Convert all new domains to findings using vendor adapter
        findings = []
        session = await self._get_session()
        for domain_data in new_domains:
            try:
                finding = self.vendor_adapter.create_finding_data(domain_data, program_name)
                if finding:
                    await self._enrich_single_finding_cross_vendor(finding, program_name, session)
                    findings.append(finding)
                else:
                    logger.warning(f"create_finding_data returned None for domain {domain_data.get('typo_domain')}")
            except Exception as e:
                logger.error(f"Error converting domain {domain_data.get('typo_domain')}: {str(e)}")
                self.results["error_count"] += 1
                self.results["errors"].append({
                    "domain": domain_data.get("typo_domain"),
                    "source": self.api_vendor,
                    "program": program_name,
                    "error": str(e)
                })

        logger.info(f"Created {len(findings)} findings from {len(new_domains)} domains")

        # RF assignee mapping + playbook unassign only for RecordedFuture-primary gathers (not TS + RF enrichment)
        if findings and self.api_vendor == "recordedfuture":
            logger.info(f"Before assignee resolution: {len(findings)} findings")
            try:
                await self._resolve_recordedfuture_assignees(findings)
            except Exception as e:
                logger.error(f"Error in assignee resolution (continuing with findings): {str(e)}")
            logger.info(f"After assignee resolution: {len(findings)} findings")

        # Only return early if there are no new findings AND no existing domains to update
        if not findings and not existing_domains_to_update:
            logger.info(f"No valid findings to process for program {program_name}")
            return

        # Process new findings if any
        if findings:
            logger.info(f"Sending {len(findings)} findings to API for single workflow processing")

            try:
                # Store all findings at once via API (will trigger single workflow)
                batch_results = await self.store_finding_batch(findings)

                # Check if batch was accepted by API
                all_success = all(result.get("success", False) for result in batch_results.values())

                if all_success:
                    # All domains accepted for processing
                    for finding in findings:
                        domain_name = finding.get("typo_domain")
                        self.results["success_count"] += 1
                        self.results["processed_domains"].append({
                            "domain": domain_name,
                            "program": program_name,
                            "source": self.api_vendor,
                            "status": "success"
                        })
                    logger.info(f"Successfully sent {len(findings)} domains for single workflow processing")
                    
                    # RF screenshots when findings include RecordedFuture panel details
                    if any((f.get("recordedfuture_data") or {}).get("raw_details") for f in findings):
                        await self._handle_recordedfuture_post_storage(findings, program_name)
                else:
                    # Some domains failed to be accepted
                    logger.error(f"Failed to send {len(findings)} domains for processing")
                    # Mark all domains as failed since we can't determine which ones failed
                    for finding in findings:
                        domain_name = finding.get("typo_domain")
                        self.results["error_count"] += 1
                        self.results["errors"].append({
                            "domain": domain_name,
                            "program": program_name,
                            "error": "Failed to queue for processing"
                        })

            except Exception as e:
                logger.error(f"Error sending {len(findings)} domains for processing: {str(e)}")
                # Mark all domains as failed
                for finding in findings:
                    domain_name = finding.get("typo_domain")
                    self.results["error_count"] += 1
                    self.results["errors"].append({
                        "domain": domain_name,
                        "program": program_name,
                        "error": f"Processing failed: {str(e)}"
                    })

        # Process existing domains for updates (similar to sync task)
        if existing_domains_to_update:
            await self._update_existing_findings(existing_domains_to_update, program_name)

        self.results['api_stats']['total_domains_found'] += len(domains)

        # Log detailed summary
        created_count = len(new_domains) if new_domains else 0
        updated_count = len(self.results.get('updated_domains', []))
        logger.info(f"Completed processing {len(domains)} domains for program {program_name}: {created_count} created, {updated_count} updated, {self.results['error_count']} errors")


    async def store_finding_batch(self, findings: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """Store multiple findings via batch API call with connection pooling"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/findings/typosquat"
            # Wrap findings in the expected API format
            batch_data = {
                "program_name": findings[0].get("program_name") if findings else "",
                "findings": {
                    "typosquat_domain": findings
                }
            }

            logger.info(f"Storing batch of {len(findings)} findings")

            session = await self._get_session()
            async with session.post(url, json=batch_data, headers=headers) as response:
                    if response.status in [200, 201]:
                        await response.json()
                        logger.info(f"Successfully initiated batch processing of {len(findings)} findings")

                        # Since processing is now in background, we can't get individual results
                        # Return success for all findings since the API accepted the batch
                        success_results = {}
                        for i in range(len(findings)):
                            success_results[i] = {
                                "success": True,
                                "message": "Processing started in background"
                            }
                        return success_results
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to store batch: HTTP {response.status} - {response_text}")

                        # Return error results for all findings in the batch
                        error_results = {}
                        for i in range(len(findings)):
                            error_results[i] = {
                                "success": False,
                                "error": f"HTTP {response.status}: {response_text}"
                            }
                        return error_results

        except Exception as e:
            logger.error(f"Error storing batch findings: {str(e)}")

            # Return error results for all findings in the batch
            error_results = {}
            for i in range(len(findings)):
                error_results[i] = {
                    "success": False,
                    "error": str(e)
                }
            return error_results

    async def store_finding(self, finding: Dict[str, Any]) -> bool:
        """Store a single finding via the API (backward compatibility) with connection pooling"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/findings/typosquat"
            logger.debug(f"Storing finding for domain: {finding.get('typo_domain')}")

            session = await self._get_session()
            async with session.post(url, json=finding, headers=headers) as response:
                    if response.status in [200, 201]:
                        logger.debug(f"Successfully stored finding for {finding.get('typo_domain')}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to store finding: HTTP {response.status} - {response_text}")
                        return False

        except Exception as e:
            logger.error(f"Error storing finding: {str(e)}")
            return False

    async def get_program_api_credentials(self, program_name: str) -> Optional[Dict[str, str]]:
        """Get API credentials for the program via API using vendor-specific field mapping"""
        return await self._get_vendor_credentials(program_name, self.api_vendor)

    async def _get_vendor_credentials(self, program_name: str, vendor: str) -> Optional[Dict[str, str]]:
        """Load credentials for a specific vendor from GET /programs/{program_name}."""
        vendor_map = {
            "threatstream": ThreatStreamAdapter,
            "recordedfuture": RecordedFutureAdapter,
        }
        adapter_cls = vendor_map.get(vendor.lower())
        if not adapter_cls:
            logger.warning(f"Unknown vendor for credential lookup: {vendor}")
            return None

        adapter = adapter_cls(self.timeout)
        credential_fields = adapter.get_credential_fields()

        try:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/programs/{program_name}"
            logger.debug(f"Fetching {vendor} API credentials for program: {program_name}")

            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"Failed to fetch program data: HTTP {response.status} - {response_text}")
                    return None

                program_data = await response.json()
                credentials: Dict[str, str] = {}
                for internal_name, db_field in credential_fields.items():
                    value = program_data.get(db_field)
                    if value:
                        credentials[internal_name] = value

                if adapter.validate_credentials(credentials):
                    return credentials

                logger.debug(f"Incomplete {vendor} credentials for program {program_name}")
                return None

        except Exception as e:
            logger.error(f"Error fetching {vendor} API credentials for program {program_name}: {str(e)}")
            return None

    async def _patch_threatstream_data(self, finding_id: str, threatstream_data: Dict[str, Any]) -> bool:
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            url = f"{self.api_base_url}/findings/typosquat/{finding_id}/threatstream-data"
            session = await self._get_session()
            async with session.patch(
                url, json={"threatstream_data": threatstream_data}, headers=headers
            ) as response:
                if response.status not in (200, 204):
                    response_text = await response.text()
                    logger.error(
                        f"PATCH threatstream_data failed for {finding_id}: HTTP {response.status} {response_text}"
                    )
                    return False
                return True
        except Exception as e:
            logger.error(f"Error PATCH threatstream_data for {finding_id}: {e}")
            return False

    async def _patch_recordedfuture_derived_columns(
        self, finding_id: str, columns: Dict[str, Any]
    ) -> bool:
        if not columns:
            return True
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            url = f"{self.api_base_url}/findings/typosquat/{finding_id}/recordedfuture-derived-columns"
            session = await self._get_session()
            async with session.patch(url, json=columns, headers=headers) as response:
                if response.status not in (200, 204):
                    response_text = await response.text()
                    logger.error(
                        f"PATCH recordedfuture-derived-columns failed for {finding_id}: "
                        f"HTTP {response.status} {response_text}"
                    )
                    return False
                return True
        except Exception as e:
            logger.error(f"Error PATCH recordedfuture-derived-columns for {finding_id}: {e}")
            return False

    async def _patch_recordedfuture_data_only(
        self, finding_id: str, recordedfuture_data: Dict[str, Any]
    ) -> bool:
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            url = f"{self.api_base_url}/findings/typosquat/{finding_id}/recordedfuture-data"
            session = await self._get_session()
            async with session.patch(
                url, json={"recordedfuture_data": recordedfuture_data}, headers=headers
            ) as response:
                if response.status not in (200, 204):
                    response_text = await response.text()
                    logger.error(
                        f"PATCH recordedfuture_data failed for {finding_id}: "
                        f"HTTP {response.status} {response_text}"
                    )
                    return False
                return True
        except Exception as e:
            logger.error(f"Error PATCH recordedfuture_data for {finding_id}: {e}")
            return False

    async def _refresh_threatstream_intel_after_rf_update(
        self,
        finding_id: str,
        domain_name: str,
        program_name: str,
        existing_ts: Optional[Dict[str, Any]],
    ) -> None:
        """Merge ThreatStream ?value= intel into stored threatstream_data after an RF update."""
        try:
            ts_creds = await self._get_vendor_credentials(program_name, "threatstream")
            if not ts_creds:
                return
            ts_adapter = ThreatStreamAdapter(self.timeout)
            session = await self._get_session()
            blob = await ts_adapter.fetch_intelligence_by_value(domain_name, ts_creds, session)
            if not blob:
                return
            merged = {**(existing_ts or {}), **blob}
            merged["last_fetched"] = blob.get("last_fetched") or merged.get("last_fetched")
            await self._patch_threatstream_data(finding_id, merged)
            logger.info(f"Merged ThreatStream intel for existing finding {domain_name}")
        except Exception as e:
            logger.warning(f"Could not refresh ThreatStream intel for {domain_name}: {e}")

    async def _enrich_single_finding_cross_vendor(
        self,
        finding: Dict[str, Any],
        program_name: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Best-effort second-vendor enrichment; failures are logged only."""
        domain = (finding.get("typo_domain") or "").strip()
        if not domain:
            return

        try:
            if self.api_vendor == "recordedfuture":
                ts_creds = await self._get_vendor_credentials(program_name, "threatstream")
                if not ts_creds:
                    return
                ts_adapter = ThreatStreamAdapter(self.timeout)
                blob = await ts_adapter.fetch_intelligence_by_value(domain, ts_creds, session)
                if blob:
                    finding["threatstream_data"] = blob
                    logger.debug(f"Cross-vendor ThreatStream enrichment for {domain}")
            else:
                rf_creds = await self._get_vendor_credentials(program_name, "recordedfuture")
                if not rf_creds or not rf_creds.get("rf_token"):
                    return
                rf_adapter = RecordedFutureAdapter(self.timeout)
                domain_data = await rf_adapter.fetch_enrichment_for_domain(
                    domain, rf_creds["rf_token"], session
                )
                if not domain_data:
                    return
                finding["recordedfuture_data"] = rf_adapter.build_recordedfuture_vendor_blob(
                    domain_data
                )
                logger.debug(f"Cross-vendor RecordedFuture enrichment for {domain} (recordedfuture_data only)")
        except Exception as e:
            logger.warning(f"Cross-vendor enrichment skipped for {domain}: {e}")

    async def fetch_existing_domains_for_program(self, program_name: str) -> set:
        """Fetch all existing typosquat domains for a program to avoid duplicates with optimized bulk fetching"""
        try:
            if self.existing_domains_cache:
                logger.debug(
                    f"Using cached domains for program {program_name}: {len(self.existing_domains_cache)} domains"
                )
                return self.existing_domains_cache

            logger.info(f"Fetching existing typosquat domains for program {program_name}")
            existing_domains = set()
            page = 1
            page_size = 500  # Larger page size for better performance

            while True:
                search_data = {
                    "hide_false_positives": False,
                    "program": program_name,
                    "sort_by": "timestamp",
                    "sort_dir": "desc",
                    "page": page,
                    "page_size": page_size,
                }

                headers = {"Content-Type": "application/json"}
                if self.api_token:
                    headers["Authorization"] = f"Bearer {self.api_token}"

                url = f"{self.api_base_url}/findings/typosquat/search"

                session = await self._get_session()
                async with session.post(url, json=search_data, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        items = data.get("items", [])
                        if not items:
                            break

                        page_domains = {
                            item.get("typo_domain", "").strip()
                            for item in items
                            if item.get("typo_domain", "").strip()
                        }
                        existing_domains.update(page_domains)

                        logger.debug(f"Page {page}: Found {len(items)} domains, {len(page_domains)} unique")

                        total_pages = data.get("pagination", {}).get("total_pages", 1)
                        if page >= total_pages:
                            break

                        page += 1

                    else:
                        response_text = await response.text()
                        logger.error(
                            f"Failed to fetch existing domains for program {program_name}: "
                            f"HTTP {response.status} - {response_text}"
                        )
                        break

            logger.info(f"Cached {len(existing_domains)} existing domains for program {program_name}")
            self.existing_domains_cache = existing_domains
            return existing_domains

        except Exception as e:
            logger.error(f"Error fetching existing domains for program {program_name}: {str(e)}")
            return set()



    async def update_job_status(self, status: str, progress: int, message: str, results: Optional[Dict[str, Any]] = None):
        """Update job status via API with connection pooling"""
        try:
            update_data = {
                "status": status,
                "progress": progress,
                "message": message
            }

            if results is not None:
                update_data["results"] = results

            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/jobs/{self.job_id}/status"
            session = await self._get_session()
            async with session.put(url, json=update_data, headers=headers) as response:
                    if response.status not in [200, 204]:
                        response_text = await response.text()
                        logger.warning(f"Failed to update job {self.job_id} status: HTTP {response.status} - {response_text}")
                    else:
                        logger.info(f"Updated job {self.job_id} status to {status} ({progress}%)")

        except Exception as e:
            logger.error(f"Error updating job status for {self.job_id}: {str(e)}")
    
    async def _handle_recordedfuture_post_storage(self, findings: List[Dict[str, Any]], program_name: str):
        """Handle RecordedFuture post-storage tasks (e.g. screenshots)."""
        try:
            rf_candidates = [
                f
                for f in findings
                if (f.get("recordedfuture_data") or {}).get("raw_details")
                and (
                    (f.get("recordedfuture_data") or {}).get("alert_id")
                    or (f.get("recordedfuture_data") or {})
                    .get("raw_alert", {})
                    .get("playbook_alert_id")
                )
            ]
            if not rf_candidates:
                return

            logger.info(
                f"Handling RecordedFuture post-storage tasks for {len(rf_candidates)} "
                f"of {len(findings)} findings"
            )

            api_credentials = await self._get_vendor_credentials(program_name, "recordedfuture")
            if not api_credentials or not api_credentials.get("rf_token"):
                logger.warning("No RecordedFuture credentials available for post-storage tasks")
                return

            rf_token = api_credentials["rf_token"]
            session = await self._get_session()
            rf_adapter = RecordedFutureAdapter(self.timeout)
            await rf_adapter.process_post_storage_tasks(
                rf_candidates, program_name, rf_token, session
            )

        except Exception as e:
            logger.error(f"Error in RecordedFuture post-storage tasks: {str(e)}")

    async def _update_existing_findings(self, existing_domains_data: List[Dict[str, Any]], program_name: str):
        """Update existing findings with fresh vendor data (similar to sync task)"""
        logger.info(f"Updating {len(existing_domains_data)} existing findings for program {program_name}")

        try:
            # Get API credentials for this program
            api_credentials = await self.get_program_api_credentials(program_name)
            if not api_credentials:
                logger.error(f"No {self.api_vendor} API credentials found for updating existing findings")
                return

            # For each existing domain, fetch its current finding data and update it
            for domain_data in existing_domains_data:
                domain_name = domain_data.get("typo_domain", "").strip()

                try:
                    # Get the existing finding from the database
                    existing_finding = await self._get_existing_finding_by_domain(domain_name, program_name)
                    if not existing_finding:
                        logger.warning(f"Could not find existing finding for domain {domain_name}")
                        continue

                    finding_id = existing_finding.get("id")
                    logger.debug(f"Found existing finding {finding_id} for domain {domain_name}")

                    # Create fresh finding data from vendor
                    fresh_finding_data = self.vendor_adapter.create_finding_data(domain_data, program_name)

                    # For RecordedFuture, handle status and assignee updates
                    if self.api_vendor == "recordedfuture":
                        await self._update_recordedfuture_finding(existing_finding, fresh_finding_data, finding_id, domain_name, program_name)
                    else:
                        await self._update_generic_finding(
                            existing_finding,
                            fresh_finding_data,
                            finding_id,
                            domain_name,
                            program_name,
                        )

                except Exception as e:
                    logger.error(f"Error updating existing finding for domain {domain_name}: {str(e)}")
                    self.results["error_count"] += 1
                    self.results["errors"].append({
                        "domain": domain_name,
                        "program": program_name,
                        "error": f"Failed to update existing finding: {str(e)}"
                    })

        except Exception as e:
            logger.error(f"Error in _update_existing_findings: {str(e)}")

    async def _get_existing_finding_by_domain(self, domain_name: str, program_name: str) -> Optional[Dict[str, Any]]:
        """Get existing finding by domain name and program"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # Search for the specific domain
            search_data = {
                "hide_false_positives": False,
                "program": program_name,
                "search": domain_name,  # Search for exact domain
                "page": 1,
                "page_size": 10
            }

            url = f"{self.api_base_url}/findings/typosquat/search"
            session = await self._get_session()

            async with session.post(url, json=search_data, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get("items", [])

                    # Find exact match
                    for item in items:
                        if item.get("typo_domain", "").strip().lower() == domain_name.lower():
                            return item

                    logger.warning(f"No exact match found for domain {domain_name}")
                    return None
                else:
                    response_text = await response.text()
                    logger.error(f"Failed to search for existing finding: HTTP {response.status} - {response_text}")
                    return None

        except Exception as e:
            logger.error(f"Error getting existing finding for domain {domain_name}: {str(e)}")
            return None

    async def _update_recordedfuture_finding(self, existing_finding: Dict[str, Any], fresh_finding_data: Dict[str, Any], finding_id: str, domain_name: str, program_name: str):
        """Update RecordedFuture finding with status/assignee and data changes"""
        try:
            # Extract RecordedFuture data from fresh finding
            # Handle case where recordedfuture_data might be None
            fresh_rf_data = fresh_finding_data.get("recordedfuture_data") or {}
            existing_rf_data = existing_finding.get("recordedfuture_data") or {}

            # Check if RF data has changed
            data_changed = self._has_recordedfuture_data_changed(existing_rf_data, fresh_rf_data)

            # Extract status and assignee updates
            status_updates = await self._extract_rf_status_and_assignee_updates(fresh_rf_data, existing_finding)

            if data_changed or status_updates:
                # Update RF data with fresh information
                updated_rf_data = existing_rf_data.copy()
                updated_rf_data.update(fresh_rf_data)
                updated_rf_data["last_fetched"] = datetime.now(timezone.utc).isoformat()

                # Use comprehensive update similar to sync task
                success = await self._update_finding_comprehensive(finding_id, updated_rf_data, status_updates)

                if success:
                    # If unassignment was requested (assigned_to set to None), also unassign in RecordedFuture
                    if status_updates.get("assigned_to") is None:
                        # Unassign in RecordedFuture API
                        await self._unassign_recordedfuture_alert(fresh_finding_data, program_name)
                    
                    self.results["success_count"] += 1
                    change_types = []
                    if data_changed:
                        change_types.append("RF data")
                    if status_updates:
                        change_types.append("status/assignee")

                    # Track the updated finding
                    self.results["updated_domains"].append({
                        "domain": domain_name,
                        "program": program_name,
                        "source": self.api_vendor,
                        "changes": change_types,
                        "status": "updated"
                    })

                    logger.info(f"✅ Updated existing finding for {domain_name}: {', '.join(change_types)}")
                else:
                    self.results["error_count"] += 1
                    self.results["errors"].append({
                        "domain": domain_name,
                        "error": "Failed to update finding via API"
                    })
            else:
                logger.info(f"⏭️  No changes needed for existing finding {domain_name}")

        except Exception as e:
            logger.error(f"Error updating RecordedFuture finding for {domain_name}: {str(e)}")
            raise
        finally:
            await self._refresh_threatstream_intel_after_rf_update(
                finding_id,
                domain_name,
                program_name,
                existing_finding.get("threatstream_data"),
            )

    async def _update_generic_finding(
        self,
        existing_finding: Dict[str, Any],
        fresh_finding_data: Dict[str, Any],
        finding_id: str,
        domain_name: str,
        program_name: str,
    ):
        """Update ThreatStream-backed finding and merge RecordedFuture cross-enrichment."""
        try:
            session = await self._get_session()
            change_tags: List[str] = []
            merged_rf: Optional[Dict[str, Any]] = None

            fresh_ts = fresh_finding_data.get("threatstream_data") or {}
            if fresh_ts:
                existing_ts = existing_finding.get("threatstream_data") or {}
                merged_ts = {**existing_ts, **fresh_ts}
                merged_ts["last_fetched"] = fresh_ts.get(
                    "last_fetched", datetime.now(timezone.utc).isoformat()
                )
                if await self._patch_threatstream_data(finding_id, merged_ts):
                    change_tags.append("threatstream_data")

            rf_creds = await self._get_vendor_credentials(program_name, "recordedfuture")
            if rf_creds and rf_creds.get("rf_token"):
                rf_adapter = RecordedFutureAdapter(self.timeout)
                domain_data = await rf_adapter.fetch_enrichment_for_domain(
                    domain_name, rf_creds["rf_token"], session
                )
                if domain_data:
                    rf_blob = rf_adapter.build_recordedfuture_vendor_blob(domain_data)
                    existing_rf = existing_finding.get("recordedfuture_data") or {}
                    merged_rf = {**existing_rf, **rf_blob}
                    merged_rf["last_fetched"] = rf_blob.get("last_fetched")
                    if await self._patch_recordedfuture_data_only(finding_id, merged_rf):
                        change_tags.append("recordedfuture_data")

            if change_tags:
                self.results["success_count"] += 1
                self.results["updated_domains"].append({
                    "domain": domain_name,
                    "program": program_name,
                    "source": self.api_vendor,
                    "changes": change_tags,
                    "status": "updated",
                })
                logger.info(f"Updated ThreatStream finding for {domain_name}: {change_tags}")

            if merged_rf and merged_rf.get("raw_details"):
                await self._handle_recordedfuture_post_storage(
                    [{"typo_domain": domain_name, "recordedfuture_data": merged_rf}],
                    program_name,
                )

        except Exception as e:
            logger.error(f"Error updating generic finding for {domain_name}: {str(e)}")
            raise

    def _has_recordedfuture_data_changed(self, existing_rf_data: Dict[str, Any], fresh_rf_data: Dict[str, Any]) -> bool:
        """Check if RecordedFuture data has changed"""
        try:
            # Ensure both are dictionaries (handle None case)
            existing_rf_data = existing_rf_data or {}
            fresh_rf_data = fresh_rf_data or {}
            
            # Compare key fields that indicate changes
            key_fields = ["entity_criticality", "risk_score", "targets", "context_list", "assignee_name"]

            for field in key_fields:
                existing_value = existing_rf_data.get(field)
                fresh_value = fresh_rf_data.get(field)

                if existing_value != fresh_value:
                    logger.debug(f"Change detected in RF field {field}: {existing_value} -> {fresh_value}")
                    return True

            # Check raw alert data if available
            existing_raw = existing_rf_data.get("raw_alert", {})
            fresh_raw = fresh_rf_data.get("raw_alert", {})

            if existing_raw != fresh_raw:
                logger.debug("Change detected in raw_alert data")
                return True

            return False

        except Exception as e:
            logger.warning(f"Error comparing RecordedFuture data, assuming changed: {str(e)}")
            return True

    async def _extract_rf_status_and_assignee_updates(self, fresh_rf_data: Dict[str, Any], existing_finding: Dict[str, Any]) -> Dict[str, Any]:
        """Extract status and assignee updates from RecordedFuture data (similar to sync task)"""
        status_updates = {}

        try:
            # Ensure fresh_rf_data is a dictionary (handle None case)
            fresh_rf_data = fresh_rf_data or {}
            
            # For RecordedFuture, extract status from the data structure
            fresh_raw_alert = fresh_rf_data.get("raw_alert", {})
            if fresh_raw_alert:
                # Extract status mapping (same as sync task logic)
                rf_status = fresh_raw_alert.get("status", "").lower()
                current_status = existing_finding.get("status")

                # Map RF status to finding status
                if rf_status == "inprogress" or rf_status == "in progress":
                    new_status = "inprogress"
                elif rf_status == "resolved":
                    new_status = "resolved"
                elif rf_status == "closed":
                    new_status = "dismissed"
                elif rf_status == "new":
                    new_status = "new"
                else:
                    new_status = None

                # Get current assignee for unassignment check
                current_assigned_to = existing_finding.get("assigned_to")
                
                # Only update status if it changed and we have a valid mapping
                if new_status and new_status != current_status:
                    status_updates["status"] = new_status
                    logger.info(f"Status change detected: {current_status} -> {new_status} (RF: {rf_status})")

                # Handle assignee updates - special case: if imported status is "new", unassign if there's a current assignee
                if new_status == "new" and current_assigned_to:
                    # Imported status is "new" (either changed or already "new") and finding has an assignee - unassign
                    status_updates["assigned_to"] = None
                    logger.info(f"Imported status is 'new' and finding has assignee {current_assigned_to} - unassigning")
                elif new_status and new_status != "new":
                    # Normal assignee handling for non-"new" status
                    assignee_name = fresh_rf_data.get("assignee_name")
                    if assignee_name:
                        # Get user ID by RF uhash (reuse existing logic)
                        assigned_to_id = await self._get_user_id_by_rf_uhash(assignee_name)

                        if assigned_to_id and assigned_to_id != current_assigned_to:
                            status_updates["assigned_to"] = assigned_to_id
                            logger.info(f"Assignee change detected: {current_assigned_to} -> {assigned_to_id} (RF: {assignee_name})")
                # If new_status is None or "new" without assignee, don't change assignment

            # If we have assignee updates but no status updates, include current status
            # because the API requires the status field to be present
            if "assigned_to" in status_updates and "status" not in status_updates:
                current_status = existing_finding.get("status", "new")
                status_updates["status"] = current_status
                logger.debug(f"Including current status '{current_status}' for assignee update")

            return status_updates

        except Exception as e:
            logger.error(f"Error extracting RF status/assignee updates: {str(e)}")
            return {}

    async def _get_user_id_by_rf_uhash(self, rf_uhash: str) -> Optional[str]:
        """Get user ID by RF uhash from global users list (reuse from existing logic)"""
        try:
            all_users = await self._get_all_users()

            # Find user with matching rf_uhash
            for user in all_users:
                if user.get("rf_uhash") == rf_uhash:
                    user_id = user.get("id")
                    logger.debug(f"Found user {user_id} for RF uhash {rf_uhash}")
                    return user_id

            logger.debug(f"No user found with RF uhash {rf_uhash} in system")
            return None

        except Exception as e:
            logger.error(f"Error looking up user by RF uhash {rf_uhash}: {str(e)}")
            return None

    async def _update_finding_comprehensive(self, finding_id: str, updated_rf_data: Dict[str, Any], status_updates: Dict[str, Any]) -> bool:
        """Update finding with both RF data and status/assignee changes (similar to sync task)"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            session = await self._get_session()

            # First, update the RecordedFuture data if we have RF data
            if updated_rf_data:
                rf_payload = {"recordedfuture_data": updated_rf_data}
                rf_url = f"{self.api_base_url}/findings/typosquat/{finding_id}/recordedfuture-data"

                async with session.patch(rf_url, json=rf_payload, headers=headers) as response:
                    if response.status not in [200, 204]:
                        response_text = await response.text()
                        logger.error(f"Failed to update RF data for finding {finding_id}: HTTP {response.status} - {response_text}")
                        return False

                logger.debug(f"Updated RF data for finding {finding_id}")

            # Then, update status and assignee if there are changes
            if status_updates:
                status_url = f"{self.api_base_url}/findings/typosquat/{finding_id}/status"

                # Create status update payload
                status_payload = {}
                if "status" in status_updates:
                    status_payload["status"] = status_updates["status"]
                if "assigned_to" in status_updates:
                    status_payload["assigned_to"] = status_updates["assigned_to"]

                logger.debug(f"Updating finding {finding_id} status/assignee: {status_payload}")

                async with session.put(status_url, json=status_payload, headers=headers) as response:
                    if response.status not in [200, 204]:
                        response_text = await response.text()
                        logger.error(f"Failed to update status/assignee for finding {finding_id}: HTTP {response.status} - {response_text}")
                        return False

                logger.debug(f"Updated status/assignee for finding {finding_id}: {status_payload}")

            return True

        except Exception as e:
            logger.error(f"Error updating finding {finding_id} comprehensively: {str(e)}")
            return False

    async def _resolve_recordedfuture_assignees(self, findings: List[Dict[str, Any]]):
        """Resolve RecordedFuture assignee uhashes to user IDs; unassign in RF when status is new.

        Call only for RecordedFuture-primary gathers. ThreatStream jobs that only merge RF enrichment
        must not use this (no assignment mapping, no playbook PUT).
        """
        try:
            logger.info(f"Resolving RecordedFuture assignees for {len(findings)} findings")

            users = await self._get_all_users()
            if not users:
                logger.warning("No users found in system")
                for finding in findings:
                    await self._check_and_unassign_new_finding(finding, self.program_name)
                return

            # Create a mapping of RF assignee names to user IDs via rf_uhash
            assignee_to_user_map = {}
            for user in users:
                rf_uhash = user.get("rf_uhash")
                if rf_uhash:
                    assignee_to_user_map[rf_uhash] = user.get("id")
                    logger.debug(f"Added user mapping: rf_uhash='{rf_uhash}' -> user_id='{user.get('id')}'")

            # Update findings with resolved assignees (skip assignment for status "new")
            updated_count = 0
            unassigned_count = 0
            for finding in findings:
                try:
                    # Check if finding status is "new" (case-insensitive)
                    finding_status = finding.get("status", "").lower()
                    # Handle case where recordedfuture_data might be None
                    rf_data = finding.get("recordedfuture_data") or {}
                    
                    # Check for assignee information in the RF data
                    assignee_name = rf_data.get("assignee_name")
                    if not assignee_name:
                        # Also check in raw_alert data
                        raw_alert = rf_data.get("raw_alert", {})
                        assignee_name = raw_alert.get("assignee_name")
                        # Also check status in raw_alert if not found in finding
                        if not finding_status and raw_alert.get("status"):
                            finding_status = raw_alert.get("status", "").lower()

                    logger.debug(f"Finding {finding.get('typo_domain')}: status='{finding_status}', assignee_name='{assignee_name}'")

                    # If status is "new" and there's an assignee, unassign instead of assigning
                    if finding_status == "new" and assignee_name:
                        logger.info(
                            f"Finding {finding.get('typo_domain')} has status 'new' with assignee "
                            f"'{assignee_name}' - unassigning"
                        )
                        finding.pop("assigned_to", None)
                        try:
                            await self._unassign_recordedfuture_alert(finding, self.program_name)
                        except Exception as unassign_error:
                            logger.warning(
                                f"Failed to unassign RecordedFuture alert for "
                                f"{finding.get('typo_domain')}: {str(unassign_error)}"
                            )
                        unassigned_count += 1
                    elif assignee_name and assignee_name in assignee_to_user_map:
                        # Normal assignment for non-"new" status findings
                        user_id = assignee_to_user_map[assignee_name]
                        finding["assigned_to"] = user_id
                        updated_count += 1
                        logger.info(f"Assigned finding {finding.get('typo_domain')} to user {user_id} (RF: {assignee_name})")
                    elif assignee_name:
                        logger.warning(f"No user mapping found for RF assignee '{assignee_name}' for finding {finding.get('typo_domain')}")
                    elif finding_status == "new":
                        # Status is "new" but no assignee - ensure no assignment
                        finding.pop("assigned_to", None)
                        logger.debug(f"Finding {finding.get('typo_domain')} has status 'new' with no assignee - keeping unassigned")
                except Exception as finding_error:
                    logger.error(f"Error processing finding {finding.get('typo_domain', 'unknown')} in assignee resolution: {str(finding_error)}")
                    # Continue processing other findings even if one fails
                    continue

            logger.info(f"Resolved assignees: {updated_count} assigned, {unassigned_count} unassigned (status 'new') out of {len(findings)} RecordedFuture findings")

        except Exception as e:
            logger.error(f"Error resolving RecordedFuture assignees: {str(e)}")
    
    async def _check_and_unassign_new_finding(self, finding: Dict[str, Any], program_name: str):
        """Clear local assignee and unassign in RF when status is new and RF shows an assignee."""
        try:
            finding_status = finding.get("status", "").lower()
            rf_data = finding.get("recordedfuture_data") or {}

            assignee_name = rf_data.get("assignee_name")
            if not assignee_name:
                raw_alert = rf_data.get("raw_alert", {})
                assignee_name = raw_alert.get("assignee_name")
                if not finding_status and raw_alert.get("status"):
                    finding_status = raw_alert.get("status", "").lower()

            if finding_status == "new" and assignee_name:
                logger.info(
                    f"Finding {finding.get('typo_domain')} has status 'new' with assignee - unassigning"
                )
                finding.pop("assigned_to", None)
                try:
                    await self._unassign_recordedfuture_alert(finding, program_name)
                except Exception as unassign_error:
                    logger.warning(
                        f"Failed to unassign RecordedFuture alert for "
                        f"{finding.get('typo_domain')}: {str(unassign_error)}"
                    )
        except Exception as e:
            logger.error(f"Error checking/unassigning new finding: {str(e)}")

    async def _unassign_recordedfuture_alert(self, finding: Dict[str, Any], program_name: str):
        """Unassign a RecordedFuture alert via API call"""
        try:
            # Handle case where recordedfuture_data might be None
            rf_data = finding.get("recordedfuture_data") or {}
            alert_id = rf_data.get("alert_id")
            
            if not alert_id:
                logger.warning(f"No alert_id found in RecordedFuture data for finding {finding.get('typo_domain')}")
                logger.debug(f"RecordedFuture data keys: {list(rf_data.keys())}")
                # Try to get alert_id from raw_alert if not in main rf_data
                raw_alert = rf_data.get("raw_alert", {})
                alert_id = raw_alert.get("playbook_alert_id")
                if not alert_id:
                    logger.warning(f"No alert_id found in raw_alert either for finding {finding.get('typo_domain')}")
                    return
                else:
                    logger.info(f"Found alert_id in raw_alert: {alert_id}")
            
            api_credentials = await self._get_vendor_credentials(program_name, "recordedfuture")
            if not api_credentials:
                logger.warning(
                    f"No RecordedFuture API credentials found for program {program_name}, cannot unassign alert"
                )
                return

            rf_token = api_credentials.get("rf_token")
            if not rf_token:
                logger.warning(f"No RecordedFuture token found for program {program_name}, cannot unassign alert")
                return
            
            # Get current status from finding or RF data
            finding_status = finding.get("status", "new")
            rf_status = rf_data.get("status", finding_status)
            
            # Map internal status to RecordedFuture status format
            # Use "New" as default if status mapping fails
            status_mapping = {
                "new": "New",
                "inprogress": "InProgress",
                "resolved": "Resolved",
                "dismissed": "Closed"
            }
            rf_status_mapped = status_mapping.get(finding_status.lower(), "New")
            
            # Make API call to unassign the alert
            url = f"https://api.recordedfuture.com/playbook-alert/common/{alert_id}"
            headers = {
                "Accept": "application/json",
                "X-RFToken": rf_token,
                "Content-Type": "application/json"
            }
            
            # Payload with assignee set to null to unassign
            # Explicitly set to None which will serialize to null in JSON
            payload = {
                "status": rf_status_mapped,
                "assignee": None
            }
            
            # Serialize to JSON string to verify null is being sent correctly
            import json
            payload_json = json.dumps(payload, ensure_ascii=False)
            logger.info(f"Unassigning RecordedFuture alert {alert_id} for finding {finding.get('typo_domain')} (status: {rf_status_mapped})")
            logger.info(f"Unassignment request URL: {url}")
            logger.info(f"Unassignment payload JSON: {payload_json}")
            logger.debug(f"Unassignment payload dict: {payload}")
            
            session = await self._get_session()
            async with session.put(url, json=payload, headers=headers) as response:
                try:
                    response_data = await response.json()
                except Exception as json_error:
                    response_text = await response.text()
                    logger.error(f"Failed to parse JSON response from RecordedFuture API for alert {alert_id}: {str(json_error)}")
                    logger.debug(f"Response text: {response_text}")
                    return
                
                if response.status == 200:
                    # Log full response at INFO level for debugging
                    import json
                    response_json = json.dumps(response_data, indent=2, ensure_ascii=False)
                    logger.info(f"RecordedFuture API response for alert {alert_id} (HTTP {response.status}):")
                    logger.info(f"Response JSON:\n{response_json}")
                    
                    # Check if the response indicates success
                    status_obj = response_data.get("status", {})
                    status_code = status_obj.get("status_code") if isinstance(status_obj, dict) else None
                    
                    # Also check the data field for assignee information
                    response_data_field = response_data.get("data", {})
                    response_assignee = response_data_field.get("assignee") if isinstance(response_data_field, dict) else None
                    
                    # Log assignee status from response
                    logger.info(f"Response assignee value: {response_assignee} (type: {type(response_assignee).__name__})")
                    
                    if status_code == "Ok":
                        # Verify that assignee was actually unassigned
                        if response_assignee is None or response_assignee == "":
                            logger.info(f"Successfully unassigned RecordedFuture alert {alert_id} for finding {finding.get('typo_domain')}")
                        else:
                            logger.warning(f"RecordedFuture API returned success but assignee is still set to '{response_assignee}' for alert {alert_id}")
                            logger.warning("Full response was logged above")
                    else:
                        status_message = status_obj.get("status_message", "Unknown error") if isinstance(status_obj, dict) else str(response_data)
                        logger.warning(f"RecordedFuture API returned 200 but status_code is not 'Ok' for alert {alert_id}: {status_message}")
                        logger.warning("Full response was logged above")
                else:
                    response_text = await response.text()
                    logger.error(f"Failed to unassign RecordedFuture alert {alert_id}: HTTP {response.status} - {response_text}")
                    logger.debug(f"Request payload was: {payload}")
                    
        except Exception as e:
            logger.error(f"Error unassigning RecordedFuture alert for finding {finding.get('typo_domain')}: {str(e)}", exc_info=True)
            # Don't raise - unassignment failure shouldn't block import

    async def _check_domain_filtering(self, domains: List[str], program_name: str) -> Dict[str, Any]:
        """Call the pre-flight filter endpoint to determine which domains pass filtering."""
        fallback: Dict[str, Any] = {
            "filtering_enabled": False,
            "allowed": list(domains),
            "filtered": [],
            "summary": {"total": len(domains), "allowed": len(domains), "filtered": 0},
        }
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            session = await self._get_session()
            async with session.post(
                f"{self.api_base_url}/findings/typosquat/check-filter",
                json={"program_name": program_name, "domains": domains},
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(
                        f"Pre-flight filter: {data.get('summary', {}).get('allowed', 0)} allowed, "
                        f"{data.get('summary', {}).get('filtered', 0)} filtered"
                    )
                    return data
                else:
                    logger.warning(f"Filter check failed (HTTP {response.status}), allowing all domains")
                    return fallback
        except Exception as e:
            logger.warning(f"Filter check error ({e}), allowing all domains")
            return fallback

    async def _resolve_filtered_rf_alerts(self, filtered_domains: List[Dict[str, Any]], program_name: str):
        """Resolve RecordedFuture alerts for domains removed by pre-flight filtering."""
        try:
            api_credentials = await self._get_vendor_credentials(program_name, "recordedfuture")
            if not api_credentials:
                logger.warning(f"No RF credentials for {program_name}, cannot resolve filtered alerts")
                return

            rf_token = api_credentials.get("rf_token")
            if not rf_token:
                logger.warning(f"No RF token for {program_name}, cannot resolve filtered alerts")
                return

            session = await self._get_session()

            for domain_data in filtered_domains:
                domain_name = domain_data.get("typo_domain", "unknown")

                # alert_id lives at top level in raw domain_data from _merge_alert_data,
                # or nested under recordedfuture_data after create_finding_data
                alert_id = domain_data.get("alert_id")
                if not alert_id:
                    rf_data = domain_data.get("recordedfuture_data") or {}
                    alert_id = rf_data.get("alert_id")
                    if not alert_id:
                        raw_alert = rf_data.get("raw_alert", {})
                        alert_id = raw_alert.get("playbook_alert_id")
                if not alert_id:
                    raw_alert = domain_data.get("raw_alert", {})
                    alert_id = raw_alert.get("playbook_alert_id")

                if not alert_id:
                    logger.debug(f"No alert_id for filtered domain {domain_name}, skipping RF resolve")
                    continue

                try:
                    url = f"https://api.recordedfuture.com/playbook-alert/common/{alert_id}"
                    headers = {
                        "Accept": "application/json",
                        "X-RFToken": rf_token,
                        "Content-Type": "application/json",
                    }
                    payload = {"status": "Resolved", "assignee": None}

                    logger.info(f"Auto-resolving RF alert {alert_id} for filtered domain {domain_name}")
                    async with session.put(url, json=payload, headers=headers) as response:
                        if response.status == 200:
                            logger.info(f"Successfully resolved RF alert {alert_id} for filtered domain {domain_name}")
                        else:
                            response_text = await response.text()
                            logger.warning(f"Failed to resolve RF alert {alert_id}: HTTP {response.status} - {response_text}")
                except Exception as e:
                    logger.error(f"Error resolving RF alert {alert_id} for {domain_name}: {e}")

        except Exception as e:
            logger.error(f"Error in _resolve_filtered_rf_alerts: {e}")

    async def _get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users from global auth endpoint for assignee resolution"""
        try:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # Fetch all users with pagination
            all_users = []
            page = 1
            limit = 100  # Use larger limit to reduce API calls

            while True:
                url = f"{self.api_base_url}/auth/users?page={page}&limit={limit}"
                session = await self._get_session()
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        users = response_data.get("users", [])
                        if not users:
                            break
                        all_users.extend(users)

                        # Check if we have more pages
                        total = response_data.get("total", 0)
                        if len(all_users) >= total:
                            break
                        page += 1
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to fetch users: HTTP {response.status} - {response_text}")
                        break

            logger.info(f"Fetched {len(all_users)} users from global auth endpoint")
            return all_users

        except Exception as e:
            logger.error(f"Error getting users from auth endpoint: {str(e)}")
            return []

    async def test_api_connectivity(self):
        """Test API connectivity and basic functionality with connection pooling"""
        try:
            logger.info("Testing API connectivity...")

            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # Test basic API connectivity
            test_url = f"{self.api_base_url}/programs"
            session = await self._get_session()
            async with session.get(test_url, headers=headers) as response:
                    logger.info(f"API connectivity test - Status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"API connectivity test successful - Found {len(data.get('programs', []))} programs")
                    else:
                        response_text = await response.text()
                        logger.warning(f"API connectivity test failed - HTTP {response.status}: {response_text}")

        except Exception as e:
            logger.error(f"API connectivity test failed: {str(e)}")
            raise
