"""HackerOne API integration service for importing program scopes"""
import logging
import httpx
from typing import Dict, List, Any, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class HackerOneService:
    """Service for interacting with HackerOne API"""
    
    BASE_URL = "https://api.hackerone.com/v1"
    TIMEOUT = 30.0  # seconds
    
    def __init__(self, username: str, api_token: str):
        """Initialize HackerOne service with credentials
        
        Args:
            username: HackerOne API username
            api_token: HackerOne API token
        """
        self.username = username
        self.api_token = api_token
        self.auth = (username, api_token)
    
    async def fetch_program_scope(self, program_handle: str) -> List[Dict[str, Any]]:
        """Fetch structured scopes for a specific program with pagination support
        
        Args:
            program_handle: HackerOne program handle (e.g., 'twitter', 'shopify')
            
        Returns:
            List of scope items
            
        Raises:
            httpx.HTTPStatusError: If API returns error status
            httpx.TimeoutException: If request times out
            Exception: For other errors
        """
        all_scopes = []
        next_url = f"{self.BASE_URL}/hackers/programs/{program_handle}/structured_scopes"
        page_count = 0
        
        headers = {
            'Accept': 'application/json'
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                while next_url:
                    page_count += 1
                    logger.info(f"Fetching scope page {page_count} for program '{program_handle}'...")
                    
                    response = await client.get(
                        next_url,
                        auth=self.auth,
                        headers=headers
                    )
                    
                    # Raise exception for bad status codes
                    response.raise_for_status()
                    
                    # Get the JSON response
                    scopes_data = response.json()
                    
                    # Add scopes from this page to our collection
                    if 'data' in scopes_data:
                        all_scopes.extend(scopes_data['data'])
                        logger.info(f"Found {len(scopes_data['data'])} scopes on page {page_count}")
                    
                    # Check for next page
                    next_url = scopes_data.get('links', {}).get('next')
                    
            logger.info(f"Successfully fetched {len(all_scopes)} total scopes for program '{program_handle}'")
            return all_scopes
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Invalid HackerOne API credentials")
                raise ValueError("Invalid HackerOne API credentials")
            elif e.response.status_code == 404:
                logger.error(f"Program '{program_handle}' not found on HackerOne")
                raise ValueError(f"Program '{program_handle}' not found on HackerOne")
            elif e.response.status_code == 429:
                logger.error("HackerOne API rate limit exceeded")
                raise ValueError("HackerOne API rate limit exceeded. Please try again later.")
            else:
                logger.error(f"HackerOne API error: {e.response.status_code} - {e.response.text}")
                raise ValueError(f"HackerOne API error: {e.response.status_code}")
                
        except httpx.TimeoutException:
            logger.error(f"Timeout fetching scope for program '{program_handle}'")
            raise ValueError("Request to HackerOne API timed out")
            
        except Exception as e:
            logger.exception(f"Unexpected error fetching scope for program '{program_handle}': {e}")
            raise ValueError(f"Failed to fetch program scope: {str(e)}")
    
    def convert_scope_to_regex(self, scopes: List[Dict[str, Any]]) -> Tuple[List[str], List[str], Dict[str, int]]:
        """Convert HackerOne scope items to domain regex patterns
        
        Args:
            scopes: List of HackerOne structured scope items
            
        Returns:
            Tuple of (in_scope_regexes, out_of_scope_regexes, summary)
            where summary is {"in_scope": count, "out_of_scope": count}
        """
        in_scope_regexes = []
        out_of_scope_regexes = []
        
        for scope in scopes:
            try:
                attrs = scope.get('attributes', {})
                
                # Only process bounty-eligible scopes
                if not attrs.get('eligible_for_bounty', False):
                    continue
                
                asset_type = attrs.get('asset_type', '')
                asset_identifier = attrs.get('asset_identifier', '')
                eligible_for_submission = attrs.get('eligible_for_submission', True)
                
                # Only process URL and WILDCARD asset types
                if asset_type not in ['URL', 'WILDCARD']:
                    continue
                
                # Check if asset_identifier contains comma-separated domains
                identifiers = self._split_comma_separated_domains(asset_identifier)
                
                # Process each identifier separately
                for identifier in identifiers:
                    # Convert to regex pattern
                    if asset_type == 'WILDCARD':
                        regex = self._convert_wildcard_to_regex(identifier)
                    elif asset_type == 'URL':
                        regex = self._extract_domain_from_url(identifier)
                    else:
                        continue
                    
                    # Add to appropriate list based on scope
                    if eligible_for_submission:
                        if regex and regex not in in_scope_regexes:
                            in_scope_regexes.append(regex)
                    else:
                        if regex and regex not in out_of_scope_regexes:
                            out_of_scope_regexes.append(regex)
                        
            except Exception as e:
                logger.warning(f"Failed to process scope item: {e}")
                continue
        
        summary = {
            "in_scope": len(in_scope_regexes),
            "out_of_scope": len(out_of_scope_regexes)
        }
        
        logger.info(f"Converted scope: {summary['in_scope']} in-scope, {summary['out_of_scope']} out-of-scope patterns")
        
        return in_scope_regexes, out_of_scope_regexes, summary
    
    def _split_comma_separated_domains(self, identifier: str) -> List[str]:
        """Split comma-separated domains into individual items
        
        Some HackerOne programs list multiple domains in a single scope item:
        'www.example1.com,www.example2.com,www.example3.com'
        
        Args:
            identifier: Asset identifier from HackerOne (may contain commas)
            
        Returns:
            List of individual domain identifiers
        """
        if not identifier:
            return []
        
        # Split by comma and strip whitespace from each part
        parts = [part.strip() for part in identifier.split(',')]
        
        # Filter out empty strings
        parts = [part for part in parts if part]
        
        if len(parts) > 1:
            logger.info(f"Split comma-separated scope item into {len(parts)} domains")
        
        return parts
    
    def _convert_wildcard_to_regex(self, wildcard: str) -> str:
        r"""Convert HackerOne wildcard pattern to regex

        Examples:
            *.example.com -> .*\.example\.com
            example.com -> example\.com
            *.*.example.com -> .*\..*\.example\.com

        Args:
            wildcard: Wildcard pattern from HackerOne

        Returns:
            Regex pattern string
        """
        # Escape special regex characters except *
        # Characters that need escaping: . ^ $ + ? { } [ ] \ | ( )
        regex = wildcard
        
        # Escape dots first
        regex = regex.replace('.', r'\.')
        
        # Replace * with .* (match any characters)
        regex = regex.replace('*', '.*')
        
        # Add anchors for exact matching if it doesn't start with wildcard
        if not wildcard.startswith('*'):
            regex = '^' + regex
        
        return regex
    
    def _extract_domain_from_url(self, url: str) -> str:
        r"""Extract domain from URL and convert to regex pattern

        Examples:
            https://example.com -> example\.com
            https://api.example.com/v1 -> api\.example\.com
            http://subdomain.example.com:8080 -> subdomain\.example\.com

        Args:
            url: URL from HackerOne

        Returns:
            Regex pattern for the domain
        """
        try:
            # Handle URLs that might not have scheme
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            parsed = urlparse(url)
            domain = parsed.netloc
            
            # Remove port if present
            if ':' in domain:
                domain = domain.split(':')[0]
            
            # Escape dots for regex
            regex = domain.replace('.', r'\.')
            
            # Add exact match anchors
            regex = '^' + regex + '$'
            
            return regex
            
        except Exception as e:
            logger.warning(f"Failed to parse URL '{url}': {e}")
            return ""
    
    def validate_credentials(self) -> bool:
        """Quick validation that credentials are not empty
        
        Returns:
            True if credentials are present, False otherwise
        """
        return bool(self.username and self.api_token)

