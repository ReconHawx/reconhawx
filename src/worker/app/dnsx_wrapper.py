#!/usr/bin/env python

import subprocess
import logging
from typing import List
import random
import os
import sys
import json
import aiohttp
import asyncio
import string
import ipaddress
import requests
import datetime
import redis
from typing import Dict, Any
logger = logging.getLogger(__name__)

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REQ_FILES_PATH = os.getenv("REQ_FILES_PATH", "/workspace/files")
RESOLVERS_FILE = os.getenv("RESOLVERS_FILE", f"{REQ_FILES_PATH}/resolvers.txt")

def fetch_oci_cidr():
    try:
        url = 'https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Initialize the result structure
        result = {
            "oracle_cloud": {
                "cidr": []
            }
        }
        
        # Extract all CIDR ranges from all regions
        for region in data.get('regions', []):
            for cidr_obj in region.get('cidrs', []):
                if 'cidr' in cidr_obj:
                    result['oracle_cloud']['cidr'].append(cidr_obj['cidr'])
        
        return result
    except requests.RequestException:
        #print(f"Error fetching OCI data: {e}")
        return {"oracle_cloud": {"cidr": []}}

def fetch_google_cloud_cidr():
    try:
        url = 'https://www.gstatic.com/ipranges/cloud.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Initialize the result structure
        grouped_prefixes = {}
        
        # Process all prefixes
        for prefix in data.get('prefixes', []):
            service = prefix.get('service', '').lower().replace(' ', '_')
            
            # Skip if no service defined
            if not service:
                continue
                
            # Initialize service entry if not exists
            if service not in grouped_prefixes:
                grouped_prefixes[service] = {"cidr": [], "asn": []}
            
            # Add IPv4 prefix if present
            if 'ipv4Prefix' in prefix:
                grouped_prefixes[service]["cidr"].append(prefix['ipv4Prefix'])
                    
        return grouped_prefixes
    except requests.RequestException:
       #print(f"Error fetching Google Cloud data: {e}")
        return {}

def fetch_azure_cidr():
    try:
        # Fetch date for last monday that has completed data
        today = datetime.datetime.now()
        # Always use the most recent completed Monday (never today if today is Monday)
        # Add 7 days to ensure we get the previous Monday if today is Monday
        last_monday = today - datetime.timedelta(days=(today.weekday() or 7) + 7)
        url = f'https://download.microsoft.com/download/7/1/d/71d86715-5596-4529-9b13-da13a5de5b63/ServiceTags_Public_{last_monday.strftime("%Y%m%d")}.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Initialize the result structure
        grouped_prefixes = {}
        
        # Process all values (services)
        for service in data.get('values', []):
            properties = service.get('properties', {})
            platform = properties.get('platform', '').lower()
            system_service = properties.get('systemService', '').lower().replace(' ', '_')
            
            # Skip if no platform or system service defined
            if not platform or not system_service:
                continue
                
            # Format provider name as platform.system_service
            # Remove "azure" prefix from systemService if it starts with it
            if system_service.startswith('azure_'):
                system_service = system_service[6:]  # Remove "azure_" prefix
            service_name = f"{platform}_{system_service}"
            
            # Initialize service entry if not exists
            if service_name not in grouped_prefixes:
                grouped_prefixes[service_name] = {"cidr": [], "asn": []}    
            
            # Add address prefixes if present (IPv4 only)
            address_prefixes = properties.get('addressPrefixes', [])
            for prefix in address_prefixes:
                if prefix:  # Ensure prefix is not empty
                    # Filter out IPv6 addresses (containing ':')
                    if ':' not in prefix:
                        grouped_prefixes[service_name]["cidr"].append(prefix)
        
        return grouped_prefixes
    except requests.RequestException:
        #print(f"Error fetching Azure data: {e}")
        return {}

def fetch_aws_cidr():
    try:
        # Fetch the JSON data
        url = 'https://ip-ranges.amazonaws.com/ip-ranges.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Group ip_prefix values by service
        grouped_prefixes = {}
        for item in data.get('prefixes', []):
            service = item.get('service', 'UNKNOWN').lower()
            if service == 'amazon':
                continue
                
            service_name = f"amazon_{service}"
            ip_prefix = item.get('ip_prefix')
            if service_name not in grouped_prefixes:
                grouped_prefixes[service_name] = {"cidr": [], "asn": []}
            if ip_prefix:
                grouped_prefixes[service_name]["cidr"].append(ip_prefix)
                grouped_prefixes[service_name]["asn"] = []
        return grouped_prefixes
    except requests.RequestException:
        #print(f"Error fetching data: {e}")
        return {}

def fetch_cdn77_cidr():
    try:
        url = 'https://prefixlists.tools.cdn77.com/public_lmax_prefixes.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Extract prefixes from the response
        prefixes = []
        for prefix_obj in data.get('prefixes', []):
            if 'prefix' in prefix_obj:
                prefixes.append(prefix_obj['prefix'])
        
        return {"cdn77": {"cidr": prefixes, "asn": []}}
    except requests.RequestException as e:
        print(f"Error fetching CDN77 data: {e}")
        return {"cdn77": {"cidr": [], "asn": ['60068']}}

def fetch_fastly_cidr():
    try:
        url = 'https://api.fastly.com/public-ip-list'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json().get("addresses", [])
        return {"fastly": {"cidr": data, "asn": ['54113']}}
    except requests.RequestException as e:
        print(f"Error fetching Fastly data: {e}")
        return {}

def build_providers_list():
    # Try to get cached result from Redis first
    cache_key = "resolve_ip:providers_list"
    #cache_ttl = 7 * 24 * 60 * 60  # 7 days in seconds
    cache_ttl = 120
    try:
        # Initialize Redis connection
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        # Try to get cached data
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
            
    except Exception as e:
        logger.debug("Redis cache error (will build fresh list): %s", e)
    
    # Build the providers list if no cache found

    _return = {
        'digitalocean': {
            'asn': ['14061'],
            'cidr': open(f'{REQ_FILES_PATH}/wafcdn_ipranges/digitalocean.txt').read().splitlines()
        },
        'cloudflare': {
            'asn': ['13335'],
            'cidr': requests.get("https://www.cloudflare.com/ips-v4").text.splitlines()
        },
        'akamai': {
            'asn': ['12222', '16625', '16702', '17204', '18680', '18717', '20189', '20940', '21342', '21357', '21399', '22207', '22452', '23454', '23455', '23903', '24319', '26008', '30675', '31107', '31108', '31109', '31110', '31377', '33047', '33905', '34164', '34850', '35204', '35993', '35994', '36183', '39836', '43639', '55409', '55770', '63949', '133103', '393560'],
            'cidr': [
                '23.32.0.0/11',
                '23.192.0.0/11',
                '23.235.32.0/20',
                '104.156.80.0/20',
                '104.160.0.0/14',
                '104.192.0.0/14',
                '104.224.0.0/12',
                '104.248.0.0/13',
                '104.252.0.0/14',
                '104.252.16.0/20',
                '104.252.32.0/19',
                '104.252.64.0/18',
                '104.252.128.0/17',
                '104.64.0.0/10',
                '2.16.0.0/13',
                '23.74.0.0/23',
                '104.101.220.0/24',
                '104.101.221.0/24',
                '184.51.125.0/24',
                '184.51.33.0/24',
                '2.16.37.0/24',
                '2.22.226.0/24',
                '23.15.12.0/24',
                '23.200.22.0/24',
                '23.56.209.0/24',
                '23.62.225.0/24',
                '23.79.224.0/24',
                '23.79.229.0/24',
                '23.79.230.0/24',
                '23.79.232.0/24',
                '23.79.237.0/24',
                '23.79.238.0/24',
                '63.208.195.0/24',
                '72.246.116.0/24',
                '72.246.199.0/24',
                '72.246.3.0/24',
                '72.246.44.0/24',
                '72.247.150.0/24',
                '72.247.44.0/24',
                '72.247.45.0/24',
                '72.247.47.0/24',
                '80.67.65.0/24',
                '80.67.70.0/24',
                '80.67.73.0/24',
                '88.221.208.0/24',
                '88.221.209.0/24'
            ]
        },
        'imperva': {
            'asn': [],
            'cidr': [
                '199.83.128.0/21',
                '198.143.32.0/19',
                '149.126.72.0/21',
                '103.28.248.0/22',
                '185.11.124.0/22',
                '192.230.64.0/18',
                '45.64.64.0/22',
                '107.154.0.0/16',
                '45.60.0.0/16',
                '45.223.0.0/16',
                '131.125.128.0/17'
            ]
        },
        'f5': {
            'asn': ['35280' ],
            'cidr': [
                '5.182.215.0/25',
                '84.54.61.0/25',
                '23.158.32.0/25',
                '84.54.62.0/25',
                '185.94.142.0/25',
                '185.94.143.0/25',
                '159.60.190.0/24',
                '159.60.168.0/24',
                '159.60.180.0/24',
                '159.60.174.0/24',
                '159.60.176.0/24',
                '5.182.213.0/25',
                '5.182.212.0/25',
                '5.182.213.128/25',
                '5.182.214.0/25',
                '84.54.60.0/25',
                '185.56.154.0/25',
                '159.60.160.0/24',
                '159.60.162.0/24',
                '159.60.188.0/24',
                '159.60.182.0/24',
                '159.60.178.0/24',
                '103.135.56.0/25',
                '103.135.57.0/25',
                '103.135.56.128/25',
                '103.135.59.0/25',
                '103.135.58.128/25',
                '103.135.58.0/25',
                '159.60.189.0/24',
                '159.60.166.0/24',
                '159.60.164.0/24',
                '159.60.170.0/24',
                '159.60.172.0/24',
                '159.60.191.0/24'
            ]
        },
        'edgecast': {
            'asn': ['15133'],
            'cidr': []
        },
        'stackpath': {
            'asn': ['12989'],
            'cidr': []
        },
        'edgenext': {
            'asn': ['139057','149981'],
            'cidr': []
        },
        **fetch_aws_cidr(),
        **fetch_oci_cidr(),
        **fetch_google_cloud_cidr(),
        **fetch_azure_cidr(),
        **fetch_fastly_cidr(),
        **fetch_cdn77_cidr(),
        'azure': {
            'asn': [],
            'cidr': open(f'{REQ_FILES_PATH}/wafcdn_ipranges/azure.txt').read().splitlines()
        }
    }
    # Cache the result in Redis for 7 days
    try:
        if 'redis_client' in locals():
            redis_client.setex(cache_key, cache_ttl, json.dumps(_return))
    except Exception as e:
        logger.debug("Failed to cache providers list in Redis: %s", e)
    
    return _return

async def get_asn(ip: str) -> str:
    """Get ASN information from whois servers for ip"""
    whois_server = "whois.cymru.com"
    command = f"whois -h {whois_server} {ip}"
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    parsed_result = result.stdout.split("\n")[1].strip().split("|")[0].replace(" ", "")
    return parsed_result

async def is_waf_cdn_ip(ip: str, providers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if an IP belongs to a WAF or CDN provider.
    
    Args:
        ip (str): IP address to check
        
    Returns:
        Dict with results containing:
        - is_waf_cdn (bool): True if IP belongs to WAF/CDN
        - provider (str): Name of the provider if found
        - match_type (str): Type of match (ASN or CIDR)
    """
    result = {
        "is_waf_cdn": False,
        "provider": None
    }
    
    try:
        # Get ASN information from whois servers for ip
        try:
            asn = await get_asn(ip)
            if asn:
                for provider, info in providers.items():
                    if "asn" in info and info['asn']:
                        if asn in info['asn']:
                            result["is_waf_cdn"] = True
                            result["provider"] = provider
                            return result
        except Exception:
            #print(f"Error getting ASN for {ip}: {str(e)}")
            pass
            
        # # Check against CIDR ranges
        ip_obj = ipaddress.ip_address(ip)
        for provider, info in providers.items():
            # First check CIDR ranges as they're faster to check
            for cidr in info['cidr']:
                try:
                    if ip_obj in ipaddress.ip_network(cidr):
                        result["is_waf_cdn"] = True
                        result["provider"] = provider
                        return result
                except ValueError:
                    continue  # Skip invalid CIDR ranges
        
    except Exception as e:
        logger.error(f"Error checking WAF/CDN IP {ip}: {str(e)}")
        logger.exception(e)
    return result

async def is_wildcard(subdomain: str):
    logger.debug(f"Starting wildcard check for subdomain: {subdomain}")
    RECORD_TYPE_CODES = {
        "A": 1,
        "AAAA": 28,
        "TXT": 16,
        "NS": 2,
        "CNAME": 5,
        "MX": 15
    }
    DNS_API_URL = "https://cloudflare-dns.com/dns-query"
    async def query_dns_records(session,subdomain, record_type):
            logger.debug(f"Querying DNS records for {subdomain} with type {record_type}")
            try:
                async with session.get(DNS_API_URL, params={'name': subdomain, 'type': record_type}, headers={'Accept': 'application/dns-json'}) as response:
                    if response.status == 200:
                        raw_response = await response.text()
                        logger.debug(f"Raw DNS response for {subdomain}: {raw_response}")
                        try:
                            result = json.loads(raw_response)
                            has_answer = "Answer" in result
                            answers = result.get("Answer", []) if has_answer else []
                            # Look at the first answer's type, as this represents the actual record type
                            # before any CNAME resolution
                            if answers:
                                first_answer_type = answers[0].get("type")
                                # Convert type code back to string for easier comparison
                                first_record_type = next(
                                    (rtype for rtype, code in RECORD_TYPE_CODES.items()
                                        if code == first_answer_type), None
                                )
                                logger.debug(f"Found answers for {subdomain}: {answers}, first record type: {first_record_type}")
                                return bool(answers), answers, first_record_type

                            if not has_answer and "Authority" in result:
                                logger.debug(f"No answers but found Authority section for {subdomain}")
                                return False, [], None

                            logger.debug(f"No answers found for {subdomain}")
                            return bool(answers), answers, None
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON decode error for {subdomain}: {e}")
                            return False, [], None
                    else:
                        logger.error(f"HTTP {response.status} error for {subdomain}")
                        return False, [], None
            except Exception as e:
                logger.error(f"Error querying DNS for {subdomain}: {e}")
                return False, [], None

    async def wildcard_check(session, subdomain, record_type):
        logger.debug(f"Starting wildcard check for {subdomain} with record type {record_type}")
        try:
            record_type_code = RECORD_TYPE_CODES.get(record_type.upper())
            if not record_type_code:
                logger.warning(f"Invalid record type {record_type}")
                return False, None
            random_label = ''.join(random.choices(string.ascii_lowercase, k=10))
            valid_base, base_answers, base_actual_type = await query_dns_records(session, subdomain, record_type)
            logger.debug(f"Base query results for {subdomain}: valid={valid_base}, type={base_actual_type}, answers={base_answers}")
            if not valid_base or not base_answers:
                logger.debug(f"No valid base or answers for {subdomain}")
                valid_random, random_answers, random_actual_type = await query_dns_records(session, f"{random_label}.{subdomain}", record_type)
                logger.debug(f"Random query results for {subdomain}: valid={valid_random}, type={random_actual_type}, answers={random_answers}")
                if not valid_random or not random_answers:
                    logger.debug(f"No valid random or answers for {subdomain}")
                    return False, None

            
            test_patterns = []
            test_patterns.append(f"{random_label}.{subdomain}")
            logger.debug(f"Testing wildcard patterns for {subdomain}: {test_patterns}")
            # Test all generated patterns
            for test_subdomain in test_patterns:
                valid_garbage, garbage_answers, garbage_actual_type = await query_dns_records(
                    session, test_subdomain, record_type
                )
                logger.debug(f"Wildcard test results for {test_subdomain}: valid={valid_garbage}, type={garbage_actual_type}, answers={garbage_answers}")
                
                # If any test succeeds with the same record type, it's a wildcard
                if valid_garbage and base_actual_type == garbage_actual_type:
                    logger.debug(f"Wildcard detected for {subdomain} with type {base_actual_type}")
                    return True, base_actual_type

            logger.debug(f"No wildcard detected for {subdomain}")
            return False, None

        except Exception as e:
            logger.error(f"Error during wildcard check for {subdomain}: {str(e)}")
            return False, None

    async def process_subdomain(subdomain):
        logger.debug(f"Processing subdomain: {subdomain}")
        async with aiohttp.ClientSession() as session:
            record_types = ["A", "AAAA", "NS", "CNAME", "TXT", "MX"]
            wildcard_types = []
            global_is_wildcard = False
            try:
                for record_type in record_types:
                    logger.debug(f"Checking record type {record_type} for {subdomain}")
                    has_records, _, actual_type = await query_dns_records(session, subdomain, record_type)
                    if has_records:
                        logger.debug(f"Found records for {subdomain} with type {record_type}")
                        is_wildcard, wildcard_type = await wildcard_check(session, subdomain, record_type)
                        if is_wildcard:
                            global_is_wildcard = True
                            logger.debug(f"Confirmed wildcard for {subdomain}: {wildcard_type}")
                            wildcard_types.append(wildcard_type)
                        else:
                            logger.debug(f"No wildcard confirmed for {subdomain}")
                    else:
                        random_label = ''.join(random.choices(string.ascii_lowercase, k=10))
                        is_random_wildcard, random_wildcard_type = await wildcard_check(session, f"{random_label}.{subdomain}", record_type)
                        if is_random_wildcard:
                            logger.debug(f"Confirmed random wildcard for {subdomain}: {random_wildcard_type}")
                            wildcard_types.append(random_wildcard_type)
                        else:
                            logger.debug(f"No random wildcard confirmed for {subdomain}")
            except Exception as e:
                logger.exception(f"Error processing subdomain {subdomain}: {e}")
                return (False, [])
            if global_is_wildcard:
                return (True, wildcard_types)
            else:
                return (False, [])    
    
    result = await process_subdomain(subdomain)
    logger.debug(f"Final result for {subdomain}: {result}")
    return result

def get_random_resolvers(qty: int = 3):
    with open(RESOLVERS_FILE, 'r') as file:
        resolvers = file.read().splitlines()
    return random.sample(resolvers, qty)

def run_dnsx(targets: List[str], is_ip: bool):
    """Runs dnsx once for a list of targets (IPs or domains)."""
    if not targets:
        logger.info(f"No targets provided for {'IP' if is_ip else 'domain'} lookup.")
        return None # No process to return if list is empty
    
    random_resolvers = get_random_resolvers()
    random_resolvers_str = ",".join(random_resolvers)
    
    # Escape targets for safe inclusion in the printf command
    # Simple escaping: replace single quotes
    escaped_targets = [t.replace("'", "'\\''") for t in targets]
    targets_str = "\n".join(escaped_targets)

    if is_ip:
        # Command for IP addresses (PTR lookup)
        command = f"printf '{targets_str}\n' | dnsx -silent -nc -ptr -resp -j -r {random_resolvers_str}"
    else:
        # Command for domain names (standard lookup)
        command = f"printf '{targets_str}\n' | dnsx -nc -resp -recon -silent -j -r {random_resolvers_str}"

    logger.debug(f"Running batched dnsx command: {command}")
    process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True
        )
    return process

def is_valid_ip(address: str) -> bool:
    """Check if the given string is a valid IP address (IPv4 or IPv6)."""
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False

def main():
        asyncio.run(_main())

async def _main():
        inputs = [line.strip() for line in sys.stdin if line.strip()]
        results = {}
        ip_list = []
        domain_list = []

        if not inputs:
            print("No domains or IPs provided via stdin.", file=sys.stderr)
            sys.exit(1)

        # Initialize results and separate inputs into IPs and domains
        for item in inputs:
            results[item] = { # Initialize structure
                "dnsx": None,
                "dnsx_error": None,
                "is_wildcard": None,
                "wildcard_type": None
            }
            if is_valid_ip(item):
                ip_list.append(item)
            else:
                domain_list.append(item)
        
        # --- Process IP Addresses --- 
        ip_process = run_dnsx(ip_list, is_ip=True)
        if ip_process and ip_process.stdout:
            logger.info(f"Processing {len(ip_list)} IP addresses...")
            for line in ip_process.stdout:
                try:
                    line_data = json.loads(line.strip())
                    host = line_data.get('host') or line_data.get('input') # dnsx uses 'host' or 'input'
                    if host in results:
                        results[host]['dnsx'] = line_data
                    else:
                        logger.warning(f"Received dnsx result for unknown host: {host}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON output line for IPs: {line.strip()}")

            if ip_process.stderr:
                stderr_output_ip = "".join(ip_process.stderr)
                if stderr_output_ip:
                    logger.warning(f"Stderr output for IP batch: {stderr_output_ip.strip()}")
                # Assign error to a generic key or try to associate if possible
                # For simplicity, maybe log it is enough unless specific error handling per IP is needed
                
            ip_process.wait()
            logger.info("Finished processing IP addresses.")

        # --- Process Domain Names --- 
        domain_process = run_dnsx(domain_list, is_ip=False)
        if domain_process and domain_process.stdout:
            logger.info(f"Processing {len(domain_list)} domain names...")
            for line in domain_process.stdout:
                try:
                    line_data = json.loads(line.strip())
                    host = line_data.get('host') or line_data.get('input')
                    if host in results:
                        results[host]['dnsx'] = line_data
                    else:
                        logger.warning(f"Received dnsx result for unknown host: {host}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON output line for domains: {line.strip()}")

            if domain_process.stderr:
                stderr_output_domain = "".join(domain_process.stderr)
                if stderr_output_domain:
                    logger.warning(f"Stderr output for domain batch: {stderr_output_domain.strip()}")
                
            domain_process.wait()
            logger.info("Finished processing domain names.")

        # --- Perform Wildcard Checks (only for domains) ---
        if domain_list:
            logger.info(f"Performing wildcard checks for {len(domain_list)} domains...")
            async def run_wildcard_checks():
                tasks = [is_wildcard(domain) for domain in domain_list]
                wildcard_results = await asyncio.gather(*tasks, return_exceptions=True)
                for domain, result in zip(domain_list, wildcard_results):
                    if isinstance(result, Exception):
                        logger.error(f"Error checking wildcard for {domain}: {result}")
                        results[domain]["is_wildcard"] = None # Or some error indicator
                        results[domain]["wildcard_type"] = None
                    elif isinstance(result, tuple) and len(result) == 2:
                        is_wild, wild_types = result
                        results[domain]["is_wildcard"] = is_wild
                        results[domain]["wildcard_type"] = wild_types
                    else:
                        logger.error(f"Unexpected result format for {domain}: {result}")
                        results[domain]["is_wildcard"] = None
                        results[domain]["wildcard_type"] = None
            
            await run_wildcard_checks()
            logger.info("Finished wildcard checks.")
            
        # --- Perform CDN, Cloud Provider and WAF detection ---
        if ip_list:
            logger.info(f"Performing CDN, Cloud Provider and WAF detection for {len(ip_list)} IPs...")
            providers = build_providers_list()
            for ip in ip_list:
                result = await is_waf_cdn_ip(ip, providers)
                results[ip]["is_waf_cdn"] = result["is_waf_cdn"]
                results[ip]["provider"] = result["provider"]
        print(json.dumps(results))

if __name__ == "__main__":
    main()