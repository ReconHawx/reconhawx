"""
Utility functions for domain processing and apex domain extraction.
"""
import tldextract
import logging
from typing import Dict, Any, List
from datetime import datetime
import re

logger = logging.getLogger(__name__)

def normalize_domain_for_comparison(domain: str) -> str:
    """
    Normalize domain for comparison operations.
    
    This function handles common domain normalization issues:
    - Converts to lowercase
    - Handles www vs non-www (removes www for comparison)
    - Removes trailing dots
    
    Args:
        domain (str): The domain to normalize
        
    Returns:
        str: Normalized domain for comparison
        
    Examples:
        >>> normalize_domain_for_comparison("WWW.example.com")
        'example.com'
        >>> normalize_domain_for_comparison("test.org.")
        'test.org'
    """
    if not domain:
        return ""
    
    # Convert to lowercase and remove trailing dots
    normalized = domain.lower().rstrip('.')
    
    # Remove www prefix for comparison
    if normalized.startswith('www.'):
        normalized = normalized[4:]
    
    return normalized

def is_same_domain(domain1: str, domain2: str) -> bool:
    """
    Compare two domains to determine if they are the same.
    
    Uses normalized domain comparison to handle www vs non-www,
    case differences, and trailing dots.
    
    Args:
        domain1 (str): First domain to compare
        domain2 (str): Second domain to compare
        
    Returns:
        bool: True if domains are the same, False otherwise
        
    Examples:
        >>> is_same_domain("www.example.com", "example.com")
        True
        >>> is_same_domain("WWW.test.org", "test.org")
        True
        >>> is_same_domain("example.com", "sub.example.com")
        False
    """
    if not domain1 or not domain2:
        return False
    
    norm1 = normalize_domain_for_comparison(domain1)
    norm2 = normalize_domain_for_comparison(domain2)
    
    return norm1 == norm2


def is_valid_domain(domain: str) -> bool:
    """
    Validate if a string is a valid domain name.
    
    Args:
        domain (str): The domain name to validate
        
    Returns:
        bool: True if the domain is valid, False otherwise
        
    Examples:
        >>> is_valid_domain("example.com")
        True
        >>> is_valid_domain("sub.example.co.uk")
        True
        >>> is_valid_domain("invalid..com")
        False
    """
    if not domain or len(domain) > 253:
        return False
        
    # Convert domain to lowercase for consistent validation
    domain = domain.lower()

    # Regular expression for validating domain names
    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    
    if not re.match(pattern, domain):
        return False
    
    # Check individual parts
    parts = domain.split('.')
    
    # Domain must have at least two parts
    if len(parts) < 2:
        return False
    
    # Validate each part
    for part in parts:
        # Each part must be between 1 and 63 characters
        if len(part) < 1 or len(part) > 63:
            return False
        
        # Parts cannot start or end with a hyphen
        if part.startswith('-') or part.endswith('-'):
            return False
        
        # Check for valid characters (letters, numbers, and hyphens)
        if not all(c.isalnum() or c == '-' for c in part):
            return False
    
    return True

def get_valid_domains(domains: List[str]) -> List[str]:
    """
    Filter a list of strings and return only the valid domain names.
    
    Args:
        domains (List[str]): List of potential domain names to validate
        
    Returns:
        List[str]: List containing only the valid domain names
        
    Examples:
        >>> get_valid_domains(["example.com", "invalid", "sub.domain.org"])
        ['example.com', 'sub.domain.org']
        >>> get_valid_domains(["not-valid", "invalid..com", "test.co.uk"])
        ['test.co.uk']
    """
    return [domain for domain in domains if is_valid_domain(domain)]


def get_whois_data(domain: str) -> Dict[str, Any]:
    """Retrieve WHOIS information using the python-whois library."""
    whois_info: Dict[str, Any] = {}

    try:
        import whois as pywhois  # lazy import

        record = pywhois.whois(domain)  # type: ignore[attr-defined]

        if not record or (not record.domain_name and not record.get("domain_name")):
            return whois_info  # No data found

        # Helper to collapse lists and convert datetimes to isoformat
        def _first(val):
            if isinstance(val, list):
                val = val[0] if val else None
            return val

        def _date_to_str(val):
            val = _first(val)
            if isinstance(val, datetime):
                return val.isoformat()
            return str(val) if val is not None else None

        whois_info["registrar"] = _first(record.registrar)
        whois_info["creation_date"] = _date_to_str(record.creation_date)
        whois_info["expiration_date"] = _date_to_str(record.expiration_date)
        whois_info["registrant_name"] = _first(record.get("name")) or _first(record.get("registrant_name"))
        whois_info["registrant_org"] = _first(record.get("org")) or _first(record.get("registrant_org"))
        whois_info["registrant_country"] = _first(record.country)
        whois_info["admin_email"] = _first(record.emails)

        # Drop keys that ended up None/empty
        whois_info = {k: v for k, v in whois_info.items() if v not in (None, "", [])}

    except Exception as e:
        # Any error (network, parsing, missing module) is non-fatal.
        logger.debug(f"WHOIS lookup failed for {domain}: {e}")

    return whois_info

def extract_apex_domain(domain_name: str) -> str:
    """
    Extract the apex domain from a given domain name.
    
    For example:
    - sub.example.com -> example.com
    - www.example.com -> example.com 
    - example.com -> example.com
    - deep.sub.example.com -> example.com
    - example.co.uk -> example.co.uk
    - sub.example.co.uk -> example.co.uk
    
    Args:
        domain_name (str): The domain name to extract apex from
        
    Returns:
        str: The apex domain
        
    Raises:
        ValueError: If domain_name is invalid or empty
    """
    if not domain_name or not isinstance(domain_name, str):
        raise ValueError("Domain name must be a non-empty string")
    
    # Clean the domain name
    domain_name = domain_name.strip().lower()
    
    if not domain_name:
        raise ValueError("Domain name cannot be empty after cleaning")
    
    try:
        # Use tldextract to parse the domain
        extracted = tldextract.extract(domain_name)
        
        # Construct the apex domain from domain + suffix
        if extracted.domain and extracted.suffix:
            apex_domain = f"{extracted.domain}.{extracted.suffix}"
            #logger.debug(f"Extracted apex domain '{apex_domain}' from '{domain_name}'")
            return apex_domain
        else:
            # If extraction fails, log warning and return original domain
            logger.warning(f"Could not extract apex domain from '{domain_name}', returning original")
            return domain_name
            
    except Exception as e:
        logger.error(f"Error extracting apex domain from '{domain_name}': {str(e)}")
        # Return the original domain if extraction fails
        return domain_name