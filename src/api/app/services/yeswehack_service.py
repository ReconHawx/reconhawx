"""YesWeHack API integration service for importing program scopes"""
import logging
import httpx
from typing import Dict, List, Any, Tuple
from urllib.parse import urlparse
import re

logger = logging.getLogger(__name__)


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
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.jwt_token}'
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
    
    def convert_scopes_to_regex(self, scopes: List[Dict[str, Any]]) -> Tuple[List[str], List[str], List[str], Dict[str, int]]:
        """Convert YesWeHack scope items to domain regex patterns and extract CIDR blocks
        
        Args:
            scopes: List of YesWeHack scope items
            
        Returns:
            Tuple of (in_scope_regexes, out_of_scope_regexes, cidr_blocks, summary)
            where summary is {"in_scope": count, "out_of_scope": count, "cidr_blocks": count}
        """
        in_scope_regexes = []
        out_of_scope_regexes = []
        cidr_blocks = []
        
        for scope_item in scopes:
            try:
                scope = scope_item.get('scope', '')
                scope_type = scope_item.get('scope_type', '')
                
                if not scope:
                    continue
                
                # Process web applications and other types
                if scope_type in ['web-application', 'other']:
                    # Parse the scope string and extract both domains and CIDRs
                    regexes, cidrs = self._parse_scope_string(scope)
                    
                    # Add domains to in-scope (YesWeHack scopes are typically in-scope by default)
                    for regex in regexes:
                        if regex and regex not in in_scope_regexes:
                            in_scope_regexes.append(regex)
                    
                    # Add CIDRs to cidr_blocks list
                    for cidr in cidrs:
                        if cidr and cidr not in cidr_blocks:
                            cidr_blocks.append(cidr)
                            
                # Skip mobile applications and other non-web scopes
                # as they don't map to domain regex patterns
                        
            except Exception as e:
                logger.warning(f"Failed to process scope item: {e}")
                continue
        
        summary = {
            "in_scope": len(in_scope_regexes),
            "out_of_scope": len(out_of_scope_regexes),
            "cidr_blocks": len(cidr_blocks)
        }
        
        logger.info(f"Converted scope: {summary['in_scope']} in-scope, {summary['out_of_scope']} out-of-scope patterns, {summary['cidr_blocks']} CIDR blocks")
        
        return in_scope_regexes, out_of_scope_regexes, cidr_blocks, summary
    
    def _parse_scope_string(self, scope: str) -> Tuple[List[str], List[str]]:
        """Parse YesWeHack scope string into regex patterns and CIDR blocks
        
        YesWeHack scopes can be in various formats:
        - URLs: https://account.post.ch
        - Wildcards: *.post.ch:80
        - Complex: (*.post.ch:80|*.post.ch:443) AND 194.41.128.0/17
        - Comma-separated: www.a.com,www.b.com
        
        CIDR blocks are extracted and returned separately.
        
        Args:
            scope: Scope string from YesWeHack
            
        Returns:
            Tuple of (regex_patterns, cidr_blocks)
        """
        regexes = []
        cidrs = []
        
        # Handle complex scope strings with AND/OR operators
        if ' AND ' in scope or ' OR ' in scope:
            # Extract the domain parts before AND/OR
            parts = re.split(r'\s+(?:AND|OR)\s+', scope)
            for part in parts:
                part = part.strip()
                # Check if it's a CIDR block
                if self._is_cidr_block(part):
                    logger.debug(f"Extracted CIDR block: {part}")
                    cidrs.append(part)
                    continue
                # Process each part
                part_regexes = self._parse_simple_scope(part)
                regexes.extend(part_regexes)
        else:
            # Simple scope - check if it's a CIDR block
            if self._is_cidr_block(scope):
                logger.debug(f"Extracted CIDR block: {scope}")
                cidrs.append(scope)
                return [], [scope]
            # Process the scope
            regexes = self._parse_simple_scope(scope)
        
        return regexes, cidrs
    
    def _parse_simple_scope(self, scope: str) -> List[str]:
        """Parse a simple scope string (no AND/OR operators)
        
        Args:
            scope: Simple scope string
            
        Returns:
            List of regex patterns
        """
        regexes = []
        
        # Remove parentheses if present
        scope = scope.strip('()')
        
        # Handle pipe-separated alternatives: *.post.ch:80|*.post.ch:443
        if '|' in scope:
            parts = scope.split('|')
            for part in parts:
                part_regexes = self._parse_single_scope(part.strip())
                regexes.extend(part_regexes)
        else:
            regexes = self._parse_single_scope(scope)
        
        return regexes
    
    def _parse_single_scope(self, scope: str) -> List[str]:
        """Parse a single scope item (URL, wildcard, or domain)
        
        Args:
            scope: Single scope string
            
        Returns:
            List of regex patterns (usually one, but could be multiple for comma-separated)
        """
        regexes = []
        
        # Check for comma-separated domains
        if ',' in scope and not scope.startswith('http'):
            # Comma-separated domains
            parts = [p.strip() for p in scope.split(',') if p.strip()]
            for part in parts:
                regex = self._convert_single_item_to_regex(part)
                if regex:
                    regexes.append(regex)
        else:
            # Single item
            regex = self._convert_single_item_to_regex(scope)
            if regex:
                regexes.append(regex)
        
        return regexes
    
    def _convert_single_item_to_regex(self, item: str) -> str:
        """Convert a single scope item to regex pattern
        
        Args:
            item: Single scope item (URL, wildcard, or domain)
            
        Returns:
            Regex pattern string
        """
        # Remove port number if present (e.g., *.post.ch:443)
        if ':' in item and not item.startswith('http'):
            # Domain with port - extract just the domain
            item = item.split(':')[0]
        
        # Handle URLs
        if item.startswith('http://') or item.startswith('https://'):
            return self._extract_domain_from_url(item)
        
        # Handle wildcards
        if item.startswith('*'):
            return self._convert_wildcard_to_regex(item)
        
        # Plain domain
        return self._escape_domain(item)
    
    def _convert_wildcard_to_regex(self, wildcard: str) -> str:
        r"""Convert wildcard pattern to regex

        Examples:
            *.example.com -> .*\.example\.com
            *.*.example.com -> .*\..*\.example\.com

        Args:
            wildcard: Wildcard pattern

        Returns:
            Regex pattern string
        """
        # Escape dots
        regex = wildcard.replace('.', r'\.')
        
        # Replace * with .*
        regex = regex.replace('*', '.*')
        
        return regex
    
    def _extract_domain_from_url(self, url: str) -> str:
        """Extract domain from URL and convert to regex pattern
        
        Args:
            url: URL string
            
        Returns:
            Regex pattern for the domain
        """
        try:
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
    
    def _escape_domain(self, domain: str) -> str:
        """Escape a plain domain for regex
        
        Args:
            domain: Plain domain string
            
        Returns:
            Escaped regex pattern
        """
        # Escape dots
        regex = domain.replace('.', r'\.')
        
        # Add exact match anchors
        regex = '^' + regex + '$'
        
        return regex
    
    def _is_cidr_block(self, text: str) -> bool:
        """Check if text is a CIDR block (IP range)
        
        Examples:
            194.41.128.0/17 -> True
            10.0.0.0/8 -> True
            example.com -> False
            
        Args:
            text: Text to check
            
        Returns:
            True if text appears to be a CIDR block
        """
        # CIDR pattern: xxx.xxx.xxx.xxx/xx
        cidr_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$'
        return bool(re.match(cidr_pattern, text.strip()))
    
    def validate_jwt(self) -> bool:
        """Quick validation that JWT is not empty
        
        Returns:
            True if JWT is present, False otherwise
        """
        return bool(self.jwt_token and len(self.jwt_token) > 20)

