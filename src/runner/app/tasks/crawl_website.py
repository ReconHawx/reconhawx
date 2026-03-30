import json
import logging
from typing import Dict, List, Any, Optional
import base64
from .base import Task, AssetType
from models.assets import Url
from utils import (
    parse_url, 
    get_valid_urls, 
    normalize_url_for_storage, 
    normalize_url_for_comparison
)
from urllib.parse import urlparse
import dns.resolver
import re

logger = logging.getLogger(__name__)

class CrawlWebsite(Task):
    name = "crawl_website"
    description = "Crawl a website"
    input_type = AssetType.STRING
    output_types = [AssetType.URL]
    chunk_size = 1


    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate command to use the worker crawl_website.py script"""
        try:
            targets_to_process = input_data if isinstance(input_data, list) else [input_data]
            # Filter valid URLs from the targets list
            urls_to_process = get_valid_urls(targets_to_process)
            
            if len(urls_to_process) > 0:
                # Get depth parameter, default to 5 if not provided
                depth = params.get("depth", 5) if params else 5
                
                # Join URLs with here document for proper newlines
                urls_text = '\n'.join(urls_to_process)
                command = f"cat << 'EOF' | python3 crawl_website.py --depth {depth}"
                if params.get("timeout", None) is not None:
                    command += f" --timeout {params.get('timeout')}"
                command += f"\n{urls_text}\nEOF"
                return command
            return ""
        except Exception as e:
            logger.error(f"Error generating command: {e}")
            return ""
    
    def _resolve_dns_safely(self, hostname: str, timeout: int = 5) -> List[str]:
        """
        Safely resolve DNS for a hostname with proper error handling and timeout.
        
        Args:
            hostname (str): The hostname to resolve
            timeout (int): DNS resolution timeout in seconds
            
        Returns:
            List[str]: List of IP addresses, empty list if resolution fails
        """
        if not hostname:
            logger.warning("Empty hostname provided for DNS resolution")
            return []
        
        try:
            # Configure DNS resolver with timeout
            resolver = dns.resolver.Resolver()
            resolver.timeout = timeout
            resolver.lifetime = timeout
            
            # Resolve A records
            records = resolver.resolve(hostname, 'A')
            # Convert RRset to list of IP addresses
            ips = [str(record) for record in records]  # type: ignore
            
            logger.debug(f"Successfully resolved {hostname} to {ips}")
            return ips
            
        except dns.resolver.NXSUBDOMAIN:
            logger.warning(f"DNS resolution failed: {hostname} does not exist (NXSUBDOMAIN)")
            return []
        except dns.resolver.NoAnswer:
            logger.warning(f"DNS resolution failed: {hostname} has no A records (NoAnswer)")
            return []
        except dns.resolver.Timeout:
            logger.warning(f"DNS resolution timed out for {hostname} after {timeout} seconds")
            return []
        except dns.resolver.NoNameservers:
            logger.warning(f"DNS resolution failed: no nameservers available for {hostname}")
            return []
        except Exception as e:
            logger.error(f"DNS resolution failed for {hostname}: {str(e)}")
            return []
    
    def _split_concatenated_json(self, text: str) -> List[str]:
        """
        Split a string containing multiple concatenated JSON objects from httpx output.
        Each object always starts with {"timestamp": and follows a consistent format.
        Returns a list of individual JSON strings.
        """
        json_objects = []
        
        # Find positions of all JSON object starts with the timestamp marker
        start_positions = [match.start() for match in re.finditer(r'{"timestamp":', text)]
        
        if not start_positions:
            # If no timestamp markers found, try to parse the whole string as JSON
            try:
                json.loads(text)
                return [text]
            except json.JSONDecodeError:
                logger.error("No valid JSON objects found in output")
                return []
        
        # Extract each JSON object
        for i, start_pos in enumerate(start_positions):
            if i < len(start_positions) - 1:
                # Get JSON string from current start to next start
                json_str = text[start_pos:start_positions[i+1]]
            else:
                # Get JSON string from current start to end
                json_str = text[start_pos:]
            
            # Add the object to our results - we'll validate during processing
            json_objects.append(json_str)
        
        return json_objects
    
    def _filter_duplicate_urls(self, url_list: List[Url]) -> List[Url]:
        """
        Filter out duplicate URLs from the list based on their URL string
        """
        seen_urls = set()
        unique_urls = []
        
        for url_obj in url_list:
            # Use normalized URL for comparison to avoid duplicates
            normalized_url = normalize_url_for_comparison(url_obj.url)
            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                unique_urls.append(url_obj)
        
        logger.info(f"Filtered {len(url_list) - len(unique_urls)} duplicate URLs")
        return unique_urls

    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse the output from the worker script into URL assets"""
        urls = []
        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        if not normalized_output or normalized_output.strip() == "":
            logger.warning("Empty output received")
            return {AssetType.URL: []}

        logger.info(f"Processing output of length: {len(normalized_output)}")

        try:
            # Parse the worker output as JSON
            worker_result = json.loads(normalized_output)
            
            # Extract the links or urls data
            urls_data = worker_result.get("urls", {})
            
            # Process each URL and its data
            for base_url, url_info in urls_data.items():
                logger.info(f"Processing URL data for {base_url}")
                
                # Get the links dictionary for this base URL
                links_dict = url_info.get("links", {})
                logger.info(f"Found links for {len(links_dict)} URLs")
                
                # Log the actual links found for debugging
                for page_url, page_links in links_dict.items():
                    logger.info(f"Page {page_url} has {len(page_links)} external links: {page_links[:5]}...")  # Show first 5 links
                
                # Process httpx output first
                httpx_output = url_info.get("httpx_output", "")
                if httpx_output:
                    logger.info(f"Processing httpx output for {base_url} (length: {len(httpx_output)})")
                    # Process httpx JSON output line by line
                    for line in httpx_output.strip().split('\n'):
                        try:
                            # Parse each line as a separate JSON object
                            item = json.loads(line)
                            if not item.get("failed", True):
                                # Get the specific links for this URL from the links dictionary
                                current_url = normalize_url_for_storage(item.get("url", ""))
                                # Only get links if this specific URL has an entry in the links dictionary
                                current_links = links_dict.get(current_url, [])
                                self._process_entry(item, urls, current_links)
                        except json.JSONDecodeError:
                            logger.warning(f"Error parsing httpx line as JSON: {line[:100]}...")
                
                # Process katana output for any URLs not found by httpx
                katana_output = url_info.get("katana_output", "")
                if katana_output:
                    logger.info(f"Processing katana output for {base_url} (length: {len(katana_output)})")
                    # Split katana output into individual URLs
                    discovered_urls = [url.strip() for url in katana_output.split('\n') if url.strip()]
                    logger.info(f"Found {len(discovered_urls)} URLs from katana for {base_url}")
                    
                    # Create URL objects for each discovered URL that wasn't already processed by httpx
                    for discovered_url in discovered_urls:
                        try:
                            parsed = urlparse(discovered_url)
                            if parsed.scheme and parsed.netloc:  # Valid URL
                                normalized_url = normalize_url_for_storage(discovered_url)
                                # Only process if this URL wasn't already handled by httpx
                                if not any(normalize_url_for_comparison(url.url) == normalize_url_for_comparison(normalized_url) for url in urls):
                                    # Only get links if this specific URL has an entry in the links dictionary
                                    url_links = links_dict.get(normalized_url, [])
                                    url_obj = Url(
                                        url=normalized_url,
                                        hostname=parsed.netloc.split(':')[0].lower(),
                                        port=int(parsed.port) if parsed.port else (443 if parsed.scheme == 'https' else 80),
                                        scheme=parsed.scheme.lower(),
                                        path=parsed.path or '/',
                                        method="GET",
                                        http_status_code=0,
                                        lines=0,
                                        words=0,
                                        content_length=0,
                                        extracted_links=url_links
                                    )
                                    urls.append(url_obj)
                        except Exception as e:
                            logger.warning(f"Failed to parse URL {discovered_url}: {e}")
            
            # Deduplicate URLs
            urls = self._filter_duplicate_urls(urls)
        
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing worker output as JSON: {e}")
            # Detailed error logging
            if len(output) > 100:
                logger.error(f"Output sample (first 100 chars): {repr(output[:100])}")
                logger.error(f"Output sample (last 100 chars): {repr(output[-100:])}")
            else:
                logger.error(f"Full output: {repr(output)}")
        except Exception as e:
            logger.error(f"Error processing output: {str(e)}")
            
        logger.info(f"Found {len(urls)} unique URLs")
        return {AssetType.URL: urls}
    
    def _process_entry(self, item: Dict, urls: List, links: List = []):
        """Process a single entry and update the collections"""        
        # Ensure URL is lowercase
        url = item.get("url", "").lower()
        item.get("host", "").lower()
        scheme = item.get("scheme", "").lower()
        
        # Normalize the URL for consistent storage
        normalized_url = normalize_url_for_storage(url)
        if not normalized_url:
            logger.warning(f"Failed to normalize URL: {url}")
            return
        
        urlObj = Url(
            url=normalized_url,
            hostname=urlparse(url).netloc.split(":")[0],
            ips=item.get("a", []),
            port=int(item.get("port", 0)),
            scheme=scheme,
            technologies=item.get("tech", []),
            path=item.get("path", ""),
            method=item.get("method", ""),
            http_status_code=item.get("status_code", 0),
            chain_status_codes=item.get("chain_status_codes", []),
            final_url=item.get("final_url", ""),
            response_time=int(item.get("time", "0ms").replace("ms", "").split(".")[0]),
            lines=item.get("lines", 0),
            title=item.get("title", ""),
            words=item.get("words", 0),
            body_preview=item.get("body_preview", ""),
            resp_body_hash=item.get("hash", {}).get("body_sha256", ""),
            favicon_hash=item.get("favicon", ""),
            favicon_url=item.get("favicon_url", ""),
            content_type=item.get("content_type", ""),
            content_length=item.get("content_length", 0),
            extracted_links=links  # Use the passed links directly
        )
        urls.append(urlObj)
        # If there is a final url, add it to the urls list
        redirect_chain = []
        for redirect in item.get("chain", []):
            request_url = redirect.get("request-url")
            if request_url:
                parsed_redirect = parse_url(request_url)
                if parsed_redirect:
                    redirect_chain.append({
                        "index": len(redirect_chain),
                        "method": redirect.get("request", "GET / HTTP/1.1").split(" ")[0],
                        "url": parsed_redirect.get('url'),
                        "http_status_code": redirect.get("status_code"),
                        "location": redirect.get("location", None)
                    })
                    
                    # Use centralized DNS resolution with error handling
                    hostname = parsed_redirect.get('hostname')
                    ips = self._resolve_dns_safely(hostname) if hostname else []
                    
                    redirect_url = Url(
                        url=parsed_redirect.get('url', ''),
                        hostname=parsed_redirect.get('hostname', ''),
                        port=parsed_redirect.get('port', 0),
                        http_status_code=redirect.get("status_code", 0),
                        scheme=parsed_redirect.get('scheme', ''),
                        path=parsed_redirect.get('path', ''),
                        ips=ips,
                        extracted_links=[]  # Redirect URLs don't have their own links
                    )
                    urls.append(redirect_url)
        if len(redirect_chain) > 0:
            urlObj.redirect_chain = redirect_chain
        if item.get("final_url"):
            final_url_str = item.get("final_url")
            if final_url_str:
                parsed_final_url = parse_url(final_url_str)
                if parsed_final_url:
                    logger.info(f"Parsed final url: {parsed_final_url}")
                    
                    # Use centralized DNS resolution with error handling
                    hostname = parsed_final_url.get('hostname')
                    ips = self._resolve_dns_safely(hostname) if hostname else []
                    
                    final_url = Url(
                        url=parsed_final_url.get('url', ''),
                        hostname=parsed_final_url.get('hostname', ''),
                        port=parsed_final_url.get('port', 0),
                        scheme=parsed_final_url.get('scheme', ''),
                        path=parsed_final_url.get('path', ''),
                        ips=ips,
                        extracted_links=[]  # Final URL doesn't have its own links
                    )
                    urls.append(final_url)
        
        logger.debug(f"Finished processing entry. Total urls: {len(urls)}")
    
    def _is_ip_address(self, host: str) -> bool:
        """Check if a host string is an IP address."""
        if not host:
            return False

        try:
            # Try to split the host into octets
            parts = host.split('.')
            if len(parts) != 4:
                return False
            # Check if all parts are valid numbers between 0 and 255
            return all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False

    # ============================================================================
    # PROXY SUPPORT METHODS - Enable AWS API Gateway proxying via FireProx
    # ============================================================================

    def supports_proxy(self) -> bool:
        """
        CrawlWebsite supports AWS API Gateway proxying via FireProx for URL targets.

        Returns:
            bool: True (this task supports proxying)
        """
        return True

    def extract_proxy_targets(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """
        Extract URLs that need proxying from input data.

        For crawl_website, only URL inputs should be proxied.

        Args:
            input_data: Task input data (list of URLs or single URL)
            params: Task parameters

        Returns:
            List of URLs to create proxies for
        """
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]

        # Get valid URLs (filter out domains and IPs)
        urls_to_proxy = get_valid_urls(targets_to_process)

        # Remove trailing slashes for consistency
        urls_to_proxy = [url.rstrip('/') for url in urls_to_proxy]

        logger.info(f"Extracted {len(urls_to_proxy)} URLs for proxying (filtered from {len(targets_to_process)} total targets)")
        return urls_to_proxy

    def replace_targets_with_proxies(self, command: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace original URLs with proxy URLs in crawl_website commands.

        Crawl_website uses heredoc format:
        cat << 'EOF' | python3 crawl_website.py
        url1
        url2
        EOF

        We need to replace URLs in the heredoc content.

        Args:
            command: Original crawl_website command string
            url_mapping: Dict mapping original URLs to proxy URLs

        Returns:
            Modified command with proxied URLs
        """
        # Extract the heredoc content (between first newline and EOF)
        parts = command.split('\n', 1)
        if len(parts) < 2:
            logger.warning("Command does not contain heredoc format, skipping proxy replacement")
            return command

        header = parts[0]  # cat << 'EOF' | python3 crawl_website.py
        remaining = parts[1]

        # Split remaining into targets and EOF
        content_parts = remaining.rsplit('\nEOF', 1)
        if len(content_parts) < 2:
            logger.warning("Command does not contain EOF marker, skipping proxy replacement")
            return command

        targets_text = content_parts[0]
        eof_part = '\nEOF' + content_parts[1]

        # Replace URLs in targets
        modified_targets = targets_text
        for original_url, proxy_url in url_mapping.items():
            original_normalized = original_url.rstrip('/')
            proxy_normalized = proxy_url.rstrip('/')

            # Try replacing with full URL (with port)
            replaced = False

            # Try exact match first
            if original_normalized + '\n' in modified_targets:
                modified_targets = modified_targets.replace(
                    original_normalized + '\n',
                    proxy_normalized + '\n'
                )
                replaced = True
            elif modified_targets.endswith(original_normalized):
                modified_targets = modified_targets[:-len(original_normalized)] + proxy_normalized
                replaced = True

            # If not replaced and URL has explicit port, try without port
            if not replaced and ':' in original_normalized:
                # Extract URL without port (e.g., https://www.somewebsite.com:443 -> https://www.somewebsite.com)
                from urllib.parse import urlunparse
                parsed = urlparse(original_normalized)
                url_without_port = urlunparse((
                    parsed.scheme,
                    parsed.hostname,  # hostname property excludes port
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))

                # Try replacing without port
                if url_without_port + '\n' in modified_targets:
                    modified_targets = modified_targets.replace(
                        url_without_port + '\n',
                        proxy_normalized + '\n'
                    )
                    replaced = True
                elif modified_targets.endswith(url_without_port):
                    modified_targets = modified_targets[:-len(url_without_port)] + proxy_normalized
                    replaced = True

            if replaced:
                logger.debug(f"Replaced {original_normalized} with {proxy_normalized}")
            else:
                logger.warning(f"Could not find {original_normalized} or variant in command to replace")

        reconstructed_command = header + '\n' + modified_targets + eof_part
        logger.debug("Replaced URLs in crawl_website command (heredoc format)")
        return reconstructed_command

    def replace_proxies_in_output(self, output: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace proxy URLs back to original URLs in crawl_website output using hostname-based replacement.

        This function:
        1. Replaces proxy hostnames with original hostnames
        2. Removes the /fireprox path prefix from all URLs

        Args:
            output: Raw crawl_website output (JSON)
            url_mapping: Dict mapping original URLs to proxy URLs

        Returns:
            Modified output with original URLs restored and /fireprox prefix removed
        """
        if not output or not url_mapping:
            return output

        modified_output = output

        # For each mapping, replace proxy hostname with original hostname
        for original_url, proxy_url in url_mapping.items():
            # Extract hostnames from URLs (without port)
            proxy_parsed = urlparse(proxy_url)
            original_parsed = urlparse(original_url)

            proxy_hostname = proxy_parsed.netloc.split(':')[0]
            original_hostname = original_parsed.netloc.split(':')[0]

            # Replace all occurrences of proxy hostname with original hostname
            # Use word boundaries to avoid partial matches
            modified_output = re.sub(
                r'\b' + re.escape(proxy_hostname) + r'\b',
                original_hostname,
                modified_output
            )

            logger.debug(f"Replaced proxy hostname {proxy_hostname} with {original_hostname}")

        # Remove /fireprox path prefix from all URLs and paths
        # This handles both: "url": "https://host/fireprox/path" and "path": "/fireprox/path"
        modified_output = re.sub(r'/fireprox(/|")', r'\1', modified_output)

        logger.debug(f"Replaced proxy URLs in crawl_website output: {len(modified_output)} chars")
        return modified_output 