from pydantic import BaseModel, Field, ConfigDict, AliasChoices, PrivateAttr, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from models.base import serialize_datetime
from utils.scope_patterns import sanitize_scope_entries


class ScopeDomainEntry(BaseModel):
    """Structured in-scope or out-of-scope hostname pattern.

    Note: rows are sanitized at the APIProgram level. This model is kept for
    OpenAPI schema clarity and downstream typing; it does not strict-validate
    the pattern shape itself so the containing request can drop bad rows
    without a 422.
    """

    pattern: str = Field(..., description="Hostname pattern; labels may be * (e.g. *.example.com, api.*.example.com)")
    wildcard: bool = Field(False, description="True if this row counts as wildcard for workflow filters")


class APIProgram(BaseModel):
    id: Optional[UUID] = Field(
        default=None,
        validation_alias=AliasChoices("id", "_id"),
    )
    name: str
    scope_domains: List[Dict[str, Any]] = Field(default_factory=list)
    out_of_scope_domains: List[Dict[str, Any]] = Field(default_factory=list)
    domain_regex: List[str] = Field(
        default_factory=list,
        description="Legacy regex lines; optional if scope_domains covers scope",
    )
    out_of_scope_regex: List[str] = Field(
        default_factory=list,
        description="Legacy regex exclusions",
    )
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

    # Captured by the scope sanitation validator so the route handler can
    # surface dropped rows to the client without failing the whole request.
    _ignored_in_scope: List[Dict[str, str]] = PrivateAttr(default_factory=list)
    _ignored_out_of_scope: List[Dict[str, str]] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _sanitize_scope(self) -> "APIProgram":
        in_valid, in_dropped = sanitize_scope_entries(self.scope_domains)
        out_valid, out_dropped = sanitize_scope_entries(self.out_of_scope_domains)
        self.scope_domains = in_valid
        self.out_of_scope_domains = out_valid
        self._ignored_in_scope = in_dropped
        self._ignored_out_of_scope = out_dropped
        return self

    def scope_warnings(self) -> Dict[str, List[Dict[str, str]]]:
        """Return non-empty dropped-entry summary for the response, or {}."""
        warnings: Dict[str, List[Dict[str, str]]] = {}
        if self._ignored_in_scope:
            warnings["ignored_in_scope"] = self._ignored_in_scope
        if self._ignored_out_of_scope:
            warnings["ignored_out_of_scope"] = self._ignored_out_of_scope
        return warnings

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "name": "Example Program",
                "scope_domains": [{"pattern": "*.example.com", "wildcard": True}],
                "out_of_scope_domains": [{"pattern": "*.dev.example.com", "wildcard": True}],
                "domain_regex": [],
                "out_of_scope_regex": [],
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
