from fastapi import APIRouter, HTTPException, Depends
from repository import ProgramRepository, CommonAssetsRepository
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs
from models.user_postgres import UserResponse
from models.postgres import AssetStatsResponse, AggregatedAssetStatsResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# GET endpoint for AGGREGATED stats across all accessible programs
@router.get("/common/stats", response_model=AggregatedAssetStatsResponse, tags=["Stats"])
async def get_aggregated_asset_stats(current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Get aggregated asset stats across all programs accessible to the user.
    Provides breakdowns for resolved/unresolved domains/IPs and root/non-root URLs.
    """
    try:
        # Get user's accessible programs
        accessible_programs = get_user_accessible_programs(current_user)
        
        # For superusers/admins, accessible_programs is empty (meaning no restrictions)
        # For regular users, we'll filter to only their accessible programs
        if accessible_programs:
            # Regular user - only get stats for accessible programs
            detailed_stats = await CommonAssetsRepository.get_aggregated_asset_stats(accessible_programs)
        else:
            # Superuser/admin - get stats for all programs
            detailed_stats = await CommonAssetsRepository.get_aggregated_asset_stats()
        
        logger.info("Retrieved aggregated asset stats for user")
        return detailed_stats

    except Exception as e:
        logger.error(f"Error calculating aggregated asset stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating aggregated asset stats: {str(e)}"
        )

# GET endpoint for DETAILED program stats counts
@router.get("/common/stats/{program_name}", response_model=AssetStatsResponse, tags=["Stats"])
async def get_program_asset_stats_detailed_get(program_name: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Get detailed counts of assets for a specific program.
    Provides breakdowns for resolved/unresolved domains/IPs and root/non-root URLs.
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
        
        # Check if program exists first
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")

        # Base filter is just the program name
        combined_filter = {"program_name": program_name}
        detailed_stats = await CommonAssetsRepository.get_detailed_asset_stats(combined_filter)
        return detailed_stats

    except HTTPException: # Re-raise HTTP exceptions
        raise
    except ValueError as ve: # Catch specific ValueErrors like invalid asset type from repo
        logger.error(f"Value error calculating program asset stats for {program_name}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error calculating program asset stats for {program_name}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating program asset stats: {str(e)}"
        )
