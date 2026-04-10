"""
Batch Repository Base Class

Provides efficient bulk database operations for asset processing.
Uses threaded chunk processing so synchronous SQLAlchemy calls do not
block the main asyncio event loop (which must stay responsive for
health-check probes and concurrent requests).
"""

import asyncio
import logging
from typing import List, Dict, Tuple

from repository.subdomain_assets_repo import SubdomainAssetsRepository
from repository.ip_assets_repo import IPAssetsRepository
from repository.service_assets_repo import ServiceAssetsRepository
from repository.url_assets_repo import UrlAssetsRepository
from repository.certificate_assets_repo import CertificateAssetsRepository
from repository.apexdomain_assets_repo import ApexDomainAssetsRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-chunked processing helpers
#
# The per-asset repository methods (create_or_update_*) are declared async but
# use synchronous SQLAlchemy underneath, blocking the event loop for every DB
# round-trip.  When a batch contains thousands of assets this starves uvicorn's
# single-threaded event loop for minutes, causing liveness-probe failures and
# pod restarts.
#
# The helpers below split a batch into small chunks and run each chunk inside a
# worker thread (via asyncio.to_thread) with its own temporary event loop.  The
# main event loop regains control between chunks so it can serve health probes
# and other requests.
# ---------------------------------------------------------------------------

_THREAD_CHUNK_SIZE = 25


async def _process_items_in_thread_chunks(
    items: List[Dict],
    program_name: str,
    process_fn,
    chunk_size: int = _THREAD_CHUNK_SIZE,
) -> List[tuple]:
    """Run *process_fn* for every item, off-loading each chunk to a thread."""
    all_results: List[tuple] = []
    for i in range(0, len(items), chunk_size):
        chunk = items[i : i + chunk_size]
        chunk_results = await asyncio.to_thread(
            _process_chunk_sync, chunk, program_name, process_fn
        )
        all_results.extend(chunk_results)
        await asyncio.sleep(0)
    return all_results


def _process_chunk_sync(
    chunk: List[Dict],
    program_name: str,
    process_fn,
) -> List[tuple]:
    """Execute inside a worker thread — creates a throwaway event loop."""
    loop = asyncio.new_event_loop()
    results: List[tuple] = []
    try:
        for item_data in chunk:
            if not item_data.get("program_name"):
                item_data["program_name"] = program_name
            try:
                result = loop.run_until_complete(process_fn(item_data))
                results.append(("ok", item_data, result))
            except Exception as e:
                results.append(("error", item_data, e))
    finally:
        loop.close()
    return results


# ---------------------------------------------------------------------------


class BatchRepository:
    """Base class for batch database operations"""

    # ------------------------------------------------------------------
    # Subdomains
    # ------------------------------------------------------------------
    @classmethod
    async def bulk_create_or_update_subdomains(
        cls,
        subdomains: List[Dict],
        program_name: str,
    ) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update subdomains with rich event data collection

        Returns:
            Tuple of (success_count, failed_count, created_count, updated_count,
            skipped_count, created_assets, updated_assets, skipped_assets,
            implicit_apex_created_events)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        out_of_scope_count = 0
        created_assets: List[Dict] = []
        updated_assets: List[Dict] = []
        skipped_assets: List[Dict] = []
        implicit_apex_created_events: List[Dict] = []

        chunk_results = await _process_items_in_thread_chunks(
            subdomains,
            program_name,
            SubdomainAssetsRepository.create_or_update_subdomain,
        )

        for status, item_data, result_or_error in chunk_results:
            if status == "error":
                failed_count += 1
                logger.error(
                    f"Error processing subdomain {item_data.get('name', 'unknown')}: "
                    f"{result_or_error}"
                )
                skipped_assets.append(
                    {
                        "name": item_data.get("name", "unknown"),
                        "program_name": program_name,
                        "error": str(result_or_error),
                    }
                )
                continue

            record_id, action, event_data, apex_created_event = result_or_error
            if apex_created_event is not None:
                implicit_apex_created_events.append(apex_created_event)

            if record_id:
                success_count += 1
                if action == "created":
                    created_count += 1
                    if event_data:
                        created_assets.append(event_data)
                elif action == "updated":
                    updated_count += 1
                    if event_data:
                        updated_assets.append(event_data)
                elif action == "skipped":
                    skipped_count += 1
                    skipped_assets.append(
                        {
                            "record_id": record_id,
                            "name": item_data.get("name"),
                            "program_name": program_name,
                            "reason": "duplicate",
                        }
                    )
                elif action == "out_of_scope":
                    out_of_scope_count += 1
                    skipped_assets.append(
                        {
                            "name": item_data.get("name"),
                            "program_name": program_name,
                            "reason": "out_of_scope",
                        }
                    )
            else:
                failed_count += 1
                skipped_assets.append(
                    {
                        "name": item_data.get("name"),
                        "program_name": program_name,
                        "error": "processing_failed",
                    }
                )

        logger.info(
            f"Enhanced bulk subdomain processing completed: {success_count} success "
            f"({created_count} created, {updated_count} updated, {skipped_count} skipped, "
            f"{out_of_scope_count} out_of_scope), {failed_count} failed"
        )

        return (
            success_count,
            failed_count,
            created_count,
            updated_count,
            skipped_count + out_of_scope_count,
            created_assets,
            updated_assets,
            skipped_assets,
            implicit_apex_created_events,
        )

    # ------------------------------------------------------------------
    # IPs
    # ------------------------------------------------------------------
    @classmethod
    async def bulk_create_or_update_ips(
        cls,
        ips: List[Dict],
        program_name: str,
    ) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update IPs with rich event data collection

        Returns:
            Tuple of (success_count, failed_count, created_count, updated_count,
            skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        out_of_scope_count = 0
        created_assets: List[Dict] = []
        updated_assets: List[Dict] = []
        skipped_assets: List[Dict] = []

        chunk_results = await _process_items_in_thread_chunks(
            ips,
            program_name,
            IPAssetsRepository.create_or_update_ip,
        )

        for status, item_data, result_or_error in chunk_results:
            if status == "error":
                failed_count += 1
                logger.error(
                    f"Error processing IP {item_data.get('ip', 'unknown')}: "
                    f"{result_or_error}"
                )
                skipped_assets.append(
                    {
                        "ip_address": item_data.get("ip", "unknown"),
                        "program_name": program_name,
                        "error": str(result_or_error),
                    }
                )
                continue

            if len(result_or_error) == 3:
                record_id, action, event_data = result_or_error
            else:
                record_id, action = result_or_error
                event_data = None

            if action == "out_of_scope":
                out_of_scope_count += 1
                skipped_assets.append(
                    {
                        "ip_address": item_data.get("ip"),
                        "program_name": program_name,
                        "reason": "out_of_scope",
                    }
                )
            elif record_id:
                success_count += 1
                if action == "created":
                    created_count += 1
                    if event_data:
                        created_assets.append(event_data)
                elif action == "updated":
                    updated_count += 1
                    if event_data:
                        updated_assets.append(event_data)
                elif action == "skipped":
                    skipped_count += 1
                    skipped_assets.append(
                        {
                            "record_id": record_id,
                            "ip_address": item_data.get("ip"),
                            "program_name": program_name,
                            "reason": "duplicate",
                        }
                    )
            else:
                failed_count += 1
                skipped_assets.append(
                    {
                        "ip_address": item_data.get("ip"),
                        "program_name": program_name,
                        "error": "processing_failed",
                    }
                )

        return (
            success_count,
            failed_count,
            created_count,
            updated_count,
            skipped_count + out_of_scope_count,
            created_assets,
            updated_assets,
            skipped_assets,
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------
    @classmethod
    async def bulk_create_or_update_services(
        cls,
        services: List[Dict],
        program_name: str,
    ) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update services with rich event data collection

        Returns:
            Tuple of (success_count, failed_count, created_count, updated_count,
            skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets: List[Dict] = []
        updated_assets: List[Dict] = []
        skipped_assets: List[Dict] = []

        chunk_results = await _process_items_in_thread_chunks(
            services,
            program_name,
            ServiceAssetsRepository.create_or_update_service,
        )

        for status, item_data, result_or_error in chunk_results:
            if status == "error":
                failed_count += 1
                logger.error(
                    f"Error processing service "
                    f"{item_data.get('ip', 'unknown')}:{item_data.get('port', 'unknown')}: "
                    f"{result_or_error}"
                )
                skipped_assets.append(
                    {
                        "ip": item_data.get("ip", "unknown"),
                        "port": item_data.get("port", "unknown"),
                        "program_name": program_name,
                        "error": str(result_or_error),
                    }
                )
                continue

            if len(result_or_error) == 3:
                record_id, action, event_data = result_or_error
            else:
                record_id, action = result_or_error
                event_data = None

            if record_id:
                success_count += 1
                if action == "created":
                    created_count += 1
                    created_assets.append(
                        {
                            "event": "asset.created",
                            "asset_type": "service",
                            "record_id": record_id,
                            "ip": item_data.get("ip"),
                            "port": item_data.get("port"),
                            "program_name": program_name,
                            "service_name": item_data.get("service_name"),
                            "protocol": item_data.get("protocol", "tcp"),
                            "banner": item_data.get("banner"),
                        }
                    )
                elif action == "updated":
                    updated_count += 1
                    updated_assets.append(
                        {
                            "event": "asset.updated",
                            "asset_type": "service",
                            "record_id": record_id,
                            "ip": item_data.get("ip"),
                            "port": item_data.get("port"),
                            "program_name": program_name,
                            "service_name": item_data.get("service_name"),
                            "protocol": item_data.get("protocol", "tcp"),
                            "banner": item_data.get("banner"),
                        }
                    )
                elif action == "skipped":
                    skipped_count += 1
                    skipped_assets.append(
                        {
                            "record_id": record_id,
                            "ip": item_data.get("ip"),
                            "port": item_data.get("port"),
                            "program_name": program_name,
                            "reason": "duplicate",
                        }
                    )
            else:
                failed_count += 1
                skipped_assets.append(
                    {
                        "ip": item_data.get("ip"),
                        "port": item_data.get("port"),
                        "program_name": program_name,
                        "error": "processing_failed",
                    }
                )

        return (
            success_count,
            failed_count,
            created_count,
            updated_count,
            skipped_count,
            created_assets,
            updated_assets,
            skipped_assets,
        )

    # ------------------------------------------------------------------
    # URLs
    # ------------------------------------------------------------------
    @classmethod
    async def bulk_create_or_update_urls(
        cls,
        urls: List[Dict],
        program_name: str,
    ) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update URLs with rich event data collection

        Returns:
            Tuple of (success_count, failed_count, created_count, updated_count,
            skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets: List[Dict] = []
        updated_assets: List[Dict] = []
        skipped_assets: List[Dict] = []

        chunk_results = await _process_items_in_thread_chunks(
            urls,
            program_name,
            UrlAssetsRepository.create_or_update_url,
        )

        for status, item_data, result_or_error in chunk_results:
            if status == "error":
                failed_count += 1
                logger.error(
                    f"Error processing URL {item_data.get('url', 'unknown')}: "
                    f"{result_or_error}"
                )
                skipped_assets.append(
                    {
                        "url": item_data.get("url", "unknown"),
                        "program_name": program_name,
                        "error": str(result_or_error),
                    }
                )
                continue

            if len(result_or_error) == 3:
                record_id, action, event_data = result_or_error
            else:
                record_id, action = result_or_error
                event_data = None

            if record_id:
                success_count += 1
                if action == "created":
                    created_count += 1
                    created_assets.append(
                        {
                            "event": "asset.created",
                            "asset_type": "url",
                            "record_id": record_id,
                            "url": item_data.get("url"),
                            "path": item_data.get("path"),
                            "program_name": program_name,
                            "http_status_code": item_data.get("http_status_code"),
                            "content_type": item_data.get("content_type"),
                            "title": item_data.get("title"),
                            "technologies": item_data.get("technologies", []),
                        }
                    )
                elif action == "updated":
                    updated_count += 1
                    updated_assets.append(
                        {
                            "event": "asset.updated",
                            "asset_type": "url",
                            "record_id": record_id,
                            "url": item_data.get("url"),
                            "path": item_data.get("path"),
                            "program_name": program_name,
                            "http_status_code": item_data.get("http_status_code"),
                            "content_type": item_data.get("content_type"),
                            "title": item_data.get("title"),
                            "technologies": item_data.get("technologies", []),
                        }
                    )
                elif action == "skipped":
                    skipped_count += 1
                    skipped_assets.append(
                        {
                            "record_id": record_id,
                            "url": item_data.get("url"),
                            "program_name": program_name,
                            "reason": "duplicate",
                        }
                    )
            else:
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": item_data.get("url"),
                        "program_name": program_name,
                        "error": "processing_failed",
                    }
                )

        return (
            success_count,
            failed_count,
            created_count,
            updated_count,
            skipped_count,
            created_assets,
            updated_assets,
            skipped_assets,
        )

    # ------------------------------------------------------------------
    # Certificates
    # ------------------------------------------------------------------
    @classmethod
    async def bulk_create_or_update_certificates(
        cls,
        certificates: List[Dict],
        program_name: str,
    ) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update certificates with rich event data collection

        Returns:
            Tuple of (success_count, failed_count, created_count, updated_count,
            skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets: List[Dict] = []
        updated_assets: List[Dict] = []
        skipped_assets: List[Dict] = []

        chunk_results = await _process_items_in_thread_chunks(
            certificates,
            program_name,
            CertificateAssetsRepository.create_or_update_certificate,
        )

        for status, item_data, result_or_error in chunk_results:
            if status == "error":
                failed_count += 1
                logger.error(
                    f"Error processing certificate "
                    f"{item_data.get('subject_dn', 'unknown')}: {result_or_error}"
                )
                skipped_assets.append(
                    {
                        "subject_dn": item_data.get("subject_dn", "unknown"),
                        "program_name": program_name,
                        "error": str(result_or_error),
                    }
                )
                continue

            if len(result_or_error) == 3:
                record_id, action, event_data = result_or_error
            else:
                record_id, action = result_or_error
                event_data = None

            if record_id:
                success_count += 1
                if action == "created":
                    created_count += 1
                    created_assets.append(
                        {
                            "event": "asset.created",
                            "asset_type": "certificate",
                            "record_id": record_id,
                            "subject_dn": item_data.get("subject_dn"),
                            "program_name": program_name,
                            "subject_cn": item_data.get("subject_cn"),
                            "issuer_cn": item_data.get("issuer_cn"),
                            "valid_from": item_data.get("valid_from"),
                            "valid_until": item_data.get("valid_until"),
                            "serial_number": item_data.get("serial_number"),
                        }
                    )
                elif action == "updated":
                    updated_count += 1
                    updated_assets.append(
                        {
                            "event": "asset.updated",
                            "asset_type": "certificate",
                            "record_id": record_id,
                            "subject_dn": item_data.get("subject_dn"),
                            "program_name": program_name,
                            "subject_cn": item_data.get("subject_cn"),
                            "issuer_cn": item_data.get("issuer_cn"),
                            "valid_from": item_data.get("valid_from"),
                            "valid_until": item_data.get("valid_until"),
                            "serial_number": item_data.get("serial_number"),
                        }
                    )
                elif action == "skipped":
                    skipped_count += 1
                    skipped_assets.append(
                        {
                            "record_id": record_id,
                            "subject_dn": item_data.get("subject_dn"),
                            "program_name": program_name,
                            "reason": "duplicate",
                        }
                    )
            else:
                failed_count += 1
                skipped_assets.append(
                    {
                        "subject_dn": item_data.get("subject_dn"),
                        "program_name": program_name,
                        "error": "processing_failed",
                    }
                )

        return (
            success_count,
            failed_count,
            created_count,
            updated_count,
            skipped_count,
            created_assets,
            updated_assets,
            skipped_assets,
        )

    # ------------------------------------------------------------------
    # Apex Domains
    # ------------------------------------------------------------------
    @classmethod
    async def bulk_create_or_update_apex_domains(
        cls,
        apex_domains: List[Dict],
        program_name: str,
    ) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update apex domains with rich event data collection

        Returns:
            Tuple of (success_count, failed_count, created_count, updated_count,
            skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets: List[Dict] = []
        updated_assets: List[Dict] = []
        skipped_assets: List[Dict] = []

        chunk_results = await _process_items_in_thread_chunks(
            apex_domains,
            program_name,
            ApexDomainAssetsRepository.create_or_update_apex_domain,
        )

        for status, item_data, result_or_error in chunk_results:
            if status == "error":
                failed_count += 1
                logger.error(
                    f"Error processing apex domain "
                    f"{item_data.get('name', 'unknown')}: {result_or_error}"
                )
                skipped_assets.append(
                    {
                        "name": item_data.get("name", "unknown"),
                        "program_name": program_name,
                        "error": str(result_or_error),
                    }
                )
                continue

            if len(result_or_error) == 3:
                record_id, action, event_data = result_or_error
            else:
                record_id, action = result_or_error
                event_data = None

            if record_id:
                success_count += 1
                if action == "created":
                    created_count += 1
                    created_assets.append(
                        {
                            "event": "asset.created",
                            "asset_type": "apex_domain",
                            "record_id": record_id,
                            "name": item_data.get("name"),
                            "program_name": program_name,
                            "notes": item_data.get("notes"),
                            "whois_status": item_data.get("whois_status"),
                        }
                    )
                elif action == "updated":
                    updated_count += 1
                    updated_assets.append(
                        {
                            "event": "asset.updated",
                            "asset_type": "apex_domain",
                            "record_id": record_id,
                            "name": item_data.get("name"),
                            "program_name": program_name,
                            "notes": item_data.get("notes"),
                            "whois_status": item_data.get("whois_status"),
                        }
                    )
                elif action == "skipped":
                    skipped_count += 1
                    skipped_assets.append(
                        {
                            "record_id": record_id,
                            "name": item_data.get("name"),
                            "program_name": program_name,
                            "reason": "duplicate",
                        }
                    )
            else:
                failed_count += 1
                skipped_assets.append(
                    {
                        "name": item_data.get("name"),
                        "program_name": program_name,
                        "error": "processing_failed",
                    }
                )

        return (
            success_count,
            failed_count,
            created_count,
            updated_count,
            skipped_count,
            created_assets,
            updated_assets,
            skipped_assets,
        )
