from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator
from models.job import DummyBatchRequest, GatherApiFindingsRequest, SyncRecordedFutureDataRequest, RefreshVendorIntelRequest
from repository import JobRepository
from repository.scheduled_job_repo import ScheduledJobRepository
from auth.dependencies import require_internal_service_or_authentication, get_current_user_from_middleware
from models.user_postgres import UserResponse
from services.job_submission import JobSubmissionService
from services.kubernetes import KubernetesService
from datetime import datetime, timezone
import uuid
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
router = APIRouter()

job_submission_service = JobSubmissionService()
k8s_service = KubernetesService()
thread_pool = ThreadPoolExecutor(max_workers=4)

_FINISHED_JOB_STATUSES = frozenset({"completed", "failed", "stopped", "cancelled"})


async def _run_job_stop_cleanup(
    job_id: str,
    job_type: Optional[str],
    current_progress: int,
) -> None:
    """Tear down Kubernetes resources and mark the job stopped."""
    logger.info("Starting Kubernetes cleanup for job: %s", job_id)

    if job_type == "workflow":
        stop_results = k8s_service.stop_workflow(job_id)
        logger.info("Workflow cleanup completed for job %s: %s", job_id, stop_results)
    else:
        pod_logs = job_submission_service.get_batch_job_pod_logs(job_id)
        if pod_logs:
            formatted_output = (
                f"\n--- Final Job Output ---\n{pod_logs}\n\n--- End Job ---\n"
            )
            await JobRepository.update_job_status(
                job_id,
                runner_pod_output=formatted_output,
            )
            logger.info("Captured runner pod output for job %s before delete", job_id)

        job_submission_service.delete_job(job_id, job_type=job_type)
        logger.info("Kubernetes cleanup completed for batch job %s", job_id)

    await ScheduledJobRepository.finalize_running_execution_for_job(job_id)

    final_progress = current_progress
    latest = await JobRepository.get_job_status(job_id)
    if latest:
        final_progress = latest.get("progress", current_progress)

    await JobRepository.update_job_status(
        job_id,
        status="stopped",
        progress=final_progress,
        message="Job stopped by user",
    )
    logger.info("Updated job status to stopped for %s", job_id)


def _submit_job_stop_cleanup(job_id: str, job_type: Optional[str], current_progress: int) -> None:
    """Run stop cleanup from a background thread."""
    try:
        try:
            loop = asyncio.get_event_loop()
            future = asyncio.run_coroutine_threadsafe(
                _run_job_stop_cleanup(job_id, job_type, current_progress),
                loop,
            )
            future.result()
        except RuntimeError:
            asyncio.run(_run_job_stop_cleanup(job_id, job_type, current_progress))
    except Exception as e:
        logger.error("Error in background Kubernetes cleanup for job %s: %s", job_id, e)
        error_update = {
            "status": "failed",
            "progress": current_progress,
            "message": f"Failed to stop job: {e}",
        }
        try:
            loop = asyncio.get_event_loop()
            future = asyncio.run_coroutine_threadsafe(
                JobRepository.update_job_status(job_id, **error_update),
                loop,
            )
            future.result()
        except RuntimeError:
            asyncio.run(JobRepository.update_job_status(job_id, **error_update))

class JobStatusUpdateRequest(BaseModel):
    """Request model for updating job status"""
    status: Optional[str] = Field(None, description="New job status (pending, running, stopping, stopped, completed, failed)")
    progress: Optional[int] = Field(None, ge=0, le=100, description="Job progress percentage (0-100)")
    message: Optional[str] = Field(None, description="Status message")
    results: Optional[Dict[str, Any]] = Field(None, description="Job results (optional)")
    runner_pod_output: Optional[str] = Field(None, description="Runner pod output/logs to append")

    @model_validator(mode="after")
    def validate_update_payload(self):
        has_status_fields = (
            self.status is not None
            or self.progress is not None
            or self.message is not None
            or self.results is not None
        )
        has_runner_output = self.runner_pod_output is not None

        if not has_status_fields and not has_runner_output:
            raise ValueError(
                "Provide status/progress/message/results or runner_pod_output"
            )

        if has_status_fields and (
            self.status is None or self.progress is None or self.message is None
        ):
            raise ValueError(
                "status, progress, and message are required for a status update"
            )

        return self

@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any])
async def get_all_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=100, description="Number of jobs per page"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    job_id_contains: Optional[str] = Query(None, description="Filter by job ID substring"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get all jobs with pagination and filtering"""
    try:
        jobs, total = await JobRepository.get_all_jobs(
            page=page,
            limit=limit,
            job_type=job_type,
            status=status,
            job_id_contains=job_id_contains,
        )
        
        return {
            "status": "success",
            "jobs": jobs,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
        
    except Exception as e:
        logger.error(f"Error getting all jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dummy-batch", response_model=Dict[str, Any])
async def create_dummy_batch_job(
    request: DummyBatchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a dummy batch job for testing purposes.
    
    This endpoint creates a Kueue job that will process items in the background.
    Users can check job status using the /jobs/{job_id}/status endpoint.
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="No items provided")

    try:
        logger.info(f"Creating dummy batch job for {len(request.items)} items")
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create job payload
        job_payload = {
            "job_id": job_id,
            "job_type": "dummy_batch",
            "items": request.items,
            "user_id": current_user.id or "unknown",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Create job status record
        job_created = await JobRepository.create_job(job_id, "dummy_batch", job_payload)
        
        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")
        
        # Submit job to Kubernetes
        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_dummy_batch_job(job_id, job_payload)
            logger.info(f"Submitted dummy batch job {job_id} to Kubernetes")
        except Exception as e:
            logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
            # Update job status to failed
            await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit to Kubernetes: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to submit job to Kubernetes: {str(e)}")
        
        logger.info(f"Created dummy batch job {job_id} for {len(request.items)} items")
        
        return {
            "status": "success",
            "message": f"Dummy batch job created with ID: {job_id}",
            "job_id": job_id,
            "total_items": len(request.items)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating dummy batch job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating dummy batch job: {str(e)}"
        )

@router.post("/gather-api-findings", response_model=Dict[str, Any])
async def create_gather_api_findings_job(
    request: GatherApiFindingsRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a gather API findings batch job that will run in Kubernetes.

    This endpoint creates a Kubernetes job that will gather typosquat domain findings
    from vendor APIs like Threatstream. The job runs asynchronously and can be
    monitored using the /jobs/{job_id}/status endpoint.

    The job will:
    - Fetch domains from the specified API vendor
    - Process and validate the domain data
    - Store findings as TyposquatDomain objects in the database
    - Provide detailed progress and result reporting
    """
    if not request.program_names:
        raise HTTPException(status_code=400, detail="At least one program name is required")

    try:
        logger.info(f"Creating gather API findings job for {len(request.program_names)} programs using {request.api_vendor}")

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Create job payload
        job_payload = {
            "job_id": job_id,
            "job_type": "gather_api_findings",
            "program_names": request.program_names,
            "user_id": current_user.id or "unknown",
            "api_vendor": request.api_vendor,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Create job status record
        job_created = await JobRepository.create_job(job_id, "gather_api_findings", job_payload)

        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")

        # Submit job to Kubernetes
        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_gather_api_findings_job(job_id, job_payload)
            logger.info(f"Submitted gather API findings job {job_id} to Kubernetes")
        except Exception as e:
            logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
            # Update job status to failed
            await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit to Kubernetes: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to submit job to Kubernetes: {str(e)}")

        logger.info(f"Created gather API findings job {job_id} for programs: {request.program_names}")

        return {
            "status": "success",
            "message": f"Gather API findings job created with ID: {job_id}",
            "job_id": job_id,
            "program_names": request.program_names,
            "api_vendor": request.api_vendor,
            "total_programs": len(request.program_names)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating gather API findings job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating gather API findings job: {str(e)}"
        )

@router.post("/sync-recordedfuture-data", response_model=Dict[str, Any])
async def create_sync_recordedfuture_data_job(
    request: SyncRecordedFutureDataRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a RecordedFuture data sync job that will run in Kubernetes.

    This endpoint creates a Kubernetes job that will synchronize existing typosquat
    domain findings with source=recordedfuture by fetching fresh data from the
    RecordedFuture API and updating the recordedfuture_data field. The job runs
    asynchronously and can be monitored using the /jobs/{job_id}/status endpoint.

    The job will:
    - Find all typosquat domain findings with source=recordedfuture for specified programs
    - Fetch current data from RecordedFuture API for those findings
    - Update the recordedfuture_data field with fresh information
    - Skip updates if data hasn't changed to avoid unnecessary writes
    - Provide detailed progress and result reporting
    """
    if not request.program_name:
        raise HTTPException(status_code=400, detail="Program name is required")

    try:
        logger.info(f"Creating RecordedFuture data sync job for program: {request.program_name}")

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Create sync options from individual fields
        sync_options = {
            "batch_size": request.batch_size,
            "max_age_days": request.max_age_days,
            "include_screenshots": request.include_screenshots
        }

        # Create job payload
        job_payload = {
            "job_id": job_id,
            "job_type": "sync_recordedfuture_data",
            "program_name": request.program_name,
            "user_id": current_user.id or "unknown",
            "sync_options": sync_options,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Create job status record
        job_created = await JobRepository.create_job(job_id, "sync_recordedfuture_data", job_payload)

        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")

        # Submit job to Kubernetes
        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_sync_recordedfuture_data_job(job_id, job_payload)
            logger.info(f"Submitted RecordedFuture data sync job {job_id} to Kubernetes")
        except Exception as e:
            logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
            # Update job status to failed
            await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit to Kubernetes: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to submit job to Kubernetes: {str(e)}")

        logger.info(f"Created RecordedFuture data sync job {job_id} for program: {request.program_name}")

        return {
            "status": "success",
            "message": f"RecordedFuture data sync job created with ID: {job_id}",
            "job_id": job_id,
            "program_name": request.program_name,
            "sync_options": sync_options,
            "batch_size": request.batch_size,
            "max_age_days": request.max_age_days,
            "include_screenshots": request.include_screenshots
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating RecordedFuture data sync job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating RecordedFuture data sync job: {str(e)}"
        )

@router.post("/refresh-vendor-intel", response_model=Dict[str, Any])
async def create_refresh_vendor_intel_job(
    request: RefreshVendorIntelRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a vendor intel refresh job that runs in Kubernetes.

    Refreshes existing typosquat findings that already have vendor JSONB populated
    (has_recordedfuture / has_threatstream). Does not change finding status,
    assignment, or Recorded Future playbook state.
    """
    if request.api_vendor not in ("recordedfuture", "threatstream"):
        raise HTTPException(
            status_code=400,
            detail="api_vendor must be 'recordedfuture' or 'threatstream'",
        )

    try:
        logger.info(
            "Creating refresh vendor intel job for program %s vendor=%s",
            request.program_name,
            request.api_vendor,
        )

        job_id = str(uuid.uuid4())
        refresh_options = {
            "batch_size": request.batch_size,
            "max_age_hours": request.max_age_hours,
            "include_screenshots": request.include_screenshots,
        }
        job_payload = {
            "job_id": job_id,
            "job_type": "refresh_vendor_intel",
            "program_name": request.program_name,
            "user_id": current_user.id or "unknown",
            "job_data": {
                "api_vendor": request.api_vendor,
                "refresh_options": refresh_options,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        job_created = await JobRepository.create_job(job_id, "refresh_vendor_intel", job_payload)
        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")

        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_refresh_vendor_intel_job(job_id, job_payload)
            logger.info("Submitted refresh vendor intel job %s to Kubernetes", job_id)
        except Exception as e:
            logger.error("Failed to submit job to Kubernetes: %s", e)
            await JobRepository.update_job_status(
                job_id, "failed", 0, f"Failed to submit to Kubernetes: {e}"
            )
            raise HTTPException(
                status_code=500, detail=f"Failed to submit job to Kubernetes: {e}"
            )

        return {
            "status": "success",
            "message": f"Refresh vendor intel job created with ID: {job_id}",
            "job_id": job_id,
            "program_name": request.program_name,
            "api_vendor": request.api_vendor,
            "refresh_options": refresh_options,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating refresh vendor intel job: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Error creating refresh vendor intel job: {str(e)}",
        )

@router.get("/{job_id}/status", response_model=Dict[str, Any])
async def get_job_status(
    job_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get the status of a background job"""
    try:
        job_status = await JobRepository.get_job_status(job_id)
        
        if not job_status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        return {
            "status": "success",
            "job": job_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{job_id}/status", response_model=Dict[str, Any])
async def update_job_status(
    job_id: str,
    request: JobStatusUpdateRequest,
    current_user: UserResponse = Depends(require_internal_service_or_authentication)
):
    """Update the status of a background job
    
    This endpoint allows workers and other services to update job status,
    progress, and results. The job must exist and be accessible to the user.
    """
    try:
        valid_statuses = ["pending", "running", "stopping", "stopped", "completed", "failed"]

        if request.status is not None:
            if request.status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{request.status}'. Must be one of: {valid_statuses}"
                )

            if request.progress is None or request.progress < 0 or request.progress > 100:
                raise HTTPException(
                    status_code=400,
                    detail="Progress must be between 0 and 100"
                )
        
        # Update job status
        success = await JobRepository.update_job_status(
            job_id=job_id,
            status=request.status,
            progress=request.progress,
            message=request.message,
            results=request.results,
            runner_pod_output=request.runner_pod_output,
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if request.status is not None:
            logger.info(
                f"Updated job {job_id} status to {request.status} ({request.progress}%)"
            )
        elif request.runner_pod_output is not None:
            logger.info(f"Appended runner_pod_output for job {job_id}")
        
        response: Dict[str, Any] = {
            "status": "success",
            "message": f"Job {job_id} status updated successfully",
            "job_id": job_id,
        }
        if request.status is not None:
            response["updated_status"] = request.status
            response["updated_progress"] = request.progress
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating job status for {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{job_id}/results", response_model=Dict[str, Any])
async def get_job_results(
    job_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get the final results of a completed job"""
    try:
        job_status = await JobRepository.get_job_status(job_id)
        
        if not job_status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if job_status["status"] != "completed":
            raise HTTPException(
                status_code=400, 
                detail=f"Job not completed yet. Current status: {job_status['status']}"
            )
        
        return {
            "job_id": job_id,
            "status": "completed",
            "results": job_status.get("results")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job results for {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{job_id}/stop", response_model=Dict[str, Any])
async def stop_job(
    job_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Stop a running batch job and cancel associated Kubernetes resources."""
    try:
        job_record = await JobRepository.get_job_status(job_id)
        if not job_record:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        current_status = (job_record.get("status") or "unknown").lower()
        if current_status in _FINISHED_JOB_STATUSES:
            return {
                "status": "already_finished",
                "message": f"Job {job_id} is already {current_status} and cannot be stopped",
                "job_id": job_id,
            }

        if current_status == "stopping":
            return {
                "status": "stopping",
                "message": f"Job {job_id} is already being stopped",
                "job_id": job_id,
            }

        job_type = job_record.get("job_type")
        current_progress = job_record.get("progress", 0)

        await JobRepository.update_job_status(
            job_id,
            status="stopping",
            progress=current_progress,
            message="Job is being stopped",
        )
        logger.info("Updated job %s status to stopping", job_id)

        thread_pool.submit(_submit_job_stop_cleanup, job_id, job_type, current_progress)

        return {
            "status": "stopping",
            "message": f"Job {job_id} is being stopped. Cleanup is running in the background.",
            "job_id": job_id,
            "note": "The job status will be updated to 'stopped' once cleanup is complete.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error stopping job %s: %s", job_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to stop job: {e}")


@router.delete("/{job_id}", response_model=Dict[str, Any])
async def delete_job(
    job_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a job status record"""
    try:
        success = await JobRepository.delete_job(job_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        return {
            "status": "success",
            "message": f"Job {job_id} deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 