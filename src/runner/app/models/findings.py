from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

from models.base import serialize_datetime

class NucleiFinding(BaseModel):
    id: Optional[str] = None
    url: Optional[str] = None
    template_id: str
    template_url: Optional[str] = None
    template_path: Optional[str] = None
    name: str
    severity: str
    type: str
    tags: Optional[List[str]] = []
    description: Optional[str] = None
    matched_at: Optional[str] = None
    matcher_name: Optional[str] = None
    ip: Optional[str] = None
    port: Optional[int] = None
    matched_line: Optional[str] = None
    program_name: Optional[str] = None
    hostname: Optional[str] = None
    scheme: Optional[str] = None
    protocol: Optional[str] = None
    extracted_results: Optional[List[str]] = []
    info: Optional[dict] = {}
    notes: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "url": "https://example.com",
                "template_id": "example-template",
                "template_url": "https://example.com/template",
                "name": "Example Finding",
                "severity": "medium",
                "type": "http",
                "tags": ["tag1", "tag2"],
                "description": "Example description",
                "matched_at": "2023-01-01T00:00:00",
                "matcher_name": "example-matcher",
                "ip": "192.168.1.1",
                "port": 80,
                "matched_line": "Example matched line",
                "program_name": "Example Program",
                "hostname": "example.com",
                "scheme": "https",
                "protocol": "tcp",
                "notes": "User notes about this finding",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )

class TyposquatDomain(BaseModel):
    typo_domain: str
    # info field removed - all data now in separate normalized columns
    fuzzers: Optional[List[str]] = []
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    program_name: Optional[str] = None
    fix_timestamp: Optional[datetime] = None
    # New normalized schema fields
    domain_registered: Optional[bool] = None
    dns_a_records: Optional[List[str]] = None
    dns_mx_records: Optional[List[str]] = None
    dns_ns_records: Optional[List[str]] = None
    is_wildcard: Optional[bool] = None
    wildcard_types: Optional[List[str]] = None
    whois_registrar: Optional[str] = None
    whois_creation_date: Optional[str] = None
    whois_expiration_date: Optional[str] = None
    whois_registrant_name: Optional[str] = None
    whois_registrant_country: Optional[str] = None
    whois_admin_email: Optional[str] = None
    geoip_country: Optional[str] = None
    geoip_city: Optional[str] = None
    geoip_organization: Optional[str] = None
    risk_analysis_total_score: Optional[int] = None
    risk_analysis_risk_level: Optional[str] = None
    risk_analysis_version: Optional[str] = None
    risk_analysis_timestamp: Optional[str] = None
    risk_analysis_category_scores: Optional[Dict[str, Any]] = None
    risk_analysis_risk_factors: Optional[Dict[str, Any]] = None
    phishlabs_data: Optional[Dict[str, Any]] = None
    threatstream_data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    source: Optional[str] = None
    # Parked domain detection
    is_parked: Optional[bool] = None
    parked_detection_timestamp: Optional[datetime] = None
    parked_detection_reasons: Optional[Dict[str, Any]] = None
    parked_confidence: Optional[int] = None  # Confidence score 0-100
    # Protected domain similarities (calculated API-side)
    protected_domain_similarities: Optional[List[Dict[str, Any]]] = None

    def to_dict(self):
        """Custom to_dict method that excludes None values to prevent overwriting existing data"""
        data = self.model_dump(by_alias=True, exclude_none=True)
        return data

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "typo_domain": "examp1e.com",
                "domain_registered": True,
                "whois_registrar": "Example Registrar",
                "whois_creation_date": "2024-11-16T15:33:34.000Z",
                "dns_a_records": ["192.168.1.1"],
                "ssl_has_ssl": False,
                "http_status_code": 200,
                "geoip_country": "United States",
                "risk_analysis_total_score": 85,
                "fuzzers": ["insertion", "substitution"],
                "timestamp": "2025-06-09T10:26:49.942Z",
                "program_name": "example-program",
                "fix_timestamp": "2025-06-09T14:26:56.269Z",
                "notes": "User notes about this typosquat domain",
                "phishlabs_data": {
                    "incident_id": 458019889,
                    "url": "https://example.com/phish",
                    "category_code": 1201,
                    "category_name": "Domain without Content",
                    "status": "Monitoring Domain",
                    "comment": "This domain does not resolve.",
                    "product": "Example Product",
                    "create_date": "2020-10-14T14:22:37.000Z",
                    "assignee": "analyst@example.com",
                    "last_comment": "DATE:\t3/27/2023 \r\nSTATUS:\tNOTREG \r\nCHANGE_CODE:\tNEW \r\nREFERENCE:\tInfraction 458019889",
                    "group_category_name": "Domain Monitoring",
                    "action_description": "",
                    "status_description": "This domain is being monitored for changes.",
                    "mitigation_start": None,
                    "date_resolved": None,
                    "severity_name": "Low",
                    "mx_record": "N",
                    "ticket_status": "Open",
                    "resolution_status": None,
                    "incident_status": "Monitoring",
                    "last_updated": "2025-09-02T22:44:02.559Z"
                },
                "threatstream_data": {
                    "id": 12345,
                    "source": "Threatstream",
                    "threatscore": 85,
                    "threat_type": "phishing"
                }
            }
        }
    )

class TyposquatURL(BaseModel):
    """
    Finding model for typosquat URLs discovered through fuzzing or other means.
    Represents a specific URL path on a typosquat domain that may be suspicious.
    """
    id: Optional[str] = None
    url: str
    typo_domain: str = Field(alias="typosquat_domain")
    hostname: Optional[str] = None
    port: Optional[int] = None
    scheme: Optional[str] = None
    path: Optional[str] = None
    http_status_code: Optional[int] = None
    content_length: Optional[int] = None
    line_count: Optional[int] = None
    word_count: Optional[int] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    technologies: Optional[List[str]] = []
    final_url: Optional[str] = None
    screenshot_url: Optional[str] = None
    discovered_via: Optional[str] = None  # e.g., "fuzzing", "http_test", "manual"
    fuzzer_wordlist: Optional[str] = None
    risk_score: Optional[int] = None
    risk_factors: Optional[Dict[str, Any]] = None
    similarity_score: Optional[float] = None  # Content similarity to original domain
    program_name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    def to_dict(self):
        """Custom to_dict method that excludes None values to prevent overwriting existing data"""
        data = self.model_dump(by_alias=True, exclude_none=True)
        return data

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "url": "https://examp1e.com/login",
                "typo_domain": "examp1e.com",
                "hostname": "examp1e.com",
                "path": "/login",
                "http_status_code": 200,
                "content_length": 1234,
                "content_type": "text/html",
                "title": "Login Page",
                "technologies": ["PHP", "Apache"],
                "final_url": "https://examp1e.com/login",
                "screenshot_url": "https://storage.example.com/screenshots/abc123.png",
                "discovered_via": "fuzzing",
                "fuzzer_wordlist": "common-paths.txt",
                "risk_score": 85,
                "risk_factors": {
                    "has_login_form": True,
                    "similar_to_original": True,
                    "suspicious_technologies": []
                },
                "similarity_score": 0.95,
                "program_name": "example-program",
                "notes": "Suspicious login page on typosquat domain",
                "status": "open",
                "assigned_to": "analyst@example.com",
                "timestamp": "2025-10-10T10:00:00.000Z",
                "created_at": "2025-10-10T10:00:00.000Z",
                "updated_at": "2025-10-10T10:00:00.000Z"
            }
        }
    )

class WPScanFinding(BaseModel):
    id: Optional[str] = None
    url: str
    item_name: str
    item_type: str  # 'wordpress'|'plugin'|'theme'
    vulnerability_type: Optional[str] = None
    severity: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    fixed_in: Optional[str] = None
    references: Optional[List[str]] = []
    cve_ids: Optional[List[str]] = []
    enumeration_data: Optional[Dict[str, Any]] = None
    hostname: Optional[str] = None
    port: Optional[int] = None
    scheme: Optional[str] = None
    program_name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    def to_dict(self):
        """Custom to_dict method that excludes None values to prevent overwriting existing data"""
        data = self.model_dump(by_alias=True, exclude_none=True)
        return data

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "url": "https://example.com",
                "item_name": "WordPress",
                "item_type": "wordpress",
                "vulnerability_type": "CVE",
                "severity": "high",
                "title": "WordPress XSS Vulnerability",
                "description": "Cross-site scripting vulnerability in WordPress core",
                "fixed_in": "5.8.2",
                "references": ["https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2021-12345"],
                "cve_ids": ["CVE-2021-12345"],
                "enumeration_data": {
                    "wordpress_version": "5.8.1",
                    "plugins": ["plugin1", "plugin2"],
                    "themes": ["theme1"],
                    "users": ["admin"]
                },
                "hostname": "example.com",
                "port": 443,
                "scheme": "https",
                "program_name": "example-program",
                "notes": "User notes about this finding",
                "status": "new",
                "assigned_to": "analyst@example.com",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )