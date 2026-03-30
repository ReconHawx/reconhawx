#!/usr/bin/env python3

import sys
import json
import asyncio
import aiohttp
import os
import re
import socket
from datetime import datetime, timezone
import logging
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Timeout configuration
REQUEST_TIMEOUT = 30  # seconds per request
CONNECT_TIMEOUT = 10  # seconds for connection
RESPONSE_READ_TIMEOUT = 10  # seconds for reading response body
CREDENTIAL_FETCH_TIMEOUT = 10  # seconds for fetching credentials
DNS_RESOLUTION_TIMEOUT = 5  # seconds for DNS resolution
MAX_CONCURRENT_REQUESTS = 5  # maximum concurrent URL checks


class BrowserManager:
    """
    Manages browser lifecycle for headless browser checks.
    Reuses a single browser instance across multiple URL checks to avoid
    the overhead of launching a new browser process for each URL.
    """
    
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._stealth_script = """
            // Override webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Override chrome
            window.chrome = {
                runtime: {}
            };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """
    
    async def get_browser(self):
        """
        Get or create a browser instance. Thread-safe with async lock.
        
        Returns:
            Browser instance
        """
        async with self._lock:
            if self._browser is None:
                from playwright.async_api import async_playwright
                
                logger.info("Launching shared browser instance...")
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--disable-site-isolation-trials',
                        '--disable-web-security',
                        '--disable-features=BlockInsecurePrivateNetworkRequests'
                    ]
                )
                logger.info("Browser instance launched successfully")
            return self._browser
    
    async def create_context(self, user_agent: str = None, extra_headers: dict = None):
        """
        Create a new browser context with stealth settings.
        Each context is isolated (separate cookies, storage, etc.)
        
        Args:
            user_agent: Custom user agent string
            extra_headers: Additional HTTP headers
            
        Returns:
            Browser context
        """
        browser = await self.get_browser()
        
        context_options = {
            "user_agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        
        if extra_headers:
            context_options["extra_http_headers"] = extra_headers
        
        context = await browser.new_context(**context_options)
        await context.add_init_script(self._stealth_script)
        
        return context
    
    async def close(self):
        """Close the browser and cleanup resources"""
        async with self._lock:
            if self._browser:
                logger.info("Closing shared browser instance...")
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                logger.info("Browser resources cleaned up")
    
    @property
    def is_active(self) -> bool:
        """Check if browser is currently active"""
        return self._browser is not None


# Global browser manager instance (created per script execution)
_browser_manager: BrowserManager = None


async def get_browser_manager() -> BrowserManager:
    """Get or create the global browser manager instance"""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager


async def cleanup_browser_manager():
    """Cleanup the global browser manager"""
    global _browser_manager
    if _browser_manager is not None:
        await _browser_manager.close()
        _browser_manager = None


def detect_social_media_platform(url):
    """
    Detect if a URL is a social media platform and return the platform type.
    
    Returns:
        str: Platform name (facebook, instagram, twitter, linkedin) or None if not social media
    """
    try:
        parsed = urlparse(url)
        domain = parsed.hostname.lower() if parsed.hostname else ''
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Facebook: facebook.com, fb.com
        if domain in ['facebook.com', 'fb.com']:
            return 'facebook'
        
        # Instagram: instagram.com
        elif domain == 'instagram.com':
            return 'instagram'
        
        # Twitter/X: twitter.com, x.com
        elif domain in ['twitter.com', 'x.com']:
            return 'twitter'  # Normalize to 'twitter' for both domains
        
        # LinkedIn: linkedin.com
        elif domain == 'linkedin.com':
            return 'linkedin'
        
        return None
    except Exception as e:
        logger.error(f"Error detecting social media platform for URL {url}: {e}")
        return None


def _blocking_dns_lookup(domain: str) -> str:
    """
    Perform blocking DNS lookup. Meant to be run in a thread pool executor.
    
    Args:
        domain: Domain name to resolve
        
    Returns:
        IP address string if resolved
        
    Raises:
        socket.gaierror: If domain doesn't resolve
    """
    return socket.gethostbyname(domain)


async def check_domain_registration(domain):
    """
    Check if a domain is registered by attempting DNS resolution.
    
    Uses asyncio.run_in_executor to run blocking DNS lookup in a thread pool,
    preventing event loop blocking.
    
    Args:
        domain: Domain name to check
        
    Returns:
        bool: True if domain resolves (registered), False if DNS fails (not registered)
    """
    loop = asyncio.get_event_loop()
    
    try:
        # Run blocking DNS lookup in thread pool with timeout
        # This prevents blocking the event loop while waiting for DNS
        ip = await asyncio.wait_for(
            loop.run_in_executor(None, _blocking_dns_lookup, domain),
            timeout=DNS_RESOLUTION_TIMEOUT
        )
        logger.info(f"Domain {domain} resolved to {ip} - domain is registered")
        return True
    except socket.gaierror as e:
        # Domain does not resolve - not registered (this is an expected case for broken links)
        logger.info(f"Domain {domain} failed DNS resolution: {e} - domain is not registered")
        return False
    except asyncio.TimeoutError:
        # Timeout - treat as inconclusive, assume registered to be safe
        logger.warning(f"DNS resolution timeout for {domain} - treating as registered")
        return True
    except Exception as e:
        # Other errors - treat as inconclusive, assume registered to be safe
        logger.warning(f"DNS resolution error for {domain}: {e} - treating as registered")
        return True


async def check_general_link(session, url):
    """
    Check a general (non-social media) link for domain registration.
    Only returns findings if domain is not registered (hijackable).
    
    Args:
        session: aiohttp ClientSession
        url: URL to check
        
    Returns:
        dict: Finding dict if domain not registered, None otherwise
    """
    try:
        parsed = urlparse(url)
        domain = parsed.hostname.lower() if parsed.hostname else ''
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
        
        if not domain:
            logger.warning(f"Could not extract domain from URL: {url}")
            return None
        
        # Check domain registration
        is_registered = await check_domain_registration(domain)
        
        if not is_registered:
            # Domain not registered - hijackable link
            return {
                "link_type": "general",
                "domain": domain,
                "reason": "domain_not_registered",
                "status": "broken",
                "url": url,
                "checked_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            # Domain is registered - check HTTP status but don't store 404s
            try:
                request_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                async with session.get(url, allow_redirects=True, timeout=request_timeout) as resp:
                    status_code = resp.status
                    
                    # If domain is registered but returns 404, don't store (not hijackable)
                    if status_code == 404:
                        logger.info(f"URL {url} returns 404 but domain is registered - not storing")
                        return None
                    
                    # For other status codes (200, 500, etc.), domain is registered so not hijackable
                    # Only store if domain is not registered (already handled above)
                    return None
            except (asyncio.TimeoutError, aiohttp.ServerTimeoutError, aiohttp.ClientError):
                # Network errors but domain is registered - not hijackable
                logger.info(f"URL {url} has network error but domain is registered - not storing")
                return None
        
    except Exception as e:
        logger.error(f"Error checking general link {url}: {e}")
        return None


async def check_broken_links():
    """Main function to check broken links (social media and general)"""
    # Read inputs from stdin (one per line as full URLs)
    raw_inputs = [line.strip() for line in sys.stdin if line.strip()]
    
    if not raw_inputs:
        logger.warning("No inputs provided")
        print(json.dumps([]))
        return
    
    # Deduplicate inputs while preserving order
    seen = set()
    inputs = []
    for url in raw_inputs:
        if url not in seen:
            seen.add(url)
            inputs.append(url)
    
    if len(inputs) < len(raw_inputs):
        logger.info(f"Deduplicated {len(raw_inputs)} inputs to {len(inputs)} unique URLs")
    
    api_base_url = os.getenv("API_URL", "http://api:8000")
    internal_api_key = os.getenv("INTERNAL_SERVICE_API_KEY", "")
    program_name = os.getenv("PROGRAM_NAME", "")
    logger.info(f"API base URL: {api_base_url}")
    logger.info(f"Internal API key: {internal_api_key}")
    logger.info(f"Program name: {program_name}")
    logger.info(f"Inputs: {inputs}")
    results = []
    
    # Configure ClientSession with timeout and increased header size limits
    timeout = aiohttp.ClientTimeout(
        total=REQUEST_TIMEOUT,
        connect=CONNECT_TIMEOUT
    )

    async with aiohttp.ClientSession(
        timeout=timeout,
        max_line_size=16384,  # Increase from default 8190 to handle large headers
        max_field_size=16384   # Increase from default 8190 to handle large header values
    ) as session:
        # Process URLs concurrently with semaphore to limit concurrency
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        async def process_url(url):
            """Process a single URL with concurrency control"""
            logger.info(f"Processing URL: {url}")
            async with semaphore:
                try:
                    # Detect if this is a social media link
                    media_type = detect_social_media_platform(url)
                    logger.info(f"Media type for {url}: {media_type}")
                    if media_type:
                        # Social media link - check validity and return all statuses
                        return await process_social_media_link(session, url, media_type, api_base_url, internal_api_key)
                    else:
                        # General link - check domain registration
                        return await check_general_link(session, url)
                except Exception as e:
                    logger.error(f"Error checking {url}: {e}")
                    return None
        
        # Process all URLs concurrently
        tasks = [process_url(url) for url in inputs]
        findings_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect valid findings
        for finding in findings_list:
            if finding and isinstance(finding, dict):
                finding["program_name"] = program_name
                results.append(finding)
            elif isinstance(finding, Exception):
                logger.error(f"Exception in URL processing: {finding}")
    
    # Cleanup browser resources if any were used
    await cleanup_browser_manager()
    
    # Output results as JSON
    print(json.dumps(results))


async def process_social_media_link(session, url, media_type, api_base_url, internal_api_key):
    """Process a social media link and return finding"""
    try:
        # Fetch credentials if available
        creds = None
        if internal_api_key:
            headers = {"Authorization": f"Bearer {internal_api_key}"}
            try:
                cred_timeout = aiohttp.ClientTimeout(total=CREDENTIAL_FETCH_TIMEOUT)
                logger.info(f"Attempting to fetch credentials for platform: {media_type}")
                async with session.get(
                    f"{api_base_url}/social-media-credentials/{media_type}",
                    headers=headers,
                    timeout=cred_timeout
                ) as resp:
                    logger.info(f"Credential fetch response for {media_type}: status={resp.status}")
                    if resp.status == 200:
                        creds = await resp.json()
                        logger.info(f"Successfully fetched credentials for {media_type}: {creds.keys() if creds else 'None'}")
                    elif resp.status == 404:
                        logger.info(f"No credentials configured for platform: {media_type}")
                    else:
                        response_text = await resp.text()
                        logger.warning(f"Failed to fetch credentials for {media_type}: status={resp.status}, response={response_text[:200]}")
            except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
                logger.warning(f"Timeout fetching credentials for {media_type}: {e}")
            except Exception as e:
                logger.warning(f"Could not fetch credentials for {media_type}: {e}")
        
        # Check the platform
        finding = await check_platform(session, media_type, creds, url)
        if finding:
            finding["link_type"] = "social_media"
            # Return all statuses (valid, broken, error, throttled)
            return finding
        return None
    except Exception as e:
        logger.error(f"Error processing social media link {url}: {e}")
        return None


async def check_platform(session, media_type, creds, original_url):
    """Check a specific platform with timeout handling"""
    try:
        # Wrap platform check in timeout to prevent hanging
        if media_type == "facebook":
            return await asyncio.wait_for(
                check_facebook(session, original_url),
                timeout=REQUEST_TIMEOUT
            )
        elif media_type == "instagram":
            return await asyncio.wait_for(
                check_instagram(session, creds, original_url),
                timeout=REQUEST_TIMEOUT
            )
        elif media_type == "twitter":
            return await asyncio.wait_for(
                check_twitter(session, creds, original_url),
                timeout=REQUEST_TIMEOUT
            )
        elif media_type == "linkedin":
            return await asyncio.wait_for(
                check_linkedin(session, original_url),
                timeout=REQUEST_TIMEOUT
            )
    except asyncio.TimeoutError:
        logger.warning(f"Timeout checking {media_type} URL {original_url}")
        return {
            "media_type": media_type,
            "status": "error",
            "url": original_url,
            "error_code": "timeout",
            "response_data": {"message": f"Request timed out after {REQUEST_TIMEOUT}s"},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    except aiohttp.ServerTimeoutError as e:
        logger.warning(f"Server timeout checking {media_type} URL {original_url}: {e}")
        return {
            "media_type": media_type,
            "status": "error",
            "url": original_url,
            "error_code": "server_timeout",
            "response_data": {"error": str(e)},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking {media_type} URL {original_url}: {e}")
        return {
            "media_type": media_type,
            "status": "error",
            "url": original_url,
            "error_code": str(type(e).__name__),
            "response_data": {"error": str(e)},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    return None


# =============================================================================
# FACEBOOK DETECTION PATTERNS (Consolidated, multilingual)
# =============================================================================

# Patterns that IMMEDIATELY indicate a broken/unavailable page (high confidence)
# These are very specific to Facebook error pages and won't appear on valid pages
FACEBOOK_ERROR_PATTERNS_IMMEDIATE = [
    # English - Content unavailable messages
    r"content\s+is\s*n['\u2019]?t\s+available\s+at\s+the\s+moment",
    r"this\s+content\s+is\s*n['\u2019]?t\s+available",
    r"this\s+page\s+is\s*n['\u2019]?t\s+available",
    r"page\s+not\s+found",
    r"page\s+does\s*n['\u2019]?t\s+exist",
    # French - Content unavailable messages  
    r"contenu\s+n['\u2019]est\s+pas\s+disponible\s+pour\s+le\s+moment",
    r"ce\s+contenu\s+n['\u2019]est\s+pas\s+disponible",
    r"cette\s+page\s+n['\u2019]est\s+pas\s+disponible",
    # Error page UI elements (only appear on error pages)
    r"go\s+to\s+(news\s+)?feed",
    r"accéder\s+au\s+fil",
    r"go\s+to\s+help\s+pages?",
    r"visit\s+help\s+centre",
    r"accéder\s+aux\s+pages\s+d['\u2019]aide",
    # Error explanation text (very specific)
    r"when\s+this\s+happens,?\s+it['\u2019]?s\s+usually\s+because",
    r"this\s+problem\s+generally\s+comes\s+from",
    r"ce\s+problème\s+vient\s+généralement",
    r"owner\s+only\s+shared\s+(it|this\s+story)\s+with",
    r"propriétaire\s+n['\u2019]a\s+partagé",
    r"has\s+been\s+removed",
    r"a\s+été\s+supprimée?",
]

# Patterns that suggest error but need context validation (medium confidence)
FACEBOOK_ERROR_PATTERNS_CONTEXT = [
    r"content\s+is\s+not\s+available",
    r"content\s+is\s*n['\u2019]?t\s+available",
    r"contenu\s+n['\u2019]est\s+pas\s+disponible",
    r"not\s+available",
    r"n['\u2019]est\s+pas\s+disponible",
]

# Context indicators that boost confidence when found near error patterns
FACEBOOK_ERROR_CONTEXT_WORDS = {
    'sorry', 'désolé', 'problem', 'problème', 'deleted', 'supprimée',
    'removed', 'owner', 'propriétaire', 'shared', 'partagé', 'modified', 'modifié',
    'go back', 'retour', 'help', 'aide'
}

# Login page indicators
FACEBOOK_LOGIN_INDICATORS = [
    r"log\s+in\s+to\s+facebook",
    r"se\s+connecter\s+à\s+facebook",
    r"email\s+or\s+phone",
    r"adresse\s+e-mail\s+ou\s+numéro",
    r"forgotten\s+account",
    r"compte\s+oublié",
    r"create\s+new\s+account",
    r"créer\s+un\s+nouveau\s+compte",
]

# Valid page indicators (presence suggests real page, not error)
FACEBOOK_VALID_PAGE_INDICATORS = {
    'timeline', 'posts', 'about', 'photos', 'videos', 'events', 'community',
    'followers', 'likes', 'page transparency', 'transparence de la page',
    'verified', 'vérifié', 'category', 'catégorie', 'reviews', 'avis',
    'mentions', 'check-ins'
}

# Compile patterns once at module load for performance
_FB_ERROR_IMMEDIATE_RE = [re.compile(p, re.IGNORECASE) for p in FACEBOOK_ERROR_PATTERNS_IMMEDIATE]
_FB_ERROR_CONTEXT_RE = [re.compile(p, re.IGNORECASE) for p in FACEBOOK_ERROR_PATTERNS_CONTEXT]
_FB_LOGIN_RE = [re.compile(p, re.IGNORECASE) for p in FACEBOOK_LOGIN_INDICATORS]


def _fb_build_result(url: str, status: str, error_code: str = None, response_data: dict = None) -> dict:
    """Helper to build consistent Facebook result dicts"""
    result = {
        "media_type": "facebook",
        "status": status,
        "url": url,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }
    if error_code:
        result["error_code"] = error_code
    if response_data:
        result["response_data"] = response_data
    return result


def _fb_analyze_content(content: str, url: str) -> dict:
    """
    Analyze Facebook page content to determine if it's an error page.
    Uses confidence scoring for better accuracy.
    
    Returns:
        dict with 'is_error', 'is_login', 'confidence', 'matched_pattern'
    """
    content_lower = content.lower()
    
    # Phase 1: Check for login page (inconclusive result)
    for pattern in _FB_LOGIN_RE:
        if pattern.search(content_lower):
            # Check if there's actual page content beyond login
            valid_count = sum(1 for ind in FACEBOOK_VALID_PAGE_INDICATORS if ind in content_lower)
            if valid_count < 2:
                return {'is_error': False, 'is_login': True, 'confidence': 0.9, 'matched_pattern': 'login_page'}
    
    # Phase 2: Check immediate error patterns (high confidence)
    for pattern in _FB_ERROR_IMMEDIATE_RE:
        match = pattern.search(content_lower)
        if match:
            logger.info(f"Facebook immediate error pattern matched: '{match.group()}' for {url}")
            return {'is_error': True, 'is_login': False, 'confidence': 0.95, 'matched_pattern': match.group()}
    
    # Phase 3: Check context-dependent patterns with nearby context validation
    for pattern in _FB_ERROR_CONTEXT_RE:
        match = pattern.search(content_lower)
        if match:
            # Extract context window around the match
            start = max(0, match.start() - 200)
            end = min(len(content_lower), match.end() + 200)
            context_window = content_lower[start:end]
            
            # Count context indicators in the window
            context_score = sum(1 for word in FACEBOOK_ERROR_CONTEXT_WORDS if word in context_window)
            
            # Also check for error page UI elements anywhere
            has_error_ui = any(p.search(content_lower) for p in _FB_ERROR_IMMEDIATE_RE[-6:])  # UI element patterns
            
            if context_score >= 1 or has_error_ui:
                logger.info(f"Facebook context error pattern matched: '{match.group()}' (context_score={context_score}) for {url}")
                return {'is_error': True, 'is_login': False, 'confidence': 0.8, 'matched_pattern': match.group()}
    
    # Phase 4: Fallback - check for error phrases + lack of valid page content
    has_any_error_phrase = any(p.search(content_lower) for p in _FB_ERROR_CONTEXT_RE)
    if has_any_error_phrase:
        valid_count = sum(1 for ind in FACEBOOK_VALID_PAGE_INDICATORS if ind in content_lower)
        if valid_count < 2:
            logger.info(f"Facebook error phrase with no valid content for {url}")
            return {'is_error': True, 'is_login': False, 'confidence': 0.7, 'matched_pattern': 'error_phrase_no_content'}
    
    # No error detected
    return {'is_error': False, 'is_login': False, 'confidence': 0.0, 'matched_pattern': None}


async def check_facebook(session, original_url):
    """
    Check Facebook link validity using HTTP request and content analysis.
    
    Detection strategy (in order):
    1. Check if redirected away from Facebook domain -> broken
    2. Check HTTP status code (404 = broken, 429 = throttled)
    3. Analyze page content for error indicators using pattern matching
    4. Detect login pages (inconclusive)
    5. Default to valid if no error indicators found
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        request_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with session.get(original_url, headers=headers, allow_redirects=True, timeout=request_timeout) as resp:
            status_code = resp.status
            final_url = str(resp.url)
            
            # Quick check 1: Redirected away from Facebook?
            parsed_final = urlparse(final_url)
            final_domain = parsed_final.netloc.lower()
            if 'facebook.com' not in final_domain and 'fb.com' not in final_domain:
                return _fb_build_result(original_url, "broken", "redirected_away", {"final_url": final_url})
            
            # Quick check 2: HTTP status codes
            if status_code == 404:
                return _fb_build_result(original_url, "broken", str(status_code))
            elif status_code == 429:
                return _fb_build_result(original_url, "throttled", str(status_code))
            elif status_code in [301, 302]:
                return _fb_build_result(original_url, "valid")
            elif status_code != 200:
                return _fb_build_result(original_url, "error", str(status_code))
            
            # Status 200 - need to analyze content
            try:
                content = await asyncio.wait_for(resp.text(), timeout=RESPONSE_READ_TIMEOUT)
                
                # Check for empty/too short content
                if not content or len(content) < 500:
                    return _fb_build_result(original_url, "error", "insufficient_content",
                                           {"final_url": final_url, "content_length": len(content) if content else 0})
                
                # Analyze content using pattern matching
                analysis = _fb_analyze_content(content, original_url)
                
                if analysis['is_login']:
                    return _fb_build_result(original_url, "error", "login_required",
                                           {"final_url": final_url, "message": "Facebook requires login"})
                
                if analysis['is_error']:
                    return _fb_build_result(original_url, "broken", "content_unavailable",
                                           {"final_url": final_url, "matched_pattern": analysis['matched_pattern'],
                                            "confidence": analysis['confidence']})
                
                # No error indicators found - consider valid
                return _fb_build_result(original_url, "valid")
                
            except asyncio.TimeoutError:
                return _fb_build_result(original_url, "error", "content_read_timeout",
                                       {"final_url": final_url, "timeout": RESPONSE_READ_TIMEOUT})
            except Exception as e:
                logger.warning(f"Could not read Facebook response content for {original_url}: {e}")
                return _fb_build_result(original_url, "error", "content_read_error",
                                       {"final_url": final_url, "error": str(e)})
                
    except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
        return _fb_build_result(original_url, "error", "timeout", {"error": str(e)})
    except aiohttp.ClientError as e:
        return _fb_build_result(original_url, "error", str(type(e).__name__), {"error": str(e)})


async def check_instagram(session, creds, original_url):
    """Check Instagram link validity using headless browser (shared browser instance)"""
    logger.info(f"Checking Instagram URL {original_url} using headless browser")

    context = None
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        # Get shared browser manager
        browser_manager = await get_browser_manager()
        
        # Create a new context for this URL (contexts are isolated, browser is shared)
        context = await browser_manager.create_context(
            extra_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        page = await context.new_page()

        logger.info(f"Navigating to {original_url}")
        # Use networkidle to wait for network activity to settle
        try:
            await page.goto(original_url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            logger.warning(f"Network idle timeout, using domcontentloaded: {e}")
            await page.goto(original_url, wait_until="domcontentloaded", timeout=30000)
        
        # Small delay to let page render
        await page.wait_for_timeout(2000)
        
        # Wait for Cloudflare challenge to pass if present
        # Check for specific Cloudflare challenge indicators, not just the word "cloudflare"
        cloudflare_wait_time = 0
        max_cloudflare_wait = 15000  # Max 15 seconds for Cloudflare
        while cloudflare_wait_time < max_cloudflare_wait:
            content = await page.content()
            content_lower = content.lower()
            title = await page.title()
            final_url = page.url
            
            # Check for specific Cloudflare challenge page indicators
            # Don't just check for "cloudflare" as it may appear in page source even after challenge passes
            challenge_indicators = [
                "checking your browser",
                "just a moment",
                "ddos protection by cloudflare",
                "cf-browser-verification",
                "challenge-platform",
                "cf-challenge",
                "cf-ray",
                "ray id"  # Cloudflare Ray ID on challenge pages
            ]
            
            # Check if page title indicates challenge page
            is_challenge_title = "just a moment" in title.lower() or "checking your browser" in title.lower()
            
            # Check if content has challenge indicators
            has_challenge_content = any(indicator in content_lower for indicator in challenge_indicators)
            
            # Also check if page is still loading (very short content might indicate challenge)
            is_very_short = len(content) < 5000 and "instagram" not in title.lower()
            
            if is_challenge_title or (has_challenge_content and is_very_short):
                logger.info(f"Cloudflare challenge detected, waiting... ({cloudflare_wait_time}ms)")
                await page.wait_for_timeout(2000)
                cloudflare_wait_time += 2000
                continue
            
            # Cloudflare passed, break
            break
        
        # Final content check
        content = await page.content()
        content_lower = content.lower()
        title = await page.title()
        final_url = page.url
        logger.info(f"Page title: {title}")
        logger.info(f"Final URL: {final_url}")

        # Final check for Cloudflare challenge - be more specific
        challenge_indicators = [
            "checking your browser",
            "just a moment",
            "ddos protection by cloudflare",
            "cf-browser-verification"
        ]
        is_challenge_title = "just a moment" in title.lower() or "checking your browser" in title.lower()
        has_challenge_content = any(indicator in content_lower for indicator in challenge_indicators) and len(content) < 5000
        
        if is_challenge_title or has_challenge_content:
            return {
                "media_type": "instagram",
                "status": "error",
                "url": original_url,
                "error_code": "cloudflare_challenge",
                "response_data": {"message": "Cloudflare challenge blocking access after wait period"},
                "checked_at": datetime.now(timezone.utc).isoformat()
            }

        # Check if redirected to login/explore (indicates profile doesn't exist)
        if '/accounts/login/' in final_url or '/accounts/onetap/' in final_url or '/explore/' in final_url:
            return {
                "media_type": "instagram",
                "status": "broken",
                "url": original_url,
                "error_code": "redirect_to_login",
                "response_data": {"final_url": final_url},
                "checked_at": datetime.now(timezone.utc).isoformat()
            }

        # Check for error indicators FIRST (before checking for valid indicators)
        error_indicators = [
            "profile isn't available",  # Actual Instagram error text
            "the link may be broken",  # Actual Instagram error text
            "the link may be broken or the profile may have been removed",  # Full error message
            "profile may have been removed",  # Actual Instagram error text
            "sorry, this page isn't available",
            "the link you followed may be broken",
            "user not found",
            "this account doesn't exist",
            "page not found",
            "try searching for another",  # Error page helper text
        ]

        for indicator in error_indicators:
            if indicator in content_lower or indicator in title.lower():
                logger.info(f"Found error indicator '{indicator}'")
                return {
                    "media_type": "instagram",
                    "status": "broken",
                    "url": original_url,
                    "error_code": "error_page_detected",
                    "response_data": {"indicator": indicator, "final_url": final_url},
                    "checked_at": datetime.now(timezone.utc).isoformat()
                }

        # Check for valid profile indicators
        # Valid Instagram profiles have specific content in the page title and body
        # Title format: "Account Name (@username) • Instagram photos and videos"
        valid_title_pattern = "instagram photos and videos" in title.lower()
        
        # Check for profile data in page content
        valid_indicators = [
            "profile_pic_url",  # JSON data
            "edge_followed_by",  # JSON data
            "biography",  # JSON data
            "edge_owner_to_timeline_media",  # Posts data
            "edge_felix_video_timeline",  # Video posts
            "edge_media_collection",  # Media collection
            "is_private",  # Account privacy setting
            "is_verified",  # Account verification status
            "username",  # Username in JSON
            "full_name",  # Full name in JSON
        ]

        # Count valid indicators
        valid_count = sum(1 for indicator in valid_indicators if indicator in content_lower)
        
        # Also check for UI elements that indicate a valid profile
        # Valid profiles have specific UI elements that error pages don't have
        # Check for multiple profile indicators together (more reliable)
        has_posts = "posts" in content_lower
        has_followers = "followers" in content_lower
        has_following = "following" in content_lower
        
        # Valid profiles have at least posts AND (followers OR following)
        has_profile_elements = has_posts and (has_followers or has_following)

        # If title matches valid pattern OR we find profile data OR UI elements, it's valid
        if valid_title_pattern or valid_count >= 2 or has_profile_elements:
            return {
                "media_type": "instagram",
                "status": "valid",
                "url": original_url,
                "checked_at": datetime.now(timezone.utc).isoformat()
            }

        # Unclear - return error
        return {
            "media_type": "instagram",
            "status": "error",
            "url": original_url,
            "error_code": "unclear_response",
            "response_data": {"message": "Could not determine link validity", "content_length": len(content), "title": title},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    except PlaywrightTimeoutError:
        logger.error(f"Timeout loading Instagram profile for {original_url}")
        return {
            "media_type": "instagram",
            "status": "error",
            "url": original_url,
            "error_code": "timeout",
            "response_data": {"message": "Timeout loading profile page"},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking Instagram URL {original_url} with headless browser: {type(e).__name__}: {e}")
        return {
            "media_type": "instagram",
            "status": "error",
            "url": original_url,
            "error_code": "browser_error",
            "response_data": {"error": str(e)},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    finally:
        # Always close the context (browser is managed globally)
        if context:
            await context.close()


async def check_twitter(session, creds, original_url):
    """Check Twitter/X link validity using headless browser (shared browser instance)"""
    logger.info(f"Checking X/Twitter URL {original_url} using headless browser")

    context = None
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        # Get shared browser manager
        browser_manager = await get_browser_manager()
        
        # Create a new context for this URL (contexts are isolated, browser is shared)
        context = await browser_manager.create_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        logger.info(f"Navigating to {original_url}")
        await page.goto(original_url, wait_until="domcontentloaded", timeout=30000)
        # Wait longer for content to load
        await page.wait_for_timeout(8000)

        content = await page.content()
        content_lower = content.lower()
        title = await page.title()
        logger.info(f"Page title: {title}")

        # Check if we hit Cloudflare challenge
        if "cloudflare" in content_lower and ("challenge" in content_lower or "checking your browser" in content_lower):
            return {
                "media_type": "twitter",
                "status": "error",
                "url": original_url,
                "error_code": "cloudflare_challenge",
                "response_data": {"message": "Cloudflare challenge blocking access"},
                "checked_at": datetime.now(timezone.utc).isoformat()
            }

        # Check for error indicators FIRST (before checking for valid indicators)
        error_indicators = [
            "this account doesn't exist",
            "this account doesn\u2019t exist",
            "try searching for another",  # Error page helper text
            "account suspended",
            "this account has been suspended",
            "user not found",
            "page doesn't exist",
            "hmm...this page doesn't exist"
        ]

        for indicator in error_indicators:
            if indicator in content_lower or indicator in title.lower():
                logger.info(f"Found error indicator '{indicator}'")
                return {
                    "media_type": "twitter",
                    "status": "broken",
                    "url": original_url,
                    "error_code": "account_not_found",
                    "response_data": {"indicator": indicator},
                    "checked_at": datetime.now(timezone.utc).isoformat()
                }

        # Check for valid profile indicators
        # Must be specific enough to only match actual profile pages, not error pages
        # Valid profiles have specific content that error pages don't have
        valid_indicators = [
            "followers_count",  # JSON data in page source
            "following_count",  # JSON data in page source
            "loading posts by @",  # Loading indicator for valid profile (e.g., "Loading posts by @h3xitsec")
            "follow @",  # Follow button text (specific to profile pages)
            "profile timelines",  # Navigation element (specific to profile pages)
            "edge_owner_to_timeline_media",  # JSON data structure
            "user_info",  # JSON structure for user data
        ]

        # Count how many valid indicators we find
        valid_count = sum(1 for indicator in valid_indicators if indicator in content_lower)
        
        # Also check for UI text patterns that are specific to valid profiles
        # These patterns appear together on valid profiles, not on error pages
        # Need to be more specific - check for actual profile content, not just generic UI
        has_profile_tabs = "profile timelines" in content_lower and ("posts" in content_lower or "replies" in content_lower or "media" in content_lower)
        has_follow_button = "follow @" in content_lower  # Specific follow button text
        has_loading_posts = "loading posts by @" in content_lower  # Specific loading indicator
        
        # If we find specific JSON data OR specific profile UI elements, it's valid
        if valid_count >= 1 or has_profile_tabs or has_follow_button or has_loading_posts:
            return {
                "media_type": "twitter",
                "status": "valid",
                "url": original_url,
                "checked_at": datetime.now(timezone.utc).isoformat()
            }

        # Unclear - return error
        return {
            "media_type": "twitter",
            "status": "error",
            "url": original_url,
            "error_code": "unclear_response",
            "response_data": {"message": "Could not determine link validity", "content_length": len(content)},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    except PlaywrightTimeoutError:
        logger.error(f"Timeout loading X profile for {original_url}")
        return {
            "media_type": "twitter",
            "status": "error",
            "url": original_url,
            "error_code": "timeout",
            "response_data": {"message": "Timeout loading profile page"},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking X URL {original_url} with headless browser: {type(e).__name__}: {e}")
        return {
            "media_type": "twitter",
            "status": "error",
            "url": original_url,
            "error_code": "browser_error",
            "response_data": {"error": str(e)},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    finally:
        # Always close the context (browser is managed globally)
        if context:
            await context.close()


async def check_linkedin(session, original_url):
    """Check LinkedIn link validity"""
    check_url = original_url
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    try:
        request_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with session.get(check_url, headers=headers, allow_redirects=False, timeout=request_timeout) as resp:
            status_code = resp.status
            if status_code == 404:
                return {
                    "media_type": "linkedin",
                    "status": "broken",
                    "url": original_url,
                    "error_code": str(status_code),
                    "checked_at": datetime.now(timezone.utc).isoformat()
                }
            elif status_code == 200:
                return {
                    "media_type": "linkedin",
                    "status": "valid",
                    "url": original_url,
                    "checked_at": datetime.now(timezone.utc).isoformat()
                }
            elif status_code == 429:
                return {
                    "media_type": "linkedin",
                    "status": "throttled",
                    "url": original_url,
                    "error_code": str(status_code),
                    "checked_at": datetime.now(timezone.utc).isoformat()
                }
            elif status_code == 999:
                return {
                    "media_type": "linkedin",
                    "status": "error",
                    "url": original_url,
                    "error_code": str(status_code),
                    "response_data": {"message": "LinkedIn login required"},
                    "checked_at": datetime.now(timezone.utc).isoformat()
                }
            else:
                return {
                    "media_type": "linkedin",
                    "status": "error",
                    "url": original_url,
                    "error_code": str(status_code),
                    "checked_at": datetime.now(timezone.utc).isoformat()
                }
    except (asyncio.TimeoutError, aiohttp.ServerTimeoutError, aiohttp.ClientError) as e:
        logger.error(f"Error checking LinkedIn URL {original_url}: {e}")
        return {
            "media_type": "linkedin",
            "status": "error",
            "url": original_url,
            "error_code": "timeout" if isinstance(e, (asyncio.TimeoutError, aiohttp.ServerTimeoutError)) else str(type(e).__name__),
            "response_data": {"error": str(e)},
            "checked_at": datetime.now(timezone.utc).isoformat()
        }


if __name__ == "__main__":
    asyncio.run(check_broken_links())
