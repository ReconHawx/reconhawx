#!/usr/bin/env python3
import argparse
import logging
import json
import sys
import os
# import ssl
import requests
import subprocess
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
# Import dnsx_wrapper for wildcard detection
from dnsx_wrapper import is_wildcard
from utils.enhanced_whois_checker import DomainStatus, EnhancedWhoisChecker

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------
# Logging setup – default to INFO but allow override via env
# or the forthcoming --log-level CLI option.
# ------------------------------------------------------------
DEFAULT_LOG_LEVEL = os.getenv("TYPO_WORKER_LOG", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)

# Disable whois.whois logging
logging.getLogger("whois.whois").setLevel(logging.CRITICAL + 1)

logger = logging.getLogger(__name__)

def process_variations(variations_data, analyzer, args, results):
    """Process variations data for both stdin and file modes"""
    
    # Handle subdomain discovery mode
    if args.find_subdomains or any(item.get('_is_subdomain_discovery') for item in variations_data):
        for variation_entry in variations_data:
            apex_domain = variation_entry['domain']            
            subdomains = analyzer._find_subdomains(apex_domain)
            if subdomains:
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    # Submit all subdomain analysis tasks
                    future_to_subdomain = {
                        executor.submit(
                            analyzer.analyze_domain,
                            subdomain,
                            args.active,
                            args.geoip
                        ): subdomain
                        for subdomain in subdomains
                    }
                    
                    # Collect results as they complete
                    for future in as_completed(future_to_subdomain):
                        subdomain = future_to_subdomain[future]
                        
                        try:
                            domain_info, typosquat_urls_objects = future.result()
                            logger.debug(f"Analyzed subdomain {subdomain}: registered={domain_info.get('registered')}, urls_count={len(typosquat_urls_objects) if typosquat_urls_objects else 0}")
                            
                            if domain_info and domain_info.get("registered", False):
                                result = {
                                    "typo_domain": subdomain,
                                    "info": domain_info,
                                    "typosquat_urls": typosquat_urls_objects or [],
                                    "fuzzers": ["subdomain_discovery"],
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }
                                
                                # Add subdomain discovery marker if enabled
                                if args.subdomain_discovery_enabled:
                                    result["_subdomain_discovery_enabled"] = True

                                results.append(result)

                        
                        except Exception as e:
                            logger.error(f"Error processing subdomain {subdomain}: {e}")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_variation = {
                executor.submit(
                    analyzer.analyze_domain,
                    variation_entry['domain'],
                    args.active,
                    args.geoip
                ): variation_entry
                for variation_entry in variations_data
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_variation):
                variation_entry = future_to_variation[future]
                
                try:
                    domain_info, typosquat_urls_objects = future.result()
                    logger.debug(f"Analyzed variation {variation_entry['domain']}: registered={domain_info.get('registered')}, urls_count={len(typosquat_urls_objects) if typosquat_urls_objects else 0}")
                    
                    if domain_info and domain_info.get("registered", False):
                        result = {
                            "typo_domain": variation_entry['domain'],
                            "info": domain_info,
                            "typosquat_urls": typosquat_urls_objects or [],
                            "fuzzers": variation_entry.get('fuzzers', []),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        
                        # Add subdomain discovery marker and run subfinder if enabled
                        if args.subdomain_discovery_enabled:
                            result["_subdomain_discovery_enabled"] = True
                            subdomains = analyzer._find_subdomains(variation_entry['domain'])
                            result["subdomains"] = subdomains
                        
                        results.append(result)
                    else:
                        logger.debug(f"Variation {variation_entry['domain']} not registered, skipping")
                    
                except Exception as e:
                    logger.debug(f"Error processing variation {variation_entry['domain']}: {e}")

class BuiltInDomainAnalyzer:
    """Built-in domain analyzer with no external dependencies"""
    
    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self._whois_checker = EnhancedWhoisChecker()
    
    def _is_subdomain(self, domain: str) -> bool:
        """Determine if a domain is a subdomain (vs root domain)"""
        parts = domain.split('.')
        # Simple heuristic: if more than 2 parts, likely a subdomain
        # This isn't perfect (doesn't handle .co.uk etc.) but works for most cases
        return len(parts) > 2
    
    def _get_root_domain(self, domain: str) -> str:
        """Extract the root domain from a subdomain"""
        parts = domain.split('.')
        if len(parts) > 2:
            # Return the last two parts (root domain)
            return '.'.join(parts[-2:])
        return domain
    
    def analyze_domain(self, domain: str, active_checks: bool = False, 
                      geoip_checks: bool = False) -> Dict[str, Any]:
        """Analyze a single domain for typosquatting characteristics"""
        info = {
            "domain": domain,
            "registered": False,
            "dns_a": [],
            "dns_mx": [],
            "dns_ns": [],
            "whois": {},
            "ssl": {},
            "http": {},
            "geoip": {},
            "is_wildcard": False,
            "wildcard_types": []
        }
        
        typosquat_urls_objects = []
        is_subdomain = self._is_subdomain(domain)
        
        try:
            # Check if domain is registered and detect wildcards using dnsx_wrapper
            dns_results = self._resolve_domain_with_wildcard_detection(domain)
            if dns_results["has_records"]:
                info["registered"] = True
                info["dns_a"] = dns_results.get("a_records", [])
                info["dns_mx"] = dns_results.get("mx_records", [])
                info["dns_ns"] = dns_results.get("ns_records", [])
                info["is_wildcard"] = dns_results.get("is_wildcard", False)
                info["wildcard_types"] = dns_results.get("wildcard_types", [])
                # Perform additional checks if domain is registered
                if active_checks:
                    #info["ssl"] = self._check_ssl(domain)
                    #info["http"] = self._check_http(domain)
                    typosquat_urls_objects = self._check_http_with_httpx(domain)

                
                if geoip_checks and info["dns_a"]:
                    info["geoip"] = self._check_geoip(info["dns_a"][0])
                
                # For subdomains that resolve to IP, get WHOIS from root domain
                if is_subdomain:
                    root_domain = self._get_root_domain(domain)
                    logger.debug(f"Subdomain {domain} resolved to IP, getting WHOIS from root domain: {root_domain}")
                    whois_results = self._check_whois(root_domain)
                    if whois_results:
                        info["registered"] = True
                        info["whois"] = whois_results
                        # Add a note that WHOIS came from root domain
                        info["whois"]["_whois_source"] = root_domain
                    else:
                        info["whois"] = {}
            else:
                # If this is a subdomain and it doesn't resolve to IP, return early
                if is_subdomain:
                    logger.debug(f"Subdomain {domain} doesn't resolve to IP, skipping further processing")
                    return info, typosquat_urls_objects

            # For root domains, check whois regardless of DNS results
            if not is_subdomain:
                # Check if domain is registered using whois without regards to the DNS results
                # WHOIS (passive – does not actively interact with the target).
                whois_results = self._check_whois(domain)
                if whois_results:
                    info["registered"] = True
                    info["whois"] = whois_results
                else:
                    info["whois"] = {}
                    # If no DNS records AND no WHOIS, mark as not registered
                    if not info.get("dns_a") and not info.get("dns_mx"):
                        info["registered"] = False

        except Exception as e:
            logger.warning(f"Error analyzing {domain}: {e}")
            # Return info with registered=False to ensure invalid domains are filtered
            info["registered"] = False

        return info, typosquat_urls_objects
    
    def _find_subdomains(self, domain: str) -> List[str]:
        """Find subdomains for a given domain using subfinder"""
        subdomains = []
        
        try:
            # Run subfinder to discover subdomains
            cmd = ['subfinder', '-d', domain, '-silent', '-o', '/dev/stdout']
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Parse subfinder output - each line is a subdomain
                raw_lines = result.stdout.strip().split('\n')
                
                for line in raw_lines:
                    subdomain = line.strip()
                    if subdomain and subdomain != domain:
                        subdomains.append(subdomain)
            else:
                logger.warning(f"❌ Subfinder failed for {domain} with return code {result.returncode}")
                logger.warning(f"   stderr: {result.stderr}")
                logger.warning(f"   stdout: {result.stdout}")
                
        except subprocess.TimeoutExpired:
            logger.error(f"⏰ Subfinder timeout for domain {domain} (300s)")
        except FileNotFoundError:
            logger.error("❌ Subfinder not found - ensure it's installed in the container")
        except Exception as e:
            logger.error(f"💥 Error running subfinder for {domain}: {e}")
            logger.exception("Full traceback:")
        
        return subdomains
    
    def _resolve_domain_with_wildcard_detection(self, domain: str) -> Dict[str, Any]:
        """Resolve domain using DNS and detect wildcard domains using dnsx_wrapper"""
        result = {
            "has_records": False,
            "a_records": [],
            "mx_records": [],
            "ns_records": [],
            "is_wildcard": False,
            "wildcard_types": []
        }
        
        #logger.debug(f"Resolving domain: {domain}")
        
        try:
            # First, do basic DNS resolution
            import socket
            try:
                ip = socket.gethostbyname(domain)
                result["a_records"] = [ip]
                result["has_records"] = True
            except socket.gaierror:
                pass
            
            # Try to resolve MX records using dig if available
            try:
                mx_result = subprocess.run(
                    ['dig', '+short', 'MX', domain],
                    capture_output=True, text=True, timeout=10
                )
                if mx_result.returncode == 0 and mx_result.stdout.strip():
                    mx_records = [line.strip() for line in mx_result.stdout.strip().split('\n') if line.strip()]
                    result["mx_records"] = mx_records
                    if mx_records:
                        result["has_records"] = True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            # Try to resolve NS records using dig if available
            try:
                ns_result = subprocess.run(
                    ['dig', '+short', 'NS', domain],
                    capture_output=True, text=True, timeout=10
                )
                if ns_result.returncode == 0 and ns_result.stdout.strip():
                    ns_records = [line.strip() for line in ns_result.stdout.strip().split('\n') if line.strip()]
                    result["ns_records"] = ns_records
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            # If domain has records, check for wildcard behavior
            if result["has_records"]:
                try:
                    # Use dnsx_wrapper to detect wildcard behavior
                    import asyncio
                    
                    # Create event loop if none exists
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    # Check for wildcard behavior
                    if loop.is_running():
                        # If loop is already running, create a new thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(self._run_wildcard_check, domain)
                            wildcard_result = future.result(timeout=30)
                    else:
                        # Run in current loop
                        wildcard_result = loop.run_until_complete(is_wildcard(domain))
                    
                    if wildcard_result and isinstance(wildcard_result, tuple) and len(wildcard_result) == 2:
                        is_wild, wild_types = wildcard_result
                        result["is_wildcard"] = is_wild
                        result["wildcard_types"] = wild_types if wild_types else []
                        
                        logger.debug(f"Wildcard check for {domain}: is_wildcard={is_wild}, types={wild_types}")
                    
                except Exception as e:
                    logger.warning(f"Wildcard detection failed for {domain}: {e}")
                    # Continue without wildcard detection
            else:
                logger.debug(f"Domain {domain} has no DNS records")
        
        except Exception as e:
            logger.debug(f"DNS resolution error for {domain}: {e}")
        
        logger.debug(f"DNS resolution result for {domain}: {result}")
        return result
    
    def _run_wildcard_check(self, domain: str):
        """Run wildcard check in a separate thread with its own event loop"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(is_wildcard(domain))
        finally:
            loop.close()
        
    def _check_http_with_httpx(self, domain: str) -> List[Dict[str, Any]]:
        """Check HTTP response with httpx"""
        try:
            command = (
                f"printf '{domain}' | httpx "
                "-fr "
                "-maxr 10 "
                "-include-chain "
                "-silent "
                "-status-code "
                "-content-length "
                "-tech-detect "
                "-threads 50 "
                "-no-color "
                "-json "
                "-efqdn "
                "-tls-grab "
                "-pipeline "
                "-http2 "
                "-bp "
                "-ip "
                "-cname "
                "-asn "
                "-random-agent "
                "-favicon "
                "-hash sha256 "
                "-p 80-99,443-449,11443,8443-8449,9000-9003,8080-8089,8801-8810,3000,5000"
            )
            # Use shell=True to allow the full command string with pipes
            result = subprocess.run(command, capture_output=True, text=True, timeout=300, shell=True)
            
            typosquat_urls = []
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    try:
                        item = json.loads(line)
                        # Extract TLS data if available
                        tls_data = item.get("tls", {})
                        
                        # Get the full URL for later screenshot processing
                        url = item.get("url", "")
                        
                        typosquat_urls.append({
                            "url": url,
                            "hostname": domain,
                            "ips": item.get("a", []),
                            "port": int(item.get("port", 0)),
                            "scheme": item.get("scheme", ""),
                            "technologies": item.get("tech", []),
                            "path": item.get("path", ""),
                            "method": item.get("method", ""),
                            "http_status_code": item.get("status_code", 0),
                            "chain_status_codes": item.get("chain_status_codes", []),
                            "final_url": item.get("final_url", ""),
                            "response_time": int(item.get("time", "0ms").replace("ms", "").split(".")[0]),
                            "lines": item.get("lines", 0),
                            "title": item.get("title", ""),
                            "words": item.get("words", 0),
                            "body_preview": item.get("body_preview", ""),
                            "resp_body_hash": item.get("hash", {}).get("body_sha256", ""),
                            "favicon_hash": item.get("favicon", ""),
                            "favicon_url": item.get("favicon_url", ""),
                            "content_type": item.get("content_type", ""),
                            "content_length": item.get("content_length", 0),
                            # Preserve TLS data for SSL certificate processing
                            "tls": tls_data
                            # Screenshots will be handled by screenshot_website task
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing HTTP response for {domain}: {e}")
                        logger.debug(f"Line: {line}")
                
                logger.debug(f"Extracted {len(typosquat_urls)} URLs from httpx output for {domain}")
            else:
                logger.warning(f"HTTPX command failed for {domain}: return_code={result.returncode}, stderr={result.stderr[:200] if result.stderr else 'None'}")

            return typosquat_urls

        except Exception as e:
            logger.debug(f"HTTP check error for {domain}: {e}")
            return []
        
    def _check_geoip(self, ip: str) -> Dict[str, Any]:
        """Check GeoIP information"""
        geoip_info = {
            "country": "",
            "city": "",
            "org": ""
        }
        
        try:
            # Use a simple GeoIP service
            response = requests.get(
                f"http://ip-api.com/json/{ip}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                geoip_info["country"] = data.get("country", "")
                geoip_info["city"] = data.get("city", "")
                geoip_info["org"] = data.get("org", "")
        
        except Exception as e:
            logger.debug(f"GeoIP check error for {ip}: {e}")
        
        return geoip_info
    
    def _check_whois(self, domain: str) -> Dict[str, Any]:
        """Retrieve WHOIS via EnhancedWhoisChecker (python-whois + direct fallback)."""
        meaningful_keys = {
            "registrar",
            "creation_date",
            "expiration_date",
            "registrant_name",
            "registrant_org",
            "registrant_country",
            "admin_email",
        }

        def _date_to_str(val: Optional[datetime]) -> Optional[str]:
            if val is None:
                return None
            return val.isoformat()

        try:
            result = self._whois_checker.check_whois(domain)
            if result.status != DomainStatus.REGISTERED:
                return {}

            whois_info: Dict[str, Any] = {
                "domain_name": domain.lower(),
                "registrar": result.registrar,
                "creation_date": _date_to_str(result.creation_date),
                "expiration_date": _date_to_str(result.expiration_date),
                "registrant_name": result.registrant_name,
                "registrant_org": result.registrant_org,
                "registrant_country": result.registrant_country,
                "admin_email": result.admin_email,
            }
            whois_info = {k: v for k, v in whois_info.items() if v not in (None, "", [])}

            if not any(key in whois_info for key in meaningful_keys):
                logger.debug(
                    "WHOIS for %s has no meaningful registration data, treating as unregistered",
                    domain,
                )
                return {}

            logger.debug("WHOIS info extracted for %s: %s", domain, whois_info)
            return whois_info

        except Exception as e:
            logger.debug("WHOIS lookup failed for %s: %s", domain, e)
            return {}

def main():
    """Main worker function that tests provided domain variations."""
    parser = argparse.ArgumentParser(description='Standalone typosquat worker for runner integration.')
    
    # Domain input options
    parser.add_argument('--variations-file', 
                       help='JSON file containing domain variations to test (generated by runner)')
    parser.add_argument('--variations-stdin', action='store_true',
                       help='Read domain variations from stdin as JSON (preferred for container environments)')
    parser.add_argument('--domain', help='Single domain to analyze for typosquatting (legacy)')
    
    # Testing options
    parser.add_argument('--workers', type=int, default=5, 
                       help='Number of parallel workers')
    parser.add_argument('--active', action='store_true', 
                       help='Enable active checks (SSL, HTTP)')
    parser.add_argument('--geoip', action='store_true', 
                       help='Enable GeoIP lookups to determine domain location/country')
    parser.add_argument('--find-subdomains', action='store_true',
                       help='Enable subdomain discovery using subfinder')
    parser.add_argument('--subdomain-discovery-enabled', action='store_true',
                       help='Mark results as coming from subdomain discovery mode')
    # Output options
    parser.add_argument('--output-json', action='store_true', 
                       help='Output findings as JSON (for runner integration)')
    parser.add_argument('--no-store', action='store_true', 
                       help='Disable storing results in MongoDB (ignored - no storage by default)')
    
    # Program identification
    # parser.add_argument('--program', default='typosquat_worker', 
    #                    help='Program name to associate with detected suspicious domains')
    
    args = parser.parse_args()
    
    try:
        analyzer = BuiltInDomainAnalyzer(max_workers=args.workers)
        results = []
        
        if args.variations_stdin:
            # New mode: read variations from stdin (preferred for containers)
            try:
                stdin_data = sys.stdin.read()
                if not stdin_data.strip():
                    logger.error("No data received from stdin")
                    return 1
                
                variations_data = json.loads(stdin_data)
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON data from stdin: {e}")
                return 1
            except Exception as e:
                logger.error(f"Error reading from stdin: {e}")
                return 1
            
            # Process variations data
            process_variations(variations_data, analyzer, args, results)
        
        elif args.variations_file:
            # File mode: test variations provided by runner via file
            try:
                with open(args.variations_file, 'r') as f:
                    variations_data = json.load(f)
            except Exception as e:
                logger.error(f"Error reading variations file: {e}")
                return 1
            
            # Process variations data
            process_variations(variations_data, analyzer, args, results)
        
        elif args.domain:
            #logger.info(f"Analyzing single domain: {args.domain}")
            # Legacy mode: single domain analysis
            domain_info, typosquat_urls_objects = analyzer.analyze_domain(args.domain, args.active, args.geoip)
            if domain_info and domain_info.get("registered", False):
                result = {
                    "typo_domain": args.domain,
                    "info": domain_info,
                    "typosquat_urls": typosquat_urls_objects or [],
                    "fuzzers": [],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Add subdomain discovery marker and run subfinder if enabled
                if args.subdomain_discovery_enabled:
                    result["_subdomain_discovery_enabled"] = True
                    subdomains = analyzer._find_subdomains(args.domain)
                    result["subdomains"] = subdomains
                
                results.append(result)
                #logger.info(f"Added single domain result: {args.domain}")
        
        else:
            logger.error("Either --variations-stdin, --variations-file, or --domain argument is required")
            return 1
        
        # Output results
        if results:
            #logger.info(f"Found {len(results)} registered domains, outputting results...")
            for result in results:
                #result['program_name'] = os.getenv('PROGRAM_NAME', '')
                #logger.debug(f"Outputting result: {result}")
                print(json.dumps(result, default=str))
        #else:
        #    logger.warning("No registered domains found - no results to output")

        return 0
        
    except Exception as e:
        logger.error(f"Error in typosquat worker: {e}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Occurs when piping output and downstream closes early (e.g., jq error)
        try:
            sys.stderr.close()
        except Exception:
            pass
        sys.exit(1)