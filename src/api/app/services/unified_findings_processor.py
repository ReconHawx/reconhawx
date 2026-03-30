"""
Unified Findings Processor - Dedicated processor for security findings

This module provides a dedicated processor for security findings that:
- Handles findings separately from assets
- Uses appropriate event types for findings
- Returns findings results in the correct format
- Is optimized for findings-specific processing
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field

from repository.nuclei_findings_repo import NucleiFindingsRepository
from repository.typosquat_findings_repo import TyposquatFindingsRepository
from repository.wpscan_findings_repo import WPScanFindingsRepository
from .event_publisher import publisher
from .recordedfuture_api_client import change_playbook_alert_status

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single finding"""
    finding_type: str
    finding_name: str
    action: str  # 'created', 'updated', 'skipped', 'failed'
    record_id: Optional[str] = None
    error: Optional[str] = None
    event_payload: Optional[Dict[str, Any]] = None


@dataclass
class FindingBatchResult:
    """Result of processing a batch of findings"""
    finding_type: str
    total_count: int = 0
    success_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    created_findings: List[Dict[str, Any]] = field(default_factory=list)
    updated_findings: List[Dict[str, Any]] = field(default_factory=list)
    skipped_findings: List[Dict[str, Any]] = field(default_factory=list)
    failed_findings: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class UnifiedFindingsProcessingResult:
    """Complete result of unified findings processing"""
    job_id: str
    program_name: str
    status: str = "processing"
    total_findings: int = 0
    processed_findings: int = 0
    success_count: int = 0
    failed_count: int = 0
    finding_results: Dict[str, FindingBatchResult] = field(default_factory=dict)
    processing_time: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class UnifiedFindingsProcessor:
    """
    Dedicated processor for security findings.

    Key features:
    - Always async (never blocks API)
    - Intelligent batching based on actual load
    - Consistent event publishing for findings
    - Simple maintenance and testing
    """

    def __init__(self):
        self.active_jobs: Dict[str, UnifiedFindingsProcessingResult] = {}
        self.finding_type_handlers: Dict[str, Callable] = {
            'nuclei': self._handle_nuclei_findings,
            'typosquat_domain': self._handle_typosquat_domain_findings,
            'wpscan': self._handle_wpscan_findings,
        }

    async def process_findings_unified(
        self,
        finding_data: Dict[str, List],
        program_name: str,
        workflow_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Main unified findings processing method.

        Args:
            finding_data: Dict with finding types as keys and lists of findings as values
            program_name: Name of the program these findings belong to
            workflow_context: Optional workflow context for job registration
                - workflow_id: ID of the workflow
                - execution_id: ID of the workflow execution
                - step_name: Name of the workflow step

        Returns:
            job_id: Unique identifier for tracking the processing job
        """
        if not program_name:
            raise ValueError("program_name is required for findings processing")

        # Generate job ID and create result object
        job_id = str(uuid.uuid4())
        result = UnifiedFindingsProcessingResult(
            job_id=job_id,
            program_name=program_name,
            total_findings=self._calculate_total_findings(finding_data)
        )

        self.active_jobs[job_id] = result

        # Register job with asset coordinator if workflow context is provided
        #if workflow_context:
        #    await self._register_job_with_coordinator(job_id, workflow_context, program_name)

        # Start async processing
        asyncio.create_task(self._process_findings_async(job_id, finding_data, program_name))

        logger.info(f"Started unified findings processing job {job_id} with {result.total_findings} findings")
        if workflow_context:
            logger.info(f"🔍 WORKFLOW REGISTRATION: Job {job_id} registered with workflow context: {workflow_context}")
        return job_id

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a processing job"""
        result = self.active_jobs.get(job_id)
        if not result:
            return None

        # Build the finding_results
        finding_results = {
            finding_type: {
                "total_count": batch_result.total_count,
                "success_count": batch_result.success_count,
                "created_count": batch_result.created_count,
                "updated_count": batch_result.updated_count,
                "skipped_count": batch_result.skipped_count,
                "failed_count": batch_result.failed_count,
                "created_findings": batch_result.created_findings,
                "updated_findings": batch_result.updated_findings,
                "skipped_findings": batch_result.skipped_findings,
                "failed_findings": batch_result.failed_findings,
                "errors": batch_result.errors[:5]  # Show first 5 errors
            }
            for finding_type, batch_result in result.finding_results.items()
        }

        response = {
            "job_id": result.job_id,
            "program_name": result.program_name,
            "status": result.status,
            "total_findings": result.total_findings,
            "processed_findings": result.processed_findings,
            "success_count": result.success_count,
            "failed_count": result.failed_count,
            "processing_time": result.processing_time,
            "created_at": result.created_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "error": result.error,
            "summary": {
                "total_findings": result.total_findings,
                "finding_types": {finding_type: batch_result.total_count for finding_type, batch_result in result.finding_results.items()},
                "detailed_counts": finding_results
            },
            "finding_results": finding_results
        }

        return response

    def _calculate_total_findings(self, finding_data: Dict[str, List]) -> int:
        """Calculate total number of findings across all types"""
        return sum(len(findings) for findings in finding_data.values() if isinstance(findings, list))

    def _get_processing_order(self) -> List[str]:
        """Get the optimal processing order for finding types"""
        return [
            "nuclei",             # Process nuclei findings first
            "typosquat_domain",  # Then typosquat domain findings
            "wpscan"             # Then WPScan findings
        ]

    def _should_use_bulk_processing(self, finding_count: int) -> bool:
        """Always use bulk processing for consistency and rich event data"""
        return True  # Always use bulk processing for rich event data collection

    async def _process_findings_async(
        self,
        job_id: str,
        finding_data: Dict[str, List],
        program_name: str
    ):
        """Internal async processing method"""
        start_time = time.time()
        result = self.active_jobs[job_id]

        try:
            # Process finding types in optimal order
            for finding_type in self._get_processing_order():
                if finding_type in finding_data and finding_data[finding_type]:
                    findings = finding_data[finding_type]

                    # Process this finding type
                    batch_result = await self._process_finding_type(
                        finding_type, findings, program_name
                    )

                    result.finding_results[finding_type] = batch_result
                    result.processed_findings += batch_result.total_count
                    result.success_count += batch_result.success_count
                    result.failed_count += batch_result.failed_count

            # Mark job as completed
            result.status = "completed"
            result.completed_at = datetime.now(timezone.utc)
            result.processing_time = time.time() - start_time

            # Publish completion events
            await self._publish_completion_events(result)

            logger.info(f"Completed unified findings processing job {job_id} in {result.processing_time:.2f}s")

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            result.completed_at = datetime.now(timezone.utc)
            result.processing_time = time.time() - start_time
            logger.error(f"Failed unified findings processing job {job_id}: {e}")

        finally:
            # Clean up old jobs after some time
            asyncio.create_task(self._cleanup_job_after_delay(job_id, 3600))  # 1 hour

    async def _process_finding_type(
        self,
        finding_type: str,
        findings: List[Dict],
        program_name: str
    ) -> FindingBatchResult:
        """Process a single finding type"""
        result = FindingBatchResult(finding_type=finding_type, total_count=len(findings))

        try:
            # Get the appropriate handler
            handler = self.finding_type_handlers.get(finding_type)
            if not handler:
                result.errors.append(f"Unknown finding type: {finding_type}")
                result.failed_count = len(findings)
                return result

            # Always use bulk processing for rich event data collection
            await self._process_bulk(handler, findings, program_name, result)

        except Exception as e:
            logger.error(f"Error processing {finding_type} batch: {e}")
            result.errors.append(str(e))
            result.failed_count = len(findings)

        return result

    async def _process_bulk(
        self,
        handler: Callable,
        findings: List[Dict],
        program_name: str,
        result: FindingBatchResult
    ):
        """Process findings using bulk operations"""
        try:
            # Use bulk repository methods for large batches
            bulk_result = await handler(findings, program_name, bulk=True)

            # Handle different return formats based on finding type
            if len(bulk_result) == 8:
                # Detailed format (nuclei findings)
                success_count, failed_count, created_count, updated_count, skipped_count, created_findings, updated_findings, skipped_findings = bulk_result
                result.success_count = success_count
                result.failed_count = failed_count
                result.created_count = created_count
                result.updated_count = updated_count
                result.skipped_count = skipped_count
                result.created_findings = created_findings
                result.updated_findings = updated_findings
                result.skipped_findings = skipped_findings
                result.failed_findings = []  # Bulk processing tracks failures via failed_count
            elif len(bulk_result) == 2:
                # Simple format (other finding types)
                success_count, failed_count = bulk_result
                result.success_count = success_count
                result.failed_count = failed_count
                # For simple bulk processing, we don't have detailed counts
                result.created_count = 0
                result.updated_count = 0
                result.skipped_count = 0
                result.created_findings = []
                result.updated_findings = []
                result.skipped_findings = []
                result.failed_findings = []
            else:
                raise ValueError(f"Unexpected bulk result format with {len(bulk_result)} elements")

        except Exception as e:
            logger.error(f"Bulk processing failed for {result.finding_type}: {e}")
            result.failed_count = len(findings)
            result.errors.append(str(e))

    async def _publish_completion_events(self, result: UnifiedFindingsProcessingResult):
        """Publish completion events for the processing job"""
        try:
            # Publish individual finding creation events
            for finding_type, batch_result in result.finding_results.items():
                await self._publish_finding_events(finding_type, batch_result, result.program_name)

        except Exception as e:
            logger.error(f"Failed to publish completion events for findings job {result.job_id}: {e}")

    async def _publish_finding_events(
        self,
        finding_type: str,
        batch_result: FindingBatchResult,
        program_name: str
    ):
        """Publish events for newly created and updated findings"""
        try:
            # Publish events for created findings
            await self._publish_finding_events_by_action(
                finding_type, batch_result.created_findings, "created", program_name
            )

            # Publish events for updated findings
            await self._publish_finding_events_by_action(
                finding_type, batch_result.updated_findings, "updated", program_name
            )

        except Exception as e:
            logger.error(f"Failed to publish finding events for {finding_type}: {e}")

    async def _publish_finding_events_by_action(
        self,
        finding_type: str,
        findings: List[Dict[str, Any]],
        action: str,
        program_name: str
    ):
        """Publish rich events for findings with a specific action (created/updated)"""
        try:
            # Always publish individual rich events for each finding, regardless of batch size
            for finding in findings:
                # Use the rich event data if available, otherwise create minimal event
                if "event" in finding:
                    # Rich event data from repository - publish as-is
                    await publisher.publish_immediate(
                        f"events.findings.{finding_type}.{action}",
                        finding
                    )
                else:
                    # Fallback for minimal data - create rich event from minimal data
                    await publisher.publish_immediate(
                        f"events.findings.{finding_type}.{action}",
                        {
                            "event": f"finding.{action}",
                            "finding_type": finding_type,
                            "record_id": finding["record_id"],
                            "name": finding["name"],
                            "program_name": program_name,
                            "action": action,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )

        except Exception as e:
            logger.error(f"Failed to publish {action} finding events for {finding_type}: {e}")

    # Finding type handlers
    async def _handle_nuclei_findings(self, findings: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle nuclei finding processing"""
        # Handle the case where findings is a single dict instead of a list
        if isinstance(findings, dict):
            findings = [findings]

        logger.info(f"🔍 NUCLEI FINDINGS PROCESSOR DEBUG: Processing {len(findings)} nuclei findings for program {program_name}")
        for i, finding in enumerate(findings):
            logger.info(f"🔍 NUCLEI FINDINGS PROCESSOR DEBUG: Finding {i+1}: url={finding.get('url')}, template_id={finding.get('template_id')}, matcher_name={finding.get('matcher_name')}, matched_at={finding.get('matched_at')}")

        if bulk:
            # Process nuclei findings individually for now since we removed the batch method
            success_count = 0
            failed_count = 0
            created_count = 0
            updated_count = 0
            skipped_count = 0
            created_findings = []
            updated_findings = []
            skipped_findings = []

            for finding_data in findings:
                try:
                    # Ensure program_name is set
                    if not finding_data.get("program_name"):
                        finding_data["program_name"] = program_name

                    # Call individual repository method
                    result_tuple = await NucleiFindingsRepository.create_or_update_nuclei_finding(finding_data)
                    if len(result_tuple) == 3:
                        record_id, action, event_data = result_tuple
                    else:
                        # Nuclei repository only returns (record_id, action)
                        record_id, action = result_tuple
                        event_data = None

                    if record_id:
                        success_count += 1
                        if action == "created":
                            created_count += 1
                            # Create event data for nuclei findings
                            event_data = {
                                "event": "finding.created",
                                "finding_type": "nuclei",
                                "record_id": record_id,
                                "url": finding_data.get('url'),
                                "program_name": program_name,
                                "template_id": finding_data.get('template_id'),
                                "name": finding_data.get('name'),
                                "severity": finding_data.get('severity'),
                                "matcher_name": finding_data.get('matcher_name'),
                                "matched_at": finding_data.get('matched_at')
                            }
                            created_findings.append(event_data)
                        elif action == "updated":
                            updated_count += 1
                            # Create event data for nuclei findings
                            event_data = {
                                "event": "finding.updated",
                                "finding_type": "nuclei",
                                "record_id": record_id,
                                "url": finding_data.get('url'),
                                "program_name": program_name,
                                "template_id": finding_data.get('template_id'),
                                "name": finding_data.get('name'),
                                "severity": finding_data.get('severity'),
                                "matcher_name": finding_data.get('matcher_name'),
                                "matched_at": finding_data.get('matched_at')
                            }
                            updated_findings.append(event_data)
                        elif action == "skipped":
                            skipped_count += 1
                            # Create minimal skipped finding data
                            skipped_finding = {
                                "record_id": record_id,
                                "url": finding_data.get('url'),
                                "matched_at": finding_data.get('matched_at'),
                                "matcher_name": finding_data.get('matcher_name'),
                                "template_id": finding_data.get('template_id'),
                                "program_name": program_name,
                                "reason": "duplicate"
                            }
                            skipped_findings.append(skipped_finding)
                    else:
                        failed_count += 1

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error processing nuclei finding {finding_data.get('url', 'unknown')}: {e}")

            logger.info(f"Enhanced bulk nuclei findings processing completed: {success_count} success ({created_count} created, {updated_count} updated, {skipped_count} skipped), {failed_count} failed")
            return success_count, failed_count, created_count, updated_count, skipped_count, created_findings, updated_findings, skipped_findings
        else:
            result_tuple = await NucleiFindingsRepository.create_or_update_nuclei_finding(findings[0])
            if len(result_tuple) == 3:
                record_id, action, event_data = result_tuple
            else:
                # Fallback for old format
                record_id, action = result_tuple
                event_data = None
            return record_id, action, event_data

    async def _handle_typosquat_domain_findings(self, findings: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle typosquat domain finding processing"""
        # Handle the case where findings is a single dict instead of a list
        if isinstance(findings, dict):
            findings = [findings]

        for i, finding in enumerate(findings):
            # Check if this finding has a 'findings' key (indicating wrong structure)
            if 'findings' in finding:
                # Extract the actual findings
                if isinstance(finding['findings'], list) and finding['findings']:
                    findings[i] = finding['findings'][0]

        if bulk:
            success_count = 0
            failed_count = 0
            created_count = 0
            updated_count = 0
            skipped_count = 0
            filtered_count = 0
            created_findings = []
            updated_findings = []
            skipped_findings = []

            for finding_data in findings:
                try:
                    if not finding_data.get("program_name"):
                        finding_data["program_name"] = program_name

                    result_tuple = await TyposquatFindingsRepository.create_or_update_typosquat_finding(finding_data)
                    if len(result_tuple) == 3:
                        record_id, action, event_data = result_tuple
                    else:
                        record_id, action = result_tuple
                        event_data = None

                    # Handle filtered domains (record_id is None, action is "filtered")
                    if action == "filtered":
                        filtered_count += 1
                        skipped_count += 1
                        typo_domain = finding_data.get('typo_domain', 'unknown')
                        filter_reason = event_data.get('filter_reason', 'unknown') if event_data else 'unknown'
                        logger.info(f"Typosquat domain {typo_domain} filtered out: {filter_reason}")

                        skipped_findings.append({
                            "typo_domain": typo_domain,
                            "program_name": program_name,
                            "reason": f"filtered:{filter_reason}"
                        })

                        # Auto-resolve RecordedFuture alerts for filtered domains
                        source = finding_data.get('source', '')
                        if source == 'recordedfuture' and event_data:
                            await self._resolve_filtered_rf_alert(event_data, program_name)

                        continue

                    if record_id:
                        success_count += 1
                        
                        if action in ("created", "updated"):
                            try:
                                risk_result = await TyposquatFindingsRepository.calculate_single_typosquat_risk_score(record_id)
                                if risk_result.get('status') == 'success':
                                    logger.debug(f"Risk score calculated for {finding_data.get('typo_domain')}: {risk_result.get('risk_score')}")
                                else:
                                    logger.warning(f"Failed to calculate risk score for {finding_data.get('typo_domain')}: {risk_result.get('message')}")
                            except Exception as risk_error:
                                logger.error(f"Error calculating risk score for {finding_data.get('typo_domain')}: {risk_error}")
                        
                        if action == "created":
                            created_count += 1
                            if event_data and "event" in event_data:
                                # Preserve repository's rich event data (whois_registrar, domain_registered, etc.)
                                event_data = {
                                    **event_data,
                                    "finding_type": "typosquat_domain",
                                    "typo_domain": event_data.get("name") or finding_data.get("typo_domain"),
                                    "fuzzers": event_data.get("fuzzer_types") or finding_data.get("fuzzers"),
                                    "timestamp": event_data.get("timestamp") or finding_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                                }
                            else:
                                event_data = {
                                    "event": "finding.created",
                                    "finding_type": "typosquat_domain",
                                    "record_id": record_id,
                                    "typo_domain": finding_data.get("typo_domain"),
                                    "program_name": program_name,
                                    "fuzzers": finding_data.get("fuzzers"),
                                    "timestamp": finding_data.get("timestamp"),
                                }
                            created_findings.append(event_data)
                        elif action == "updated":
                            updated_count += 1
                            if event_data and "event" in event_data:
                                # Preserve repository's rich event data (whois_registrar, domain_registered, etc.)
                                event_data = {
                                    **event_data,
                                    "event": "finding.updated",
                                    "finding_type": "typosquat_domain",
                                    "typo_domain": event_data.get("name") or finding_data.get("typo_domain"),
                                    "fuzzers": event_data.get("fuzzer_types") or finding_data.get("fuzzers"),
                                    "timestamp": event_data.get("timestamp") or finding_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                                }
                            else:
                                event_data = {
                                    "event": "finding.updated",
                                    "finding_type": "typosquat_domain",
                                    "record_id": record_id,
                                    "typo_domain": finding_data.get("typo_domain"),
                                    "program_name": program_name,
                                    "fuzzers": finding_data.get("fuzzers"),
                                    "timestamp": finding_data.get("timestamp"),
                                }
                            updated_findings.append(event_data)
                        elif action == "skipped":
                            skipped_count += 1
                            skipped_finding = {
                                "record_id": record_id,
                                "typo_domain": finding_data.get('typo_domain'),
                                "program_name": program_name,
                                "reason": "duplicate"
                            }
                            skipped_findings.append(skipped_finding)
                    else:
                        failed_count += 1

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error processing typosquat finding {finding_data.get('typo_domain', 'unknown')}: {e}")

            if filtered_count > 0:
                logger.info(f"Typosquat filtering: {filtered_count} domains filtered out by pre-insertion gate")
            logger.info(f"Bulk typosquat domain findings processing completed: {success_count} success ({created_count} created, {updated_count} updated, {skipped_count} skipped, {filtered_count} filtered), {failed_count} failed")
            return success_count, failed_count, created_count, updated_count, skipped_count, created_findings, updated_findings, skipped_findings
        else:
            result_tuple = await TyposquatFindingsRepository.create_or_update_typosquat_finding(findings[0])
            if len(result_tuple) == 3:
                record_id, action, event_data = result_tuple
            else:
                record_id, action = result_tuple
                event_data = None

            if action == "filtered" and event_data:
                source = findings[0].get('source', '')
                if source == 'recordedfuture':
                    await self._resolve_filtered_rf_alert(event_data, program_name)
                return None, "filtered", event_data

            if record_id and action in ("created", "updated"):
                try:
                    risk_result = await TyposquatFindingsRepository.calculate_single_typosquat_risk_score(record_id)
                    if risk_result.get('status') == 'success':
                        logger.debug(f"Risk score calculated for {findings[0].get('typo_domain')}: {risk_result.get('risk_score')}")
                    else:
                        logger.warning(f"Failed to calculate risk score for {findings[0].get('typo_domain')}: {risk_result.get('message')}")
                except Exception as risk_error:
                    logger.error(f"Error calculating risk score for {findings[0].get('typo_domain')}: {risk_error}")
            
            return record_id, action, event_data

    async def _handle_wpscan_findings(self, findings: List[Dict], program_name: str, bulk: bool = False) -> Tuple:
        """Handle WPScan finding processing"""
        # Handle the case where findings is a single dict instead of a list
        if isinstance(findings, dict):
            findings = [findings]

        if bulk:
            # Process WPScan findings individually
            success_count = 0
            failed_count = 0
            created_count = 0
            updated_count = 0
            skipped_count = 0
            created_findings = []
            updated_findings = []
            skipped_findings = []

            for finding_data in findings:
                try:
                    # Ensure program_name is set
                    if not finding_data.get("program_name"):
                        finding_data["program_name"] = program_name

                    # Call individual repository method
                    record_id, action = await WPScanFindingsRepository.create_or_update_wpscan_finding(finding_data)

                    if record_id:
                        success_count += 1
                        if action == "created":
                            created_count += 1
                            # Create event data for WPScan findings
                            event_data = {
                                "event": "finding.created",
                                "finding_type": "wpscan",
                                "record_id": record_id,
                                "url": finding_data.get('url'),
                                "program_name": program_name,
                                "item_name": finding_data.get('item_name'),
                                "item_type": finding_data.get('item_type'),
                                "severity": finding_data.get('severity'),
                                "title": finding_data.get('title'),
                            }
                            created_findings.append(event_data)
                        elif action == "updated":
                            updated_count += 1
                            # Create event data for WPScan findings
                            event_data = {
                                "event": "finding.updated",
                                "finding_type": "wpscan",
                                "record_id": record_id,
                                "url": finding_data.get('url'),
                                "program_name": program_name,
                                "item_name": finding_data.get('item_name'),
                                "item_type": finding_data.get('item_type'),
                                "severity": finding_data.get('severity'),
                                "title": finding_data.get('title'),
                            }
                            updated_findings.append(event_data)
                        elif action == "skipped":
                            skipped_count += 1
                            # Create minimal skipped finding data
                            skipped_finding = {
                                "record_id": record_id,
                                "url": finding_data.get('url'),
                                "item_name": finding_data.get('item_name'),
                                "program_name": program_name,
                                "reason": "duplicate"
                            }
                            skipped_findings.append(skipped_finding)
                    else:
                        failed_count += 1

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error processing WPScan finding {finding_data.get('item_name', 'unknown')}: {e}")

            logger.info(f"Bulk WPScan findings processing completed: {success_count} success ({created_count} created, {updated_count} updated, {skipped_count} skipped), {failed_count} failed")
            return success_count, failed_count, created_count, updated_count, skipped_count, created_findings, updated_findings, skipped_findings
        else:
            result_tuple = await WPScanFindingsRepository.create_or_update_wpscan_finding(findings[0])
            record_id, action = result_tuple
            event_data = None
            return record_id, action, event_data

    async def _resolve_filtered_rf_alert(self, filter_event_data: Dict[str, Any], program_name: str):
        """Resolve a RecordedFuture alert whose typosquat domain was filtered out."""
        try:
            rf_data = filter_event_data.get("recordedfuture_data") or {}
            alert_id = rf_data.get("alert_id")
            if not alert_id:
                raw_alert = rf_data.get("raw_alert", {})
                alert_id = raw_alert.get("playbook_alert_id")

            if not alert_id:
                logger.warning(
                    f"Cannot resolve RF alert for filtered domain "
                    f"{filter_event_data.get('typo_domain')} - no alert_id found"
                )
                return

            logger.info(
                f"Auto-resolving RF alert {alert_id} for filtered domain "
                f"{filter_event_data.get('typo_domain')} "
                f"(reason: {filter_event_data.get('filter_reason')})"
            )
            result = await change_playbook_alert_status(
                program_name=program_name,
                alert_id=alert_id,
                new_status="Resolved",
                log_entry=f"Auto-resolved: domain filtered out ({filter_event_data.get('filter_reason')})",
            )
            if result.get("success"):
                logger.info(f"Successfully resolved RF alert {alert_id} for filtered domain")
            else:
                logger.warning(f"Failed to resolve RF alert {alert_id}: {result.get('message')}")
        except Exception as e:
            logger.error(
                f"Error resolving RF alert for filtered domain "
                f"{filter_event_data.get('typo_domain')}: {e}"
            )

    def _extract_finding_name(self, finding_type: str, finding: Dict[str, Any]) -> str:
        """Extract the appropriate name field based on finding type"""
        if finding_type == "nuclei":
            return finding.get("url", "unknown")
        elif finding_type == "typosquat":
            return finding.get("typo_domain", "unknown")
        elif finding_type == "wpscan":
            return finding.get("item_name", "unknown")
        else:
            return "unknown"

    async def _cleanup_job_after_delay(self, job_id: str, delay_seconds: int):
        """Clean up completed jobs after a delay"""
        await asyncio.sleep(delay_seconds)
        if job_id in self.active_jobs:
            del self.active_jobs[job_id]
            logger.info(f"Cleaned up unified findings processing job {job_id}")

    async def shutdown(self):
        """Shutdown the unified findings processor gracefully"""
        try:
            # Cancel any active jobs
            for job_id, result in self.active_jobs.items():
                if result.status == "processing":
                    result.status = "cancelled"
                    result.error = "Processor shutdown"
                    result.completed_at = datetime.now(timezone.utc)
                    logger.info(f"Cancelled active findings job {job_id} during shutdown")

            # Clear active jobs
            self.active_jobs.clear()

            logger.info("Unified findings processor shutdown complete")

        except Exception as e:
            logger.error(f"Error during unified findings processor shutdown: {e}")
            raise


# Global instance
unified_findings_processor = UnifiedFindingsProcessor()
