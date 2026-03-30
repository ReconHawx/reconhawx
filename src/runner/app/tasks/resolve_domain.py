import json
import logging
from typing import Dict, List, Any, Optional
from utils.utils import get_valid_domains, is_valid_domain
from .base import Task, AssetType
from models.assets import Domain, Ip
import base64
import random
logger = logging.getLogger(__name__)

class ResolveDomain(Task):
    name = "resolve_domain"
    description = "Resolves domain names to IP addresses using dnsx"
    input_type = AssetType.STRING
    output_types = [AssetType.SUBDOMAIN, AssetType.IP]
    
    # Timeout and execution threshold are now handled by the base Task class
    # which fetches parameters from the API

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
        valid_domains = []

        # Select 3 random resolvers from the file
        with open("files/resolvers.txt", 'r') as file:
            resolvers = file.read().splitlines()
        random_resolvers = random.sample(resolvers, 3)
        ",".join(random_resolvers)
        
        # Handle both string and list inputs
        domains_to_process = input_data if isinstance(input_data, list) else [input_data]
        valid_domains = get_valid_domains(domains_to_process)
        
        if not valid_domains:
            logger.warning("No valid domains found in input")
            return "echo ''"
            
        # Use here document to properly handle newlines
        domains_text = '\n'.join(valid_domains)
        return f"cat << 'EOF' | python3 dnsx_wrapper.py\n{domains_text}\nEOF"
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse dnsx output into Domain and IP assets"""
        domains = []
        ips = set()  # Use set to deduplicate IPs

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        # Process the output based on its format
        if not normalized_output:
            logger.warning("Empty output received")
            return {AssetType.SUBDOMAIN: [], AssetType.IP: []}

        output_json = json.loads(normalized_output)
        for domain, data in output_json.items():
            if domain and data.get("dnsx", None):
                #logger.info(f"Processing {domain}: {data}")
                self._process_data(domain, data, domains, ips)
        # Convert IPs set to list
        ip_list = list(ips)
        
        
        logger.info(f"Found {len(domains)} domains and {len(ip_list)} unique IPs")
        
        return {
            AssetType.SUBDOMAIN: domains,
            AssetType.IP: ip_list
        }
    
    def _process_data(self, input_domain, data, domains, ips):
        """Process a single data entry and add to domains and IPs collections"""
        try:
            dnsx_data = data.get("dnsx")
            # if dnsx_data.get('status_code', '') in ['REFUSED', 'NXSUBDOMAIN']:
            #     return
            # Extract domain information and ensure it's lowercase
            domain_name = dnsx_data.get('host', '').lower() if dnsx_data.get('host') else ''
            is_wildcard = data.get("is_wildcard")
            wildcard_type = data.get("wildcard_type")
        except Exception:
            logger.warning(f"Invalid data: {data}, skipping...")
            return

        if domain_name:
            if is_valid_domain(domain_name):
                # Extract IP addresses as strings for the domain
                ip_addresses = []
                
                # Create IP objects for the IP asset type
                for addr in dnsx_data.get('a', []):
                    # Add the string IP address to the domain's IP list
                    ip_addresses.append(addr)
                    
                    # Create and add IP object to the unique IPs set (provenance for API scope check)
                    ip_obj = Ip(ip=addr, discovered_via_domain=domain_name)
                    ips.add(ip_obj)
                
                # Get first CNAME and ensure it's lowercase
                cname = dnsx_data.get('cname', [])
                if cname:
                    cname = cname[0].lower()
                else:
                    cname = None
                
                # Only add domain if it has A records or CNAME record
                # Skip domains that don't resolve to anything
                if ip_addresses or cname:
                    # Create Domain object with string IP addresses
                    domain = Domain(
                        name=domain_name,
                        ip=ip_addresses,
                        cname_record=cname,
                        is_wildcard=is_wildcard,
                        wildcard_type=wildcard_type
                    )
                    domains.append(domain)
                else:
                    logger.debug(f"Skipping {domain_name} - no A or CNAME records")