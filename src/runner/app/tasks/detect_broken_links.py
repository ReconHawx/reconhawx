import json
import logging
import base64
from typing import Dict, List, Any, Optional
from .base import Task, AssetType, FindingType

logger = logging.getLogger(__name__)

class DetectBrokenLinks(Task):
    name = "detect_broken_links"
    description = "Detect broken links: social media links (Facebook, Instagram, Twitter/X, LinkedIn) and general links with unregistered domains (hijackable)"
    input_type = AssetType.STRING
    output_types = [FindingType.BROKEN_LINK]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate a unique hash for the task execution"""
        hash_dict = {
            "task": self.name,
            "target": target,
            "params": params
        }
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate command to check broken links using worker script"""
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]
        
        # Filter valid URLs (must be strings and look like URLs)
        # Use dict.fromkeys to deduplicate while preserving order
        seen = set()
        valid_inputs = []
        for target in targets_to_process:
            if isinstance(target, str) and target.strip():
                url = target.strip()
                # Basic URL validation - must start with http:// or https://
                if url.startswith(('http://', 'https://')) and url not in seen:
                    seen.add(url)
                    valid_inputs.append(url)
        
        if not valid_inputs:
            logger.warning("No valid URL inputs found")
            return ""
        
        # Use here document to pipe inputs to worker script
        # Each input is on a separate line
        inputs_text = '\n'.join(valid_inputs)
        
        # Worker script reads from stdin and outputs JSON
        return f"cat << 'EOF' | python3 check_broken_links.py\n{inputs_text}\nEOF"
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse output from broken links check"""
        findings = []
        
        # Normalize output format
        normalized_output = self.normalize_output_for_parsing(output)
        
        if not normalized_output:
            logger.warning("Empty output received from broken links check")
            return {FindingType.BROKEN_LINK: []}
        
        try:
            # Parse JSON output
            if isinstance(normalized_output, str):
                # Try to parse as JSON
                try:
                    data = json.loads(normalized_output)
                    if isinstance(data, list):
                        findings = data
                    elif isinstance(data, dict):
                        findings = [data]
                except json.JSONDecodeError:
                    # If not JSON, try to find JSON in the output
                    lines = normalized_output.strip().split('\n')
                    for line in lines:
                        if line.strip().startswith('{') or line.strip().startswith('['):
                            try:
                                data = json.loads(line)
                                if isinstance(data, list):
                                    findings.extend(data)
                                elif isinstance(data, dict):
                                    findings.append(data)
                            except json.JSONDecodeError:
                                continue
            
            # Convert to finding objects
            broken_link_findings = []
            for finding_data in findings:
                if isinstance(finding_data, dict):
                    broken_link_findings.append(finding_data)
            
            logger.info(f"Parsed {len(broken_link_findings)} broken link findings")
            return {FindingType.BROKEN_LINK: broken_link_findings}
            
        except Exception as e:
            logger.error(f"Error parsing broken links output: {str(e)}")
            logger.error(f"Raw output: {normalized_output[:500]}")
            return {FindingType.BROKEN_LINK: []}

