import logging
import json
from typing import Dict, List, Any, Optional
import base64
from .base import Task, AssetType
from models.assets import Service, Ip
from utils import get_valid_ips
import xml.etree.ElementTree as ET
import os
import requests
logger = logging.getLogger(__name__)

class PortScan(Task):
    name = "port_scan"
    description = "Scan ports on a target. Accepts IP addresses for port range scanning or IP:PORT for specific port scanning"
    input_type = AssetType.STRING
    output_types = [AssetType.SERVICE]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    

    def get_ips_with_provider(self, program_name: str) -> List[str]:
        """Get IPs with provider from api"""
        try:
            logger.info(f"Getting IPs with provider for program: {program_name}")
            api_url = os.getenv("API_URL", "http://api:8000")
            query_data = {"program":program_name,"sort_by":"ip_address","sort_dir":"asc","page":1,"page_size":10000,"has_service_provider":True}
            headers = {}
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
            if internal_api_key:
                headers['Authorization'] = f'Bearer {internal_api_key}'
            else:
                logger.warning("No internal API key found for IP query")
            response = requests.post(f"{api_url}/assets/ip/search", json=query_data, headers=headers)
            if response.status_code == 200:
                if len(response.json().get("items", [])) > 0:
                    return [i.get("ip_address") for i in response.json().get("items", [])]
                else:
                    return []
        except Exception as e:
            logger.error(f"Error getting IPs with provider from api: {str(e)}")
            return []

    def get_ip_info(self, ip: str) -> Dict[str, Any]:
        """Fetch IP information from api synchronously (legacy method)"""
        try:
            api_url = os.getenv("API_URL", "http://api:8000")
            query_data = {"exact_match":ip,"sort_by":"ip_address","sort_dir":"asc","page":1,"page_size":1}
            
            headers = {}
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
            if internal_api_key:
                headers['Authorization'] = f'Bearer {internal_api_key}'
            else:
                logger.warning("No internal API key found for IP query")
            
            logger.debug(f"Making IP query API request to: {api_url}/assets/ip/search")
            logger.debug(f"Request headers: {headers}")
            
            response = requests.post(f"{api_url}/assets/ip/search", json=query_data, headers=headers)
            logger.debug(f"IP query API response: {response}")
            logger.debug(f"IP query API response status: {response.status_code}")
            if response.status_code != 200:
                logger.debug(f"IP query API response text: {response.text[:200]}...")
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                return items[0] if items else {}  # Return first item or empty dict
            return {}
        except Exception as e:
            logger.error(f"Error fetching IP info for {ip}: {str(e)}")
            return {}
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate nmap command for the given input"""
        # Process input data to handle both IP and IP:PORT formats
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]
        
        # Separate IPs and IP:PORT targets
        ip_targets = []
        ip_port_targets = []
        
        for target in targets_to_process:
            target_str = str(target).strip()
            if ':' in target_str and not target_str.startswith('['):  # IPv6 addresses start with [
                # Check if it's IP:PORT format
                parts = target_str.split(':')
                if len(parts) == 2 and parts[1].isdigit():
                    ip_port_targets.append(target_str)
                    continue
            
            # Try to extract valid IPs from the target
            valid_ips = get_valid_ips([target_str])
            if valid_ips:
                ip_targets.extend(valid_ips)
        
        # Filter out cloud provider IPs for IP-only targets
        filtered_ips = []
        ip_with_provider = self.get_ips_with_provider(os.getenv("PROGRAM_NAME"))
        for ip in ip_targets:
            if ip in ip_with_provider:
                logger.info(f"Skipping IP {ip} as it belongs to cloud or waf provider")
            else:
                filtered_ips.append(ip)
        
        # Filter out cloud provider IPs for IP:PORT targets
        filtered_ip_ports = []
        for ip_port in ip_port_targets:
            ip_part = ip_port.split(':')[0]
            if ip_part in ip_with_provider:
                logger.info(f"Skipping IP:PORT {ip_port} as IP belongs to cloud or waf provider")
            else:
                filtered_ip_ports.append(ip_port)
        
        if not filtered_ips and not filtered_ip_ports:
            logger.warning("No valid targets to scan after filtering cloud providers")
            return []
        
        # Build combined target list: IPs (port range) + IP:PORT (specific ports)
        targets = list(filtered_ips) + list(filtered_ip_ports)
        targets_text = '\n'.join(targets)
        command = f"cat << 'EOF' | python3 /workspace/port_scan_wrapper.py\n{targets_text}\nEOF"
        return [command]
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse output into Service assets. Supports JSON (port_scan_wrapper) and nmap XML (fallback)."""
        services = []
        ips = []

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        if not normalized_output:
            logger.warning("Empty output received")
            return {
                AssetType.SERVICE: [],
            }

        stripped = normalized_output.strip()

        # Try JSON format first (port_scan_wrapper output)
        if stripped.startswith('{'):
            try:
                data = json.loads(stripped)
                svc_list = data.get("services", [])
                ip_list = data.get("ips", [])
                seen_ips = set()
                for s in svc_list:
                    ip = s.get("ip")
                    port = s.get("port")
                    if ip is None or port is None:
                        continue
                    if ip not in seen_ips:
                        seen_ips.add(ip)
                        ips.append(Ip(ip=ip))
                    services.append(Service(
                        ip=ip,
                        port=int(port),
                        protocol=s.get("protocol", "tcp"),
                        service_name=s.get("service_name", "unknown"),
                        banner=s.get("banner"),
                        nerva_metadata=s.get("nerva_metadata"),
                    ))
                # Ensure all IPs from ips list are represented
                for ip_str in ip_list:
                    if ip_str not in seen_ips:
                        ips.append(Ip(ip=ip_str))
                return {
                    AssetType.SERVICE: services,
                    AssetType.IP: ips,
                }
            except json.JSONDecodeError:
                pass  # Fall through to nmap XML

        # Fallback: nmap XML format
        try:
            root = ET.fromstring(normalized_output)
            hosts = root.findall('.//host')
            if not hosts:
                logger.warning("No hosts found in nmap output")
                return {AssetType.SERVICE: [], AssetType.IP: []}

            for host in hosts:
                address = host.find('.//address[@addrtype="ipv4"]')
                if address is None:
                    continue
                target_ip = address.get('addr')
                if target_ip is None:
                    continue

                for port in host.findall('.//port'):
                    port_id = port.get('portid')
                    protocol = port.get('protocol')
                    if port_id is None or protocol is None:
                        continue
                    state = port.find('state')
                    if state is None or state.get('state') != 'open':
                        continue
                    service = port.find('service')
                    service_name = service.get('name') if service is not None else "unknown"
                    if service_name is None:
                        service_name = "unknown"
                    banner = None
                    script = port.find('.//script[@id="banner"]')
                    if script is not None:
                        banner = script.get('output')

                    ips.append(Ip(ip=target_ip))
                    services.append(Service(
                        ip=target_ip,
                        port=int(port_id),
                        protocol=protocol,
                        service_name=service_name,
                        banner=banner
                    ))

            return {
                AssetType.SERVICE: services,
                AssetType.IP: ips
            }
        except ET.ParseError as e:
            logger.error(f"Error parsing XML: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error processing port scan output: {str(e)}")
            raise