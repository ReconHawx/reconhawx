"""
Data models for CT Monitor Services.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class CertificateInfo:
    """Information extracted from a certificate"""
    
    domains: List[str]
    issuer: str
    issuer_cn: str
    not_before: Optional[str] = None
    not_after: Optional[str] = None
    fingerprint: Optional[str] = None
    serial_number: Optional[str] = None
    source: str = "unknown"
    cert_index: Optional[int] = None
    seen_at: Optional[str] = None
    update_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "domains": self.domains,
            "issuer": self.issuer,
            "issuer_cn": self.issuer_cn,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "fingerprint": self.fingerprint,
            "serial_number": self.serial_number,
            "source": self.source,
            "cert_index": self.cert_index,
            "seen_at": self.seen_at,
            "update_type": self.update_type
        }


@dataclass
class MatchResult:
    """Result of domain matching against protected domains"""
    
    matched: bool
    protected_domain: str
    cert_domain: str
    similarity_score: float
    match_type: str  # e.g. "keyword", "protected_similarity", "dnstwist:<fuzzer>"
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "protected_domain": self.protected_domain,
            "cert_domain": self.cert_domain,
            "similarity_score": self.similarity_score,
            "match_type": self.match_type,
            "details": self.details
        }


@dataclass
class CTAlert:
    """Alert generated when a suspicious certificate is detected"""
    
    event_type: str = "ct_typosquat_detected"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    program_name: str = ""
    
    # Match information
    protected_domain: str = ""
    detected_domain: str = ""
    similarity_score: float = 0.0
    match_type: str = ""
    match_details: Dict[str, Any] = field(default_factory=dict)
    
    # Certificate information
    certificate: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    source: str = "ct_monitor"
    priority: str = "medium"
    auto_analyze: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "program_name": self.program_name,
            "protected_domain": self.protected_domain,
            "detected_domain": self.detected_domain,
            "similarity_score": self.similarity_score,
            "match_type": self.match_type,
            "match_details": self.match_details,
            "certificate": self.certificate,
            "source": self.source,
            "priority": self.priority,
            "auto_analyze": self.auto_analyze
        }


@dataclass 
class ProcessingStats:
    """Statistics for CT stream processing"""
    
    total_received: int = 0
    filtered_by_tld: int = 0
    processed: int = 0
    matches_found: int = 0
    alerts_published: int = 0
    skipped_existing: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0
    start_time: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        runtime = (datetime.utcnow() - self.start_time).total_seconds()
        rate = self.total_received / runtime if runtime > 0 else 0
        
        return {
            "total_received": self.total_received,
            "filtered_by_tld": self.filtered_by_tld,
            "processed": self.processed,
            "matches_found": self.matches_found,
            "alerts_published": self.alerts_published,
            "skipped_existing": self.skipped_existing,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "errors": self.errors,
            "runtime_seconds": int(runtime),
            "certs_per_second": round(rate, 2)
        }

