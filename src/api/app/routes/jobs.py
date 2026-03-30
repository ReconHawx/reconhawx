from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from models.job import DummyBatchRequest, GatherApiFindingsRequest, SyncRecordedFutureDataRequest
from repository import JobRepository
from auth.dependencies import require_internal_service_or_authentication, get_current_user_from_middleware
from models.user_postgres import UserResponse
from services.job_submission import JobSubmissionService
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class JobStatusUpdateRequest(BaseModel):
    """Request model for updating job status"""
    status: str = Field(..., description="New job status (pending, running, completed, failed)")
    progress: int = Field(..., ge=0, le=100, description="Job progress percentage (0-100)")
    message: str = Field(..., description="Status message")
    results: Optional[Dict[str, Any]] = Field(None, description="Job results (optional)")

@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any])
async def get_all_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=100, description="Number of jobs per page"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get all jobs with pagination and filtering"""
    try:
        jobs, total = await JobRepository.get_all_jobs(
            page=page,
            limit=limit,
            job_type=job_type,
            status=status
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
        # Validate status values
        valid_statuses = ["pending", "running", "completed", "failed"]
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status '{request.status}'. Must be one of: {valid_statuses}"
            )
        
        # Validate progress range
        if request.progress < 0 or request.progress > 100:
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
            results=request.results
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        logger.info(f"Updated job {job_id} status to {request.status} ({request.progress}%)")
        
        return {
            "status": "success",
            "message": f"Job {job_id} status updated successfully",
            "job_id": job_id,
            "updated_status": request.status,
            "updated_progress": request.progress
        }
        
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