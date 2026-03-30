from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
import logging
from models.postgres import SocialMediaCredentialsCreate, SocialMediaCredentialsUpdate, SocialMediaCredentialsResponse
from repository.social_media_credentials_repo import SocialMediaCredentialsRepository
from auth.dependencies import require_admin_or_manager, require_internal_service_or_authentication
from models.user_postgres import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/social-media-credentials", response_model=SocialMediaCredentialsResponse)
async def create_social_media_credential(
    credential: SocialMediaCredentialsCreate,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Create a new social media credential set (admin only)"""
    try:
        credential_dict = credential.model_dump()
        credential_id = await SocialMediaCredentialsRepository.create_credential(credential_dict)
        
        created_credential = await SocialMediaCredentialsRepository.get_credential_by_id(credential_id)
        if not created_credential:
            raise HTTPException(status_code=404, detail="Social media credential not found after creation")
        
        logger.info(f"Successfully created social media credential with ID: {credential_id}")
        return SocialMediaCredentialsResponse(**created_credential)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating social media credential: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create social media credential: {str(e)}")

@router.get("/social-media-credentials", response_model=List[SocialMediaCredentialsResponse])
async def list_social_media_credentials(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """List all social media credential sets (admin only)"""
    try:
        credentials = await SocialMediaCredentialsRepository.list_all_credentials(platform)
        return [SocialMediaCredentialsResponse(**cred) for cred in credentials]
        
    except Exception as e:
        logger.error(f"Error listing social media credentials: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list social media credentials: {str(e)}")

@router.get("/social-media-credentials/{platform}", response_model=SocialMediaCredentialsResponse)
async def get_active_credentials_by_platform(
    platform: str,
    current_user: UserResponse = Depends(require_internal_service_or_authentication)
):
    """Get active credentials for a specific platform (internal service endpoint)"""
    try:
        credential = await SocialMediaCredentialsRepository.get_active_by_platform(platform)
        
        if not credential:
            raise HTTPException(status_code=404, detail=f"No active credentials found for platform: {platform}")
        
        return SocialMediaCredentialsResponse(**credential)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting credentials for platform {platform}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get credentials for platform: {str(e)}")

@router.get("/social-media-credentials/id/{credential_id}", response_model=SocialMediaCredentialsResponse)
async def get_social_media_credential_by_id(
    credential_id: str,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Get a social media credential set by ID (admin only)"""
    try:
        credential = await SocialMediaCredentialsRepository.get_credential_by_id(credential_id)
        
        if not credential:
            raise HTTPException(status_code=404, detail="Social media credential not found")
        
        return SocialMediaCredentialsResponse(**credential)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting social media credential: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get social media credential: {str(e)}")

@router.put("/social-media-credentials/{credential_id}", response_model=SocialMediaCredentialsResponse)
async def update_social_media_credential(
    credential_id: str,
    update_data: SocialMediaCredentialsUpdate,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Update a social media credential set (admin only)"""
    try:
        updated = await SocialMediaCredentialsRepository.update_credential(
            credential_id,
            update_data.model_dump(exclude_none=True)
        )
        
        if not updated:
            raise HTTPException(status_code=404, detail="Social media credential not found")
        
        return SocialMediaCredentialsResponse(**updated)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating social media credential: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update social media credential: {str(e)}")

@router.delete("/social-media-credentials/{credential_id}")
async def delete_social_media_credential(
    credential_id: str,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a social media credential set (admin only)"""
    try:
        deleted = await SocialMediaCredentialsRepository.delete_credential(credential_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Social media credential not found")
        
        return {"status": "success", "message": "Social media credential deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting social media credential: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete social media credential: {str(e)}")

