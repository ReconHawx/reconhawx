"""
Workflow processing utilities for handling variables in workflow definitions.
This module provides functionality to process workflow templates with variable values.
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def extract_variables_from_workflow(workflow_data: Dict[str, Any]) -> List[str]:
    """
    Extract variable names from workflow data using Jinja2-style template syntax.
    
    Args:
        workflow_data: The workflow definition dictionary
        
    Returns:
        List of variable names found in the workflow
    """
    variables = set()
    
    def extract_from_value(value):
        if isinstance(value, str):
            # Find all {{ variable }} patterns
            matches = re.findall(r'\{\{\s*(\w+)\s*\}\}', value)
            variables.update(matches)
        elif isinstance(value, dict):
            for v in value.values():
                extract_from_value(v)
        elif isinstance(value, list):
            for item in value:
                extract_from_value(item)
    
    # Extract from workflow data recursively
    extract_from_value(workflow_data)
    
    return list(variables)

def process_workflow_with_variables(workflow_data: Dict[str, Any], variable_values: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a workflow definition by replacing variables with their values.
    
    Args:
        workflow_data: The workflow definition dictionary
        variable_values: Dictionary mapping variable names to their values
        
    Returns:
        Processed workflow data with variables replaced
    """
    def process_value(value):
        if isinstance(value, str):
            # Replace {{ variable }} patterns with actual values
            def replace_var(match):
                var_name = match.group(1).strip()
                if var_name in variable_values:
                    return str(variable_values[var_name])
                else:
                    logger.warning(f"Variable '{var_name}' not found in provided values")
                    return match.group(0)  # Keep original if variable not found
            return re.sub(r'\{\{\s*(\w+)\s*\}\}', replace_var, value)
        elif isinstance(value, dict):
            return {k: process_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [process_value(item) for item in value]
        else:
            return value
    
    # Create a copy to avoid modifying the original
    processed_workflow = workflow_data.copy()
    
    # Process the entire workflow recursively
    processed_workflow = process_value(processed_workflow)
    
    return processed_workflow

def validate_variables(workflow_data: Dict[str, Any], variable_values: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that all required variables are provided.
    
    Args:
        workflow_data: The workflow definition dictionary
        variable_values: Dictionary mapping variable names to their values
        
    Returns:
        Dictionary with 'success' boolean and 'errors' list
    """
    required_variables = extract_variables_from_workflow(workflow_data)
    errors = []
    
    for var_name in required_variables:
        if var_name not in variable_values or variable_values[var_name] is None or variable_values[var_name] == '':
            errors.append(f"Variable '{var_name}' is required but not provided")
    
    return {
        'success': len(errors) == 0,
        'errors': errors
    } 