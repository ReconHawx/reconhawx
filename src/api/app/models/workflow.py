from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

class InputDefinition(BaseModel):
    """Definition for a single workflow input source."""
    type: str = Field(..., description="Type of input: 'program_asset', 'program_finding', or 'direct'")
    asset_type: Optional[str] = Field(None, description="For program_asset, the type of asset (e.g., 'apex-domain')")
    finding_type: Optional[str] = Field(None, description="For program_finding, the type of finding (e.g., 'typosquat_url')")
    value_type: Optional[str] = Field(None, description="For direct input, the type of value (e.g., 'domains', 'urls')")
    values: Optional[List[Any]] = Field(None, description="For direct input, the list of static values")
    filter: Optional[str] = Field(None, description="Jinja2 filter to apply to program assets or findings")
    filter_type: Optional[str] = Field(None, description="Filter type for program assets (e.g., 'resolved', 'unresolved')")
    limit: Optional[int] = Field(None, description="Limit the number of items from program assets or findings")
    min_similarity_percent: Optional[float] = Field(None, description="For typosquat_domain/typosquat_apex_domain: minimum similarity % with protected domain (0-100)")
    similarity_protected_domain: Optional[str] = Field(None, description="For typosquat_domain/typosquat_apex_domain: filter by this protected domain")

class TaskDefinition(BaseModel):
    """Task definition for workflow execution (New Format)"""
    name: str = Field(..., description="Unique name for this task instance within the step")
    task_type: Optional[str] = Field(None, description="The type of task to run (e.g., 'subdomain_finder') - optional for backward compatibility")
    input_mapping: Optional[Dict[str, Union[List[str], str]]] = Field(None, description="Mapping of task inputs to workflow inputs or previous task outputs (supports multiple sources per input)")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)
    force: Optional[bool] = False
    output_mode: Optional[str] = Field(None, description="Output mode: 'assets' (default) or 'typosquat_findings'")
    use_proxy: Optional[bool] = Field(None, description="Enable AWS API Gateway proxying via FireProx for supported tasks")

class WorkflowStep(BaseModel):
    """Step model for workflow execution - matches frontend format"""
    name: str
    tasks: List[TaskDefinition]

class WorkflowRequest(BaseModel):
    """Request for creating/saving a workflow definition (program_name is optional)"""
    workflow_name: str
    program_name: Optional[str] = Field(None, description="Program name for program-specific workflows. If null, workflow is global")
    description: Optional[str] = None
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict)
    inputs: Optional[Dict[str, InputDefinition]] = Field(default_factory=dict, description="Centralized workflow inputs")
    steps: List[WorkflowStep]
    workflow_definition_id: Optional[str] = Field(None, description="ID of existing workflow definition if running a saved workflow")

class WorkflowRunRequest(BaseModel):
    """Request for running a workflow (program_name is required)"""
    workflow_name: str
    program_name: str = Field(..., description="Program name where the workflow will be executed")
    description: Optional[str] = None
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict)
    inputs: Optional[Dict[str, InputDefinition]] = Field(default_factory=dict, description="Centralized workflow inputs")
    steps: List[WorkflowStep]
    workflow_definition_id: Optional[str] = Field(None, description="ID of existing workflow definition if running a saved workflow")

class WorkflowCreateResponse(BaseModel):
    workflow_id: str
    status: str
    status_url: str

class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    status: str
    progress: Dict[str, Any]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    workflow_steps: List[Dict[str, Any]] = Field(default_factory=list)

class WorkflowListResponse(BaseModel):
    workflow_id: str
    name: str
    program_name: Optional[str] = Field(None, description="Program name if workflow is program-specific, null if global")
    status: str
    created_at: datetime
    updated_at: datetime

class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    task_name: Optional[str] = None
    step_name: Optional[str] = None
    status_url: Optional[str] = None

class WorkflowTasksResponse(BaseModel):
    workflow_id: str
    tasks: List[TaskStatus]
    count: int

class WorkflowPostLogsResponse(BaseModel):
    execution_id: str
    status: str

class WorkflowLogs(BaseModel):
    execution_id: Optional[str] = None
    program_name: str
    workflow_name: str
    result: str
    workflow_steps: List[Dict[str, Any]] = Field(default_factory=list)
    workflow_definition: Optional[Dict[str, Any]] = None
    runner_pod_output: Optional[str] = None
    task_execution_logs: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class WorkflowLogsListResponse(BaseModel):
    workflows: List[WorkflowLogs]
    total: int

class TaskStatusResponse(BaseModel):
    task_id: str
    workflow_id: str
    status: str
    output: str 