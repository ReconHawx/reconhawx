import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging
import os

from .api_vendors import RecordedFutureAdapter

logger = logging.getLogger(__name__)

class SyncRecordedFutureDataTask:
    """Task for synchronizing RecordedFuture data in existing typosquat domain findings"""

    def __init__(self, job_id: str, program_name: str, user_id: str, sync_options: Optional[Dict[str, Any]] = None):
        self.job_id = job_id
        self.program_name = program_name
        self.user_id = user_id
        self.sync_options = sync_options or {}

        # Sync configuration with defaults
        self.batch_size = self.sync_options.get("batch_size", 50)
        self.max_age_days = self.sync_options.get("max_age_days", 30)
        self.include_screenshots = self.sync_options.get("include_screenshots", True)

        self.results = {
            "success_count": 0,
            "error_count": 0,
            "errors": [],
            "updated_findings": [],
            "skipped_findings": [],
            "api_stats": {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "findings_updated": 0,
                "findings_unchanged": 0
            }
        }

        # API configuration
        self.api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
        self.api_token = os.getenv("INTERNAL_SERVICE_API_KEY", "")
        self.timeout = aiohttp.ClientTimeout(total=120)

        # Initialize RecordedFuture adapter
        self.rf_adapter = RecordedFutureAdapter(self.timeout)

        # Connection pool for HTTP requests
        self.connector = None
        self.session = None

        logger.info(f"SyncRecordedFutureDataTask initialized for program: {program_name}")
        logger.info(f"Sync options: batch_size={self.batch_size}, max_age_days={self.max_age_days}")

    async def execute(self):
        """Main execution method for syncing RecordedFuture data"""
        try:
            # Update job status to running
            await self.update_job_status("running", 0, "Starting RecordedFuture data sync...")

            # Test API connectivity first
            await self.test_api_connectivity()

            # Process the single program
            await self.sync_program_findings(self.program_name)

            # Aggregate RF adapter stats
            rf_stats = self.rf_adapter.get_stats()
            self.results['api_stats'].update(rf_stats)

            # Final status update
            message = f"Sync completed: {self.results['success_count']} updated, {self.results['error_count']} errors"
            if self.results['api_stats']['findings_unchanged'] > 0:
                message += f", {self.results['api_stats']['findings_unchanged']} unchanged"

            logger.info(f"Sync job {self.job_id} final results: {self.results}")
            await self.update_job_status("completed", 100, message, self.results)

        except Exception as e:
            logger.error(f"Error in sync job {self.job_id}: {str(e)}")
            await self.update_job_status("failed", 0, f"Sync job failed: {str(e)}")
        finally:
            await self._cleanup_session()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a shared HTTP session with connection pooling"""
        if self.session is None or self.session.closed:
            if self.connector is None or self.connector.closed:
                self.connector = aiohttp.TCPConnector(
                    limit=10,
                    limit_per_host=5,
                    keepalive_timeout=30,
                    enable_cleanup_closed=True
                )

            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=self.timeout
            )
            logger.debug("Created new HTTP session for RF sync")

        return self.session

    async def _cleanup_session(self):
        """Clean up HTTP session and connector"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("Closed RF sync HTTP session")

        if self.connector and not self.connector.closed:
            await self.connector.close()
            logger.debug("Closed RF sync HTTP connector")

    async def sync_program_findings(self, program_name: str):
        """Sync RecordedFuture data for all findings in a specific program"""
        logger.info(f"Syncing RecordedFuture data for program: {program_name} (fetching ALL findings regardless of RF status)")

        try:
            # Get API credentials for this program
            api_credentials = await self.get_program_api_credentials(program_name)
            if not api_credentials:
                logger.error(f"No RecordedFuture API credentials found for program {program_name}")
                self.results["error_count"] += 1
                self.results["errors"].append({
                    "program": program_name,
                    "error": "No RecordedFuture API credentials configured for this program"
                })
                return

            # Validate credentials
            if not self.rf_adapter.validate_credentials(api_credentials):
                required_fields = self.rf_adapter.get_required_credentials()
                logger.error(f"Invalid credentials for program {program_name}. Required: {required_fields}")
                self.results["error_count"] += 1
                self.results["errors"].append({
                    "program": program_name,
                    "error": f"Invalid RecordedFuture API credentials. Required fields: {required_fields}"
                })
                return

            # Fetch existing RecordedFuture findings for this program
            existing_findings = await self.fetch_existing_rf_findings(program_name)
            if not existing_findings:
                logger.info(f"No RecordedFuture findings found for program {program_name}")
                return

            logger.info(f"Found {len(existing_findings)} RecordedFuture findings for program {program_name}")

            # Group findings by alert_id and batch process
            await self.process_findings_in_batches(existing_findings, api_credentials, program_name)

        except Exception as e:
            logger.error(f"Error syncing program {program_name}: {str(e)}")
            self.results["error_count"] += 1
            self.results["errors"].append({
                "program": program_name,
                "error": str(e)
            })

    async def fetch_existing_rf_findings(self, program_name: str) -> List[Dict[str, Any]]:
        """Fetch existing typosquat findings with RecordedFuture source"""
        try:
            logger.info(f"Fetching existing RecordedFuture findings for program {program_name}")
            findings = []
            page = 1
            page_size = 500

            # Calculate minimum sync interval to avoid unnecessary API calls
            # For sync operations, we want to skip data that was recently fetched
            min_sync_interval = None
            interval_hours = 0
            if self.max_age_days > 0:
                # Use a reasonable minimum sync interval based on max_age_days
                if self.max_age_days >= 7:
                    # For weekly+ intervals, use 6 hours minimum
                    interval_hours = 6
                elif self.max_age_days >= 1:
                    # For daily intervals, use 1 hour minimum
                    interval_hours = 1
                else:
                    # For sub-daily intervals, use max_age_days converted to hours
                    interval_hours = self.max_age_days * 24

                min_sync_interval = datetime.now(timezone.utc) - timedelta(hours=interval_hours)
                logger.info(f"Skipping findings synced within last {interval_hours} hours (after {min_sync_interval.strftime('%Y-%m-%d %H:%M:%S')})")

            while True:
                search_data = {
                    "hide_dismissed": False,
                    "hide_resolved": False,
                    "hide_false_positives": False,  # Include all findings
                    "program": program_name,
                    "source": "recordedfuture",  # Only RecordedFuture findings
                    "sort_by": "timestamp",
                    "sort_dir": "desc",
                    "page": page,
                    "page_size": page_size
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
                            break  # No more items

                        logger.info(f"Page {page}: Received {len(items)} items from API")

                        # Debug: Log sample item structure
                        if items and len(items) > 0:
                            sample_item = items[0]
                            logger.info(f"Sample item fields: {list(sample_item.keys())}")
                            rf_data = sample_item.get("recordedfuture_data")
                            logger.info(f"Sample recordedfuture_data: {rf_data} (type: {type(rf_data)})")

                        # Filter by age if specified
                        filtered_items = []
                        for item in items:
                            rf_data = item.get("recordedfuture_data", {})
                            alert_id = rf_data.get("alert_id")

                            # Skip findings without valid alert_ids
                            if not alert_id:
                                logger.debug(f"Skipping finding {item.get('typo_domain')} - no alert_id")
                                continue

                            # Check if RecordedFuture data was recently synced (skip if too recent)
                            if min_sync_interval:
                                # Use last_fetched from recordedfuture_data
                                last_fetched_str = rf_data.get("last_fetched")
                                if last_fetched_str:
                                    try:
                                        last_fetched = datetime.fromisoformat(last_fetched_str.replace('Z', '+00:00'))
                                        if last_fetched > min_sync_interval:
                                            # RF data was synced recently, skip this finding
                                            hours_ago = (datetime.now(timezone.utc) - last_fetched).total_seconds() / 3600
                                            logger.info(f"🕘 Skipping {item.get('typo_domain')}: RF data too recent ({hours_ago:.1f} hours ago, within {interval_hours}h interval)")
                                            continue
                                        else:
                                            hours_ago = (datetime.now(timezone.utc) - last_fetched).total_seconds() / 3600
                                            logger.debug(f"✓ Including {item.get('typo_domain')}: RF data is {hours_ago:.1f} hours old (outside {interval_hours}h interval)")
                                    except ValueError:
                                        logger.warning(f"Could not parse last_fetched timestamp: {last_fetched_str}")
                                        # Include the finding if we can't parse the timestamp
                                else:
                                    # No last_fetched timestamp, include it (data may need to be fetched for the first time)
                                    logger.info(f"🆕 Including {item.get('typo_domain')}: no last_fetched timestamp (first sync)")

                            filtered_items.append(item)

                        findings.extend(filtered_items)
                        logger.info(f"📊 Page {page}: {len(filtered_items)}/{len(items)} findings selected for sync (based on last_fetched + alert_id criteria)")

                        # Check if we have more pages
                        total_pages = data.get("pagination", {}).get("total_pages", 1)
                        if page >= total_pages:
                            break

                        page += 1
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to fetch findings for program {program_name}: HTTP {response.status} - {response_text}")
                        break

            logger.info(f"🎯 Final selection: {len(findings)} RecordedFuture findings eligible for sync from program {program_name}")
            return findings

        except Exception as e:
            logger.error(f"Error fetching existing RF findings for program {program_name}: {str(e)}")
            return []

    async def process_findings_in_batches(self, findings: List[Dict[str, Any]], api_credentials: Dict[str, str], program_name: str):
        """Process findings in batches to respect API rate limits"""
        logger.info(f"Processing {len(findings)} findings in batches of {self.batch_size}")

        # Group findings into batches
        for i in range(0, len(findings), self.batch_size):
            batch = findings[i:i + self.batch_size]
            logger.info(f"Processing batch {i // self.batch_size + 1}: {len(batch)} findings")

            # Extract alert_ids from this batch (we already have the alert IDs from our findings)
            alert_ids = []
            finding_by_alert_id = {}

            for finding in batch:
                rf_data = finding.get("recordedfuture_data", {})
                alert_id = rf_data.get("alert_id")
                domain = finding.get("typo_domain", "unknown")
                last_fetched = rf_data.get("last_fetched", "never")

                if alert_id:
                    alert_ids.append(alert_id)
                    finding_by_alert_id[alert_id] = finding
                    logger.debug(f"🔄 Will fetch RF details for {domain} (alert_id: {alert_id}, last_fetched: {last_fetched})")
                else:
                    logger.debug(f"⚠️  Skipping {domain} - no alert_id in stored RF data")

            if not alert_ids:
                logger.info("No valid alert_ids in this batch, skipping")
                continue

            # Fetch fresh data from RecordedFuture API using direct alert details (no search needed)
            logger.info(f"📡 Fetching RF alert details for {len(alert_ids)} known alert_ids: {alert_ids[:3]}{'...' if len(alert_ids) > 3 else ''}")
            fresh_data = await self.fetch_fresh_rf_data(alert_ids, api_credentials)

            # Update findings with fresh data
            await self.update_findings_with_fresh_data(fresh_data, finding_by_alert_id, program_name)

            # Small delay between batches to be respectful to RF API
            await asyncio.sleep(1)

    async def fetch_fresh_rf_data(self, alert_ids: List[str], api_credentials: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """Fetch fresh alert details directly from RecordedFuture API for known alert IDs"""
        logger.info(f"Fetching fresh alert details for {len(alert_ids)} known alerts from RecordedFuture (bypassing search)")

        rf_token = api_credentials.get("rf_token")
        session = await self._get_session()

        # Use the bulk fetch method to get details for known alert IDs, ignoring status filter for sync operations
        fresh_data = await self.rf_adapter.bulk_fetch_alert_details(alert_ids, rf_token, session, ignore_status_filter=True)

        # Update our local stats with RF adapter stats
        rf_stats = self.rf_adapter.get_stats()
        self.results["api_stats"]["total_requests"] += rf_stats.get("total_requests", 0)
        self.results["api_stats"]["successful_requests"] += rf_stats.get("successful_requests", 0)
        self.results["api_stats"]["failed_requests"] += rf_stats.get("failed_requests", 0)

        logger.info(f"Successfully fetched fresh details for {len(fresh_data)} out of {len(alert_ids)} alerts from RF API")
        return fresh_data

    async def update_findings_with_fresh_data(self, fresh_data: Dict[str, Dict[str, Any]], finding_by_alert_id: Dict[str, Dict[str, Any]], program_name: str):
        """Update local findings with fresh RecordedFuture data"""
        logger.info(f"Updating {len(fresh_data)} findings with fresh data")

        for alert_id, fresh_alert_data in fresh_data.items():
            try:
                finding = finding_by_alert_id.get(alert_id)
                if not finding:
                    continue

                finding_id = finding.get("id")
                domain_name = finding.get("typo_domain")

                # Get existing RF data
                existing_rf_data = finding.get("recordedfuture_data", {})

                # Extract status and assignee changes from RF data first
                status_updates = await self._extract_status_and_assignee_updates(
                    fresh_alert_data, finding, program_name
                )

                # Check if data has actually changed by comparing key fields
                data_changed = self._has_data_changed(existing_rf_data, fresh_alert_data)
                status_changed = bool(status_updates)  # True if any status/assignee updates

                # Debug output for decision making
                last_fetched = existing_rf_data.get("last_fetched", "never")
                last_synced = existing_rf_data.get("last_synced", "never")

                logger.debug(f"🔍 Analyzing {domain_name}: data_changed={data_changed}, status_changed={status_changed}, last_fetched={last_fetched}, last_synced={last_synced}")

                if status_updates:
                    logger.debug(f"📝 Status/assignee updates for {domain_name}: {status_updates}")

                if data_changed or status_changed:
                    # Merge fresh data with existing raw_alert data
                    updated_rf_data = existing_rf_data.copy()
                    updated_rf_data["raw_details"] = fresh_alert_data
                    updated_rf_data["last_synced"] = datetime.now(timezone.utc).isoformat()
                    updated_rf_data["last_fetched"] = datetime.now(timezone.utc).isoformat()

                    # Extract key fields from fresh data for easier access
                    panel_status = fresh_alert_data.get("panel_status", {})
                    if panel_status:
                        updated_rf_data.update({
                            "entity_criticality": panel_status.get("entity_criticality"),
                            "risk_score": panel_status.get("risk_score"),
                            "targets": panel_status.get("targets", []),
                            "context_list": panel_status.get("context_list", [])
                        })

                    # Update the finding via API (both RF data and status/assignee)
                    success = await self.update_finding_comprehensive(
                        finding_id, updated_rf_data, status_updates
                    )

                    if success:
                        self.results["success_count"] += 1
                        update_details = {
                            "finding_id": finding_id,
                            "domain": domain_name,
                            "program": program_name,
                            "alert_id": alert_id,
                            "data_changed": data_changed,
                            "status_changed": status_changed
                        }
                        if status_updates:
                            update_details["status_updates"] = status_updates

                        self.results["updated_findings"].append(update_details)
                        self.results["api_stats"]["findings_updated"] += 1

                        change_types = []
                        if data_changed:
                            change_types.append("RF data")
                        if status_changed:
                            change_types.append("status/assignee")

                        logger.info(f"✅ Updated {domain_name}: {', '.join(change_types)} (last_fetched: {last_fetched} → now)")

                        logger.info(f"Updated finding {finding_id} ({domain_name}) - changes: {', '.join(change_types)}")
                    else:
                        self.results["error_count"] += 1
                        self.results["errors"].append({
                            "finding_id": finding_id,
                            "domain": domain_name,
                            "program": program_name,
                            "error": "Failed to update finding via API"
                        })
                else:
                    # Data hasn't changed
                    self.results["skipped_findings"].append({
                        "finding_id": finding_id,
                        "domain": domain_name,
                        "program": program_name,
                        "reason": "No changes detected"
                    })
                    self.results["api_stats"]["findings_unchanged"] += 1
                    logger.info(f"⏭️  Skipped {domain_name}: no changes detected (last_fetched: {last_fetched}, last_synced: {last_synced})")

            except Exception as e:
                logger.error(f"Error updating finding for alert {alert_id}: {str(e)}")
                self.results["error_count"] += 1
                self.results["errors"].append({
                    "alert_id": alert_id,
                    "error": str(e)
                })

    def _has_data_changed(self, existing_rf_data: Dict[str, Any], fresh_alert_data: Dict[str, Any]) -> bool:
        """Check if the fresh data is different from existing data"""
        try:
            # Compare key fields that indicate changes
            existing_details = existing_rf_data.get("raw_details", {})
            existing_status = existing_details.get("panel_status", {})
            fresh_status = fresh_alert_data.get("panel_status", {})

            # Check key fields for changes
            key_fields = ["entity_criticality", "risk_score", "targets", "context_list"]

            for field in key_fields:
                existing_value = existing_status.get(field)
                fresh_value = fresh_status.get(field)

                if existing_value != fresh_value:
                    logger.debug(f"Change detected in field {field}: {existing_value} -> {fresh_value}")
                    return True

            # Check if there's no existing raw_details (first sync)
            if not existing_details:
                return True

            return False

        except Exception as e:
            logger.warning(f"Error comparing data, assuming changed: {str(e)}")
            return True

    async def _extract_status_and_assignee_updates(self, fresh_alert_data: Dict[str, Any], finding: Dict[str, Any], program_name: str) -> Dict[str, Any]:
        """Extract status and assignee updates from fresh RF data"""
        status_updates = {}

        try:
            # Extract RF status from panel_status (same structure as gather task)
            panel_status = fresh_alert_data.get("panel_status", {})
            rf_status = panel_status.get("status", "").lower()
            current_status = finding.get("status")

            logger.info(f"Sync status mapping: domain={finding.get('typo_domain')}, rf_status='{rf_status}', original='{panel_status.get('status')}'")

            # Map RF status to finding status (same logic as gather task)
            if rf_status == "inprogress" or rf_status == "in progress":
                new_status = "inprogress"
            elif rf_status == "resolved":
                new_status = "resolved"
            elif rf_status == "dismissed":
                new_status = "dismissed"
            elif rf_status == "new":
                new_status = "new"
            else:
                new_status = None

            # Only update status if it changed and we have a valid mapping
            if new_status and new_status != current_status:
                status_updates["status"] = new_status
                logger.info(f"Status change detected: {current_status} -> {new_status} (RF: {rf_status})")

            # Extract assignee information from panel_status (same logic as gather task)
            rf_assignee_id = panel_status.get("assignee_id")
            if rf_assignee_id:
                # Extract the uhash value from assignee_id (format: "uhash:7DFz7Cw2GV")
                if rf_assignee_id.startswith("uhash:"):
                    rf_uhash = rf_assignee_id[6:]  # Remove "uhash:" prefix
                else:
                    rf_uhash = rf_assignee_id

                # Get the user ID by rf_uhash using global users
                assigned_to_id = await self._get_user_id_by_rf_uhash(rf_uhash)
                current_assigned_to = finding.get("assigned_to")

                if assigned_to_id and assigned_to_id != current_assigned_to:
                    status_updates["assigned_to"] = assigned_to_id
                    logger.info(f"Assignee change detected: {current_assigned_to} -> {assigned_to_id} (RF uhash: {rf_uhash})")

            # If we have assignee updates but no status updates, include current status
            # because the API requires the status field to be present
            if "assigned_to" in status_updates and "status" not in status_updates:
                current_status = finding.get("status", "new")
                status_updates["status"] = current_status
                logger.debug(f"Including current status '{current_status}' for assignee update")

            return status_updates

        except Exception as e:
            logger.error(f"Error extracting status/assignee updates: {str(e)}")
            return {}

    async def _get_user_id_by_rf_uhash(self, rf_uhash: str) -> Optional[str]:
        """Get user ID by RF uhash from global users list"""
        try:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # Fetch all users with pagination from global auth endpoint
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

    async def update_finding_comprehensive(self, finding_id: str, updated_rf_data: Dict[str, Any], status_updates: Dict[str, Any]) -> bool:
        """Update finding with both RF data and status/assignee changes"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            session = await self._get_session()

            # First, update the RecordedFuture data
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

                # Add bypass header for sync operations to skip workflow validation
                status_headers = headers.copy()
                status_headers["X-Bypass-Workflow"] = "true"

                logger.info(f"Updating finding {finding_id} status/assignee: {status_payload} (workflow bypass enabled)")

                async with session.put(status_url, json=status_payload, headers=status_headers) as response:
                    if response.status not in [200, 204]:
                        response_text = await response.text()
                        logger.error(f"Failed to update status/assignee for finding {finding_id}: HTTP {response.status} - {response_text}")
                        return False

                logger.info(f"Updated status/assignee for finding {finding_id}: {status_payload}")

            return True

        except Exception as e:
            logger.error(f"Error updating finding {finding_id} comprehensively: {str(e)}")
            return False

    async def update_finding_rf_data(self, finding_id: str, updated_rf_data: Dict[str, Any]) -> bool:
        """Update a finding's RecordedFuture data via API"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/findings/typosquat/{finding_id}/recordedfuture-data"

            payload = {"recordedfuture_data": updated_rf_data}

            session = await self._get_session()
            async with session.patch(url, json=payload, headers=headers) as response:
                if response.status in [200, 204]:
                    return True
                else:
                    response_text = await response.text()
                    logger.error(f"Failed to update finding {finding_id}: HTTP {response.status} - {response_text}")
                    return False

        except Exception as e:
            logger.error(f"Error updating finding {finding_id}: {str(e)}")
            return False

    async def get_program_api_credentials(self, program_name: str) -> Optional[Dict[str, str]]:
        """Get RecordedFuture API credentials for the program"""
        try:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/programs/{program_name}"
            logger.info(f"Fetching RecordedFuture API credentials for program: {program_name}")

            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    program_data = await response.json()

                    # Use RF adapter to get field mapping
                    credential_fields = self.rf_adapter.get_credential_fields()

                    credentials = {}
                    for internal_name, db_field in credential_fields.items():
                        value = program_data.get(db_field)
                        if value:
                            credentials[internal_name] = value

                    if credentials:
                        logger.info(f"Found RecordedFuture API credentials for program {program_name}")
                        return credentials
                    else:
                        logger.warning("No RecordedFuture API credentials found in program data")
                else:
                    response_text = await response.text()
                    logger.error(f"Failed to fetch program data: HTTP {response.status} - {response_text}")

        except Exception as e:
            logger.error(f"Error fetching API credentials for program {program_name}: {str(e)}")
            return None

    async def update_job_status(self, status: str, progress: int, message: str, results: Optional[Dict[str, Any]] = None):
        """Update job status via API"""
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

    async def test_api_connectivity(self):
        """Test API connectivity and basic functionality"""
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