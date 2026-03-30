from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import aiohttp
import logging

logger = logging.getLogger(__name__)


class BaseAPIVendor(ABC):
    """Abstract base class for API vendor implementations"""

    def __init__(self, vendor_name: str, timeout: aiohttp.ClientTimeout):
        self.vendor_name = vendor_name
        self.timeout = timeout
        self.api_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_domains_found": 0
        }

    @abstractmethod
    async def gather_domains(self, api_credentials: Dict[str, str], program_name: str, session: Optional[aiohttp.ClientSession] = None, date_range_hours: Optional[int] = None, custom_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Gather domains from the vendor API

        Args:
            api_credentials: API credentials for this vendor
            program_name: Target program name for context
            session: Optional shared HTTP session to use
            date_range_hours: Optional number of hours to limit the data range (for vendors that support it)
            custom_query: Optional custom query string to override default query (vendor-specific)

        Returns:
            List of domain data dictionaries
        """
        pass

    @abstractmethod
    def parse_domain_object(self, obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse vendor-specific domain object into standardized format
        
        Args:
            obj: Raw domain object from vendor API
            
        Returns:
            Standardized domain data dictionary or None if invalid
        """
        pass

    @abstractmethod
    def get_required_credentials(self) -> List[str]:
        """
        Get list of required credential field names for this vendor
        
        Returns:
            List of required credential field names
        """
        pass

    @abstractmethod
    def get_credential_fields(self) -> Dict[str, str]:
        """
        Get mapping of internal credential names to database field names
        
        Returns:
            Dict mapping internal names to database field names
        """
        pass

    def validate_credentials(self, api_credentials: Dict[str, str]) -> bool:
        """
        Validate that all required credentials are present
        
        Args:
            api_credentials: Provided credentials
            
        Returns:
            True if all required credentials are present
        """
        required = self.get_required_credentials()
        return all(api_credentials.get(field) for field in required)

    def create_finding_data(self, domain_data: Dict[str, Any], program_name: str) -> Dict[str, Any]:
        """
        Create standardized finding data structure
        
        Args:
            domain_data: Parsed domain data
            program_name: Target program name
            
        Returns:
            Standardized finding data structure
        """
        from datetime import datetime, timezone
        
        # Base finding structure
        finding = {
            "typo_domain": domain_data.get("typo_domain", ""),
            "program_name": program_name,
            "source": self.vendor_name,  # Set source to vendor name
            "notes": f"Gathered from {self.vendor_name} API",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "new",
        }
        
        # Extract database column fields from domain_data to root level
        database_columns = self._get_database_columns()
        for column in database_columns:
            if column in domain_data:
                finding[column] = domain_data[column]

        # Store vendor-specific data in appropriate field (excluding database columns)
        vendor_data_field = f"{self.vendor_name.lower()}_data"
        vendor_data = {k: v for k, v in domain_data.items() if k not in database_columns and k != "typo_domain"}

        # Add timestamp for when data was fetched from the vendor API
        vendor_data["last_fetched"] = datetime.now(timezone.utc).isoformat()

        finding[vendor_data_field] = vendor_data

        # For RecordedFuture, map RF status to finding status
        if self.vendor_name == "recordedfuture":
            rf_status = domain_data.get("status", "").lower()
            logger.info(f"RecordedFuture status mapping: domain={domain_data.get('typo_domain')}, rf_status='{rf_status}', original='{domain_data.get('status')}'")
            if rf_status == "inprogress" or rf_status == "in progress":
                finding["status"] = "inprogress"
                logger.info(f"Mapped RF status '{rf_status}' to finding status 'inprogress'")
            elif rf_status == "resolved":
                finding["status"] = "resolved"
                logger.info(f"Mapped RF status '{rf_status}' to finding status 'resolved'")
            elif rf_status == "closed":
                finding["status"] = "dismissed"
                logger.info(f"Mapped RF status '{rf_status}' to finding status 'dismissed'")
            elif rf_status == "new":
                finding["status"] = "new"
                logger.info(f"Mapped RF status '{rf_status}' to finding status 'new'")
            else:
                logger.warning(f"No mapping for RF status '{rf_status}', keeping default 'new'")
            # If no valid RF status mapping, keep default "new"
        
        # Ensure source field is always set to vendor name (override any source in domain_data)
        finding["source"] = self.vendor_name

        # Enhance notes with key information
        notes_parts = [finding["notes"]]
        
        if domain_data.get("description"):
            notes_parts.append(domain_data["description"])
            
        if domain_data.get("source"):
            notes_parts.append(f"Source: {domain_data['source']}")
            
        if domain_data.get("threatscore"):
            notes_parts.append(f"Threat Score: {domain_data['threatscore']}")
            
        # RecordedFuture-specific notes
        if self.vendor_name == "recordedfuture":
            if domain_data.get("alert_id"):
                notes_parts.append(f"Alert ID: {domain_data['alert_id']}")
            if domain_data.get("priority"):
                notes_parts.append(f"Priority: {domain_data['priority']}")
            if domain_data.get("risk_score"):
                notes_parts.append(f"Risk Score: {domain_data['risk_score']}")
            if domain_data.get("entity_criticality"):
                notes_parts.append(f"Criticality: {domain_data['entity_criticality']}")
            
        finding["notes"] = " | ".join(notes_parts)
        
        return finding

    def get_stats(self) -> Dict[str, int]:
        """Get current API statistics"""
        return self.api_stats.copy()

    def reset_stats(self):
        """Reset API statistics"""
        self.api_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_domains_found": 0
        }
    
    def _get_database_columns(self) -> List[str]:
        """
        Get list of database column names that should be extracted to root level
        Override in subclasses to specify vendor-specific columns
        """
        return []