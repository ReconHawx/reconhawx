from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import Dict, Any, List, Optional
from models.job import (
    ScheduledJobRequest, ScheduledJobResponse, ScheduledJobUpdateRequest,
    JobType, JobExecutionHistory
)
from models.user_postgres import UserResponse
from auth.dependencies import get_current_user_from_middleware, check_program_permission_by_id, get_user_accessible_programs
from services.job_scheduler import JobSchedulerService
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Global scheduler service instance
scheduler_service = JobSchedulerService()

async def _resolve_program_names_to_ids(current_user: UserResponse, names: List[str]) -> List[str]:
    """Resolve ordered unique program names to UUID strings."""
    out: List[str] = []
    for name in names:
        out.append(await _resolve_program_id(current_user, name))
    return out


async def _user_has_analyst_on_any_program(current_user: UserResponse, program_ids: List[str]) -> bool:
    if not program_ids:
        return False
    for pid in program_ids:
        if await check_program_permission_by_id(current_user, pid, "analyst"):
            return True
    return False


async def _user_has_manager_on_all_programs(current_user: UserResponse, program_ids: List[str]) -> bool:
    if not program_ids:
        return False
    for pid in program_ids:
        if not await check_program_permission_by_id(current_user, pid, "manager"):
            return False
    return True


async def _resolve_program_id(current_user: UserResponse, program_name: str) -> str:
    """Resolve program name to program ID and verify user has access"""
    
    # Check if user has access to this program
    accessible_program_names = get_user_accessible_programs(current_user)
    # Note: For superusers/admins, accessible_program_names is empty meaning "no restrictions"
    if accessible_program_names and program_name not in accessible_program_names:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to program '{program_name}'"
        )
    
    # Convert program name to ID by looking it up in the database
    from repository import ProgramRepository
    
    try:
        program_data = await ProgramRepository.get_program_by_name(program_name)
        
        if not program_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Program '{program_name}' not found"
            )
        
        return program_data['id']
        
    except Exception as e:
        logger.error(f"Error resolving program ID for '{program_name}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resolving program ID"
        )

@router.on_event("startup")
async def startup_event():
    """Start the job scheduler on API startup"""
    await scheduler_service.start()

@router.on_event("shutdown")
async def shutdown_event():
    """Stop the job scheduler on API shutdown"""
    await scheduler_service.stop()

@router.post("", response_model=ScheduledJobResponse)
@router.post("/", response_model=ScheduledJobResponse)
async def create_scheduled_job(
    request: ScheduledJobRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a new scheduled job
    
    This endpoint allows users to schedule jobs to run at specific times or intervals.
    The program ID is automatically determined based on user permissions and job context.
    Supported schedule types:
    - once: Run once at a specific time
    - recurring: Run at regular intervals
    - cron: Run based on cron expressions
    """
    try:
        logger.info(f"Creating scheduled job: {request.name} (type: {request.job_type})")
        
        # Validate job data based on job type
        await _validate_job_data(request.job_type, request.job_data)

        target_names = list(request.program_names) if request.program_names else [request.program_name]
        program_id_list = await _resolve_program_names_to_ids(current_user, target_names)

        if not await _user_has_manager_on_all_programs(current_user, program_id_list):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager access required on all selected programs to create scheduled job",
            )

        scheduled_job = await scheduler_service.create_scheduled_job(
            request,
            current_user.id or "unknown",
            program_id_list,
        )
        
        logger.info(f"Successfully created scheduled job {scheduled_job.schedule_id}")
        
        return scheduled_job
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error creating scheduled job: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating scheduled job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating scheduled job: {str(e)}")

@router.get("", response_model=List[ScheduledJobResponse])
@router.get("/", response_model=List[ScheduledJobResponse])
async def get_scheduled_jobs(
    job_type: Optional[JobType] = Query(None, description="Filter by job type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get all scheduled jobs for the current user
    
    Returns a list of scheduled jobs with optional filtering by job type, status, or tags.
    """
    try:
        # Get user's accessible program names
        accessible_program_names = get_user_accessible_programs(current_user)
        
        # Convert program names to program IDs
        program_ids = []
        if accessible_program_names:
            from repository import ProgramRepository
            for program_name in accessible_program_names:
                try:
                    program_data = await ProgramRepository.get_program_by_name(program_name)
                    if program_data:
                        program_ids.append(program_data['id'])
                except Exception as e:
                    logger.warning(f"Could not resolve program ID for '{program_name}': {str(e)}")
        
        # Get all scheduled jobs for the programs the user has access to
        scheduled_jobs = await scheduler_service.get_all_scheduled_jobs(
            user_id=None,  # Remove user filtering - show all jobs for accessible programs
            program_ids=program_ids if program_ids else None
        )
        
        # Apply additional filters
        filtered_jobs = []
        for job in scheduled_jobs:
            # Filter by job type
            if job_type and job.job_type != job_type:
                continue
            
            # Filter by status
            if status and job.status.value != status:
                continue
            
            # Filter by tag
            if tag and tag not in job.tags:
                continue
            
            filtered_jobs.append(job)
        
        logger.info(f"Retrieved {len(filtered_jobs)} scheduled jobs for user {current_user.id}")
        return filtered_jobs
        
    except Exception as e:
        logger.error(f"Error getting scheduled jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/types", response_model=Dict[str, Any])
async def get_supported_job_types():
    """Get supported job types and their configurations
    
    Returns information about the job types that can be scheduled and their required data formats.
    """
    try:
        job_types_info = {
            "dummy_batch": {
                "name": "Dummy Batch Job",
                "description": "A test job that processes a list of items",
                "required_data": {
                    "items": "List[str] - List of items to process"
                },
                "example": {
                    "items": ["item1", "item2", "item3"]
                }
            },
            "typosquat_batch": {
                "name": "Typosquat Batch Job",
                "description": "Analyze domains for typosquatting characteristics",
                "required_data": {
                    "domains": "List[str] - List of domains to analyze"
                },
                "example": {
                    "domains": ["example.com", "test.com"]
                }
            },
            "phishlabs_batch": {
                "name": "PhishLabs Batch Job",
                "description": "Enrich typosquat findings with PhishLabs data",
                "required_data": {
                    "finding_ids": "List[str] - List of finding IDs to enrich"
                },
                "example": {
                    "finding_ids": ["finding1", "finding2", "finding3"]
                }
            },
            "ai_analysis_batch": {
                "name": "AI Analysis Batch Job",
                "description": "Run AI threat analysis on typosquat findings",
                "required_data": {
                    "finding_ids": "List[str] - List of finding IDs to analyze",
                    "model": "Optional[str] - Override Ollama model",
                    "force": "bool - Re-analyze even if already analyzed"
                },
                "example": {
                    "finding_ids": ["finding1", "finding2"],
                    "model": None,
                    "force": False
                }
            },
            "gather_api_findings": {
                "name": "Gather API Findings",
                "description": "Gather typosquat findings from vendor APIs (ThreatStream, RecordedFuture)",
                "required_data": {
                    "program_name": "str - Program to gather findings for (mirrors schedule program_name)",
                    "api_vendor": "str - threatstream or recordedfuture",
                    "custom_query": "str - Required when api_vendor is threatstream (ThreatStream intelligence q= query)",
                    "date_range_hours": "Optional[int] - Limit to findings created within the last N hours (0-8760; 0 = no date filter)"
                },
                "example": {
                    "program_name": "myprogram",
                    "api_vendor": "threatstream",
                    "custom_query": "(feed_name = \"Intel 471\" and itype = mal_domain and (value contains example))",
                    "date_range_hours": 168
                }
            },
            "sync_recordedfuture_data": {
                "name": "Sync RecordedFuture Data",
                "description": "Synchronize RecordedFuture data for existing findings",
                "required_data": {
                    "program_name": "str - Program name to sync data for",
                    "sync_options": "Dict - Synchronization options"
                },
                "example": {
                    "program_name": "example_program",
                    "sync_options": {
                        "batch_size": 50,
                        "max_age_days": 30,
                        "include_screenshots": true
                    }
                }
            },
            "workflow": {
                "name": "Workflow Job",
                "description": "Execute a predefined workflow",
                "required_data": {
                    "workflow_id": "str - ID of the workflow to execute",
                    "workflow_variables": "Optional[Dict] - Variable values for workflow execution"
                },
                "schedule_fields": {
                    "program_name": "str - Single program (non-workflow jobs)",
                    "program_names": "List[str] - For workflow jobs only: one runner per program (manager on all required)"
                },
                "example": {
                    "workflow_id": "workflow-123",
                    "workflow_variables": {
                        "domain": "example.com",
                        "port": "443"
                    }
                }
            }
        }
        
        return {
            "supported_job_types": job_types_info,
            "schedule_types": {
                "once": "Run once at a specific time",
                "recurring": "Run at regular intervals",
                "cron": "Run based on cron expressions"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting job types info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{schedule_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(
    schedule_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a specific scheduled job by ID"""
    try:
        scheduled_job = await scheduler_service.get_scheduled_job(schedule_id)
        
        if not scheduled_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        if not await _user_has_analyst_on_any_program(current_user, scheduled_job.program_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to scheduled job",
            )
        
        return scheduled_job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scheduled job {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{schedule_id}", response_model=ScheduledJobResponse)
async def update_scheduled_job(
    schedule_id: str,
    request: ScheduledJobUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update a scheduled job
    
    Allows updating the name, description, schedule, enabled status, and tags of a scheduled job.
    """
    try:
        # Get the existing job to check program permissions
        existing_job = await scheduler_service.get_scheduled_job(schedule_id)
        if not existing_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        if not await _user_has_manager_on_all_programs(current_user, existing_job.program_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager access required on all programs for this scheduled job",
            )
        
        # Build update data from request
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.description is not None:
            update_data["description"] = request.description
        if request.schedule is not None:
            update_data["schedule"] = request.schedule.dict()
        if request.enabled is not None:
            update_data["enabled"] = request.enabled
        if request.tags is not None:
            update_data["tags"] = request.tags
        if request.job_data is not None:
            await _validate_job_data(existing_job.job_type, request.job_data)
            update_data["job_data"] = request.job_data

        if request.program_names is not None:
            if len(request.program_names) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="program_names cannot be empty",
                )
            if existing_job.job_type != JobType.WORKFLOW:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="program_names can only be updated for workflow scheduled jobs",
                )
            new_ids = await _resolve_program_names_to_ids(current_user, request.program_names)
            if not await _user_has_manager_on_all_programs(current_user, new_ids):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Manager access required on all selected programs",
                )
            update_data["program_ids"] = new_ids

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update the scheduled job
        updated_job = await scheduler_service.update_scheduled_job(schedule_id, update_data)
        
        if not updated_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        logger.info(f"Updated scheduled job {schedule_id}")
        return updated_job
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error updating scheduled job {schedule_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating scheduled job {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{schedule_id}", response_model=Dict[str, Any])
async def delete_scheduled_job(
    schedule_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a scheduled job
    
    This will remove the job from the scheduler and delete all associated data.
    """
    try:
        # Get the existing job to check program permissions
        existing_job = await scheduler_service.get_scheduled_job(schedule_id)
        if not existing_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        if not await _user_has_manager_on_all_programs(current_user, existing_job.program_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager access required on all programs for this scheduled job",
            )
        
        success = await scheduler_service.delete_scheduled_job(schedule_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        logger.info(f"Deleted scheduled job {schedule_id}")
        
        return {
            "status": "success",
            "message": f"Scheduled job {schedule_id} deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting scheduled job {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{schedule_id}/enable", response_model=Dict[str, Any])
async def enable_scheduled_job(
    schedule_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Enable a scheduled job
    
    This will resume the job in the scheduler if it was previously disabled.
    """
    try:
        # Get the existing job to check program permissions
        existing_job = await scheduler_service.get_scheduled_job(schedule_id)
        if not existing_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        if not await _user_has_manager_on_all_programs(current_user, existing_job.program_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager access required on all programs for this scheduled job",
            )
        
        success = await scheduler_service.enable_scheduled_job(schedule_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        logger.info(f"Enabled scheduled job {schedule_id}")
        
        return {
            "status": "success",
            "message": f"Scheduled job {schedule_id} enabled successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling scheduled job {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{schedule_id}/disable", response_model=Dict[str, Any])
async def disable_scheduled_job(
    schedule_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Disable a scheduled job
    
    This will pause the job in the scheduler without deleting it.
    """
    try:
        # Get the existing job to check program permissions
        existing_job = await scheduler_service.get_scheduled_job(schedule_id)
        if not existing_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        if not await _user_has_manager_on_all_programs(current_user, existing_job.program_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager access required on all programs for this scheduled job",
            )
        
        success = await scheduler_service.disable_scheduled_job(schedule_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        logger.info(f"Disabled scheduled job {schedule_id}")
        
        return {
            "status": "success",
            "message": f"Scheduled job {schedule_id} disabled successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling scheduled job {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{schedule_id}/run-now", response_model=Dict[str, Any])
async def run_scheduled_job_now(
    schedule_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Run a scheduled job immediately
    
    This will trigger the job to run now, regardless of its schedule.
    """
    try:
        # Get the scheduled job
        scheduled_job = await scheduler_service.get_scheduled_job(schedule_id)
        
        if not scheduled_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        if not await _user_has_manager_on_all_programs(current_user, scheduled_job.program_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager access required on all programs for this scheduled job",
            )
        
        # Trigger the job immediately
        success = await scheduler_service.run_scheduled_job_now(schedule_id)
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to execute scheduled job {schedule_id}")
        
        logger.info(f"Manual execution completed for scheduled job {schedule_id}")
        
        return {
            "status": "success",
            "message": f"Scheduled job {schedule_id} execution triggered",
            "schedule_id": schedule_id,
            "triggered_at": datetime.now(timezone.utc)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running scheduled job {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{schedule_id}/executions", response_model=List[JobExecutionHistory])
async def get_scheduled_job_executions(
    schedule_id: str,
    limit: int = Query(50, ge=1, le=100, description="Number of executions to return"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get execution history for a scheduled job
    
    Returns the history of job executions for the specified scheduled job.
    """
    try:
        # Check if scheduled job exists
        scheduled_job = await scheduler_service.get_scheduled_job(schedule_id)
        
        if not scheduled_job:
            raise HTTPException(status_code=404, detail=f"Scheduled job {schedule_id} not found")
        
        if not await _user_has_analyst_on_any_program(current_user, scheduled_job.program_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to execution history for scheduled job",
            )
        
        # Get execution history from database
        from repository import ScheduledJobRepository
        
        execution_history = await ScheduledJobRepository.get_execution_history(schedule_id, limit)
        
        logger.info(f"Retrieved {len(execution_history)} execution history records for scheduled job {schedule_id}")
        
        return execution_history
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution history for {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def _validate_job_data(job_type: JobType, job_data: Dict[str, Any]):
    """Validate job data based on job type"""
    if job_type == JobType.DUMMY_BATCH:
        if "items" not in job_data or not isinstance(job_data["items"], list):
            raise ValueError("Dummy batch jobs require 'items' field as a list")
        if not job_data["items"]:
            raise ValueError("Items list cannot be empty")
    
    elif job_type == JobType.TYPOSQUAT_BATCH:
        if "domains" not in job_data or not isinstance(job_data["domains"], list):
            raise ValueError("Typosquat batch jobs require 'domains' field as a list")
        if not job_data["domains"]:
            raise ValueError("Domains list cannot be empty")
    elif job_type == JobType.PHISHLABS_BATCH:
        if "finding_ids" not in job_data or not isinstance(job_data["finding_ids"], list):
            raise ValueError("PhishLabs batch jobs require 'finding_ids' field as a list")
        if not job_data["finding_ids"]:
            raise ValueError("Finding IDs list cannot be empty")

    elif job_type == JobType.GATHER_API_FINDINGS:
        if "program_name" not in job_data or not isinstance(job_data["program_name"], str):
            raise ValueError("Gather API findings jobs require 'program_name' field as a string")
        if not job_data["program_name"]:
            raise ValueError("Program name cannot be empty")
        if "api_vendor" not in job_data or job_data["api_vendor"] not in ["threatstream", "recordedfuture"]:
            raise ValueError("Gather API findings jobs require 'api_vendor' field with value 'threatstream' or 'recordedfuture'")
        if job_data["api_vendor"] == "threatstream":
            cq = job_data.get("custom_query")
            if not isinstance(cq, str) or not cq.strip():
                raise ValueError(
                    "Gather API findings jobs with api_vendor 'threatstream' require a non-empty string 'custom_query'"
                )
        if "date_range_hours" in job_data:
            if not isinstance(job_data["date_range_hours"], int) or job_data["date_range_hours"] < 0 or job_data["date_range_hours"] > 8760:
                raise ValueError("date_range_hours must be an integer between 0 and 8760 (1 year). Use 0 for no date filtering.")

    elif job_type == JobType.SYNC_RECORDEDFUTURE_DATA:
        if "program_name" not in job_data or not isinstance(job_data["program_name"], str):
            raise ValueError("Sync RecordedFuture data jobs require 'program_name' field as a string")
        if not job_data["program_name"]:
            raise ValueError("Program name cannot be empty")

        # Validate sync_options if provided
        if "sync_options" in job_data:
            sync_options = job_data["sync_options"]
            if not isinstance(sync_options, dict):
                raise ValueError("sync_options must be a dictionary")

            if "batch_size" in sync_options:
                if not isinstance(sync_options["batch_size"], int) or sync_options["batch_size"] < 10 or sync_options["batch_size"] > 200:
                    raise ValueError("batch_size must be an integer between 10 and 200")

            if "max_age_days" in sync_options:
                if not isinstance(sync_options["max_age_days"], int) or sync_options["max_age_days"] < 0 or sync_options["max_age_days"] > 365:
                    raise ValueError("max_age_days must be an integer between 0 and 365")

            if "include_screenshots" in sync_options:
                if not isinstance(sync_options["include_screenshots"], bool):
                    raise ValueError("include_screenshots must be a boolean")

    elif job_type == JobType.WORKFLOW:
        if "workflow_id" not in job_data:
            raise ValueError("Workflow jobs require 'workflow_id' field")
        #if "program_name" not in job_data:
        #    raise ValueError("Workflow jobs require 'program_name' field")
        
        # Validate workflow variables if provided
        if "workflow_variables" in job_data:
            from repository import WorkflowDefinitionRepository
            from utils.workflow_processor import validate_variables
            
            try:
                # Load workflow definition to validate variables
                workflow_repo = WorkflowDefinitionRepository()
                workflow_definition = await workflow_repo.get_workflow_definition(job_data["workflow_id"])
                
                if workflow_definition:
                    # Create workflow data structure for validation
                    workflow_data = {
                        "steps": workflow_definition.get("steps", []),
                        "variables": workflow_definition.get("variables", {}),
                        "inputs": workflow_definition.get("inputs", {})
                    }
                    
                    # Validate variables
                    validation = validate_variables(workflow_data, job_data["workflow_variables"])
                    if not validation["success"]:
                        raise ValueError(f"Workflow variable validation failed: {', '.join(validation['errors'])}")
                else:
                    logger.warning(f"Workflow definition not found for validation: {job_data['workflow_id']}")
            except Exception as e:
                logger.error(f"Error validating workflow variables: {str(e)}")
                # Don't fail the job creation if validation fails, just log it
    
    else:
        raise ValueError(f"Unsupported job type: {job_type}") 