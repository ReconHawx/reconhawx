from typing import Dict, List, Any, Optional
import json
import logging
from .base import Task, AssetType, FindingType
from models.assets import Url, Domain, Service, Ip
from models.findings import NucleiFinding
from utils import parse_url
from urllib.parse import urlparse
import base64
import re

logger = logging.getLogger(__name__)

class NucleiScan(Task):
    name = "nuclei_scan"
    description = "Run nuclei vulnerability scanner on target"
    input_type = [AssetType.SUBDOMAIN, AssetType.IP, AssetType.URL]  # Can accept multiple input types
    output_types = [FindingType.NUCLEI, AssetType.SUBDOMAIN, AssetType.IP, AssetType.SERVICE, AssetType.URL]  # Can output multiple asset types

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target,
            "params": params
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def _parse_matched_at_ip_port(self, matched_at: str) -> Optional[tuple]:
        """Parse ip:port pattern from matched_at field. Returns (ip, port) tuple or None."""
        if not matched_at:
            return None
        
        # Pattern to match ip:port format
        # Supports both IPv4 and IPv6 addresses
        ip_port_pattern = r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[?[0-9a-fA-F:]+]?):(\d+)$'
        match = re.match(ip_port_pattern, matched_at.strip())
        
        if match:
            ip = match.group(1)
            port = int(match.group(2))
            return (ip, port)
        
        return None
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate nuclei command for the given input"""
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]
        
        # Use here document to properly handle newlines
        targets_text = '\n'.join(targets_to_process)
        
        cmd_args = params.get("cmd_args") if params else None
        template = params.get("template", {}) if params else {}
        nuclei_command = "nuclei -or -silent -j"
        # Handle base templates (official categories, folders, or specific templates)
        for template_path in template.get("official", []):
            nuclei_command += f" -t {template_path}"
        
        # Handle custom templates
        for t in template.get("custom", []):
            nuclei_command += f" -t http://api.recon.svc.cluster.local:8000/nuclei-templates/raw/{t}.yaml"
        
        if cmd_args:
            nuclei_command += f" {' '.join(cmd_args)}"
        command = f"cat << 'EOF' | {nuclei_command}\n{targets_text}\nEOF"
        logger.debug(f"Generated nuclei command: {command}")
        return command

    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse nuclei JSON output into multiple asset types"""
        findings = []
        services = []
        urls = []
        domains = set()  # Use set to deduplicate domains
        ips = set()      # Use set to deduplicate IPs
        url_tech_accumulator = {}  # Accumulate technologies per URL

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)
        lines = normalized_output.splitlines()
        logger.debug(f"Processing {len(lines)} lines from nuclei output")
        
        for i, line in enumerate(lines):
            if not line.strip() or line.startswith('stderr:'):
                continue
                
            try:
                finding = json.loads(line)
                # Extract hostname/domain from URL
                hostname = finding.get('host', '')
                url = finding.get('url')
                scheme = finding.get('scheme', "")
                port = finding.get('port', "")

                # Try parse_url for scheme URLs (handles IPs; is_valid_url rejects them)
                if url and url.startswith(('http://', 'https://')):
                    parsed_url = parse_url(url)
                    if parsed_url:
                        hostname = parsed_url.get("hostname")
                        scheme = parsed_url.get("scheme")
                        port = parsed_url.get("port")
                elif ":" in (url or "") and not (url or "").startswith(('http://', 'https://')):
                    # Bare host:port format (e.g. 192.168.1.1:8080)
                    hostname = url.split(":")[0]
                    port = url.split(":")[1]
                # Create nuclei finding
                template_id = finding.get('template-id', '')
                info_section = finding.get('info', {})
                name_value = info_section.get('name', template_id or 'Unknown Template')
                
                # Prepare all fields for NucleiFinding creation
                finding_data = {
                    'url': url,
                    'matched_at': finding.get('matched-at', ''),
                    'matcher_name': finding.get('matcher-name', ''),
                    'type': finding.get('type', ''),
                    'ip': finding.get('ip', ''),
                    'port': int(port) if port and str(port).isdigit() else None,
                    'scheme': scheme.lower() if scheme else None,
                    'template_id': template_id,
                    'template_path': finding.get('template',''),
                    'name': name_value,
                    'severity': info_section.get('severity', 'info'),
                    'extracted_results': finding.get('extracted-results', []),
                    'protocol': finding.get('protocol', None),
                    'tags': finding.get('info', {}).get('tags', []),
                    'description': finding.get('info', {}).get('description', ''),
                    'hostname': hostname,  # Add extracted hostname (already lowercase)
                }
                
                # Add protocol information
                if finding.get('type') == "http":
                    finding_data['protocol'] = "tcp"
                elif finding.get('type') == "tcp":
                    finding_data['protocol'] = "tcp"
                    if "-detect" in finding.get('template-id'):
                        finding_data['scheme'] = finding.get('template-id').replace("-detect", "")
                nuclei_finding = NucleiFinding(**finding_data)

                findings.append(nuclei_finding)

                # Create service if we have a valid IP address from the finding
                if nuclei_finding.ip:
                    service = Service(
                        ip=nuclei_finding.ip,
                        port=nuclei_finding.port or 0,
                        protocol=nuclei_finding.protocol or "",
                        service_name=nuclei_finding.scheme or "",
                        banner=None,
                        program_name=nuclei_finding.program_name
                    )
                    services.append(service)
                
                # Also create service if matched_at contains ip:port pattern
                matched_at_ip_port = self._parse_matched_at_ip_port(nuclei_finding.matched_at)
                if matched_at_ip_port:
                    matched_ip, matched_port = matched_at_ip_port
                    # Only create service if we don't already have one for this IP/port combination
                    existing_service = any(
                        s.ip == matched_ip and s.port == matched_port 
                        for s in services
                    )
                    if not existing_service:
                        service = Service(
                            ip=matched_ip,
                            port=matched_port,
                            protocol=nuclei_finding.protocol or "tcp",
                            service_name=nuclei_finding.scheme or "",
                            banner=None,
                            program_name=nuclei_finding.program_name
                        )
                        services.append(service)
                        logger.debug(f"Created service from matched_at pattern: {matched_ip}:{matched_port}")
                # Technology detection
                if finding.get('template','').startswith("http/technologies"): # or finding.get('template','') == "http/technologies/tech-detect.yaml":
                    if nuclei_finding.matcher_name and nuclei_finding.url:
                        parsed_url = parse_url(nuclei_finding.url)
                        if parsed_url:
                            logger.debug(f"Parsed URL: {parsed_url}")
                            if nuclei_finding.scheme == "":
                                if nuclei_finding.url and nuclei_finding.url.startswith("http"):
                                    url_scheme = parsed_url.get("scheme", "")
                            else:
                                url_scheme = nuclei_finding.scheme or ""
                            url_techs = [nuclei_finding.matcher_name]
                        else:
                            logger.debug(f"No parsed URL: {nuclei_finding.url}")
                            url_techs = [nuclei_finding.template_id.replace("-detect", "").replace("-version", "")]
                            parsed_url = {"url": "", "path": ""}
                            url_scheme = ""
                    else:
                        url_techs = [nuclei_finding.template_id.replace("-detect", "").replace("-version", "")]
                        parsed_url = {"url": "", "path": ""}
                        url_scheme = ""
                    # Accumulate technologies per URL instead of creating separate objects
                    if url or nuclei_finding.hostname:
                        # Use the nuclei_finding.url as the key to group technologies
                        
                        url_key = url if url else nuclei_finding.hostname.lower()
                        if url_key not in url_tech_accumulator:
                            url_tech_accumulator[url_key] = {
                                'url': url,
                                'hostname': nuclei_finding.hostname,
                                'port': nuclei_finding.port,
                                'scheme': url_scheme,
                                'path': parsed_url.get("path", ""),
                                'technologies': []
                            }

                        # Add technology if not already present
                        if url_techs[0] not in url_tech_accumulator[url_key]['technologies']:
                            url_tech_accumulator[url_key]['technologies'].append(url_techs[0])
                
            except json.JSONDecodeError:
                logger.debug(f"Skipping non-JSON line: {line[:100]}...")  # Log only first 100 chars
                continue
            except ValueError as e:
                logger.error(f"Error processing finding: {str(e)}")
                logger.error(f"Finding data that caused error: {finding}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error processing finding: {str(e)}")
                logger.error(f"Finding data that caused error: {finding}")
                logger.error(f"Error type: {type(e).__name__}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                continue
                
        # Create URL objects from accumulated technologies
        for url_key, url_data in url_tech_accumulator.items():
            url = Url(
                url=url_data['url'],
                hostname=url_data['hostname'],
                port=url_data['port'],
                scheme=url_data['scheme'],
                path=url_data['path'],
                technologies=url_data['technologies']
            )
            urls.append(url)

        # Convert domains and IPs to their respective models
        domain_objects = [Domain(name=d).to_dict() for d in domains]
        ip_objects = [Ip(ip=i).to_dict() for i in ips]

        logger.debug(f"Parse output complete. Results: {len(findings)} findings, {len(domain_objects)} domains, {len(ip_objects)} IPs, {len(services)} services, {len(urls)} URLs")

        return {
            FindingType.NUCLEI: findings,
            AssetType.SUBDOMAIN: domain_objects,
            AssetType.IP: ip_objects,
            AssetType.SERVICE: services,
            AssetType.URL: urls
        }

    # ============================================================================
    # PROXY SUPPORT METHODS - Enable AWS API Gateway proxying via FireProx
    # ============================================================================

    def supports_proxy(self) -> bool:
        """
        NucleiScan supports AWS API Gateway proxying via FireProx for URL targets.

        Note: Only URL inputs will be proxied. Domains and IPs cannot be proxied
        through API Gateway and will be passed through unchanged.

        Returns:
            bool: True (this task supports proxying)
        """
        return True

    def extract_proxy_targets(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """
        Extract URLs that need proxying from input data.

        For nuclei_scan, only URL inputs should be proxied. Domains and IPs
        cannot be proxied through API Gateway and will be filtered out.

        Args:
            input_data: Task input data (list of subdomains/IPs/URLs or single value)
            params: Task parameters

        Returns:
            List of URLs to create proxies for
        """
        from utils import get_valid_urls

        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]

        # Only proxy URL inputs (filter out domains and IPs)
        urls_to_proxy = get_valid_urls(targets_to_process)

        # Remove trailing slashes for consistency
        urls_to_proxy = [url.rstrip('/') for url in urls_to_proxy]

        logger.info(f"Extracted {len(urls_to_proxy)} URLs for proxying (filtered from {len(targets_to_process)} total targets)")
        return urls_to_proxy

    def replace_targets_with_proxies(self, command: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace original URLs with proxy URLs in nuclei commands.

        Nuclei uses heredoc format:
        cat << 'EOF' | nuclei ...
        target1
        target2
        target3
        EOF

        We need to replace URLs in the heredoc content while preserving
        domains and IPs unchanged.

        Args:
            command: Original nuclei command string
            url_mapping: Dict mapping original URLs to proxy URLs

        Returns:
            Modified command with proxied URLs
        """
        # Extract the heredoc content (between first newline and EOF)
        parts = command.split('\n', 1)
        if len(parts) < 2:
            logger.warning("Command does not contain heredoc format, skipping proxy replacement")
            return command

        header = parts[0]  # cat << 'EOF' | nuclei ...
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
                from urllib.parse import urlparse, urlunparse
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
        logger.debug("Replaced URLs in nuclei command (heredoc format)")
        return reconstructed_command

    def replace_proxies_in_output(self, output: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace proxy URLs back to original URLs in nuclei output using hostname-based replacement.

        This function:
        1. Replaces proxy hostnames with original hostnames
        2. Removes the /fireprox path prefix from all URLs

        Args:
            output: Raw nuclei output (JSON lines)
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
        # This handles both: "url": "https://host/fireprox/path" and "matched-at": "https://host:443/fireprox/path"
        modified_output = re.sub(r'/fireprox(/|")', r'\1', modified_output)

        logger.debug(f"Replaced proxy URLs in nuclei output: {len(modified_output)} chars")
        return modified_output 