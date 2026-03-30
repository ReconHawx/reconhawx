from fastapi import APIRouter, HTTPException, Query, Depends, Body
from typing import Dict, Any, Optional, List
import logging
from models.findings import BrokenLink, BrokenLinkCreate, BrokenLinkUpdate, BrokenLinkSearchRequest
from repository.broken_links_repo import BrokenLinksRepository
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs, require_admin_or_manager
from models.user_postgres import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/broken-links", response_model=BrokenLink)
async def create_broken_link(
    finding: BrokenLinkCreate,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a new broken link finding or update if exists"""
    try:
        # Check program access
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and 'admin' not in current_user.roles:
            if finding.program_name not in (accessible or []):
                raise HTTPException(status_code=403, detail="Access denied to this program")
        
        finding_dict = finding.model_dump()
        finding_id, action = await BrokenLinksRepository.create_or_update_broken_link(finding_dict)
        
        created_finding = await BrokenLinksRepository.get_broken_link_by_id(finding_id)
        if not created_finding:
            raise HTTPException(status_code=404, detail="Broken link finding not found after creation")
        
        logger.info(f"Successfully {action} broken link finding with ID: {finding_id}")
        return BrokenLink(**created_finding)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating broken link finding: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create broken link finding: {str(e)}")

@router.post("/broken-links/search", response_model=Dict[str, Any])
async def search_broken_links(
    request: BrokenLinkSearchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Search broken links with filtering and pagination"""
    try:
        # Check program access
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and 'admin' not in current_user.roles:
            if request.program_name and request.program_name not in (accessible or []):
                raise HTTPException(status_code=403, detail="Access denied to this program")
            # If no program specified, filter to accessible programs
            if not request.program_name and not accessible:
                return {'findings': [], 'total': 0, 'page': 1, 'page_size': request.page_size, 'total_pages': 0}
        
        result = await BrokenLinksRepository.search_broken_links(
            program_name=request.program_name,
            link_type=request.link_type,
            media_type=request.media_type,
            status=request.status,
            domain_search=request.domain_search,
            sort_by=request.sort_by,
            sort_dir=request.sort_dir,
            page=request.page,
            page_size=request.page_size
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching broken links: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to search broken links: {str(e)}")

@router.get("/broken-links/{finding_id}", response_model=BrokenLink)
async def get_broken_link(
    finding_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a single broken link finding by ID"""
    try:
        finding = await BrokenLinksRepository.get_broken_link_by_id(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail="Broken link finding not found")
        
        # Check program access
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and 'admin' not in current_user.roles:
            if finding['program_name'] not in (accessible or []):
                raise HTTPException(status_code=403, detail="Access denied to this finding")
        
        return BrokenLink(**finding)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting broken link finding: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get broken link finding: {str(e)}")

@router.put("/broken-links/{finding_id}", response_model=BrokenLink)
async def update_broken_link(
    finding_id: str,
    update_data: BrokenLinkUpdate,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update a broken link finding"""
    try:
        # Get existing finding to check access
        existing = await BrokenLinksRepository.get_broken_link_by_id(finding_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Broken link finding not found")
        
        # Check program access
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and 'admin' not in current_user.roles:
            if existing['program_name'] not in (accessible or []):
                raise HTTPException(status_code=403, detail="Access denied to this finding")
        
        updated = await BrokenLinksRepository.update_broken_link(finding_id, update_data.model_dump(exclude_none=True))
        
        if not updated:
            raise HTTPException(status_code=404, detail="Broken link finding not found")
        
        return BrokenLink(**updated)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating broken link finding: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update broken link finding: {str(e)}")

@router.delete("/broken-links/batch", response_model=Dict[str, Any])
async def delete_broken_links_batch(
    finding_ids: List[str] = Body(...),
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple broken link findings by their IDs"""
    try:
        if not finding_ids:
            raise HTTPException(status_code=400, detail="No finding IDs provided")
        
        result = await BrokenLinksRepository.delete_broken_links_batch(finding_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for broken link findings",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting broken link findings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to batch delete broken link findings: {str(e)}")

@router.delete("/broken-links/{finding_id}")
async def delete_broken_link(
    finding_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a broken link finding"""
    try:
        # Get existing finding to check access
        existing = await BrokenLinksRepository.get_broken_link_by_id(finding_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Broken link finding not found")
        
        # Check program access
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and 'admin' not in current_user.roles:
            if existing['program_name'] not in (accessible or []):
                raise HTTPException(status_code=403, detail="Access denied to this finding")
        
        deleted = await BrokenLinksRepository.delete_broken_link(finding_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Broken link finding not found")
        
        return {"status": "success", "message": "Broken link finding deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting broken link finding: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete broken link finding: {str(e)}")

@router.get("/broken-links/stats", response_model=Dict[str, Any])
async def get_broken_links_stats(
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get statistics for broken links"""
    try:
        # Check program access
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and 'admin' not in current_user.roles:
            if program_name and program_name not in (accessible or []):
                raise HTTPException(status_code=403, detail="Access denied to this program")
        
        stats = await BrokenLinksRepository.get_broken_links_stats(program_name)
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting broken links stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get broken links stats: {str(e)}")

