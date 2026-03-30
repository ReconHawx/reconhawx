import yaml
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

def extract_template_metadata(content: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Extract metadata from nuclei template YAML content
    
    Returns:
        Tuple of (is_valid, metadata_dict, error_message)
    """
    try:
        # Parse YAML content
        template_data = yaml.safe_load(content)
        
        if not isinstance(template_data, dict):
            return False, None, "Template content must be a valid YAML object"
        
        # Check for required fields
        if 'id' not in template_data:
            return False, None, "Template must have an 'id' field"
        
        if 'info' not in template_data:
            return False, None, "Template must have an 'info' field"
        
        info = template_data.get('info', {})
        if not isinstance(info, dict):
            return False, None, "Template 'info' field must be an object"
        

        
        # Extract metadata
        template_id = template_data.get('id', '')
        info_section = template_data.get('info', {})
        
        metadata = {
            'id': template_id,
            'name': info_section.get('name', template_id),  # Use id as fallback for name
            'author': info_section.get('author'),
            'severity': info_section.get('severity'),
            'description': info_section.get('description'),
            'tags': info_section.get('tags', []),
            'content': content
        }
        
        # Ensure tags is a list
        if not isinstance(metadata['tags'], list):
            metadata['tags'] = []
        
        # Validate severity if present
        if metadata['severity'] and metadata['severity'] not in ['low', 'medium', 'high', 'critical', 'info']:
            logger.warning(f"Unknown severity level: {metadata['severity']}")
        
        return True, metadata, None
        
    except yaml.YAMLError as e:
        return False, None, f"Invalid YAML content: {str(e)}"
    except Exception as e:
        logger.error(f"Error parsing nuclei template: {str(e)}")
        return False, None, f"Error parsing template: {str(e)}"

def validate_template_content(content: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that the content is a valid nuclei template
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, _, error_message = extract_template_metadata(content)
    return is_valid, error_message 