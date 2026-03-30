from fastapi import APIRouter, Depends, HTTPException
from models.postgres import FindingsStatsResponse, AggregatedFindingsStatsResponse
from repository import CommonFindingsRepository
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs
from models.user_postgres import UserResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/common/stats", response_model=AggregatedFindingsStatsResponse)
async def get_aggregated_findings_stats(current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Get aggregated findings statistics across all programs accessible to the user.
    
    Returns counts for both Nuclei findings (by severity) and Typosquat findings (by status).
    """
    try:
        # Get user's accessible programs
        accessible_programs = get_user_accessible_programs(current_user)
        
        # For superusers/admins, accessible_programs is empty (meaning no restrictions)
        # For regular users, we'll filter to only their accessible programs
        if accessible_programs:
            # Regular user - only get stats for accessible programs
            stats = await CommonFindingsRepository.get_aggregated_findings_stats(accessible_programs)
        else:
            # Superuser/admin - get stats for all programs
            stats = await CommonFindingsRepository.get_aggregated_findings_stats()
        
        return stats
        
    except Exception as e:
        logger.error(f"Error retrieving aggregated findings stats: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error while retrieving aggregated findings stats: {str(e)}"
        )

@router.get("/common/stats/{program_name}", response_model=FindingsStatsResponse)
async def get_findings_stats(program_name: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Get detailed findings statistics for a specific program.
    
    Returns counts for both Nuclei findings (by severity) and Typosquat findings (by status).
    """
    try:
        # Check if user has access to this program
        if not current_user.is_superuser and "admin" not in current_user.roles:
            # Check if user has access to this specific program
            user_programs = current_user.program_permissions.keys()
            if program_name not in user_programs:
                raise HTTPException(
                    status_code=403, 
                    detail=f"Access denied to program '{program_name}'"
                )
        
        # Get findings stats
        filter_data = {"program_name": program_name}
        stats = await CommonFindingsRepository.get_detailed_findings_stats(filter_data)
        
        return stats
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error retrieving findings stats for program '{program_name}': {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error while retrieving findings stats: {str(e)}"
        )
