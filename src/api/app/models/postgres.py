from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, ARRAY, BigInteger, SmallInteger, UniqueConstraint, LargeBinary, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from datetime import datetime
from typing import Dict, Any
import uuid
from pydantic import BaseModel
from typing import Optional

Base = declarative_base()

# Detailed Stat Models
class SubdomainStats(BaseModel):
    total: int = 0
    resolved: int = 0
    unresolved: int = 0
    wildcard: int = 0

class ApexDomainStats(BaseModel):
    total: int = 0

class IPStats(BaseModel):
    total: int = 0
    resolved: int = 0  # Has PTR
    unresolved: int = 0 # No PTR

class URLStats(BaseModel):
    total: int = 0
    root: int = 0       # Path is '/'
    non_root: int = 0   # Path is not '/'
    root_https: int = 0 # Path is '/' and scheme is https
    root_http: int = 0 # Path is '/' and scheme is http

class ServiceStats(BaseModel):
    total: int = 0

class CertificateStats(BaseModel):
    total: int = 0
    valid: int = 0
    expiring_soon: int = 0  # within 30 days
    expired: int = 0
    self_signed: int = 0
    wildcards: int = 0

# Response Model for Stats
class AssetStatsResponse(BaseModel):
    apex_domain_details: Optional[ApexDomainStats] = None
    subdomain_details: Optional[SubdomainStats] = None
    ip_details: Optional[IPStats] = None
    service_details: Optional[ServiceStats] = None # Changed from service_count
    url_details: Optional[URLStats] = None
    certificate_details: Optional[CertificateStats] = None

# Findings Stats Models
class NucleiFindingStats(BaseModel):
    total: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0

class TyposquatFindingStats(BaseModel):
    total: int = 0
    new: int = 0
    inprogress: int = 0
    resolved: int = 0
    dismissed: int = 0

# Response Model for Findings Stats
class FindingsStatsResponse(BaseModel):
    nuclei_findings: Optional[NucleiFindingStats] = None
    typosquat_findings: Optional[TyposquatFindingStats] = None

# Aggregated Stats Models for Multiple Programs
class AggregatedAssetStatsResponse(BaseModel):
    total_programs: int = 0
    apex_domain_details: Optional[ApexDomainStats] = None
    subdomain_details: Optional[SubdomainStats] = None
    ip_details: Optional[IPStats] = None
    service_details: Optional[ServiceStats] = None
    url_details: Optional[URLStats] = None
    certificate_details: Optional[CertificateStats] = None

class AggregatedFindingsStatsResponse(BaseModel):
    total_programs: int = 0
    nuclei_findings: Optional[NucleiFindingStats] = None
    typosquat_findings: Optional[TyposquatFindingStats] = None

class Program(Base):
    """Bug bounty programs - central entity for scoping assets"""
    __tablename__ = "programs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    domain_regex = Column(ARRAY(Text), default=[])  # Regex patterns for domain scope
    out_of_scope_regex = Column(ARRAY(Text), default=[])  # Regex patterns for out-of-scope domains (exclusions)
    cidr_list = Column(ARRAY(Text), default=[])     # CIDR ranges for IP scope
    safe_registrar = Column(ARRAY(Text), default=[])  # Trusted registrars
    safe_ssl_issuer = Column(ARRAY(Text), default=[]) # Trusted SSL issuers
    phishlabs_api_key = Column(String(255), nullable=True)
    threatstream_api_key = Column(String(255), nullable=True)  # API key for Threatstream integration
    threatstream_api_user = Column(String(255), nullable=True)  # API user for Threatstream integration
    recordedfuture_api_key = Column(String(255), nullable=True)  # API key for RecordedFuture integration
    protected_domains = Column(ARRAY(Text), default=[])  # Apex domains to monitor for typosquatting/CT alerts
    protected_subdomain_prefixes = Column(ARRAY(Text), default=[])  # Keywords that auto-qualify typosquat domains when found in domain name
    notification_settings = Column(JSONB, default=dict)
    # True: program event_handler_configs rows are additive on top of global; False: legacy full snapshot
    event_handler_addon_mode = Column(Boolean, nullable=False, default=False)
    typosquat_auto_resolve_settings = Column(JSONB, default=dict)  # {"min_parked_confidence_percent": 80, "min_similarity_percent": 85.0}
    typosquat_filtering_settings = Column(JSONB, default=dict)  # {"min_similarity_percent": 60.0, "enabled": true}
    ai_analysis_settings = Column(JSONB, default=dict)  # {"enabled": false, "model": "llama3:latest", ...}
    ct_monitoring_enabled = Column(Boolean, nullable=False, default=False)  # CT log monitoring for typosquat alerts
    ct_monitor_program_settings = Column(JSONB, nullable=False, default=dict)  # {"tld_filter": "com,net", "similarity_threshold": 0.75}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    apex_domains = relationship("ApexDomain", back_populates="program", cascade="all, delete-orphan")
    subdomains = relationship("Subdomain", back_populates="program", cascade="all, delete-orphan") 
    ips = relationship("IP", back_populates="program", cascade="all, delete-orphan")
    services = relationship("Service", back_populates="program", cascade="all, delete-orphan")
    urls = relationship("URL", back_populates="program", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="program", cascade="all, delete-orphan")
    extracted_links = relationship("ExtractedLink", back_populates="program", cascade="all, delete-orphan")
    technologies = relationship("Technology", overlaps="program", cascade="all, delete-orphan")
    nuclei_findings = relationship("NucleiFinding", back_populates="program", cascade="all, delete-orphan")
    typosquat_findings = relationship("TyposquatDomain", back_populates="program", cascade="all, delete-orphan")
    typosquat_apex_domains = relationship(
        "TyposquatApexDomain", back_populates="program", cascade="all, delete-orphan"
    )
    broken_links = relationship("BrokenLink", back_populates="program", cascade="all, delete-orphan")
    wpscan_findings = relationship("WPScanFinding", back_populates="program", cascade="all, delete-orphan")
    workflows = relationship("Workflow", back_populates="program", cascade="all, delete-orphan")
    workflow_logs = relationship("WorkflowLog", back_populates="program", cascade="all, delete-orphan")
    wordlists = relationship("Wordlist", back_populates="program")

class ApexDomain(Base):
    """Root/apex domains (e.g., example.com)"""
    __tablename__ = "apex_domains"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # WHOIS (workflow whois_domain_check / imports)
    whois_status = Column(String(64), nullable=True)
    whois_registrar = Column(Text, nullable=True)
    whois_creation_date = Column(DateTime, nullable=True)
    whois_expiration_date = Column(DateTime, nullable=True)
    whois_updated_date = Column(DateTime, nullable=True)
    whois_name_servers = Column(ARRAY(Text), nullable=True)
    whois_registrant_name = Column(Text, nullable=True)
    whois_registrant_org = Column(Text, nullable=True)
    whois_registrant_country = Column(String(128), nullable=True)
    whois_admin_email = Column(String(320), nullable=True)
    whois_tech_email = Column(String(320), nullable=True)
    whois_dnssec = Column(String(64), nullable=True)
    whois_registry_server = Column(String(255), nullable=True)
    whois_response_source = Column(String(64), nullable=True)
    whois_raw_response = Column(Text, nullable=True)
    whois_error = Column(Text, nullable=True)
    whois_checked_at = Column(DateTime, nullable=True)
    
    # Relationships
    program = relationship("Program", back_populates="apex_domains")
    subdomains = relationship("Subdomain", back_populates="apex_domain", cascade="all, delete-orphan")

class IP(Base):
    """IP addresses with PTR and geolocation data"""
    __tablename__ = "ips"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_address = Column(INET, unique=True, nullable=False, index=True)  # PostgreSQL INET type for IP addresses
    ptr_record = Column(String(255), index=True)  # PTR/reverse DNS record
    service_provider = Column(String(255))
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="ips")
    subdomain_ips = relationship("SubdomainIP", back_populates="ip", cascade="all, delete-orphan")
    services = relationship("Service", back_populates="ip", cascade="all, delete-orphan")
    nuclei_findings = relationship("NucleiFinding", back_populates="ip")

class Subdomain(Base):
    """Subdomains with DNS resolution data"""
    __tablename__ = "subdomains"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    apex_domain_id = Column(UUID(as_uuid=True), ForeignKey("apex_domains.id"), nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    cname_record = Column(String(255))  # CNAME target
    is_wildcard = Column(Boolean, default=False)
    wildcard_types = Column(ARRAY(String(10)))  # DNS record types that wildcard
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="subdomains")
    apex_domain = relationship("ApexDomain", back_populates="subdomains")
    subdomain_ips = relationship("SubdomainIP", back_populates="subdomain", cascade="all, delete-orphan")
    urls = relationship("URL", back_populates="subdomain")

class SubdomainIP(Base):
    """Many-to-many relationship between subdomains and IPs (replaces MongoDB arrays)"""
    __tablename__ = "subdomain_ips"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subdomain_id = Column(UUID(as_uuid=True), ForeignKey("subdomains.id"), nullable=False)
    ip_id = Column(UUID(as_uuid=True), ForeignKey("ips.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    subdomain = relationship("Subdomain", back_populates="subdomain_ips")
    ip = relationship("IP", back_populates="subdomain_ips")
    
    # Unique constraint to prevent duplicates
    __table_args__ = (
        UniqueConstraint('subdomain_id', 'ip_id'),
    )

class Service(Base):
    """Services running on IP:port combinations"""
    __tablename__ = "services"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_id = Column(UUID(as_uuid=True), ForeignKey("ips.id"), nullable=False, index=True)
    port = Column(Integer, nullable=False)
    protocol = Column(String(10), default="tcp")  # tcp/udp
    service_name = Column(String(50))  # http, ssh, ftp, etc.
    banner = Column(Text)  # Service banner/version info
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    notes = Column(Text)
    nerva_metadata = Column(JSONB)  # Nerva fingerprinting: cpes, confidence, algo, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="services")
    ip = relationship("IP", back_populates="services")
    url_associations = relationship("URLService", back_populates="service", cascade="all, delete-orphan")
    
    # Unique constraint on ip_id + port
    __table_args__ = (
        UniqueConstraint('ip_id', 'port'),
    )

class Certificate(Base):
    """SSL/TLS certificates"""
    __tablename__ = "certificates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_dn = Column(Text, nullable=False)
    subject_cn = Column(String(255), nullable=False, index=True)
    subject_alternative_names = Column(ARRAY(String(255)))  # SAN list
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False, index=True)
    issuer_dn = Column(Text, nullable=False)
    tls_version = Column(String(255), nullable=False)
    cipher = Column(String(255), nullable=False)
    issuer_cn = Column(String(255), nullable=False)
    issuer_organization = Column(ARRAY(String(255)))
    serial_number = Column(String(255), unique=True, nullable=False, index=True)
    fingerprint_hash = Column(String(255), nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="certificates")
    urls = relationship("URL", back_populates="certificate")

class URL(Base):
    """URLs with comprehensive HTTP response metadata"""
    __tablename__ = "urls"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, unique=True, nullable=False, index=True)
    hostname = Column(String(255), nullable=False, index=True)
    port = Column(Integer)
    path = Column(Text)
    scheme = Column(String(10))  # http/https
    
    # HTTP Response Data
    http_status_code = Column(SmallInteger)
    http_method = Column(String(10), default="GET")
    response_time_ms = Column(Integer)
    content_type = Column(String(255))
    content_length = Column(BigInteger)
    line_count = Column(Integer)
    word_count = Column(Integer)
    title = Column(Text)
    final_url = Column(Text)  # After redirects
    
    # Technical Analysis
    # Note: technologies now stored in separate tables (technologies, url_technologies)
    response_body_hash = Column(String(255), index=True)
    body_preview = Column(Text)  # First N characters of response
    favicon_hash = Column(String(255))
    favicon_url = Column(Text)
    
    # Navigation Data  
    redirect_chain = Column(JSONB)  # Full redirect sequence
    chain_status_codes = Column(ARRAY(SmallInteger))
    # Relationships
    certificate_id = Column(UUID(as_uuid=True), ForeignKey("certificates.id"), nullable=True, index=True)
    subdomain_id = Column(UUID(as_uuid=True), ForeignKey("subdomains.id"), nullable=True, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="urls")
    certificate = relationship("Certificate", back_populates="urls")
    service_associations = relationship("URLService", back_populates="url", cascade="all, delete-orphan")
    subdomain = relationship("Subdomain", back_populates="urls")
    screenshots = relationship("Screenshot", back_populates="url", cascade="all, delete-orphan")
    extracted_link_sources = relationship("ExtractedLinkSource", back_populates="source_url", cascade="all, delete-orphan")
    technology_associations = relationship("URLTechnology", back_populates="url", cascade="all, delete-orphan")

class URLService(Base):
    """Junction table linking URLs to Services (many-to-many: hostname can resolve to multiple IPs)"""
    __tablename__ = "url_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url_id = Column(UUID(as_uuid=True), ForeignKey("urls.id"), nullable=False, index=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    url = relationship("URL", back_populates="service_associations")
    service = relationship("Service", back_populates="url_associations")

    __table_args__ = (
        UniqueConstraint('url_id', 'service_id'),
    )

class ExtractedLink(Base):
    """Unique external links with references to source URLs"""
    __tablename__ = "extracted_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    link_url = Column(Text, unique=True, nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    program = relationship("Program", overlaps="extracted_links")
    sources = relationship("ExtractedLinkSource", back_populates="extracted_link", cascade="all, delete-orphan")

class ExtractedLinkSource(Base):
    """Junction table linking extracted links to their source URLs"""
    __tablename__ = "extracted_link_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extracted_link_id = Column(UUID(as_uuid=True), ForeignKey("extracted_links.id"), nullable=False, index=True)
    source_url_id = Column(UUID(as_uuid=True), ForeignKey("urls.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    extracted_link = relationship("ExtractedLink", back_populates="sources")
    source_url = relationship("URL", back_populates="extracted_link_sources")

    # Unique constraint to prevent duplicate source associations
    __table_args__ = (
        UniqueConstraint('extracted_link_id', 'source_url_id'),
    )

class Technology(Base):
    """Unique web technologies detected on URLs"""
    __tablename__ = "technologies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    program = relationship("Program", overlaps="technologies")
    url_associations = relationship("URLTechnology", back_populates="technology", cascade="all, delete-orphan")

    # Unique constraint on technology name per program
    __table_args__ = (
        UniqueConstraint('name', 'program_id'),
    )

class URLTechnology(Base):
    """Junction table linking technologies to URLs"""
    __tablename__ = "url_technologies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    technology_id = Column(UUID(as_uuid=True), ForeignKey("technologies.id"), nullable=False, index=True)
    url_id = Column(UUID(as_uuid=True), ForeignKey("urls.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    technology = relationship("Technology", back_populates="url_associations")
    url = relationship("URL", back_populates="technology_associations")

    # Unique constraint to prevent duplicate associations
    __table_args__ = (
        UniqueConstraint('technology_id', 'url_id'),
    )

class ScreenshotFile(Base):
    """Screenshot file content storage"""
    __tablename__ = "screenshot_files"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_content = Column(LargeBinary, nullable=False)  # Actual image content
    content_type = Column(String(100), nullable=False)
    filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    screenshot = relationship("Screenshot", back_populates="file", uselist=False)

class Screenshot(Base):
    """Website screenshots with deduplication"""
    __tablename__ = "screenshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url_id = Column(UUID(as_uuid=True), ForeignKey("urls.id"), nullable=False, index=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("screenshot_files.id"), nullable=False)  # Reference to file content
    image_hash = Column(String(255), nullable=False, index=True)  # For deduplication
    workflow_id = Column(String(255), index=True)  # Track which workflow captured it
    step_name = Column(String(255), index=True)  # Step name that captured it
    program_name = Column(String(255), index=True)  # Associated program name
    capture_count = Column(Integer, default=1)  # How many times this exact image was captured
    last_captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    extracted_text = Column(Text, nullable=True)  # HTML-derived page text from gowitness JSONL
    
    # Relationships
    url = relationship("URL", back_populates="screenshots")
    file = relationship("ScreenshotFile", back_populates="screenshot", uselist=False)

# === FINDINGS MODELS ===

class NucleiFinding(Base):
    """Security findings from Nuclei scanner"""
    __tablename__ = "nuclei_findings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, index=True)
    template_id = Column(String(255), nullable=False, index=True)
    template_url = Column(Text)
    template_path = Column(Text)
    name = Column(String(500), nullable=False)
    severity = Column(String(20), nullable=False, index=True)  # low, medium, high, critical
    finding_type = Column(String(50), nullable=False)  # http, dns, etc.
    tags = Column(ARRAY(String(100)))
    description = Column(Text)
    matched_at = Column(Text, index=True)
    matcher_name = Column(String(255))
    
    # Network Information
    ip_id = Column(UUID(as_uuid=True), ForeignKey("ips.id"), nullable=True, index=True)
    hostname = Column(String(255), index=True)
    port = Column(Integer)
    scheme = Column(String(10))
    protocol = Column(String(10))
    
    # Finding Details
    matched_line = Column(Text)
    extracted_results = Column(ARRAY(Text))
    info_data = Column(JSONB)  # Additional structured data
    
    # Program Association
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="nuclei_findings")
    ip = relationship("IP", back_populates="nuclei_findings")
    
    # Unique constraint to prevent duplicate findings
    __table_args__ = (
        UniqueConstraint('url', 'template_id', 'matcher_name', 'program_id', 'matched_at'),
    )

class TyposquatApexDomain(Base):
    """Registrable (apex) typosquat domain — WHOIS and DNS registration metadata"""

    __tablename__ = "typosquat_apex_domains"
    __table_args__ = (UniqueConstraint("program_id", "apex_domain", name="uq_typosquat_apex_program_domain"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    apex_domain = Column(String(255), nullable=False, index=True)
    whois_registrar = Column(Text)
    whois_creation_date = Column(DateTime)
    whois_expiration_date = Column(DateTime)
    whois_registrant_name = Column(Text)
    whois_registrant_country = Column(Text)
    whois_admin_email = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    program = relationship("Program", back_populates="typosquat_apex_domains")
    typosquat_findings = relationship("TyposquatDomain", back_populates="typosquat_apex")


class TyposquatDomain(Base):
    """Typosquatting domain detections"""
    __tablename__ = "typosquat_domains"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    typo_domain = Column(String(255), unique=True, nullable=False, index=True)
    fuzzer_types = Column(ARRAY(String(50)))  # insertion, substitution, etc.
    risk_score = Column(Integer)  # Computed risk score
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    fixed_at = Column(DateTime, nullable=True, index=True)  # When issue was resolved
    status = Column(String(20), default='new', index=True)  # new, inprogress, resolved, dismissed
    assigned_to = Column(String(255))  # User assigned to investigate
    notes = Column(Text)
    apex_typosquat_domain_id = Column(
        UUID(as_uuid=True), ForeignKey("typosquat_apex_domains.id"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Domain information
    domain_registered = Column(Boolean)
    dns_a_records = Column(ARRAY(Text))
    dns_mx_records = Column(ARRAY(Text))
    dns_ns_records = Column(ARRAY(Text))
    is_wildcard = Column(Boolean)
    wildcard_types = Column(ARRAY(Text))
        
    # GeoIP information
    geoip_country = Column(Text)
    geoip_city = Column(Text)
    geoip_organization = Column(Text)
    
    # Risk analysis
    risk_analysis_total_score = Column(Integer)
    risk_analysis_risk_level = Column(Text)
    risk_analysis_version = Column(Text)
    risk_analysis_timestamp = Column(DateTime)
    risk_analysis_category_scores = Column(JSONB)
    risk_analysis_risk_factors = Column(JSONB)
    
    # PhishLabs information (consolidated into JSONB)
    phishlabs_data = Column(JSONB)

    # Threatstream data - stores complete Threatstream API response
    threatstream_data = Column(JSONB)

    # RecordedFuture data - stores complete RecordedFuture API response
    recordedfuture_data = Column(JSONB)

    # Source of the data
    source = Column(String(255))

    # Actions taken (array of strings)
    action_taken = Column(ARRAY(String(255)))
    
    # Parked domain detection
    is_parked = Column(Boolean, nullable=True)
    parked_detection_timestamp = Column(DateTime, nullable=True)
    parked_detection_reasons = Column(JSONB, nullable=True)
    parked_confidence = Column(Integer, nullable=True)  # Confidence score 0-100

    # Protected domain similarity scores
    protected_domain_similarities = Column(JSONB, nullable=True, default=[])

    # Auto-resolve flag: true when finding meets program thresholds (parked confidence + similarity)
    auto_resolve = Column(Boolean, default=False, nullable=False)

    # AI analysis
    ai_analysis = Column(JSONB, nullable=True)
    ai_analyzed_at = Column(DateTime, nullable=True)

    # Append-only closure history: {to_status, closed_at, closed_by_user_id, source_action_log_id?}[]
    closure_events = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Denormalized: same instant as last closure_events[].closed_at (UTC naive)
    last_closure_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    program = relationship("Program", back_populates="typosquat_findings")
    typosquat_apex = relationship("TyposquatApexDomain", back_populates="typosquat_findings")

class BrokenLink(Base):
    """Broken link findings (social media and general)"""
    __tablename__ = "broken_links"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    link_type = Column(String(20), nullable=False, default='social_media', index=True)  # social_media or general
    media_type = Column(String(50), nullable=True, index=True)  # facebook, instagram, twitter, x, linkedin (for social_media)
    domain = Column(String(255), nullable=True, index=True)  # Domain name (for general)
    reason = Column(String(100), nullable=True)  # Reason for broken link (for general)
    status = Column(String(20), nullable=False, index=True)  # valid, broken, error, throttled
    url = Column(Text)
    error_code = Column(String(50))
    response_data = Column(JSONB)
    checked_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="broken_links")
    
    # Unique constraint to prevent duplicate findings
    __table_args__ = (
        UniqueConstraint('program_id', 'url', name='uq_broken_links_program_url'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'program_id': str(self.program_id),
            'link_type': self.link_type,
            'media_type': self.media_type,
            'domain': self.domain,
            'reason': self.reason,
            'status': self.status,
            'url': self.url,
            'error_code': self.error_code,
            'response_data': self.response_data,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class WPScanFinding(Base):
    """Security findings from WPScan scanner"""
    __tablename__ = "wpscan_findings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    item_name = Column(String(255), nullable=False, index=True)
    item_type = Column(String(50), nullable=False, index=True)  # 'wordpress'|'plugin'|'theme'
    vulnerability_type = Column(String(100))
    severity = Column(String(20), index=True)
    title = Column(Text)
    description = Column(Text)
    fixed_in = Column(String(100))
    references = Column(ARRAY(Text), name='references')
    cve_ids = Column(ARRAY(Text))
    enumeration_data = Column(JSONB)  # Stores discovered plugins/themes/usernames
    hostname = Column(String(255), index=True)
    port = Column(Integer)
    scheme = Column(String(10))
    notes = Column(Text)
    status = Column(String(50), index=True)
    assigned_to = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="wpscan_findings")
    
    # Unique constraint to prevent duplicate findings
    __table_args__ = (
        UniqueConstraint('url', 'item_name', 'program_id', name='uq_wpscan_findings_url_item_program'),
    )

class SocialMediaCredentials(Base):
    """Social media credentials for system-wide use"""
    __tablename__ = "social_media_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)  # facebook, instagram, twitter, linkedin
    username = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'name': self.name,
            'platform': self.platform,
            'username': self.username,
            'email': self.email,
            'password': self.password,  # Note: In production, this should be encrypted/hashed
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

# Pydantic models for SocialMediaCredentials API
class SocialMediaCredentialsCreate(BaseModel):
    name: str
    platform: str
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: bool = True

class SocialMediaCredentialsUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class SocialMediaCredentialsResponse(BaseModel):
    id: str
    name: str
    platform: str
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None  # Note: In production, this should be encrypted/hashed
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

# === WORKFLOW MODELS ===

class Workflow(Base):
    """Workflow definitions"""
    __tablename__ = "workflows"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    description = Column(Text)
    variables = Column(JSONB)  # Workflow variables
    inputs = Column(JSONB)     # Input definitions
    steps = Column(JSONB)      # Workflow steps configuration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="workflows")
    logs = relationship("WorkflowLog", back_populates="workflow", cascade="all, delete-orphan")  # Add relationship to WorkflowLog with cascade
    
    # Unique constraint on name + program
    __table_args__ = (
        UniqueConstraint('name', 'program_id'),
    )

class WorkflowLog(Base):
    """Workflow execution logs"""
    __tablename__ = "workflow_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True, index=True)  # Add foreign key with CASCADE DELETE
    workflow_name = Column(String(255), nullable=False)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False, index=True)
    execution_id = Column(String(255), unique=True, nullable=False, index=True)  # Kubernetes job ID
    status = Column(String(20), nullable=False, index=True)  # pending, running, completed, failed
    result_data = Column(JSONB)  # Execution results
    workflow_steps = Column(JSONB)  # Step execution details
    workflow_definition = Column(JSONB)  # Complete workflow definition structure
    runner_pod_output = Column(Text)  # Runner pod output/logs
    task_execution_logs = Column(JSONB)  # Per-task execution logs
    started_at = Column(DateTime, index=True)
    completed_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    program = relationship("Program", back_populates="workflow_logs")
    workflow = relationship("Workflow", back_populates="logs")  # Add relationship to Workflow
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'workflow_id': str(self.workflow_id) if self.workflow_id else None,
            'workflow_name': self.workflow_name,
            'program_id': str(self.program_id),
            'program_name': self.program.name if self.program else None,  # Include program name from relationship
            'execution_id': self.execution_id,
            'status': self.status,
            'result': self.status,  # Map status to result for compatibility
            'result_data': self.result_data,
            'workflow_steps': self.workflow_steps,
            'workflow_definition': self.workflow_definition,
            'runner_pod_output': self.runner_pod_output,
            'task_execution_logs': self.task_execution_logs,
            'started_at': self.started_at.isoformat() + 'Z' if self.started_at else None,
            'completed_at': self.completed_at.isoformat() + 'Z' if self.completed_at else None,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None
        }

# === SECURITY MODELS ===

class NucleiTemplate(Base):
    """Nuclei security templates"""
    __tablename__ = "nuclei_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(String(255), unique=True, nullable=False, index=True)  # nuclei template ID
    name = Column(String(500), nullable=False)
    author = Column(String(255))
    severity = Column(String(20), index=True)
    description = Column(Text)
    tags = Column(ARRAY(String(100)), index=True)
    yaml_content = Column(Text, nullable=False)  # Full YAML template
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class WordlistFile(Base):
    """Wordlist file content storage"""
    __tablename__ = "wordlist_files"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_content = Column(LargeBinary, nullable=False)  # Actual file content
    content_type = Column(String(100), nullable=False)
    filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    wordlist = relationship("Wordlist", back_populates="file", uselist=False)

class Wordlist(Base):
    """Wordlist file metadata - supports both static (file-based) and dynamic (generated) wordlists"""
    __tablename__ = "wordlists"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text)
    word_count = Column(Integer, nullable=False)
    tags = Column(ARRAY(String(100)))
    file_id = Column(UUID(as_uuid=True), ForeignKey("wordlist_files.id"), nullable=True)  # Nullable for dynamic wordlists
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True, index=True)
    created_by = Column(String(255))
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Dynamic wordlist fields
    is_dynamic = Column(Boolean, default=False, nullable=False, index=True)
    dynamic_type = Column(String(50), nullable=True)  # "subdomain_prefixes", "apex_domains", etc.
    dynamic_config = Column(JSONB, nullable=True)  # {"program_id": "..."} for generation params
    
    # Relationships
    program = relationship("Program", back_populates="wordlists")
    file = relationship("WordlistFile", back_populates="wordlist", uselist=False)

# === AUTHENTICATION MODELS ===

class User(Base):
    """User accounts with program-based permissions"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(150), unique=True, nullable=False, index=True)
    email = Column(String(254), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(150))
    last_name = Column(String(150))
    is_active = Column(Boolean, default=True, index=True)
    is_superuser = Column(Boolean, default=False)
    roles = Column(ARRAY(String(50)), default=["user"])
    rf_uhash = Column(String(255), nullable=True)
    hackerone_api_token = Column(String(255), nullable=True)
    hackerone_api_user = Column(String(255), nullable=True)
    intigriti_api_token = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    api_tokens = relationship("APIToken", back_populates="user", cascade="all, delete-orphan")
    program_permissions = relationship("UserProgramPermission", back_populates="user", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        # Convert program permissions to dict format expected by frontend
        program_permissions = {}
        for perm in self.program_permissions:
            if perm.program:
                program_permissions[perm.program.name] = perm.permission_level
        
        return {
            'id': str(self.id),
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_active': self.is_active,
            'is_superuser': self.is_superuser,
            'roles': self.roles,
            'program_permissions': program_permissions,
            'rf_uhash': self.rf_uhash,
            'hackerone_api_token': self.hackerone_api_token,
            'hackerone_api_user': self.hackerone_api_user,
            'intigriti_api_token': self.intigriti_api_token,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'must_change_password': bool(self.must_change_password),
        }

class UserProgramPermission(Base):
    """Many-to-many user program permissions (replaces MongoDB embedded document)"""
    __tablename__ = "user_program_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    permission_level = Column(String(20), nullable=False)  # analyst, manager
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="program_permissions")
    program = relationship("Program")
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint('user_id', 'program_id'),
    )

class APIToken(Base):
    """API tokens for authentication"""
    __tablename__ = "api_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500))
    permissions = Column(ARRAY(String(100)))
    is_active = Column(Boolean, default=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="api_tokens")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'name': self.name,
            'description': self.description,
            'permissions': self.permissions,
            'is_active': self.is_active,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

# === ADMIN MODELS ===

class JobStatus(Base):
    """Job execution status tracking"""
    __tablename__ = "job_status"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(String(255), unique=True, nullable=False, index=True)
    job_type = Column(String(100), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, index=True)  # pending, running, completed, failed
    progress = Column(SmallInteger, default=0)  # 0-100
    message = Column(Text)
    results = Column(JSONB)  # Job results data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    user = relationship("User")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'job_id': self.job_id,
            'job_type': self.job_type,
            'user_id': str(self.user_id) if self.user_id else None,
            'status': self.status,
            'progress': self.progress,
            'message': self.message,
            'results': self.results,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class ReconTaskParameters(Base):
    """Configuration parameters for recon tasks"""
    __tablename__ = "recon_task_parameters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recon_task = Column(String(100), unique=True, nullable=False, index=True)
    parameters = Column(JSONB, nullable=False)  # Task-specific configuration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'recon_task': self.recon_task,
            'parameters': self.parameters,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class AwsCredentials(Base):
    """AWS credentials for system-wide use"""
    __tablename__ = "aws_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    access_key = Column(String(255), nullable=False)
    secret_access_key = Column(String(255), nullable=False)
    default_region = Column(String(50), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'name': self.name,
            'access_key': self.access_key,
            'secret_access_key': self.secret_access_key,
            'default_region': self.default_region,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class SystemSetting(Base):
    """Key-value store for system-wide configuration"""
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'key': self.key,
            'value': self.value,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class EventHandlerConfig(Base):
    """Event handler configuration: one row per handler, program_id NULL = global"""
    __tablename__ = "event_handler_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=True)
    handler_id = Column(String(100), nullable=False)
    event_type = Column(String(100), nullable=False)
    config = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_handler_dict(self) -> Dict[str, Any]:
        """Convert row to handler object format: {id, event_type, conditions, actions, description, ...}"""
        out = dict(self.config) if self.config else {}
        out["id"] = self.handler_id
        out["event_type"] = self.event_type
        return out


class ScheduledJob(Base):
    """Scheduled job definitions"""
    __tablename__ = "scheduled_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id = Column(String(255), unique=True, nullable=False, index=True)
    job_type = Column(String(100), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    schedule_data = Column(JSONB, nullable=False)  # Schedule configuration
    job_data = Column(JSONB, nullable=False)  # Job-specific data
    workflow_variables = Column(JSONB, default={})  # Workflow variable values for scheduled workflow jobs
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    program_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    status = Column(String(20), nullable=False, index=True)  # scheduled, running, completed, failed, cancelled
    tags = Column(ARRAY(String(100)), default=[])
    next_run = Column(DateTime, nullable=True, index=True)
    last_run = Column(DateTime, nullable=True)
    total_executions = Column(Integer, default=0)
    successful_executions = Column(Integer, default=0)
    failed_executions = Column(Integer, default=0)
    enabled = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'schedule_id': self.schedule_id,
            'job_type': self.job_type,
            'name': self.name,
            'description': self.description,
            'schedule_data': self.schedule_data,
            'job_data': self.job_data,
            'workflow_variables': self.workflow_variables or {},
            'user_id': str(self.user_id) if self.user_id else None,
            'program_ids': [str(pid) for pid in self.program_ids] if self.program_ids else [],
            'status': self.status,
            'tags': self.tags or [],
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'total_executions': self.total_executions,
            'successful_executions': self.successful_executions,
            'failed_executions': self.failed_executions,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class JobExecutionHistory(Base):
    """Job execution history tracking"""
    __tablename__ = "job_execution_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(String(255), unique=True, nullable=False, index=True)
    schedule_id = Column(String(255), nullable=False, index=True)
    job_id = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)  # pending, running, completed, failed
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    error_message = Column(Text)
    results = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'execution_id': self.execution_id,
            'schedule_id': self.schedule_id,
            'job_id': self.job_id,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'error_message': self.error_message,
            'results': self.results,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class InternalServiceToken(Base):
    """Internal service tokens for API-to-service authentication"""
    __tablename__ = "internal_service_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }

class TyposquatCertificate(Base):
    """Typosquat certificates - similar to certificates table but for typosquat URLs"""
    __tablename__ = "typosquat_certificates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_dn = Column(Text, nullable=False)
    subject_cn = Column(String(255), nullable=False, index=True)
    subject_alternative_names = Column(ARRAY(String(255)), nullable=True)
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False, index=True)
    issuer_dn = Column(Text, nullable=False)
    issuer_cn = Column(String(255), nullable=False)
    issuer_organization = Column(ARRAY(String(255)), nullable=True)
    serial_number = Column(String(255), nullable=False, unique=True)
    fingerprint_hash = Column(String(255), nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    program = relationship("Program")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'subject_dn': self.subject_dn,
            'subject_cn': self.subject_cn,
            'subject_alternative_names': self.subject_alternative_names or [],
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'issuer_dn': self.issuer_dn,
            'issuer_cn': self.issuer_cn,
            'issuer_organization': self.issuer_organization or [],
            'serial_number': self.serial_number,
            'fingerprint_hash': self.fingerprint_hash,
            'program_id': str(self.program_id) if self.program_id else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class TyposquatURL(Base):
    """Typosquat URLs - identical to URLs table but for typosquat domains"""
    __tablename__ = "typosquat_urls"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, unique=True, nullable=False, index=True)
    hostname = Column(String(255), nullable=False, index=True)
    port = Column(Integer, nullable=True)
    path = Column(Text, nullable=True)
    scheme = Column(String(10), nullable=True)
    http_status_code = Column(SmallInteger, nullable=True, index=True)
    http_method = Column(String(10), nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    content_type = Column(String(255), nullable=True)
    content_length = Column(BigInteger, nullable=True)
    line_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    title = Column(Text, nullable=True)
    final_url = Column(Text, nullable=True)
    technologies = Column(ARRAY(String(100)), nullable=True, index=True)
    response_body_hash = Column(String(255), nullable=True, index=True)
    body_preview = Column(Text, nullable=True)
    favicon_hash = Column(String(255), nullable=True)
    favicon_url = Column(Text, nullable=True)
    redirect_chain = Column(JSONB, nullable=True)
    chain_status_codes = Column(ARRAY(SmallInteger), nullable=True)
    typosquat_certificate_id = Column(UUID(as_uuid=True), ForeignKey("typosquat_certificates.id"), nullable=True, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True, index=True)
    typosquat_domain_id = Column(UUID(as_uuid=True), ForeignKey("typosquat_domains.id"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    typosquat_certificate = relationship("TyposquatCertificate")
    program = relationship("Program")
    typosquat_domain = relationship("TyposquatDomain")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'url': self.url,
            'hostname': self.hostname,
            'port': self.port,
            'path': self.path,
            'scheme': self.scheme,
            'http_status_code': self.http_status_code,
            'http_method': self.http_method,
            'response_time_ms': self.response_time_ms,
            'content_type': self.content_type,
            'content_length': self.content_length,
            'line_count': self.line_count,
            'word_count': self.word_count,
            'title': self.title,
            'final_url': self.final_url,
            'technologies': self.technologies or [],
            'response_body_hash': self.response_body_hash,
            'body_preview': self.body_preview,
            'favicon_hash': self.favicon_hash,
            'favicon_url': self.favicon_url,
            'redirect_chain': self.redirect_chain,
            'chain_status_codes': self.chain_status_codes or [],
            'typosquat_certificate_id': str(self.typosquat_certificate_id) if self.typosquat_certificate_id else None,
            'program_id': str(self.program_id) if self.program_id else None,
            'typosquat_domain_id': str(self.typosquat_domain_id) if self.typosquat_domain_id else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class TyposquatScreenshotFile(Base):
    """Typosquat screenshot files - identical to screenshot_files table but for typosquat domains"""
    __tablename__ = "typosquat_screenshot_files"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_content = Column(LargeBinary, nullable=False)
    content_type = Column(String(100), nullable=False)
    filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'content_type': self.content_type,
            'filename': self.filename,
            'file_size': self.file_size,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class TyposquatScreenshot(Base):
    """Typosquat screenshots - identical to screenshots table but references typosquat_urls"""
    __tablename__ = "typosquat_screenshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url_id = Column(UUID(as_uuid=True), ForeignKey("typosquat_urls.id"), nullable=False, index=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("typosquat_screenshot_files.id"), nullable=False, unique=True, index=True)
    image_hash = Column(String(255), nullable=False, index=True)
    workflow_id = Column(String(255), nullable=True, index=True)
    capture_count = Column(Integer, nullable=True, index=True)
    last_captured_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    step_name = Column(String(255), nullable=True, index=True)
    program_name = Column(String(255), nullable=True, index=True)
    extracted_text = Column(Text, nullable=True)  # HTML-derived page text from gowitness JSONL
    source_created_at = Column(DateTime, nullable=True, index=True)  # When screenshot was taken at source (e.g. RecordedFuture)
    source = Column(String(255), nullable=True, index=True)  # Source of screenshot (e.g. "recordedfuture")
    
    # Relationships
    url = relationship("TyposquatURL")
    file = relationship("TyposquatScreenshotFile")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            'id': str(self.id),
            'url_id': str(self.url_id) if self.url_id else None,
            'file_id': str(self.file_id) if self.file_id else None,
            'image_hash': self.image_hash,
            'workflow_id': self.workflow_id,
            'capture_count': self.capture_count,
            'last_captured_at': self.last_captured_at.isoformat() if self.last_captured_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'step_name': self.step_name,
            'program_name': self.program_name,
            'extracted_text': self.extracted_text,
            'source_created_at': self.source_created_at.isoformat() if self.source_created_at else None,
            'source': self.source
        } 