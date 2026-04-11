"""Chunked PostgreSQL bulk upserts for asset ingestion (optional feature flags)."""

from repository.bulk_sql.config import (
    bulk_sql_apex_domains_enabled,
    bulk_sql_certificates_enabled,
    bulk_sql_ips_enabled,
    bulk_sql_services_enabled,
    bulk_sql_subdomains_enabled,
    bulk_sql_urls_enabled,
    sql_chunk_size,
)

__all__ = [
    "bulk_sql_apex_domains_enabled",
    "bulk_sql_certificates_enabled",
    "bulk_sql_ips_enabled",
    "bulk_sql_services_enabled",
    "bulk_sql_subdomains_enabled",
    "bulk_sql_urls_enabled",
    "sql_chunk_size",
]
