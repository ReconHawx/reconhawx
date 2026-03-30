from urllib.parse import urlparse
import logging

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