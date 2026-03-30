"""
Unified Asset Processor - Single Method for All Asset Processing

This module provides a single, unified approach to asset processing that:
- Handles all asset types consistently
- Uses intelligent batching
- Always processes asynchronously
- Publishes events uniformly
- Is much simpler to maintain and test
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field

from repository.apexdomain_assets_repo import ApexDomainAssetsRepository
from repository.subdomain_assets_repo import SubdomainAssetsRepository
from repository.ip_assets_repo import IPAssetsRepository
from repository.service_assets_repo import ServiceAssetsRepository
from repository.certificate_assets_repo import CertificateAssetsRepository
from repository.url_assets_repo import UrlAssetsRepository
from repository.batch_repository import BatchRepository
from .event_publisher import publisher

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single asset"""
    asset_type: str
    asset_name: str
    action: str  # 'created', 'updated', 'skipped', 'out_of_scope', 'failed'
    record_id: Optional[str] = None
    error: Optional[str] = None
    event_payload: Optional[Dict[str, Any]] = None


@dataclass
class AssetBatchResult:
    """Result of processing a batch of assets"""
    asset_type: str
    total_count: int = 0
    success_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    out_of_scope_count: int = 0
    failed_count: int = 0
    created_assets: List[Dict[str, Any]] = field(default_factory=list)
    updated_assets: List[Dict[str, Any]] = field(default_factory=list)
    skipped_assets: List[Dict[str, Any]] = field(default_factory=list)
    failed_assets: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    implicit_apex_created_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class UnifiedProcessingResult:
    """Complete result of unified asset processing"""
    job_id: str
    program_name: str
    status: str = "processing"
    total_assets: int = 0
    processed_assets: int = 0
    success_count: int = 0
    failed_count: int = 0
    asset_results: Dict[str, AssetBatchResult] = field(default_factory=dict)
    processing_time: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class UnifiedAssetProcessor:
    """
    Single unified asset processor that handles all asset types consistently.

    Key features:
    - Always async (never blocks API)
    - Intelligent batching based on actual load
    - Consistent event publishing
    - Simple maintenance and testing
    """

    def __init__(self):
        self.active_jobs: Dict[str, UnifiedProcessingResult] = {}
        self.asset_type_handlers: Dict[str, Callable] = {
            'ip': self._handle_ip_assets,
            'subdomain': self._handle_subdomain_assets,
            'url': self._handle_url_assets,
            'service': self._handle_service_assets,
            'certificate': self._handle_certificate_assets,
            'apex_domain': self._handle_apex_domain_assets,
            # Note: nuclei and typosquat findings are now handled by unified_findings_processor
        }

    async def process_assets_unified(
        self,
        asset_data: Dict[str, List],
        program_name: str
    ) -> str:
        """
        Main unified processing method.

        Args:
            asset_data: Dict with asset types as keys and lists of assets as values
            program_name: Name of the program these assets belong to

        Returns:
            job_id: Unique identifier for tracking the processing job
        """
        if not program_name:
            raise ValueError("program_name is required for asset processing")

        # Generate job ID and create result object
        job_id = str(uuid.uuid4())
        result = UnifiedProcessingResult(
            job_id=job_id,
            program_name=program_name,
            total_assets=self._calculate_total_assets(asset_data)
        )

        self.active_jobs[job_id] = result

        # Start async processing
        asyncio.create_task(self._process_assets_async(job_id, asset_data, program_name))

        logger.info(f"Started unified asset processing job {job_id} with {result.total_assets} assets")
        return job_id

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a processing job"""
        result = self.active_jobs.get(job_id)
        if not result:
            return None

        # # Debug the asset results
        # if result.asset_results:
        #     for asset_type, batch_result in result.asset_results.items():
        #         logger.info(f"Asset result for {asset_type}: created_assets={len(batch_result.created_assets)}, updated_assets={len(batch_result.updated_assets)}, skipped_assets={len(batch_result.skipped_assets)}, failed_assets={len(batch_result.failed_assets)}")

        # Build the asset_results
        asset_results = {
            asset_type: {
                "total_count": batch_result.total_count,
                "success_count": batch_result.success_count,
                "created_count": batch_result.created_count,
                "updated_count": batch_result.updated_count,
                "skipped_count": batch_result.skipped_count,
                "out_of_scope_count": batch_result.out_of_scope_count,
                "failed_count": batch_result.failed_count,
                "created_assets": batch_result.created_assets,
                "updated_assets": batch_result.updated_assets,
                "skipped_assets": batch_result.skipped_assets,
                "failed_assets": batch_result.failed_assets,
                "errors": batch_result.errors[:5]  # Show first 5 errors
            }
            for asset_type, batch_result in result.asset_results.items()
        }

        response = {
            "job_id": result.job_id,
            "program_name": result.program_name,
            "status": result.status,
            "total_assets": result.total_assets,
            "processed_assets": result.processed_assets,
            "success_count": result.success_count,
            "failed_count": result.failed_count,
            "processing_time": result.processing_time,
            "created_at": result.created_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "error": result.error,
            "summary": {
                "total_assets": result.total_assets,
                "asset_types": {asset_type: batch_result.total_count for asset_type, batch_result in result.asset_results.items()},
                "detailed_counts": asset_results
            },
            "asset_results": asset_results
        }

        return response

    def _calculate_total_assets(self, asset_data: Dict[str, List]) -> int:
        """Calculate total number of assets across all types"""
        return sum(len(assets) for assets in asset_data.values() if isinstance(assets, list))

    def _get_processing_order(self) -> List[str]:
        """Get the optimal processing order for asset types"""
        return [
            "ip",           # Process IPs first
            "apex_domain",  # Then apex domains
            "subdomain",    # Then subdomains (may reference existing IPs)
            "service",      # Then services (URLs need service_id)
            "certificate",  # Then certificates (URLs need certificate_id for HTTPS)
            "url",          # Then URLs (can resolve certificate, service, subdomain FKs)
            "nuclei",       # Then nuclei findings
            "typosquat"     # Finally typosquat findings
        ]

    def _should_use_bulk_processing(self, asset_count: int) -> bool:
        """Always use bulk processing for consistency and rich event data"""
        return True  # Always use bulk processing for rich event data collection

    async def _process_assets_async(
        self,
        job_id: str,
        asset_data: Dict[str, List],
        program_name: str
    ):
        """Internal async processing method"""
        start_time = time.time()
        result = self.active_jobs[job_id]

        try:
            # Process asset types in optimal order
            for asset_type in self._get_processing_order():
                if asset_type in asset_data and asset_data[asset_type]:
                    assets = asset_data[asset_type]

                    # Process this asset type
                    batch_result = await self._process_asset_type(
                        asset_type, assets, program_name
                    )

                    result.asset_results[asset_type] = batch_result
                    result.processed_assets += batch_result.total_count
                    result.success_count += batch_result.success_count
                    result.failed_count += batch_result.failed_count

            # Mark job as completed
            result.status = "completed"
            result.completed_at = datetime.now(timezone.utc)
            result.processing_time = time.time() - start_time

            # Publish completion events
            await self._publish_completion_events(result)

            logger.info(f"Completed unified asset processing job {job_id} in {result.processing_time:.2f}s")

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            result.completed_at = datetime.now(timezone.utc)
            result.processing_time = time.time() - start_time
            logger.error(f"Failed unified asset processing job {job_id}: {e}")

        finally:
            # Clean up old jobs after some time
            asyncio.create_task(self._cleanup_job_after_delay(job_id, 3600))  # 1 hour

    async def _process_asset_type(
        self,
        asset_type: str,
        assets: List[Dict],
        program_name: str
    ) -> AssetBatchResult:
        """Process a single asset type"""
        result = AssetBatchResult(asset_type=asset_type, total_count=len(assets))

        try:
            # Get the appropriate handler
            handler = self.asset_type_handlers.get(asset_type)
            if not handler:
                result.errors.append(f"Unknown asset type: {asset_type}")
                result.failed_count = len(assets)
                return result

            # Always use bulk processing for rich event data collection
            await self._process_bulk(handler, assets, program_name, result)

        except Exception as e:
            logger.error(f"Error processing {asset_type} batch: {e}")
            result.errors.append(str(e))
            result.failed_count = len(assets)

        return result

    async def _process_bulk(
        self,
        handler: Callable,
        assets: List[Dict],
        program_name: str,
        result: AssetBatchResult
    ):
        """Process assets using bulk operations"""
        try:
            # Use bulk repository methods for large batches
            bulk_result = await handler(assets, program_name, bulk=True)

            # Handle different return formats based on asset type
            if len(bulk_result) == 9:
                # Subdomain bulk: includes implicit apex_domain.created payloads
                (
                    success_count,
                    failed_count,
                    created_count,
                    updated_count,
                    skipped_count,
                    created_assets,
                    updated_assets,
                    skipped_assets,
                    implicit_apex,
                ) = bulk_result
                result.success_count = success_count
                result.failed_count = failed_count
                result.created_count = created_count
                result.updated_count = updated_count
                result.skipped_count = skipped_count
                result.created_assets = created_assets
                result.updated_assets = updated_assets
                result.skipped_assets = skipped_assets
                result.implicit_apex_created_events = implicit_apex
                result.failed_assets = []  # Bulk processing tracks failures via failed_count
            elif len(bulk_result) == 8:
                # Detailed format (IPs, URLs, apex_domain batches, etc.)
                success_count, failed_count, created_count, updated_count, skipped_count, created_assets, updated_assets, skipped_assets = bulk_result
                result.success_count = success_count
                result.failed_count = failed_count
                result.created_count = created_count
                result.updated_count = updated_count
                result.skipped_count = skipped_count
                result.created_assets = created_assets
                result.updated_assets = updated_assets
                result.skipped_assets = skipped_assets
                result.failed_assets = []  # Bulk processing tracks failures via failed_count
            elif len(bulk_result) == 2:
                # Simple format (other asset types)
                success_count, failed_count = bulk_result
                result.success_count = success_count
                result.failed_count = failed_count
                # For simple bulk processing, we don't have detailed counts
                result.created_count = 0
                result.updated_count = 0
                result.skipped_count = 0
                result.created_assets = []
                result.updated_assets = []
                result.skipped_assets = []
                result.failed_assets = []
            else:
                raise ValueError(f"Unexpected bulk result format with {len(bulk_result)} elements")

        except Exception as e:
            logger.error(f"Bulk processing failed for {result.asset_type}: {e}")
            result.failed_count = len(assets)
            result.errors.append(str(e))



    async def _process_individual(
        self,
        handler: Callable,
        assets: List[Dict],
        program_name: str,
        result: AssetBatchResult
    ):
        """Process assets individually"""
        for asset_data in assets:
            try:
                # Ensure program_name is set
                if not asset_data.get("program_name"):
                    asset_data["program_name"] = program_name

                # Process individual asset
                result_tuple = await handler(asset_data, program_name, bulk=False)
                apex_created_event: Optional[Dict[str, Any]] = None
                if len(result_tuple) == 4:
                    record_id, action, event_data, apex_created_event = result_tuple
                elif len(result_tuple) == 3:
                    record_id, action, event_data = result_tuple
                else:
                    # Fallback for old format
                    record_id, action = result_tuple
                    event_data = None

                if apex_created_event is not None:
                    result.implicit_apex_created_events.append(apex_created_event)

                if record_id:
                    result.success_count += 1
                    if action == "created":
                        result.created_count += 1
                        # Use rich event_data if available, otherwise create minimal data
                        if event_data:
                            result.created_assets.append(event_data)
                        else:
                            result.created_assets.append({
                                "record_id": record_id,
                                "name": self._extract_asset_name(result.asset_type, asset_data),
                                "program_name": program_name
                            })
                    elif action == "updated":
                        result.updated_count += 1
                        # Use rich event_data if available, otherwise create minimal data
                        if event_data:
                            result.updated_assets.append(event_data)
                        else:
                            result.updated_assets.append({
                                "record_id": record_id,
                                "name": self._extract_asset_name(result.asset_type, asset_data),
                                "program_name": program_name
                            })
                    elif action == "skipped":
                        result.skipped_count += 1
                        skipped_asset = {
                            "name": self._extract_asset_name(result.asset_type, asset_data),
                            "program_name": program_name,
                            "reason": "duplicate"
                        }
                        # For nuclei findings, include constraint fields for proper deduplication
                        if result.asset_type == "nuclei":
                            skipped_asset.update({
                                "url": asset_data.get("url", ""),
                                "template_id": asset_data.get("template_id", ""),
                                "matcher_name": asset_data.get("matcher_name", ""),
                                "matched_at": asset_data.get("matched_at", "")
                            })
                        result.skipped_assets.append(skipped_asset)
                    elif action == "out_of_scope":
                        result.out_of_scope_count += 1
                        out_of_scope_asset = {
                            "name": self._extract_asset_name(result.asset_type, asset_data),
                            "program_name": program_name,
                            "reason": "out_of_scope"
                        }
                        # For nuclei findings, include constraint fields for proper deduplication
                        if result.asset_type == "nuclei":
                            out_of_scope_asset.update({
                                "url": asset_data.get("url", ""),
                                "template_id": asset_data.get("template_id", ""),
                                "matcher_name": asset_data.get("matcher_name", ""),
                                "matched_at": asset_data.get("matched_at", "")
                            })
                        result.skipped_assets.append(out_of_scope_asset)
                else:
                    result.failed_count += 1
                    failed_asset = {
                        "name": self._extract_asset_name(result.asset_type, asset_data),
                        "program_name": program_name,
                        "error": "processing_failed"
                    }
                    # For nuclei findings, include constraint fields for proper deduplication
                    if result.asset_type == "nuclei":
                        failed_asset.update({
                            "url": asset_data.get("url", ""),
                            "template_id": asset_data.get("template_id", ""),
                            "matcher_name": asset_data.get("matcher_name", ""),
                            "matched_at": asset_data.get("matched_at", "")
                        })
                    result.failed_assets.append(failed_asset)
                    result.errors.append(f"Failed to process {result.asset_type} asset")

            except Exception as e:
                result.failed_count += 1
                failed_asset = {
                    "name": self._extract_asset_name(result.asset_type, asset_data),
                    "program_name": program_name,
                    "error": str(e)
                }
                # For nuclei findings, include constraint fields for proper deduplication
                if result.asset_type == "nuclei":
                    failed_asset.update({
                        "url": asset_data.get("url", ""),
                        "template_id": asset_data.get("template_id", ""),
                        "matcher_name": asset_data.get("matcher_name", ""),
                        "matched_at": asset_data.get("matched_at", "")
                    })
                result.failed_assets.append(failed_asset)
                result.errors.append(f"Error processing {result.asset_type} asset: {str(e)}")

    async def _publish_completion_events(self, result: UnifiedProcessingResult):
        """Publish completion events for the processing job"""
        try:
            # Publish summary event - DISABLED: events.assets.processing.completed removed
            # await publisher.publish_immediate(
            #     "events.assets.processing.completed",
            #     {
            #         "event": "asset_processing_completed",
            #         "job_id": result.job_id,
            #         "program_name": result.program_name,
            #         "total_assets": result.total_assets,
            #         "success_count": result.success_count,
            #         "failed_count": result.failed_count,
            #         "processing_time": result.processing_time,
            #         "asset_summary": {
            #             asset_type: {
            #                 "total": batch_result.total_count,
            #                 "created": batch_result.created_count,
            #                 "updated": batch_result.updated_count,
            #                 "failed": batch_result.failed_count
            #             }
            #             for asset_type, batch_result in result.asset_results.items()
            #         }
            #     }
            # )

            # Publish individual asset creation events
            for asset_type, batch_result in result.asset_results.items():
                await self._publish_asset_events(asset_type, batch_result, result.program_name)

            subdomain_batch = result.asset_results.get("subdomain")
            if subdomain_batch and subdomain_batch.implicit_apex_created_events:
                await self._publish_asset_events_by_action(
                    "apex_domain",
                    subdomain_batch.implicit_apex_created_events,
                    "created",
                    result.program_name,
                )

        except Exception as e:
            logger.error(f"Failed to publish completion events for job {result.job_id}: {e}")

    async def _publish_asset_events(
        self,
        asset_type: str,
        batch_result: AssetBatchResult,
        program_name: str
    ):
        """Publish events for newly created and updated assets"""
        try:
            # Publish events for created assets
            await self._publish_asset_events_by_action(
                asset_type, batch_result.created_assets, "created", program_name
            )

            # Publish events for updated assets
            await self._publish_asset_events_by_action(
                asset_type, batch_result.updated_assets, "updated", program_name
            )

        except Exception as e:
            logger.error(f"Failed to publish asset events for {asset_type}: {e}")

    async def _publish_asset_events_by_action(
        self,
        asset_type: str,
        assets: List[Dict[str, Any]],
        action: str,
        program_name: str
    ):
        """Publish rich events for assets with a specific action (created/updated)"""
        try:
            # Always publish individual rich events for each asset, regardless of batch size
            for i, asset in enumerate(assets):
                # Use the rich event data if available, otherwise create minimal event
                if "event" in asset:
                    # Rich event data from repository - publish as-is
                    if asset_type == "typosquat":
                        # Typosquat findings use findings events
                        await publisher.publish(
                            f"events.findings.{asset_type}.{action}",
                            asset
                        )
                    elif asset_type == "nuclei":
                        # Nuclei findings use findings events
                        await publisher.publish(
                            f"events.findings.{asset_type}.{action}",
                            asset
                        )
                    else:
                        # Regular assets use asset events
                        await publisher.publish(
                            f"events.assets.{asset_type}.{action}",
                            asset
                        )
                else:
                    # Fallback for minimal data - create rich event from minimal data
                    if asset_type == "typosquat":
                        # Typosquat findings use findings events
                        await publisher.publish(
                            f"events.findings.{asset_type}.{action}",
                            {
                                "event": f"finding.{action}",
                                "finding_type": asset_type,
                                "record_id": asset["record_id"],
                                "name": asset["name"],
                                "program_name": program_name,
                                "asset_type": asset_type,
                                "action": action,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                    elif asset_type == "nuclei":
                        # Nuclei findings use findings events
                        await publisher.publish(
                            f"events.findings.{asset_type}.{action}",
                            {
                                "event": f"finding.{action}",
                                "finding_type": asset_type,
                                "record_id": asset["record_id"],
                                "name": asset["name"],
                                "program_name": program_name,
                                "asset_type": asset_type,
                                "action": action,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                    else:
                        # Regular assets use asset events
                        await publisher.publish(
                            f"events.assets.{asset_type}.{action}",
                            {
                                "event": f"asset.{action}",
                                "asset_type": asset_type,
                                "record_id": asset["record_id"],
                                "name": asset["name"],
                                "program_name": program_name,
                                "action": action,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )

                # Yield control every 10 events to prevent event loop blocking
                # This prevents the API from becoming unresponsive during event publishing
                if i % 10 == 0 and i > 0:
                    await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Failed to publish {action} asset events for {asset_type}: {e}")

    # Asset type handlers
    async def _handle_ip_assets(self, assets: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle IP asset processing"""
        # Handle the case where assets is a single dict instead of a list
        if isinstance(assets, dict):
            assets = [assets]

        if bulk:
            return await BatchRepository.bulk_create_or_update_ips(assets, program_name)
        else:
            result_tuple = await IPAssetsRepository.create_or_update_ip(assets[0])
            if len(result_tuple) == 3:
                record_id, action, event_data = result_tuple
            else:
                # Fallback for old format
                record_id, action = result_tuple
                event_data = None
            return record_id, action, event_data

    async def _handle_subdomain_assets(self, assets: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle subdomain asset processing"""
        # Handle the case where assets is a single dict instead of a list
        if isinstance(assets, dict):
            assets = [assets]

        if bulk:
            return await BatchRepository.bulk_create_or_update_subdomains(assets, program_name)
        else:
            return await SubdomainAssetsRepository.create_or_update_subdomain(assets[0])

    async def _handle_url_assets(self, assets: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle URL asset processing"""
        # Handle the case where assets is a single dict instead of a list
        if isinstance(assets, dict):
            assets = [assets]

        if bulk:
            return await BatchRepository.bulk_create_or_update_urls(assets, program_name)
        else:
            result_tuple = await UrlAssetsRepository.create_or_update_url(assets[0])
            if len(result_tuple) == 3:
                record_id, action, event_data = result_tuple
            else:
                # Fallback for old format
                record_id, action = result_tuple
                event_data = None
            return record_id, action, event_data

    async def _handle_service_assets(self, assets: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle service asset processing"""
        # Handle the case where assets is a single dict instead of a list
        if isinstance(assets, dict):
            assets = [assets]

        if bulk:
            return await BatchRepository.bulk_create_or_update_services(assets, program_name)
        else:
            result_tuple = await ServiceAssetsRepository.create_or_update_service(assets[0])
            if len(result_tuple) == 3:
                record_id, action, event_data = result_tuple
            else:
                # Fallback for old format
                record_id, action = result_tuple
                event_data = None
            return record_id, action, event_data

    async def _handle_certificate_assets(self, assets: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle certificate asset processing"""
        # Handle the case where assets is a single dict instead of a list
        if isinstance(assets, dict):
            assets = [assets]

        if bulk:
            return await BatchRepository.bulk_create_or_update_certificates(assets, program_name)
        else:
            result_tuple = await CertificateAssetsRepository.create_or_update_certificate(assets[0])
            if len(result_tuple) == 3:
                record_id, action, event_data = result_tuple
            else:
                # Fallback for old format
                record_id, action = result_tuple
                event_data = None
            return record_id, action, event_data


    async def _handle_apex_domain_assets(self, assets: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle apex domain asset processing"""
        # Handle the case where assets is a single dict instead of a list
        if isinstance(assets, dict):
            assets = [assets]

        if bulk:
            return await BatchRepository.bulk_create_or_update_apex_domains(assets, program_name)
        else:
            result_tuple = await ApexDomainAssetsRepository.create_or_update_apex_domain(assets[0])
            if len(result_tuple) == 3:
                record_id, action, event_data = result_tuple
            else:
                # Fallback for old format
                record_id, action = result_tuple
                event_data = None
            return record_id, action, event_data


    def _extract_asset_name(self, asset_type: str, asset: Dict[str, Any]) -> str:
        """Extract the appropriate name field based on asset type"""
        if asset_type in ["subdomain", "apex_domain"]:
            return asset.get("name", "unknown")
        elif asset_type == "ip":
            return asset.get("ip", "unknown")
        elif asset_type == "url":
            return asset.get("url", "unknown")
        elif asset_type == "service":
            ip = asset.get("ip", "unknown")
            port = asset.get("port", "unknown")
            return f"{ip}:{port}"
        elif asset_type == "certificate":
            return asset.get("subject_dn", "unknown")
        else:
            return "unknown"

    async def _cleanup_job_after_delay(self, job_id: str, delay_seconds: int):
        """Clean up completed jobs after a delay"""
        await asyncio.sleep(delay_seconds)
        if job_id in self.active_jobs:
            del self.active_jobs[job_id]

    async def shutdown(self):
        """Shutdown the unified asset processor gracefully"""
        try:
            # Cancel any active jobs
            for job_id, result in self.active_jobs.items():
                if result.status == "processing":
                    result.status = "cancelled"
                    result.error = "Processor shutdown"
                    result.completed_at = datetime.now(timezone.utc)
            # Clear active jobs
            self.active_jobs.clear()

        except Exception as e:
            logger.error(f"Error during unified asset processor shutdown: {e}")
            raise


# Global instance
unified_asset_processor = UnifiedAssetProcessor()
