import re
from typing import List
from urllib.parse import urlparse
import logging
import tldextract

logger = logging.getLogger(__name__)

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

def parse_url(url: str):
    """
    Parse a URL and return a dictionary containing website information.
    Returns False if the URL is invalid.
    """
    _return = {}
    try:
        _parsed_url = urlparse(url)
        if _parsed_url.scheme is None or _parsed_url.hostname is None:
            raise Exception("Invalid URL")
        
        # Ensure hostname is lowercase
        hostname = _parsed_url.hostname.lower() if _parsed_url.hostname else None
        
        _port = None
        if _parsed_url.port:
            _port = _parsed_url.port
        else:
            if _parsed_url.scheme == 'https':
                _port = 443
            elif _parsed_url.scheme == 'http': 
                _port = 80
        _base_url = f"{_parsed_url.scheme}://{hostname}:{_port}"
    except Exception as e:
        logger.error(f"Error parsing URL {url}: {str(e)}")
        return False
    
    try:
        if _parsed_url.path:
            _path = _parsed_url.path
        else:
            _path = "/"
        _fixed_url = f"{_base_url}{_path}"
        _parsed_fixed_url = urlparse(_fixed_url)
    except Exception as e:
        logger.error(f"Error fixing url {url}: {str(e)}")
        return False
    
    _return = {
        "url": _fixed_url,
        "path": _parsed_fixed_url.path,
        "hostname": _parsed_fixed_url.hostname,
        "port": _parsed_fixed_url.port,
        "scheme": _parsed_fixed_url.scheme,
    }
    return _return

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

def get_valid_ips(ips: List[str]) -> List[str]:
    """
    Filter a list of strings and return only the valid IP addresses.
    """
    return [ip for ip in ips if is_valid_ip(ip)]

def is_valid_ip(ip: str) -> bool:
    """
    Validate if a string is a valid IP address.
    """
    return re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip) is not None

def is_valid_url(url: str) -> tuple[bool, str]:
    """
    Validate if a string is a valid URL and return it in a standardized format.
    
    Args:
        url (str): The URL to validate
        
    Returns:
        tuple[bool, str]: A tuple containing (is_valid, standardized_url)
        
    Examples:
        >>> is_valid_url("https://example.com")
        (True, 'https://example.com:443')
        >>> is_valid_url("http://sub.domain.org:8080")
        (True, 'http://sub.domain.org:8080')
        >>> is_valid_url("invalid-url")
        (False, '')
    """
    if not url:
        return False, ''
    
    # Convert URL to lowercase for consistent validation
    url = url.lower()
    
    try:
        # Parse URL using urllib
        parsed = urlparse(url)
        
        # Validate scheme
        if parsed.scheme not in ['http', 'https']:
            return False, ''
        
        # Validate hostname
        if not is_valid_domain(parsed.netloc.split(':')[0]):
            return False, ''
        
        # Get or set default port
        if parsed.port:
            # Validate port number
            if parsed.port < 1 or parsed.port > 65535:
                return False, ''
            port = str(parsed.port)
        else:
            port = '443' if parsed.scheme == 'https' else '80'
        
        # Construct standardized URL with scheme://hostname:port
        hostname = parsed.netloc.split(':')[0]
        standardized_url = f"{parsed.scheme}://{hostname}:{port}"
        
        return True, standardized_url
        
    except Exception:
        return False, ''

def get_valid_urls(urls: List[str]) -> List[str]:
    """
    Filter a list of URLs and return only the valid ones in standardized format.
    
    Args:
        urls (List[str]): List of potential URLs to validate
        
    Returns:
        List[str]: List containing only the valid URLs in scheme://hostname:port format
        
    Examples:
        >>> get_valid_urls(["https://example.com", "invalid", "http://test.org"])
        ['https://example.com:443', 'http://test.org:80']
        >>> get_valid_urls(["https://sub.domain.org:8443", "not-valid"])
        ['https://sub.domain.org:8443']
    """
    valid_urls = []
    for url in urls:
        is_valid, standardized_url = is_valid_url(url)
        if is_valid:
            valid_urls.append(standardized_url)
    return valid_urls

def normalize_url_for_storage(url: str) -> str:
    """
    Standardize URL format for consistent storage in the database.
    
    This function ensures URLs are stored in a consistent format:
    - Lowercase scheme and hostname
    - Explicit port numbers (443 for https, 80 for http)
    - Trailing slash removed from root paths
    - Proper path handling
    
    Args:
        url (str): The URL to normalize
        
    Returns:
        str: Normalized URL in format scheme://hostname:port/path
        
    Examples:
        >>> normalize_url_for_storage("https://EXAMPLE.com")
        'https://example.com:443/'
        >>> normalize_url_for_storage("http://test.org:8080/path/")
        'http://test.org:8080/path'
        >>> normalize_url_for_storage("https://site.com/")
        'https://site.com:443/'
    """
    if not url:
        return ""
    
    try:
        # Parse the URL
        parsed = urlparse(url.lower())
        
        # Validate required components
        if not parsed.scheme or not parsed.hostname:
            logger.warning(f"Invalid URL format: {url}")
            return ""
        
        # Set default ports if not specified
        port = parsed.port
        if not port:
            port = 443 if parsed.scheme == 'https' else 80
        
        # Handle path normalization
        path = parsed.path
        if not path:
            path = "/"
        elif path.endswith("/") and len(path) > 1:
            # Remove trailing slash except for root path
            path = path.rstrip("/")
        
        # Construct normalized URL
        normalized = f"{parsed.scheme}://{parsed.hostname}:{port}{path}"
        
        return normalized
        
    except Exception as e:
        logger.error(f"Error normalizing URL {url}: {str(e)}")
        return ""

def normalize_url_for_comparison(url: str) -> str:
    """
    Normalize URL for comparison operations (link matching, deduplication).
    
    This function creates a consistent format for URL comparison:
    - Lowercase scheme and hostname
    - Explicit port numbers
    - Consistent path handling
    - Removes query parameters and fragments for comparison
    
    Args:
        url (str): The URL to normalize for comparison
        
    Returns:
        str: Normalized URL suitable for comparison
        
    Examples:
        >>> normalize_url_for_comparison("https://EXAMPLE.com/path?param=1#fragment")
        'https://example.com:443/path'
        >>> normalize_url_for_comparison("http://test.org:8080/")
        'http://test.org:8080/'
    """
    if not url:
        return ""
    
    try:
        # Parse the URL
        parsed = urlparse(url.lower())
        
        # Validate required components
        if not parsed.scheme or not parsed.hostname:
            return ""
        
        # Set default ports if not specified
        port = parsed.port
        if not port:
            port = 443 if parsed.scheme == 'https' else 80
        
        # Handle path normalization (keep trailing slash for root)
        path = parsed.path
        if not path:
            path = "/"
        elif path.endswith("/") and len(path) > 1:
            # Remove trailing slash except for root path
            path = path.rstrip("/")
        
        # Construct normalized URL (ignore query and fragment for comparison)
        normalized = f"{parsed.scheme}://{parsed.hostname}:{port}{path}"
        
        return normalized
        
    except Exception as e:
        logger.error(f"Error normalizing URL for comparison {url}: {str(e)}")
        return ""


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