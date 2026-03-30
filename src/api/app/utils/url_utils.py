from fastapi import Request
from urllib.parse import urlparse
from typing import List
import logging

logger = logging.getLogger(__name__)

def create_status_url(request: Request, resource_type: str, resource_id: str) -> str:
    """Create a status URL for a resource"""
    base_url = str(request.base_url).rstrip('/')
    return f"{base_url}/{resource_type}/{resource_id}/status" 

def parse_url(url: str):
    """
    Parse a URL and return a dictionary containing website information.
    Returns False if the URL is invalid.
    """
    try:
        _parsed_url = urlparse(url)
        if _parsed_url.scheme is None or _parsed_url.hostname is None:
            raise Exception("Invalid URL")
        
        # Ensure hostname is lowercase
        hostname = _parsed_url.hostname.lower() if _parsed_url.hostname else None
        
        # Determine port
        port = None
        if _parsed_url.port:
            port = _parsed_url.port
        else:
            if _parsed_url.scheme == 'https':
                port = 443
            elif _parsed_url.scheme == 'http': 
                port = 80
        
        # Determine path
        path = _parsed_url.path if _parsed_url.path else "/"
        
        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path
        
        _return = {
            "url": url,
            "path": path,
            "hostname": hostname,
            "port": port,
            "scheme": _parsed_url.scheme,
        }
        return _return
        
    except Exception as e:
        logger.error(f"Error parsing URL {url}: {str(e)}")
        return False

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

def get_root_url(url: str) -> str:
    """
    Get the root URL (scheme://hostname:port/) for a given URL.
    Used to inherit relations (certificate, services, subdomain) from the root when
    a path URL is added without full test_http data.
    
    Examples:
        >>> get_root_url("https://example.com:443/some/path")
        'https://example.com:443/'
        >>> get_root_url("http://test.org:8080/api/v1")
        'http://test.org:8080/'
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.lower())
        if not parsed.scheme or not parsed.hostname:
            return ""
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        return f"{parsed.scheme}://{parsed.hostname}:{port}/"
    except Exception:
        return ""


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
