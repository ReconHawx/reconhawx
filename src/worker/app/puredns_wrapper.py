#!/usr/bin/env python3
"""
PureDNS Wrapper for DNS Bruteforce Task

This wrapper handles:
1. Downloading wordlists from URLs (including API endpoints with auth)
2. Running puredns bruteforce with proper arguments
3. Filtering wildcard results (if wildcard IPs provided)
4. Parsing and outputting results in JSON format

Usage:
    python3 puredns_wrapper.py -d example.com -w /path/to/wordlist.txt
    python3 puredns_wrapper.py -d example.com -w https://api/wordlists/uuid/download
    python3 puredns_wrapper.py -d example.com -w wordlist.txt --wildcard-ips 1.2.3.4,5.6.7.8

Output format (JSON lines):
    {"domain": "sub.example.com", "ips": ["1.2.3.4", "5.6.7.8"], "cname": "alias.example.com"}
"""

import argparse
import ipaddress
import json
import logging
import os
import subprocess
import sys
import tempfile
import requests
from typing import List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Configuration
RESOLVERS_FILE = os.getenv("RESOLVERS_FILE", "/workspace/files/resolvers.txt")
TRUSTED_RESOLVERS_FILE = os.getenv("TRUSTED_RESOLVERS_FILE", "/workspace/files/resolvers-trusted.txt")
INTERNAL_API_KEY = os.getenv("INTERNAL_SERVICE_API_KEY", "")


def download_wordlist(url: str, output_path: str) -> bool:
    """
    Download a wordlist from a URL to a local file.
    
    Handles authentication for internal API downloads.
    
    Args:
        url: URL to download from
        output_path: Local path to save the wordlist
        
    Returns:
        True if download successful, False otherwise
    """
    try:
        logger.info(f"Downloading wordlist from: {url}")
        
        headers = {}
        
        # Add authorization header for internal API downloads
        if 'api:' in url or '/wordlists/' in url:
            if INTERNAL_API_KEY:
                headers['Authorization'] = f'Bearer {INTERNAL_API_KEY}'
                logger.debug("Using internal service API key for authentication")
            else:
                logger.warning("No INTERNAL_SERVICE_API_KEY found - API call may fail")
        
        response = requests.get(url, headers=headers, timeout=60, stream=True)
        response.raise_for_status()
        
        # Write to file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Get file size
        file_size = os.path.getsize(output_path)
        logger.info(f"Downloaded wordlist: {file_size} bytes")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download wordlist from {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error saving wordlist: {e}")
        return False


def resolve_wordlist(wordlist: str) -> Optional[str]:
    """
    Resolve wordlist parameter to a local file path.
    
    If the wordlist is a URL, downloads it to a temporary file.
    
    Args:
        wordlist: Wordlist path or URL
        
    Returns:
        Local file path to wordlist, or None if failed
    """
    if wordlist.startswith('http'):
        # Download to temporary file
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', 
            delete=False, 
            suffix='.txt', 
            prefix='puredns_wordlist_'
        )
        temp_path = temp_file.name
        temp_file.close()
        
        if download_wordlist(wordlist, temp_path):
            return temp_path
        else:
            # Clean up temp file on failure
            try:
                os.unlink(temp_path)
            except:
                pass
            return None
    else:
        # Local file path
        if os.path.exists(wordlist):
            return wordlist
        else:
            logger.error(f"Wordlist file not found: {wordlist}")
            return None


def run_puredns(domain: str, wordlist_path: str, wildcard_ips: List[str] = None,
                wildcard_cidrs: List[str] = None) -> List[dict]:
    """
    Run puredns bruteforce and parse results.
    
    Args:
        domain: Target domain to bruteforce
        wordlist_path: Path to local wordlist file
        wildcard_ips: List of wildcard IPs to filter out (optional)
        wildcard_cidrs: List of wildcard CIDRs; results whose IPs all fall in these subnets are filtered (optional)
        
    Returns:
        List of result dictionaries
    """
    results = []
    wildcard_ips = wildcard_ips or []
    wildcard_ips_set = set(wildcard_ips)
    wildcard_cidrs = wildcard_cidrs or []
    wildcard_networks: List[ipaddress.IPv4Network] = []
    for cidr in wildcard_cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if net.version != 4:
                logger.warning(f"Skipping non-IPv4 wildcard CIDR: {cidr}")
                continue
            wildcard_networks.append(net)
        except ValueError as e:
            logger.warning(f"Invalid wildcard CIDR {cidr}: {e}")
    
    if wildcard_ips:
        logger.info(f"Will filter results matching wildcard IPs: {wildcard_ips}")
    if wildcard_networks:
        logger.info(f"Will filter results whose IPs all fall in wildcard CIDRs: {wildcard_cidrs}")
    
    # Build puredns command
    # puredns bruteforce <wordlist> <domain> -r <resolvers> --wildcard-batch 1000 -q
    cmd = [
        'puredns',
        'bruteforce',
        wordlist_path,
        domain,
        '-r', RESOLVERS_FILE,
        '--wildcard-batch', '1000',
        '-q'  # Quiet mode - only output resolved domains
    ]
    
    # Add trusted resolvers if file exists
    if os.path.exists(TRUSTED_RESOLVERS_FILE):
        cmd.extend(['--resolvers-trusted', TRUSTED_RESOLVERS_FILE])
    
    logger.info(f"Running puredns: {' '.join(cmd)}")
    
    try:
        # Run puredns
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(timeout=600)  # 10 minute timeout
        
        if stderr:
            # Log stderr but don't fail - puredns outputs progress to stderr
            logger.debug(f"puredns stderr: {stderr[:500]}")
        
        if process.returncode != 0:
            logger.warning(f"puredns returned non-zero exit code: {process.returncode}")
        
        # Parse stdout - each line is a resolved subdomain
        for line in stdout.strip().split('\n'):
            subdomain = line.strip()
            if subdomain and '.' in subdomain:
                # puredns outputs just the subdomain name
                # We need to resolve it to get IPs
                result = {
                    'domain': subdomain.lower(),
                    'ips': [],
                    'cname': ''
                }
                results.append(result)
        
        logger.info(f"puredns found {len(results)} subdomains (before filtering)")
        
        # Now resolve the discovered subdomains to get IPs
        if results:
            results = resolve_subdomains(results)

        # After resolution, drop any subdomain that has no IPs at all.
        # We don't want to keep empty-IP entries for either assets or typosquat findings.
        if results:
            before_empty_filter = len(results)
            results = [r for r in results if r.get('ips')]
            removed_empty = before_empty_filter - len(results)
            if removed_empty > 0:
                logger.info(f"🔍 Dropped {removed_empty} subdomains with no resolved IPs")

        # Filter out results that only have wildcard IPs or IPs in wildcard CIDRs
        if (wildcard_ips_set or wildcard_networks) and results:
            def ip_is_wildcard(ip_str: str) -> bool:
                if ip_str in wildcard_ips_set:
                    return True
                try:
                    addr = ipaddress.ip_address(ip_str)
                except ValueError:
                    return False
                if addr.version != 4:
                    return False
                return any(addr in net for net in wildcard_networks)

            original_count = len(results)
            filtered_results = []

            for result in results:
                result_ips = list(result.get('ips', []))

                if not result_ips:
                    filtered_results.append(result)
                    continue

                non_wildcard_ips = [ip for ip in result_ips if not ip_is_wildcard(ip)]

                if non_wildcard_ips:
                    logger.debug(f"✅ Keeping {result['domain']} - has non-wildcard IPs: {non_wildcard_ips}")
                    filtered_results.append(result)
                else:
                    logger.debug(f"🚫 Filtering {result['domain']} - only has wildcard IPs: {result_ips}")

            results = filtered_results
            filtered_count = original_count - len(results)

            if filtered_count > 0:
                logger.info(f"🔍 Filtered out {filtered_count} wildcard results, keeping {len(results)} unique results")
        
        return results
        
    except subprocess.TimeoutExpired:
        logger.error("puredns timed out after 600 seconds")
        process.kill()
        return results
    except Exception as e:
        logger.error(f"Error running puredns: {e}")
        return results


def resolve_subdomains(subdomains: List[dict]) -> List[dict]:
    """
    Resolve discovered subdomains to get their IP addresses using dnsx.
    
    Args:
        subdomains: List of subdomain dictionaries
        
    Returns:
        Updated list with IP addresses populated
    """
    if not subdomains:
        return subdomains
    
    # Create a mapping from domain to result index
    domain_map = {s['domain']: i for i, s in enumerate(subdomains)}
    
    # Write subdomains to temp file for dnsx
    temp_input = tempfile.NamedTemporaryFile(
        mode='w',
        delete=False,
        suffix='.txt',
        prefix='dnsx_input_'
    )
    
    try:
        for subdomain in subdomains:
            temp_input.write(f"{subdomain['domain']}\n")
        temp_input.close()
        
        # Run dnsx to resolve IPs
        cmd = [
            'dnsx',
            '-l', temp_input.name,
            '-silent',
            '-resp',
            '-j',  # JSON output
            '-r', RESOLVERS_FILE
        ]
        
        logger.info(f"Resolving {len(subdomains)} subdomains with dnsx")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(timeout=120)
        
        # Parse dnsx JSON output
        for line in stdout.strip().split('\n'):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                host = data.get('host', '').lower()
                
                if host in domain_map:
                    idx = domain_map[host]
                    
                    # Extract A records (IPs)
                    a_records = data.get('a', [])
                    if a_records:
                        subdomains[idx]['ips'] = a_records
                    
                    # Extract CNAME
                    cname_records = data.get('cname', [])
                    if cname_records:
                        subdomains[idx]['cname'] = cname_records[0].lower()
                        
            except json.JSONDecodeError:
                continue
        
        logger.info("Resolved IPs for subdomains")
        
    except subprocess.TimeoutExpired:
        logger.error("dnsx timed out")
    except Exception as e:
        logger.error(f"Error running dnsx: {e}")
    finally:
        # Clean up temp file
        try:
            os.unlink(temp_input.name)
        except:
            pass
    
    return subdomains


def main():
    parser = argparse.ArgumentParser(description='PureDNS wrapper for DNS bruteforce')
    parser.add_argument('-d', '--domain', required=True, help='Target domain to bruteforce')
    parser.add_argument('-w', '--wordlist', required=True, help='Wordlist path or URL')
    parser.add_argument('--wildcard-ips', dest='wildcard_ips', default='',
                       help='Comma-separated list of wildcard IPs to filter out')
    parser.add_argument('--wildcard-cidrs', dest='wildcard_cidrs', default='',
                       help='Comma-separated CIDRs; results whose IPs all fall in these subnets are filtered as wildcard')
    
    args = parser.parse_args()
    
    # Parse wildcard IPs if provided
    wildcard_ips = []
    if args.wildcard_ips:
        wildcard_ips = [ip.strip() for ip in args.wildcard_ips.split(',') if ip.strip()]
        logger.info(f"Wildcard IPs to filter: {wildcard_ips}")
    
    # Parse wildcard CIDRs if provided
    wildcard_cidrs = []
    if args.wildcard_cidrs:
        wildcard_cidrs = [c.strip() for c in args.wildcard_cidrs.split(',') if c.strip()]
        logger.info(f"Wildcard CIDRs to filter: {wildcard_cidrs}")
    
    logger.info(f"Starting DNS bruteforce for {args.domain}")
    
    # Resolve wordlist
    wordlist_path = resolve_wordlist(args.wordlist)
    if not wordlist_path:
        logger.error("Failed to resolve wordlist")
        sys.exit(1)
    
    downloaded_wordlist = wordlist_path != args.wordlist  # Track if we downloaded it
    
    try:
        # Run puredns with wildcard filtering
        results = run_puredns(args.domain, wordlist_path, wildcard_ips, wildcard_cidrs)
        
        # Output results as JSON lines to stdout
        for result in results:
            print(json.dumps(result))
        
        logger.info(f"DNS bruteforce complete: {len(results)} subdomains found")
        
    finally:
        # Clean up downloaded wordlist
        if downloaded_wordlist and os.path.exists(wordlist_path):
            try:
                os.unlink(wordlist_path)
                logger.debug(f"Cleaned up downloaded wordlist: {wordlist_path}")
            except:
                pass


if __name__ == '__main__':
    main()
