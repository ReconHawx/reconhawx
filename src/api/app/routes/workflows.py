import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Query, Request, Depends, status
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import logging
import uuid
import os

from repository import WorkflowRepository, WorkflowDefinitionRepository
from models.workflow import (
    WorkflowRequest,
    WorkflowCreateResponse,
    WorkflowStatusResponse,
    WorkflowTasksResponse,
    WorkflowPostLogsResponse,
    TaskStatus,
    WorkflowLogs,
    WorkflowLogsListResponse
)
from models.user_postgres import UserResponse
from auth.dependencies import get_current_user_from_middleware, filter_by_user_programs, check_program_permission
from services.kubernetes import KubernetesService
from utils import create_status_url

logger = logging.getLogger(__name__)
router = APIRouter()

# Terminal workflow `result` values from the runner; used to trigger ConfigMap cleanup on log POST.
_TERMINAL_WORKFLOW_RESULTS = frozenset(
    {"success", "completed", "failed", "stopped", "cancelled"}
)

# Initialize services
k8s_service = KubernetesService()
workflow_repository = WorkflowRepository()
workflow_definition_repository = WorkflowDefinitionRepository()

# Create a thread pool executor for running blocking Kubernetes operations
thread_pool = ThreadPoolExecutor(max_workers=4)

# === WORKFLOW DEFINITIONS (CRUD) ===

class WorkflowDefinition(BaseModel):
    name: str = Field(..., description="Workflow name")
    program_name: Optional[str] = Field(None, description="Program this workflow belongs to (optional, can be set at runtime)")
    description: Optional[str] = Field(None, description="Workflow description")
    steps: List[Dict[str, Any]] = Field(..., description="Workflow steps")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Workflow variables")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Workflow inputs")

class WorkflowResponse(BaseModel):
    id: str
    name: str
    program_name: Optional[str]
    description: Optional[str]
    steps: List[Dict[str, Any]]
    variables: Dict[str, Any]
    inputs: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class WorkflowListResponse(BaseModel):
    status: str = "success"
    workflows: List[WorkflowResponse]
    count: int



@router.get("/definitions", response_model=WorkflowListResponse)
async def get_workflow_definitions(
    program_name: Optional[str] = Query(None, description="Filter by program name ('global' for global workflows, 'all' for all workflows)"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get all saved workflow definitions"""
    try:
        # Get workflow definitions from PostgreSQL repository
        workflows_data = await workflow_definition_repository.get_workflow_definitions(program_name)
        
        # Filter workflows based on user permissions
        accessible_workflows = []
        for workflow_data in workflows_data:
            workflow_program = workflow_data.get("program_name")
            
            # Global workflows are accessible to everyone
            if not workflow_program:
                accessible_workflows.append(workflow_data)
                continue
            
            # Check program permission for program-specific workflows
            if check_program_permission(current_user, workflow_program, "analyst"):
                accessible_workflows.append(workflow_data)
        
        workflows = []
        for workflow_data in accessible_workflows:
            workflows.append(WorkflowResponse(**workflow_data))
        
        return WorkflowListResponse(
            workflows=workflows,
            count=len(workflows)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workflows: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching workflows: {str(e)}")

@router.post("/definitions", response_model=WorkflowResponse)
async def create_workflow_definition(
    workflow: WorkflowDefinition,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a new workflow definition"""
    try:
        # Check program permission for creation if program is specified
        if workflow.program_name and not check_program_permission(current_user, workflow.program_name, "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Manager access required to create workflows in program {workflow.program_name}"
            )
        
        # Check superuser permission for creating global workflows
        if not workflow.program_name and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superuser access required to create global workflows"
            )
        
        # Check for duplicate name within the same scope
        has_conflict = await workflow_definition_repository.check_name_conflict(
            workflow.name, workflow.program_name
        )
        
        if has_conflict:
            scope_desc = f"in program '{workflow.program_name}'" if workflow.program_name else "globally"
            raise HTTPException(
                status_code=400, 
                detail=f"Workflow '{workflow.name}' already exists {scope_desc}"
            )
        
        # Create workflow document
        workflow_doc = {
            'name': workflow.name,
            'program_name': workflow.program_name,  # Can be None for global workflows
            'description': workflow.description,
            'steps': workflow.steps,
            'variables': workflow.variables,
            'inputs': workflow.inputs
        }
        
        # Create in PostgreSQL database
        created_workflow = await workflow_definition_repository.create_workflow_definition(workflow_doc)
        
        return WorkflowResponse(**created_workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating workflow: {str(e)}")

@router.get("/definitions/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow_definition(
    workflow_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a specific workflow definition by ID"""
    try:
        # Get workflow from PostgreSQL repository
        workflow = await workflow_definition_repository.get_workflow_definition(workflow_id)
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Check program permission if workflow belongs to a specific program
        workflow_program = workflow.get("program_name")
        if workflow_program and not check_program_permission(current_user, workflow_program, "analyst"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to workflow in program {workflow_program}"
            )
        
        return WorkflowResponse(**workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching workflow: {str(e)}")

@router.put("/definitions/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow_definition(
    workflow_id: str, 
    workflow: WorkflowDefinition,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update an existing workflow definition"""
    try:
        # Check if workflow exists
        existing = await workflow_definition_repository.get_workflow_definition(workflow_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Check program permission for existing workflow
        existing_program = existing.get("program_name")
        if existing_program and not check_program_permission(current_user, existing_program, "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Manager access required to update workflow in program {existing_program}"
            )
        
        # Check superuser permission for global workflows
        if not existing_program and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superuser access required to update global workflows"
            )
        
        # Check program permission for new program if different
        if workflow.program_name and workflow.program_name != existing_program:
            if not check_program_permission(current_user, workflow.program_name, "manager"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Manager access required to move workflow to program {workflow.program_name}"
                )
        
        # Check for name conflicts within the same scope
        has_conflict = await workflow_definition_repository.check_name_conflict(
            workflow.name, workflow.program_name, workflow_id
        )
        
        if has_conflict:
            scope_desc = f"in program '{workflow.program_name}'" if workflow.program_name else "globally"
            raise HTTPException(
                status_code=400, 
                detail=f"Workflow '{workflow.name}' already exists {scope_desc}"
            )
        
        # Update workflow
        update_data = {
            'name': workflow.name,
            'program_name': workflow.program_name,  # Can be None for global workflows
            'description': workflow.description,
            'steps': workflow.steps,
            'variables': workflow.variables,
            'inputs': workflow.inputs
        }
        
        # Update in PostgreSQL database
        updated_workflow = await workflow_definition_repository.update_workflow_definition(workflow_id, update_data)
        
        if not updated_workflow:
            raise HTTPException(status_code=500, detail="Failed to update workflow")
        
        return WorkflowResponse(**updated_workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating workflow: {str(e)}")

@router.delete("/definitions/{workflow_id}")
async def delete_workflow_definition(
    workflow_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a workflow definition"""
    try:
        # Check if workflow exists and get its program
        existing = await workflow_definition_repository.get_workflow_definition(workflow_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Check program permission for deletion
        existing_program = existing.get("program_name")
        if existing_program and not check_program_permission(current_user, existing_program, "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Manager access required to delete workflow in program {existing_program}"
            )
        
        # Check superuser permission for global workflows
        if not existing_program and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superuser access required to delete global workflows"
            )
        
        # Delete from PostgreSQL database
        deleted = await workflow_definition_repository.delete_workflow_definition(workflow_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return {"status": "success", "message": "Workflow definition deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting workflow: {str(e)}")

# === WORKFLOW EXECUTIONS ===

# Define pagination query model
class QueryFilter(BaseModel):
    filter: Dict[str, Any] = Field(default_factory=dict)
    limit: Optional[int] = 25
    page: Optional[int] = 1
    sort: Optional[Dict[str, int]] = None

class WorkflowStatusListResponse(BaseModel):
    status: str = "success"
    executions: List[Dict[str, Any]]
    total_pages: int
    current_page: int
    total_items: int

@router.post("/run", response_model=WorkflowCreateResponse)
async def run_workflow(
    request: Request, 
    workflow_request: WorkflowRequest,
    priority: str = Query("normal", description="Workflow priority: low, normal, high, critical"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Execute a workflow"""
    try:
        import json
        logger.debug(f"Workflow request: {json.dumps(workflow_request.model_dump())}")
        # Check program permission for workflow execution
        if workflow_request.program_name and not check_program_permission(current_user, workflow_request.program_name, "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Manager access required to execute workflows in program {workflow_request.program_name}"
            )
        
        # If using a saved workflow definition, check access to it
        if workflow_request.workflow_definition_id:
            workflow_def = await workflow_definition_repository.get_workflow_definition(workflow_request.workflow_definition_id)
            if workflow_def and workflow_def.get("program_name"):
                if not check_program_permission(current_user, workflow_def["program_name"], "analyst"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Access denied to workflow definition in program {workflow_def['program_name']}"
                    )
        
        environment = os.getenv('KUBERNETES_NAMESPACE', '')
        logger.info(f"Environment: {environment}")
        execution_id = str(uuid.uuid4())
        
        # Determine workflow_id based on whether this is a saved workflow or custom workflow
        workflow_id = workflow_request.workflow_definition_id if workflow_request.workflow_definition_id else None
        
        logger.info(f"Running workflow {workflow_request.workflow_name} with {len(workflow_request.steps)} steps")
        logger.info(f"Execution ID: {execution_id}, Workflow Definition ID: {workflow_id}")

        # Validate priority
        valid_priorities = ['low', 'normal', 'high', 'critical']
        if priority not in valid_priorities:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid priority. Must be one of: {', '.join(valid_priorities)}"
            )
        
        # The new frontend sends a complete, runnable definition.
        # We just need to ensure it's structured correctly for the runner.
        workflow_data = {
            "workflow_id": workflow_id,  # Use workflow definition ID (or None for custom workflows)
            "execution_id": execution_id,  # Pass the execution ID separately
            "program_name": workflow_request.program_name,
            "name": workflow_request.workflow_name,
            "description": workflow_request.description,
            "priority": priority,  # Add priority to workflow data
            "variables": workflow_request.variables or {},
            "inputs": {k: v.dict() if hasattr(v, 'dict') else v for k, v in (workflow_request.inputs or {}).items()},
            "steps": [step.dict(exclude_none=False) for step in workflow_request.steps]
        }

        logger.info(f"Workflow request received with {len(workflow_request.inputs or {})} inputs and {len(workflow_request.variables or {})} variables")

        # Try to create the runner job with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await k8s_service.create_runner_job(workflow_data)
                logger.info(f"Successfully created runner job for workflow: {execution_id}")
                break
            except Exception as e:
                logger.error(f"Error creating Kubernetes job (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    # Last attempt failed
                    raise HTTPException(status_code=500, detail=f"Failed to run workflow after {max_retries} attempts: {str(e)}")
                else:
                    # Wait before retry
                    import time
                    time.sleep(1)

        # Create pending workflow log so status page shows workflow immediately
        pending_log = {
            "execution_id": execution_id,
            "workflow_name": workflow_request.workflow_name,
            "program_name": workflow_request.program_name,
            "workflow_definition_id": workflow_id,
            "result": "pending",
            "workflow_steps": [],
            "workflow_definition": workflow_data
        }
        try:
            await workflow_repository.create_workflow_log(pending_log)
        except Exception as e:
            logger.warning(f"Failed to create pending workflow log: {e}")
            # Don't fail the request - workflow will appear when runner starts

        return WorkflowCreateResponse(
            workflow_id=execution_id,
            status="started",
            status_url=create_status_url(request, "workflow", execution_id)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in workflow execution: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/executions", response_model=WorkflowStatusListResponse)
async def get_workflow_executions(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    sort_field: Optional[str] = Query(None, description="Field to sort by"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc or desc)"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get paginated list of workflow executions"""
    try:
        # Build filter query
        filter_query = {}
        if program_name:
            filter_query['program_name'] = program_name
        
        # Apply user program permissions to the query filter
        filtered_query = filter_by_user_programs(filter_query, current_user)
        logger.info(f"Filtered query: {filtered_query}")
        # Sanitize the query
        sanitized_query = await workflow_repository.sanitize_query(filtered_query)
        logger.info(f"Sanitized query: {sanitized_query}")
        # Count total items
        total_count = await workflow_repository.count_workflow_logs(sanitized_query)
        
        # Calculate pagination
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
        skip = (page - 1) * limit
        
        
        # Build sort parameter
        sort_order_int = -1 if sort_order == "desc" else 1
        if sort_field:
            # Map frontend field names to database field names
            field_mapping = {
                "workflow_name": "workflow_name",
                "program_name": "program_name", 
                "status": "result",
                "started_at": "created_at",
                "completed_at": "updated_at",
                "progress": "created_at"  # Default to created_at for progress sorting
            }
            db_field = field_mapping.get(sort_field, "created_at")
            sort_param = {db_field: sort_order_int}
        else:
            # Default sort by creation date, recent first
            sort_param = {"created_at": -1}
        
        # Execute query
        executions = await workflow_repository.execute_query(
            sanitized_query,
            limit=limit,
            skip=skip,
            sort=sort_param
        )
        
        logger.info(f"Retrieved {len(executions)} executions from database")
        
        # Transform executions for frontend consumption
        transformed_executions = []
        for execution in executions:
            # Extract execution info from workflow log structure
            execution_data = {
                "id": execution.get("execution_id", execution.get("workflow_id", execution.get("_id", ""))),
                "workflow_name": execution.get("workflow_name", execution.get("workflow_id", "Unknown")),
                "program_name": execution.get("program_name", "Unknown"),
                "status": execution.get("result", "unknown").lower(),
                "started_at": execution.get("created_at"),
                "completed_at": execution.get("updated_at") if execution.get("result") in ["success", "completed", "failed"] else None,
                "progress": {
                    "completed": 0,
                    "total": 0,
                    "percentage": 0
                },
                "workflow_steps": execution.get("workflow_steps", [])
            }
            
            # Calculate progress based on workflow steps
            completed_steps = 0
            total_steps = execution.get("total_steps", 0)  # Use stored total_steps if available
            
            # Count completed steps from workflow_steps execution results  
            if "workflow_steps" in execution and execution["workflow_steps"]:
                for step in execution["workflow_steps"]:
                    if isinstance(step, dict):
                        for step_name, step_data in step.items():
                            # If step_data has content (like {"domain": 1, "ip": 1}), consider it completed
                            if step_data and isinstance(step_data, dict) and step_data:
                                completed_steps += 1
                                break  # Only count the step once
            
            # Fallback logic if we don't have total_steps stored
            if total_steps == 0:
                if "workflow_steps" in execution and execution["workflow_steps"]:
                    # For older logs without total_steps, use the length of workflow_steps as total
                    total_steps = len(execution["workflow_steps"])
                else:
                    # For workflows with no steps yet, estimate from result status
                    if execution.get("result") == "running":
                        total_steps = 1  # Assume at least 1 step for running workflows
                    elif execution.get("result") in ["success", "failed", "completed"]:
                        total_steps = 1
                        if execution.get("result") == "success":
                            completed_steps = 1
            
            # Set progress information
            execution_data["progress"] = {
                "completed": completed_steps,
                "total": total_steps,
                "percentage": (completed_steps / total_steps * 100) if total_steps > 0 else 0
            }
            
            transformed_executions.append(execution_data)
        
        logger.info(f"Transformed {len(transformed_executions)} executions for frontend")
        
        return WorkflowStatusListResponse(
            executions=transformed_executions,
            total_pages=total_pages,
            current_page=page,
            total_items=total_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workflow status list: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching workflow status: {str(e)}")

@router.get("/executions/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_execution_status(
    workflow_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get detailed status for a specific workflow execution"""
    try:
        # Get workflow logs from database by execution_id
        workflow_log = await workflow_repository.get_workflow_logs_by_execution_id(workflow_id)
        
        if not workflow_log:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        # Check program permission for this workflow execution
        workflow_program = workflow_log.get("program_name")
        if workflow_program and not check_program_permission(current_user, workflow_program, "analyst"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to workflow execution in program {workflow_program}"
            )
        
        # Extract status from workflow log
        result = workflow_log.get("result", "unknown")
        current_status = result.lower() if isinstance(result, str) else "unknown"
        
        # Format output from workflow logs
        output_parts = []
        
        # Add basic workflow info
        workflow_name = workflow_log.get("name") or workflow_log.get("workflow_id", "Unknown")
        output_parts.append(f"Workflow: {workflow_name}")
        
        if workflow_log.get("program_name"):
            output_parts.append(f"Program: {workflow_log['program_name']}")
        if workflow_log.get("created_at"):
            output_parts.append(f"Started: {workflow_log['created_at']}")
        if workflow_log.get("updated_at"):
            output_parts.append(f"Updated: {workflow_log['updated_at']}")
        
        output_parts.append(f"Status: {current_status}")
        
        # Add workflow steps information if available
        workflow_steps = workflow_log.get("workflow_steps", [])
        if workflow_steps:
            output_parts.append("\nWorkflow Steps:")
            for i, step in enumerate(workflow_steps, 1):
                if isinstance(step, dict):
                    for step_name, step_data in step.items():
                        if step_data and isinstance(step_data, dict):
                            # Show the results/counts for completed steps
                            results = []
                            for key, value in step_data.items():
                                results.append(f"{key}: {value}")
                            step_status = f"completed ({', '.join(results)})"
                        else:
                            step_status = "pending"
                        output_parts.append(f"  {i}. {step_name}: {step_status}")
        
        # Add any execution output if available
        if workflow_log.get("output"):
            output_parts.append(f"\nExecution Output:\n{workflow_log['output']}")
        
        # Add error information if available
        if workflow_log.get("error"):
            output_parts.append(f"\nError:\n{workflow_log['error']}")
        
        "\n".join(output_parts)
        
        # Calculate progress
        completed_steps = 0
        total_steps = len(workflow_steps) if workflow_steps else 1
        
        for step in workflow_steps:
            if isinstance(step, dict):
                for step_name, step_data in step.items():
                    if step_data and isinstance(step_data, dict) and step_data:
                        completed_steps += 1
                        break
        
        progress = {
            "completed": completed_steps,
            "total": total_steps,
            "percentage": (completed_steps / total_steps * 100) if total_steps > 0 else 0
        }
        
        # Handle datetime conversion
        started_at = workflow_log.get("created_at")
        completed_at = workflow_log.get("updated_at") if current_status in ["success", "completed", "failed"] else None
        
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=current_status,
            progress=progress,
            started_at=started_at if isinstance(started_at, datetime) else None,
            completed_at=completed_at if isinstance(completed_at, datetime) else None,
            workflow_steps=[step for step in workflow_log.get("workflow_steps", []) if isinstance(step, dict)] if isinstance(workflow_log.get("workflow_steps"), list) else []
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow execution status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/executions/{workflow_id}/logs", response_model=WorkflowLogs)
async def get_workflow_execution_logs(
    workflow_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get logs for a specific workflow execution"""
    try:
        log = await workflow_repository.get_workflow_logs_by_execution_id(workflow_id)
        if not log:
            return WorkflowLogs(
                workflow_id=workflow_id,
                execution_id=None,
                program_name="",
                workflow_name="",
                result="not_found"
            )
        
        # Check program permission for this workflow execution
        workflow_program = log.get("program_name")
        if workflow_program and not check_program_permission(current_user, workflow_program, "analyst"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to workflow logs in program {workflow_program}"
            )
        
        # Ensure we have proper types for WorkflowLogs model
        started_at_val = log.get("started_at")
        completed_at_val = log.get("completed_at")
        created_at_val = log.get("created_at")
        updated_at_val = log.get("updated_at")

        # Parse ISO timestamp strings back to datetime objects
        def parse_timestamp(ts_val):
            from datetime import datetime
            if isinstance(ts_val, str) and ts_val.endswith('Z'):
                try:
                    # Remove 'Z' and parse as ISO format
                    return datetime.fromisoformat(ts_val[:-1])
                except ValueError:
                    return None
            elif isinstance(ts_val, datetime):
                return ts_val
            return None

        return WorkflowLogs(
            workflow_id=str(log.get("workflow_id", workflow_id)),
            execution_id=log.get("execution_id"),
            program_name=str(log.get("program_name", "")),
            workflow_name=str(log.get("workflow_name") or log.get("name", "")),
            result=str(log.get("result", "unknown")),
            workflow_steps=[step for step in log.get("workflow_steps", []) if isinstance(step, dict)] if isinstance(log.get("workflow_steps"), list) else [],
            workflow_definition=log.get("workflow_definition"),
            runner_pod_output=log.get("runner_pod_output"),
            task_execution_logs=[task_log for task_log in log.get("task_execution_logs", []) if isinstance(task_log, dict)] if isinstance(log.get("task_execution_logs"), list) else [],
            started_at=parse_timestamp(started_at_val),
            completed_at=parse_timestamp(completed_at_val),
            created_at=parse_timestamp(created_at_val),
            updated_at=parse_timestamp(updated_at_val)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting workflow logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/executions/{execution_id}/logs", response_model=WorkflowPostLogsResponse)
async def post_workflow_execution_logs(log_object: Dict[str, Any]):
    """Post logs for a workflow execution"""
    try:
        await workflow_repository.create_workflow_log(log_object)

        raw_result = log_object.get("result")
        execution_id_for_cleanup = log_object.get("execution_id")
        if (
            isinstance(raw_result, str)
            and raw_result.lower() in _TERMINAL_WORKFLOW_RESULTS
            and execution_id_for_cleanup
        ):

            def _delete_workflow_configmap_bg():
                try:
                    k8s_service.delete_workflow_configmap(str(execution_id_for_cleanup))
                except Exception as exc:
                    logger.warning(
                        "Background ConfigMap delete failed for execution %s: %s",
                        execution_id_for_cleanup,
                        exc,
                    )

            thread_pool.submit(_delete_workflow_configmap_bg)

        return WorkflowPostLogsResponse(
            execution_id=log_object["execution_id"],
            status="success"
        )
    except Exception as e:
        logger.error(f"Error posting workflow logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/executions/{execution_id}/tasks", response_model=WorkflowTasksResponse)
async def list_workflow_execution_tasks(
    request: Request, 
    execution_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """List all tasks for a workflow execution"""
    try:
        # Get workflow logs to check program permission
        workflow_log = await workflow_repository.get_workflow_logs_by_execution_id(execution_id)
        if not workflow_log:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        # Check program permission for viewing tasks
        workflow_program = workflow_log.get("program_name")
        if workflow_program and not check_program_permission(current_user, workflow_program, "analyst"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to workflow tasks in program {workflow_program}"
            )
        
        jobs = k8s_service.get_workflow_tasks(execution_id)
        workflow_tasks = []
        for job in jobs.items:
            if not job.metadata.labels or 'task-id' not in job.metadata.labels:
                logger.warning(f"Job {job.metadata.name} missing task-id label")
                continue
                
            task_id = job.metadata.labels['task-id']
            task_name = job.metadata.labels['task-name']
            step_name = job.metadata.labels['step-name']
            status = "running"
            if job.status.succeeded:
                status = "completed"
            elif job.status.failed:
                status = "failed"
                
            task_status = TaskStatus(
                task_id=task_id,
                started_at=job.status.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                completed_at=job.status.completion_time.strftime("%Y-%m-%d %H:%M:%S") if job.status.completion_time else None,
                task_name=task_name,
                step_name=step_name,
                status=status,
                status_url=create_status_url(request, "task", task_id)
            )
            workflow_tasks.append(task_status)
        
        return WorkflowTasksResponse(
            execution_id=execution_id,
            count=len(workflow_tasks),
            tasks=workflow_tasks
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/executions/{execution_id}")
async def delete_workflow_execution(
    execution_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a workflow execution and its associated resources"""
    try:
        # Get workflow logs to check program permission
        workflow_log = await workflow_repository.get_workflow_logs_by_execution_id(execution_id)
        if not workflow_log:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        # Check program permission for deletion
        workflow_program = workflow_log.get("program_name")
        if workflow_program and not check_program_permission(current_user, workflow_program, "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Manager access required to delete workflow execution in program {workflow_program}"
            )
        
        k8s_service.stop_workflow(execution_id)
        return {"message": f"Workflow execution {execution_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        if getattr(e, "status", None) == 404:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/executions/{execution_id}/stop")
async def stop_workflow_execution(
    execution_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Stop a running workflow execution and cancel all associated resources"""
    try:
        # Check if workflow exists in logs by execution_id
        workflow_log = await workflow_repository.get_workflow_logs_by_execution_id(execution_id)
        if not workflow_log:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        # Check program permission for stopping workflow
        workflow_program = workflow_log.get("program_name")
        if workflow_program and not check_program_permission(current_user, workflow_program, "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Manager access required to stop workflow execution in program {workflow_program}"
            )
        
        # Check if workflow is still running (can be stopped)
        result = workflow_log.get("result", "unknown")
        current_status = result.lower() if isinstance(result, str) else "unknown"
        if current_status in ["success", "completed", "failed", "stopped", "cancelled"]:
            return {
                "status": "already_finished",
                "message": f"Workflow {execution_id} is already {current_status} and cannot be stopped",
                "execution_id": execution_id
            }
        
        # Immediately update workflow status to 'stopping' to prevent race conditions
        try:
            update_data = {
                "result": "stopping",
                "updated_at": datetime.utcnow(),
                "stop_reason": "manually_stopped"
            }
            update_data["execution_id"] = execution_id
            await workflow_repository.create_workflow_log(update_data)
            logger.info(f"Updated workflow status to 'stopping' for {execution_id}")
        except Exception as e:
            logger.warning(f"Failed to update workflow status to 'stopping': {e}")
        
        # Run the Kubernetes cleanup in a background thread to avoid blocking the API
        def run_k8s_cleanup():
            try:
                logger.info(f"Starting background Kubernetes cleanup for workflow: {execution_id}")
                stop_results = k8s_service.stop_workflow(execution_id)
                logger.info(f"Kubernetes cleanup completed for workflow {execution_id}: {stop_results}")
                
                # Update workflow status to 'stopped' after cleanup is complete
                try:
                    final_update_data = {
                        "result": "stopped",
                        "updated_at": datetime.utcnow(),
                        "stop_reason": "manually_stopped",
                        "stop_results": stop_results
                    }
                    final_update_data["execution_id"] = execution_id
                    
                    # Use asyncio.run_coroutine_threadsafe to update from background thread
                    try:
                        loop = asyncio.get_event_loop()
                        future = asyncio.run_coroutine_threadsafe(
                            workflow_repository.create_workflow_log(final_update_data), 
                            loop
                        )
                        future.result()  # Wait for the update to complete
                        logger.info(f"Updated workflow status to 'stopped' for {execution_id}")
                    except RuntimeError:
                        # Event loop not available, try to create a new one
                        logger.warning(f"Event loop not available for workflow {execution_id}, creating new one")
                        asyncio.run(workflow_repository.create_workflow_log(final_update_data))
                        logger.info(f"Updated workflow status to 'stopped' for {execution_id} using new event loop")
                        
                except Exception as e:
                    logger.error(f"Failed to update final workflow status in database: {e}")
                    
            except Exception as e:
                logger.error(f"Error in background Kubernetes cleanup for workflow {execution_id}: {str(e)}")
                # Try to update status to 'failed' if cleanup fails
                try:
                    error_update_data = {
                        "result": "failed",
                        "updated_at": datetime.utcnow(),
                        "stop_reason": "cleanup_failed",
                        "stop_error": str(e)
                    }
                    error_update_data["execution_id"] = execution_id
                    
                    try:
                        loop = asyncio.get_event_loop()
                        future = asyncio.run_coroutine_threadsafe(
                            workflow_repository.create_workflow_log(error_update_data), 
                            loop
                        )
                        future.result()
                        logger.info(f"Updated workflow status to 'failed' due to cleanup error for {execution_id}")
                    except RuntimeError:
                        # Event loop not available, try to create a new one
                        logger.warning(f"Event loop not available for error update of workflow {execution_id}, creating new one")
                        asyncio.run(workflow_repository.create_workflow_log(error_update_data))
                        logger.info(f"Updated workflow status to 'failed' for {execution_id} using new event loop")
                        
                except Exception as update_error:
                    logger.error(f"Failed to update workflow status after cleanup error: {update_error}")
        
        # Submit the cleanup task to the thread pool
        thread_pool.submit(run_k8s_cleanup)
        
        return {
            "status": "stopping",
            "message": f"Workflow {execution_id} is being stopped. Cleanup is running in the background.",
            "execution_id": execution_id,
            "note": "The workflow status will be updated to 'stopped' once cleanup is complete."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping workflow execution {execution_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to stop workflow execution: {str(e)}"
        )

@router.get("/logs", response_model=WorkflowLogsListResponse)
async def get_all_workflow_logs(
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get all workflow logs without pagination (legacy endpoint)"""
    try:
        # Note: This endpoint returns all logs but should be filtered by program permissions
        # For now, we'll apply basic authentication but the repository should handle filtering
        logs = await workflow_repository.get_all_workflow_logs()
        logger.info(f"Raw logs from repository: {logs}")
        workflow_logs = []
        for log in logs:
            workflow_logs.append(WorkflowLogs(
                workflow_id=log.get("workflow_id", ""),
                execution_id=log.get("execution_id"),
                program_name=log.get("program_name", ""),
                workflow_name=log.get("workflow_name") or log.get("name", ""),
                result=log.get("result", "unknown"),
                workflow_steps=[step for step in log.get("workflow_steps", []) if isinstance(step, dict)] if isinstance(log.get("workflow_steps"), list) else [],
                created_at=log.get("created_at") if isinstance(log.get("created_at"), datetime) and not isinstance(log.get("created_at"), dict) else None,
                updated_at=log.get("updated_at") if isinstance(log.get("updated_at"), datetime) and not isinstance(log.get("updated_at"), dict) else None
            ))
        response = WorkflowLogsListResponse(
            workflows=workflow_logs,
            total=len(workflow_logs)
        )
        logger.info(f"Processed response: {response}")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting all workflow logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === KUEUE QUEUE MANAGEMENT ===

class WorkloadStatusResponse(BaseModel):
    execution_id: str
    status: str
    kueue_status: str
    queue_position: int
    priority: int
    queue_name: str
    resource_requirements: Dict[str, Any]
    created_at: str
    conditions: List[Dict[str, Any]]

class WorkloadListResponse(BaseModel):
    status: str = "success"
    workloads: List[Dict[str, Any]]
    count: int

class QueueCapacityResponse(BaseModel):
    queue_length: int
    has_capacity: bool
    estimated_wait_time: int
    queue_name: str
    error: Optional[str] = None

class PriorityUpdateRequest(BaseModel):
    priority: str = Field(..., description="Priority level: low, normal, high, critical")

@router.get("/queue/status", response_model=QueueCapacityResponse)
async def get_queue_status(
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get current queue status and capacity"""
    try:
        capacity_info = k8s_service.check_queue_capacity()
        return QueueCapacityResponse(**capacity_info)
    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/queue/workloads", response_model=WorkloadListResponse)
async def list_queue_workloads(
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """List all workloads in the queue"""
    try:
        workloads = k8s_service.list_workloads(program_name)
        
        # Filter workloads based on user permissions
        accessible_workloads = []
        for workload in workloads:
            workload_program = workload.get('program_name')
            
            # Check program permission for program-specific workloads
            if workload_program and not check_program_permission(current_user, workload_program, "analyst"):
                continue
            
            accessible_workloads.append(workload)
        
        return WorkloadListResponse(
            workloads=accessible_workloads,
            count=len(accessible_workloads)
        )
    except Exception as e:
        logger.error(f"Error listing queue workloads: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/queue/workloads/{execution_id}", response_model=WorkloadStatusResponse)
async def get_workload_status(
    execution_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get detailed status for a specific workload"""
    try:
        status_info = k8s_service.get_workload_status(execution_id)
        
        if status_info.get('status') == 'NotFound':
            raise HTTPException(status_code=404, detail="Workload not found")
        
        # Check program permission if we can determine the program
        # Note: We'd need to get this from the workload metadata or database
        # For now, we'll allow access and let the frontend handle filtering
        
        return WorkloadStatusResponse(**status_info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workload status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/queue/workloads/{execution_id}/priority")
async def update_workload_priority(
    execution_id: str,
    priority_request: PriorityUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update workload priority in queue"""
    try:
        # Validate priority value
        valid_priorities = ['low', 'normal', 'high', 'critical']
        if priority_request.priority not in valid_priorities:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid priority. Must be one of: {', '.join(valid_priorities)}"
            )
        
        success = k8s_service.update_workload_priority(execution_id, priority_request.priority)
        
        if not success:
            raise HTTPException(status_code=404, detail="Workload not found")
        
        return {
            "status": "success",
            "message": f"Workload priority updated to {priority_request.priority}",
            "execution_id": execution_id,
            "priority": priority_request.priority
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating workload priority: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/queue/workloads/{execution_id}")
async def delete_workload(
    execution_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a workload from the queue"""
    try:
        success = k8s_service.delete_workload(execution_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Workload not found")
        
        return {
            "status": "success",
            "message": f"Workload {execution_id} deleted successfully",
            "execution_id": execution_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/queue/workloads/{execution_id}/position")
async def get_workload_queue_position(
    execution_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get queue position for a specific workload"""
    try:
        status_info = k8s_service.get_workload_status(execution_id)
        
        if status_info.get('status') == 'NotFound':
            raise HTTPException(status_code=404, detail="Workload not found")
        
        return {
            "execution_id": execution_id,
            "queue_position": status_info.get('queue_position', -1),
            "queue_name": status_info.get('queue_name', ''),
            "status": status_info.get('status', 'Unknown'),
            "priority": status_info.get('priority', 5)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workload queue position: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))