#!/usr/bin/env python3
"""
Generate nuclei templates tree JSON file
This script generates a complete tree structure of the nuclei templates repository
and saves it to /opt/nuclei-templates-tree.json for faster API responses.
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def count_folders(tree: Dict[str, Any]) -> int:
    """Count folders in tree structure"""
    if not tree:
        return 0
    if tree.get("type") == "directory":
        return 1 + sum(count_folders(child) for child in tree.get("children", []))
    return 0

def count_files(tree: Dict[str, Any]) -> int:
    """Count files in tree structure"""
    if not tree:
        return 0
    if tree.get("type") == "file":
        return 1
    elif tree.get("type") == "directory":
        return sum(count_files(child) for child in tree.get("children", []))
    return 0

def extract_template_info(template_file: Path) -> Dict[str, Any]:
    """Extract basic information from a nuclei template file"""
    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse YAML
        template_data = yaml.safe_load(content)
        
        if not template_data:
            return {"name": template_file.name, "error": "Empty or invalid YAML"}
        
        # Ensure template_data is a dictionary
        if not isinstance(template_data, dict):
            return {"name": template_file.name, "error": "Template data is not a dictionary"}
        
        # Extract basic info with safe navigation
        info = {
            "id": template_data.get("id", ""),
            "name": template_data.get("info", {}).get("name", template_file.name) if isinstance(template_data.get("info"), dict) else template_file.name,
            "author": template_data.get("info", {}).get("author", "") if isinstance(template_data.get("info"), dict) else "",
            "severity": template_data.get("info", {}).get("severity", "") if isinstance(template_data.get("info"), dict) else "",
            "description": template_data.get("info", {}).get("description", "") if isinstance(template_data.get("info"), dict) else "",
            "tags": template_data.get("info", {}).get("tags", []) if isinstance(template_data.get("info"), dict) else [],
            "reference": template_data.get("info", {}).get("reference", []) if isinstance(template_data.get("info"), dict) else [],
            "classification": template_data.get("info", {}).get("classification", {}) if isinstance(template_data.get("info"), dict) else {}
        }
        
        return info
        
    except Exception as e:
        return {
            "name": template_file.name,
            "error": f"Failed to parse template: {str(e)}"
        }

def build_tree(path: Path) -> Optional[Dict[str, Any]]:
    """Recursively build tree structure"""
    try:
        if path.is_file():
            if path.suffix in ['.yaml', '.yml']:
                try:
                    template_info = extract_template_info(path)
                    return {
                        "type": "file",
                        "name": path.name,
                        "template": template_info
                    }
                except Exception as e:
                    logger.warning(f"Error processing template file {path}: {e}")
                    return {
                        "type": "file",
                        "name": path.name,
                        "error": str(e)
                    }
            else:
                return None
        elif path.is_dir():
            children = []
            try:
                for child in sorted(path.iterdir()):
                    if not child.name.startswith('.'):
                        child_tree = build_tree(child)
                        if child_tree:
                            children.append(child_tree)
            except Exception as e:
                logger.warning(f"Error reading directory {path}: {e}")
                children = []
            
            return {
                "type": "directory",
                "name": path.name,
                "children": children,
                "file_count": sum(count_files(child) for child in children),
                "folder_count": sum(count_folders(child) for child in children)
            }
        return None
    except Exception as e:
        logger.warning(f"Error building tree for {path}: {e}")
        return None

def generate_templates_tree(repo_path: str = "/opt/nuclei-templates") -> Dict[str, Any]:
    """Generate the complete tree structure of templates"""
    if not os.path.exists(repo_path):
        return {"error": "Repository not found"}
    
    try:
        tree = build_tree(Path(repo_path))
        if tree is None:
            return {"error": "Failed to build tree structure"}
        return tree
    except Exception as e:
        logger.error(f"Error building templates tree: {e}")
        return {"error": f"Failed to build tree structure: {str(e)}"}

def main():
    """Main function to generate and save the tree JSON"""
    repo_path = "/opt/nuclei-templates"
    output_path = "/opt/nuclei-templates-tree.json"
    
    logger.info("Starting nuclei templates tree generation...")
    
    # Check if repository exists
    if not os.path.exists(repo_path):
        logger.error(f"Repository not found at {repo_path}")
        return 1
    
    # Generate tree
    logger.info("Generating tree structure...")
    tree = generate_templates_tree(repo_path)
    
    if "error" in tree:
        logger.error(f"Failed to generate tree: {tree['error']}")
        return 1
    
    # Save to JSON file
    logger.info(f"Saving tree to {output_path}...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(tree, f, indent=2, ensure_ascii=False)
        
        # Get file size for logging
        file_size = os.path.getsize(output_path)
        logger.info(f"Tree saved successfully! File size: {file_size:,} bytes")
        
        # Count total templates for verification
        def count_templates_in_tree(tree_node):
            if tree_node.get("type") == "file":
                return 1
            elif tree_node.get("type") == "directory":
                return sum(count_templates_in_tree(child) for child in tree_node.get("children", []))
            return 0
        
        total_templates = count_templates_in_tree(tree)
        logger.info(f"Total templates in tree: {total_templates}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to save tree to {output_path}: {e}")
        return 1

if __name__ == "__main__":
    exit(main()) 