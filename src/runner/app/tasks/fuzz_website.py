import json
import logging
import os
import re
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
from .base import Task, AssetType, FindingType
from models.assets import Url
from models.findings import TyposquatURL
from utils import get_valid_urls

logger = logging.getLogger(__name__)

class FuzzWebsite(Task):
    name = "fuzz_website"
    description = "Fuzz website paths using ffuf"
    input_type = AssetType.STRING
    output_types = [AssetType.URL]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate unique hash for task execution tracking"""
        import base64
        wordlist = params.get("wordlist", "/workspace/files/webcontent_test.txt") if params else "/workspace/files/webcontent_test.txt"
        
        # For database wordlists, use the ID for caching (not the converted URL)
        # This ensures the same wordlist ID always has the same hash
        hash_dict = {
            "task": self.name,
            "target": target,
            "wordlist": wordlist  # Keep original wordlist parameter for consistent hashing
        }
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """Generate the ffuf command for website fuzzing"""
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]
        
        # Filter valid URLs
        urls_to_process = get_valid_urls(targets_to_process)
        if not urls_to_process:
            logger.warning("No valid URLs found in input data")
            return ""
        
        # Get wordlist from params or use default
        wordlist = params.get("wordlist", "/workspace/files/webcontent_test.txt") if params else "/workspace/files/webcontent_test.txt"
        
        # Check if wordlist is a database wordlist ID (UUID format)
        import re
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        original_wordlist = wordlist
        
        if uuid_pattern.match(wordlist):
            # Convert wordlist ID to API download URL
            api_url = os.getenv("API_URL", "http://api:8000")
            wordlist = f"{api_url}/wordlists/{wordlist}/download"
            logger.info(f"Converted wordlist ID '{original_wordlist}' to API URL: {wordlist}")
        elif wordlist.startswith('http'):
            logger.info(f"Using remote wordlist URL: {wordlist}")
        elif wordlist.startswith('/'):
            logger.info(f"Using local wordlist file: {wordlist}")
        else:
            # If it's not a UUID, not a URL, and not an absolute path, assume it's a filename
            # and use the default wordlist
            logger.warning(f"Invalid wordlist format '{original_wordlist}', using default")
            wordlist = "/workspace/files/webcontent_test.txt"
        
        # Prepare URLs for ffuf processing
        commands = []
        # Build ffuf command - we need to process one URL at a time
        # since ffuf expects a single base URL with FUZZ placeholder
        for url in urls_to_process:
            if url.endswith('/'):
                url = url[:-1]
            # parse url to get hostname value
            hostname = urlparse(url).hostname
            command = (
                f"python ffuf_wrapper.py "
                f"-u {url}/FUZZ "
                f"-w {wordlist} "
                f"-s "  # Silent mode
                f"-json "  # JSON output
                f"-mc 200,204,301,302,307,401,405 "  # Match status codes
                f"-t 50 "  # Threads
                "-ac "
                f"-H 'Host: {hostname}' "
                f"-timeout 10 "  # Timeout per request
                )
            commands.append(command)

        # Return array of commands to spawn separate worker jobs for each URL
        if commands:
            logger.debug(f"Generated {len(commands)} ffuf commands for separate worker jobs")
            return commands
        else:
            logger.warning("No valid URLs found for fuzzing")
            return []
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse ffuf output into URL assets"""
        urls = []

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        if not normalized_output:
            logger.warning("Empty output received from ffuf")
            return {AssetType.URL: []}

        logger.info(f"Processing ffuf output: {len(normalized_output)} characters")
        
        try:
            # Handle multiple JSON objects per line
            if isinstance(normalized_output, str) and '\n' in normalized_output:
                logger.info("Processing multi-line JSON text")
                for line in normalized_output.strip().split('\n'):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        self._process_ffuf_entry(item, urls)
                    except json.JSONDecodeError as e:
                        logger.error(f"Error processing line: {str(e)}")
                        logger.error(f"Problematic line: {line}")
            # Handle single JSON object
            elif isinstance(normalized_output, str):
                logger.info("Processing single JSON text")
                item = json.loads(normalized_output)
                if isinstance(item, dict):
                    self._process_ffuf_entry(item, urls)
                elif isinstance(item, list):
                    for entry in item:
                        self._process_ffuf_entry(entry, urls)
                        
        except json.JSONDecodeError as e:
            logger.error(f"Error processing output as JSON: {str(e)}")
            logger.error(f"Raw output: {normalized_output}")
            
        logger.info(f"Found {len(urls)} URLs from fuzzing")
        return {AssetType.URL: urls}
    
    def _process_ffuf_entry(self, item: Dict, urls: List[Url]):
        """Process a single ffuf entry and create URL asset"""
        try:
            # Extract data from ffuf output
            url = item.get("url", "")
            status_code = item.get("status", 0)
            content_length = item.get("length", 0)
            content_type = item.get("content-type", "")
            redirect_location = item.get("redirectlocation", "")
            words = item.get("words")
            lines = item.get("lines")

            if not url:
                logger.warning("No URL found in ffuf entry")
                return

            # Parse the URL to extract components
            parsed = urlparse(url)
            logger.debug(f"Parsed URL: {parsed}")
            hostname = parsed.netloc.split(":")[0] if parsed.netloc else ""
            logger.debug(f"Hostname: {hostname}")
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            scheme = parsed.scheme or "http"
            path = parsed.path or "/"

            # Create URL asset
            url_obj = Url(
                url=url,
                hostname=hostname,
                port=port,
                scheme=scheme,
                path=path,
                http_status_code=status_code,
                content_type=content_type,
                content_length=content_length,
                words=words,
                lines=lines,
                final_url=redirect_location if redirect_location else url
            )
            logger.debug(f"Created URL asset: {url_obj}")
            urls.append(url_obj)
            logger.debug(f"Created URL asset: {url}")

        except Exception as e:
            logger.error(f"Error processing ffuf entry: {str(e)}")
            logger.error(f"Entry data: {item}")

    def transform_to_findings(self, assets: Dict[AssetType, List[Any]], context: Dict[str, Any]) -> Dict[Any, List[Any]]:
        """
        Transform URL assets to TyposquatURL findings for typosquat detection workflow.

        This implements the dual-purpose task pattern where the same task can produce
        either assets (normal mode) or findings (typosquat mode).

        Args:
            assets: Parsed URL assets from parse_output()
            context: Typosquat context containing:
                - typo_domain: The typosquat domain being analyzed
                - risk_factors: Risk analysis data
                - fuzzer_wordlist: Wordlist used for fuzzing
                - program_name: Program name for the finding

        Returns:
            Dict mapping FindingType.TYPOSQUAT_URL to list of TyposquatURL findings
        """
        urls = assets.get(AssetType.URL, [])
        if not urls:
            logger.info("No URLs to transform to findings")
            return {}

        # Extract context
        typo_domain = context.get('typo_domain', '')
        risk_factors = context.get('risk_factors', {})
        fuzzer_wordlist = context.get('fuzzer_wordlist', 'unknown')
        program_name = context.get('program_name', '')

        # If typo_domain is not provided, infer it from the first URL's hostname
        # This handles cases where fuzz_website is used standalone without typosquat context
        if not typo_domain and urls:
            typo_domain = urls[0].hostname
            logger.info(f"No typo_domain in context, using hostname from first URL: {typo_domain}")

        logger.info(f"Transforming {len(urls)} URL assets to TyposquatURL findings")
        logger.info(f"Context: typo={typo_domain}, wordlist={fuzzer_wordlist}")

        findings = []
        for url_asset in urls:
            try:
                # Calculate risk score based on URL characteristics
                risk_score = self._calculate_url_risk_score(url_asset, risk_factors)

                # Create TyposquatURL finding
                finding = TyposquatURL(
                    url=url_asset.url,
                    typo_domain=typo_domain,
                    hostname=url_asset.hostname,
                    port=url_asset.port,
                    scheme=url_asset.scheme,
                    path=url_asset.path,
                    http_status_code=url_asset.http_status_code,
                    content_length=url_asset.content_length,
                    content_type=url_asset.content_type,
                    line_count=url_asset.lines,
                    word_count=url_asset.words,
                    title=getattr(url_asset, 'title', None),
                    technologies=getattr(url_asset, 'technologies', []),
                    final_url=url_asset.final_url,
                    discovered_via='fuzzing',
                    fuzzer_wordlist=fuzzer_wordlist,
                    risk_score=risk_score,
                    risk_factors=self._extract_url_risk_factors(url_asset, risk_factors),
                    program_name=program_name
                )

                findings.append(finding)
                logger.debug(f"Created TyposquatURL finding: {finding.url} (risk={risk_score})")

            except Exception as e:
                logger.error(f"Error transforming URL asset to finding: {e}")
                logger.error(f"URL asset: {url_asset}")

        logger.info(f"Successfully transformed {len(findings)} URLs to TyposquatURL findings")
        return {FindingType.TYPOSQUAT_URL: findings}

    def _calculate_url_risk_score(self, url_asset: Url, risk_factors: Dict[str, Any]) -> int:
        """
        Calculate risk score for a typosquat URL based on its characteristics.

        Args:
            url_asset: URL asset to analyze
            risk_factors: Additional risk factors from domain analysis

        Returns:
            Risk score from 0-100
        """
        score = 0

        # Base score from domain risk if available
        domain_risk = risk_factors.get('total_score', 0)
        score += min(domain_risk // 2, 30)  # Up to 30 points from domain risk

        # HTTP status code scoring
        if url_asset.http_status_code:
            if url_asset.http_status_code == 200:
                score += 20  # Active content is high risk
            elif url_asset.http_status_code in [301, 302, 307]:
                score += 15  # Redirects are medium-high risk
            elif url_asset.http_status_code == 401:
                score += 25  # Auth pages are very high risk (possible phishing)
            elif url_asset.http_status_code == 403:
                score += 10  # Forbidden but exists

        # Path-based scoring (login, admin paths are higher risk)
        path_lower = url_asset.path.lower() if url_asset.path else ''
        high_risk_paths = ['login', 'signin', 'admin', 'account', 'auth', 'password', 'secure']
        if any(keyword in path_lower for keyword in high_risk_paths):
            score += 20

        # Content type scoring
        if url_asset.content_type:
            if 'html' in url_asset.content_type.lower():
                score += 10  # HTML pages are more interesting

        # Cap at 100
        return min(score, 100)

    def _extract_url_risk_factors(self, url_asset: Url, domain_risk_factors: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract specific risk factors for a URL.

        Args:
            url_asset: URL asset to analyze
            domain_risk_factors: Risk factors from domain analysis

        Returns:
            Dict of risk factors specific to this URL
        """
        factors = {
            'has_active_content': url_asset.http_status_code == 200 if url_asset.http_status_code else False,
            'is_redirect': url_asset.http_status_code in [301, 302, 307] if url_asset.http_status_code else False,
            'requires_auth': url_asset.http_status_code == 401 if url_asset.http_status_code else False,
            'is_html_page': 'html' in (url_asset.content_type or '').lower(),
        }

        # Check for suspicious paths
        path_lower = url_asset.path.lower() if url_asset.path else ''
        factors['has_login_path'] = any(kw in path_lower for kw in ['login', 'signin', 'auth'])
        factors['has_admin_path'] = any(kw in path_lower for kw in ['admin', 'administrator'])
        factors['has_account_path'] = any(kw in path_lower for kw in ['account', 'profile', 'user'])

        # Inherit domain-level risk factors
        if domain_risk_factors:
            factors['domain_registered'] = domain_risk_factors.get('domain_registered', False)
            factors['domain_risk_level'] = domain_risk_factors.get('risk_level', 'unknown')

        return factors

    # ============================================================================
    # PROXY SUPPORT METHODS - Enable AWS API Gateway proxying via FireProx
    # ============================================================================

    def supports_proxy(self) -> bool:
        """
        FuzzWebsite supports AWS API Gateway proxying via FireProx.

        Returns:
            bool: True (this task supports proxying)
        """
        return True

    def extract_proxy_targets(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """
        Extract URLs that need proxying from input data.

        For fuzz_website, we extract the base URLs that will be fuzzed.

        Args:
            input_data: Task input data (list of URLs or single URL)
            params: Task parameters

        Returns:
            List of base URLs to create proxies for
        """
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]

        # Filter valid URLs
        urls_to_proxy = get_valid_urls(targets_to_process)

        # Remove trailing slashes for consistency
        urls_to_proxy = [url.rstrip('/') for url in urls_to_proxy]

        logger.info(f"Extracted {len(urls_to_proxy)} URLs for proxying: {urls_to_proxy}")
        return urls_to_proxy

    def replace_targets_with_proxies(self, command: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace original URLs with proxy URLs in ffuf commands.

        For fuzz_website, we need to replace the base URL in ffuf commands like:
        -u https://target.com/FUZZ -> -u https://xxx.execute-api.region.amazonaws.com/fireprox/FUZZ

        Args:
            command: Original ffuf command string
            url_mapping: Dict mapping original URLs to proxy URLs

        Returns:
            Modified command with proxied URLs
        """
        modified_command = command

        for original_url, proxy_url in url_mapping.items():
            # Normalize URLs for replacement (remove trailing slashes)
            original_normalized = original_url.rstrip('/')
            proxy_normalized = proxy_url.rstrip('/')

            # Replace in command string
            # ffuf commands use format: -u https://target.com/FUZZ
            modified_command = modified_command.replace(
                f"{original_normalized}/FUZZ",
                f"{proxy_normalized}/FUZZ"
            )

            # Also replace any other occurrences
            modified_command = modified_command.replace(original_normalized, proxy_normalized)

        logger.debug(f"Replaced URLs in command: {modified_command[:200]}...")
        return modified_command

    def replace_proxies_in_output(self, output: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace proxy URLs back to original URLs in ffuf output using hostname-based replacement.

        This function:
        1. Replaces proxy hostnames with original hostnames
        2. Removes the /fireprox path prefix from all URLs

        Args:
            output: Raw ffuf output (JSON lines)
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
        # This handles both: "url": "https://host/fireprox/path" and "final_url": "https://host:443/fireprox/path"
        modified_output = re.sub(r'/fireprox(/|")', r'\1', modified_output)

        logger.debug(f"Replaced proxy URLs in ffuf output: {len(modified_output)} chars")
        return modified_output
