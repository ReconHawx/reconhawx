from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from models.base import serialize_datetime


class APIProgram(BaseModel):
    id: Optional[UUID] = Field(
        default=None,
        validation_alias=AliasChoices("id", "_id"),
    )
    name: str
    domain_regex: List[str] = []  # List of regex patterns for domain scope
    out_of_scope_regex: List[str] = []  # List of regex patterns for out-of-scope domains (exclusions)
    cidr_list: List[str] = []  # List of CIDR ranges
    safe_registrar: List[str] = []  # List of safe registrars
    safe_ssl_issuer: List[str] = []  # List of safe SSL issuers
    protected_subdomain_prefixes: List[str] = []  # Keywords that auto-qualify typosquat domains when found in domain name
    threatstream_api_key: Optional[str] = None  # API key for Threatstream integration
    threatstream_api_user: Optional[str] = None  # API user for Threatstream integration
    recordedfuture_api_key: Optional[str] = None  # API key for RecordedFuture integration
    typosquat_filtering_settings: Optional[Dict[str, Any]] = None
    ct_monitor_program_settings: Optional[Dict[str, Any]] = None
    ct_monitoring_enabled: bool = False
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "name": "Example Program",
                "domain_regex": [".*\\.example\\.com", ".*\\.example\\.org"],
                "out_of_scope_regex": ["^test-.*\\.example\\.com", "^staging-.*\\.example\\.com"],
                "cidr_list": ["192.168.1.0/24", "10.0.0.0/8"],
                "safe_registrar": ["GoDaddy", "Namecheap"],
                "safe_ssl_issuer": ["Let's Encrypt", "DigiCert"],
                "threatstream_api_key": "your-threatstream-api-key",
                "threatstream_api_user": "your-threatstream-username",
                "recordedfuture_api_key": "your-recordedfuture-api-key",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00",
            }
        },
    )
