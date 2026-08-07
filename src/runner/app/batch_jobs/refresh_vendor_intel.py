import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta
import logging
import os
from typing import Any, Dict, List, Optional

from .api_vendors import RecordedFutureAdapter, ThreatStreamAdapter

logger = logging.getLogger(__name__)

VALID_VENDORS = ("recordedfuture", "threatstream")


class RefreshVendorIntelTask:
    """Refresh vendor JSONB on existing typosquat findings without changing status/assignment."""

    def __init__(
        self,
        job_id: str,
        program_name: str,
        user_id: str,
        api_vendor: str = "recordedfuture",
        program_id: Optional[str] = None,
        refresh_options: Optional[Dict[str, Any]] = None,
    ):
        self.job_id = job_id
        self.program_name = program_name
        self.user_id = user_id
        self.program_id = program_id
        self.api_vendor = (api_vendor or "recordedfuture").lower()
        if self.api_vendor not in VALID_VENDORS:
            raise ValueError(f"api_vendor must be one of {VALID_VENDORS}")

        opts = refresh_options or {}
        self.batch_size = int(opts.get("batch_size", 50))
        self.max_age_hours = float(opts.get("max_age_hours", 6))
        self.include_screenshots = bool(opts.get("include_screenshots", True))

        self.results: Dict[str, Any] = {
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "errors": [],
            "updated_findings": [],
            "skipped_findings": [],
            "api_vendor": self.api_vendor,
        }

        self.api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
        self.api_token = os.getenv("INTERNAL_SERVICE_API_KEY", "")
        self.timeout = aiohttp.ClientTimeout(total=120)

        self.rf_adapter = RecordedFutureAdapter(self.timeout)
        self.ts_adapter = ThreatStreamAdapter(self.timeout)

        self.connector: Optional[aiohttp.TCPConnector] = None
        self.session: Optional[aiohttp.ClientSession] = None

    async def execute(self):
        try:
            await self.update_job_status(
                "running", 0, f"Starting {self.api_vendor} vendor intel refresh..."
            )
            await self.test_api_connectivity()
            await self._ensure_program_id()

            if self.api_vendor == "recordedfuture":
                await self._refresh_recordedfuture()
            else:
                await self._refresh_threatstream()

            message = (
                f"Refresh completed: {self.results['success_count']} updated, "
                f"{self.results['skipped_count']} skipped, "
                f"{self.results['error_count']} errors"
            )
            await self.update_job_status("completed", 100, message, self.results)
        except Exception as e:
            logger.error(f"Refresh vendor intel job {self.job_id} failed: {e}")
            await self.update_job_status("failed", 0, f"Job failed: {e}")
        finally:
            await self._cleanup_session()

    async def _refresh_recordedfuture(self):
        credentials = await self._get_vendor_credentials("recordedfuture")
        if not credentials or not credentials.get("rf_token"):
            raise ValueError("No RecordedFuture API credentials configured for this program")

        findings = await self._fetch_findings(has_recordedfuture=True)
        if not findings:
            logger.info("No findings with recordedfuture_data for program %s", self.program_name)
            return

        logger.info("Refreshing RecordedFuture intel for %d findings", len(findings))
        rf_token = credentials["rf_token"]
        session = await self._get_session()

        for i in range(0, len(findings), self.batch_size):
            batch = findings[i : i + self.batch_size]
            alert_ids: List[str] = []
            finding_by_alert: Dict[str, Dict[str, Any]] = {}

            for finding in batch:
                rf_data = finding.get("recordedfuture_data") or {}
                alert_id = rf_data.get("alert_id")
                if not alert_id:
                    self._skip_finding(
                        finding,
                        "missing alert_id in recordedfuture_data",
                    )
                    continue
                alert_ids.append(alert_id)
                finding_by_alert[alert_id] = finding

            if not alert_ids:
                continue

            fresh_by_alert = await self.rf_adapter.bulk_fetch_alert_details(
                alert_ids, rf_token, session, ignore_status_filter=True
            )

            screenshot_candidates: List[Dict[str, Any]] = []
            for alert_id, fresh_details in fresh_by_alert.items():
                finding = finding_by_alert.get(alert_id)
                if not finding:
                    continue
                try:
                    updated = await self._apply_rf_refresh(finding, fresh_details)
                    if updated:
                        self.results["success_count"] += 1
                        self.results["updated_findings"].append(
                            {
                                "finding_id": finding.get("id"),
                                "domain": finding.get("typo_domain"),
                                "vendor": "recordedfuture",
                            }
                        )
                except Exception as e:
                    self._record_error(finding, str(e))

                if self.include_screenshots:
                    candidate = self._rf_screenshot_candidate(finding)
                    if candidate:
                        screenshot_candidates.append(candidate)

            # Fresh fetch may fail for some alerts; still attempt missing screenshots
            # from stored raw_details (same as gather re-processing existing findings).
            if self.include_screenshots:
                for alert_id, finding in finding_by_alert.items():
                    if alert_id in fresh_by_alert:
                        continue
                    candidate = self._rf_screenshot_candidate(finding)
                    if candidate:
                        screenshot_candidates.append(candidate)

            screenshot_candidates = self._dedupe_screenshot_candidates(
                screenshot_candidates
            )

            if screenshot_candidates and self.program_id:
                await self._run_rf_screenshot_pass(
                    screenshot_candidates, rf_token, session
                )

            await asyncio.sleep(1)

    async def _refresh_threatstream(self):
        credentials = await self._get_vendor_credentials("threatstream")
        if not credentials:
            raise ValueError("No ThreatStream API credentials configured for this program")

        findings = await self._fetch_findings(has_threatstream=True)
        if not findings:
            logger.info("No findings with threatstream_data for program %s", self.program_name)
            return

        logger.info("Refreshing ThreatStream intel for %d findings", len(findings))
        session = await self._get_session()
        rf_credentials = await self._get_vendor_credentials("recordedfuture")
        rf_token = (rf_credentials or {}).get("rf_token")
        screenshot_candidates: List[Dict[str, Any]] = []

        for finding in findings:
            domain = (finding.get("typo_domain") or "").strip()
            finding_id = finding.get("id")
            if not domain or not finding_id:
                continue

            try:
                fresh_ts = await self.ts_adapter.fetch_intelligence_by_value(
                    domain, credentials, session
                )
                if not fresh_ts:
                    self._skip_finding(finding, "no ThreatStream intelligence returned")
                else:
                    existing_ts = finding.get("threatstream_data") or {}
                    merged_ts = {**existing_ts, **fresh_ts}
                    merged_ts["last_fetched"] = fresh_ts.get(
                        "last_fetched", datetime.now(timezone.utc).isoformat()
                    )

                    if not await self._patch_threatstream_data(finding_id, merged_ts):
                        self._record_error(finding, "PATCH threatstream-data failed")
                    else:
                        self.results["success_count"] += 1
                        self.results["updated_findings"].append(
                            {
                                "finding_id": finding_id,
                                "domain": domain,
                                "vendor": "threatstream",
                            }
                        )
                        if self._has_threatstream_changed(existing_ts, merged_ts):
                            logger.info("Updated ThreatStream intel for %s", domain)
                        else:
                            logger.info(
                                "Refreshed ThreatStream intel for %s (re-applied vendor payload)",
                                domain,
                            )
            except Exception as e:
                self._record_error(finding, str(e))

            if self.include_screenshots and rf_token:
                await self._maybe_refresh_rf_enrichment_for_screenshots(
                    finding, domain, rf_token, session
                )
                candidate = self._rf_screenshot_candidate(finding)
                if candidate:
                    screenshot_candidates.append(candidate)

            await asyncio.sleep(0.2)

        screenshot_candidates = self._dedupe_screenshot_candidates(screenshot_candidates)
        if screenshot_candidates and self.program_id and rf_token:
            await self._run_rf_screenshot_pass(screenshot_candidates, rf_token, session)

    async def _apply_rf_refresh(
        self, finding: Dict[str, Any], fresh_details: Dict[str, Any]
    ) -> bool:
        finding_id = finding.get("id")
        existing_rf = finding.get("recordedfuture_data") or {}

        updated_rf = self.rf_adapter.rebuild_recordedfuture_data_from_details(
            existing_rf, fresh_details
        )
        finding["recordedfuture_data"] = updated_rf

        logger.info(
            "PATCHing RecordedFuture intel for %s (finding %s)",
            finding.get("typo_domain"),
            finding_id,
        )
        if not await self._patch_recordedfuture_data(finding_id, updated_rf):
            raise RuntimeError("PATCH recordedfuture-data failed")

        derived = self._extract_derived_columns(fresh_details)
        if derived:
            await self._patch_recordedfuture_derived_columns(finding_id, derived)

        if self._has_rf_data_changed(existing_rf, updated_rf):
            logger.info(
                "Updated RecordedFuture intel for %s",
                finding.get("typo_domain"),
            )
        else:
            logger.info(
                "Refreshed RecordedFuture intel for %s (re-applied vendor payload)",
                finding.get("typo_domain"),
            )
        return True

    def _resolve_rf_alert_id(self, rf_data: Dict[str, Any]) -> Optional[str]:
        alert_id = rf_data.get("alert_id")
        if alert_id:
            return str(alert_id)
        raw_alert = rf_data.get("raw_alert") or {}
        playbook_alert_id = raw_alert.get("playbook_alert_id")
        return str(playbook_alert_id) if playbook_alert_id else None

    def _rf_screenshot_candidate(
        self, finding: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build a gather-compatible finding payload for RF screenshot download."""
        rf_data = finding.get("recordedfuture_data") or {}
        raw_details = rf_data.get("raw_details")
        alert_id = self._resolve_rf_alert_id(rf_data)
        typo_domain = (finding.get("typo_domain") or "").strip()
        if not raw_details or not alert_id or not typo_domain:
            return None
        rf_payload = {**rf_data, "alert_id": alert_id, "typo_domain": typo_domain}
        return {"typo_domain": typo_domain, "recordedfuture_data": rf_payload}

    @staticmethod
    def _dedupe_screenshot_candidates(
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        seen: set = set()
        deduped: List[Dict[str, Any]] = []
        for candidate in candidates:
            domain = candidate.get("typo_domain")
            if not domain or domain in seen:
                continue
            seen.add(domain)
            deduped.append(candidate)
        return deduped

    async def _run_rf_screenshot_pass(
        self,
        findings: List[Dict[str, Any]],
        rf_token: str,
        session: aiohttp.ClientSession,
    ):
        if not self.program_id:
            logger.warning("Skipping RF screenshots: program_id not resolved")
            return
        logger.info(
            "Running RecordedFuture screenshot pass for %d findings", len(findings)
        )
        await self.rf_adapter.process_post_storage_tasks(
            findings,
            self.program_name,
            self.program_id,
            rf_token,
            session,
        )

    async def _maybe_refresh_rf_enrichment_for_screenshots(
        self,
        finding: Dict[str, Any],
        domain: str,
        rf_token: str,
        session: aiohttp.ClientSession,
    ):
        """Read-only RF enrichment to refresh raw_details before screenshot download."""
        domain_data = await self.rf_adapter.fetch_enrichment_for_domain(
            domain, rf_token, session
        )
        if not domain_data:
            return
        rf_blob = self.rf_adapter.build_recordedfuture_vendor_blob(domain_data)
        existing_rf = finding.get("recordedfuture_data") or {}
        merged_rf = {**existing_rf, **rf_blob}
        merged_rf["last_fetched"] = rf_blob.get(
            "last_fetched", datetime.now(timezone.utc).isoformat()
        )
        finding_id = finding.get("id")
        if finding_id:
            await self._patch_recordedfuture_data(finding_id, merged_rf)
        finding["recordedfuture_data"] = merged_rf

    def _extract_derived_columns(self, fresh_details: Dict[str, Any]) -> Dict[str, Any]:
        panel_whois = fresh_details.get("panel_evidence_whois", {})
        panel_dns = fresh_details.get("panel_evidence_dns", {})
        columns: Dict[str, Any] = {}
        columns.update(self.rf_adapter._extract_whois_data(panel_whois))
        columns.update(self.rf_adapter._extract_dns_data(panel_dns))
        return {k: v for k, v in columns.items() if v is not None and v != []}

    def _has_rf_data_changed(
        self, existing_rf: Dict[str, Any], updated_rf: Dict[str, Any]
    ) -> bool:
        if not existing_rf.get("raw_details"):
            return True
        if existing_rf.get("raw_details") != updated_rf.get("raw_details"):
            return True
        key_fields = [
            "entity_criticality",
            "risk_score",
            "targets",
            "context_list",
        ]
        for field in key_fields:
            if existing_rf.get(field) != updated_rf.get(field):
                return True
        existing_status = (existing_rf.get("raw_details") or {}).get("panel_status", {})
        fresh_status = (updated_rf.get("raw_details") or {}).get("panel_status", {})
        for field in key_fields:
            if existing_status.get(field) != fresh_status.get(field):
                return True
        return False

    def _has_threatstream_changed(
        self, existing_ts: Dict[str, Any], merged_ts: Dict[str, Any]
    ) -> bool:
        compare_fields = (
            "threatscore",
            "confidence",
            "status",
            "tags",
            "modified_ts",
            "itype",
        )
        for field in compare_fields:
            if existing_ts.get(field) != merged_ts.get(field):
                return True
        return not existing_ts

    async def _fetch_findings(
        self,
        *,
        has_recordedfuture: bool = False,
        has_threatstream: bool = False,
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        page = 1
        page_size = 500
        min_sync_interval: Optional[datetime] = None
        if self.max_age_hours > 0:
            min_sync_interval = datetime.now(timezone.utc) - timedelta(
                hours=self.max_age_hours
            )

        vendor_key = "recordedfuture_data" if has_recordedfuture else "threatstream_data"

        while True:
            search_data: Dict[str, Any] = {
                "hide_dismissed": False,
                "hide_resolved": False,
                "hide_false_positives": False,
                "program": self.program_name,
                "sort_by": "timestamp",
                "sort_dir": "desc",
                "page": page,
                "page_size": page_size,
            }
            if has_recordedfuture:
                search_data["has_recordedfuture"] = True
            if has_threatstream:
                search_data["has_threatstream"] = True

            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/findings/typosquat/search"
            session = await self._get_session()
            async with session.post(url, json=search_data, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(
                        "Failed to fetch findings page %s: HTTP %s %s",
                        page,
                        response.status,
                        text,
                    )
                    break
                data = await response.json()
                items = data.get("items") or []
                if not items:
                    break

                for item in items:
                    vendor_blob = item.get(vendor_key) or {}
                    if min_sync_interval:
                        last_fetched_str = vendor_blob.get("last_fetched")
                        if last_fetched_str:
                            try:
                                last_fetched = datetime.fromisoformat(
                                    last_fetched_str.replace("Z", "+00:00")
                                )
                                if last_fetched > min_sync_interval:
                                    self._skip_finding(
                                        item,
                                        f"refreshed within last {self.max_age_hours}h",
                                    )
                                    continue
                            except ValueError:
                                pass
                    findings.append(item)

                pagination = data.get("pagination") or {}
                total_pages = pagination.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1

        logger.info(
            "Selected %d findings for %s refresh (program=%s)",
            len(findings),
            self.api_vendor,
            self.program_name,
        )
        return findings

    async def _get_vendor_credentials(self, vendor: str) -> Optional[Dict[str, str]]:
        try:
            headers: Dict[str, str] = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/programs/{self.program_name}"
            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                program_data = await response.json()

            if vendor == "recordedfuture":
                adapter = self.rf_adapter
            elif vendor == "threatstream":
                adapter = self.ts_adapter
            else:
                return None

            credentials: Dict[str, str] = {}
            for internal_name, db_field in adapter.get_credential_fields().items():
                value = program_data.get(db_field)
                if value:
                    credentials[internal_name] = value

            if not adapter.validate_credentials(credentials):
                return None
            return credentials
        except Exception as e:
            logger.error("Error fetching %s credentials: %s", vendor, e)
            return None

    async def _ensure_program_id(self):
        if self.program_id:
            return
        headers: Dict[str, str] = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        url = f"{self.api_base_url}/programs/{self.program_name}"
        session = await self._get_session()
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                self.program_id = data.get("id")
                if self.program_id:
                    logger.info("Resolved program_id=%s for %s", self.program_id, self.program_name)

    async def _patch_recordedfuture_data(
        self, finding_id: str, recordedfuture_data: Dict[str, Any]
    ) -> bool:
        return await self._patch_vendor_blob(
            finding_id, "recordedfuture-data", "recordedfuture_data", recordedfuture_data
        )

    async def _patch_threatstream_data(
        self, finding_id: str, threatstream_data: Dict[str, Any]
    ) -> bool:
        return await self._patch_vendor_blob(
            finding_id, "threatstream-data", "threatstream_data", threatstream_data
        )

    async def _patch_recordedfuture_derived_columns(
        self, finding_id: str, columns: Dict[str, Any]
    ) -> bool:
        if not columns:
            return True
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        url = (
            f"{self.api_base_url}/findings/typosquat/{finding_id}/"
            "recordedfuture-derived-columns"
        )
        session = await self._get_session()
        async with session.patch(url, json=columns, headers=headers) as response:
            return response.status in (200, 204)

    async def _patch_vendor_blob(
        self,
        finding_id: str,
        route_suffix: str,
        json_key: str,
        payload: Dict[str, Any],
    ) -> bool:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        url = f"{self.api_base_url}/findings/typosquat/{finding_id}/{route_suffix}"
        session = await self._get_session()
        async with session.patch(url, json={json_key: payload}, headers=headers) as response:
            if response.status not in (200, 204):
                text = await response.text()
                logger.error(
                    "PATCH %s failed for %s: HTTP %s %s",
                    route_suffix,
                    finding_id,
                    response.status,
                    text,
                )
                return False
            logger.info("PATCH %s succeeded for finding %s", route_suffix, finding_id)
            return True

    def _skip_finding(self, finding: Dict[str, Any], reason: str):
        self.results["skipped_count"] += 1
        self.results["skipped_findings"].append(
            {
                "finding_id": finding.get("id"),
                "domain": finding.get("typo_domain"),
                "reason": reason,
            }
        )

    def _record_error(self, finding: Dict[str, Any], error: str):
        self.results["error_count"] += 1
        self.results["errors"].append(
            {
                "finding_id": finding.get("id"),
                "domain": finding.get("typo_domain"),
                "error": error,
            }
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            if self.connector is None or self.connector.closed:
                self.connector = aiohttp.TCPConnector(
                    limit=10,
                    limit_per_host=5,
                    keepalive_timeout=30,
                    enable_cleanup_closed=True,
                )
            self.session = aiohttp.ClientSession(
                connector=self.connector, timeout=self.timeout
            )
        return self.session

    async def _cleanup_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
        if self.connector and not self.connector.closed:
            await self.connector.close()

    async def test_api_connectivity(self):
        headers: Dict[str, str] = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        url = f"{self.api_base_url}/programs"
        session = await self._get_session()
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise RuntimeError(f"API connectivity check failed: HTTP {response.status}")

    async def update_job_status(
        self,
        status: str,
        progress: int,
        message: str,
        results: Optional[Dict[str, Any]] = None,
    ):
        try:
            update_data: Dict[str, Any] = {
                "status": status,
                "progress": progress,
                "message": message,
            }
            if results is not None:
                update_data["results"] = results
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            url = f"{self.api_base_url}/jobs/{self.job_id}/status"
            session = await self._get_session()
            async with session.put(url, json=update_data, headers=headers) as response:
                if response.status not in (200, 204):
                    text = await response.text()
                    logger.warning(
                        "Failed to update job %s status: HTTP %s %s",
                        self.job_id,
                        response.status,
                        text,
                    )
        except Exception as e:
            logger.error("Error updating job status: %s", e)
