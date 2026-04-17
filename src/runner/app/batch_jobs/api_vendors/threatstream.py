import aiohttp
import asyncio
import urllib.parse
from typing import Dict, List, Any, Optional
import logging

from .base import BaseAPIVendor
from .config import vendor_config

logger = logging.getLogger(__name__)


class ThreatStreamAdapter(BaseAPIVendor):
    """ThreatStream API vendor implementation"""

    def __init__(self, timeout: aiohttp.ClientTimeout):
        super().__init__("threatstream", timeout)
        
        # Load configuration from vendor config manager
        self.config = vendor_config.get_vendor_config("threatstream") or {}
        self.query_config = dict(vendor_config.get_query_config("threatstream") or {})
        self.retry_config = vendor_config.get_retry_config("threatstream")
        
    def get_required_credentials(self) -> List[str]:
        """ThreatStream requires api_user and api_key"""
        return ["api_user", "api_key"]

    def get_credential_fields(self) -> Dict[str, str]:
        """Mapping of internal names to database field names"""
        return {
            "api_user": "threatstream_api_user",
            "api_key": "threatstream_api_key"
        }

    async def gather_domains(self, api_credentials: Dict[str, str], program_name: str, session: Optional[aiohttp.ClientSession] = None, date_range_hours: Optional[int] = None, custom_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Gather domains from Threatstream API using v2 intelligence endpoint

        Args:
            custom_query: ThreatStream q= query string (required); set via job_data.custom_query

        Note: date_range_hours parameter filters results by created_ts in the query
        """
        if custom_query is None or not str(custom_query).strip():
            raise ValueError(
                "ThreatStream intelligence gather requires a non-empty custom_query in job configuration "
                "(job_data.custom_query)."
            )
        main_query = custom_query.strip()

        # Calculate cutoff date if date_range_hours is provided
        cutoff_date = None
        if date_range_hours:
            from datetime import datetime, timedelta, timezone
            cutoff_date = datetime.now(timezone.utc) - timedelta(hours=date_range_hours)
            logger.info(f"Using date range filter: {date_range_hours} hours (cutoff: {cutoff_date.isoformat()})")

        logger.info(f"🔍 Making ThreatStream API calls for program: {program_name} using job custom_query")

        # Extract and validate credentials
        api_user = api_credentials.get("api_user")
        api_key = api_credentials.get("api_key")

        if not self.validate_credentials({"api_user": api_user, "api_key": api_key}):
            raise Exception("Missing API credentials: both api_user and api_key are required")

        try:
            domains = []
            offset = 0
            limit = self.query_config.get("limit", 1000)  # Configurable limit

            while True:
                self.api_stats['total_requests'] += 1

                # Add date filter if provided
                if cutoff_date:
                    # Format the date for ThreatStream API (remove microseconds and Z suffix, add proper format)
                    cutoff_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S')
                    date_filter = f"created_ts>={cutoff_str}"
                    querystr = f"{date_filter} and ({main_query})"
                    logger.info(f"Added date filter: {date_filter}")
                else:
                    querystr = main_query

                encoded_query = urllib.parse.quote(querystr)

                # Build final URL
                base_url = "https://api.threatstream.com/api/v2/intelligence"
                final_url = f"{base_url}/?q={encoded_query}&limit={limit}&offset={offset}"

                logger.info(f"ThreatStream API request: page={offset//limit + 1}, offset={offset}, limit={limit}")

                # Set up headers with authentication
                headers = {
                    "Authorization": f"apikey {api_user}:{api_key}"
                }

                # Use provided session or create a new one
                if session:
                    async with session.get(final_url, headers=headers) as response:
                        result = await self._process_response(response, domains, limit, offset)
                        if result == "break":
                            break
                        elif result == "continue":
                            continue
                        else:
                            offset = result
                else:
                    async with aiohttp.ClientSession(timeout=self.timeout) as temp_session:
                        async with temp_session.get(final_url, headers=headers) as response:
                            result = await self._process_response(response, domains, limit, offset)
                            if result == "break":
                                break
                            elif result == "continue":
                                continue
                            else:
                                offset = result

                # Small delay to be respectful to the API
                delay = self.query_config.get("rate_limit_delay", 1)
                await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"Error gathering from ThreatStream: {str(e)}")
            self.api_stats['failed_requests'] += 1
            raise

        self.api_stats['total_domains_found'] += len(domains)

        # Log final summary with domain type breakdown
        if domains:
            final_type_counts = {}
            for domain in domains:
                itype = domain.get("itype", "unknown")
                final_type_counts[itype] = final_type_counts.get(itype, 0) + 1

            type_summary = ", ".join([f"{itype}: {count}" for itype, count in final_type_counts.items()])
            logger.info(f"Successfully gathered {len(domains)} domains from ThreatStream API ({type_summary})")
        else:
            logger.info(f"Successfully gathered {len(domains)} domains from ThreatStream API")

        return domains

    def parse_domain_object(self, obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a ThreatStream domain object into standardized format"""
        try:
            domain_value = obj.get("value", "").strip()
            if not domain_value:
                return None

            # Extract relevant information from ThreatStream object
            domain_data = {
                "typo_domain": domain_value,
                "source": obj.get("source", "ThreatStream"),
                "threatscore": obj.get("threatscore"),
                "threat_type": obj.get("threat_type"),
                "confidence": obj.get("confidence", 0),
                "source_reported_confidence": obj.get("source_reported_confidence", 0),
                "retina_confidence": obj.get("retina_confidence", 0),
                "created_ts": obj.get("created_ts"),
                "modified_ts": obj.get("modified_ts"),
                "expiration_ts": obj.get("expiration_ts"),
                "status": obj.get("status", "unknown"),
                "is_public": obj.get("is_public", False),
                "is_anonymous": obj.get("is_anonymous", False),
                "tlp": obj.get("tlp"),
                "subtype": obj.get("subtype"),
                "description": obj.get("description"),
                "tags": [tag.get("name", "") for tag in (obj.get("tags") or []) if tag and tag.get("name")],
                "target_industries": obj.get("target_industry") or [],
                "locations": [loc.get("name", "") for loc in (obj.get("locations") or []) if loc and loc.get("name")],
                "trusted_circle_ids": obj.get("trusted_circle_ids") or [],
                "workgroups": obj.get("workgroups") or [],
                "resource_uri": obj.get("resource_uri"),
                "update_id": obj.get("update_id"),
                "id": obj.get("id"),
                "uuid": obj.get("uuid"),
                "feed_id": obj.get("feed_id"),
                "meta": obj.get("meta", {}),
                "can_add_public_tags": obj.get("can_add_public_tags", False),
                "is_editable": obj.get("is_editable", False),
                "source_locations": obj.get("source_locations") or [],
                "created_by": obj.get("created_by"),
                "rdns": obj.get("rdns"),
                "org": obj.get("org", ""),
                "asn": obj.get("asn", ""),
                "itype": obj.get("itype", ""),
                "owner_organization_id": obj.get("owner_organization_id")
            }

            return domain_data

        except Exception as e:
            logger.error(f"Error parsing ThreatStream domain object: {str(e)}")
            return None

    def update_config(self, config: Dict[str, Any]):
        """Update adapter configuration at runtime"""
        if "query" in config:
            query_updates = config["query"]
            for key, value in query_updates.items():
                if key in self.query_config:
                    self.query_config[key] = value
        
        if "retry" in config:
            self.retry_config.update(config["retry"])
        
        logger.info(f"Updated ThreatStream adapter config: query={self.query_config}, retry={self.retry_config}")

    async def _process_response(self, response, domains: List[Dict[str, Any]], limit: int, offset: int):
        """Process HTTP response and return next action"""
        if response.status == 200:
            data = await response.json()
            objects = data.get("objects", [])

            logger.info(f"API response: {len(objects)} objects returned")

            if not objects:
                logger.info(f"No more objects returned at offset {offset}")
                return "break"

            # Parse and filter domain objects
            batch_domains = []
            domain_type_counts = {}
            for obj in objects:
                if obj.get("type") == "domain" and obj.get("value"):
                    domain_data = self.parse_domain_object(obj)
                    if domain_data:
                        batch_domains.append(domain_data)
                        # Track domain types for logging
                        itype = obj.get("itype", "unknown")
                        domain_type_counts[itype] = domain_type_counts.get(itype, 0) + 1

            domains.extend(batch_domains)

            # Enhanced logging with domain type breakdown
            if domain_type_counts:
                type_breakdown = ", ".join([f"{itype}: {count}" for itype, count in domain_type_counts.items()])
                logger.info(f"Processed {len(batch_domains)} domains from current batch ({type_breakdown})")
            else:
                logger.info(f"Processed {len(batch_domains)} domains from current batch")

            # Check if we got fewer objects than the limit (last page)
            if len(objects) < limit:
                self.api_stats['successful_requests'] += 1
                return "break"

            self.api_stats['successful_requests'] += 1
            return offset + limit

        elif response.status == 401:
            response_text = await response.text()
            logger.error(f"Authentication failed: {response_text}")
            raise Exception("Authentication failed - check API credentials")
        elif response.status == 429:
            wait_time = self.retry_config.get("rate_limit_wait", 60)
            logger.warning(f"Rate limited by ThreatStream API, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
            return "continue"
        elif response.status == 400:
            response_text = await response.text()
            logger.error(f"Bad request - check query syntax: {response_text}")
            raise Exception(f"Bad request - check query syntax: {response.status}")
        else:
            response_text = await response.text()
            logger.error(f"ThreatStream API error {response.status}: {response_text}")
            raise Exception(f"ThreatStream API error {response.status}: {response_text}")

    async def fetch_intelligence_by_value(
        self,
        domain: str,
        api_credentials: Dict[str, str],
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        GET /api/v2/intelligence/?value=<domain> for cross-vendor enrichment (Recorded Future primary).
        Returns a threatstream_data-shaped dict (no typo_domain key) + last_fetched.
        """
        from datetime import datetime, timezone
        domain_clean = (domain or "").strip()
        if not domain_clean:
            return None
        logger.info(f"Fetching intelligence for domain: {domain_clean}")
        api_user = api_credentials.get("api_user")
        api_key = api_credentials.get("api_key")
        if not self.validate_credentials({"api_user": api_user, "api_key": api_key}):
            return None

        self.api_stats["total_requests"] += 1
        encoded = urllib.parse.quote(domain_clean, safe="")
        intel_url = f"https://api.threatstream.com/api/v2/intelligence/?value={encoded}"
        headers = {"Authorization": f"apikey {api_user}:{api_key}"}

        try:
            if session:
                async with session.get(intel_url, headers=headers) as response:
                    return await self._parse_intelligence_value_response(
                        response, domain_clean, datetime.now(timezone.utc).isoformat()
                    )
            async with aiohttp.ClientSession(timeout=self.timeout) as temp_session:
                async with temp_session.get(intel_url, headers=headers) as response:
                    return await self._parse_intelligence_value_response(
                        response, domain_clean, datetime.now(timezone.utc).isoformat()
                    )
        except Exception as e:
            logger.error(f"fetch_intelligence_by_value failed for {domain_clean}: {e}")
            self.api_stats["failed_requests"] += 1
            return None

    async def _parse_intelligence_value_response(
        self, response, domain_clean: str, fetched_at: str
    ) -> Optional[Dict[str, Any]]:
        if response.status == 200:
            logger.info(f"ThreatStream value lookup successful for {domain_clean}")
            data = await response.json()
            objects = data.get("objects") or []
            domain_objs = [o for o in objects if o.get("type") == "domain" and o.get("value")]
            logger.info(f"ThreatStream value lookup: {len(domain_objs)} domain objects found")
            if not domain_objs:
                logger.debug(f"ThreatStream value lookup: no domain objects for {domain_clean}")
                self.api_stats["successful_requests"] += 1
                return None

            def score(obj):
                return obj.get("threatscore") or 0

            dc = domain_clean.lower()
            exact = [o for o in domain_objs if (o.get("value") or "").strip().lower() == dc]
            pool = exact if exact else domain_objs
            best = max(pool, key=score)

            parsed = self.parse_domain_object(best)
            if not parsed:
                return None

            out = {k: v for k, v in parsed.items() if k != "typo_domain"}
            out["last_fetched"] = fetched_at
            if len(domain_objs) > 1:
                out["cross_vendor_intel_count"] = len(domain_objs)
            self.api_stats["successful_requests"] += 1
            return out

        if response.status == 401:
            response_text = await response.text()
            logger.error(f"ThreatStream value lookup auth failed: {response_text}")
            raise Exception("Authentication failed - check ThreatStream credentials")
        if response.status == 429:
            wait_time = self.retry_config.get("rate_limit_wait", 60)
            logger.warning(f"ThreatStream value lookup rate limited, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
            return None

        response_text = await response.text()
        logger.warning(f"ThreatStream value lookup HTTP {response.status}: {response_text}")
        self.api_stats["failed_requests"] += 1
        return None