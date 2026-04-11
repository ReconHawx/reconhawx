"""PostgreSQL bulk upsert asset ingestion (default on).

Per-asset toggles default to **enabled**. Set the corresponding env var to
``false`` / ``0`` / ``off`` / ``no`` to fall back to threaded ORM ingestion for
that type only.
"""

import os


def _env_bool(key: str, default: bool = True) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def sql_chunk_size() -> int:
    return max(50, int(os.getenv("ASSET_BULK_SQL_CHUNK_SIZE", "1000")))


def bulk_sql_subdomains_enabled() -> bool:
    return _env_bool("ASSET_BULK_SQL_SUBDOMAINS", True)


def bulk_sql_ips_enabled() -> bool:
    return _env_bool("ASSET_BULK_SQL_IPS", True)


def bulk_sql_apex_domains_enabled() -> bool:
    return _env_bool("ASSET_BULK_SQL_APEX_DOMAINS", True)


def bulk_sql_services_enabled() -> bool:
    return _env_bool("ASSET_BULK_SQL_SERVICES", True)


def bulk_sql_certificates_enabled() -> bool:
    return _env_bool("ASSET_BULK_SQL_CERTIFICATES", True)


def bulk_sql_urls_enabled() -> bool:
    return _env_bool("ASSET_BULK_SQL_URLS", True)
