"""
Batch Repository Base Class

Provides efficient bulk database operations for asset processing.
This class optimizes database connections and operations for large batches.
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

class BatchRepository:
    """Base class for batch database operations"""
    
    @classmethod
    async def bulk_create_or_update_subdomains(cls, subdomains: List[Dict], program_name: str) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update subdomains with rich event data collection

        Returns:
            Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict], List[Dict]]:
            (success_count, failed_count, created_count, updated_count, skipped_count,
             created_assets, updated_assets, skipped_assets, implicit_apex_created_events)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        out_of_scope_count = 0
        created_assets = []
        updated_assets = []
        skipped_assets = []
        implicit_apex_created_events: List[Dict] = []

        # Process subdomains individually to collect rich event data
        for i, subdomain_data in enumerate(subdomains):
            try:
                # Ensure program_name is set
                if not subdomain_data.get("program_name"):
                    subdomain_data["program_name"] = program_name

                # Call individual repository method to get rich event data
                record_id, action, event_data, apex_created_event = await SubdomainAssetsRepository.create_or_update_subdomain(subdomain_data)
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
                        # Create minimal skipped asset data
                        skipped_asset = {
                            "record_id": record_id,
                            "name": subdomain_data.get('name'),
                            "program_name": program_name,
                            "reason": "duplicate"
                        }
                        skipped_assets.append(skipped_asset)
                    elif action == "out_of_scope":
                        out_of_scope_count += 1
                        # Create out-of-scope asset data
                        out_of_scope_asset = {
                            "name": subdomain_data.get('name'),
                            "program_name": program_name,
                            "reason": "out_of_scope"
                        }
                        skipped_assets.append(out_of_scope_asset)
                else:
                    failed_count += 1
                    failed_asset = {
                        "name": subdomain_data.get('name'),
                        "program_name": program_name,
                        "error": "processing_failed"
                    }
                    # Add to skipped_assets for consistency with unified processor expectations
                    skipped_assets.append(failed_asset)

                # Yield control every 10 items to prevent event loop blocking
                # This prevents the API from becoming unresponsive during bulk processing
                if i % 10 == 0 and i > 0:
                    await asyncio.sleep(0)

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing subdomain {subdomain_data.get('name', 'unknown')}: {e}")
                failed_asset = {
                    "name": subdomain_data.get('name', 'unknown'),
                    "program_name": program_name,
                    "error": str(e)
                }
                skipped_assets.append(failed_asset)

        logger.info(f"Enhanced bulk subdomain processing completed: {success_count} success ({created_count} created, {updated_count} updated, {skipped_count} skipped, {out_of_scope_count} out_of_scope), {failed_count} failed")

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
    
    @classmethod
    async def bulk_create_or_update_ips(cls, ips: List[Dict], program_name: str) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update IPs with rich event data collection

        Returns:
            Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
            (success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        out_of_scope_count = 0
        created_assets = []
        updated_assets = []
        skipped_assets = []

        # Process IPs individually to collect rich event data
        for ip_data in ips:
            try:
                # Ensure program_name is set
                if not ip_data.get("program_name"):
                    ip_data["program_name"] = program_name

                # Call individual repository method to get rich event data
                result_tuple = await IPAssetsRepository.create_or_update_ip(ip_data)
                if len(result_tuple) == 3:
                    record_id, action, event_data = result_tuple
                else:
                    # Fallback for old format
                    record_id, action = result_tuple
                    event_data = None

                if action == "out_of_scope":
                    out_of_scope_count += 1
                    skipped_assets.append({
                        "ip_address": ip_data.get('ip'),
                        "program_name": program_name,
                        "reason": "out_of_scope"
                    })
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
                        # Create minimal skipped asset data
                        skipped_asset = {
                            "record_id": record_id,
                            "ip_address": ip_data.get('ip'),
                            "program_name": program_name,
                            "reason": "duplicate"
                        }
                        skipped_assets.append(skipped_asset)
                else:
                    failed_count += 1
                    failed_asset = {
                        "ip_address": ip_data.get('ip'),
                        "program_name": program_name,
                        "error": "processing_failed"
                    }
                    skipped_assets.append(failed_asset)

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing IP {ip_data.get('ip', 'unknown')}: {e}")
                failed_asset = {
                    "ip_address": ip_data.get('ip', 'unknown'),
                    "program_name": program_name,
                    "error": str(e)
                }
                skipped_assets.append(failed_asset)

        return success_count, failed_count, created_count, updated_count, skipped_count + out_of_scope_count, created_assets, updated_assets, skipped_assets
    
    @classmethod
    async def bulk_create_or_update_services(cls, services: List[Dict], program_name: str) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update services with rich event data collection

        Returns:
            Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
            (success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets = []
        updated_assets = []
        skipped_assets = []

        # Process services individually to collect event data
        for service_data in services:
            try:
                # Ensure program_name is set
                if not service_data.get("program_name"):
                    service_data["program_name"] = program_name

                # Call individual repository method
                result_tuple = await ServiceAssetsRepository.create_or_update_service(service_data)
                if len(result_tuple) == 3:
                    record_id, action, event_data = result_tuple
                else:
                    # Service repository only returns (record_id, action)
                    record_id, action = result_tuple
                    event_data = None

                if record_id:
                    success_count += 1
                    if action == "created":
                        created_count += 1
                        # Create event data for services
                        event_data = {
                            "event": "asset.created",
                            "asset_type": "service",
                            "record_id": record_id,
                            "ip": service_data.get('ip'),
                            "port": service_data.get('port'),
                            "program_name": program_name,
                            "service_name": service_data.get('service_name'),
                            "protocol": service_data.get('protocol', 'tcp'),
                            "banner": service_data.get('banner')
                        }
                        created_assets.append(event_data)
                    elif action == "updated":
                        updated_count += 1
                        # Create event data for services
                        event_data = {
                            "event": "asset.updated",
                            "asset_type": "service",
                            "record_id": record_id,
                            "ip": service_data.get('ip'),
                            "port": service_data.get('port'),
                            "program_name": program_name,
                            "service_name": service_data.get('service_name'),
                            "protocol": service_data.get('protocol', 'tcp'),
                            "banner": service_data.get('banner')
                        }
                        updated_assets.append(event_data)
                    elif action == "skipped":
                        skipped_count += 1
                        # Create minimal skipped asset data
                        skipped_asset = {
                            "record_id": record_id,
                            "ip": service_data.get('ip'),
                            "port": service_data.get('port'),
                            "program_name": program_name,
                            "reason": "duplicate"
                        }
                        skipped_assets.append(skipped_asset)
                else:
                    failed_count += 1
                    failed_asset = {
                        "ip": service_data.get('ip'),
                        "port": service_data.get('port'),
                        "program_name": program_name,
                        "error": "processing_failed"
                    }
                    skipped_assets.append(failed_asset)

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing service {service_data.get('ip', 'unknown')}:{service_data.get('port', 'unknown')}: {e}")
                failed_asset = {
                    "ip": service_data.get('ip', 'unknown'),
                    "port": service_data.get('port', 'unknown'),
                    "program_name": program_name,
                    "error": str(e)
                }
                skipped_assets.append(failed_asset)

        return success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets
    
    @classmethod
    async def bulk_create_or_update_urls(cls, urls: List[Dict], program_name: str) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update URLs with rich event data collection

        Returns:
            Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
            (success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets = []
        updated_assets = []
        skipped_assets = []

        # Process URLs individually to collect event data
        for url_data in urls:
            try:
                # Ensure program_name is set
                if not url_data.get("program_name"):
                    url_data["program_name"] = program_name

                # Call individual repository method
                result_tuple = await UrlAssetsRepository.create_or_update_url(url_data)
                if len(result_tuple) == 3:
                    record_id, action, event_data = result_tuple
                else:
                    # URL repository only returns (record_id, action)
                    record_id, action = result_tuple
                    event_data = None

                if record_id:
                    success_count += 1
                    if action == "created":
                        created_count += 1
                        # Create event data for URLs
                        event_data = {
                            "event": "asset.created",
                            "asset_type": "url",
                            "record_id": record_id,
                            "url": url_data.get('url'),
                            "path": url_data.get('path'),
                            "program_name": program_name,
                            "http_status_code": url_data.get('http_status_code'),
                            "content_type": url_data.get('content_type'),
                            "title": url_data.get('title'),
                            "technologies": url_data.get('technologies', [])
                        }
                        created_assets.append(event_data)
                    elif action == "updated":
                        updated_count += 1
                        # Create event data for URLs
                        event_data = {
                            "event": "asset.updated",
                            "asset_type": "url",
                            "record_id": record_id,
                            "url": url_data.get('url'),
                            "path": url_data.get('path'),
                            "program_name": program_name,
                            "http_status_code": url_data.get('http_status_code'),
                            "content_type": url_data.get('content_type'),
                            "title": url_data.get('title'),
                            "technologies": url_data.get('technologies', [])
                        }
                        updated_assets.append(event_data)
                    elif action == "skipped":
                        skipped_count += 1
                        # Create minimal skipped asset data
                        skipped_asset = {
                            "record_id": record_id,
                            "url": url_data.get('url'),
                            "program_name": program_name,
                            "reason": "duplicate"
                        }
                        skipped_assets.append(skipped_asset)
                else:
                    failed_count += 1
                    failed_asset = {
                        "url": url_data.get('url'),
                        "program_name": program_name,
                        "error": "processing_failed"
                    }
                    skipped_assets.append(failed_asset)

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing URL {url_data.get('url', 'unknown')}: {e}")
                failed_asset = {
                    "url": url_data.get('url', 'unknown'),
                    "program_name": program_name,
                    "error": str(e)
                }
                skipped_assets.append(failed_asset)

        return success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets
    
    @classmethod
    async def bulk_create_or_update_certificates(cls, certificates: List[Dict], program_name: str) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update certificates with rich event data collection

        Returns:
            Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
            (success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets = []
        updated_assets = []
        skipped_assets = []

        # Process certificates individually to collect event data
        for certificate_data in certificates:
            try:
                # Ensure program_name is set
                if not certificate_data.get("program_name"):
                    certificate_data["program_name"] = program_name

                # Call individual repository method
                result_tuple = await CertificateAssetsRepository.create_or_update_certificate(certificate_data)
                if len(result_tuple) == 3:
                    record_id, action, event_data = result_tuple
                else:
                    # Certificate repository only returns (record_id, action)
                    record_id, action = result_tuple
                    event_data = None

                if record_id:
                    success_count += 1
                    if action == "created":
                        created_count += 1
                        # Create event data for certificates
                        event_data = {
                            "event": "asset.created",
                            "asset_type": "certificate",
                            "record_id": record_id,
                            "subject_dn": certificate_data.get('subject_dn'),
                            "program_name": program_name,
                            "subject_cn": certificate_data.get('subject_cn'),
                            "issuer_cn": certificate_data.get('issuer_cn'),
                            "valid_from": certificate_data.get('valid_from'),
                            "valid_until": certificate_data.get('valid_until'),
                            "serial_number": certificate_data.get('serial_number')
                        }
                        created_assets.append(event_data)
                    elif action == "updated":
                        updated_count += 1
                        # Create event data for certificates
                        event_data = {
                            "event": "asset.updated",
                            "asset_type": "certificate",
                            "record_id": record_id,
                            "subject_dn": certificate_data.get('subject_dn'),
                            "program_name": program_name,
                            "subject_cn": certificate_data.get('subject_cn'),
                            "issuer_cn": certificate_data.get('issuer_cn'),
                            "valid_from": certificate_data.get('valid_from'),
                            "valid_until": certificate_data.get('valid_until'),
                            "serial_number": certificate_data.get('serial_number')
                        }
                        updated_assets.append(event_data)
                    elif action == "skipped":
                        skipped_count += 1
                        # Create minimal skipped asset data
                        skipped_asset = {
                            "record_id": record_id,
                            "subject_dn": certificate_data.get('subject_dn'),
                            "program_name": program_name,
                            "reason": "duplicate"
                        }
                        skipped_assets.append(skipped_asset)
                else:
                    failed_count += 1
                    failed_asset = {
                        "subject_dn": certificate_data.get('subject_dn'),
                        "program_name": program_name,
                        "error": "processing_failed"
                    }
                    skipped_assets.append(failed_asset)

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing certificate {certificate_data.get('subject_dn', 'unknown')}: {e}")
                failed_asset = {
                    "subject_dn": certificate_data.get('subject_dn', 'unknown'),
                    "program_name": program_name,
                    "error": str(e)
                }
                skipped_assets.append(failed_asset)

        return success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets
    
    
    @classmethod
    async def bulk_create_or_update_apex_domains(cls, apex_domains: List[Dict], program_name: str) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
        """
        Enhanced bulk create or update apex domains with rich event data collection

        Returns:
            Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
            (success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets)
        """
        success_count = 0
        failed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        created_assets = []
        updated_assets = []
        skipped_assets = []

        # Process apex domains individually to collect event data
        for apex_domain_data in apex_domains:
            try:
                # Ensure program_name is set
                if not apex_domain_data.get("program_name"):
                    apex_domain_data["program_name"] = program_name

                # Call individual repository method
                result_tuple = await ApexDomainAssetsRepository.create_or_update_apex_domain(apex_domain_data)
                if len(result_tuple) == 3:
                    record_id, action, event_data = result_tuple
                else:
                    # Apex domain repository only returns (record_id, action)
                    record_id, action = result_tuple
                    event_data = None

                if record_id:
                    success_count += 1
                    if action == "created":
                        created_count += 1
                        # Create event data for apex domains
                        event_data = {
                            "event": "asset.created",
                            "asset_type": "apex_domain",
                            "record_id": record_id,
                            "name": apex_domain_data.get('name'),
                            "program_name": program_name,
                            "notes": apex_domain_data.get('notes'),
                            "whois_status": apex_domain_data.get('whois_status'),
                        }
                        created_assets.append(event_data)
                    elif action == "updated":
                        updated_count += 1
                        # Create event data for apex domains
                        event_data = {
                            "event": "asset.updated",
                            "asset_type": "apex_domain",
                            "record_id": record_id,
                            "name": apex_domain_data.get('name'),
                            "program_name": program_name,
                            "notes": apex_domain_data.get('notes'),
                            "whois_status": apex_domain_data.get('whois_status'),
                        }
                        updated_assets.append(event_data)
                    elif action == "skipped":
                        skipped_count += 1
                        # Create minimal skipped asset data
                        skipped_asset = {
                            "record_id": record_id,
                            "name": apex_domain_data.get('name'),
                            "program_name": program_name,
                            "reason": "duplicate"
                        }
                        skipped_assets.append(skipped_asset)
                else:
                    failed_count += 1
                    failed_asset = {
                        "name": apex_domain_data.get('name'),
                        "program_name": program_name,
                        "error": "processing_failed"
                    }
                    skipped_assets.append(failed_asset)

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing apex domain {apex_domain_data.get('name', 'unknown')}: {e}")
                failed_asset = {
                    "name": apex_domain_data.get('name', 'unknown'),
                    "program_name": program_name,
                    "error": str(e)
                }
                skipped_assets.append(failed_asset)

        return success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets
    