"""
Configuration for CT Monitor Service.

Environment variables:
- API_URL: API base URL (default: http://api:8000)
- NATS_URL: NATS server URL (default: nats://nats:4222)
- INTERNAL_SERVICE_API_KEY: API authentication key
- CERTSTREAM_URL: WebSocket URL for self-hosted certstream-server
- CT_INGESTION_TLD_FILTER_ENABLED: when true, filter certs by program tld_filter union (default false)
- CT_TLD_FILTER: legacy; only used if CT_INGESTION_TLD_FILTER_ENABLED=true
- CT_DOMAIN_REFRESH_INTERVAL: Seconds between domain refreshes (default: 300)
- LOG_LEVEL: Logging level (default: INFO)
- CT_MONITOR_AUTO_START: If true, start monitoring on pod boot after API is reachable (default: true)
- CT_CERTSTREAM_SCALE_ENABLED: Scale certstream-server Deployment 0/1 (auto-detect in-cluster)
- CERTSTREAM_DEPLOYMENT_NAME, KUBERNETES_NAMESPACE, CT_CERTSTREAM_READY_TIMEOUT
- CERTSTREAM_QUEUE_MAXSIZE: asyncio queue depth (default 5000)
- CERTSTREAM_YIELD_EVERY_N: event-loop yield every N dequeued certs (default 50)
"""

import os
from dataclasses import dataclass, field
from typing import Set


def certstream_scale_enabled_default() -> bool:
    from certstream_k8s import certstream_scale_enabled_from_env

    return certstream_scale_enabled_from_env()


@dataclass
class CTMonitorConfig:
    """Configuration for CT Monitor Service"""

    # API Configuration
    api_url: str = field(default_factory=lambda: os.getenv("API_URL", "http://api:8000"))
    api_key: str = field(default_factory=lambda: os.getenv("INTERNAL_SERVICE_API_KEY", ""))

    # NATS Configuration
    nats_url: str = field(default_factory=lambda: os.getenv("NATS_URL", "nats://nats:4222"))

    # Ingestion TLD filter (off by default — all CT certificate TLDs are matched)
    ingestion_tld_filter_enabled: bool = field(
        default_factory=lambda: os.getenv("CT_INGESTION_TLD_FILTER_ENABLED", "false")
        .strip()
        .lower()
        in ("true", "1", "yes", "on")
    )

    # Refresh interval for protected domains (seconds)
    domain_refresh_interval: int = field(
        default_factory=lambda: int(os.getenv("CT_DOMAIN_REFRESH_INTERVAL", "300"))
    )

    # CertStream (self-hosted certstream-server)
    certstream_url: str = field(
        default_factory=lambda: os.getenv("CERTSTREAM_URL", "ws://certstream:4000/")
    )
    reconnect_delay: int = field(
        default_factory=lambda: int(os.getenv("CT_RECONNECT_DELAY", "5"))
    )

    ct_source: str = "certstream"

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
        default_factory=lambda: int(os.getenv("CT_CACHE_TTL_EXISTS", "86400"))
    )
    cache_ttl_not_exists: int = field(
        default_factory=lambda: int(os.getenv("CT_CACHE_TTL_NOT_EXISTS", "300"))
    )
    enable_cache: bool = field(
        default_factory=lambda: os.getenv("CT_ENABLE_CACHE", "true").lower() == "true"
    )

    ct_monitor_auto_start: bool = field(
        default_factory=lambda: os.getenv("CT_MONITOR_AUTO_START", "true").lower()
        in ("true", "1", "yes")
    )

    # Scale certstream-server Deployment 0/1 with program CT gating (in-cluster)
    certstream_deployment_name: str = field(
        default_factory=lambda: os.getenv("CERTSTREAM_DEPLOYMENT_NAME", "certstream-server")
    )
    kubernetes_namespace: str = field(
        default_factory=lambda: os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
    )
    certstream_scale_enabled: bool = field(default_factory=certstream_scale_enabled_default)
    certstream_ready_timeout_sec: int = field(
        default_factory=lambda: int(os.getenv("CT_CERTSTREAM_READY_TIMEOUT", "90"))
    )
    certstream_queue_maxsize: int = field(
        default_factory=lambda: int(os.getenv("CERTSTREAM_QUEUE_MAXSIZE", "5000"))
    )
    certstream_yield_every_n: int = field(
        default_factory=lambda: max(1, int(os.getenv("CERTSTREAM_YIELD_EVERY_N", "50")))
    )


def get_config() -> CTMonitorConfig:
    """Get configuration instance"""
    return CTMonitorConfig()
