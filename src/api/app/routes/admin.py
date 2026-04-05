from fastapi import APIRouter, HTTPException, Depends, Path, Body, Query
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from repository import AdminRepository
from auth.dependencies import require_superuser, require_admin_or_manager
from models.user_postgres import UserResponse
from datetime import datetime
import logging
import os
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic models for request/response
class ReconTaskParametersRequest(BaseModel):
    """Request model for setting recon task parameters"""
    parameters: Dict[str, Any] = Field(..., description="Task parameters dictionary")

class ReconTaskParametersResponse(BaseModel):
    """Response model for recon task parameters"""
    id: Optional[str] = Field(None, description="Document ID")
    recon_task: str = Field(..., description="Name of the recon task")
    parameters: Dict[str, Any] = Field(..., description="Task parameters")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")

class ReconTaskParametersListResponse(BaseModel):
    """Response model for listing recon task parameters"""
    status: str = Field(..., description="Response status")
    tasks: List[ReconTaskParametersResponse] = Field(..., description="List of recon task parameters")
    total: int = Field(..., description="Total number of tasks")

class LastExecutionThresholdRequest(BaseModel):
    """Request model for setting last execution threshold"""
    last_execution_threshold: int = Field(..., ge=1, description="Last execution threshold in hours")

class LastExecutionThresholdResponse(BaseModel):
    """Response model for last execution threshold"""
    recon_task: str = Field(..., description="Name of the recon task")
    last_execution_threshold: int = Field(..., description="Last execution threshold in hours")

class ChunkSizeRequest(BaseModel):
    """Request model for setting chunk size"""
    chunk_size: int = Field(..., ge=1, description="Chunk size (number of items per chunk)")

class ChunkSizeResponse(BaseModel):
    """Response model for chunk size"""
    recon_task: str = Field(..., description="Name of the recon task")
    chunk_size: int = Field(..., description="Chunk size (number of items per chunk)")

class AwsCredentialRequest(BaseModel):
    """Request model for creating/updating AWS credentials"""
    name: str = Field(..., min_length=1, max_length=255, description="Name for the credential set")
    access_key: str = Field(..., min_length=1, max_length=255, description="AWS access key ID")
    secret_access_key: str = Field(..., min_length=1, max_length=255, description="AWS secret access key")
    default_region: str = Field(..., min_length=1, max_length=50, description="Default AWS region")
    is_active: Optional[bool] = Field(True, description="Whether the credential is active")

class AwsCredentialResponse(BaseModel):
    """Response model for AWS credentials"""
    id: str = Field(..., description="Credential ID")
    name: str = Field(..., description="Name for the credential set")
    access_key: str = Field(..., description="AWS access key ID")
    secret_access_key: str = Field(..., description="AWS secret access key")
    default_region: str = Field(..., description="Default AWS region")
    is_active: bool = Field(..., description="Whether the credential is active")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")

class AwsCredentialListResponse(BaseModel):
    """Response model for listing AWS credentials"""
    status: str = Field(..., description="Response status")
    credentials: List[AwsCredentialResponse] = Field(..., description="List of AWS credentials")
    total: int = Field(..., description="Total number of credentials")

@router.get("/recon-tasks/parameters", response_model=ReconTaskParametersListResponse)
async def list_recon_task_parameters(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    List all recon task parameters (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        tasks = await admin_repo.list_recon_task_parameters()
        
        # Convert to response models
        task_responses = []
        for task in tasks:
            task_responses.append(ReconTaskParametersResponse(**task))
        
        return ReconTaskParametersListResponse(
            status="success",
            tasks=task_responses,
            total=len(task_responses)
        )
        
    except Exception as e:
        logger.error(f"Error listing recon task parameters: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recon-tasks/{recon_task}/parameters", response_model=ReconTaskParametersResponse)
async def get_recon_task_parameters(
    recon_task: str = Path(..., description="Name of the recon task"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get parameters for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        task_params = await admin_repo.get_recon_task_parameters(recon_task)
        
        if not task_params:
            raise HTTPException(
                status_code=404,
                detail=f"Parameters for recon task '{recon_task}' not found"
            )
        
        return ReconTaskParametersResponse(**task_params)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recon task parameters for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/public/recon-tasks/{recon_task}/parameters", response_model=ReconTaskParametersResponse)
async def get_recon_task_parameters_public(
    recon_task: str = Path(..., description="Name of the recon task")
):
    """
    Get parameters for a specific recon task (public endpoint - no authentication required)
    This endpoint is used by the runner to fetch task parameters.
    """
    try:
        admin_repo = AdminRepository()
        task_params = await admin_repo.get_recon_task_parameters(recon_task)
        
        if not task_params:
            raise HTTPException(
                status_code=404,
                detail=f"Parameters for recon task '{recon_task}' not found"
            )
        
        return ReconTaskParametersResponse(**task_params)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recon task parameters for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/recon-tasks/{recon_task}/parameters", response_model=ReconTaskParametersResponse)
async def create_recon_task_parameters(
    recon_task: str = Path(..., description="Name of the recon task"),
    request: ReconTaskParametersRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Create parameters for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        
        # Check if parameters already exist
        existing = await admin_repo.get_recon_task_parameters(recon_task)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Parameters for recon task '{recon_task}' already exist. Use PUT to update."
            )
        
        # Create new parameters
        task_params = await admin_repo.set_recon_task_parameters(recon_task, request.parameters)
        
        if not task_params:
            raise HTTPException(status_code=500, detail="Failed to create recon task parameters")
        
        return ReconTaskParametersResponse(**task_params)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating recon task parameters for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/recon-tasks/{recon_task}/parameters", response_model=ReconTaskParametersResponse)
async def update_recon_task_parameters(
    recon_task: str = Path(..., description="Name of the recon task"),
    request: ReconTaskParametersRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Update parameters for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        
        # Update parameters
        task_params = await admin_repo.set_recon_task_parameters(recon_task, request.parameters)
        
        if not task_params:
            raise HTTPException(status_code=500, detail="Failed to update recon task parameters")
        
        return ReconTaskParametersResponse(**task_params)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating recon task parameters for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/recon-tasks/{recon_task}/parameters")
async def delete_recon_task_parameters(
    recon_task: str = Path(..., description="Name of the recon task"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Delete parameters for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        
        # Check if parameters exist
        existing = await admin_repo.get_recon_task_parameters(recon_task)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Parameters for recon task '{recon_task}' not found"
            )
        
        # Delete parameters
        deleted = await admin_repo.delete_recon_task_parameters(recon_task)
        
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete recon task parameters")
        
        return {
            "status": "success",
            "message": f"Parameters for recon task '{recon_task}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting recon task parameters for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recon-tasks/{recon_task}/last-execution-threshold", response_model=LastExecutionThresholdResponse)
async def get_last_execution_threshold(
    recon_task: str = Path(..., description="Name of the recon task"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get the last execution threshold for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        threshold = await admin_repo.get_last_execution_threshold(recon_task)
        
        if threshold is None:
            raise HTTPException(
                status_code=404,
                detail=f"Last execution threshold for recon task '{recon_task}' not found"
            )
        
        return LastExecutionThresholdResponse(
            recon_task=recon_task,
            last_execution_threshold=threshold
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting last execution threshold for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/recon-tasks/{recon_task}/last-execution-threshold", response_model=LastExecutionThresholdResponse)
async def set_last_execution_threshold(
    recon_task: str = Path(..., description="Name of the recon task"),
    request: LastExecutionThresholdRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Set the last execution threshold for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        
        # Get existing parameters or create new ones
        existing_params = await admin_repo.get_recon_task_parameters(recon_task)
        if existing_params:
            parameters = existing_params.get("parameters", {})
        else:
            parameters = {}
        
        # Update the last execution threshold
        parameters["last_execution_threshold"] = request.last_execution_threshold
        
        # Save the updated parameters
        task_params = await admin_repo.set_recon_task_parameters(recon_task, parameters)
        
        if not task_params:
            raise HTTPException(status_code=500, detail="Failed to set last execution threshold")
        
        return LastExecutionThresholdResponse(
            recon_task=recon_task,
            last_execution_threshold=request.last_execution_threshold
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting last execution threshold for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recon-tasks/{recon_task}/chunk-size", response_model=ChunkSizeResponse)
async def get_chunk_size(
    recon_task: str = Path(..., description="Name of the recon task"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get the chunk size for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        chunk_size = await admin_repo.get_chunk_size(recon_task)
        
        if chunk_size is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chunk size for recon task '{recon_task}' not found"
            )
        
        return ChunkSizeResponse(
            recon_task=recon_task,
            chunk_size=chunk_size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chunk size for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/recon-tasks/{recon_task}/chunk-size", response_model=ChunkSizeResponse)
async def set_chunk_size(
    recon_task: str = Path(..., description="Name of the recon task"),
    request: ChunkSizeRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Set the chunk size for a specific recon task (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        
        # Get existing parameters or create new ones
        existing_params = await admin_repo.get_recon_task_parameters(recon_task)
        if existing_params:
            parameters = existing_params.get("parameters", {})
        else:
            parameters = {}
        
        # Update the chunk size
        parameters["chunk_size"] = request.chunk_size
        
        # Save the updated parameters
        task_params = await admin_repo.set_recon_task_parameters(recon_task, parameters)
        
        if not task_params:
            raise HTTPException(status_code=500, detail="Failed to set chunk size")
        
        return ChunkSizeResponse(
            recon_task=recon_task,
            chunk_size=request.chunk_size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting chunk size for {recon_task}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Internal Service Token Management Models
class InternalTokenCreateRequest(BaseModel):
    """Request model for creating internal service tokens"""
    name: str = Field(..., min_length=1, max_length=100, description="Token name")
    description: Optional[str] = Field(None, max_length=500, description="Token description")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Token expiration in days")

class InternalTokenResponse(BaseModel):
    """Response model for internal service token (without token value)"""
    id: str = Field(..., description="Token ID")
    name: str = Field(..., description="Token name")
    description: Optional[str] = Field(None, description="Token description")
    is_active: bool = Field(..., description="Whether token is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")

class InternalTokenCreateResponse(BaseModel):
    """Response model for creating internal service tokens (includes token value)"""
    id: str = Field(..., description="Token ID")
    name: str = Field(..., description="Token name")
    description: Optional[str] = Field(None, description="Token description")
    token: str = Field(..., description="Generated token (only shown once)")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")

class InternalTokenListResponse(BaseModel):
    """Response model for listing internal service tokens"""
    status: str = Field(..., description="Response status")
    tokens: List[InternalTokenResponse] = Field(..., description="List of internal tokens")
    total: int = Field(..., description="Total number of tokens")

class AiSettingsUpdateRequest(BaseModel):
    """Request model for updating AI settings (merge into existing)"""
    typosquat: Optional[Dict[str, Any]] = Field(None, description="Typosquat AI settings")
    ollama: Optional[Dict[str, Any]] = Field(None, description="Ollama URL, model, timeout, retries")

# Internal Service Token Management Endpoints
@router.get("/internal-tokens", response_model=InternalTokenListResponse)
async def list_internal_tokens(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    List all internal service tokens (superuser only)
    """
    try:
        from services.internal_token_service import InternalTokenService
        token_service = InternalTokenService()
        tokens = await token_service.list_tokens()
        
        return InternalTokenListResponse(
            status="success",
            tokens=tokens,
            total=len(tokens)
        )
        
    except Exception as e:
        logger.error(f"Error listing internal tokens: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/internal-tokens", response_model=InternalTokenCreateResponse)
async def create_internal_token(
    request: InternalTokenCreateRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Create a new internal service token (superuser only)
    """
    try:
        from services.internal_token_service import InternalTokenService
        token_service = InternalTokenService()
        
        token = await token_service.create_internal_token(
            name=request.name,
            description=request.description,
            expires_in_days=request.expires_in_days
        )
        
        # Get token info (without the actual token)
        tokens = await token_service.list_tokens()
        created_token = next((t for t in tokens if t["name"] == request.name), None)
        
        if not created_token:
            raise HTTPException(status_code=500, detail="Token created but could not retrieve details")
        
        return InternalTokenCreateResponse(
            id=created_token["id"],
            name=created_token["name"],
            description=created_token["description"],
            token=token,
            expires_at=created_token["expires_at"]
        )
        
    except Exception as e:
        logger.error(f"Error creating internal token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/internal-tokens/{token_id}/rotate")
async def rotate_internal_token(
    token_id: str = Path(..., description="Token ID to rotate"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Rotate an internal service token (superuser only)
    """
    try:
        from services.internal_token_service import InternalTokenService
        token_service = InternalTokenService()
        
        new_token = await token_service.rotate_token(token_id)
        
        return {
            "status": "success",
            "message": "Token rotated successfully",
            "new_token": new_token
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error rotating internal token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/internal-tokens/{token_id}")
async def deactivate_internal_token(
    token_id: str = Path(..., description="Token ID to deactivate"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Deactivate an internal service token (superuser only)
    """
    try:
        from services.internal_token_service import InternalTokenService
        token_service = InternalTokenService()
        
        success = await token_service.deactivate_token(token_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Token not found")
        
        return {
            "status": "success",
            "message": "Token deactivated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating internal token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# AI Settings Endpoints
@router.get("/ai-settings", response_model=Dict[str, Any])
async def get_ai_settings(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get AI settings merged with in-code defaults (superuser only).
    Returns full structure for all features (typosquat, future: nuclei, etc.).
    """
    try:
        from services.ai_analysis_service import get_ai_settings as get_ai_settings_impl
        settings = await get_ai_settings_impl()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error(f"Error getting AI settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai-settings/defaults", response_model=Dict[str, Any])
async def get_ai_settings_defaults(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get in-code default AI settings (for reset) (superuser only).
    """
    try:
        from services.ai_analysis_service import _get_default_ai_settings_structure
        return {"status": "success", "settings": _get_default_ai_settings_structure()}
    except Exception as e:
        logger.error(f"Error getting AI settings defaults: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/ai-settings", response_model=Dict[str, Any])
async def update_ai_settings(
    request: AiSettingsUpdateRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Update AI settings (merge into existing) (superuser only).
    """
    try:
        from services.ai_analysis_service import get_ai_settings
        admin_repo = AdminRepository()
        row = await admin_repo.get_system_setting("ai_settings")
        current = (row or {}).get("value", {}) if isinstance(row, dict) else {}
        if not isinstance(current, dict):
            current = {}

        # Merge request into current
        if request.typosquat:
            current.setdefault("typosquat", {})
            for k, v in request.typosquat.items():
                if v is not None:
                    current["typosquat"][k] = v

        if request.ollama:
            current.setdefault("ollama", {})
            for k, v in request.ollama.items():
                if v is not None:
                    current["ollama"][k] = v

        await admin_repo.set_system_setting("ai_settings", current)
        settings = await get_ai_settings()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error(f"Error updating AI settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/list-all-parameters")
async def debug_list_all_parameters(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Debug endpoint to list all parameters in database
    """
    try:
        admin_repo = AdminRepository()

        # Get all task names and their parameters
        tasks = await admin_repo.list_recon_task_parameters()

        return {
            "status": "success",
            "message": f"Found {len(tasks)} recon task parameter entries",
            "tasks": tasks
        }
    except Exception as e:
        logger.error(f"Error listing all parameters: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# === AWS Credentials Management Endpoints ===

@router.get("/aws-credentials", response_model=AwsCredentialListResponse)
async def list_aws_credentials(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    List all AWS credentials (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        credentials = await admin_repo.list_aws_credentials()

        # Convert to response models
        credential_responses = []
        for cred in credentials:
            credential_responses.append(AwsCredentialResponse(**cred))

        return AwsCredentialListResponse(
            status="success",
            credentials=credential_responses,
            total=len(credential_responses)
        )

    except Exception as e:
        logger.error(f"Error listing AWS credentials: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/aws-credentials/{credential_id}", response_model=AwsCredentialResponse)
async def get_aws_credential(
    credential_id: str = Path(..., description="ID of the AWS credential"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get a specific AWS credential by ID (superuser only)
    """
    try:
        admin_repo = AdminRepository()
        credential = await admin_repo.get_aws_credential(credential_id)

        if not credential:
            raise HTTPException(
                status_code=404,
                detail=f"AWS credential with ID '{credential_id}' not found"
            )

        return AwsCredentialResponse(**credential)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AWS credential {credential_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/aws-credentials", response_model=AwsCredentialResponse)
async def create_aws_credential(
    request: AwsCredentialRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Create a new AWS credential (superuser only)
    """
    try:
        admin_repo = AdminRepository()

        # Create new credential
        credential = await admin_repo.create_aws_credential(
            name=request.name,
            access_key=request.access_key,
            secret_access_key=request.secret_access_key,
            default_region=request.default_region,
            is_active=request.is_active if request.is_active is not None else True
        )

        if not credential:
            raise HTTPException(status_code=500, detail="Failed to create AWS credential")

        return AwsCredentialResponse(**credential)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating AWS credential: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/aws-credentials/{credential_id}", response_model=AwsCredentialResponse)
async def update_aws_credential(
    credential_id: str = Path(..., description="ID of the AWS credential"),
    request: AwsCredentialRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Update an existing AWS credential (superuser only)
    """
    try:
        admin_repo = AdminRepository()

        # Update credential
        update_data = {
            "name": request.name,
            "access_key": request.access_key,
            "secret_access_key": request.secret_access_key,
            "default_region": request.default_region,
            "is_active": request.is_active if request.is_active is not None else True
        }

        credential = await admin_repo.update_aws_credential(credential_id, update_data)

        if not credential:
            raise HTTPException(
                status_code=404,
                detail=f"AWS credential with ID '{credential_id}' not found"
            )

        return AwsCredentialResponse(**credential)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating AWS credential {credential_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/aws-credentials/{credential_id}")
async def delete_aws_credential(
    credential_id: str = Path(..., description="ID of the AWS credential"),
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Delete an AWS credential (superuser only)
    """
    try:
        admin_repo = AdminRepository()

        # Check if credential exists
        existing = await admin_repo.get_aws_credential(credential_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"AWS credential with ID '{credential_id}' not found"
            )

        # Delete credential
        deleted = await admin_repo.delete_aws_credential(credential_id)

        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete AWS credential")

        return {
            "status": "success",
            "message": f"AWS credential '{existing['name']}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting AWS credential {credential_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# NATS Event Queue Statistics
class EventsPurgeRequest(BaseModel):
    confirm: Literal["PURGE_EVENTS"] = Field(
        ...,
        description='Must be exactly "PURGE_EVENTS" to purge the stream',
    )


class EventsDeleteMessagesRequest(BaseModel):
    sequences: List[int] = Field(..., min_length=1, max_length=500)

    @field_validator("sequences")
    @classmethod
    def validate_sequences(cls, v: List[int]) -> List[int]:
        if any(s < 1 for s in v):
            raise ValueError("sequence numbers must be positive integers")
        # stable order for NATS calls
        return sorted(set(v))


@router.get("/events/stats", response_model=Dict[str, Any])
async def get_events_stats(
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """
    Get NATS JetStream event queue statistics (admin or manager).
    Returns stream and consumer metrics for the EVENTS stream.
    """
    try:
        from services.nats_stats import get_event_stats
        return await get_event_stats()
    except Exception as e:
        logger.error(f"Error fetching event stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/batches", response_model=Dict[str, Any])
async def get_events_batches(
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """
    Get event-handler batches waiting in Redis (admin or manager).
    Batches are accumulated by handler (e.g. subdomain_resolve_workflow) and
    program, and flushed when max_events or max_delay is reached.
    """
    try:
        from services.event_batches import get_event_batches
        return get_event_batches()
    except Exception as e:
        logger.error(f"Error fetching event batches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/pending", response_model=Dict[str, Any])
async def get_events_pending(
    limit: int = 50,
    search: Optional[str] = Query(
        None,
        description="Substring match on subject and payload (case-insensitive); scans up to max_scan sequences",
    ),
    max_scan: int = Query(
        5000,
        ge=1,
        le=50000,
        description="Max stream messages to examine when search is set",
    ),
    current_user: UserResponse = Depends(require_admin_or_manager),
):
    """
    Get pending messages from the NATS EVENTS stream (admin or manager).
    Uses direct stream read - does NOT consume or ack messages, so the
    event-handler can still process them normally.
    """
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    try:
        from services.nats_stats import get_pending_messages
        return await get_pending_messages(limit=limit, search=search, max_scan=max_scan)
    except Exception as e:
        logger.error(f"Error fetching pending messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/events/purge", response_model=Dict[str, Any])
async def post_events_purge(
    body: EventsPurgeRequest,
    current_user: UserResponse = Depends(require_admin_or_manager),
):
    """
    Purge all messages from the NATS EVENTS JetStream stream (admin or manager).
    Destructive: includes in-flight / unacknowledged messages for this stream.
    """
    logger.warning(
        "NATS EVENTS stream purge by user id=%s email=%s",
        getattr(current_user, "id", None),
        getattr(current_user, "email", None),
    )
    try:
        from services.nats_stats import purge_events_stream
        return await purge_events_stream()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error purging EVENTS stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/events/messages/delete", response_model=Dict[str, Any])
async def post_events_messages_delete(
    body: EventsDeleteMessagesRequest,
    current_user: UserResponse = Depends(require_admin_or_manager),
):
    """
    Delete specific messages from the EVENTS stream by JetStream sequence (admin or manager).
    """
    logger.warning(
        "NATS EVENTS stream batch delete: %s sequence(s) by user id=%s email=%s",
        len(body.sequences),
        getattr(current_user, "id", None),
        getattr(current_user, "email", None),
    )
    try:
        from services.nats_stats import delete_event_messages_by_seq
        return await delete_event_messages_by_seq(body.sequences)
    except Exception as e:
        logger.error(f"Error deleting EVENTS messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# CT Monitor Control Endpoints
CT_MONITOR_URL = os.getenv("CT_MONITOR_URL", "http://ct-monitor:8002")

@router.get("/ct-monitor/status", response_model=Dict[str, Any])
async def get_ct_monitor_status(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get CT monitor service status and statistics (superuser only)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{CT_MONITOR_URL}/status")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.error("Timeout connecting to CT monitor service")
        raise HTTPException(
            status_code=503,
            detail="CT monitor service is not responding"
        )
    except httpx.ConnectError:
        logger.error(f"Failed to connect to CT monitor service at {CT_MONITOR_URL}")
        raise HTTPException(
            status_code=503,
            detail="CT monitor service is unavailable"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"CT monitor service returned error: {e.response.status_code}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"CT monitor service error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Error getting CT monitor status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ct-monitor/start", response_model=Dict[str, Any])
async def start_ct_monitor(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Start the CT monitor service (superuser only)
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{CT_MONITOR_URL}/start")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.error("Timeout starting CT monitor service")
        raise HTTPException(
            status_code=503,
            detail="CT monitor service is not responding"
        )
    except httpx.ConnectError:
        logger.error(f"Failed to connect to CT monitor service at {CT_MONITOR_URL}")
        raise HTTPException(
            status_code=503,
            detail="CT monitor service is unavailable"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"CT monitor service returned error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail.get("message", "Failed to start CT monitor")
            )
        except Exception:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"CT monitor service error: {e.response.text}"
            )
    except Exception as e:
        logger.error(f"Error starting CT monitor: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ct-monitor/stop", response_model=Dict[str, Any])
async def stop_ct_monitor(
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Stop the CT monitor service (superuser only)
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{CT_MONITOR_URL}/stop")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.error("Timeout stopping CT monitor service")
        raise HTTPException(
            status_code=503,
            detail="CT monitor service is not responding"
        )
    except httpx.ConnectError:
        logger.error(f"Failed to connect to CT monitor service at {CT_MONITOR_URL}")
        raise HTTPException(
            status_code=503,
            detail="CT monitor service is unavailable"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"CT monitor service returned error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail.get("message", "Failed to stop CT monitor")
            )
        except Exception:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"CT monitor service error: {e.response.text}"
            )
    except Exception as e:
        logger.error(f"Error stopping CT monitor: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-status")
async def get_system_status(
    current_user: UserResponse = Depends(require_superuser)
):
    """Return platform version and live Deployment status from the Kubernetes cluster."""
    try:
        from services.kubernetes import KubernetesService
        k8s = KubernetesService()
        services = k8s.list_deployments()
    except Exception as e:
        logger.error(f"Error querying Kubernetes deployments: {e}")
        services = []

    return {
        "app_version": os.getenv("APP_VERSION", "dev"),
        "services": services,
    }


class CtMonitorRuntimeUpdateRequest(BaseModel):
    """Partial update for global CT monitor runtime (stored in system_settings)."""

    domain_refresh_interval: Optional[int] = Field(None, ge=1, le=86400)
    stats_interval: Optional[int] = Field(None, ge=1, le=3600)
    ct_poll_interval: Optional[int] = Field(None, ge=1, le=600)
    ct_batch_size: Optional[int] = Field(None, ge=1, le=5000)
    ct_max_entries_per_poll: Optional[int] = Field(None, ge=1, le=100000)
    ct_start_offset: Optional[int] = Field(None, ge=0, le=10_000_000)


@router.get("/ct-monitor/runtime-settings", response_model=Dict[str, Any])
async def get_ct_monitor_runtime_settings_admin(
    current_user: UserResponse = Depends(require_superuser),
):
    """Get merged CT monitor runtime settings (superuser)."""
    try:
        from services.ct_monitor_runtime_settings import get_ct_monitor_runtime_merged

        settings = await get_ct_monitor_runtime_merged()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error("Error getting ct_monitor runtime settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ct-monitor/runtime-settings", response_model=Dict[str, Any])
async def put_ct_monitor_runtime_settings_admin(
    request: CtMonitorRuntimeUpdateRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser),
):
    """Update CT monitor runtime settings; notifies ct-monitor to reload (superuser)."""
    try:
        from services.ct_monitor_runtime_settings import update_ct_monitor_runtime_partial
        from services.ct_monitor_client import notify_ct_monitor_reload_runtime_settings

        payload = request.model_dump(exclude_none=True)
        if not payload:
            raise HTTPException(status_code=400, detail="No fields to update")
        settings = await update_ct_monitor_runtime_partial(payload)
        await notify_ct_monitor_reload_runtime_settings()
        return {"status": "success", "settings": settings}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating ct_monitor runtime settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class WorkflowKubernetesUpdateRequest(BaseModel):
    """Partial update for workflow runner/worker images (stored in system_settings)."""

    runner_image: Optional[str] = None
    worker_image: Optional[str] = None
    image_pull_policy: Optional[Literal["Always", "Never", "IfNotPresent"]] = None


@router.get("/workflow-kubernetes-settings", response_model=Dict[str, Any])
async def get_workflow_kubernetes_settings_admin(
    current_user: UserResponse = Depends(require_superuser),
):
    """Get effective workflow K8s image settings (merged with APP_VERSION defaults) (superuser)."""
    try:
        from services.workflow_kubernetes_settings import get_workflow_kubernetes_merged

        settings = await get_workflow_kubernetes_merged()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error("Error getting workflow kubernetes settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow-kubernetes-settings/defaults", response_model=Dict[str, Any])
async def get_workflow_kubernetes_settings_defaults_admin(
    current_user: UserResponse = Depends(require_superuser),
):
    """Built-in defaults from current APP_VERSION (superuser)."""
    try:
        from services.workflow_kubernetes_settings import builtin_workflow_kubernetes_defaults

        return {"status": "success", "settings": builtin_workflow_kubernetes_defaults()}
    except Exception as e:
        logger.error("Error getting workflow kubernetes defaults: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/workflow-kubernetes-settings", response_model=Dict[str, Any])
async def put_workflow_kubernetes_settings_admin(
    request: WorkflowKubernetesUpdateRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser),
):
    """Partial update of stored overrides; effective settings returned (superuser)."""
    try:
        from services.workflow_kubernetes_settings import update_workflow_kubernetes_partial

        payload = request.model_dump(exclude_unset=True)
        if not payload:
            raise HTTPException(status_code=400, detail="No fields to update")
        settings = await update_workflow_kubernetes_partial(payload)
        return {"status": "success", "settings": settings}
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("Error updating workflow kubernetes settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workflow-kubernetes-settings", response_model=Dict[str, Any])
async def delete_workflow_kubernetes_settings_admin(
    current_user: UserResponse = Depends(require_superuser),
):
    """Remove stored overrides so effective settings follow APP_VERSION defaults (superuser)."""
    try:
        from services.workflow_kubernetes_settings import (
            WORKFLOW_KUBERNETES_KEY,
            get_workflow_kubernetes_merged,
        )

        admin_repo = AdminRepository()
        await admin_repo.delete_system_setting(WORKFLOW_KUBERNETES_KEY)
        settings = await get_workflow_kubernetes_merged()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error("Error deleting workflow kubernetes settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
