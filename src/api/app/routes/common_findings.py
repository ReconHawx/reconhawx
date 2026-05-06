from fastapi import APIRouter, Depends, HTTPException, Query
from models.postgres import (
    FindingsStatsResponse,
    AggregatedFindingsStatsResponse,
    FindingsTrendsResponse,
)
from repository import CommonFindingsRepository, ProgramRepository
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs
from models.user_postgres import UserResponse
import logging
from typing import Optional, List
from datetime import date

logger = logging.getLogger(__name__)

router = APIRouter()

_EMPTY_TREND_PROGRAM_SCOPE = "__reconhawx__empty_trend_scope__"

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


@router.get("/common/trends", response_model=FindingsTrendsResponse)
async def get_findings_trends(
    days: int = Query(30, ge=1, le=366),
    program_name: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="Inclusive UTC calendar day (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Inclusive UTC calendar day (YYYY-MM-DD)"),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Daily created counts for Nuclei and Typosquat findings (UTC days)."""
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
            logger.warning(
                "Program '%s' not found for findings trends; returning empty buckets",
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
        result = await CommonFindingsRepository.get_findings_trends(
            program_names=program_names_list,
            start_day=sd,
            end_day=ed,
            days=days,
        )
        return result.model_copy(update={"program_name": selected_name})
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
