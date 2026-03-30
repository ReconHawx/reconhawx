from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import datetime

from models.base import serialize_datetime

class Ip(BaseModel):
    ip: str
    ptr: Optional[str] = None
    service_provider: Optional[str] = None
    program_name: Optional[str] = None
    notes: Optional[str] = None
    # Hostname whose DNS A-records yielded this IP (runner → API scope gate; not persisted on IP row)
    discovered_via_domain: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "ip": "192.168.1.1",
                "ptr": ["example.com"],
                "service_provider": "Example Provider",
                "program_name": "Example Program",
                "notes": "User notes about this IP",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )

    def to_dict(self):
        return self.model_dump(by_alias=True)

    def __hash__(self):
        return hash((self.ip, self.discovered_via_domain))

    def __eq__(self, other):
        if not isinstance(other, Ip):
            return False
        return self.ip == other.ip and self.discovered_via_domain == other.discovered_via_domain

class Domain(BaseModel):
    name: str
    apex_domain: Optional[str] = None
    ip: Optional[List[str]] = []  # List of IP addresses as strings
    cname_record: Optional[str] = None
    is_wildcard: Optional[bool] = None
    wildcard_type: Optional[List[str]] = None
    program_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "name": "sub.example.com",
                "apex_domain": "example.com",
                "ip": ["192.168.1.1", "10.0.0.1"],  # Example shows direct IP addresses
                "cname_record": "alias.example.com",
                "is_wildcard": False,
                "wildcard_type": ["A", "TXT"],
                "program_name": "Example Program",
                "notes": "User notes about this domain",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )

    def to_dict(self):
        return self.model_dump(by_alias=True)

class Service(BaseModel):
    ip: str
    port: int
    protocol: str = ""
    service_name: str = ""
    banner: Optional[str] = None
    program_name: Optional[str] = None
    notes: Optional[str] = None
    nerva_metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "ip": "192.168.1.1",
                "port": 80,
                "protocol": "tcp", 
                "service_name": "http",
                "banner": "Example Banner",
                "program_name": "Example Program",
                "notes": "User notes about this service",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )

class Website(BaseModel):
    url: str
    host: Optional[str] = None
    port: Optional[int] = None
    scheme: Optional[str] = None
    techs: Optional[List[str]] = []
    favicon_hash: Optional[str] = None
    favicon_url: Optional[str] = None
    program_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "url": "https://example.com",
                "host": "example.com",
                "port": 443,
                "scheme": "https",
                "techs": ["Node.js", "Express"], 
                "favicon_hash": "1234567890",
                "favicon_url": "https://example.com/favicon.ico",
                "program_name": "Example Program",
                "notes": "User notes about this website",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )

class Url(BaseModel):
    url: str
    hostname: Optional[str] = None
    ips: Optional[List[str]] = []
    port: Optional[int] = None
    path: Optional[str] = None
    scheme: Optional[str] = None
    technologies: Optional[List[str]] = []
    response_time: Optional[int] = None
    lines: Optional[int] = None
    title: Optional[str] = None
    words: Optional[int] = None
    method: Optional[str] = None
    http_status_code: Optional[int] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    chain_status_codes: Optional[List[int]] = None
    final_url: Optional[str] = None
    body_preview: Optional[str] = None
    resp_body_hash: Optional[str] = None
    favicon_hash: Optional[str] = None
    favicon_url: Optional[str] = None
    redirect_chain: Optional[List[Dict[str, Any]]] = None
    certificate_serial: Optional[str] = None
    notes: Optional[str] = None
    extracted_links: Optional[List[str]] = None
    created_at: Optional[datetime] = None #Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None #Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},
        json_schema_extra={
            "example": {
                "url": "https://example.com",
                "hostname": "example.com",
                "port": 443,
                "path": "/",
                "scheme": "https",
                "techs": ["Node.js", "Express"], 
                "response_time": 100,
                "lines": 100,
                "title": "Example Title",
                "words": 100,
                "method": "GET",
                "http_status_code": 200,
                "content_type": "text/html",
                "content_length": 100,
                "chain_status_codes": [200, 201],
                "body_preview": "<html><body><h1>Example Title</h1></body",
                "resp_body_hash": "1234567890",
                "favicon_hash": "1234567890",
                "favicon_url": "https://example.com/favicon.ico",
                "final_url": "https://example.com",
                "redirect_chain": [{"index": 0, "method": "GET", "url": "https://example.com", "status_code": 301, "location": "https://example.com/redirected"}],
                "notes": "User notes about this URL",
                "extracted_links": ["https://example.com/link1", "https://example.com/link2"],
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )

    def to_dict(self):
        return self.model_dump(by_alias=True)

class Certificate(BaseModel):
    subject_dn: str
    subject_cn: str
    subject_alternative_names: Optional[List[str]] = None
    valid_from: str
    valid_until: str
    issuer_dn: str
    issuer_cn: str
    issuer_organization: Optional[List[str]] = None
    serial_number: str
    fingerprint_hash: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: serialize_datetime},    
        json_schema_extra={
            "example": {
                "subject_dn": "CN=example.com,OU=Example,O=Example,L=Example,ST=Example,C=US",
                "subject_cn": "example.com",
                "subject_alternative_names": ["example.com"],
                "valid_from": "2023-01-01",
                "valid_until": "2023-01-01",
                "issuer_dn": "CN=example.com,OU=Example,O=Example,L=Example,ST=Example,C=US",
                "issuer_cn": "example.com",
                "tls_version": "tls12",
                "cipher": "AES-256-GCM-SHA384",
                "issuer_organization": ["Example Org"],
                "serial_number": "1234567890",
                "fingerprint_hash": "1234567890",
                "notes": "User notes about this certificate",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        }
    )