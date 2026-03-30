#!/usr/bin/env python3
"""
Test script for all runner/worker tasks.

Usage:
    python test_tasks.py <task_name> <target> [asset_types]

Examples:
    python test_tasks.py test_http "https://example.com"
    python test_tasks.py nuclei_scan "example.com" url,domain
    python test_tasks.py port_scan "192.168.1.1" service
    python test_tasks.py resolve_domain "example.com" domain,ip
    python test_tasks.py resolve_ip "8.8.8.8" ip
    python test_tasks.py subdomain_finder "example.com" domain
    python test_tasks.py crawl_website "https://example.com" url
    python test_tasks.py fuzz_website "https://example.com" url

Asset Types:
    - domain: Domain assets
    - ip: IP address assets  
    - url: URL assets
    - service: Service assets
    - nuclei: Nuclei finding assets
    - certificate: Certificate assets
    - all: All asset types (default)
"""

import sys
import os
import logging
import subprocess
from typing import Dict, List, Any, Optional, Set

# Add the recon src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'recon', 'src'))

# Import task classes
from tasks.test_http import TestHTTP
from tasks.nuclei_scan import NucleiScan
from tasks.port_scan import PortScan
from tasks.resolve_domain import ResolveDomain
from tasks.resolve_ip import ResolveIP
from tasks.subdomain_finder import SubdomainFinder
from tasks.crawl_website import CrawlWebsite
from tasks.typosquat_detection import TyposquatDetection
from tasks.fuzz_website import FuzzWebsite
from tasks.whois_domain_check import WhoisDomainCheck
from tasks.base import AssetType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskTester:
    """Test class for running and testing all tasks"""
    
    def __init__(self):
        self.tasks = {
            'test_http': TestHTTP(),
            'nuclei_scan': NucleiScan(),
            'port_scan': PortScan(),
            'resolve_domain': ResolveDomain(),
            'resolve_ip': ResolveIP(),
            'subdomain_finder': SubdomainFinder(),
            'crawl_website': CrawlWebsite(),
            'typosquat_detection': TyposquatDetection(),
            'fuzz_website': FuzzWebsite(),
            'whois_domain_check': WhoisDomainCheck(),
        }
        
        # Asset type mapping
        self.asset_type_map = {
            'domain': AssetType.SUBDOMAIN,
            'ip': AssetType.IP,
            'url': AssetType.URL,
            'service': AssetType.SERVICE,
            'nuclei': AssetType.NUCLEI,
            'certificate': AssetType.CERTIFICATE,
            'typosquat': AssetType.TYPOSQUAT,
            'apex_domain': AssetType.APEX_DOMAIN,
            'all': None  # Special case for all types
        }
    
    def get_available_tasks(self) -> List[str]:
        """Return list of available task names"""
        return list(self.tasks.keys())
    
    def get_available_asset_types(self) -> List[str]:
        """Return list of available asset type names"""
        return list(self.asset_type_map.keys())
    
    def parse_asset_types(self, asset_types_str: str) -> Set[AssetType]:
        """
        Parse asset types string into a set of AssetType enums
        
        Args:
            asset_types_str: Comma-separated string of asset types
            
        Returns:
            Set of AssetType enums to include
        """
        if not asset_types_str or asset_types_str.lower() == 'all':
            return set()  # Empty set means all types
        
        asset_types = set()
        for asset_type_name in asset_types_str.lower().split(','):
            asset_type_name = asset_type_name.strip()
            if asset_type_name in self.asset_type_map:
                asset_type = self.asset_type_map[asset_type_name]
                if asset_type:  # Skip 'all' which maps to None
                    asset_types.add(asset_type)
            else:
                logger.warning(f"Unknown asset type: {asset_type_name}")
        
        return asset_types
    
    def test_task(self, task_name: str, target: str, asset_types: Optional[Set[AssetType]] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Test a specific task with a given target
        
        Args:
            task_name: Name of the task to test
            target: Target to test against
            asset_types: Set of asset types to include (empty set means all)
            params: Optional parameters for the task
            
        Returns:
            Dictionary containing test results
        """
        if task_name not in self.tasks:
            raise ValueError(f"Unknown task: {task_name}. Available tasks: {self.get_available_tasks()}")
        
        task = self.tasks[task_name]
        params = params or {}
        asset_types = asset_types or set()
        
        logger.info(f"Testing task: {task_name}")
        logger.info(f"Target: {target}")
        logger.info(f"Asset types to include: {[at.value for at in asset_types] if asset_types else 'all'}")
        logger.info(f"Parameters: {params}")
        
        try:
            # Get the command that would be executed
            command = task.get_command(target, params)
            logger.info(f"Generated command: {command}")
            
            # Execute the command and capture output
            output = self._execute_command(command)
            logger.info(f"Command output length: {len(output) if output else 0}")
            
            # Parse the output using the task's parse_output method
            parsed_assets = task.parse_output(output)
            logger.info(f"Parsed assets: {list(parsed_assets.keys())}")
            
            # Filter assets if specific types were requested
            if asset_types:
                filtered_assets = {}
                for asset_type, assets in parsed_assets.items():
                    if asset_type in asset_types:
                        filtered_assets[asset_type] = assets
                parsed_assets = filtered_assets
                logger.info(f"Filtered to asset types: {[at.value for at in asset_types]}")
            
            return {
                'task_name': task_name,
                'target': target,
                'command': command,
                'raw_output': output,
                'parsed_assets': parsed_assets,
                'asset_types_filtered': list(asset_types) if asset_types else None,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Error testing task {task_name}: {str(e)}")
            return {
                'task_name': task_name,
                'target': target,
                'error': str(e),
                'success': False
            }
    
    def _execute_command(self, command: str) -> str:
        """
        Execute a shell command and return the output
        
        Args:
            command: Shell command to execute
            
        Returns:
            Command output as string
        """
        try:
            # For commands that return a list (like subdomain_finder), join them
            if isinstance(command, list):
                command = ' && '.join(command)
            
            logger.info(f"Executing command: {command}")
            
            # Execute the command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.warning(f"Command returned non-zero exit code: {result.returncode}")
                logger.warning(f"Stderr: {result.stderr}")
            
            return result.stdout
            
        except subprocess.TimeoutExpired:
            logger.error("Command timed out after 5 minutes")
            return ""
        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return ""
    
    def print_assets(self, parsed_assets: Dict[AssetType, List[Any]], asset_types_filtered: Optional[List[AssetType]] = None):
        """
        Pretty print the parsed assets
        
        Args:
            parsed_assets: Dictionary of asset types to lists of assets
            asset_types_filtered: List of asset types that were filtered (for display)
        """
        print("\n" + "="*80)
        print("PARSED ASSETS")
        if asset_types_filtered:
            print(f"Filtered to: {[at.value for at in asset_types_filtered]}")
        print("="*80)
        
        for asset_type, assets in parsed_assets.items():
            print(f"\n{asset_type.value.upper()} ASSETS ({len(assets)} found):")
            print("-" * 60)
            
            if not assets:
                print("  No assets found")
                continue
            
            for i, asset in enumerate(assets, 1):
                print(f"\n  {i}. {asset_type.value.title()}:")
                
                # Handle different asset types
                if hasattr(asset, 'to_dict'):
                    # For Pydantic models
                    asset_dict = asset.to_dict()
                elif hasattr(asset, '__dict__'):
                    # For regular objects
                    asset_dict = asset.__dict__
                else:
                    # For simple types
                    asset_dict = str(asset)
                
                # Pretty print the asset
                self._print_dict(asset_dict, indent=4)
    
    def _print_dict(self, data: Any, indent: int = 0):
        """Recursively print dictionary data with proper indentation"""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    print(" " * indent + f"{key}:")
                    self._print_dict(value, indent + 2)
                else:
                    print(" " * indent + f"{key}: {value}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                print(" " * indent + f"[{i}]:")
                self._print_dict(item, indent + 2)
        else:
            print(" " * indent + str(data))

def main():
    """Main function to run the test script"""
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print(__doc__)
        print(f"\nAvailable tasks: {', '.join(TaskTester().get_available_tasks())}")
        print(f"Available asset types: {', '.join(TaskTester().get_available_asset_types())}")
        sys.exit(1)
    
    task_name = sys.argv[1]
    target = sys.argv[2]
    asset_types_str = sys.argv[3] if len(sys.argv) == 4 else "all"
    
    # Create tester and parse asset types
    tester = TaskTester()
    asset_types = tester.parse_asset_types(asset_types_str)
    
    try:
        result = tester.test_task(task_name, target, asset_types)
        
        if result['success']:
            print(f"\nTask '{task_name}' completed successfully!")
            print(f"Target: {result['target']}")
            print(f"Command: {result['command']}")
            
            # Print the parsed assets
            tester.print_assets(result['parsed_assets'], result['asset_types_filtered'])
            
            # Print summary
            total_assets = sum(len(assets) for assets in result['parsed_assets'].values())
            print("\n" + "="*80)
            print(f"SUMMARY: Found {total_assets} total assets across {len(result['parsed_assets'])} asset types")
            if result['asset_types_filtered']:
                print(f"Filtered to: {[at.value for at in result['asset_types_filtered']]}")
            print("="*80)
            
        else:
            print(f"\nTask '{task_name}' failed!")
            print(f"Error: {result['error']}")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 