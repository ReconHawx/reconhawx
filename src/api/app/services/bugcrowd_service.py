"""
Bugcrowd API Integration Service

This service handles communication with the Bugcrowd platform for importing
program scopes into the recon platform.

Based on: https://github.com/sw33tLie/bbscope/blob/master/pkg/platforms/bugcrowd/bugcrowd.go
"""

import logging
import httpx
import re
import json
from typing import Dict, Any, List, Tuple, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class BugcrowdService:
    """Service for interacting with Bugcrowd platform"""
    
    BASE_URL = "https://bugcrowd.com"
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:82.0) Gecko/20100101 Firefox/82.0"
    
    def __init__(self, session_token: str):
        """Initialize Bugcrowd service
        
        Args:
            session_token: Bugcrowd session token (_bugcrowd_session cookie value)
        """
        self.session_token = session_token
        self.headers = {
            "Cookie": f"_bugcrowd_session={session_token}",
            "User-Agent": self.USER_AGENT,
            "Accept": "*/*"
        }
    
    async def fetch_program_scope(self, program_code: str) -> Dict[str, Any]:
        """Fetch program scope from Bugcrowd
        
        Args:
            program_code: Bugcrowd program code/handle (e.g., 'tesla', 'paypal', 'okta')
            
        Returns:
            Dictionary containing in-scope and out-of-scope targets
            
        Raises:
            ValueError: If API request fails or program not found
        """
        try:
            async with httpx.AsyncClient(follow_redirects=False) as client:
                # Step 1: Check if it's a regular program or engagement
                # First try to access the program URL to see if it redirects
                program_url = f"{self.BASE_URL}/{program_code}"
                
                logger.info(f"Checking program type for: {program_code}")
                response = await client.get(
                    program_url,
                    headers=self.headers,
                    timeout=30.0
                )
                
                # Check for redirect to /engagements/
                is_engagement = False
                if response.status_code == 302:
                    redirect_location = response.headers.get("location", "")
                    if "/engagements/" in redirect_location:
                        is_engagement = True
                        logger.info(f"Detected engagement program: {program_code}")
                
                if is_engagement:
                    # Handle engagement programs
                    return await self._fetch_engagement_scope(client, program_code)
                else:
                    # Handle regular programs
                    return await self._fetch_regular_program_scope(client, program_code)
                
        except httpx.RequestError as e:
            logger.exception(f"Network error fetching program '{program_code}': {e}")
            raise ValueError(f"Failed to connect to Bugcrowd: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching program '{program_code}': {e}")
            raise ValueError(f"Failed to fetch program scope: {str(e)}")
    
    async def _fetch_regular_program_scope(self, client: httpx.AsyncClient, program_code: str) -> Dict[str, Any]:
        """Fetch scope for regular (non-engagement) programs"""
        target_groups_url = f"{self.BASE_URL}/{program_code}/target_groups"
        
        logger.info(f"Fetching regular program target groups from: {target_groups_url}")
        response = await client.get(
            target_groups_url,
            headers=self.headers,
            timeout=30.0
        )
        
        if response.status_code == 401 or response.status_code == 403:
            raise ValueError("Invalid Bugcrowd session token or access forbidden")
        elif response.status_code == 404:
            raise ValueError(f"Program '{program_code}' not found on Bugcrowd")
        elif response.status_code == 406:
            raise ValueError("Bugcrowd WAF blocked the request - please try again later")
        elif response.status_code != 200:
            raise ValueError(f"Bugcrowd API error: {response.status_code} - {response.text}")
        
        target_groups_data = response.json()
        groups = target_groups_data.get("groups", [])
        
        if not groups:
            logger.warning(f"No target groups found for program '{program_code}'")
            return {"in_scope": [], "out_of_scope": []}
        
        logger.info(f"Found {len(groups)} target groups")
        
        # Fetch targets from each group
        in_scope_targets = []
        out_of_scope_targets = []
        
        for i, group in enumerate(groups):
            targets_url = group.get("targets_url")
            is_in_scope = group.get("in_scope", False)
            
            if not targets_url:
                continue
            
            logger.debug(f"Fetching targets from group {i+1}/{len(groups)}: {targets_url}")
            
            targets = await self._fetch_target_table(client, targets_url)
            
            if is_in_scope:
                in_scope_targets.extend(targets)
            else:
                out_of_scope_targets.extend(targets)
        
        logger.info(f"Fetched {len(in_scope_targets)} in-scope and {len(out_of_scope_targets)} out-of-scope targets")
        
        return {
            "in_scope": in_scope_targets,
            "out_of_scope": out_of_scope_targets
        }
    
    async def _fetch_engagement_scope(self, client: httpx.AsyncClient, program_code: str) -> Dict[str, Any]:
        """Fetch scope for engagement programs
        
        For engagements, we need to:
        1. Fetch the engagement HTML page
        2. Extract the brief version document URL from data-api-endpoints
        3. Fetch the brief document JSON
        4. Parse the data.scope array for targets
        """
        engagement_url = f"{self.BASE_URL}/engagements/{program_code}"
        
        logger.info(f"Fetching engagement page from: {engagement_url}")
        response = await client.get(
            engagement_url,
            headers=self.headers,
            timeout=30.0
        )
        
        if response.status_code == 401 or response.status_code == 403:
            raise ValueError("Invalid Bugcrowd session token or access forbidden")
        elif response.status_code == 404:
            raise ValueError(f"Engagement '{program_code}' not found on Bugcrowd")
        elif response.status_code == 406:
            raise ValueError("Bugcrowd WAF blocked the request - please try again later")
        elif response.status_code != 200:
            raise ValueError(f"Bugcrowd API error: {response.status_code} - {response.text}")
        
        # Parse HTML to extract API endpoints
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the ResearcherEngagementBrief div with data-api-endpoints
        brief_div = soup.find('div', {'data-react-class': 'ResearcherEngagementBrief'})
        
        if not brief_div:
            raise ValueError(f"Could not find engagement brief data for '{program_code}' - may require 2FA or compliance")
        
        api_endpoints_str = brief_div.get('data-api-endpoints', '{}')
        
        try:
            api_endpoints = json.loads(api_endpoints_str)
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse API endpoints for engagement '{program_code}'")
        
        # Get the brief version document URL
        brief_url = api_endpoints.get('engagementBriefApi', {}).get('getBriefVersionDocument')
        
        if not brief_url:
            logger.warning("No brief version document found - may require 2FA or compliance")
            raise ValueError(f"Engagement '{program_code}' requires additional authentication (2FA) or compliance acceptance")
        
        # Fetch the brief document JSON
        brief_full_url = f"{self.BASE_URL}{brief_url}.json"
        logger.info(f"Fetching engagement brief from: {brief_full_url}")
        
        brief_response = await client.get(
            brief_full_url,
            headers=self.headers,
            timeout=30.0
        )
        
        if brief_response.status_code != 200:
            raise ValueError(f"Failed to fetch engagement brief: {brief_response.status_code}")
        
        brief_data = brief_response.json()
        
        # Parse scope from data.scope array
        scope_array = brief_data.get('data', {}).get('scope', [])
        
        if not scope_array:
            logger.warning(f"No scope data found in engagement brief for '{program_code}'")
            return {"in_scope": [], "out_of_scope": []}
        
        logger.info(f"Found {len(scope_array)} scope groups in engagement brief")
        
        in_scope_targets = []
        out_of_scope_targets = []
        
        # Parse each scope element
        for scope_element in scope_array:
            is_in_scope = scope_element.get('inScope', False)
            targets = scope_element.get('targets', [])
            
            for target in targets:
                name = target.get('name', '')
                uri = target.get('uri', '')
                category = target.get('category', '')
                description = target.get('description', '')
                
                # Use name if URI is empty
                if not uri:
                    uri = name
                
                if not uri:
                    continue
                
                target_obj = {
                    "name": name,
                    "uri": uri,
                    "category": category,
                    "description": description
                }
                
                if is_in_scope:
                    in_scope_targets.append(target_obj)
                else:
                    out_of_scope_targets.append(target_obj)
        
        logger.info(f"Parsed {len(in_scope_targets)} in-scope and {len(out_of_scope_targets)} out-of-scope targets from engagement brief")
        
        return {
            "in_scope": in_scope_targets,
            "out_of_scope": out_of_scope_targets
        }
    
    async def _fetch_target_table(self, client: httpx.AsyncClient, targets_url: str) -> List[Dict[str, Any]]:
        """Fetch targets from a target table URL
        
        Args:
            client: HTTP client
            targets_url: Relative URL to targets table (e.g., '/targets/123')
            
        Returns:
            List of target dictionaries
        """
        try:
            full_url = f"{self.BASE_URL}{targets_url}"
            
            response = await client.get(
                full_url,
                headers=self.headers,
                timeout=30.0
            )
            
            if response.status_code == 403 or response.status_code == 406:
                raise ValueError("Bugcrowd WAF blocked the request")
            elif response.status_code != 200:
                logger.warning(f"Failed to fetch targets from {targets_url}: {response.status_code}")
                return []
            
            data = response.json()
            targets = data.get("targets", [])
            
            parsed_targets = []
            for target in targets:
                name = target.get("name", "").strip()
                uri = target.get("uri", "").strip()
                category = target.get("category", "")
                description = target.get("description", "")
                
                if uri:  # Only include targets with a URI
                    parsed_targets.append({
                        "name": name,
                        "uri": uri,
                        "category": category,
                        "description": description
                    })
            
            return parsed_targets
            
        except Exception as e:
            logger.warning(f"Error fetching target table from {targets_url}: {e}")
            return []
    
    def convert_targets_to_regex(self, scope_data: Dict[str, Any]) -> Tuple[List[str], List[str], List[str], Dict[str, int]]:
        """Convert Bugcrowd targets to domain regex patterns and IP ranges
        
        Args:
            scope_data: Dictionary with 'in_scope' and 'out_of_scope' target lists
            
        Returns:
            Tuple of (in_scope_regexes, out_of_scope_regexes, ip_list, summary)
        """
        in_scope_regexes = []
        out_of_scope_regexes = []
        ip_list = []
        
        # Process in-scope targets
        for target in scope_data.get("in_scope", []):
            uri = target.get("uri", "")
            category = target.get("category", "")
            
            # Convert based on category
            if category == "website":
                regex = self._convert_url_to_regex(uri)
                if regex and regex not in in_scope_regexes:
                    in_scope_regexes.append(regex)
            elif category == "api":
                regex = self._convert_url_to_regex(uri)
                if regex and regex not in in_scope_regexes:
                    in_scope_regexes.append(regex)
            elif category == "other":
                # Try to parse as domain or IP
                if self._is_ip_or_cidr(uri):
                    if uri not in ip_list:
                        ip_list.append(uri)
                else:
                    regex = self._convert_wildcard_to_regex(uri)
                    if regex and regex not in in_scope_regexes:
                        in_scope_regexes.append(regex)
        
        # Process out-of-scope targets
        for target in scope_data.get("out_of_scope", []):
            uri = target.get("uri", "")
            category = target.get("category", "")
            
            if category in ["website", "api", "other"]:
                if not self._is_ip_or_cidr(uri):
                    regex = self._convert_wildcard_to_regex(uri)
                    if regex and regex not in out_of_scope_regexes:
                        out_of_scope_regexes.append(regex)
        
        summary = {
            "in_scope": len(in_scope_regexes),
            "out_of_scope": len(out_of_scope_regexes),
            "ip_ranges": len(ip_list)
        }
        
        logger.info(f"Converted targets: {summary['in_scope']} in-scope, {summary['out_of_scope']} out-of-scope, {summary['ip_ranges']} IPs")
        
        return in_scope_regexes, out_of_scope_regexes, ip_list, summary
    
    def _convert_url_to_regex(self, url: str) -> Optional[str]:
        """Convert URL to domain regex pattern
        
        Args:
            url: URL from Bugcrowd (e.g., "https://example.com", "*.example.com")
            
        Returns:
            Regex pattern for the domain
        """
        # Remove protocol
        domain = url
        if "://" in domain:
            domain = domain.split("://", 1)[1]
        
        # Remove path
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        
        # Remove port
        if ":" in domain and not domain.count(":") > 1:  # Not IPv6
            domain = domain.split(":", 1)[0]
        
        # Check for wildcard
        if "*" in domain:
            return self._convert_wildcard_to_regex(domain)
        
        # Escape special regex characters
        domain_escaped = re.escape(domain)
        return f"^{domain_escaped}$"
    
    def _convert_wildcard_to_regex(self, pattern: str) -> Optional[str]:
        """Convert wildcard pattern to regex
        
        Args:
            pattern: Wildcard pattern (e.g., "*.example.com", "*.example.*")
            
        Returns:
            Regex pattern
        """
        # Remove protocol if present
        if "://" in pattern:
            pattern = pattern.split("://", 1)[1]
        
        # Remove path if present
        if "/" in pattern:
            pattern = pattern.split("/", 1)[0]
        
        # Remove port if present
        if ":" in pattern and not pattern.count(":") > 1:  # Not IPv6
            pattern = pattern.split(":", 1)[0]
        
        # Replace wildcards with regex
        parts = pattern.split("*")
        escaped_parts = [re.escape(part) for part in parts]
        regex = ".*".join(escaped_parts)
        
        logger.debug(f"Converted wildcard '{pattern}' to regex: {regex}")
        return regex
    
    def _is_ip_or_cidr(self, text: str) -> bool:
        """Check if text is an IP address or CIDR block
        
        Args:
            text: Text to check
            
        Returns:
            True if text appears to be an IP or CIDR
        """
        # CIDR pattern
        cidr_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$'
        if re.match(cidr_pattern, text.strip()):
            return True
        
        # IP pattern
        ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
        if re.match(ip_pattern, text.strip()):
            return True
        
        # IP range pattern (e.g., "192.168.1.1-192.168.1.255")
        if "-" in text and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}-\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', text.strip()):
            return True
        
        return False
    
    def validate_session_token(self, token: str) -> bool:
        """Basic validation of session token format
        
        Args:
            token: Session token to validate
            
        Returns:
            True if token appears valid
        """
        if not token or len(token) < 10:
            return False
        return True

