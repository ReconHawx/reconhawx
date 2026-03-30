from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, model_validator
from datetime import datetime

class InputDefinition(BaseModel):
    """Definition for a single workflow input source."""
    type: str  # "program_asset", "program_finding", "program_protected_domains", or "direct"
    asset_type: Optional[str] = None  # For program_asset, the type of asset (e.g., 'apex-domain')
    finding_type: Optional[str] = None  # For program_finding, the type of finding (e.g., 'typosquat_url')
    value_type: Optional[str] = None  # For direct input, the type of value (e.g., 'domains', 'urls')
    values: Optional[List[Any]] = None  # For direct input, the list of static values
    filter: Optional[str] = None  # Jinja2 filter to apply to program assets or findings
    filter_type: Optional[str] = None  # Filter type for program assets (e.g., 'resolved', 'unresolved')
    limit: Optional[int] = None  # Limit the number of items from program assets or findings
    min_similarity_percent: Optional[float] = None  # For typosquat_domain/typosquat_apex_domain: min similarity % with protected domain (0-100)
    similarity_protected_domain: Optional[str] = None  # For typosquat_domain/typosquat_apex_domain: filter by this protected domain

class TaskDefinition(BaseModel):
    """Task definition for workflow execution (New Format)"""
    name: str
    task_type: Optional[str] = None  # Optional for backward compatibility - will use name if not provided
    input_mapping: Optional[Dict[str, Union[List[str], str]]] = None  # Mapping of task inputs to workflow inputs or previous task outputs (supports multiple sources per input)
    params: Optional[Dict[str, Any]] = None
    force: Optional[bool] = False
    output_mode: Optional[str] = None  # Output mode: "assets" (default) or "typosquat_findings"
    use_proxy: Optional[bool] = None  # Enable AWS API Gateway proxy for supported tasks (fuzz_website, nuclei_scan)

    # Legacy fields for backward compatibility
    input: Optional[List[str]] = None
    input_from: Optional[List[str]] = None
    input_limit: Optional[int] = None
    input_filter: Optional[str] = None
    internal: Optional[bool] = False

    model_config = {
        "extra": "allow",
        "validate_assignment": True,
        "validate_default": True,
        "arbitrary_types_allowed": True
    }

class WorkflowStep(BaseModel):
    """Step model for workflow execution - matches frontend format"""
    name: str
    tasks: List[TaskDefinition]

class Step(BaseModel):
    """Legacy step model for backward compatibility"""
    name: str
    tasks: List[TaskDefinition]

    model_config = {
        "extra": "allow",
        "validate_assignment": True,
        "validate_default": True,
        "arbitrary_types_allowed": True
    }

class WorkflowDefinition(BaseModel):
    """Workflow definition containing steps, inputs, and variables"""
    description: Optional[str] = None
    variables: Optional[Dict[str, Any]] = {}
    inputs: Dict[str, InputDefinition] = {}
    steps: List[WorkflowStep]

class Workflow(BaseModel):
    """Base workflow model - supports both old and new formats"""
    name: str
    program_name: Optional[str] = None  # Optional for workflow definitions, null means global
    steps: List[Union[Step, WorkflowStep]]
    
    # New format fields
    definition: Optional[WorkflowDefinition] = None
    
    # Legacy fields for backward compatibility
    variables: Optional[Dict[str, Any]] = {}
    inputs: Optional[Dict[str, InputDefinition]] = {}

    @model_validator(mode='after')
    def extract_definition_fields(self) -> 'Workflow':
        """Extract fields from definition if present for easier access"""
        if self.definition:
            # Use definition fields if available
            if not self.inputs:
                self.inputs = self.definition.inputs
            if not self.variables:
                self.variables = self.definition.variables
            # Replace steps if definition has steps
            if self.definition.steps:
                self.steps = self.definition.steps
        return self

class WorkflowRequest(BaseModel):
    """Model for workflow creation requests (program_name is optional for definitions)"""
    workflow_name: str
    program_name: Optional[str] = None  # Optional for workflow definitions
    steps: List[Step]

class WorkflowRunRequest(BaseModel):
    """Model for workflow execution requests (program_name is required)"""
    workflow_name: str
    program_name: str  # Required for workflow execution
    steps: List[Step]

class WorkflowCreateResponse(BaseModel):
    """Model for workflow creation response"""
    workflow_id: str
    status: str
    status_url: str

class WorkflowStatusResponse(BaseModel):
    """Model for workflow status response"""
    workflow_id: str
    status: str
    output: Optional[str] = ""

class WorkflowListResponse(BaseModel):
    """Model for workflow list response"""
    workflow_id: str
    name: str
    program_name: Optional[str] = None  # Optional for workflow definitions
    status: str

class TaskStatusResponse(BaseModel):
    """Model for task status response"""
    task_id: str
    workflow_id: str
    status: str
    output: Optional[str] = ""

class WorkflowPostLogsResponse(BaseModel):
    """Model for workflow post logs response"""
    workflow_id: str
    status: str

class WorkflowLogs(BaseModel):
    """Model for workflow logs"""
    _id: str
    program_name: str  # Required for workflow execution logs
    workflow_name: Optional[str] = None
    workflow_id: str
    workflow_steps: List[Dict[str, Dict[str, Any]]]
    result: str
    created_at: datetime
    updated_at: datetime
    total_steps: Optional[int] = None

class WorkflowLogsListResponse(BaseModel):
    """Model for workflow logs list response"""
    count: int
    items: List[WorkflowLogs]

class TaskStatus(BaseModel):
    """Model for task status"""
    task_id: str
    started_at: str
    completed_at: Optional[str] = None
    task_name: str
    step_name: str
    status: str
    status_url: str

class WorkflowTasksResponse(BaseModel):
    """Model for workflow tasks response"""
    workflow_id: str
    count: int
    tasks: List[TaskStatus]

class AssetStore:
    """Asset storage for workflow execution"""
    def __init__(self):
        self.assets: Dict[str, Dict[str, List[Any]]] = {}
    
    def add_step_assets(self, step_name: str, asset_type: str, assets: List[Any]):
        """Add assets from a step to the store"""
        if step_name not in self.assets:
            self.assets[step_name] = {}
        
        if asset_type not in self.assets[step_name]:
            self.assets[step_name][asset_type] = []
        
        self.assets[step_name][asset_type].extend(assets)
    
    def get_step_assets(self, step_name: str, asset_type: Optional[str] = None) -> Union[Dict[str, List[Any]], List[Any]]:
        """Get assets from a step"""
        if step_name not in self.assets:
            return {} if asset_type is None else []
        
        if asset_type is None:
            return self.assets[step_name]
        
        return self.assets[step_name].get(asset_type, [])
    
    def get_all_assets(self) -> Dict[str, Dict[str, List[Any]]]:
        """Get all assets"""
        return self.assets 