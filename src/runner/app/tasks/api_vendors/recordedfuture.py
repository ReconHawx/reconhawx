import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
import logging
import os

from .base import BaseAPIVendor
from .config import vendor_config
from utils.html_extractor import extract_text_from_image_ocr

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


class RecordedFutureAdapter(BaseAPIVendor):
    """RecordedFuture API vendor implementation"""

    def __init__(self, timeout: aiohttp.ClientTimeout):
        super().__init__("recordedfuture", timeout)
        
        # Load configuration from vendor config manager
        self.config = vendor_config.get_vendor_config("recordedfuture") or {}
        self.query_config = vendor_config.get_query_config("recordedfuture")
        self.retry_config = vendor_config.get_retry_config("recordedfuture")
        
        logger.info(f"RecordedFuture adapter initialized with config: {self.query_config}")

    def get_required_credentials(self) -> List[str]:
        """RecordedFuture requires RF token"""
        return ["rf_token"]

    def get_credential_fields(self) -> Dict[str, str]:
        """Mapping of internal names to database field names"""
        return {
            "rf_token": "recordedfuture_api_key"
        }

    async def gather_domains(self, api_credentials: Dict[str, str], program_name: str, session: Optional[aiohttp.ClientSession] = None, date_range_hours: Optional[int] = None, custom_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Gather domains from RecordedFuture API using two-stage approach:
        1. Search for playbook alerts
        2. Get detailed information for each alert

        Note: custom_query parameter is not supported by RecordedFuture API and will be ignored
        """
        if custom_query:
            logger.warning("Note: custom_query parameter is not supported by RecordedFuture API and will be ignored")

        logger.info(f"🔍 Making RecordedFuture API calls for program: {program_name}")

        # Extract and validate credentials
        rf_token = api_credentials.get("rf_token")

        if not self.validate_credentials({"rf_token": rf_token}):
            raise Exception("Missing API credentials: rf_token is required")

        try:
            domains = []
            
            # Stage 1: Get all playbook alerts
            alerts = await self._fetch_playbook_alerts(rf_token, session, date_range_hours)
            logger.info(f"Found {len(alerts)} playbook alerts from RecordedFuture")
            
            if not alerts:
                return domains
            
            # Stage 2: Get detailed information for each alert
            for alert in alerts:
                try:
                    alert_id = alert.get("playbook_alert_id")
                    if not alert_id:
                        logger.warning(f"Alert missing playbook_alert_id: {alert}")
                        continue
                    
                    # Get detailed information for this alert
                    alert_details = await self._fetch_alert_details(rf_token, alert_id, session)
                    if alert_details:
                        # Combine basic alert info with detailed info
                        domain_data = self._merge_alert_data(alert, alert_details)
                        if domain_data:
                            domains.append(domain_data)
                            
                    # Small delay between detail requests to be respectful
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error processing alert {alert.get('playbook_alert_id', 'unknown')}: {str(e)}")
                    self.api_stats['failed_requests'] += 1
                    continue

        except Exception as e:
            logger.error(f"Error gathering from RecordedFuture: {str(e)}")
            self.api_stats['failed_requests'] += 1
            raise

        self.api_stats['total_domains_found'] += len(domains)
        logger.info(f"Successfully gathered {len(domains)} domains from RecordedFuture API")
        return domains

    async def _fetch_playbook_alerts(self, rf_token: str, session: Optional[aiohttp.ClientSession] = None, date_range_hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch playbook alerts from RecordedFuture API (Stage 1)"""
        alerts = []
        from_offset = 0
        limit = self.query_config.get("limit", 100)
        
        # Build the updated_range if date_range_hours is provided
        updated_range = {}
        if date_range_hours:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            from_time = now - timedelta(hours=date_range_hours)

            updated_range = {
                "from": from_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "until": now.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            logger.info(f"Using date range filter: {updated_range['from']} to {updated_range['until']} ({date_range_hours} hours)")

        while True:
            self.api_stats['total_requests'] += 1

            # Build search payload
            search_payload = {
                "from": from_offset,
                "limit": limit,
                "order_by": self.query_config.get("order_by", "created"),
                "direction": self.query_config.get("direction", "asc"),
                "entity": [],
                "statuses": self.query_config.get("statuses"),
                "priority": [],
                "category": self.query_config.get("category", ["domain_abuse"]),
                "assignee": [],
                "created_range": {},
                "updated_range": updated_range,
                "organisation": []
            }
            
            url = "https://api.recordedfuture.com/playbook-alert/search"
            headers = {
                "Accept": "application/json",
                "X-RFToken": rf_token,
                "Content-Type": "application/json"
            }
            
            logger.info(f"RecordedFuture search request: offset={from_offset}, limit={limit}")
            logger.debug(f"RecordedFuture search payload: {search_payload}")
            # Make the request
            if session:
                async with session.post(url, json=search_payload, headers=headers) as response:
                    result = await self._process_search_response(response, alerts, limit, from_offset)
            else:
                async with aiohttp.ClientSession(timeout=self.timeout) as temp_session:
                    async with temp_session.post(url, json=search_payload, headers=headers) as response:
                        result = await self._process_search_response(response, alerts, limit, from_offset)
            
            if result == "break":
                break
            elif result == "continue":
                continue
            else:
                from_offset = result
                
            # Rate limiting delay
            delay = self.query_config.get("rate_limit_delay", 1)
            await asyncio.sleep(delay)
        
        return alerts

    async def _fetch_alert_details(self, rf_token: str, alert_id: str, session: Optional[aiohttp.ClientSession] = None, ignore_status_filter: bool = False) -> Optional[Dict[str, Any]]:
        """Fetch detailed information for a specific alert (Stage 2)

        Args:
            rf_token: RecordedFuture API token
            alert_id: Alert ID to fetch details for
            session: Optional aiohttp session
            ignore_status_filter: If True, fetch details regardless of alert status (used for sync operations)
        """
        self.api_stats['total_requests'] += 1

        # Build details payload
        details_payload = {
            "panels": self.query_config.get("details_panels", ["status", "dns", "whois"])
        }

        url = f"https://api.recordedfuture.com/playbook-alert/domain_abuse/{alert_id}"
        headers = {
            "Accept": "application/json",
            "X-RFToken": rf_token,
            "Content-Type": "application/json"
        }

        logger.debug(f"Fetching details for alert: {alert_id} (ignore_status_filter={ignore_status_filter})")

        try:
            # Make the request
            if session:
                async with session.post(url, json=details_payload, headers=headers) as response:
                    return await self._process_details_response(response, alert_id, ignore_status_filter)
            else:
                async with aiohttp.ClientSession(timeout=self.timeout) as temp_session:
                    async with temp_session.post(url, json=details_payload, headers=headers) as response:
                        return await self._process_details_response(response, alert_id, ignore_status_filter)

        except Exception as e:
            logger.error(f"Error fetching details for alert {alert_id}: {str(e)}")
            self.api_stats['failed_requests'] += 1
            return None

    async def _process_search_response(self, response, alerts: List[Dict[str, Any]], limit: int, from_offset: int):
        """Process search response and return next action"""
        if response.status == 200:
            data = await response.json()
            status = data.get("status", {})
            
            if status.get("status_code") != "Ok":
                logger.error(f"RecordedFuture API error: {status.get('status_message', 'Unknown error')}")
                return "break"
            
            alert_data = data.get("data", [])
            counts = data.get("counts", {})
            
            logger.info(f"API response: {len(alert_data)} alerts returned, {counts.get('total', 0)} total")
            
            if not alert_data:
                logger.info(f"No more alerts returned at offset {from_offset}")
                return "break"
            
            alerts.extend(alert_data)
            
            # Check if we got fewer alerts than the limit (last page)
            if len(alert_data) < limit:
                self.api_stats['successful_requests'] += 1
                return "break"
            
            self.api_stats['successful_requests'] += 1
            return from_offset + limit
            
        elif response.status == 401:
            response_text = await response.text()
            logger.error(f"Authentication failed: {response_text}")
            raise Exception("Authentication failed - check RF token")
        elif response.status == 429:
            wait_time = self.retry_config.get("rate_limit_wait", 60)
            logger.warning(f"Rate limited by RecordedFuture API, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
            return "continue"
        else:
            response_text = await response.text()
            logger.error(f"RecordedFuture API error {response.status}: {response_text}")
            raise Exception(f"RecordedFuture API error {response.status}: {response_text}")

    async def _process_details_response(self, response, alert_id: str, ignore_status_filter: bool = False) -> Optional[Dict[str, Any]]:
        """Process details response for a specific alert

        Args:
            response: HTTP response object
            alert_id: Alert ID being processed
            ignore_status_filter: If True, return details regardless of alert status
        """
        if response.status == 200:
            data = await response.json()
            status = data.get("status", {})

            if status.get("status_code") != "Ok":
                logger.error(f"RecordedFuture details API error for {alert_id}: {status.get('status_message', 'Unknown error')}")
                return None

            alert_data = data.get("data")
            if not alert_data:
                logger.warning(f"No data returned for alert {alert_id}")
                return None

            # If ignore_status_filter is True (sync operation), return all alerts regardless of status
            if ignore_status_filter:
                logger.debug(f"Returning alert {alert_id} data (status filter ignored for sync)")
                self.api_stats['successful_requests'] += 1
                return alert_data

            # For gather operations, check if alert status matches our filter criteria
            panel_status = alert_data.get("panel_status", {})
            alert_status = panel_status.get("status", "").lower()

            # Only return alerts that match our status filter (for gather operations)
            allowed_statuses = [s.lower() for s in self.query_config.get("statuses")]
            if alert_status in allowed_statuses:
                logger.debug(f"Alert {alert_id} status '{alert_status}' matches filter, returning data")
                self.api_stats['successful_requests'] += 1
                return alert_data
            else:
                logger.debug(f"Alert {alert_id} status '{alert_status}' does not match filter {allowed_statuses}, skipping")
                return None

        elif response.status == 401:
            response_text = await response.text()
            logger.error(f"Authentication failed for details {alert_id}: {response_text}")
            raise Exception("Authentication failed - check RF token")
        elif response.status == 429:
            wait_time = self.retry_config.get("rate_limit_wait", 60)
            logger.warning(f"Rate limited by RecordedFuture API, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
            return None
        else:
            response_text = await response.text()
            logger.error(f"RecordedFuture details API error {response.status} for {alert_id}: {response_text}")
            return None

    def _merge_alert_data(self, alert: Dict[str, Any], details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Merge basic alert info with detailed information and preserve raw data"""
        try:
            # Extract domain from alert title or entity_name
            domain = alert.get("title", "")
            if details and details.get("panel_status"):
                domain = details["panel_status"].get("entity_name", domain)
            
            if not domain:
                logger.warning(f"No domain found in alert {alert.get('playbook_alert_id')}")
                return None
            
            # Create the main domain data structure with extracted key fields for easy access
            domain_data = {
                # Required field for the finding
                "typo_domain": domain,
                
                # Key extracted fields for quick reference
                "alert_id": alert.get("playbook_alert_id"),
                "status": alert.get("status"),
                "priority": alert.get("priority"),
                "category": alert.get("category"),
                "created": alert.get("created"),
                "updated": alert.get("updated"),
                "assignee_name": alert.get("assignee_name"),
                "owner_name": alert.get("owner_name"),
                "organisation_name": alert.get("organisation_name"),
                
                # Preserve complete raw data from both API calls
                "raw_alert": alert,  # Complete alert data from search API
                "raw_details": details  # Complete details data from details API
            }
            
            # Extract commonly used fields from details for easier access
            if details:
                panel_status = details.get("panel_status", {})
                panel_dns = details.get("panel_evidence_dns", {})
                panel_whois = details.get("panel_evidence_whois", {})
                
                # Add key status panel fields for easier access
                domain_data.update({
                    "entity_id": panel_status.get("entity_id"),
                    "entity_criticality": panel_status.get("entity_criticality"),
                    "risk_score": panel_status.get("risk_score"),
                    "targets": panel_status.get("targets", []),
                    "context_list": panel_status.get("context_list", [])
                })

                # Override status with the one from panel_status if available
                if panel_status.get("status"):
                    extracted_status = panel_status.get("status")
                    domain_data["status"] = extracted_status
                    logger.info(f"Extracted status from panel_status for {domain}: '{extracted_status}'")

                # Override assignee with the one from panel_status if available
                if panel_status.get("assignee_id"):
                    # Extract the uhash value from assignee_id (format: "uhash:7DFz7Cw2GV")
                    assignee_id = panel_status.get("assignee_id")
                    if assignee_id.startswith("uhash:"):
                        domain_data["assignee_name"] = assignee_id[6:]  # Remove "uhash:" prefix
                    else:
                        domain_data["assignee_name"] = assignee_id
                
                # Extract WHOIS data for database columns
                whois_data = self._extract_whois_data(panel_whois)
                domain_data.update(whois_data)
                
                # Extract DNS data for database columns
                dns_data = self._extract_dns_data(panel_dns)
                domain_data.update(dns_data)
            
            return domain_data
            
        except Exception as e:
            logger.error(f"Error merging alert data for {alert.get('playbook_alert_id')}: {str(e)}")
            return None

    def _select_alert_for_domain_entity_search(
        self, alert_rows: List[Dict[str, Any]], typo_domain: str
    ) -> Optional[Dict[str, Any]]:
        if not alert_rows:
            return None
        td = typo_domain.strip().lower()
        domain_abuse = [a for a in alert_rows if a.get("category") == "domain_abuse"]
        candidates = domain_abuse if domain_abuse else list(alert_rows)
        for a in candidates:
            title = (a.get("title") or "").strip().lower()
            if title == td:
                return a
        for a in candidates:
            title = (a.get("title") or "").strip().lower()
            if title.endswith(td) or td in title:
                return a
        return candidates[0]

    async def fetch_enrichment_for_domain(
        self,
        typo_domain: str,
        rf_token: str,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a typo domain to playbook alert details via entity search + domain_abuse panel
        (ignore_status_filter on details so Resolved/Closed alerts still enrich).
        """
        domain_clean = (typo_domain or "").strip()
        if not domain_clean:
            return None

        url = "https://api.recordedfuture.com/playbook-alert/search"
        headers = {
            "Accept": "application/json",
            "X-RFToken": rf_token,
            "Content-Type": "application/json",
        }

        async def _post_search(category_value: List[str]) -> Optional[Dict[str, Any]]:
            search_payload = {
                "from": 0,
                "limit": 100,
                "order_by": self.query_config.get("order_by", "created"),
                "direction": self.query_config.get("direction", "asc"),
                "entity": [f"idn:{domain_clean}"],
                "statuses": [],
                "priority": [],
                "category": category_value,
                "assignee": [],
                "created_range": {},
                "updated_range": {},
                "organisation": [],
            }
            if session:
                async with session.post(url, json=search_payload, headers=headers) as response:
                    return await self._parse_entity_search_response(response)
            async with aiohttp.ClientSession(timeout=self.timeout) as temp_session:
                async with temp_session.post(url, json=search_payload, headers=headers) as response:
                    return await self._parse_entity_search_response(response)

        try:
            parsed = await _post_search(["domain_abuse"])
            if not parsed or not parsed.get("data"):
                parsed = await _post_search([])

            if not parsed:
                self.api_stats["failed_requests"] += 1
                return None

            alert_rows = parsed.get("data") or []
            alert = self._select_alert_for_domain_entity_search(alert_rows, domain_clean)
            if not alert:
                logger.info(f"No playbook alert row selected for entity idn:{domain_clean}")
                return None

            alert_id = alert.get("playbook_alert_id")
            if not alert_id:
                logger.warning(f"Entity search hit missing playbook_alert_id for {domain_clean}")
                return None

            details = await self._fetch_alert_details(
                rf_token, alert_id, session, ignore_status_filter=True
            )
            if not details:
                return None

            return self._merge_alert_data(alert, details)

        except Exception as e:
            logger.error(f"fetch_enrichment_for_domain failed for {domain_clean}: {e}")
            self.api_stats["failed_requests"] += 1
            return None

    async def _parse_entity_search_response(self, response) -> Optional[Dict[str, Any]]:
        self.api_stats["total_requests"] += 1
        if response.status == 200:
            data = await response.json()
            status = data.get("status", {})
            if status.get("status_code") != "Ok":
                logger.error(
                    f"RecordedFuture entity search error: {status.get('status_message', 'Unknown')}"
                )
                return None
            self.api_stats["successful_requests"] += 1
            return data
        if response.status == 401:
            response_text = await response.text()
            logger.error(f"RecordedFuture entity search auth failed: {response_text}")
            raise Exception("Authentication failed - check RF token")
        if response.status == 429:
            wait_time = self.retry_config.get("rate_limit_wait", 60)
            logger.warning(f"Rate limited (entity search), waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
            return None
        response_text = await response.text()
        logger.error(f"RecordedFuture entity search error {response.status}: {response_text}")
        return None

    def build_recordedfuture_vendor_blob(self, domain_data: Dict[str, Any]) -> Dict[str, Any]:
        """Same shape as recordedfuture_data inside create_finding_data (excludes typo_domain + DB columns)."""
        from datetime import datetime, timezone

        db_cols = set(self._get_database_columns()) | {"typo_domain"}
        vendor_data = {k: v for k, v in domain_data.items() if k not in db_cols}
        vendor_data["last_fetched"] = datetime.now(timezone.utc).isoformat()
        return vendor_data

    def parse_domain_object(self, obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a RecordedFuture domain object into standardized format"""
        # This is already handled in _merge_alert_data, but kept for interface compliance
        return obj

    def update_config(self, config: Dict[str, Any]):
        """Update adapter configuration at runtime"""
        if "query" in config:
            query_updates = config["query"]
            for key, value in query_updates.items():
                if key in self.query_config:
                    self.query_config[key] = value
        
        if "retry" in config:
            self.retry_config.update(config["retry"])
        
        logger.info(f"Updated RecordedFuture adapter config: query={self.query_config}, retry={self.retry_config}")
    
    async def process_post_storage_tasks(self, findings: List[Dict[str, Any]], program_name: str, rf_token: str, session: Optional[aiohttp.ClientSession] = None):
        """Process tasks that need to happen after domain storage (like screenshots)"""
        try:
            logger.info(f"Processing post-storage tasks for {len(findings)} RecordedFuture findings")
            
            for finding in findings:
                # Get the RecordedFuture data from the finding
                rf_data = finding.get("recordedfuture_data", {})
                raw_details = rf_data.get("raw_details", {})
                alert_id = rf_data.get("alert_id")
                domain_name = finding.get("typo_domain")
                
                if alert_id and domain_name and raw_details:
                    await self._process_screenshots(rf_token, alert_id, rf_data, program_name, session)
                else:
                    logger.debug(f"Skipping finding - missing required data: domain={domain_name}, alert_id={alert_id}, has_details={bool(raw_details)}")
                    
        except Exception as e:
            logger.error(f"Error in post-storage tasks: {str(e)}")
    
    async def process_screenshots_for_stored_domain(self, domain_name: str, program_name: str, rf_token: str, session: Optional[aiohttp.ClientSession] = None):
        """Process screenshots for a domain that has already been stored"""
        # This method can be called externally after domain storage
        pass

    async def bulk_fetch_alert_details(self, alert_ids: List[str], rf_token: str, session: Optional[aiohttp.ClientSession] = None, ignore_status_filter: bool = False) -> Dict[str, Dict[str, Any]]:
        """Fetch alert details for multiple alerts efficiently with rate limiting

        Args:
            alert_ids: List of alert IDs to fetch
            rf_token: RecordedFuture API token
            session: Optional aiohttp session
            ignore_status_filter: If True, fetch details regardless of alert status (used for sync operations)
        """
        logger.info(f"Bulk fetching details for {len(alert_ids)} RecordedFuture alerts (ignore_status_filter={ignore_status_filter})")

        results = {}

        # Process alerts with controlled concurrency and rate limiting
        semaphore = asyncio.Semaphore(3)  # Limit concurrent requests

        async def fetch_single_alert(alert_id: str):
            async with semaphore:
                try:
                    details = await self._fetch_alert_details(rf_token, alert_id, session, ignore_status_filter)
                    if details:
                        results[alert_id] = details
                        logger.debug(f"Successfully fetched details for alert {alert_id}")
                    else:
                        logger.warning(f"No details returned for alert {alert_id}")
                except Exception as e:
                    logger.error(f"Error fetching details for alert {alert_id}: {str(e)}")
                    self.api_stats['failed_requests'] += 1

                # Rate limiting delay between requests
                await asyncio.sleep(0.5)

        # Execute all requests concurrently but with rate limiting
        await asyncio.gather(*[fetch_single_alert(alert_id) for alert_id in alert_ids], return_exceptions=True)

        logger.info(f"Bulk fetch completed: {len(results)} out of {len(alert_ids)} alerts fetched successfully")
        return results
    
    def _get_database_columns(self) -> List[str]:
        """Database columns that should be extracted to root level for RecordedFuture"""
        return [
            "whois_registrar",
            "whois_creation_date", 
            "whois_expiration_date",
            "whois_registrant_name",
            "whois_registrant_country",
            "whois_admin_email",
            "dns_a_records",
            "dns_mx_records",
            "domain_registered"
        ]
    
    def _extract_whois_data(self, panel_whois: Dict[str, Any]) -> Dict[str, Any]:
        """Extract WHOIS data from RecordedFuture panel_evidence_whois for database columns"""
        whois_fields = {
            "whois_registrar": None,
            "whois_creation_date": None,
            "whois_expiration_date": None,
            "whois_registrant_name": None,
            "whois_registrant_country": None,
            "whois_admin_email": None
        }
        
        try:
            if not panel_whois or not panel_whois.get("body"):
                return whois_fields
            
            # Find the main WHOIS entry
            main_whois = None
            whois_contacts = []
            
            for entry in panel_whois["body"]:
                if entry.get("attribute") == "attr:whois":
                    main_whois = entry.get("value", {})
                elif entry.get("attribute") == "attr:whoisContacts":
                    contact = entry.get("value", {})
                    if contact:
                        whois_contacts.append(contact)
            
            # Extract data from main WHOIS entry
            if main_whois:
                whois_fields["domain_registered"] = True
                # Registrar
                whois_fields["whois_registrar"] = main_whois.get("registrarName")
                
                # Dates - convert ISO format to date strings
                created_date = main_whois.get("createdDate")
                if created_date:
                    try:
                        # Convert from ISO format like "2023-06-21T00:00:00.000Z" to date
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                        whois_fields["whois_creation_date"] = dt.strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        whois_fields["whois_creation_date"] = created_date
                
                expires_date = main_whois.get("expiresDate")
                if expires_date:
                    try:
                        dt = datetime.fromisoformat(expires_date.replace('Z', '+00:00'))
                        whois_fields["whois_expiration_date"] = dt.strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        whois_fields["whois_expiration_date"] = expires_date
            
            # Extract contact information from whoisContacts
            # Note: RecordedFuture doesn't seem to provide detailed contact info in this format
            # but we'll check for any additional data structures
            
            return whois_fields
            
        except Exception as e:
            logger.error(f"Error extracting WHOIS data: {str(e)}")
            return whois_fields
    
    def _extract_dns_data(self, panel_dns: Dict[str, Any]) -> Dict[str, Any]:
        """Extract DNS data from RecordedFuture panel_evidence_dns for database columns"""
        dns_fields = {
            "dns_a_records": [],
            "dns_mx_records": []
        }
        
        try:
            if not panel_dns:
                return dns_fields
            
            # Extract A records
            ip_list = panel_dns.get("ip_list", [])
            a_records = []
            for ip_entry in ip_list:
                if ip_entry.get("record_type") == "A":
                    ip_address = ip_entry.get("entity", "")
                    # Remove "ip:" prefix if present
                    if ip_address.startswith("ip:"):
                        ip_address = ip_address[3:]
                    if ip_address:
                        a_records.append(ip_address)
            
            dns_fields["dns_a_records"] = a_records
            
            # Extract MX records
            mx_list = panel_dns.get("mx_list", [])
            mx_records = []
            for mx_entry in mx_list:
                mx_server = mx_entry.get("entity", "")
                # Remove any prefix if present
                if mx_server.startswith("idn:"):
                    mx_server = mx_server[4:]
                elif mx_server.startswith("mx:"):
                    mx_server = mx_server[3:]
                
                if mx_server:
                    # Include priority if available
                    priority = mx_entry.get("priority")
                    if priority is not None:
                        mx_records.append(f"{priority} {mx_server}")
                    else:
                        mx_records.append(mx_server)
            
            dns_fields["dns_mx_records"] = mx_records
            
            return dns_fields
            
        except Exception as e:
            logger.error(f"Error extracting DNS data: {str(e)}")
            return dns_fields
    
    async def _process_screenshots(self, rf_token: str, alert_id: str, domain_data: Dict[str, Any], program_name: str, session: Optional[aiohttp.ClientSession] = None):
        """Process screenshots from RecordedFuture alert details"""
        try:
            # Check if we have screenshot data in the details
            raw_details = domain_data.get("raw_details", {})
            panel_summary = raw_details.get("panel_evidence_summary", {})
            screenshots = panel_summary.get("screenshots", [])
            
            # Try multiple ways to get the domain name
            domain_name = domain_data.get("typo_domain")
            if not domain_name:
                # Try from raw alert data
                raw_alert = domain_data.get("raw_alert", {})
                domain_name = raw_alert.get("title")
            if not domain_name:
                # Try from raw details
                panel_status = raw_details.get("panel_status", {})
                domain_name = panel_status.get("entity_name")
            
            if not domain_name:
                logger.warning(f"No domain name found for alert {alert_id}")
                return
            
            if not screenshots:
                logger.debug(f"No screenshots found for alert {alert_id}")
                return
            
            logger.info(f"Processing {len(screenshots)} screenshots for domain {domain_name}")
            
            # Create typosquat URL first
            url_id = await self._create_typosquat_url(domain_name, program_name, session)
            if not url_id:
                logger.error(f"Failed to create typosquat URL for {domain_name}")
                return
            
            # Process each screenshot
            for screenshot in screenshots:
                if screenshot.get("availability") == "Available":
                    image_id = screenshot.get("image_id")
                    if image_id:
                        await self._fetch_and_upload_screenshot(
                            rf_token, alert_id, image_id, domain_name, program_name, url_id, session,
                            screenshot_created=screenshot.get("created"),
                            source="recordedfuture"
                        )
                        
        except Exception as e:
            logger.error(f"Error processing screenshots for alert {alert_id}: {str(e)}")
    
    async def _create_typosquat_url(self, domain_name: str, program_name: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[str]:
        """Create a typosquat URL entry via API"""
        try:
            # Build URL data
            url = f"https://{domain_name}"
            url_data = {
                "url": url,
                "hostname": domain_name,
                "scheme": "https",
                "port": 443,
                "path": "/",
                "typosquat_domain": domain_name,
                "program_name": program_name
            }
            
            headers = {"Content-Type": "application/json"}
            import os
            api_token = os.getenv("INTERNAL_SERVICE_API_KEY", "")
            if api_token:
                headers["Authorization"] = f"Bearer {api_token}"
            
            # Get API base URL from environment or config
            api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
            url_endpoint = f"{api_base_url}/findings/typosquat-url"
            
            if session:
                async with session.post(url_endpoint, json=url_data, headers=headers) as response:
                    return await self._handle_url_response(response, domain_name)
            else:
                async with aiohttp.ClientSession(timeout=self.timeout) as temp_session:
                    async with temp_session.post(url_endpoint, json=url_data, headers=headers) as response:
                        return await self._handle_url_response(response, domain_name)
                        
        except Exception as e:
            logger.error(f"Error creating typosquat URL for {domain_name}: {str(e)}")
            return None
    
    async def _handle_url_response(self, response, domain_name: str) -> Optional[str]:
        """Handle the URL creation response"""
        if response.status in [200, 201]:
            data = await response.json()
            url_id = data.get("url_id")
            logger.info(f"Successfully created typosquat URL for {domain_name}: {url_id}")
            return url_id
        else:
            response_text = await response.text()
            logger.error(f"Failed to create typosquat URL for {domain_name}: HTTP {response.status} - {response_text}")
            return None
    
    async def _fetch_and_upload_screenshot(self, rf_token: str, alert_id: str, image_id: str, domain_name: str, program_name: str, url_id: str, session: Optional[aiohttp.ClientSession] = None, screenshot_created: Optional[str] = None, source: Optional[str] = None):
        """Fetch screenshot from RecordedFuture and upload to our API"""
        try:
            # URL encode the IDs for the screenshot URL
            import urllib.parse
            encoded_alert_id = urllib.parse.quote(alert_id, safe='')
            encoded_image_id = urllib.parse.quote(image_id, safe='')
            
            screenshot_url = f"https://api.recordedfuture.com/playbook-alert/domain_abuse/{encoded_alert_id}/image/{encoded_image_id}"
            
            headers = {
                "X-RFToken": rf_token,
                "Accept": "image/*"
            }
            
            logger.info(f"Fetching screenshot {image_id} for domain {domain_name}")
            
            # Fetch the screenshot
            screenshot_data = None
            if session:
                async with session.get(screenshot_url, headers=headers) as response:
                    screenshot_data = await self._handle_screenshot_response(response, image_id)
            else:
                async with aiohttp.ClientSession(timeout=self.timeout) as temp_session:
                    async with temp_session.get(screenshot_url, headers=headers) as response:
                        screenshot_data = await self._handle_screenshot_response(response, image_id)
            
            if screenshot_data:
                await self._upload_screenshot(screenshot_data, domain_name, program_name, url_id, image_id, screenshot_created=screenshot_created, source=source)
                
        except Exception as e:
            logger.error(f"Error fetching/uploading screenshot {image_id} for {domain_name}: {str(e)}")
    
    async def _handle_screenshot_response(self, response, image_id: str) -> Optional[bytes]:
        """Handle screenshot fetch response"""
        if response.status == 200:
            screenshot_data = await response.read()
            logger.info(f"Successfully fetched screenshot {image_id}: {len(screenshot_data)} bytes")
            return screenshot_data
        else:
            response_text = await response.text()
            logger.error(f"Failed to fetch screenshot {image_id}: HTTP {response.status} - {response_text}")
            return None
    
    async def _upload_screenshot(self, screenshot_data: bytes, domain_name: str, program_name: str, url_id: str, image_id: str, screenshot_created: Optional[str] = None, source: Optional[str] = None):
        """Upload screenshot to our API"""
        try:
            # Prepare multipart form data
            from aiohttp import FormData

            # Run OCR on screenshot to extract text
            extracted_text = extract_text_from_image_ocr(screenshot_data)
            if extracted_text:
                logger.debug(f"OCR extracted {len(extracted_text)} chars from screenshot {image_id}")

            form_data = FormData()

            # Determine file extension from image_id or default to .png
            filename = f"recordedfuture_{image_id.replace(':', '_')}.png"

            form_data.add_field('file', screenshot_data, filename=filename, content_type='image/png')
            form_data.add_field('url', f"https://{domain_name}")
            form_data.add_field('program_name', program_name)
            if screenshot_created:
                form_data.add_field('source_created_at', screenshot_created)
            if source:
                form_data.add_field('source', source)
            if extracted_text:
                form_data.add_field('extracted_text', extracted_text)
            
            headers = {}
            import os
            api_token = os.getenv("INTERNAL_SERVICE_API_KEY", "")
            if api_token:
                headers["Authorization"] = f"Bearer {api_token}"
            
            # Get API base URL from environment
            api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
            screenshot_endpoint = f"{api_base_url}/findings/typosquat-screenshot"
            
            async with aiohttp.ClientSession(timeout=self.timeout) as upload_session:
                async with upload_session.post(screenshot_endpoint, data=form_data, headers=headers) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        logger.info(f"Successfully uploaded screenshot for {domain_name}: {data.get('file_id')}")
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to upload screenshot for {domain_name}: HTTP {response.status} - {response_text}")
                        
        except Exception as e:
            logger.error(f"Error uploading screenshot for {domain_name}: {str(e)}")