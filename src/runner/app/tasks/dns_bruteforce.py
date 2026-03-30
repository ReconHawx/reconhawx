import ipaddress
import json
import logging
import os
import re
import random
import string
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
import base64
import requests

from .base import Task, AssetType, FindingType, CommandSpec
from models.assets import Domain, Ip
from models.findings import TyposquatDomain

logger = logging.getLogger(__name__)

# DNS record type codes for wildcard detection
RECORD_TYPE_CODES = {
    "A": 1,
    "AAAA": 28,
    "TXT": 16,
    "NS": 2,
    "CNAME": 5,
    "MX": 15
}
DNS_API_URL = "https://cloudflare-dns.com/dns-query"


class DnsBruteforce(Task):
    """
    Orchestrator task that performs DNS bruteforcing using PureDNS
    to discover subdomains from a wordlist.
    
    Workflow:
    1. Receives input domains (e.g., ["example.com", "target.com"])
    2. Checks if domains are wildcards (skips wildcards)
    3. Downloads/resolves wordlist
    4. Spawns puredns worker jobs for each non-wildcard domain
    5. Aggregates and returns discovered subdomains and IPs
    
    Task parameters:
    - wordlist (str): Wordlist ID, URL, or file path for bruteforcing
    - chunk_size (int): Number of domains per worker job (default: 10)
    - batch_size (int): Number of jobs to spawn per batch (default: 5)
    - timeout (int): Timeout per job in seconds (default: 600)
    
    Output modes:
    - Default: Produces subdomain and IP assets
    - typosquat_findings: Produces TyposquatDomain findings (for typosquat workflows)
    """
    
    name = "dns_bruteforce"
    description = "Bruteforce subdomains using PureDNS with wordlist"
    input_type = AssetType.STRING
    output_types = [AssetType.SUBDOMAIN, AssetType.IP]

    def __init__(self):
        super().__init__()

        # Configuration for job management
        self.chunk_size = int(os.getenv('DNS_BRUTEFORCE_CHUNK_SIZE', '10'))
        self.batch_size = int(os.getenv('DNS_BRUTEFORCE_BATCH_SIZE', '5'))
        self.job_timeout = int(os.getenv('DNS_BRUTEFORCE_JOB_TIMEOUT', '600'))
        self.total_timeout = int(os.getenv('DNS_BRUTEFORCE_TOTAL_TIMEOUT', '3600'))
        
        # Default wordlist
        self.default_wordlist = os.getenv('DNS_BRUTEFORCE_WORDLIST', '/workspace/files/subdomains.txt')

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate hash for caching based on target and wordlist."""
        wordlist = params.get("wordlist", self.default_wordlist) if params else self.default_wordlist
        hash_dict = {
            "task": self.name,
            "target": target,
            "wordlist": wordlist
        }
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()

    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """
        Generate the puredns command for a single domain.
        
        This method is not used for orchestrator tasks - return empty.
        Orchestrator tasks spawn worker jobs instead of executing commands directly.
        """
        return ""

    def _resolve_wordlist_path(self, wordlist: str) -> str:
        """
        Resolve wordlist parameter to actual file path or URL.
        Handles database wordlist IDs, URLs, and local file paths.
        
        Args:
            wordlist: Wordlist identifier (UUID, URL, or file path)
            
        Returns:
            Resolved wordlist path or URL
        """
        # Check if it's a database wordlist ID (UUID format)
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        
        if uuid_pattern.match(wordlist):
            # Convert wordlist ID to API download URL
            api_url = os.getenv("API_URL", "http://api:8000")
            download_url = f"{api_url}/wordlists/{wordlist}/download"
            logger.info(f"Converted wordlist ID '{wordlist}' to API URL: {download_url}")
            return download_url
        elif wordlist.startswith('http'):
            logger.info(f"Using remote wordlist URL: {wordlist}")
            return wordlist
        elif wordlist.startswith('/'):
            logger.info(f"Using absolute path wordlist: {wordlist}")
            return wordlist
        else:
            # Relative path - assume it's relative to workspace
            logger.info(f"Using relative path wordlist: {wordlist}")
            return wordlist

    def _check_wildcard_via_api(self, domain: str, program_name: str) -> tuple:
        """
        Check if a domain is a wildcard by querying the API.
        
        Args:
            domain: Domain to check
            program_name: Program name for API query
            
        Returns:
            Tuple of (is_wildcard, found_in_api)
            - is_wildcard: True if domain is a wildcard, False otherwise
            - found_in_api: True if domain was found in API, False otherwise
        """
        api_url = os.getenv('API_URL', 'http://api:8000')
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
        
        if not api_url or not internal_api_key:
            logger.warning("API configuration not available")
            return False, False
        
        search_url = f"{api_url.rstrip('/')}/assets/subdomain/search"
        headers = {
            'Authorization': f'Bearer {internal_api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            request_data = {
                "exact_match": domain.strip().lower(),
                "program": program_name,
                "page": 1,
                "page_size": 1
            }
            
            response = requests.post(
                search_url,
                json=request_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                items = result.get("items", [])
                
                if items:
                    domain_data = items[0]
                    is_wildcard = domain_data.get("is_wildcard", False)
                    logger.debug(f"Domain {domain} found in API: is_wildcard={is_wildcard}")
                    return is_wildcard, True
                else:
                    logger.debug(f"Domain {domain} not found in API")
                    return False, False
            else:
                logger.debug(f"API error for {domain}")
                return False, False
                
        except Exception as e:
            logger.debug(f"Error checking API for {domain}: {e}")
            return False, False

    async def _query_dns_records(self, session: aiohttp.ClientSession, subdomain: str, record_type: str) -> tuple:
        """
        Query DNS records for a subdomain using Cloudflare DNS-over-HTTPS.
        
        Args:
            session: aiohttp session
            subdomain: Subdomain to query
            record_type: DNS record type (A, AAAA, etc.)
            
        Returns:
            Tuple of (has_answer, answers, actual_record_type)
        """
        try:
            async with session.get(
                DNS_API_URL, 
                params={'name': subdomain, 'type': record_type}, 
                headers={'Accept': 'application/dns-json'},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    # Use content_type=None to accept application/dns-json from Cloudflare
                    result = await response.json(content_type=None)
                    has_answer = "Answer" in result
                    answers = result.get("Answer", []) if has_answer else []
                    
                    if answers:
                        first_answer_type = answers[0].get("type")
                        first_record_type = next(
                            (rtype for rtype, code in RECORD_TYPE_CODES.items()
                             if code == first_answer_type), None
                        )
                        return bool(answers), answers, first_record_type
                    
                    return bool(answers), answers, None
                else:
                    return False, [], None
        except Exception as e:
            logger.debug(f"Error querying DNS for {subdomain}: {e}")
            return False, [], None

    def _infer_wildcard_subnets(self, ips: List[str]) -> List[str]:
        """
        Infer /24 wildcard subnets from a list of sampled IPs.
        Any /24 that contains at least 2 IPs from the sample is returned,
        so the worker can filter entire subnets (e.g. whole wildcard pools).
        """
        if len(ips) < 2:
            return []
        networks_to_count: Dict[Any, int] = {}
        for ip_str in ips:
            try:
                addr = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if addr.version != 4:
                continue
            net = ipaddress.ip_network(f"{ip_str}/24", strict=False)
            networks_to_count[net] = networks_to_count.get(net, 0) + 1
        return [str(net) for net, count in networks_to_count.items() if count >= 2]

    async def _check_wildcard_dns(self, domain: str) -> dict:
        """
        Check if a domain is a wildcard by testing random subdomain resolution.
        
        This is the actual wildcard detection - if random subdomains resolve,
        the domain has wildcard DNS configured. Performs multiple probes and
        multiple A-record queries per probe to collect all possible wildcard IPs
        (e.g. round-robin or multiple A records), so the worker can filter them.
        
        Args:
            domain: Domain to check
            
        Returns:
            Dict with keys:
            - is_wildcard (bool): True if domain is a wildcard
            - wildcard_ips (list): List of IPs that random subdomains resolve to
            - wildcard_cname (str): CNAME that random subdomains resolve to (if any)
        """
        logger.info(f"🔬 Testing wildcard status for {domain} via DNS...")
        
        # Env-based tuning: probe count and queries per probe to discover all wildcard IPs
        probe_count = int(os.getenv('DNS_WILDCARD_PROBE_COUNT', '10'))
        probe_count = max(5, min(30, probe_count))
        queries_per_probe = int(os.getenv('DNS_WILDCARD_QUERIES_PER_PROBE', '3'))
        queries_per_probe = max(1, min(10, queries_per_probe))
        query_delay = float(os.getenv('DNS_WILDCARD_QUERY_DELAY', '0.1'))
        use_delay = query_delay > 0
        
        result = {
            'is_wildcard': False,
            'wildcard_ips': [],
            'wildcard_subnets': [],
            'wildcard_cname': ''
        }
        
        wildcard_ips = set()
        wildcard_cname = None
        
        async with aiohttp.ClientSession() as session:
            # Generate random subdomain labels for testing (more probes = better IP coverage)
            test_labels = [
                ''.join(random.choices(string.ascii_lowercase, k=12)) for _ in range(probe_count)
            ]
            
            # Test A records: multiple probes, multiple queries per probe (catches round-robin)
            for test_label in test_labels:
                test_subdomain = f"{test_label}.{domain}"
                
                for q in range(queries_per_probe):
                    has_records, answers, _ = await self._query_dns_records(session, test_subdomain, "A")
                    
                    if has_records and answers:
                        for answer in answers:
                            ip = answer.get('data', '')
                            if ip:
                                wildcard_ips.add(ip)
                        
                        if not result['is_wildcard']:
                            logger.info(f"⚠️ Domain {domain} is WILDCARD - random subdomain {test_subdomain} resolved to {answers[0].get('data', 'unknown')}")
                            result['is_wildcard'] = True
                    
                    # Small delay between repeated queries (same subdomain) to encourage round-robin variety
                    if use_delay and q < queries_per_probe - 1:
                        await asyncio.sleep(query_delay)
            
            # Also test CNAME records (single probe, one query)
            test_label = ''.join(random.choices(string.ascii_lowercase, k=12))
            test_subdomain = f"{test_label}.{domain}"
            
            has_records, answers, actual_type = await self._query_dns_records(session, test_subdomain, "CNAME")
            
            if has_records and answers and actual_type == "CNAME":
                wildcard_cname = answers[0].get('data', '')
                if not result['is_wildcard']:
                    logger.info(f"⚠️ Domain {domain} is WILDCARD (CNAME) - random subdomain {test_subdomain} resolved to {wildcard_cname}")
                    result['is_wildcard'] = True
        
        if result['is_wildcard']:
            result['wildcard_ips'] = list(wildcard_ips)
            result['wildcard_subnets'] = self._infer_wildcard_subnets(result['wildcard_ips'])
            result['wildcard_cname'] = wildcard_cname or ''
            total_queries = probe_count * queries_per_probe
            logger.info(f"📋 Wildcard IPs for {domain}: {result['wildcard_ips']} (from {probe_count} probes, {total_queries} A queries)")
            if result['wildcard_subnets']:
                logger.info(f"📋 Wildcard subnets for {domain}: {result['wildcard_subnets']}")
            if result['wildcard_cname']:
                logger.info(f"📋 Wildcard CNAME for {domain}: {result['wildcard_cname']}")
        else:
            logger.info(f"✅ Domain {domain} is NOT a wildcard")
        
        return result

    async def _resolve_domain_ips(self, domain: str) -> List[str]:
        """
        Resolve the actual A record IPs for a domain.
        
        This is separate from wildcard detection - it gets the real IPs
        for the domain itself, not random subdomain wildcard IPs.
        
        Args:
            domain: Domain to resolve
            
        Returns:
            List of IP addresses for the domain
        """
        logger.debug(f"🔍 Resolving actual IPs for {domain}...")
        
        ips = []
        
        async with aiohttp.ClientSession() as session:
            # Query A records for the domain itself
            has_records, answers, _ = await self._query_dns_records(session, domain, "A")
            
            if has_records and answers:
                for answer in answers:
                    ip = answer.get('data', '')
                    if ip and ip not in ips:
                        ips.append(ip)
                
                logger.debug(f"✅ Resolved {domain} to IPs: {ips}")
            else:
                logger.debug(f"⚠️ No A records found for {domain}")
        
        return ips

    async def _detect_wildcard_info(self, domains: List[str], program_name: str) -> Dict[str, dict]:
        """
        Detect wildcard information for each domain.
        
        First checks the API for known wildcard status. If not found in API,
        performs actual DNS wildcard detection by testing random subdomains.
        
        Args:
            domains: List of domain names to check
            program_name: Program name for API query
            
        Returns:
            Dict mapping domain to wildcard info:
            {
                "example.com": {
                    "is_wildcard": True,
                    "wildcard_ips": ["1.2.3.4"],
                    "wildcard_cname": ""
                }
            }
        """
        wildcard_info = {}
        
        for domain in domains:
            try:
                # First check API for cached wildcard status
                is_wildcard, found_in_api = self._check_wildcard_via_api(domain, program_name)
                
                if found_in_api and is_wildcard:
                    # Domain found in API and marked as wildcard - but we need IPs
                    # Fall through to DNS check to get wildcard IPs
                    logger.info(f"⚠️ Domain {domain} marked as wildcard in API, detecting wildcard IPs...")
                    wildcard_result = await self._check_wildcard_dns(domain)
                    wildcard_info[domain] = wildcard_result
                elif found_in_api and not is_wildcard:
                    # Domain found in API and not wildcard
                    logger.debug(f"✅ Non-wildcard domain (from API): {domain}")
                    wildcard_info[domain] = {
                        'is_wildcard': False,
                        'wildcard_ips': [],
                        'wildcard_subnets': [],
                        'wildcard_cname': ''
                    }
                else:
                    # Domain not found in API - test wildcard via DNS
                    logger.info(f"🔍 Domain {domain} not in API, testing wildcard status via DNS...")
                    wildcard_result = await self._check_wildcard_dns(domain)
                    wildcard_info[domain] = wildcard_result
                        
            except Exception as e:
                logger.warning(f"Error checking wildcard for {domain}: {e}")
                # On error, perform DNS check as fallback
                try:
                    wildcard_result = await self._check_wildcard_dns(domain)
                    wildcard_info[domain] = wildcard_result
                except Exception as e2:
                    logger.error(f"Fallback DNS check also failed for {domain}: {e2}")
                    # Default to non-wildcard on error
                    wildcard_info[domain] = {
                        'is_wildcard': False,
                        'wildcard_ips': [],
                        'wildcard_subnets': [],
                        'wildcard_cname': ''
                    }
        
        # Log summary
        wildcards = [d for d, info in wildcard_info.items() if info['is_wildcard']]
        non_wildcards = [d for d, info in wildcard_info.items() if not info['is_wildcard']]
        
        if wildcards:
            logger.info(f"⚠️ Detected {len(wildcards)} wildcard domain(s): {', '.join(wildcards)}")
            for domain in wildcards:
                info = wildcard_info[domain]
                logger.info(f"   {domain}: IPs={info.get('wildcard_ips', [])}, subnets={info.get('wildcard_subnets', [])}, CNAME={info['wildcard_cname']}")
        if non_wildcards:
            logger.info(f"✅ {len(non_wildcards)} non-wildcard domain(s): {', '.join(non_wildcards)}")
        
        return wildcard_info

    async def generate_commands(
        self,
        input_data: List[Any],
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[CommandSpec]:
        """
        Generate puredns commands for each domain with wildcard detection.
        Stores wildcard_info in context for get_synthetic_assets.
        """
        if not input_data:
            return []

        domains_to_process = input_data if isinstance(input_data, list) else [input_data]
        logger.info(f"📋 Processing {len(domains_to_process)} input domains for DNS bruteforce")

        # Extract parameters
        wordlist = params.get('wordlist', self.default_wordlist)
        program_name = context.get('program_name', os.getenv('PROGRAM_NAME', 'default'))
        task_def = context.get('task_def')
        if task_def and hasattr(task_def, 'params') and task_def.params:
            wordlist = task_def.params.get('wordlist', wordlist)
            self.chunk_size = task_def.params.get('chunk_size', self.chunk_size)
            self.batch_size = task_def.params.get('batch_size', self.batch_size)
            self.job_timeout = task_def.params.get('timeout', self.job_timeout)

        output_mode = getattr(task_def, 'output_mode', None) if task_def else None
        logger.info(f"📋 Output mode: {output_mode or 'assets (default)'}")

        resolved_wordlist = self._resolve_wordlist_path(wordlist)

        # Detect wildcard information for all domains
        logger.info("🔍 Detecting wildcard information for domains...")
        wildcard_info = await self._detect_wildcard_info(domains_to_process, program_name)
        context['wildcard_info'] = wildcard_info
        context['output_mode'] = output_mode

        # Generate CommandSpec for each domain
        command_specs = []
        for domain in domains_to_process:
            info = wildcard_info.get(domain, {})
            wildcard_ips = info.get('wildcard_ips', [])
            wildcard_subnets = info.get('wildcard_subnets', [])

            command = f"python3 puredns_wrapper.py -d {domain} -w {resolved_wordlist}"
            if wildcard_ips:
                wildcard_ips_str = ','.join(wildcard_ips)
                command += f" --wildcard-ips {wildcard_ips_str}"
                logger.info(f"📋 Command for {domain} will filter wildcard IPs: {wildcard_ips_str}")
            if wildcard_subnets:
                wildcard_cidrs_str = ','.join(wildcard_subnets)
                command += f" --wildcard-cidrs {wildcard_cidrs_str}"
                logger.info(f"📋 Command for {domain} will filter wildcard CIDRs: {wildcard_cidrs_str}")

            command_specs.append(
                CommandSpec(task_name=self.name, command=command, params=params)
            )

        logger.info(f"📦 Generated {len(command_specs)} puredns commands")
        return command_specs

    async def get_synthetic_assets(
        self, context: Dict[str, Any]
    ) -> Optional[Dict[AssetType, List[Any]]]:
        """Create wildcard parent domain assets for domains with wildcard DNS."""
        wildcard_info = context.get('wildcard_info', {})
        output_mode = context.get('output_mode')
        if output_mode == 'typosquat_findings':
            logger.info("📊 Typosquat mode: skipping wildcard parent asset insertion")
            return None

        wildcard_parent_assets = []
        wildcard_parent_ips = set()  # Ip objects (ip + discovered_via_domain for API scope)

        for domain, info in wildcard_info.items():
            if not info.get('is_wildcard'):
                continue

            wildcard_ips = info.get('wildcard_ips', [])
            wildcard_cname = info.get('wildcard_cname', '')

            wildcard_types = []
            if wildcard_ips:
                wildcard_types.append('A')
            if wildcard_cname:
                wildcard_types.append('CNAME')

            actual_domain_ips = await self._resolve_domain_ips(domain)
            actual_domain_cname = None

            if actual_domain_ips:
                logger.info(f"📋 Root domain {domain} actual IPs: {actual_domain_ips}")
            else:
                logger.info(f"📋 Root domain {domain} has no A records (may be CNAME only)")

            parent_domain = Domain(
                name=domain,
                ip=actual_domain_ips if actual_domain_ips else [],
                is_wildcard=True,
                wildcard_type=wildcard_types if wildcard_types else None,
                cname_record=actual_domain_cname or wildcard_cname or None
            )
            wildcard_parent_assets.append(parent_domain)
            logger.info(f"📋 Adding wildcard parent domain as asset: {domain}")

            apex = domain.lower() if isinstance(domain, str) else str(domain).lower()
            for ip in actual_domain_ips:
                wildcard_parent_ips.add(Ip(ip=ip, discovered_via_domain=apex))

        if not wildcard_parent_assets:
            return None

        logger.info(f"📋 Will include {len(wildcard_parent_assets)} wildcard parent domain(s) in results")
        return {
            AssetType.SUBDOMAIN: wildcard_parent_assets,
            AssetType.IP: list(wildcard_parent_ips),
        }

    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """
        Parse puredns output into Domain and IP assets.
        
        Expected output format (JSON lines):
        {"domain": "sub.example.com", "ips": ["1.2.3.4"], "cname": "alias.example.com"}
        
        Args:
            output: Raw output from puredns wrapper
            params: Optional task parameters
            
        Returns:
            Dict mapping AssetType to lists of assets
        """
        domains = []
        ips = set()

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        if not normalized_output:
            logger.warning("Empty output received from puredns")
            return {AssetType.SUBDOMAIN: [], AssetType.IP: []}

        # Process JSON lines output
        for line in normalized_output.strip().split('\n'):
            if not line.strip():
                continue
            
            try:
                data = json.loads(line)
                self._process_puredns_entry(data, domains, ips)
            except json.JSONDecodeError:
                # Try to parse as plain domain name
                domain_name = line.strip().lower()
                if domain_name and '.' in domain_name:
                    domain = Domain(name=domain_name)
                    domains.append(domain)
                    logger.debug(f"Parsed plain domain: {domain_name}")

        # Convert IPs set to list
        ip_list = list(ips)
        
        logger.info(f"Found {len(domains)} subdomains and {len(ip_list)} unique IPs from DNS bruteforce")
        
        return {
            AssetType.SUBDOMAIN: domains,
            AssetType.IP: ip_list
        }

    def _process_puredns_entry(self, data: Dict, domains: List[Domain], ips: set):
        """
        Process a single puredns entry and add to domains and IPs collections.
        
        Args:
            data: Parsed JSON data from puredns output
            domains: List to append Domain objects to
            ips: Set to add Ip objects to
        """
        try:
            # Extract domain name
            domain_name = data.get('domain', '').lower()
            if not domain_name:
                return
            
            # Extract IP addresses
            ip_addresses = data.get('ips', [])
            if isinstance(ip_addresses, str):
                ip_addresses = [ip_addresses]
            
            # Extract CNAME
            cname = data.get('cname', '')
            if cname:
                cname = cname.lower()
            
            # Create IP objects
            for ip_addr in ip_addresses:
                if ip_addr:
                    ip_obj = Ip(ip=ip_addr, discovered_via_domain=domain_name)
                    ips.add(ip_obj)
            
            # Create Domain object
            domain = Domain(
                name=domain_name,
                ip=ip_addresses if ip_addresses else [],
                cname_record=cname if cname else None
            )
            domains.append(domain)
                        
        except Exception as e:
            logger.error(f"Error processing puredns entry: {e}")
            logger.error(f"Entry data: {data}")

    def transform_to_findings(self, assets: Dict[AssetType, List[Any]], context: Dict[str, Any]) -> Dict[Any, List[Any]]:
        """
        Transform subdomain assets to TyposquatDomain findings for typosquat detection workflow.

        This implements the dual-purpose task pattern where the same task can produce
        either assets (normal mode) or findings (typosquat mode).

        Args:
            assets: Parsed subdomain assets from parse_output()
            context: Typosquat context containing:
                - program_name: Program name for the finding

        Returns:
            Dict mapping FindingType.TYPOSQUAT_DOMAIN to list of TyposquatDomain findings
        """
        subdomains = assets.get(AssetType.SUBDOMAIN, [])
        if not subdomains:
            logger.info("No subdomains to transform to findings")
            return {}

        # Extract context
        program_name = context.get('program_name', '')

        logger.info(f"Transforming {len(subdomains)} subdomain assets to TyposquatDomain findings")
        logger.info(f"Context: program={program_name}")

        findings = []
        for domain_asset in subdomains:
            # Skip any subdomain that has no resolved IPs – we don't want
            # empty-IP entries as either assets or typosquat findings.
            if not getattr(domain_asset, "ip", None):
                logger.debug(f"Skipping {getattr(domain_asset, 'name', 'unknown')} for findings – no IPs")
                continue

            try:
                # Create TyposquatDomain finding
                finding = TyposquatDomain(
                    typo_domain=domain_asset.name,
                    dns_a_records=domain_asset.ip,
                    is_wildcard=domain_asset.is_wildcard,
                    wildcard_types=domain_asset.wildcard_type,
                    domain_registered=True,
                    program_name=program_name,
                    source='dns_bruteforce'
                )

                findings.append(finding)
                logger.debug(f"Created TyposquatDomain finding: {finding.typo_domain}")

            except Exception as e:
                logger.error(f"Error transforming subdomain asset to finding: {e}")
                logger.error(f"Domain asset: {domain_asset}")

        logger.info(f"Successfully transformed {len(findings)} subdomains to TyposquatDomain findings")
        return {FindingType.TYPOSQUAT_DOMAIN: findings}
