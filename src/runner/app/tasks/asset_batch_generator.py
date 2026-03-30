#!/usr/bin/env python3
"""
Asset Batch Generator Task

This task generates batches of random assets for testing background processing functionality.
It replicates the functionality of test_background_processing.py but as a proper runner task.

The task generates realistic asset distributions including:
- Subdomains (with apex domain creation)
- IP addresses
- Services (port scanning results)
- URLs
- Certificates
- Nuclei findings
- Apex domains

Parameters:
- batch_size: Number of assets to generate (default: 100)
- asset_types: List of asset types to generate (default: all types)
- program_name: Program name for the assets (default: from input)
"""

import logging
import random
import string
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from .base import Task, AssetType, FindingType
from models.assets import Domain, Ip, Service, Url, Certificate

logger = logging.getLogger(__name__)

class AssetBatchGenerator(Task):
    name = "asset_batch_generator"
    description = "Generates batches of random assets for testing background processing"
    input_type = AssetType.STRING  # Input will be the program name
    output_types = [
        AssetType.SUBDOMAIN, 
        AssetType.IP, 
        AssetType.SERVICE, 
        AssetType.URL, 
        AssetType.CERTIFICATE, 
        FindingType.NUCLEI, 
        AssetType.STRING  # For apex domains
    ]

    def get_timeout(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> int:
        """Return timeout based on batch size"""
        if params and 'batch_size' in params:
            batch_size = params['batch_size']
            if batch_size > 1000:
                return 600  # 10 minutes for very large batches
            elif batch_size > 500:
                return 300  # 5 minutes for large batches
            else:
                return 120  # 2 minutes for smaller batches
        return 120

    def get_last_execution_threshold(self) -> int:
        """Allow re-execution every hour for testing"""
        return 1

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate hash based on program name and batch size"""
        batch_size = params.get('batch_size', 100) if params else 100
        hash_input = f"{self.name}:{target}:{batch_size}"
        return hash_input

    def get_command(self, input_data: List[str], params: Optional[Dict[Any, Any]] = None) -> str:
        """
        Returns a simple command that just echoes the batch size.
        The actual asset generation happens in parse_output.
        
        Args:
            input_data: List containing any input data (not used for program name)
            params: Task parameters including batch_size
            
        Returns:
            str: Simple command to execute
        """
        batch_size = params.get('batch_size', 100) if params else 100
        
        # Return a simple command that just includes the batch size
        # The program name is handled by the runner/system, not the task
        return f"echo 'BATCH_SIZE:{batch_size}|Generating {batch_size} test assets'"

    def parse_output(self, output: str, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """
        Generate random assets instead of parsing actual output.
        This replicates the test_background_processing.py functionality.
        
        Args:
            output: Raw command output containing batch size
            
        Returns:
            Dict[AssetType, List[Any]]: Generated assets by type
        """
        # Extract batch size from the output
        batch_size = 100  # Default
        
        try:
            # Parse the output to extract BATCH_SIZE
            if "BATCH_SIZE:" in output:
                lines = output.split('|')
                for line in lines:
                    if line.startswith('BATCH_SIZE:'):
                        batch_size_str = line.replace('BATCH_SIZE:', '').strip()
                        try:
                            batch_size = int(batch_size_str)
                        except ValueError:
                            logger.warning(f"Invalid batch size: {batch_size_str}, using default 100")
                            batch_size = 100
        except Exception as e:
            logger.warning(f"Error parsing output for parameters: {e}, using defaults")
        
        logger.info(f"Generating {batch_size} random assets for testing")
        
        # Generate assets with realistic distribution (without program_name)
        assets = self._generate_asset_batch(batch_size)
        
        logger.info(f"Generated {sum(len(asset_list) for asset_list in assets.values())} total assets")
        
        return assets

    def _generate_asset_batch(self, batch_size: int) -> Dict[AssetType, List[Any]]:
        """Generate a batch of random assets with realistic distribution"""
        assets = {}
        
        # Calculate distribution (similar to test script)
        base_subdomains = max(1, batch_size // 3)
        base_ips = max(1, (batch_size - base_subdomains) // 3)
        base_services = max(1, (batch_size - base_subdomains - base_ips) // 2)
        base_urls = batch_size - base_subdomains - base_ips - base_services
        
        # Generate subdomains
        subdomains = []
        for i in range(base_subdomains):
            # Create variety of subdomain types
            if i % 3 == 0:
                # Some might be apex domains themselves
                name = self._generate_random_domain()
                is_wildcard = False
                wildcard_types = []
                cname_record = None
            elif i % 3 == 1:
                # Some with CNAME records
                subdomain_part = self._generate_random_string(random.randint(3, 6))
                domain_part = self._generate_random_domain()
                name = f"{subdomain_part}.{domain_part}"
                is_wildcard = False
                wildcard_types = []
                cname_record = f"{subdomain_part}.{domain_part}"
            else:
                # Regular subdomains
                subdomain_part = self._generate_random_string(random.randint(4, 8))
                domain_part = self._generate_random_domain()
                name = f"{subdomain_part}.{domain_part}"
                is_wildcard = False
                wildcard_types = []
                cname_record = None

            subdomain = Domain(
                name=name,
                ip=[self._generate_random_ip()],  # Use random IP
                is_wildcard=is_wildcard,
                wildcard_type=wildcard_types,  # Domain expects wildcard_type (singular)
                cname_record=cname_record
                # program_name is added by the runner/system, not the task
            )
            subdomains.append(subdomain)
        
        assets[AssetType.SUBDOMAIN] = subdomains
        
        # Generate IPs
        ips = []
        for i in range(base_ips):
            ip_addr = self._generate_random_ip()
            ptr_domain = self._generate_random_domain()
            ip = Ip(
                ip=ip_addr,
                ptr_record=f"ptr.{ptr_domain}",
                service_provider="test-provider"
                # program_name is added by the runner/system, not the task
            )
            ips.append(ip)
        
        assets[AssetType.IP] = ips
        
        # Generate services
        services = []
        service_types = ["http", "https", "ssh", "ftp", "smtp", "pop3", "imap", "dns"]
        for i in range(base_services):
            service_name = random.choice(service_types)
            service = Service(
                ip=self._generate_random_ip(),
                port=random.randint(1, 65535),
                protocol=random.choice(["tcp", "udp"]),
                service=service_name,
                banner=f"Test {service_name} service {self._generate_random_string(6)}"
                # program_name is added by the runner/system, not the task
            )
            services.append(service)
        
        assets[AssetType.SERVICE] = services
        
        # Generate URLs
        urls = []
        for i in range(base_urls):
            hostname = self._generate_random_domain()
            scheme = random.choice(["http", "https"])
            port = 80 if scheme == "http" else 443
            path = f"/{self._generate_random_string(random.randint(3, 10))}"
            url = Url(
                url=f"{scheme}://{hostname}{path}",
                scheme=scheme,
                hostname=hostname,
                port=port,
                path=path
                # program_name is added by the runner/system, not the task
            )
            urls.append(url)
        
        assets[AssetType.URL] = urls
        
        # For larger batches, add optional asset types
        if batch_size >= 100:
            optional_certificates = min(3, batch_size // 30)
            optional_apex_domains = min(2, batch_size // 40)
            optional_nuclei_findings = min(2, batch_size // 50)
            
            # Generate certificates
            if optional_certificates > 0:
                certificates = []
                for i in range(optional_certificates):
                    domain = self._generate_random_domain()
                    alt_domain = self._generate_random_domain()
                    cert = Certificate(
                        subject_dn=f"CN={domain},O=Test Org,C=US",
                        subject_cn=domain,
                        subject_alternative_names=[alt_domain],
                        valid_from=datetime.now().isoformat(),
                        valid_until=(datetime.now() + timedelta(days=365)).isoformat(),
                        issuer_dn="CN=Test CA,O=Test CA Org,C=US",
                        issuer_cn="Test CA",
                        issuer_organization=["Test CA Org"],
                        serial_number=f"{self._generate_random_string(16)}",
                        fingerprint_hash=f"sha256:{self._generate_random_string(16)}"
                    )
                    certificates.append(cert)
                
                assets[AssetType.CERTIFICATE] = certificates
            
            # Generate apex domains (standalone)
            if optional_apex_domains > 0:
                apex_domains = []
                for i in range(optional_apex_domains):
                    apex_domain = {
                        "name": self._generate_random_domain(),
                        "notes": f"Standalone apex domain {self._generate_random_string(8)}"
                        # program_name is added by the runner/system, not the task
                    }
                    apex_domains.append(apex_domain)
                
                assets[AssetType.STRING] = apex_domains
            
            # Generate nuclei findings
            if optional_nuclei_findings > 0:
                findings = []
                severity_levels = ["low", "medium", "high", "critical"]
                finding_types = ["http", "dns", "tcp", "ssl"]
                for i in range(optional_nuclei_findings):
                    template_name = f"test-{self._generate_random_string(8)}"
                    hostname = self._generate_random_domain()
                    scheme = random.choice(["http", "https"])
                    port = 80 if scheme == "http" else 443
                    finding = {
                        "template_name": template_name,
                        "name": f"Test Vulnerability {self._generate_random_string(6)}",
                        "url": f"{scheme}://{hostname}",
                        "template_id": template_name,
                        "type": random.choice(finding_types),  # Repository expects 'type' not 'finding_type'
                        "severity": random.choice(severity_levels),
                        "description": f"Test vulnerability description {self._generate_random_string(12)}",
                        "tags": ["test", "vulnerability", self._generate_random_string(4)],
                        "hostname": hostname,
                        "scheme": scheme,
                        "port": port,
                        "protocol": scheme
                        # program_name is added by the runner/system, not the task
                    }
                    findings.append(finding)
                
                assets[FindingType.NUCLEI] = findings
        
        # Verify total count matches expected
        total_generated = sum(len(asset_list) for asset_list in assets.values() if isinstance(asset_list, list))
        if total_generated != batch_size:
            logger.warning(f"Asset count mismatch: requested {batch_size}, generated {total_generated}")
            # Try to fix by adjusting URLs (most flexible)
            if total_generated > batch_size and AssetType.URL in assets:
                excess = total_generated - batch_size
                current_urls = len(assets[AssetType.URL])
                if current_urls > excess:
                    assets[AssetType.URL] = assets[AssetType.URL][:current_urls - excess]
                    logger.info("Adjusted URLs to match requested batch size")
        
        return assets

    def _generate_random_string(self, length: int = 8) -> str:
        """Generate a random string for asset names"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def _generate_random_ip(self) -> str:
        """Generate a random IP address"""
        return f"{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"

    def _generate_random_domain(self) -> str:
        """Generate a random domain name"""
        tlds = ['com', 'net', 'org', 'io', 'co', 'dev']
        name = self._generate_random_string(random.randint(3, 8))
        tld = random.choice(tlds)
        return f"{name}.{tld}"
