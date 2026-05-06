from fastapi import APIRouter, HTTPException, Depends, Query
from repository import ProgramRepository, CommonAssetsRepository
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs
from models.user_postgres import UserResponse
from models.postgres import AssetStatsResponse, AggregatedAssetStatsResponse, AssetTrendsResponse
import logging
from typing import Optional, List
from datetime import date

logger = logging.getLogger(__name__)
router = APIRouter()

# Sentinel name so `get_asset_trends(program_names=[...])` resolves to zero program_ids and returns empty buckets.
_EMPTY_TREND_PROGRAM_SCOPE = "__reconhawx__empty_trend_scope__"

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

        # Repository returns empty stats when the program row is missing (matches findings/common/stats).
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


def _parse_iso_date_optional(value: Optional[str], field: str) -> Optional[date]:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field}; use YYYY-MM-DD",
        ) from exc


@router.get("/common/trends", response_model=AssetTrendsResponse, tags=["Stats"])
async def get_asset_trends(
    days: int = Query(30, ge=1, le=366),
    program_name: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="Inclusive UTC calendar day (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Inclusive UTC calendar day (YYYY-MM-DD)"),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Daily counts of assets **created** per UTC day (for charts / sparklines).
    Either pass ``days`` (ending today UTC) or both ``start_date`` and ``end_date``.
    """
    sd = _parse_iso_date_optional(start_date, "start_date")
    ed = _parse_iso_date_optional(end_date, "end_date")
    if (sd is None) ^ (ed is None):
        raise HTTPException(
            status_code=400,
            detail="Both start_date and end_date are required for a custom range",
        )

    program_names_list: Optional[List[str]] = None
    selected_name: Optional[str] = None

    if program_name:
        selected_name = program_name
        if not current_user.is_superuser and "admin" not in current_user.roles:
            user_programs = current_user.program_permissions.keys()
            if program_name not in user_programs:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied to program '{program_name}'",
                )
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            # Stale UI filter or renamed program — match findings/common/stats soft-empty (avoid 404 on charts).
            logger.warning(
                "Program '%s' not found for asset trends; returning empty buckets",
                program_name,
            )
            program_names_list = [_EMPTY_TREND_PROGRAM_SCOPE]
        else:
            program_names_list = [program_name]
    else:
        accessible_programs = get_user_accessible_programs(current_user)
        if accessible_programs:
            program_names_list = list(accessible_programs)
        else:
            program_names_list = None

    try:
        result = await CommonAssetsRepository.get_asset_trends(
            program_names=program_names_list,
            start_day=sd,
            end_day=ed,
            days=days,
        )
        return result.model_copy(update={"program_name": selected_name})
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
