import sys
import json
import logging
from typing import List
import subprocess
import os
import argparse
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag
import re
import tempfile
import uuid
from utils import (
    normalize_url_for_storage,
    normalize_domain_for_comparison,
    is_same_domain
)

from worker_logging import configure_worker_logging

configure_worker_logging()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
        if url.endswith('/fireprox/') or url.endswith('/fireprox'):
            standardized_url = f"{parsed.scheme}://{hostname}:{port}/fireprox/"
        return True, standardized_url
        
    except Exception:
        return False, ''


def run_katana(target: str, depth: int = 5, timeout: int = 0):
    command = [
        "katana", "-silent", "-d", str(depth), "-jc", "-jsl"
    ]
    if timeout > 0:
        command.append("-ct")
        command.append(str(int((timeout/100) * 80)))
    command.append("-u")
    command.append(target)
    logger.info(f"Running katana command: {command}")
    return subprocess.run(command, capture_output=True, text=True)

def run_httpx(urls: str):
    # Split the input by newlines to get individual URLs (newline-separated text)
    url_list = [x.strip() for x in urls.strip().split("\n") if x.strip()]
    
    # Create a temporary file to store URLs
    tmp_filename = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            for url in url_list:
                tmp.write(f"{url}\n")
            tmp_filename = tmp.name
        
        # Create a temporary directory to store the output in /tmp/httpx_output
        base_dir = "/tmp/httpx_output"
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        # generate a random directory name
        random_dir = os.path.join(base_dir, str(uuid.uuid4()))
        os.makedirs(random_dir)
        
        command = [
            "/usr/local/bin/httpx", "-sr", "-srd", random_dir, "-silent", "-json", "-fr",
            "-threads", "50", "-timeout", "10", "-include-chain", "-status-code", 
            "-content-length", "-tech-detect", "-no-color", "-efqdn", "-tls-grab", 
            "-pa", "-pipeline", "-http2", "-bp", "-ip", "-cname", "-asn", 
                "-random-agent", "-favicon", "-hash", "sha256", "-l", tmp_filename
            ]
        result = subprocess.run(command, capture_output=True, text=True)
        return result

    except Exception as e:
        logger.error(f"Error running httpx: {str(e)}")
        return None
    finally:
        # Always clean up the temporary file
        if tmp_filename and os.path.exists(tmp_filename):
            try:
                os.unlink(tmp_filename)
                logger.debug(f"Cleaned up temporary file: {tmp_filename}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {tmp_filename}: {str(e)}")

def parse_links(target_url: str):
    IGNORED_PATTERNS = [
        "^\\/$",
        "^#.*$",
        "^mailto:.*$",
        "^tel:.*$",
        "^javascript:.*$",
        "^data:.*$",
        "^blob:.*$",
        "^file:.*$",
        "^.*\\.css$",
        "^.*\\.png$",
        "^.*\\.jpg$",
        "^.*\\.jpeg$",
        "^.*\\.gif$",
    ]
    MATCH_PATTERNS = [
        "^http:.*$",
        "^https:.*$",
        "^\\/\\/.*$"
    ]

    # Extract target domain info for filtering
    target_parsed = urlparse(target_url)
    target_domain = normalize_domain_for_comparison(target_parsed.netloc.lower())
    logger.info(f"Target domain for comparison: {target_domain} (from {target_url})")

    logger.info("Starting parse_links()")
    links = {}
    try:
        # Loop through the subfolders in /tmp/httpx_output
        logger.info("Looking for subfolders in /tmp/httpx_output")
        subfolders = os.listdir("/tmp/httpx_output")
        logger.info(f"Found {len(subfolders)} subfolders")

        for subfolder in subfolders:
            logger.info(f"Processing subfolder: {subfolder}")
            index_path = os.path.join("/tmp/httpx_output", subfolder, "response", "index.txt")
            logger.info(f"Reading index file: {index_path}")
            with open(index_path, "r") as f:
                lines = f.readlines()
            logger.info(f"Read {len(lines)} lines from index file")

            for line in lines:
                line = line.strip()
                if "(200 OK)" in line:
                    line = line.split(" (200 OK)")[0].strip()
                    if len(line.split(" ")) != 2:
                        continue
                    url = line.split(" ")[1]
                    logger.info(f"Processing URL: {url}")
                    
                    # Extract the domain of the current page for comparison
                    current_page_parsed = urlparse(url)
                    current_page_domain = normalize_domain_for_comparison(current_page_parsed.netloc.lower())
                    logger.info(f"Current page domain: {current_page_domain}")
                    
                    # Next line should contain the file path
                    file_path = line.split(" ")[0].strip()
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                html_content = f.read()
                                # Parse HTML and extract links
                                soup = BeautifulSoup(html_content, 'html.parser')
                                # Extract links, filtering out ignored patterns
                                page_links = []
                                try:
                                    anchors = soup.find_all('a', href=True)
                                    logger.info(f"Found {len(anchors)} anchor tags in {url}")
                                    for a in anchors:
                                        if not isinstance(a, Tag):
                                            continue
                                        href = a.attrs.get('href')
                                        if not href or not isinstance(href, str):
                                            continue
                                        
                                        logger.debug(f"Processing href: {href}")
                                        
                                        # Skip ignored links first
                                        if any(re.match(pattern, href) for pattern in IGNORED_PATTERNS):
                                            logger.debug(f"Skipping ignored link: {href}")
                                            continue
                                        
                                        # Only process links that match valid URL patterns
                                        if any(re.match(pattern, href) for pattern in MATCH_PATTERNS):
                                            logger.debug(f"Processing valid link: {href}")
                                            # Parse the href to check if it's from a different domain
                                            try:
                                                # Handle relative URLs by joining with the current page URL
                                                if href.startswith('//'):
                                                    href = f"{current_page_parsed.scheme}:{href}"
                                                elif href.startswith('/'):
                                                    href = f"{current_page_parsed.scheme}://{current_page_parsed.netloc}{href}"
                                                elif not href.startswith(('http://', 'https://')):
                                                    href = f"{current_page_parsed.scheme}://{current_page_parsed.netloc}/{href}"

                                                logger.debug(f"Resolved href to: {href}")
                                                href_parsed = urlparse(href)
                                                href_domain = normalize_domain_for_comparison(href_parsed.netloc.lower())
                                                
                                                logger.debug(f"Comparing domains - href: {href_domain}, page: {current_page_domain}")
                                                
                                                # Only add if it's from a different domain (external link)
                                                if not is_same_domain(href_domain, current_page_domain):
                                                    # Normalize the external link for storage
                                                    normalized_href = normalize_url_for_storage(href)
                                                    if normalized_href:
                                                        logger.debug(f"Found external link: {normalized_href} (domain: {href_domain} vs page: {current_page_domain})")
                                                        page_links.append(normalized_href)
                                                else:
                                                    logger.debug(f"Skipping internal link: {href} (domain: {href_domain} vs page: {current_page_domain})")
                                            except Exception as e:
                                                logger.warning(f"Error processing href {href}: {str(e)}")
                                                continue
                                        else:
                                            logger.debug(f"Skipping non-matching link: {href}")

                                except Exception as e:
                                    logger.warning(f"Error parsing {file_path}: {str(e)}")
                                    continue

                                if page_links:
                                    # Normalize the page URL for consistent storage
                                    normalized_page_url = normalize_url_for_storage(url)
                                    if normalized_page_url:
                                        links[normalized_page_url] = page_links
                                        logger.info(f"Added {len(page_links)} external links for {normalized_page_url}")
                        except Exception as e:
                            logger.error(f"Error processing {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Error parsing index.txt: {str(e)}")

    logger.info(f"Finished parse_links(), found links for {len(links)} URLs")
    return links

def delete_temp_output():
    """Clean up temporary output directories to prevent disk space issues"""
    try:
        if os.path.exists("/tmp/httpx_output"):
            # Use shutil.rmtree() to recursively delete directory and contents
            import shutil
            shutil.rmtree("/tmp/httpx_output")
            logger.info("Successfully cleaned up /tmp/httpx_output directory")
    except Exception as e:
        logger.error(f"Error deleting temp output directory: {str(e)}")

def cleanup_old_temp_directories():
    """Clean up old temporary directories that might have been left behind"""
    try:
        import shutil
        import time

        base_dir = "/tmp/httpx_output"
        if not os.path.exists(base_dir):
            return

        current_time = time.time()
        # Remove directories older than 1 hour
        max_age = 3600  # 1 hour in seconds

        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path):
                try:
                    # Check if directory is old enough to be cleaned up
                    dir_age = current_time - os.path.getmtime(item_path)
                    if dir_age > max_age:
                        shutil.rmtree(item_path)
                        logger.info(f"Cleaned up old temp directory: {item_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up old temp directory {item_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Error during periodic cleanup: {str(e)}")


def _discovered_urls_from_katana_stdout(stdout: str) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for line in (stdout or "").splitlines():
        u = line.strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def run_full_crawl_for_target(
    normalized_url: str, depth: int, timeout: int, results: dict
) -> None:
    """Katana + httpx + link extraction for one seed (legacy full mode)."""
    results["urls"][normalized_url] = {
        "httpx_output": None,
        "httpx_error": None,
        "links": {},
    }
    katana_process = run_katana(normalized_url, depth, timeout)
    if not katana_process.stdout and katana_process.stderr:
        logger.error(f"Katana error for {normalized_url}: {katana_process.stderr}")
    elif katana_process.stdout:
        logger.info(f"Katana found URLs to process for {normalized_url}")
        logger.info(f"Running httpx against discovered URLs for {normalized_url}...")
        httpx_process = run_httpx(katana_process.stdout)
        if httpx_process:
            logger.info(f"Httpx process completed for {normalized_url}")
            if httpx_process.stderr:
                logger.warning(f"Httpx warnings for {normalized_url}: {httpx_process.stderr}")
                results["urls"][normalized_url]["httpx_error"] = httpx_process.stderr
            httpx_output = httpx_process.stdout
            httpx_output_obj = []
            for line in httpx_output.split("\n"):
                if line.strip():
                    try:
                        httpx_output_obj.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"Error parsing httpx output: {str(e)}")
                        continue
            results["urls"][normalized_url]["httpx_output"] = httpx_output_obj
            logger.info(f"Parsing links for {normalized_url}...")
            results["urls"][normalized_url]["links"] = parse_links(normalized_url)
            logger.info(
                "Extracted links for %s: %s pages with external links",
                normalized_url,
                len(results["urls"][normalized_url]["links"]),
            )
        else:
            logger.error(f"Failed to run httpx for {normalized_url}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("full", "discover", "probe"),
        default="full",
        help="full: katana+httpx per seed; discover: katana only; probe: httpx+links for stdin URLs",
    )
    parser.add_argument("--seed", type=str, default=None, help="Normalized seed URL (required for probe mode)")
    parser.add_argument("--depth", type=int, default=5, help="Crawling depth for katana")
    parser.add_argument("--timeout", type=int, required=False, default=0, help="Timeout for the script")
    args, unknown = parser.parse_known_args()
    depth = args.depth
    timeout = args.timeout
    mode = args.mode
    logger.info("Mode: %s, depth: %s, timeout: %s", mode, depth, timeout)

    input_urls = [url.strip() for url in sys.stdin.readlines() if url.strip()]
    logger.info("Received %s stdin lines", len(input_urls))

    cleanup_old_temp_directories()

    try:
        results: dict = {"urls": {}}

        if mode == "probe":
            if not args.seed:
                logger.error("probe mode requires --seed")
                sys.exit(1)
            is_valid, normalized_seed = is_valid_url(args.seed)
            if not is_valid:
                logger.error("Invalid --seed URL: %s", args.seed)
                sys.exit(1)
            if not input_urls:
                logger.error("probe mode requires at least one URL on stdin")
                sys.exit(1)
            probe_text = "\n".join(input_urls)
            results["urls"][normalized_seed] = {
                "httpx_output": None,
                "httpx_error": None,
                "links": {},
            }
            httpx_process = run_httpx(probe_text)
            if httpx_process:
                if httpx_process.stderr:
                    logger.warning("Httpx stderr: %s", httpx_process.stderr)
                    results["urls"][normalized_seed]["httpx_error"] = httpx_process.stderr
                httpx_output_obj = []
                for line in (httpx_process.stdout or "").split("\n"):
                    if line.strip():
                        try:
                            httpx_output_obj.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.error("Error parsing httpx output: %s", e)
                            continue
                results["urls"][normalized_seed]["httpx_output"] = httpx_output_obj
                results["urls"][normalized_seed]["links"] = parse_links(normalized_seed)
            else:
                logger.error("Failed to run httpx in probe mode")
        elif mode == "discover":
            if not input_urls:
                logger.error("No targets provided via stdin.")
                sys.exit(1)
            for target in input_urls:
                is_valid, normalized_url = is_valid_url(target)
                if not is_valid:
                    logger.error("Invalid target URL: %s", target)
                    results["urls"][target] = {
                        "error": "Invalid URL format",
                        "normalized_url": None,
                        "discovered": [],
                    }
                    continue
                results["urls"][normalized_url] = {"discovered": [], "katana_stderr": None}
                katana_process = run_katana(normalized_url, depth, timeout)
                if katana_process.stderr:
                    results["urls"][normalized_url]["katana_stderr"] = katana_process.stderr
                if not katana_process.stdout and katana_process.stderr:
                    logger.error("Katana error for %s: %s", normalized_url, katana_process.stderr)
                else:
                    discovered = _discovered_urls_from_katana_stdout(katana_process.stdout or "")
                    if normalized_url not in discovered:
                        discovered.insert(0, normalized_url)
                    results["urls"][normalized_url]["discovered"] = discovered
                    logger.info("Discover: %s URLs for %s", len(discovered), normalized_url)
        else:
            # full
            if not input_urls:
                logger.error("No targets provided via stdin.")
                sys.exit(1)
            for target in input_urls:
                is_valid, normalized_url = is_valid_url(target)
                if not is_valid:
                    logger.error("Invalid target URL: %s", target)
                    results["urls"][target] = {
                        "error": "Invalid URL format",
                        "normalized_url": None,
                    }
                    continue
                logger.info("Crawling target: %s", normalized_url)
                run_full_crawl_for_target(normalized_url, depth, timeout, results)

    finally:
        delete_temp_output()

    logger.info("All tasks completed, outputting results")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
