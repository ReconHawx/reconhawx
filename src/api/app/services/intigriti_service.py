"""
Intigriti API Integration Service

This service handles communication with the Intigriti API for importing
program scopes into the recon platform.
"""

import logging
import httpx
import re
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class IntigritiService:
    """Service for interacting with Intigriti API"""
    
    BASE_URL = "https://api.intigriti.com/external/researcher/v1"
    
    def __init__(self, api_token: str):
        """Initialize Intigriti service
        
        Args:
            api_token: Intigriti API token from user profile
        """
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json"
        }
    
    async def find_program_by_handle(self, program_handle: str) -> Optional[Dict[str, Any]]:
        """Find a program by handle from the programs list
        
        Fetches all programs using pagination and searches for the matching handle.
        
        Args:
            program_handle: Handle of the program to find (case-insensitive)
            
        Returns:
            Program dictionary with id and basic info, or None if not found
            
        Raises:
            ValueError: If API request fails
        """
        try:
            async with httpx.AsyncClient() as client:
                all_records = []
                limit = 100  # Fetch 100 programs per page
                offset = 0
                program_handle_lower = program_handle.lower()
                
                while True:
                    # Fetch page with limit and offset
                    response = await client.get(
                        f"{self.BASE_URL}/programs",
                        headers=self.headers,
                        params={"limit": limit, "offset": offset},
                        timeout=30.0
                    )
                    
                    if response.status_code == 401:
                        raise ValueError("Invalid Intigriti API token")
                    elif response.status_code == 403:
                        raise ValueError("Intigriti API access forbidden - check token permissions")
                    elif response.status_code == 429:
                        raise ValueError("Intigriti API rate limit exceeded - please try again later")
                    elif response.status_code != 200:
                        raise ValueError(f"Intigriti API error: {response.status_code} - {response.text}")
                    
                    data = response.json()
                    records = data.get("records", [])
                    
                    if not records:
                        # No more records, stop pagination
                        break
                    
                    logger.debug(f"Fetched {len(records)} programs (offset: {offset})")
                    
                    # Search in current page
                    for program in records:
                        if program.get("handle", "").lower() == program_handle_lower:
                            logger.info(f"Found program by handle: {program.get('name')} (handle: {program.get('handle')})")
                            return program
                    
                    # Add to all records for debugging
                    all_records.extend(records)
                    
                    # If we got fewer records than the limit, we've reached the end
                    if len(records) < limit:
                        break
                    
                    # Move to next page
                    offset += limit
                
                # If not found, log available handles for debugging
                available_handles = [p.get("handle") for p in all_records if p.get("handle")]
                logger.info(f"Searched through {len(all_records)} total programs. Available handles: {', '.join(available_handles)}")
                
                # Log similar handles
                similar = [p.get("handle") for p in all_records if program_handle_lower in p.get("handle", "").lower()]
                if similar:
                    logger.warning(f"Handle '{program_handle}' not found. Similar handles found: {', '.join(similar)}")
                else:
                    logger.warning(f"Handle '{program_handle}' not found. No similar handles found in {len(all_records)} programs.")
                
                return None
                
        except httpx.RequestError as e:
            logger.exception(f"Network error fetching programs: {e}")
            raise ValueError(f"Failed to connect to Intigriti API: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error finding program '{program_handle}': {e}")
            raise ValueError(f"Failed to find program: {str(e)}")
    
    async def fetch_program_details(self, program_id: str) -> Dict[str, Any]:
        """Fetch detailed program information including scopes
        
        Args:
            program_id: Intigriti program ID
            
        Returns:
            Full program details including domains/scopes
            
        Raises:
            ValueError: If API request fails
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/programs/{program_id}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 401:
                    raise ValueError("Invalid Intigriti API token")
                elif response.status_code == 404:
                    raise ValueError(f"Program '{program_id}' not found on Intigriti")
                elif response.status_code == 429:
                    raise ValueError("Intigriti API rate limit exceeded - please try again later")
                elif response.status_code != 200:
                    raise ValueError(f"Intigriti API error: {response.status_code} - {response.text}")
                
                data = response.json()
                logger.info(f"Fetched program details: {data.get('name')} with {len(data.get('domains', {}).get('content', []))} scope items")
                
                return data
                
        except httpx.RequestError as e:
            logger.exception(f"Network error fetching program '{program_id}': {e}")
            raise ValueError(f"Failed to connect to Intigriti API: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching program '{program_id}': {e}")
            raise ValueError(f"Failed to fetch program details: {str(e)}")
    
    def convert_scopes_to_regex(self, domains_data: Dict[str, Any]) -> Tuple[List[str], List[str], List[str], Dict[str, int]]:
        """Convert Intigriti scope items to domain regex patterns and extract IP ranges
        
        Args:
            domains_data: The 'domains' object from Intigriti program details
            
        Returns:
            Tuple of (in_scope_regexes, out_of_scope_regexes, ip_list, summary)
            where summary is {"in_scope": count, "out_of_scope": count, "ip_ranges": count}
        """
        in_scope_regexes = []
        out_of_scope_regexes = []
        ip_list = []
        
        content = domains_data.get("content", [])
        
        for scope_item in content:
            try:
                scope_type = scope_item.get("type", {}).get("value", "")
                endpoint = scope_item.get("endpoint", "")
                tier = scope_item.get("tier", {}).get("value", "")
                
                if not endpoint:
                    continue
                
                # Determine if in-scope or out-of-scope based on tier
                is_out_of_scope = tier in ["Out Of Scope", "No Bounty"]
                
                # Process based on type
                if scope_type == "Url":
                    regex = self._convert_url_to_regex(endpoint)
                    if regex:
                        if is_out_of_scope:
                            if regex not in out_of_scope_regexes:
                                out_of_scope_regexes.append(regex)
                        else:
                            if regex not in in_scope_regexes:
                                in_scope_regexes.append(regex)
                
                elif scope_type == "Wildcard":
                    regex = self._convert_wildcard_to_regex(endpoint)
                    if regex:
                        if is_out_of_scope:
                            if regex not in out_of_scope_regexes:
                                out_of_scope_regexes.append(regex)
                        else:
                            if regex not in in_scope_regexes:
                                in_scope_regexes.append(regex)
                
                elif scope_type == "IpRange":
                    # Extract individual IPs (can be comma-separated or CIDR)
                    ips = self._parse_ip_range(endpoint)
                    for ip in ips:
                        if ip and ip not in ip_list and not is_out_of_scope:
                            ip_list.append(ip)
                
            except Exception as e:
                logger.warning(f"Failed to process scope item: {e}")
                continue
        
        summary = {
            "in_scope": len(in_scope_regexes),
            "out_of_scope": len(out_of_scope_regexes),
            "ip_ranges": len(ip_list)
        }
        
        logger.info(f"Converted scope: {summary['in_scope']} in-scope, {summary['out_of_scope']} out-of-scope patterns, {summary['ip_ranges']} IP ranges")
        
        return in_scope_regexes, out_of_scope_regexes, ip_list, summary
    
    def _convert_url_to_regex(self, url: str) -> Optional[str]:
        """Convert URL to domain regex pattern
        
        Args:
            url: URL from Intigriti (e.g., "https://example.com" or "example.com")
            
        Returns:
            Regex pattern for the domain
        """
        # Extract domain from URL
        domain = url
        
        # Remove protocol if present
        if "://" in domain:
            domain = domain.split("://", 1)[1]
        
        # Remove path if present
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        
        # Remove port if present
        if ":" in domain:
            domain = domain.split(":", 1)[0]
        
        # Escape special regex characters
        domain_escaped = re.escape(domain)
        
        logger.debug(f"Converted URL '{url}' to regex: ^{domain_escaped}$")
        return f"^{domain_escaped}$"
    
    def _convert_wildcard_to_regex(self, wildcard: str) -> Optional[str]:
        """Convert wildcard pattern to regex
        
        Args:
            wildcard: Wildcard pattern (e.g., "*.example.com", "*.example.*")
            
        Returns:
            Regex pattern
        """
        # Remove port if present
        if ":" in wildcard:
            wildcard = wildcard.split(":", 1)[0]
        
        # Escape the domain part
        # Replace * with .* for regex, but escape other special characters
        parts = wildcard.split("*")
        escaped_parts = [re.escape(part) for part in parts]
        regex = ".*".join(escaped_parts)
        
        logger.debug(f"Converted wildcard '{wildcard}' to regex: {regex}")
        return regex
    
    def _parse_ip_range(self, ip_range: str) -> List[str]:
        """Parse IP range string into individual IPs or CIDR blocks
        
        Intigriti can provide:
        - Comma-separated IPs: "192.168.1.1,192.168.1.2,192.168.1.3"
        - CIDR blocks: "192.168.1.0/24"
        - Individual IPs: "192.168.1.1"
        
        Args:
            ip_range: IP range string from Intigriti
            
        Returns:
            List of individual IP addresses or CIDR blocks
        """
        ips = []
        
        # Split by comma for multiple IPs
        parts = [part.strip() for part in ip_range.split(",")]
        
        for part in parts:
            if part:
                ips.append(part)
        
        logger.debug(f"Parsed IP range '{ip_range}' into {len(ips)} entries")
        return ips

