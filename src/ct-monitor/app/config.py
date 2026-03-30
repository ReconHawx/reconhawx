"""
Configuration for CT Monitor Service.

Environment variables:
- API_URL: API base URL (default: http://api:8000)
- NATS_URL: NATS server URL (default: nats://nats:4222)
- INTERNAL_SERVICE_API_KEY: API authentication key
- CT_TLD_FILTER: Comma-separated TLDs to monitor (default: com,net,org,io,co,app)
- CT_DOMAIN_REFRESH_INTERVAL: Seconds between domain refreshes (default: 300)
- LOG_LEVEL: Logging level (default: INFO)
- CT_MONITOR_AUTO_START: If true, start monitoring on pod boot after API is reachable (default: true)
"""

import os
from dataclasses import dataclass, field
from typing import Set


@dataclass
class CTMonitorConfig:
    """Configuration for CT Monitor Service"""
    
    # API Configuration
    api_url: str = field(default_factory=lambda: os.getenv("API_URL", "http://api:8000"))
    api_key: str = field(default_factory=lambda: os.getenv("INTERNAL_SERVICE_API_KEY", ""))
    
    # NATS Configuration
    nats_url: str = field(default_factory=lambda: os.getenv("NATS_URL", "nats://nats:4222"))
    
    # TLD Filter - only process certs for these TLDs
    tld_filter: Set[str] = field(default_factory=lambda: set(
        os.getenv("CT_TLD_FILTER", "com,net,org,io,co,app,xyz,online,site,info,biz").split(",")
    ))
    
    # Refresh interval for protected domains (seconds)
    domain_refresh_interval: int = field(
        default_factory=lambda: int(os.getenv("CT_DOMAIN_REFRESH_INTERVAL", "300"))
    )
    
    # CertStream configuration (fallback)
    certstream_url: str = field(
        default_factory=lambda: os.getenv("CERTSTREAM_URL", "wss://certstream.calidog.io/")
    )
    reconnect_delay: int = field(
        default_factory=lambda: int(os.getenv("CT_RECONNECT_DELAY", "5"))
    )
    
    ct_source: str = "ct_logs"
    
    # CT Log Polling configuration
    ct_poll_interval: int = field(
        default_factory=lambda: int(os.getenv("CT_POLL_INTERVAL", "10"))
    )
    ct_batch_size: int = field(
        default_factory=lambda: int(os.getenv("CT_BATCH_SIZE", "100"))
    )
    ct_max_entries_per_poll: int = field(
        default_factory=lambda: int(os.getenv("CT_MAX_ENTRIES_PER_POLL", "1000"))
    )
    ct_start_offset: int = field(
        default_factory=lambda: int(os.getenv("CT_START_OFFSET", "0"))
    )
    
    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    # Stats reporting interval (seconds)
    stats_interval: int = field(
        default_factory=lambda: int(os.getenv("CT_STATS_INTERVAL", "60"))
    )
    
    # HTTP Server configuration
    http_host: str = field(
        default_factory=lambda: os.getenv("CT_MONITOR_HTTP_HOST", "0.0.0.0")
    )
    
    http_port: int = field(
        default_factory=lambda: int(os.getenv("CT_MONITOR_HTTP_PORT", "8002"))
    )
    
    # Redis configuration for caching
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    cache_ttl_exists: int = field(
        default_factory=lambda: int(os.getenv("CT_CACHE_TTL_EXISTS", "86400"))  # 24 hours
    )
    cache_ttl_not_exists: int = field(
        default_factory=lambda: int(os.getenv("CT_CACHE_TTL_NOT_EXISTS", "300"))  # 5 minutes
    )
    enable_cache: bool = field(
        default_factory=lambda: os.getenv("CT_ENABLE_CACHE", "true").lower() == "true"
    )

    # When true, on pod startup wait for API then call start() (service stays up; program_match_states empty if no programs enabled)
    ct_monitor_auto_start: bool = field(
        default_factory=lambda: os.getenv("CT_MONITOR_AUTO_START", "true").lower()
        in ("true", "1", "yes")
    )


def get_config() -> CTMonitorConfig:
    """Get configuration instance"""
    return CTMonitorConfig()

