from typing import Dict, Any, Optional
import os
import json
import logging

logger = logging.getLogger(__name__)


class VendorConfig:
    """Configuration manager for API vendor settings"""
    
    def __init__(self):
        self.configs = self._load_default_configs()
        self._load_custom_configs()
    
    def _load_default_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load default vendor configurations"""
        return {
            "threatstream": {
                "query": {
                    "limit": 1000,
                    "rate_limit_delay": 1
                },
                "timeout": 120,
                "retry": {
                    "max_attempts": 3,
                    "backoff_factor": 2,
                    "rate_limit_wait": 60
                }
            },
            "recordedfuture": {
                "query": {
                    "limit": 100,
                    "order_by": "created",
                    "direction": "asc",
                    "statuses": ["New", "InProgress"],
                    "category": ["domain_abuse"],
                    "details_panels": ["status", "dns", "whois", "summary"],
                    "rate_limit_delay": 0.5
                },
                "timeout": 120,
                "retry": {
                    "max_attempts": 3,
                    "backoff_factor": 2,
                    "rate_limit_wait": 60
                }
            },
            # Template for new vendors
            "example_vendor": {
                "query": {
                    "endpoints": {
                        "domains": "/api/v1/domains",
                        "auth": "/api/v1/auth"
                    },
                    "filters": {
                        "malicious_only": True,
                        "confidence_threshold": 75
                    },
                    "pagination": {
                        "limit": 100,
                        "max_pages": 50
                    }
                },
                "timeout": 60,
                "retry": {
                    "max_attempts": 3,
                    "backoff_factor": 1.5,
                    "rate_limit_wait": 30
                }
            }
        }
    
    def _load_custom_configs(self):
        """Load custom configurations from environment or file"""
        # Check for environment variable with JSON config
        custom_config_json = os.getenv("API_VENDOR_CONFIG")
        if custom_config_json:
            try:
                custom_configs = json.loads(custom_config_json)
                self._merge_configs(custom_configs)
                logger.info("Loaded custom vendor configs from environment")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse API_VENDOR_CONFIG JSON: {e}")
        
        # Check for config file
        config_file = os.getenv("API_VENDOR_CONFIG_FILE", "/config/vendor_config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    custom_configs = json.load(f)
                self._merge_configs(custom_configs)
                logger.info(f"Loaded custom vendor configs from {config_file}")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load config file {config_file}: {e}")
    
    def _merge_configs(self, custom_configs: Dict[str, Any]):
        """Merge custom configurations with defaults"""
        for vendor, config in custom_configs.items():
            if vendor in self.configs:
                # Deep merge with defaults
                self._deep_merge(self.configs[vendor], config)
            else:
                # New vendor configuration
                self.configs[vendor] = config
    
    def _deep_merge(self, base_dict: Dict[str, Any], overlay_dict: Dict[str, Any]):
        """Deep merge two dictionaries"""
        for key, value in overlay_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_merge(base_dict[key], value)
            else:
                base_dict[key] = value
    
    def get_vendor_config(self, vendor_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific vendor"""
        return self.configs.get(vendor_name.lower())
    
    def get_query_config(self, vendor_name: str) -> Optional[Dict[str, Any]]:
        """Get query configuration for a vendor"""
        vendor_config = self.get_vendor_config(vendor_name)
        return vendor_config.get("query") if vendor_config else None
    
    def get_timeout(self, vendor_name: str) -> int:
        """Get timeout setting for a vendor"""
        vendor_config = self.get_vendor_config(vendor_name)
        return vendor_config.get("timeout", 60) if vendor_config else 60
    
    def get_retry_config(self, vendor_name: str) -> Dict[str, Any]:
        """Get retry configuration for a vendor"""
        vendor_config = self.get_vendor_config(vendor_name)
        if vendor_config and "retry" in vendor_config:
            return vendor_config["retry"]
        return {
            "max_attempts": 3,
            "backoff_factor": 2,
            "rate_limit_wait": 60
        }
    
    def update_vendor_config(self, vendor_name: str, config_updates: Dict[str, Any]):
        """Update configuration for a vendor at runtime"""
        vendor_name = vendor_name.lower()
        if vendor_name not in self.configs:
            self.configs[vendor_name] = {}
        
        self._deep_merge(self.configs[vendor_name], config_updates)
        logger.info(f"Updated configuration for vendor {vendor_name}")
    
    def list_supported_vendors(self) -> list:
        """Get list of supported vendors"""
        return list(self.configs.keys())
    
    def validate_vendor_config(self, vendor_name: str) -> bool:
        """Validate that a vendor has required configuration"""
        config = self.get_vendor_config(vendor_name)
        if not config:
            return False
        
        # Basic validation - ensure required sections exist
        required_sections = ["query", "timeout"]
        return all(section in config for section in required_sections)


# Global configuration instance
vendor_config = VendorConfig()