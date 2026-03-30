import json
import logging
from typing import Dict, List, Any, Optional
import base64
from .base import Task, AssetType
from models.assets import Url, Domain, Ip, Service, Certificate
from utils import parse_url, get_valid_urls, get_valid_domains
from urllib.parse import urlparse
import dns.resolver
logger = logging.getLogger(__name__)

class TestHTTP(Task):
    name = "test_http"
    description = "Test HTTP"
    input_type = AssetType.STRING
    output_types = [AssetType.SERVICE, AssetType.SUBDOMAIN, AssetType.IP, AssetType.URL]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """Generate the httpx command for HTTP testing"""
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]

        # Use printf to properly handle newlines
        # filter url and domains from the targets list
        urls_to_process = get_valid_urls(targets_to_process)
        domains_to_process = get_valid_domains(targets_to_process)

        commands = []

        if len(urls_to_process) > 0:
            urls_text = '\n'.join(urls_to_process)
            commands.append(
                f"cat << 'EOF' | httpx -fr -maxr 10 -include-chain -silent -status-code -content-length -tech-detect -threads 50 -no-color -json -efqdn -tls-grab -pa -pipeline -http2 -bp -ip -cname -asn -random-agent -favicon -hash sha256\n{urls_text}\nEOF"
            )

        if len(domains_to_process) > 0:
            domains_text = '\n'.join(domains_to_process)
            commands.append(
                f"cat << 'EOF' | httpx -fr -maxr 10 -include-chain -silent -status-code -content-length -tech-detect -threads 50 -no-color -json -efqdn -tls-grab -pa -pipeline -http2 -bp -ip -cname -asn -random-agent -favicon -hash sha256 -p 80-99,443-449,11443,8443-8449,9000-9003,8080-8089,8801-8810,3000,5000\n{domains_text}\nEOF"
            )

        # Return array of commands to spawn separate worker jobs
        if commands:
            return commands
        else:
            return []
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse httpx output into Service, Domain, and IP assets"""
        services = []
        domains = []
        ips = []
        urls = []
        certificates = []

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        if not normalized_output:
            logger.warning("Empty output received")
            return {
                AssetType.SERVICE: [],
                AssetType.URL: [],
                AssetType.SUBDOMAIN: [],
                AssetType.IP: [],
                AssetType.CERTIFICATE: []
            }
        try:
            # Handle multiple JSON objects per line
            if isinstance(normalized_output, str) and '\n' in normalized_output:
                logger.info("Processing multi-line JSON text")
                for line in normalized_output.strip().split('\n'):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        if not item.get("failed", True):  # Only process successful requests
                            self._process_entry(item, services, domains, ips, urls, certificates)
                    except json.JSONDecodeError as e:
                        logger.error(f"Error processing line: {str(e)}")
                        logger.error(f"Problematic line: {line}")
            # Handle single JSON object
            elif isinstance(normalized_output, str):
                logger.info("Processing single JSON text")
                item = json.loads(normalized_output)
                if isinstance(item, dict):
                    if not item.get("failed", True):
                        self._process_entry(item, services, domains, ips, urls, certificates)
                elif isinstance(item, list):
                    for entry in item:
                        if not entry.get("failed", True):
                            self._process_entry(entry, services, domains, ips, urls, certificates)
                        
        except json.JSONDecodeError as e:
            logger.error(f"Error processing output as JSON: {str(e)}")
            
        logger.info(f"Found {len(services)} services, {len(domains)} domains, {len(ips)} IPs, {len(urls)} URLs, {len(certificates)} certificates")
        return {
            AssetType.SERVICE: services,
            AssetType.SUBDOMAIN: domains,
            AssetType.IP: list(ips),  # Convert set to list
            AssetType.URL: urls,
            AssetType.CERTIFICATE: certificates
        }
    
    def _process_entry(self, item: Dict, services: List, domains: List, ips: List, urls: List, certificates: List):
        """Process a single entry and update the collections"""        
        # Ensure URL is lowercase
        url = item.get("url", "").lower()
        host = item.get("host", "").lower()
        hostname = urlparse(url).netloc.split(":")[0]
        if hostname:
            hostname = hostname.lower()
        ip_discovered_via = (
            hostname if hostname and not self._is_ip_address(hostname) else None
        )
        scheme = item.get("scheme", "").lower()
        
        for ip in item.get("a", []):
            # Create Service object
            service = Service(
                ip=ip,
                port=int(item.get("port", 0)),
                protocol="tcp",
                service_name=scheme,
                program_name=item.get("program_name", ""),
            )
            services.append(service)

        
        urlObj = Url(
            url=url.rstrip('/') + item.get("path", "/"),
            hostname=hostname,
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
            content_length=item.get("content_length", 0)
        )
        urls.append(urlObj)

        # Add domain to domains list (hostname already lowercased above)
        if hostname and not self._is_ip_address(hostname):
            # Get CNAME and ensure it's lowercase
            cname = item.get("cname", [])
            if cname:
                cname = cname[0].lower()
            else:
                cname = None
            
            # Create Domain object for main host with IPs
            domain = Domain(
                name=hostname,
                ip=item.get("a", []),  # Only associate IPs with the main domain
                cname_record=cname
            )
            domains.append(domain)
        
        # If there is a final url, add it to the urls list
        redirect_chain = []
        for redirect in item.get("chain", []):
            parsed_redirect = parse_url(redirect.get("request-url"))
            if parsed_redirect:  # Check if parse_url returned a valid dict
                redirect_chain.append({
                    "index": len(redirect_chain),
                    "method": redirect.get("request", "GET / HTTP/1.1").split(" ")[0],
                    "url": parsed_redirect.get('url'),
                    "http_status_code": redirect.get("status_code"),
                    "location": redirect.get("location", None)
                })
                try:
                    hostname = parsed_redirect.get('hostname')
                    if hostname:
                        records = dns.resolver.resolve(hostname, 'A')
                        redirect_ips = [str(record.address) for record in records.rrset] if records.rrset else []
                    else:
                        redirect_ips = []
                except Exception:
                    redirect_ips = []
                
                redirect_url = Url(
                    url=parsed_redirect.get('url') or '',
                    hostname=parsed_redirect.get('hostname') or '',
                    http_status_code=redirect.get("http_status_code"),
                    port=parsed_redirect.get('port'),
                    scheme=parsed_redirect.get('scheme') or '',
                    path=parsed_redirect.get('path') or '',
                    ips=redirect_ips
                )
                urls.append(redirect_url)
        if len(redirect_chain) > 0:
            urlObj.redirect_chain = redirect_chain
        if item.get("final_url"):
            final_url_str = item.get("final_url")
            if final_url_str:
                parsed_final_url = parse_url(final_url_str)
                if parsed_final_url:  # Check if parse_url returned a valid dict
                    # Resolve the ips for the final url
                    try:
                        hostname = parsed_final_url.get('hostname')
                        if hostname:
                            records = dns.resolver.resolve(hostname, 'A')
                            final_ips = [str(record.address) for record in records.rrset] if records.rrset else []
                        else:
                            final_ips = []
                    except Exception:
                        final_ips = []
                    
                    final_url = Url(
                        url=parsed_final_url.get('url') or '',
                        hostname=parsed_final_url.get('hostname') or '',
                        port=parsed_final_url.get('port'),
                        scheme=parsed_final_url.get('scheme') or '',
                        path=parsed_final_url.get('path') or '',
                        ips=final_ips,
                    )
                    urls.append(final_url)
        # Get IP addresses for all domains
        #ip_addresses = item.get("a", [])
        #logger.info(f"Created IP addresses: {ip_addresses}")
        
        
        
        # # Ensure hostname is lowercase
        # if hostname:
        #     hostname = hostname.lower()
            
        # logger.debug(f"Processing TLS host: {hostname}")
        
        # if hostname and not self._is_ip_address(hostname):
        #     # Get CNAME and ensure it's lowercase
        #     cname = item.get("cname", [])
        #     if cname:
        #         cname = cname[0].lower()
        #     else:
        #         cname = None
        #     logger.debug(f"Found CNAME: {cname}")
            
        #     # Create Domain object for main host with IPs
        #     domain = Domain(
        #         name=hostname,
        #         ip=ip_addresses,  # Only associate IPs with the main domain
        #         cname=cname
        #     )
        #     logger.debug(f"Created domain object for host: {host}")
        #     domains.append(domain)
        
        # Process TLS certificate
        tls_data = item.get("tls", {})
        if tls_data:
            certificate = Certificate(
                subject_dn=item.get("tls", {}).get("subject_dn", ""),
                subject_cn=item.get("tls", {}).get("subject_cn", ""),
                subject_alternative_names=item.get("tls", {}).get("subject_an", []),
                valid_from=item.get("tls", {}).get("not_before", ""),
                valid_until=item.get("tls", {}).get("not_after", ""),
                issuer_dn=item.get("tls", {}).get("issuer_dn", ""),
                issuer_cn=item.get("tls", {}).get("issuer_cn", ""),
                issuer_organization=item.get("tls", {}).get("issuer_org", []),
                serial_number=item.get("tls", {}).get("serial", ""),
                fingerprint_hash=item.get("tls", {}).get("fingerprint_hash", {}).get("sha256", "")
            )
            certificates.append(certificate)
            urlObj.certificate_serial = certificate.serial_number
        # Process TLS certificate alternate names

            cert_names = tls_data.get("subject_an", [])
            if cert_names:
                
                # Create domain objects for each alternate name without IPs
                for cert_name in cert_names:
                    # Skip wildcards, IP addresses, and the main host
                    if cert_name.startswith("*.") or self._is_ip_address(cert_name) or cert_name == host:
                        continue
                        
                    alt_domain = Domain(
                        name=cert_name,
                        ip=[],  # No IPs for alternate names
                        cname=None  # No CNAME for alternate names from cert
                    )
                    domains.append(alt_domain)
        # Add IPs (provenance for API scope when target was a hostname, not raw IP)
        for ip in item.get("a", []):
            ips.append(Ip(ip=ip, discovered_via_domain=ip_discovered_via))
    
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