import logging
from typing import Dict, List, Any, Optional
import base64
from .base import Task, AssetType
from utils.utils import get_valid_domains
from models.assets import Domain
logger = logging.getLogger(__name__)

class SubdomainFinder(Task):
    name = "subdomain_finder"
    description = "Finds subdomains using subfinder"
    input_type = AssetType.STRING
    output_types = [AssetType.SUBDOMAIN]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """Generate individual commands for each subdomain discovery tool"""
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]

        # Generate individual commands for each tool
        commands = []
        for target in targets_to_process:
            # Each tool gets its own command
            commands.append(f"subfinder -d {target} -silent")
            commands.append(f"echo {target} | assetfinder -subs-only")
            #commands.append(f"curl -s https://crt.sh/?q=%.{target}&output=json | jq -r '.[].name_value' 2>/dev/null | sed 's/\\*\\.//g' | sort -u")

        return commands
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse subfinder output into Domain assets"""
        domains = []

        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)

        raw_output_lines = get_valid_domains(normalized_output.strip().split('\n'))

        try:
            # Process each line as a subdomain
            for line in raw_output_lines:
                if not line.strip():
                    continue
                
                # Create Domain object for each subdomain
                domain = Domain(name=line.strip())
                domains.append(domain)
        
        except Exception as e:
            logger.error(f"Error parsing subfinder output: {e}")
        
        return {
            AssetType.SUBDOMAIN: domains
        } 