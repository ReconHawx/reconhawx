"""YesWeHack API integration service for importing program scopes"""
import logging
import httpx
from typing import Dict, List, Any, Tuple, Optional
from urllib.parse import urlparse
import re

logger = logging.getLogger(__name__)

# Scope rows that map to hostname/CIDR patterns (aligned with Bugcrowd importer).
_ELIGIBLE_SCOPE_TYPES = frozenset({"web-application", "api", "other"})


class YesWeHackService:
    """Service for interacting with YesWeHack API"""

    BASE_URL = "https://api.yeswehack.com"
    TIMEOUT = 30.0  # seconds

    def __init__(self, jwt_token: str):
        """Initialize YesWeHack service with JWT token

        Args:
            jwt_token: YesWeHack JWT authentication token
        """
        self.jwt_token = jwt_token

    async def fetch_program_details(self, program_slug: str) -> Dict[str, Any]:
        """Fetch program details including scopes from YesWeHack API

        Args:
            program_slug: YesWeHack program slug (e.g., 'swiss-post')

        Returns:
            Program details dictionary

        Raises:
            httpx.HTTPStatusError: If API returns error status
            httpx.TimeoutException: If request times out
            Exception: For other errors
        """
        url = f"{self.BASE_URL}/programs/{program_slug}"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.jwt_token}",
        }

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                logger.info(f"Fetching program details for '{program_slug}' from YesWeHack API...")

                response = await client.get(url, headers=headers)

                # Raise exception for bad status codes
                response.raise_for_status()

                # Get the JSON response
                program_data = response.json()

                logger.info(f"Successfully fetched program '{program_slug}' ({program_data.get('title', 'Unknown')})")
                return program_data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Invalid YesWeHack JWT token")
                raise ValueError("Invalid YesWeHack JWT token. Please provide a valid JWT.")
            elif e.response.status_code == 404:
                logger.error(f"Program '{program_slug}' not found on YesWeHack")
                raise ValueError(f"Program '{program_slug}' not found on YesWeHack")
            elif e.response.status_code == 429:
                logger.error("YesWeHack API rate limit exceeded")
                raise ValueError("YesWeHack API rate limit exceeded. Please try again later.")
            else:
                logger.error(f"YesWeHack API error: {e.response.status_code} - {e.response.text}")
                raise ValueError(f"YesWeHack API error: {e.response.status_code}")

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching program details for '{program_slug}'")
            raise ValueError("Request to YesWeHack API timed out")

        except Exception as e:
            logger.exception(f"Unexpected error fetching program '{program_slug}': {e}")
            raise ValueError(f"Failed to fetch program details: {str(e)}")

    def convert_scopes_to_structured(
        self, scopes: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str], Dict[str, int]]:
        """Convert YesWeHack scope items to structured scope rows and extract CIDR blocks.

        Returns:
            Tuple of (in_scope rows, out_of_scope rows, cidr_blocks, summary)
            where each scope row is ``{"pattern": str, "wildcard": bool}``.
            Out-of-scope is empty until the API exposes a reliable per-item flag.
        """
        in_scope: List[Dict[str, Any]] = []
        out_scope: List[Dict[str, Any]] = []
        seen_in: set = set()
        cidr_blocks: List[str] = []

        for scope_item in scopes:
            try:
                scope = scope_item.get("scope", "")
                scope_type = scope_item.get("scope_type", "")

                if not scope or scope_type not in _ELIGIBLE_SCOPE_TYPES:
                    continue

                patterns, cidrs = self._parse_scope_string_structured(scope)
                for row in patterns:
                    pat = row["pattern"]
                    wc = row["wildcard"]
                    key = (pat, wc)
                    if key not in seen_in:
                        seen_in.add(key)
                        in_scope.append({"pattern": pat, "wildcard": wc})

                for cidr in cidrs:
                    if cidr and cidr not in cidr_blocks:
                        cidr_blocks.append(cidr)

            except Exception as e:
                logger.warning(f"Failed to process scope item: {e}")
                continue

        summary = {
            "in_scope": len(in_scope),
            "out_of_scope": len(out_scope),
            "cidr_blocks": len(cidr_blocks),
        }

        logger.info(
            "Converted YesWeHack scope: %s in-scope, %s out-of-scope patterns, %s CIDR blocks",
            summary["in_scope"],
            summary["out_of_scope"],
            summary["cidr_blocks"],
        )

        return in_scope, out_scope, cidr_blocks, summary

    def _parse_scope_string_structured(self, scope: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Parse YesWeHack scope string into structured hostname patterns and CIDR blocks.

        YesWeHack scopes can be in various formats:
        - URLs: https://account.post.ch
        - Wildcards: *.post.ch:80
        - Complex: (*.post.ch:80|*.post.ch:443) AND 194.41.128.0/17
        - Comma-separated: www.a.com,www.b.com
        """
        patterns: List[Dict[str, Any]] = []
        cidrs: List[str] = []

        if " AND " in scope or " OR " in scope:
            parts = re.split(r"\s+(?:AND|OR)\s+", scope)
            for part in parts:
                part = part.strip()
                if self._is_cidr_block(part):
                    logger.debug(f"Extracted CIDR block: {part}")
                    cidrs.append(part)
                    continue
                patterns.extend(self._parse_simple_scope_structured(part))
        else:
            if self._is_cidr_block(scope):
                logger.debug(f"Extracted CIDR block: {scope}")
                return [], [scope]
            patterns = self._parse_simple_scope_structured(scope)

        return patterns, cidrs

    def _parse_simple_scope_structured(self, scope: str) -> List[Dict[str, Any]]:
        scope = scope.strip("()")
        if "|" in scope:
            rows: List[Dict[str, Any]] = []
            for part in scope.split("|"):
                rows.extend(self._parse_single_scope_structured(part.strip()))
            return rows
        return self._parse_single_scope_structured(scope)

    def _parse_single_scope_structured(self, scope: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if "," in scope and not scope.startswith("http"):
            for part in scope.split(","):
                p = part.strip()
                row = self._single_scope_fragment_to_structured(p)
                if row:
                    rows.append(row)
        else:
            row = self._single_scope_fragment_to_structured(scope)
            if row:
                rows.append(row)
        return rows

    def _single_scope_fragment_to_structured(self, item: str) -> Optional[Dict[str, Any]]:
        """Map one scope fragment to ``{"pattern","wildcard"}`` or None if unusable."""
        item = item.strip()
        if not item:
            return None

        # Domain with port (e.g. *.post.ch:443), not a URL scheme
        if ":" in item and not item.startswith("http"):
            item = item.split(":")[0]

        if item.startswith("http://") or item.startswith("https://"):
            pat = self._plain_domain_from_url(item)
            if not pat:
                return None
            labels = pat.split(".")
            wc = any(lab == "*" for lab in labels)
            return {"pattern": pat, "wildcard": wc}

        pat = item.lower().strip(".")
        if not pat:
            return None
        labels = pat.split(".")
        wc = any(lab == "*" for lab in labels)
        return {"pattern": pat, "wildcard": wc}

    def _plain_domain_from_url(self, url: str) -> str:
        """Extract hostname from URL (lowercase)."""
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            parsed = urlparse(url)
            domain = parsed.netloc or ""
            if ":" in domain:
                domain = domain.split(":")[0]
            return domain.lower().strip(".")
        except Exception as e:
            logger.warning(f"Failed to parse URL '{url}': {e}")
            return ""

    def _is_cidr_block(self, text: str) -> bool:
        """Check if text is an IPv4 CIDR block."""
        cidr_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$"
        return bool(re.match(cidr_pattern, text.strip()))

    def validate_jwt(self) -> bool:
        """Quick validation that JWT is not empty"""
        return bool(self.jwt_token and len(self.jwt_token) > 20)
