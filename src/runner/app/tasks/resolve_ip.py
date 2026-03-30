import json
import logging
from typing import Dict, List, Any, Optional
import base64
from .base import Task, AssetType
from models.assets import Domain, Ip
import random
logger = logging.getLogger(__name__)

class ResolveIP(Task):
    name = "resolve_ip"
    description = "Resolves IP addresses to domain names using dnsx"
    input_type = AssetType.STRING
    output_types = [AssetType.SUBDOMAIN, AssetType.IP]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate the dnsx command for domain resolution"""
        # Filter out error messages and invalid domains
        valid_ips = []

        # Select 3 random resolvers from the file
        with open("files/resolvers.txt", 'r') as file:
            resolvers = file.read().splitlines()
        random_resolvers = random.sample(resolvers, 3)
        ",".join(random_resolvers)


        # Handle both string and list inputs
        if isinstance(input_data, list):
            # If input_data is already a list of IPs, process each element
            for item in input_data:
                if isinstance(item, str):
                    # Split the string on newlines and spaces to handle multiple IPs in one string
                    for ip in item.replace('\n', ' ').split():
                        ip = ip.strip()
                        if ip:
                            try:
                                octets = ip.split('.')
                                if len(octets) == 4 and all(0 <= int(octet) <= 255 for octet in octets):
                                    valid_ips.append(ip)
                            except ValueError:
                                logger.warning(f"Invalid IP address: {ip}")
                elif isinstance(item, list):
                    # Handle nested list case
                    logger.warning(f"Unexpected nested list in input_data: {item}")
                    for nested_item in item:
                        ip = str(nested_item).strip()
                        try:
                            octets = ip.split('.')
                            if len(octets) == 4 and all(0 <= int(octet) <= 255 for octet in octets):
                                valid_ips.append(ip)
                        except ValueError:
                            logger.warning(f"Invalid IP address: {ip}")
                else:
                    # Handle other types
                    ip = str(item).strip()
                    try:
                        octets = ip.split('.')
                        if len(octets) == 4 and all(0 <= int(octet) <= 255 for octet in octets):
                            valid_ips.append(ip)
                    except ValueError:
                        logger.warning(f"Invalid IP address: {ip}")
        else:
            # Handle single string input
            input_str = str(input_data)
            for ip in input_str.replace('\n', ' ').split():
                ip = ip.strip()
                if ip:
                    try:
                        octets = ip.split('.')
                        if len(octets) == 4 and all(0 <= int(octet) <= 255 for octet in octets):
                            valid_ips.append(ip)
                        else:
                            logger.warning(f"Invalid IP format in string: {ip}")
                    except ValueError:
                        logger.warning(f"Invalid IP address in string: {ip}")


        if not valid_ips:
            logger.warning("No valid IPs found in input")
            return "echo ''"

        # Create a robust command using a here document to avoid quoting issues
        ips_text = '\n'.join(valid_ips)
        command = f"cat << 'EOF' | python3 dnsx_wrapper.py\n{ips_text}\nEOF"
        return command
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse dnsx output into Domain and IP assets"""
        domains = []
        ips = set()  # Use set to deduplicate IPs

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        # Parse the normalized output
        try:
            output_json = json.loads(normalized_output)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON output: {e}")
            return {
                AssetType.SUBDOMAIN: domains,
                AssetType.IP: list(ips)
            }

        for ip, data in output_json.items():
            if ip and isinstance(data, dict) and data.get("dnsx", None):
                self._process_data(ip, data, domains, ips)



        # Convert IPs set to list
        ip_list = list(ips)
        logger.info(f"Found {len(domains)} domains and {len(ip_list)} unique IPs")

        return {
            AssetType.SUBDOMAIN: domains,
            AssetType.IP: ip_list
        }
    
    def _process_data(self, input_ip, data, domains, ips):
        """Process a single data entry and add to domains and IPs collections"""

        # Ensure data is a dictionary
        if not isinstance(data, dict):
            logger.error(f"Data for IP {input_ip} is not a dictionary: {type(data)} - {data}")
            return

        dnsx_data = data.get("dnsx")
        if not dnsx_data:
            logger.warning(f"No dnsx data found for IP {input_ip}")
            return

        # Ensure dnsx_data is a dictionary
        if not isinstance(dnsx_data, dict):
            logger.error(f"DNSX data for IP {input_ip} is not a dictionary: {type(dnsx_data)} - {dnsx_data}")
            return

        # Extract IP information
        ip_address = dnsx_data.get('host', '')
        if not ip_address:
            logger.warning(f"No host IP found in dnsx data for {input_ip}")
            return

        # Extract PTR records (domain names) for the IP
        ptr_records = dnsx_data.get('ptr', [])
        if not isinstance(ptr_records, list):
            logger.warning(f"PTR records for IP {ip_address} is not a list: {type(ptr_records)} - {ptr_records}")
            ptr_records = []

        # Create IP object with PTR records
        ip_obj = Ip(ip=ip_address, ptr=ptr_records[0] if len(ptr_records) > 0 else None, service_provider=data.get('provider', None))
        ips.add(ip_obj)

        # Create Domain objects for each PTR record
        for domain_name in ptr_records:
            if isinstance(domain_name, str) and domain_name.strip():
                domain = Domain(
                    name=domain_name.strip(),
                    ip=[ip_address],  # List with the single IP address
                    cname=None
                )
                domains.append(domain)
            else:
                logger.warning(f"Invalid domain name in PTR records: {domain_name} (type: {type(domain_name)})")