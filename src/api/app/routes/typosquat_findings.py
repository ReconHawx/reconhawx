from fastapi import APIRouter, HTTPException, Query, Depends, Request, File, Form, UploadFile
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel
from enum import Enum

#from models.postgres import TyposquatDomain
from models.findings import TyposquatDomain
from models.common import StatsQueryFilter
from repository.typosquat_findings_repo import TyposquatFindingsRepository
from repository.program_repo import ProgramRepository
from repository.apexdomain_assets_repo import ApexDomainAssetsRepository
from repository.action_log_repo import ActionLogRepository
from services.unified_findings_processor import unified_findings_processor
from services.typosquat_filtering_service import TyposquatFilteringService
import logging
from pydantic import Field
from sqlalchemy import and_
from auth.dependencies import filter_by_user_programs, require_admin_or_manager, get_current_user_from_middleware, get_user_accessible_programs, require_internal_service_or_authentication
from models.user_postgres import UserResponse
from utils.domain_utils import extract_apex_domain
from models.job import (
    BatchPhishlabsRequest,
    AIAnalysisBatchRequest,
)
from repository.job_repo import JobRepository
from services.job_submission import JobSubmissionService
from datetime import datetime, timezone
import aiohttp
import uuid
import io

logger = logging.getLogger(__name__)
router = APIRouter()

def validate_status_transition(old_status: str, new_status: str, assigned_to: Optional[str], comment: Optional[str], bypass_workflow: bool = False) -> tuple[bool, Optional[str]]:
    """
    Validate status transitions based on workflow rules.
    Returns (is_valid, error_message)

    Args:
        old_status: Current status
        new_status: Desired new status
        assigned_to: User assigned to the finding
        comment: Comment for the status change
        bypass_workflow: If True, skip workflow validation (for sync jobs)
    """
    # Skip validation if workflow bypass is enabled
    if bypass_workflow:
        logger.info(f"Workflow validation bypassed: {old_status} -> {new_status}")
        return True, None

    # Rule 1: From 'new' status, only 'inprogress' is allowed
    if old_status == 'new' and new_status not in ['new', 'inprogress']:
        return False, f"From 'new' status, you can only transition to 'inprogress'. Cannot change to '{new_status}'"

    # Rule 2: 'inprogress' status requires an assigned user
    if new_status == 'inprogress' and not assigned_to:
        return False, "'In Progress' status requires an assigned user"

    # Rule 3: Transitions from 'inprogress' to 'dismissed' or 'resolved' require a comment
    if old_status == 'inprogress' and new_status in ['dismissed', 'resolved'] and not comment:
        return False, f"Transition from 'In Progress' to '{new_status}' requires a comment"

    return True, None

def apply_status_transition_rules(old_status: str, new_status: str, assigned_to: Optional[str]) -> Optional[str]:
    """
    Apply automatic rules for status transitions.
    Returns the modified assigned_to value if needed.
    """
    # Rule: When changing from 'inprogress' to 'new', automatically unassign
    if old_status == 'inprogress' and new_status == 'new':
        return None  # Unassign user

    return assigned_to  # No change needed

class BatchDeleteRequest(BaseModel):
    finding_ids: List[str]

class QueryFilter(BaseModel):
    filter: Dict[str, Any]
    limit: Optional[int] = None
    skip: Optional[int] = 0
    sort: Optional[Dict[str, int]] = None

@router.post("/typosquat/distinct/{field_name}", response_model=List[str])
async def get_typosquat_domain_distinct_typed(
    field_name: str,
    request: Optional[Dict[str, Any]] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    try:
        requested_programs: Optional[List[str]] = None
        if request:
            program_field = request.get("program")
            if isinstance(program_field, str) and program_field.strip():
                requested_programs = [program_field.strip()]
            elif isinstance(program_field, list):
                requested_programs = [p for p in program_field if isinstance(p, str) and p.strip()]

            if not requested_programs:
                legacy_filter = request.get("filter") or {}
                pn = legacy_filter.get("program_name")
                if isinstance(pn, str) and pn.strip():
                    requested_programs = [pn.strip()]
                elif isinstance(pn, list):
                    requested_programs = [p for p in pn if isinstance(p, str) and p.strip()]

        accessible = get_user_accessible_programs(current_user)
        programs: Optional[List[str]] = None
        if current_user.is_superuser or 'admin' in current_user.roles:
            programs = requested_programs if requested_programs else None
        else:
            allowed = accessible or []
            if not allowed:
                return []
            if requested_programs:
                programs = [p for p in requested_programs if p in allowed]
                if not programs:
                    return []
            else:
                programs = allowed

        values = await TyposquatFindingsRepository.get_distinct_typosquat_values_typed(field_name, programs)
        return values
    except ValueError as ve:
        logger.error(f"Value error getting typosquat distinct '{field_name}': {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting typosquat distinct '{field_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving distinct typosquat values for '{field_name}'")

@router.post("/typosquat-url/distinct/{field_name}", response_model=List[str])
async def get_typosquat_url_distinct_typed(
    field_name: str,
    request: Optional[Dict[str, Any]] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    try:
        requested_programs: Optional[List[str]] = None
        if request:
            program_field = request.get("program")
            if isinstance(program_field, str) and program_field.strip():
                requested_programs = [program_field.strip()]
            elif isinstance(program_field, list):
                requested_programs = [p for p in program_field if isinstance(p, str) and p.strip()]

            if not requested_programs:
                legacy_filter = request.get("filter") or {}
                pn = legacy_filter.get("program_name")
                if isinstance(pn, str) and pn.strip():
                    requested_programs = [pn.strip()]
                elif isinstance(pn, list):
                    requested_programs = [p for p in pn if isinstance(p, str) and p.strip()]

        accessible = get_user_accessible_programs(current_user)
        programs: Optional[List[str]] = None
        if current_user.is_superuser or 'admin' in current_user.roles:
            programs = requested_programs if requested_programs else None
        else:
            allowed = accessible or []
            if not allowed:
                return []
            if requested_programs:
                programs = [p for p in requested_programs if p in allowed]
                if not programs:
                    return []
            else:
                programs = allowed

        values = await TyposquatFindingsRepository.get_distinct_typosquat_url_values_typed(field_name, programs)
        return values
    except ValueError as ve:
        logger.error(f"Value error getting typosquat url distinct '{field_name}': {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting typosquat url distinct '{field_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving distinct typosquat url values for '{field_name}'")


# Typed typosquat search request
class TyposquatSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Fuzzy search on typo_domain")
    exact_match: Optional[str] = Field(None, description="Exact match on typo_domain")
    status: Optional[List[str]] = Field(None, description="Finding statuses (multi-select array)")
    registrar_contains: Optional[str] = Field(None, description="Substring match on registrar")
    country: Optional[str] = Field(None, description="GeoIP country code")
    min_risk_score: Optional[int] = Field(None)
    max_risk_score: Optional[int] = Field(None)
    ip_contains: Optional[str] = Field(None, description="Substring to match within dns_a_records")
    has_ip: Optional[bool] = Field(None)
    is_wildcard: Optional[bool] = Field(None)
    is_parked: Optional[bool] = Field(None, description="Filter by parked domain status")
    auto_resolve: Optional[bool] = Field(None, description="Filter by auto-resolve flag")
    http_status: Optional[int] = Field(None)
    has_phishlabs: Optional[bool] = Field(None)
    has_whois_registrar: Optional[bool] = Field(None, description="Filter domains that have a whois_registrar")
    phishlabs_incident_status: Optional[List[str]] = Field(None, description="PhishLabs incident status filter (multi-select: no_incident, monitoring, other)")
    # Threatstream filters
    has_threatstream: Optional[bool] = Field(None, description="Filter domains that have threatstream data")
    threatstream_id: Optional[str] = Field(None, description="Filter by specific threatstream ID")
    min_threatstream_score: Optional[int] = Field(None, description="Minimum threatstream threat score")
    max_threatstream_score: Optional[int] = Field(None, description="Maximum threatstream threat score")
    # Protected domain similarity filters
    similarity_protected_domain: Optional[str] = Field(None, description="Filter by similarity to a specific protected domain")
    min_similarity_percent: Optional[float] = Field(None, ge=0, le=100, description="Minimum similarity percentage with the protected domain")
    source: Optional[str] = Field(None, description="Filter by source of the finding")
    assigned_to_username: Optional[str] = Field(None, description="Filter by assigned user username")
    apex_domain: Optional[str] = Field(None, description="Filter by apex domain name")
    apex_only: Optional[bool] = Field(None, description="Show only apex domains (hide subdomains)")
    program: Optional[Union[List[str], str]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Optional[str] = Field("updated_at")
    sort_dir: Optional[str] = Field("desc")
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

class TyposquatProcessingResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    processing_mode: str  # Always "unified_async"
    summary: Dict[str, Any]

async def _extract_typosquat_domain_data(data: Dict[str, Any]) -> Dict[str, List]:
    """Extract and prepare typosquat domain findings data from the request"""
    typosquat_domain_data = {"typosquat_domain": []}
    
    if "findings" in data:
        findings = data["findings"]
        
        # Process typosquat domain findings
        if "typosquat_domain" in findings:
            logger.info("Processing typosquat domain findings")
            for finding in findings["typosquat_domain"]:
                if isinstance(finding, dict):
                    # Add program name to finding if available
                    if "program_name" in data:
                        finding["program_name"] = data["program_name"]
                    try:
                        # Map template_name to name if name is not present
                        if "template_name" in finding and "name" not in finding:
                            finding["name"] = finding["template_name"]
                        typosquat_domain_data["typosquat_domain"].append(finding)
                    except Exception as e:
                        logger.error(f"Error processing typosquat domain finding: {str(e)}")
                        logger.error(f"Finding data: {finding}")
                        continue
    
    return typosquat_domain_data

@router.post("/typosquat", response_model=TyposquatProcessingResponse)
async def create_typosquat_finding(
    request: Request,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create typosquat findings using unified processing.

    Supports both single finding and batch processing with consistent event publishing.
    """
    try:
        # Get raw request body to handle both single objects and arrays
        data = await request.json()
        logger.info(f"Received typosquat data with keys: {list(data.keys())}")
        # Validate program_name
        program_name = data.get("program_name")
        if not program_name:
            raise HTTPException(status_code=400, detail="program_name is required")
        
        # Extract and prepare typosquat domain data
        typosquat_domain_data = await _extract_typosquat_domain_data(data)
        total_typosquat_domain = len(typosquat_domain_data["typosquat_domain"])
        logger.info(f"Extracted {total_typosquat_domain} typosquat domain findings")
        
        if total_typosquat_domain == 0:
            raise HTTPException(status_code=400, detail="No typosquat domain findings provided for processing")

        # Use unified processor - always async, never blocks API
        job_id = await unified_findings_processor.process_findings_unified(typosquat_domain_data, program_name)


        return TyposquatProcessingResponse(
            status="processing",
            message=f"Started unified processing of {total_typosquat_domain} typosquat domain findings",
            job_id=job_id,
            processing_mode="unified_async",
            summary={
                "total_findings": total_typosquat_domain,
                "finding_types": {"typosquat_domain": total_typosquat_domain},
                "processing_method": "unified_async"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_typosquat_finding: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process typosquat finding(s): {str(e)}")


class CheckFilterRequest(BaseModel):
    program_name: str = Field(..., description="Program name to check filtering against")
    domains: List[str] = Field(..., description="List of domain names to check", min_length=1)


@router.post("/typosquat/check-filter", response_model=Dict[str, Any])
async def check_typosquat_filter(
    request: CheckFilterRequest,
    current_user: UserResponse = Depends(require_internal_service_or_authentication)
):
    """Pre-flight check: determine which domains would pass the typosquat filtering gate.

    Pure read-only computation -- no database writes.  Returns per-domain
    pass/fail with reasons plus convenience ``allowed`` / ``filtered`` lists.
    """
    try:
        program = await ProgramRepository.get_program_by_name(request.program_name)
        if not program:
            raise HTTPException(status_code=404, detail=f"Program '{request.program_name}' not found")

        protected_domains = program.get("protected_domains") or []
        protected_prefixes = program.get("protected_subdomain_prefixes") or []
        filtering_settings = program.get("typosquat_filtering_settings") or {}
        asset_apex_domains = await ApexDomainAssetsRepository.get_apex_domain_names_for_program(
            request.program_name
        )

        results: Dict[str, Any] = {}
        allowed: List[str] = []
        filtered: List[str] = []

        for domain in request.domains:
            passes, reason = TyposquatFilteringService.should_insert_domain(
                domain, protected_domains, protected_prefixes, filtering_settings,
                asset_apex_domains=asset_apex_domains,
            )
            results[domain] = {"allowed": passes, "reason": reason}
            if passes:
                allowed.append(domain)
            else:
                filtered.append(domain)

        return {
            "filtering_enabled": filtering_settings.get("enabled", False),
            "results": results,
            "allowed": allowed,
            "filtered": filtered,
            "summary": {
                "total": len(request.domains),
                "allowed": len(allowed),
                "filtered": len(filtered),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in check_typosquat_filter: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to check domain filtering: {str(e)}")


class SimilarityRecalculationResponse(BaseModel):
    status: str
    message: str
    total: Optional[int] = None
    updated: Optional[int] = None
    failed: Optional[int] = None
    error: Optional[str] = None


class ApplyFilterRetroactivelyResponse(BaseModel):
    status: str
    message: str
    deleted: int = 0
    rf_resolved: int = 0
    skipped: int = 0
    errors: List[str] = []
    dry_run: bool = False


@router.post("/typosquat/apply-filter-retroactively/{program_name}", response_model=ApplyFilterRetroactivelyResponse)
async def apply_filter_retroactively(
    program_name: str,
    dry_run: bool = Query(False, description="Preview without deleting"),
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """
    Apply typosquat filtering rules retroactively to existing domains.
    Deletes domains that fail the filter. For RecordedFuture-sourced domains
    with non-resolved status, resolves the RF alert before deletion.
    Use dry_run=true to preview what would be deleted without making changes.
    """
    try:
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and "admin" not in current_user.roles:
            if accessible and program_name not in accessible:
                raise HTTPException(status_code=403, detail=f"Access denied to program '{program_name}'")

        result = await TyposquatFindingsRepository.apply_filter_retroactively(
            program_name=program_name,
            dry_run=dry_run,
        )

        if result.get("status") == "error":
            raise HTTPException(status_code=404, detail=result.get("message", "Unknown error"))

        return ApplyFilterRetroactivelyResponse(
            status=result.get("status", "success"),
            message=result.get("message", ""),
            deleted=result.get("deleted", 0),
            rf_resolved=result.get("rf_resolved", 0),
            skipped=result.get("skipped", 0),
            errors=result.get("errors", []),
            dry_run=result.get("dry_run", False),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying filter retroactively for {program_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/typosquat/recalculate-similarities/{program_name}", response_model=SimilarityRecalculationResponse)
async def recalculate_protected_similarities(
    program_name: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Recalculate protected domain similarities for all typosquat domains in a program.
    
    This endpoint is useful when:
    - Protected domains have been updated and you want to recalculate immediately
    - You want to manually trigger recalculation for existing domains
    
    The calculation runs asynchronously in batches to avoid blocking.
    """
    try:
        # Check if user has access to this program
        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and 'admin' not in current_user.roles:
            if accessible and program_name not in accessible:
                raise HTTPException(status_code=403, detail=f"Access denied to program '{program_name}'")
        
        # Trigger recalculation
        result = await TyposquatFindingsRepository.recalculate_protected_domain_similarities(program_name)
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return SimilarityRecalculationResponse(
            status=result.get("status", "success"),
            message=f"Recalculated similarities for {result.get('updated', 0)} domains",
            total=result.get("total"),
            updated=result.get("updated"),
            failed=result.get("failed"),
            error=result.get("error")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recalculating similarities for {program_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to recalculate similarities: {str(e)}")


@router.post("/typosquat/{finding_id}/recalculate-similarities", response_model=SimilarityRecalculationResponse)
async def recalculate_protected_similarities_for_finding(
    finding_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Recalculate protected domain similarities for a single typosquat finding.
    Uses the finding's program protected_domains list.
    """
    try:
        finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        if not finding:
            raise HTTPException(status_code=404, detail="Finding not found")

        program_name = finding.get("program_name")
        if not program_name:
            raise HTTPException(status_code=400, detail="Finding has no program")

        accessible = get_user_accessible_programs(current_user)
        if not current_user.is_superuser and "admin" not in current_user.roles:
            if accessible and program_name not in accessible:
                raise HTTPException(status_code=403, detail=f"Access denied to program '{program_name}'")

        result = await TyposquatFindingsRepository.recalculate_protected_domain_similarities_for_finding(
            finding_id
        )

        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("error") or result.get("message") or "Unknown error",
            )

        return SimilarityRecalculationResponse(
            status=result.get("status", "success"),
            message=result.get("message")
            or f"Recalculated similarities ({result.get('updated', 0)} updated)",
            total=result.get("total"),
            updated=result.get("updated"),
            failed=result.get("failed"),
            error=result.get("error"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recalculating similarities for finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to recalculate similarities: {str(e)}")


@router.post("/typosquat/search", response_model=Dict[str, Any])
async def search_typosquat_typed(request: TyposquatSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    try:
        # Resolve programs within user access
        accessible = get_user_accessible_programs(current_user)
        requested_programs: Optional[List[str]] = None
        if isinstance(request.program, str) and request.program.strip():
            requested_programs = [request.program.strip()]
        elif isinstance(request.program, list):
            requested_programs = [p for p in request.program if isinstance(p, str) and p.strip()]

        programs: Optional[List[str]] = None
        if current_user.is_superuser or "admin" in current_user.roles:
            programs = requested_programs if requested_programs else None
        else:
            allowed = accessible or []
            if not allowed:
                return {
                    "status": "success",
                    "pagination": {
                        "total_items": 0,
                        "total_pages": 1,
                        "current_page": request.page,
                        "page_size": request.page_size,
                        "has_next": False,
                        "has_previous": False,
                    },
                    "items": [],
                }
            if requested_programs:
                programs = [p for p in requested_programs if p in allowed]
                if not programs:
                    return {
                        "status": "success",
                        "pagination": {
                            "total_items": 0,
                            "total_pages": 1,
                            "current_page": request.page,
                            "page_size": request.page_size,
                            "has_next": False,
                            "has_previous": False,
                        },
                        "items": [],
                    }
            else:
                programs = allowed

        skip = (request.page - 1) * request.page_size

        result = await TyposquatFindingsRepository.search_typosquat_typed(
            search_typed=request.search,
            exact_match_typed=request.exact_match,
            status=request.status,
            registrar_contains=request.registrar_contains,
            country=request.country,
            min_risk_score=request.min_risk_score,
            max_risk_score=request.max_risk_score,
            ip_contains=request.ip_contains,
            has_ip=request.has_ip,
            is_wildcard=request.is_wildcard,
            is_parked=request.is_parked,
            auto_resolve=request.auto_resolve,
            http_status=request.http_status,
            has_phishlabs=request.has_phishlabs,
            has_whois_registrar=request.has_whois_registrar,
            phishlabs_incident_status=request.phishlabs_incident_status,
            has_threatstream=request.has_threatstream,
            threatstream_id=request.threatstream_id,
            min_threatstream_score=request.min_threatstream_score,
            max_threatstream_score=request.max_threatstream_score,
            similarity_protected_domain=request.similarity_protected_domain,
            min_similarity_percent=request.min_similarity_percent,
            source=request.source,
            assigned_to_username=request.assigned_to_username,
            apex_domain=request.apex_domain,
            apex_only=request.apex_only,
            programs=programs,
            sort_by=request.sort_by or "updated_at",
            sort_dir=request.sort_dir or "desc",
            limit=request.page_size,
            skip=skip,
        )

        total_count = result.get("total_count", 0)
        total_pages = (total_count + request.page_size - 1) // request.page_size if request.page_size > 0 else 1
        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": request.page,
                "page_size": request.page_size,
                "has_next": request.page < total_pages,
                "has_previous": request.page > 1,
            },
            "items": result.get("items", []),
        }
    except Exception as e:
        logger.error(f"Error executing typed typosquat search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed typosquat search: {str(e)}")

@router.post("/typosquat/create-or-update", response_model=TyposquatDomain)
async def create_or_update_typosquat_finding(
    typosquat: TyposquatDomain
):
    """Create a new typosquat finding or update if exists with merged data"""
    try:
        logger.info(f"Creating or updating typosquat finding: {typosquat.typo_domain}")
        
        # Convert Pydantic model to dictionary for repository
        typosquat_dict = typosquat.model_dump()
        
        result = await TyposquatFindingsRepository.create_or_update_typosquat_finding(typosquat_dict)
        if isinstance(result, tuple):
            inserted_id, _action, _event = (result[0], result[1], result[2] if len(result) > 2 else None)
        else:
            inserted_id = result

        if not inserted_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create/update typosquat finding - no ID returned"
            )
            
        # Calculate risk score after creation/update to ensure all data is available
        try:
            logger.info(f"Calculating risk score for typosquat finding: {typosquat.typo_domain}")
            risk_calc_result = await TyposquatFindingsRepository.calculate_single_typosquat_risk_score(str(inserted_id))
            if risk_calc_result['status'] == 'success':
                logger.info(f"Risk score calculated for {typosquat.typo_domain}: {risk_calc_result['risk_score']}")
            else:
                logger.warning(f"Failed to calculate risk score for {typosquat.typo_domain}: {risk_calc_result.get('message')}")
        except Exception as risk_error:
            logger.error(f"Error calculating risk score for {typosquat.typo_domain}: {str(risk_error)}")
            # Don't fail the creation if risk calculation fails
            pass
            
        # Fetch and return the created/updated finding
        created_typosquat = await TyposquatFindingsRepository.get_typosquat_by_id(inserted_id)
        if not created_typosquat:
            raise HTTPException(
                status_code=404,
                detail=f"Typosquat finding not found after create/update with ID {inserted_id}"
            )
            
        logger.info(f"Successfully created/updated typosquat finding with ID: {inserted_id}")
        return TyposquatDomain(**created_typosquat)
        
    except Exception as e:
        logger.error(f"Error in create_or_update_typosquat_finding: {str(e)}")
        logger.error(f"Typosquat data: {typosquat.model_dump()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create/update typosquat finding: {str(e)}"
        )

# Pydantic models for typosquat findings import functionality
class TyposquatFindingImportData(BaseModel):
    typo_domain: str = Field(..., description="Typosquat domain name")
    fuzzers: Optional[List[str]] = Field(None, description="Fuzzer types used")
    risk_analysis_total_score: Optional[int] = Field(None, description="Risk analysis total score")
    program_name: str = Field(..., description="Program name")
    timestamp: Optional[str] = Field(None, description="Detection timestamp")
    notes: Optional[str] = Field(None, description="Investigation notes")
    # Domain information
    domain_registered: Optional[bool] = Field(None, description="Whether domain is registered")
    dns_a_records: Optional[List[str]] = Field(None, description="DNS A records")
    dns_mx_records: Optional[List[str]] = Field(None, description="DNS MX records")
    is_wildcard: Optional[bool] = Field(None, description="Whether domain is wildcard")
    wildcard_types: Optional[List[str]] = Field(None, description="Wildcard DNS record types")
    # WHOIS information
    whois_registrar: Optional[str] = Field(None, description="WHOIS registrar")
    whois_creation_date: Optional[str] = Field(None, description="WHOIS creation date")
    whois_expiration_date: Optional[str] = Field(None, description="WHOIS expiration date")
    whois_registrant_name: Optional[str] = Field(None, description="WHOIS registrant name")
    whois_registrant_country: Optional[str] = Field(None, description="WHOIS registrant country")
    whois_admin_email: Optional[str] = Field(None, description="WHOIS admin email")
    # GeoIP information
    geoip_country: Optional[str] = Field(None, description="GeoIP country code")
    geoip_city: Optional[str] = Field(None, description="GeoIP city")
    geoip_organization: Optional[str] = Field(None, description="GeoIP organization")
    # Risk analysis
    risk_analysis_risk_level: Optional[str] = Field(None, description="Risk analysis risk level")
    risk_analysis_version: Optional[str] = Field(None, description="Risk analysis version")
    risk_analysis_timestamp: Optional[str] = Field(None, description="Risk analysis timestamp")
    risk_analysis_category_scores: Optional[Dict[str, Any]] = Field(None, description="Risk analysis category scores")
    risk_analysis_risk_factors: Optional[Dict[str, Any]] = Field(None, description="Risk analysis risk factors")
    # PhishLabs information (consolidated into JSONB)
    phishlabs_data: Optional[Dict[str, Any]] = Field(None, description="PhishLabs data containing incident details")

class TyposquatFindingImportRequest(BaseModel):
    findings: List[TyposquatFindingImportData] = Field(..., description="List of typosquat findings to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing findings")
    validate_findings: Optional[bool] = Field(True, description="Whether to validate finding data")

@router.post("/typosquat/import", response_model=Dict[str, Any])
async def import_typosquat_findings(
    request: TyposquatFindingImportRequest, 
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Import multiple typosquat findings from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of typosquat finding objects and imports them into the database.
    It supports:
    - Validation of finding data
    - Merging with existing finding data
    - Batch processing for efficiency
    - Program-based filtering based on user permissions
    """
    try:
        # Filter findings by user program permissions
        allowed_findings = []
        for finding_data in request.findings:
            # If user has program restrictions, check if they can access this program
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if finding_data.program_name and finding_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import finding {finding_data.typo_domain} to unauthorized program {finding_data.program_name}")
                    continue
            allowed_findings.append(finding_data)
        
        if not allowed_findings:
            raise HTTPException(
                status_code=403,
                detail="No findings to import - all findings belong to programs you don't have access to"
            )
        
        # Process findings in batches for better performance
        imported_count = 0
        errors = []
        
        for finding_data in allowed_findings:
            try:
                finding_dict = {
                    "typo_domain": finding_data.typo_domain.strip(),
                    "fuzzers": finding_data.fuzzers or [],
                    "risk_analysis_total_score": finding_data.risk_analysis_total_score,
                    "program_name": finding_data.program_name.strip(),
                    "timestamp": finding_data.timestamp,
                    "notes": finding_data.notes,
                    # Domain information
                    "domain_registered": finding_data.domain_registered,
                    "dns_a_records": finding_data.dns_a_records or [],
                    "dns_mx_records": finding_data.dns_mx_records or [],
                    "is_wildcard": finding_data.is_wildcard,
                    "wildcard_types": finding_data.wildcard_types or [],
                    # WHOIS information
                    "whois_registrar": finding_data.whois_registrar,
                    "whois_creation_date": finding_data.whois_creation_date,
                    "whois_expiration_date": finding_data.whois_expiration_date,
                    "whois_registrant_name": finding_data.whois_registrant_name,
                    "whois_registrant_country": finding_data.whois_registrant_country,
                    "whois_admin_email": finding_data.whois_admin_email,
                    # GeoIP information
                    "geoip_country": finding_data.geoip_country,
                    "geoip_city": finding_data.geoip_city,
                    "geoip_organization": finding_data.geoip_organization,
                    # Risk analysis
                    "risk_analysis_total_score": finding_data.risk_analysis_total_score,
                    "risk_analysis_risk_level": finding_data.risk_analysis_risk_level,
                    "risk_analysis_version": finding_data.risk_analysis_version,
                    "risk_analysis_timestamp": finding_data.risk_analysis_timestamp,
                    "risk_analysis_category_scores": finding_data.risk_analysis_category_scores,
                    "risk_analysis_risk_factors": finding_data.risk_analysis_risk_factors,
                    # PhishLabs information (consolidated into JSONB)
                    "phishlabs_data": finding_data.phishlabs_data if finding_data.phishlabs_data and finding_data.phishlabs_data != "null" else None
                }
                
                # Remove None values, empty strings, and string "null" values, but keep empty lists and valid lists
                finding_dict = {k: v for k, v in finding_dict.items() if v is not None and v != "" and v != "null"}
                
                # Use create_or_update_typosquat_finding which handles merging automatically
                _cu = await TyposquatFindingsRepository.create_or_update_typosquat_finding(finding_dict)
                if isinstance(_cu, tuple):
                    finding_id, import_action, _import_event = (
                        _cu[0],
                        _cu[1],
                        _cu[2] if len(_cu) > 2 else None,
                    )
                else:
                    finding_id, import_action = _cu, None

                if finding_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated finding: {finding_dict['typo_domain']}")
                    
                    # Calculate risk score after import
                    try:
                        risk_result = await TyposquatFindingsRepository.calculate_single_typosquat_risk_score(str(finding_id))
                        if risk_result.get('status') == 'success':
                            logger.debug(f"Risk score calculated for {finding_dict['typo_domain']}: {risk_result.get('risk_score')}")
                        else:
                            logger.warning(f"Failed to calculate risk score for {finding_dict['typo_domain']}: {risk_result.get('message')}")
                    except Exception as risk_error:
                        logger.error(f"Error calculating risk score for {finding_dict['typo_domain']}: {risk_error}")
                        # Don't fail the import if risk calculation fails
                elif import_action == "filtered":
                    logger.info(
                        "Skipping import for filtered typosquat finding %s",
                        finding_dict.get("typo_domain"),
                    )
                else:
                    errors.append(f"Failed to create/update finding: {finding_dict['typo_domain']}")
                        
            except Exception as e:
                error_msg = f"Error processing finding {finding_data.typo_domain}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create program if it doesn't exist and findings were processed
        if imported_count > 0:
            for finding_data in allowed_findings:
                if finding_data.program_name:
                    # Check if program exists, if not create it
                    program = await ProgramRepository.get_program_by_name(finding_data.program_name)
                    if not program:
                        program_data = {"name": finding_data.program_name}
                        await ProgramRepository.create_program(program_data)
                        logger.info(f"Created new program: {finding_data.program_name}")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Import completed: {imported_count} processed",
            "data": {
                "processed_count": imported_count,
                "total_processed": len(allowed_findings),
                "total_submitted": len(request.findings)
            }
        }
        
        # Add errors to response if any occurred
        if errors:
            response_data["data"]["errors"] = errors[:10]  # Limit error list
            response_data["data"]["error_count"] = len(errors)
            
        # Adjust status if there were significant errors
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no findings were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        logger.info(f"Typosquat findings import completed by user {current_user.username}: {response_data['message']}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in typosquat findings import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing typosquat findings: {str(e)}"
        )

@router.get("/typosquat", response_model=Dict[str, Any])
async def get_all_typosquat_domains(
    program_name: Optional[str] = None,
    id: Optional[str] = Query(None),
    limit: int = 1000000,
    skip: int = 0,
    exclude_status: Optional[str] = Query(None, description="Exclude findings with this status (e.g. 'dismissed')"),
    min_similarity_percent: Optional[float] = Query(None, ge=0, le=100, description="Minimum similarity percentage with protected domain"),
    similarity_protected_domain: Optional[str] = Query(None, description="Filter by similarity to a specific protected domain"),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Get all typosquat domains with optional filtering and pagination"""
    try:
        # If an id is provided, return a single finding by id
        if id:
            finding = await TyposquatFindingsRepository.get_typosquat_by_id(id)
            if not finding:
                raise HTTPException(status_code=404, detail=f"Typosquat finding {id} not found")
            finding_program = finding.get("program_name")
            if finding_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and finding_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"Typosquat finding {id} not found")
            return {"status": "success", "data": finding}

        # Create a filter based on user program permissions
        base_filter = {}
        if program_name:
            base_filter["program_name"] = program_name
        if exclude_status:
            base_filter["status"] = {"$ne": exclude_status}
        if min_similarity_percent is not None:
            base_filter["min_similarity_percent"] = min_similarity_percent
        if similarity_protected_domain:
            base_filter["similarity_protected_domain"] = similarity_protected_domain

        filtered_query = filter_by_user_programs(base_filter, current_user)
        
        # If user has no program access, return empty result
        program_name_filter = filtered_query.get("program_name")
        if isinstance(program_name_filter, dict) and program_name_filter.get("$in") == []:
            return {
                "status": "success",
                "pagination": {
                    "total_items": 0,
                    "total_pages": 0,
                    "current_page": 1,
                    "page_size": limit,
                    "has_next": False,
                    "has_previous": False
                },
                "items": []
            }
        
        # Use query-based filtering to get typosquat domains user has access to
        total_count = await TyposquatFindingsRepository.get_typosquat_query_count(filtered_query)
        typosquat_domains = await TyposquatFindingsRepository.execute_typosquat_query(
            filtered_query,
            limit=limit,
            skip=skip,
            sort={"timestamp": -1}
        )
        # Calculate pagination metadata
        page_size = limit if limit else len(typosquat_domains)
        current_page = skip // page_size + 1 if page_size > 0 else 1
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1    
        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": current_page,
                "page_size": page_size,
                "has_next": current_page < total_pages,
                "has_previous": current_page > 1
            },
            "items": typosquat_domains
        }
    except Exception as e:
        logger.error(f"Error listing typosquat domains: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Define the expected response model for typosquat stats
class TyposquatRiskStats(BaseModel):
    critical: int = 0  # risk_score >= 80
    high: int = 0      # risk_score >= 60
    medium: int = 0    # risk_score >= 40
    low: int = 0       # risk_score >= 20
    info: int = 0      # risk_score < 20

@router.get("/typosquat/stats", response_model=TyposquatRiskStats)
async def get_typosquat_stats():
    """
    Get the count of typosquat domains grouped by risk level, based on the provided filter.
    Accepts a filter object similar to the /query endpoint.
    """
    try:
        # Use empty filter for stats
        sanitized_query = {}
        
        # Use MongoDB aggregation to get counts per risk level
        stats = await TyposquatFindingsRepository.get_typosquat_stats_by_risk_level(sanitized_query)
        
        # Return the stats, ensuring all risk levels are present (defaulting to 0)
        return TyposquatRiskStats(**stats)
        
    except Exception as e:
        logger.error(f"Error calculating typosquat stats: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error calculating typosquat stats: {str(e)}"
        )

# GET endpoint for DETAILED program typosquat stats counts
@router.get("/typosquat/stats/{program_name}", response_model=TyposquatRiskStats)
async def get_program_typosquat_stats_detailed_get(program_name: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Get detailed counts of typosquat domains for a specific program.
    Provides breakdowns by risk level.
    """
    try:
        # Check if program exists first
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")
        
        # Check if user has access to this program
        accessible_programs = get_user_accessible_programs(current_user)
        # For superusers/admins, accessible_programs is empty (meaning no restrictions)
        if accessible_programs and program_name not in accessible_programs:
            raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")

        # Base filter is just the program name
        combined_filter = {"program_name": program_name}
        detailed_stats = await TyposquatFindingsRepository.get_typosquat_stats_by_risk_level(combined_filter)
        return detailed_stats

    except HTTPException: # Re-raise HTTP exceptions
        raise
    except ValueError as ve: # Catch specific ValueErrors like invalid asset type from repo
        logger.error(f"Value error calculating program typosquat stats for {program_name}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error calculating program typosquat stats for {program_name}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating program typosquat stats: {str(e)}"
        )

# New endpoint to get distinct values for a field
@router.post("/typosquat/distinct/{field_name}", response_model=List[str])
async def get_distinct_typosquat_field_values(field_name: str, query: Optional[StatsQueryFilter] = None):
    """
    Get distinct values for a specified field in typosquat domains, optionally applying a filter.
    Allowed fields: typo_domain, program_name, fuzzers, geoip_country, whois_registrar, http_status_code, risk_score, status, assigned_to, assigned_to_username, source, typosquat_apex_domain.
    """
    allowed_fields = {"typo_domain", "program_name", "fuzzers", "geoip_country", "whois_registrar", "http_status_code", "risk_score", "status", "assigned_to", "assigned_to_username", "source", "typosquat_apex_domain"}
    if field_name not in allowed_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{field_name}' is not allowed for distinct query. Allowed fields: {', '.join(allowed_fields)}"
        )

    try:
        # Extract filter from the optional query body
        filter_data = query.filter if query and query.filter else {}

        # Get distinct values using the repository method
        distinct_values = await TyposquatFindingsRepository.get_distinct_typosquat_values(field_name, filter_data)
        return distinct_values

    except ValueError as ve:
        logger.error(f"Value error getting distinct values for {field_name}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting distinct values for field '{field_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving distinct values for field '{field_name}'"
        )

# Enums for action types
class ActionTaken(str, Enum):
    TAKEDOWN_REQUESTED = "takedown_requested"
    REPORTED_GOOGLE_SAFE_BROWSING = "reported_google_safe_browsing"
    BLOCKED_FIREWALL = "blocked_firewall"
    MONITORING = "monitoring"
    OTHER = "other"

# Pydantic models for update requests
class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="New status value")
    assigned_to: Optional[str] = Field(None, description="User assigned to investigate")
    comment: Optional[str] = Field(None, description="Comment for status change")
    action_taken: Optional[ActionTaken] = Field(None, description="Action taken when status is resolved")

class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

@router.put("/typosquat/batch/status", response_model=Dict[str, Any])
async def update_typosquat_status_batch(
    request: Dict[str, Any],
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update the status for multiple typosquat findings"""
    try:
        finding_ids = request.get("finding_ids", [])
        new_status = request.get("status")
        assigned_to = request.get("assigned_to")
        comment = request.get("comment")
        action_taken = request.get("action_taken")
        force_assignment_overwrite = request.get("force_assignment_overwrite", False)

        if not finding_ids:
            raise HTTPException(status_code=400, detail="No finding IDs provided")

        # Ensure at least one field is being updated
        if not new_status and "assigned_to" not in request and not comment and not action_taken:
            raise HTTPException(status_code=400, detail="At least one field must be updated (status, assigned_to, comment, or action_taken)")

        # Validate status value if provided
        if new_status:
            valid_statuses = ['new', 'inprogress', 'resolved', 'dismissed']
            if new_status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{new_status}'. Must be one of: {', '.join(valid_statuses)}"
                )

        # Validate action_taken if provided
        if action_taken:
            valid_actions = [action.value for action in ActionTaken]
            if action_taken not in valid_actions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid action_taken '{action_taken}'. Must be one of: {', '.join(valid_actions)}"
                )

        # Prepare base update data
        base_update_data = {}
        if new_status:
            base_update_data["status"] = new_status
        if "assigned_to" in request:
            logger.debug(f"Batch processing assigned_to: {assigned_to}")
            base_update_data["assigned_to"] = assigned_to
        if comment:
            base_update_data["comment"] = comment
        if action_taken:
            base_update_data["action_taken"] = action_taken

        # Update each finding
        updated_count = 0
        failed_count = 0
        failed_ids = []

        for finding_id in finding_ids:
            try:
                # Get current status before update for logging
                current_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
                if not current_finding:
                    failed_count += 1
                    failed_ids.append(finding_id)
                    continue

                old_status = current_finding.get('status', 'unknown')
                old_assigned_to = current_finding.get('assigned_to')

                # Validate status transition only if status is being changed
                if new_status:
                    is_valid, error_message = validate_status_transition(old_status, new_status, assigned_to, comment)
                    if not is_valid:
                        logger.warning(f"Status transition validation failed for finding {finding_id}: {error_message}")
                        failed_count += 1
                        failed_ids.append(finding_id)
                        continue

                # Create individual update_data for this finding
                update_data = base_update_data.copy()

                # Apply smart assignment logic if assignment is requested
                if "assigned_to" in request:
                    if old_assigned_to is None:
                        # Finding is unassigned -> always assign to selected user
                        logger.debug(f"Finding {finding_id} is unassigned, assigning to {assigned_to}")
                        update_data["assigned_to"] = assigned_to
                    elif force_assignment_overwrite:
                        # Finding is assigned + force overwrite -> change assignment
                        logger.debug(f"Finding {finding_id} assignment being overwritten from {old_assigned_to} to {assigned_to}")
                        update_data["assigned_to"] = assigned_to
                    else:
                        # Finding is assigned + no force -> preserve existing assignment
                        logger.debug(f"Finding {finding_id} assignment preserved: {old_assigned_to}")
                        # Remove assigned_to from update_data to preserve existing assignment
                        if "assigned_to" in update_data:
                            update_data.pop("assigned_to")

                # Apply automatic rules (like auto-unassign) - may override smart assignment logic
                # Only apply if status is being changed
                if new_status:
                    final_assigned_to = apply_status_transition_rules(old_status, new_status, update_data.get("assigned_to", old_assigned_to))
                    if final_assigned_to != update_data.get("assigned_to", old_assigned_to):
                        update_data["assigned_to"] = final_assigned_to

                # Fetch user_rf_uhash for RecordedFuture integration if assignment is involved
                if "assigned_to" in update_data:
                    final_assigned_user = update_data["assigned_to"]
                    if final_assigned_user is not None:
                        from repository.auth_repo import AuthRepository
                        auth_repo = AuthRepository()
                        user_data = await auth_repo.get_user_by_id(user_id=final_assigned_user)
                        logger.debug(f"Batch user data for {finding_id}: {user_data}")
                        if user_data:
                            update_data["user_rf_uhash"] = user_data.get("rf_uhash")
                            logger.debug(f"Batch setting user_rf_uhash for {finding_id}: {user_data.get('rf_uhash')}")
                    else:
                        # Unassigning - clear the rf_uhash as well
                        update_data["user_rf_uhash"] = None
                        logger.debug(f"Batch clearing user_rf_uhash for unassignment on {finding_id}")

                # Perform the update
                success = await TyposquatFindingsRepository.update_typosquat_domain(finding_id, update_data)
                if success:
                    updated_count += 1

                    # Log the actions
                    try:
                        # Check if assignment changed
                        # Only check for assignment change if assigned_to is explicitly in update_data
                        # If it's not in update_data, it means we're preserving the existing assignment
                        assignment_changed = False
                        if "assigned_to" in update_data:
                            new_assigned_to = update_data["assigned_to"]
                            # Detect assignment change: different values or one is None and other isn't
                            if old_assigned_to != new_assigned_to:
                                assignment_changed = True
                                logger.debug(f"Batch assignment change detected: {old_assigned_to} -> {new_assigned_to}")
                        else:
                            # assigned_to not in update_data means we're preserving existing assignment
                            new_assigned_to = old_assigned_to

                        # Log status change action only if status actually changed
                        if old_status != new_status:
                            metadata = {}
                            if comment:
                                metadata['comment'] = comment
                            if action_taken:
                                metadata['action_taken'] = action_taken
                            if "assigned_to" in request:
                                metadata['assigned_to'] = assigned_to

                            await ActionLogRepository.log_action(
                                entity_type='typosquat_finding',
                                entity_id=finding_id,
                                action_type='status_change',
                                user_id=str(current_user.id),
                                old_value={'status': old_status},
                                new_value={'status': new_status},
                                metadata=metadata if metadata else None
                            )

                        # Log assignment change action if assignment changed
                        if assignment_changed:
                            # Get usernames for old and new assignments
                            from repository.auth_repo import AuthRepository
                            auth_repo = AuthRepository()

                            old_assigned_username = None
                            new_assigned_username = None

                            if old_assigned_to:
                                old_user_data = await auth_repo.get_user_by_id(user_id=old_assigned_to)
                                if old_user_data:
                                    old_assigned_username = old_user_data.get("username")

                            if new_assigned_to:
                                new_user_data = await auth_repo.get_user_by_id(user_id=new_assigned_to)
                                if new_user_data:
                                    new_assigned_username = new_user_data.get("username")

                            # Create assignment change metadata
                            assignment_metadata = {}
                            if comment:
                                assignment_metadata['comment'] = comment

                            # Log assignment change
                            await ActionLogRepository.log_action(
                                entity_type='typosquat_finding',
                                entity_id=finding_id,
                                action_type='assignment_change',
                                user_id=str(current_user.id),
                                old_value={
                                    'assigned_to': old_assigned_to,
                                    'assigned_to_username': old_assigned_username
                                },
                                new_value={
                                    'assigned_to': new_assigned_to,
                                    'assigned_to_username': new_assigned_username
                                },
                                metadata=assignment_metadata if assignment_metadata else None
                            )

                    except Exception as e:
                        logger.error(f"Error logging actions for finding {finding_id}: {str(e)}")
                        # Don't fail the update if logging fails
                else:
                    failed_count += 1
                    failed_ids.append(finding_id)
            except Exception as e:
                logger.error(f"Error updating status for finding {finding_id}: {str(e)}")
                failed_count += 1
                failed_ids.append(finding_id)

        return {
            "status": "success",
            "message": f"Updated status for {updated_count} out of {len(finding_ids)} findings",
            "updated_count": updated_count,
            "failed_count": failed_count,
            "failed_ids": failed_ids,
            "new_status": new_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch updating typosquat status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/typosquat/{finding_id}/status", response_model=Dict[str, Any])
async def update_typosquat_status(
    finding_id: str,
    request: StatusUpdateRequest,
    http_request: Request,
    current_user: UserResponse = Depends(require_internal_service_or_authentication)
):
    """Update the status and optionally the assigned user for a typosquat finding"""
    try:
        # Validate status value
        valid_statuses = ['new', 'inprogress', 'resolved', 'dismissed']
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{request.status}'. Must be one of: {', '.join(valid_statuses)}"
            )

        # Validate action_taken if provided
        if request.action_taken:
            valid_actions = [action.value for action in ActionTaken]
            if request.action_taken not in valid_actions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid action_taken '{request.action_taken}'. Must be one of: {', '.join(valid_actions)}"
                )

        # Get current finding data for logging
        current_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        if not current_finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        old_status = current_finding.get('status', 'unknown')
        old_assigned_to = current_finding.get('assigned_to')

        # Check for workflow bypass header (only allowed for internal services)
        bypass_workflow = http_request.headers.get("X-Bypass-Workflow", "false").lower() == "true"

        if bypass_workflow:
            # Verify this is an internal service request (require_internal_service_or_authentication ensures this)
            logger.info(f"Workflow bypass requested for finding {finding_id}: {old_status} -> {request.status}")

        # Validate status transition
        is_valid, error_message = validate_status_transition(old_status, request.status, request.assigned_to, request.comment, bypass_workflow)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)

        # Apply automatic rules (like auto-unassign)
        final_assigned_to = apply_status_transition_rules(old_status, request.status, request.assigned_to)

        # Prepare update data
        logger.debug(f"Request: status={request.status} assigned_to={request.assigned_to} comment={request.comment} action_taken={request.action_taken}")
        update_data = {"status": request.status}

        if hasattr(request, 'assigned_to'):
            logger.debug(f"Processing assigned_to: {request.assigned_to} -> final: {final_assigned_to}")
            update_data["assigned_to"] = final_assigned_to

            # Only fetch user data if assigning to a user (not null)
            if final_assigned_to is not None:
                from repository.auth_repo import AuthRepository
                auth_repo = AuthRepository()
                user_data = await auth_repo.get_user_by_id(user_id=final_assigned_to)
                logger.debug(f"User data: {user_data}")
                if user_data:
                    update_data["user_rf_uhash"] = user_data.get("rf_uhash")
            else:
                # Unassigning - clear the rf_uhash as well
                update_data["user_rf_uhash"] = None

        if request.comment:
            update_data["comment"] = request.comment
        if request.action_taken:
            update_data["action_taken"] = request.action_taken

        # Update the finding
        success = await TyposquatFindingsRepository.update_typosquat_domain(finding_id, update_data)

        if not success:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        # Log the actions (skip for internal service users)
        is_internal_service = str(current_user.id).startswith("internal-service-")

        # Debug logging for action logging logic
        logger.info(f"Action logging debug: user_id={current_user.id}, username={current_user.username}, is_internal_service={is_internal_service}")
        logger.info(f"Assignment values: old_assigned_to={old_assigned_to}, final_assigned_to={final_assigned_to}")

        try:
            if not is_internal_service:
                # Check if assignment changed
                assignment_changed = False
                new_assigned_to = final_assigned_to

                # Detect assignment change: different values or one is None and other isn't
                if old_assigned_to != new_assigned_to:
                    assignment_changed = True
                    logger.debug(f"Assignment change detected: {old_assigned_to} -> {new_assigned_to}")

                # Log status change action only if status actually changed
                if old_status != request.status:
                    metadata = {}
                    if request.comment:
                        metadata['comment'] = request.comment
                    if request.action_taken:
                        metadata['action_taken'] = request.action_taken
                    if hasattr(request, 'assigned_to'):
                        metadata['assigned_to'] = final_assigned_to

                    await ActionLogRepository.log_action(
                        entity_type='typosquat_finding',
                        entity_id=finding_id,
                        action_type='status_change',
                        user_id=str(current_user.id),
                        old_value={'status': old_status},
                        new_value={'status': request.status},
                        metadata=metadata if metadata else None
                    )

                # Log assignment change action if assignment changed
                if assignment_changed:
                    # Get usernames for old and new assignments
                    from repository.auth_repo import AuthRepository
                    auth_repo = AuthRepository()

                    old_assigned_username = None
                    new_assigned_username = None

                    if old_assigned_to:
                        old_user_data = await auth_repo.get_user_by_id(user_id=old_assigned_to)
                        if old_user_data:
                            old_assigned_username = old_user_data.get("username")

                    if new_assigned_to:
                        new_user_data = await auth_repo.get_user_by_id(user_id=new_assigned_to)
                        if new_user_data:
                            new_assigned_username = new_user_data.get("username")

                    # Create assignment change metadata
                    assignment_metadata = {}
                    if request.comment:
                        assignment_metadata['comment'] = request.comment

                    # Log assignment change
                    await ActionLogRepository.log_action(
                        entity_type='typosquat_finding',
                        entity_id=finding_id,
                        action_type='assignment_change',
                        user_id=str(current_user.id),
                        old_value={
                            'assigned_to': old_assigned_to,
                            'assigned_to_username': old_assigned_username
                        },
                        new_value={
                            'assigned_to': new_assigned_to,
                            'assigned_to_username': new_assigned_username
                        },
                        metadata=assignment_metadata if assignment_metadata else None
                    )
            else:
                # Skip action logging for internal service users
                logger.info(f"Skipping action logging for internal service user: {current_user.username}")

        except Exception as e:
            logger.error(f"Error logging actions for finding {finding_id}: {str(e)}")
            # Don't fail the update if logging fails

        # Return updated data
        updated_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)

        if not updated_finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found after update")

        return {
            "status": "success",
            "message": "Status updated successfully",
            "data": {
                "status": updated_finding.get("status"),
                "assigned_to": updated_finding.get("assigned_to")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating typosquat status {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class ActionTakenUpdateRequest(BaseModel):
    action_taken: ActionTaken = Field(..., description="Action taken to add to the finding")

@router.patch("/typosquat/{finding_id}/action-taken", response_model=Dict[str, Any])
async def update_typosquat_action_taken(
    finding_id: str,
    request: ActionTakenUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update the action_taken field for a typosquat finding without changing status"""
    try:
        # Validate action_taken
        valid_actions = [action.value for action in ActionTaken]
        if request.action_taken not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action_taken '{request.action_taken}'. Must be one of: {', '.join(valid_actions)}"
            )

        # Get current finding data for logging
        current_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        if not current_finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        # Prepare update data - only action_taken
        update_data = {"action_taken": request.action_taken}

        logger.info(f"Adding action_taken '{request.action_taken}' to finding {finding_id}")

        # Update the finding
        success = await TyposquatFindingsRepository.update_typosquat_domain(finding_id, update_data)

        if not success:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        logger.info(f"Successfully added action_taken '{request.action_taken}' to finding {finding_id}")

        return {
            "status": "success",
            "message": f"Action taken '{request.action_taken}' added successfully",
            "data": {
                "finding_id": finding_id,
                "action_taken": request.action_taken
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating action_taken for finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/typosquat/{finding_id}/notes", response_model=Dict[str, Any])
async def update_typosquat_notes(finding_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for a typosquat finding"""
    try:
        # Update the finding
        update_data = {"notes": request.notes}
        success = await TyposquatFindingsRepository.update_typosquat_domain(finding_id, update_data)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
        
        return {
            "status": "success",
            "message": "Notes updated successfully",
            "data": {
                "notes": request.notes
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating typosquat notes {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/typosquat/action-logs", response_model=Dict[str, Any])
async def get_all_typosquat_action_logs(
    program: Optional[str] = Query(None, description="Filter by program name"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    search: Optional[str] = Query(None, description="Search in log content"),
    limit: int = Query(100, description="Maximum number of logs to return", le=500),
    offset: int = Query(0, description="Number of logs to skip"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Get action logs for all typosquat findings.
    Supports filtering by program, action type, entity ID, and search.
    """
    try:
        # Get user accessible programs
        accessible_programs = get_user_accessible_programs(current_user)

        # Build filter conditions
        filters = {"entity_type": "typosquat_finding"}

        # Handle program filtering
        if program:
            # Check if user has access to the requested program
            if accessible_programs and program not in accessible_programs:
                return {
                    "status": "success",
                    "message": "No action logs found - no access to requested program",
                    "data": {
                        "action_logs": [],
                        "pagination": {
                            "limit": limit,
                            "offset": offset,
                            "total": 0
                        }
                    }
                }
            filters["program_name"] = program
        elif accessible_programs:
            # For non-admin users, restrict to accessible programs only
            filters["program_names"] = accessible_programs

        if action_type:
            filters["action_type"] = action_type

        if entity_id:
            filters["entity_id"] = entity_id

        # Get action logs with filters
        action_logs = await ActionLogRepository.get_action_logs_with_filters(
            filters=filters,
            search_term=search,
            limit=limit,
            offset=offset
        )

        return {
            "status": "success",
            "message": f"Found {len(action_logs)} action logs",
            "data": {
                "action_logs": action_logs,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "count": len(action_logs)
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting all typosquat action logs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting action logs: {str(e)}")

@router.get("/typosquat/ai-analysis/{finding_id}", response_model=Dict[str, Any])
async def get_ai_analysis(
    finding_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Get AI analysis results for a specific typosquat finding."""
    finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

    return {
        "status": "success",
        "finding_id": finding_id,
        "ai_analysis": finding.get("ai_analysis"),
        "ai_analyzed_at": finding.get("ai_analyzed_at"),
    }


@router.get("/typosquat/{finding_id}/ai-analysis-context", response_model=Dict[str, Any])
async def get_ai_analysis_context(
    finding_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Get full context for AI analysis (finding, URLs, screenshot texts). Used by runner jobs."""
    ctx = await TyposquatFindingsRepository.get_ai_analysis_context(finding_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
    finding_program = ctx["finding"].get("program_name")
    if finding_program:
        accessible = get_user_accessible_programs(current_user)
        if accessible and finding_program not in accessible:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
    return {"status": "success", "data": ctx}


class AIAnalysisUpdateRequest(BaseModel):
    """Request body for PATCH ai-analysis endpoint (runner use)."""
    ai_analysis: Dict[str, Any] = Field(..., description="Structured AI analysis result")
    ai_analyzed_at: Optional[str] = Field(None, description="ISO timestamp of analysis")


@router.patch("/typosquat/{finding_id}/ai-analysis", response_model=Dict[str, Any])
async def update_ai_analysis(
    finding_id: str,
    request: AIAnalysisUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Update AI analysis result for a finding. Used by runner jobs."""
    from db import get_db_session
    from models.postgres import TyposquatDomain
    from datetime import datetime, timezone

    finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
    finding_program = finding.get("program_name")
    if finding_program:
        accessible = get_user_accessible_programs(current_user)
        if accessible and finding_program not in accessible:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

    analyzed_at = request.ai_analyzed_at
    if not analyzed_at:
        analyzed_at = datetime.now(timezone.utc).isoformat()

    async with get_db_session() as db:
        domain = db.query(TyposquatDomain).filter(TyposquatDomain.id == finding_id).first()
        if domain:
            domain.ai_analysis = request.ai_analysis
            domain.ai_analyzed_at = datetime.fromisoformat(analyzed_at.replace("Z", "+00:00"))
            db.commit()

    return {
        "status": "success",
        "finding_id": finding_id,
        "ai_analysis": request.ai_analysis,
        "ai_analyzed_at": analyzed_at,
    }


@router.get("/typosquat/{finding_id}", response_model=Dict[str, Any])
async def get_typosquat_finding_by_id(finding_id: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """Get a single typosquat finding by its ID"""
    try:
        finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
        
        # Check if user has access to this finding's program
        finding_program = finding.get("program_name")
        if finding_program:
            accessible_programs = get_user_accessible_programs(current_user)
            # For superusers/admins, accessible_programs is empty (meaning no restrictions)
            if accessible_programs and finding_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
        
        return {
            "status": "success",
            "data": finding,  # Keep data field for backward compatibility
            "items": [finding]  # Keep items field for consistency with other endpoints
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting typosquat finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/typosquat/{finding_id}/related-domains", response_model=Dict[str, Any])
async def get_related_typosquat_domains(
    finding_id: str, 
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get all typosquat domains that share the same base domain as the specified finding"""
    try:
        # Get the main finding first
        finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
        
        # Check if user has access to this finding's program
        finding_program = finding.get("program_name")
        if finding_program:
            accessible_programs = get_user_accessible_programs(current_user)
            # For superusers/admins, accessible_programs is empty (meaning no restrictions)
            if accessible_programs and finding_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
        
        typo_domain = finding.get("typo_domain")
        if not typo_domain:
            raise HTTPException(status_code=400, detail="Typosquat finding does not have a domain")
        
        # Debug logging
        base_domain = extract_apex_domain(typo_domain)
        logger.info(f"API endpoint: Finding related domains for {typo_domain}, base domain: {base_domain}, program: {finding_program}")
        
        # Get related domains using the repository method
        related_domains = await TyposquatFindingsRepository.get_related_typosquat_domains(
            typo_domain, finding_program
        )
        
        logger.info(f"API endpoint: Found {len(related_domains)} related domains")
        
        # If no domains found, let's try without program filter for debugging
        if len(related_domains) == 0 and finding_program:
            logger.info("No related domains found with program filter, trying without program filter for debugging")
            all_domains_debug = await TyposquatFindingsRepository.get_related_typosquat_domains(
                typo_domain, None  # No program filter
            )
            logger.info(f"Without program filter, found {len(all_domains_debug)} related domains")
        
        return {
            "status": "success",
            "message": f"Found {len(related_domains)} related domains for {typo_domain}",
            "base_domain": extract_apex_domain(typo_domain),
            "current_domain": typo_domain,
            "debug": {
                "finding_program": finding_program,
                "base_domain": base_domain,
                "typo_domain": typo_domain
            },
            "items": related_domains
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting related domains for finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/typosquat/{finding_id}/related-urls", response_model=Dict[str, Any])
async def get_related_typosquat_urls(
    finding_id: str, 
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get all typosquat URLs for domains that share the same base domain as the specified finding"""
    try:
        # Get the main finding first
        finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
        
        # Check if user has access to this finding's program
        finding_program = finding.get("program_name")
        if finding_program:
            accessible_programs = get_user_accessible_programs(current_user)
            # For superusers/admins, accessible_programs is empty (meaning no restrictions)
            if accessible_programs and finding_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
        
        typo_domain = finding.get("typo_domain")
        if not typo_domain:
            raise HTTPException(status_code=400, detail="Typosquat finding does not have a domain")
        
        logger.info(f"API endpoint: Finding related URLs for {typo_domain}, program: {finding_program}")
        
        # Get related URLs using the repository method
        related_urls = await TyposquatFindingsRepository.get_related_typosquat_urls(
            typo_domain, finding_program
        )
        
        logger.info(f"API endpoint: Found {len(related_urls)} related URLs")
        
        # Group URLs by domain for summary
        domains_with_urls = {}
        for url in related_urls:
            domain = url.get("typo_domain", "unknown")
            if domain not in domains_with_urls:
                domains_with_urls[domain] = 0
            domains_with_urls[domain] += 1
        
        return {
            "status": "success",
            "message": f"Found {len(related_urls)} URLs across {len(domains_with_urls)} related domains for {typo_domain}",
            "current_domain": typo_domain,
            "summary": {
                "total_urls": len(related_urls),
                "domains_with_urls": len(domains_with_urls),
                "urls_per_domain": domains_with_urls
            },
            "items": related_urls
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting related URLs for finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/typosquat/{finding_id}/action-logs", response_model=Dict[str, Any])
async def get_typosquat_finding_action_logs(
    finding_id: str,
    limit: int = Query(50, description="Maximum number of logs to return"),
    offset: int = Query(0, description="Number of logs to skip"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get action logs for a specific typosquat finding"""
    try:
        # Get the finding first to check access
        finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)

        if not finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        # Check if user has access to this finding's program
        finding_program = finding.get("program_name")
        if finding_program:
            accessible_programs = get_user_accessible_programs(current_user)
            # For superusers/admins, accessible_programs is empty (meaning no restrictions)
            if accessible_programs and finding_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        # Get action logs for this finding
        action_logs = await ActionLogRepository.get_action_logs_for_entity(
            entity_type="typosquat_finding",
            entity_id=finding_id,
            limit=limit,
            offset=offset
        )

        return {
            "status": "success",
            "message": f"Found {len(action_logs)} action logs for finding {finding_id}",
            "items": action_logs
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting action logs for finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Typosquat findings batch delete route
@router.delete("/typosquat/batch", response_model=Dict[str, Any])
async def delete_typosquat_findings_batch(
    request: BatchDeleteRequest,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple typosquat findings by their IDs"""
    try:
        logger.info("=== TYPOSQUAT FINDINGS BATCH DELETE ENDPOINT CALLED ===")
        logger.info("Endpoint: /typosquat/batch")
        logger.info(f"Received batch delete request: {request}")

        # Extract finding_ids from request body
        finding_ids = request.finding_ids

        logger.info(f"Extracted finding_ids: {finding_ids}")
        logger.info(f"Finding IDs type: {type(finding_ids)}")

        if not finding_ids:
            raise HTTPException(status_code=400, detail="No finding IDs provided")

        logger.info(f"Batch deleting {len(finding_ids)} typosquat findings: {finding_ids}")

        result = await TyposquatFindingsRepository.delete_typosquat_findings_batch(finding_ids)

        logger.info(f"Batch delete result: {result}")
        logger.info("=== TYPOSQUAT FINDINGS BATCH DELETE COMPLETED ===")

        return {
            "status": "success",
            "message": "Batch delete completed for typosquat findings",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting typosquat findings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/typosquat/{finding_id}", response_model=Dict[str, Any])
async def delete_typosquat_finding(
    finding_id: str, 
    delete_related: bool = Query(False, description="Delete all findings with the same base domain"),
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a typosquat finding by its ID, optionally including related findings with the same base domain"""
    try:
        if delete_related:
            # Get the finding first to extract its typo_domain and program
            finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
            if not finding:
                raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
            
            typo_domain = finding.get("typo_domain")
            program_name = finding.get("program_name")
            
            if not typo_domain:
                raise HTTPException(status_code=400, detail="Cannot find related domains: typo_domain is missing")
            
            # Find all related domain IDs
            related_ids = await TyposquatFindingsRepository.find_related_typosquat_domains(
                typo_domain, program_name
            )
            
            if not related_ids:
                raise HTTPException(status_code=404, detail="No related typosquat findings found")
            
            logger.info(f"Deleting {len(related_ids)} related typosquat findings for base domain of {typo_domain}")
            logger.info(f"Related IDs to delete: {related_ids}")
            
            # Use batch delete for related domains
            result = await TyposquatFindingsRepository.delete_typosquat_findings_batch(related_ids)
            
            logger.info(f"Batch delete result: {result}")
            
            return {
                "status": "success",
                "message": f"Deleted {result.get('deleted_count', 0)} typosquat findings related to {typo_domain}",
                "deleted_count": result.get("deleted_count", 0),
                "related_domains": related_ids,
                "base_domain": extract_apex_domain(typo_domain)
            }
        else:
            # Standard single deletion
            deleted = await TyposquatFindingsRepository.delete_typosquat_domain(finding_id)
            
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")
            
            return {
                "status": "success",
                "message": f"Typosquat finding {finding_id} deleted successfully"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting typosquat finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== PHISHLABS INTEGRATION ENDPOINTS =====

async def _call_phishlabs_apis(
    session: aiohttp.ClientSession,
    url: str,
    api_key: str,
    catcode: str = "12345",
    action: str = "check"
) -> Dict[str, Any]:
    """Helper function to call PhishLabs APIs for a single domain.

    Args:
        session: aiohttp ClientSession
        url: Domain name (typo_domain) to check/create incident for - this will be used as the URL parameter
        api_key: PhishLabs API key
        catcode: PhishLabs category code (default: "12345" for checking)
        action: "check" to check existing incident, "create" to create new incident

    Returns:
        Dictionary with API responses and incident information
    """
    # Infer flags from action
    if action == "create":
        flags = 0  # Create incident
        # Use provided catcode or default to 12345
        final_catcode = catcode if catcode else "12345"
        if final_catcode == "12345":
            raise HTTPException(
                status_code=400,
                detail="Valid catcode required for creating incidents (cannot use default 12345)"
            )
        comment = "Typosquat domain that impersonate our Brand. Please monitor."
    else:
        flags = 2  # Check/fetch existing incident
        final_catcode = "12345"  # Default catcode for checking
    # Validate based on action

    # Ensure url is a string (handle Pydantic URL objects)
    if hasattr(url, '__class__') and 'Url' in str(type(url)):
        # Convert Pydantic URL object to string
        url = str(url)
    elif not isinstance(url, str):
        # Convert any other object to string
        url = str(url)

    logger.debug(f"Using url for PhishLabs API: {url} (type: {type(url)})")

    #Prepare PhishLabs URLs
    createincident_url = (
        "https://feed.phishlabs.com/createincident"
        f"?custid={api_key}"
        "&requestid=placeholder"
        f"&url={url}"
        f"&catcode={final_catcode}"
        f"&flags={flags}"
    )
    if action == "create":
        createincident_url += f"&comment={comment}"
    incident_id: int | None = None
    createincident_response: Dict[str, Any] | None = None
    incident_response: Dict[str, Any] | None = None
    
    # First call – createincident
    async with session.get(createincident_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            body_text = await resp.text()
            raise HTTPException(
                status_code=502,
                detail=f"PhishLabs createincident error {resp.status}: {body_text[:1000]}"
            )
        createincident_response = await resp.json(content_type=None)

    if createincident_response is None:
        raise HTTPException(status_code=502, detail="Empty response from PhishLabs createincident call")

    incident_id = createincident_response.get("IncidentId")
    error_message = createincident_response.get("ErrorMessage")
    logger.debug(f"Phishlabs Incident ID: {incident_id}")
    if error_message:
        # PhishLabs returned an error
        raise HTTPException(status_code=400, detail=f"PhishLabs error: {error_message}")

    # Handle case where no incident exists for this domain
    if not incident_id:
        return {
            "createincident_response": createincident_response,
            "incident_response": None,
            "incident_id": None,
            "no_incident": True
        }

    # Second call – incident.get
    incident_get_url = (
        "https://feed.phishlabs.com/incident.get"
        f"?custid={api_key}"
        f"&incidentid={incident_id}"
    )
    async with session.get(incident_get_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            body_text = await resp.text()
            raise HTTPException(
                status_code=502,
                detail=f"PhishLabs incident.get error {resp.status}: {body_text[:1000]}"
            )
        incident_response = await resp.json(content_type=None)
    logger.debug(f"Phishlabs Incident Response: {incident_response}")
    result = {
        "createincident_response": createincident_response,
        "incident_response": incident_response,
        "incident_id": str(incident_id) if incident_id is not None else None,
        "no_incident": False,
        "action": action,
        "catcode": catcode,
        "flags": flags
    }
    return result

@router.post("/typosquat/phishlabs/batch", response_model=Dict[str, Any])
async def create_phishlabs_batch_job(
    request: BatchPhishlabsRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a background job to fetch PhishLabs data for multiple typosquat findings.
    
    This endpoint creates a Kueue job that will process the findings in the background.
    Users can check job status using the /jobs/{job_id}/status endpoint.
    """
    if not request.finding_ids:
        raise HTTPException(status_code=400, detail="No finding IDs provided")

    try:
        logger.info(f"Creating batch PhishLabs job for {len(request.finding_ids)} findings")
        
        # Validate that all finding IDs exist
        findings = []
        for finding_id in request.finding_ids:
            finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
            if not finding:
                logger.warning(f"Typosquat finding {finding_id} not found, skipping")
                continue
            findings.append(finding)
        
        if not findings:
            raise HTTPException(status_code=404, detail="No valid typosquat findings found")
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create job payload
        job_payload = {
            "job_id": job_id,
            "job_type": "phishlabs_batch",
            "finding_ids": request.finding_ids,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Create job status record
        job_created = await JobRepository.create_job(job_id, "phishlabs_batch", job_payload)
        
        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")
        
        # Submit job to Kubernetes
        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_phishlabs_batch_job(job_id, job_payload)
            logger.info(f"Submitted PhishLabs batch job {job_id} to Kubernetes")
        except Exception as e:
            logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
            # Update job status to failed
            await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit to Kubernetes: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to submit job to Kubernetes: {str(e)}")
        
        logger.info(f"Created PhishLabs batch job {job_id} for {len(findings)} findings")

        return {
            "status": "success",
            "message": f"PhishLabs batch job created with ID: {job_id}",
            "job_id": job_id,
            "total_findings": len(findings)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating PhishLabs batch job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating PhishLabs batch job: {str(e)}"
        )


@router.post("/typosquat/phishlabs-incidents/batch", response_model=Dict[str, Any])
async def create_phishlabs_incidents_batch_job(
    request: BatchPhishlabsRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a background job to create PhishLabs incidents for multiple typosquat findings.

    This endpoint creates a Kueue job that will process the findings in the background
    and create PhishLabs incidents for each finding.
    Users can check job status using the /jobs/{job_id}/status endpoint.
    """
    if not request.finding_ids:
        raise HTTPException(status_code=400, detail="No finding IDs provided")

    try:
        logger.info(f"Creating batch PhishLabs incidents job for {len(request.finding_ids)} findings")

        # Validate that all finding IDs exist
        findings = []
        for finding_id in request.finding_ids:
            finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
            if not finding:
                logger.warning(f"Typosquat finding {finding_id} not found, skipping")
                continue
            findings.append(finding)

        if not findings:
            raise HTTPException(status_code=404, detail="No valid typosquat findings found")

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Determine action based on whether catcode is provided
        action = "create" if request.catcode else "fetch"

        # Create job payload
        job_payload = {
            "job_id": job_id,
            "job_type": "phishlabs_batch" if action == "fetch" else "phishlabs_incidents_batch",
            "finding_ids": request.finding_ids,
            "catcode": request.catcode,
            "action": action,
            "report_to_gsb": request.report_to_gsb,
            "user_id": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Create job status record
        job_created = await JobRepository.create_job(job_id, job_payload["job_type"], job_payload)

        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")

        # Submit job to Kubernetes
        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_phishlabs_batch_job(job_id, job_payload)
            if action == "fetch":
                logger.info(f"Submitted PhishLabs batch job {job_id} to Kubernetes")
            else:
                logger.info(f"Submitted PhishLabs incidents batch job {job_id} to Kubernetes")
        except Exception as e:
            logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
            # Update job status to failed
            await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit to Kubernetes: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to submit job to Kubernetes: {str(e)}")

        logger.info(f"Created PhishLabs batch job {job_id} for {len(findings)} findings (action: {action}, GSB: {request.report_to_gsb})")

        # Prepare response message
        message = f"PhishLabs {'incidents ' if action == 'create' else ''}batch job created with ID: {job_id}"
        if request.report_to_gsb:
            message += " (includes Google Safe Browsing reporting)"

        return {
            "status": "success",
            "message": message,
            "job_id": job_id,
            "total_findings": len(findings),
            "action": action,
            "report_to_gsb": request.report_to_gsb
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating PhishLabs incidents batch job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating PhishLabs incidents batch job: {str(e)}"
        )


@router.post("/typosquat/phishlabs-incidents", response_model=Dict[str, Any])
async def create_phishlabs_incident(
    typo_domain: str = Query(..., description="Typosquat domain to create incident for"),
    program_name: str = Query(..., description="Program name associated with the typosquat domain"),
    catcode: str = Query(..., description="PhishLabs category code for the incident"),
    report_to_gsb: bool = Query(False, description="Whether to also report the domain to Google Safe Browsing"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a PhishLabs incident for a single typosquat domain using async job processing.

    This endpoint will:
    1. Find the typosquat finding by domain and program
    2. Create a background Kubernetes job to process the incident creation
    3. Return job ID for status monitoring
    """
    # Validate inputs
    if not typo_domain:
        raise HTTPException(status_code=400, detail="Parameter 'typo_domain' is required")
    if not program_name:
        raise HTTPException(status_code=400, detail="Parameter 'program_name' is required")
    if not catcode:
        raise HTTPException(status_code=400, detail="Parameter 'catcode' is required")

    # 1. Get program & API key
    program = await ProgramRepository.get_program_by_name(program_name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")

    # Fetch the typosquat finding document
    from models.postgres import TyposquatDomain, Program
    from db import get_db_session

    async with get_db_session() as db:
        existing_doc = db.query(TyposquatDomain).join(Program).filter(
            and_(TyposquatDomain.typo_domain == typo_domain, Program.name == program_name)
        ).first()

        if not existing_doc:
            raise HTTPException(status_code=404, detail=f"Typosquat domain '{typo_domain}' not found for program '{program_name}'")

        domain_id_str = str(existing_doc.id)

    api_key = program.get("phishlabs_api_key")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"Program '{program_name}' does not have a PhishLabs API key configured"
        )

    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Create job payload for single finding
        job_payload = {
            "job_id": job_id,
            "job_type": "phishlabs_incidents_batch",
            "finding_ids": [domain_id_str],
            "catcode": catcode,
            "action": "create",
            "report_to_gsb": report_to_gsb,
            "user_id": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Create job status record
        job_created = await JobRepository.create_job(job_id, job_payload["job_type"], job_payload)

        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")

        # Submit job to Kubernetes
        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_phishlabs_batch_job(job_id, job_payload)
            logger.info(f"Submitted PhishLabs incident job {job_id} to Kubernetes for single finding {domain_id_str}")
        except Exception as e:
            logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
            # Update job status to failed
            await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit to Kubernetes: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to submit job to Kubernetes: {str(e)}")

        logger.info(f"Created PhishLabs incident job {job_id} for single finding {domain_id_str} (GSB: {report_to_gsb})")

        # Prepare response message
        message = f"PhishLabs incident job created with ID: {job_id}"
        if report_to_gsb:
            message += " (includes Google Safe Browsing reporting)"

        return {
            "status": "success",
            "message": message,
            "job_id": job_id,
            "typo_domain": typo_domain,
            "program_name": program_name,
            "catcode": catcode,
            "report_to_gsb": report_to_gsb
        }

    except HTTPException:
        # Re-raise FastAPI exceptions directly
        raise
    except Exception as e:
        logger.error(f"Error communicating with PhishLabs: {e}")
        raise HTTPException(status_code=502, detail=f"Error communicating with PhishLabs: {e}")

@router.post("/typosquat/phishlabs", response_model=Dict[str, Any])
async def enrich_typosquat_with_phishlabs(
    typo_domain: str = Query(..., description="Typosquat domain to enrich using PhishLabs"),
    program_name: str = Query(..., description="Program name associated with the typosquat domain"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Fetch PhishLabs information for a typosquat domain using async job processing.

    This endpoint will:
    1. Find the typosquat finding by domain and program
    2. Create a background Kubernetes job to process the PhishLabs data fetching
    3. Return job ID for status monitoring

    The job will use the improved logic that tries multiple URL formats:
    - domain.com
    - http://domain.com
    - https://domain.com
    """
    # Validate inputs – trivial but explicit for better error messages
    if not typo_domain:
        raise HTTPException(status_code=400, detail="Parameter 'typo_domain' is required")
    if not program_name:
        raise HTTPException(status_code=400, detail="Parameter 'program_name' is required")

    # 1. Get program & API key
    program = await ProgramRepository.get_program_by_name(program_name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")

    # Fetch the typosquat finding document early so we have its ID for later updates
    from models.postgres import TyposquatDomain, Program
    from db import get_db_session
    
    async with get_db_session() as db:
        existing_doc = db.query(TyposquatDomain).join(Program).filter(
            and_(TyposquatDomain.typo_domain == typo_domain, Program.name == program_name)
        ).first()
        
        if not existing_doc:
            raise HTTPException(status_code=404, detail=f"Typosquat domain '{typo_domain}' not found for program '{program_name}'")

        domain_id_str = str(existing_doc.id)

    api_key = program.get("phishlabs_api_key")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"Program '{program_name}' does not have a PhishLabs API key configured"
        )

    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Create job payload for single finding with fetch action
        job_payload = {
            "job_id": job_id,
            "job_type": "phishlabs_batch",
            "finding_ids": [domain_id_str],
            "action": "fetch",
            "user_id": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Create job status record
        job_created = await JobRepository.create_job(job_id, "phishlabs_batch", job_payload)

        if not job_created:
            raise HTTPException(status_code=500, detail="Failed to create job status record")

        # Submit job to Kubernetes
        try:
            job_submission_service = JobSubmissionService()
            job_submission_service.create_phishlabs_batch_job(job_id, job_payload)
            logger.info(f"Submitted PhishLabs fetch job {job_id} to Kubernetes for single finding {domain_id_str}")
        except Exception as e:
            logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
            # Update job status to failed
            await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit to Kubernetes: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to submit job to Kubernetes: {str(e)}")

        logger.info(f"Created PhishLabs fetch job {job_id} for single finding {domain_id_str}")

        return {
            "status": "success",
            "message": f"PhishLabs fetch job created with ID: {job_id}. The job will try multiple URL formats to find existing incidents.",
            "job_id": job_id,
            "typo_domain": typo_domain,
            "program_name": program_name,
            "action": "fetch"
        }
    except HTTPException:
        # Re-raise FastAPI exceptions directly
        raise
    except Exception as e:
        logger.error(f"Error creating PhishLabs fetch job: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating PhishLabs fetch job: {e}")


@router.post("/typosquat/phishlabs/create-infraction", response_model=Dict[str, Any])
async def create_phishlabs_infraction(
    typo_domain: str = Query(..., description="Typosquat domain to create infraction for"),
    program_name: str = Query(..., description="Program name associated with the typosquat domain"),
    catcode: str = Query(..., description="PhishLabs category code for the infraction"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a PhishLabs infraction for a typosquat domain.

    This endpoint will:
    1. Retrieve the program configuration to obtain the PhishLabs API key
    2. Use the typo_domain as the URL for the infraction
    3. Call PhishLabs createincident API with flags=0 to create a new infraction
    4. Persist the infraction information into the corresponding typosquat finding document
    """
    # Validate inputs
    if not typo_domain:
        raise HTTPException(status_code=400, detail="Parameter 'typo_domain' is required")
    if not program_name:
        raise HTTPException(status_code=400, detail="Parameter 'program_name' is required")
    if not catcode:
        raise HTTPException(status_code=400, detail="Parameter 'catcode' is required")

    # 1. Get program & API key
    program = await ProgramRepository.get_program_by_name(program_name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")

    # Fetch the typosquat finding document
    from models.postgres import TyposquatDomain, Program
    from db import get_db_session

    async with get_db_session() as db:
        existing_doc = db.query(TyposquatDomain).join(Program).filter(
            and_(TyposquatDomain.typo_domain == typo_domain, Program.name == program_name)
        ).first()

        if not existing_doc:
            raise HTTPException(status_code=404, detail=f"Typosquat domain '{typo_domain}' not found for program '{program_name}'")

        domain_id_str = str(existing_doc.id)

    api_key = program.get("phishlabs_api_key")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"Program '{program_name}' does not have a PhishLabs API key configured"
        )

    try:
        # Use aiohttp for async HTTP calls
        async with aiohttp.ClientSession() as session:
            # Call PhishLabs APIs using the helper function with create action
            # Use typo_domain as the URL parameter for PhishLabs API
            phishlabs_result = await _call_phishlabs_apis(
                session, typo_domain, api_key, catcode, action="create"
            )

            # Get current typosquat data for upsert
            current_typosquat = await TyposquatFindingsRepository.get_typosquat_by_id(domain_id_str)
            if not current_typosquat:
                raise HTTPException(status_code=404, detail=f"Typosquat domain {domain_id_str} not found")

            # Prepare data for create_or_update_typosquat_finding
            upsert_data = {
                "typo_domain": current_typosquat.get("typo_domain"),
                "program_name": current_typosquat.get("program_name")
            }

            # Initialize phishlabs_data with meta information
            phishlabs_meta = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "url": typo_domain
            }

            # Extract detailed PhishLabs data from the response
            incident_response = phishlabs_result.get("incident_response", {})
            if incident_response:
                infraction = incident_response.get("Infraction", {})
                enrichment = incident_response.get("EnrichmentData", {})

                # Map Infraction data (consolidated into JSONB)
                if infraction:
                    phishlabs_data = {
                        "incident_id": infraction.get("Infrid"),
                        "category_code": infraction.get("Catcode"),
                        "category_name": infraction.get("Catname"),
                        "status": infraction.get("Status"),
                        "comment": infraction.get("Comment"),
                        "product": infraction.get("Product"),
                        "create_date": infraction.get("Createdate"),
                        "assignee": infraction.get("Assignee"),
                        "last_comment": infraction.get("Lastcomment"),
                        "group_category_name": infraction.get("Groupcatname"),
                        "action_description": infraction.get("Actiondescr"),
                        "status_description": infraction.get("Statusdescr"),
                        "mitigation_start": infraction.get("Mitigationstart"),
                        "date_resolved": infraction.get("Dateresolved"),
                        "severity_name": infraction.get("Severityname"),
                        "mx_record": infraction.get("Mxrecord"),
                        "ticket_status": infraction.get("Ticketstatus"),
                        "resolution_status": infraction.get("Resolutionstatus"),
                        "incident_status": infraction.get("Incidentstatus")
                    }
                    # Merge meta data with incident data
                    phishlabs_data.update(phishlabs_meta)
                    upsert_data["phishlabs_data"] = phishlabs_data
                else:
                    # No incident data, just store the meta information
                    upsert_data["phishlabs_data"] = phishlabs_meta

                # Map EnrichmentData (this can update existing domain data)
                if enrichment:
                    # Only update if we don't already have this data
                    if not current_typosquat.get("whois_registrar"):
                        upsert_data["whois_registrar"] = enrichment.get("RegistrarName")
                    if not current_typosquat.get("whois_creation_date"):
                        upsert_data["whois_creation_date"] = enrichment.get("RegistrationDate")
                    if not current_typosquat.get("whois_expiration_date"):
                        upsert_data["whois_expiration_date"] = enrichment.get("ExpiryDate")
                    if not current_typosquat.get("whois_registrant_name"):
                        upsert_data["whois_registrant_name"] = enrichment.get("RegistrantFullName")
                    if not current_typosquat.get("geoip_country"):
                        upsert_data["geoip_country"] = enrichment.get("Country")
                    if not current_typosquat.get("geoip_organization"):
                        upsert_data["geoip_organization"] = enrichment.get("Isp")

            if phishlabs_result.get("no_incident"):
                # Add no_incident flag to phishlabs_data if it exists, otherwise create it
                if "phishlabs_data" in upsert_data:
                    upsert_data["phishlabs_data"]["no_incident"] = True
                else:
                    phishlabs_meta["no_incident"] = True
                    upsert_data["phishlabs_data"] = phishlabs_meta

            # Ensure datetime objects in phishlabs_data are properly serialized as ISO strings for JSONB
            if upsert_data.get("phishlabs_data"):
                for key, value in upsert_data["phishlabs_data"].items():
                    if isinstance(value, datetime):
                        # Convert datetime to ISO format string
                        upsert_data["phishlabs_data"][key] = value.isoformat()
                    elif key in ["create_date", "mitigation_start", "date_resolved"] and value:
                        # For known date fields that come as strings, ensure they're properly formatted
                        try:
                            if isinstance(value, str) and 'Z' in value:
                                # Convert to datetime first, then back to proper ISO format
                                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                upsert_data["phishlabs_data"][key] = dt.isoformat()
                        except (ValueError, AttributeError) as e:
                            logger.warning(f"Failed to parse date field {key}: {value}, error: {e}")
                            upsert_data["phishlabs_data"][key] = None


            logger.info(f"Upserting typosquat domain {current_typosquat.get('typo_domain')} with PhishLabs data: {list(upsert_data.keys())}")
            _cu = await TyposquatFindingsRepository.create_or_update_typosquat_finding(upsert_data)
            upserted_id = _cu[0] if isinstance(_cu, tuple) else _cu
            if upserted_id:
                logger.info(f"Successfully upserted typosquat domain {current_typosquat.get('typo_domain')} with ID: {upserted_id}")
            else:
                logger.error(f"Failed to upsert typosquat domain {current_typosquat.get('typo_domain')} with PhishLabs data")

            return {
                "status": "success",
                "message": "PhishLabs infraction created and stored successfully" if not phishlabs_result.get("no_incident") else "PhishLabs infraction creation completed - no new infraction created",
                "incident_id": phishlabs_result.get("incident_id"),
                "createincident_response": phishlabs_result.get("createincident_response"),
                "incident_response": phishlabs_result.get("incident_response"),
                "catcode": catcode,
                "url": typo_domain
            }

    except HTTPException:
        # Re-raise FastAPI exceptions directly
        raise
    except Exception as e:
        logger.error(f"Error communicating with PhishLabs: {e}")
        raise HTTPException(status_code=502, detail=f"Error communicating with PhishLabs: {e}")

# ===== TYPOSQUAT RISK SCORE CALCULATION ENDPOINTS =====

class RiskCalculationRequest(BaseModel):
    program_name: Optional[str] = None
    finding_ids: Optional[List[str]] = None

@router.post("/typosquat/calculate-risk-scores")
async def calculate_typosquat_risk_scores(
    request: RiskCalculationRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Calculate risk scores for typosquat domains.
    
    This endpoint can:
    1. Calculate risk scores for specific finding IDs (if finding_ids provided)
    2. Calculate risk scores for all domains in a program (if program_name provided)
    3. Calculate risk scores for all domains (if neither provided)
    
    The endpoint uses the latest program configuration and risk factors.
    """
    try:
        program_name = request.program_name
        finding_ids = request.finding_ids
        
        if finding_ids:
            logger.info(f"Starting risk score calculation for {len(finding_ids)} specific findings")
        elif program_name:
            logger.info(f"Starting batch risk score calculation for program: {program_name}")
        else:
            logger.info("Starting batch risk score calculation for all domains")
        
        result = await TyposquatFindingsRepository.calculate_typosquat_risk_scores(program_name, finding_ids)
        
        if result['status'] == 'success':
            if finding_ids:
                logger.info(f"Risk score calculation completed: {result['updated_count']}/{result['total_domains']} selected domains updated")
                message = f"Risk scores calculated for {result['updated_count']} out of {result['total_domains']} selected domains"
            else:
                logger.info(f"Batch risk score calculation completed: {result['updated_count']}/{result['total_domains']} domains updated")
                message = f"Risk scores calculated for {result['updated_count']} out of {result['total_domains']} domains"
            
            return {
                "status": "success",
                "message": message,
                "total_domains": result['total_domains'],
                "updated_count": result['updated_count'],
                "program_name": result.get('program_name'),
                "finding_ids": finding_ids
            }
        else:
            logger.error(f"Risk score calculation failed: {result.get('message')}")
            raise HTTPException(
                status_code=500,
                detail=f"Risk score calculation failed: {result.get('message')}"
            )
            
    except Exception as e:
        logger.error(f"Error in risk score calculation: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating risk scores: {str(e)}"
        )

@router.post("/typosquat/{domain_id}/calculate-risk-score")
async def calculate_single_typosquat_risk_score(
    domain_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Calculate risk score for a single typosquat domain.
    This endpoint triggers a recalculation of the risk score for a specific domain
    using the latest program configuration and risk factors.
    """
    try:
        logger.info(f"Starting risk score calculation for domain: {domain_id}")
        
        result = await TyposquatFindingsRepository.calculate_single_typosquat_risk_score(domain_id)
        
        if result['status'] == 'success':
            logger.info(f"Risk score calculation completed for domain {result['domain']}: {result['risk_score']}")
            return {
                "status": "success",
                "message": f"Risk score calculated for domain {result['domain']}",
                "domain": result['domain'],
                "risk_score": result['risk_score'],
                "program_name": result.get('program_name')
            }
        else:
            logger.error(f"Risk score calculation failed for domain {domain_id}: {result.get('message')}")
            raise HTTPException(
                status_code=400,
                detail=f"Risk score calculation failed: {result.get('message')}"
            )
            
    except Exception as e:
        logger.error(f"Error in risk score calculation for domain {domain_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating risk score: {str(e)}"
        )

# Pydantic models for typosquat URL search
class TyposquatURLSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Fuzzy search on URL")
    exact_match: Optional[str] = Field(None, description="Exact match on URL")
    protocol: Optional[str] = Field(None, description="Filter by protocol (http/https)")
    status_code: Optional[int] = Field(None, description="Filter by HTTP status code")
    only_root: Optional[bool] = Field(None, description="Only path = '/' ")
    technology_text: Optional[str] = Field(None, description="Text search in technologies")
    technology: Optional[str] = Field(None, description="Exact technology match")
    program: Optional[str] = Field(None, description="Filter by program name")
    sort_by: Optional[str] = Field("url", description="Sort field")
    sort_dir: Optional[str] = Field("asc", description="Sort direction (asc/desc)")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(25, ge=1, le=1000, description="Page size")

# Pydantic models for typosquat screenshot search
class TyposquatScreenshotSearchRequest(BaseModel):
    search_url: Optional[str] = Field(None, description="Fuzzy search on URL")
    url_equals: Optional[str] = Field(None, description="Exact match on URL")
    typosquat_type: Optional[str] = Field(None, description="Filter by typosquat type")
    exclude_parked: Optional[bool] = Field(False, description="Exclude screenshots whose URL's typosquat domain is identified as parked")
    program: Optional[str] = Field(None, description="Filter by program name")
    sort_by: Optional[str] = Field("upload_date", description="Sort field")
    sort_dir: Optional[str] = Field("desc", description="Sort direction (asc/desc)")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=1000, description="Page size")

# Pydantic models for typosquat URL creation
class TyposquatURLCreateRequest(BaseModel):
    url: str = Field(..., description="URL to store")
    hostname: str = Field(..., description="Hostname")
    port: Optional[int] = Field(None, description="Port number")
    path: Optional[str] = Field(None, description="URL path")
    scheme: Optional[str] = Field(None, description="URL scheme (http/https)")
    http_status_code: Optional[int] = Field(None, description="HTTP status code")
    http_method: Optional[str] = Field(None, description="HTTP method")
    response_time_ms: Optional[int] = Field(None, description="Response time in milliseconds")
    content_type: Optional[str] = Field(None, description="Content type")
    content_length: Optional[int] = Field(None, description="Content length")
    line_count: Optional[int] = Field(None, description="Line count")
    word_count: Optional[int] = Field(None, description="Word count")
    title: Optional[str] = Field(None, description="Page title")
    final_url: Optional[str] = Field(None, description="Final URL after redirects")
    technologies: Optional[List[str]] = Field(None, description="Technologies detected")
    response_body_hash: Optional[str] = Field(None, description="Response body hash")
    body_preview: Optional[str] = Field(None, description="Body preview")
    favicon_hash: Optional[str] = Field(None, description="Favicon hash")
    favicon_url: Optional[str] = Field(None, description="Favicon URL")
    redirect_chain: Optional[Dict[str, Any]] = Field(None, description="Redirect chain")
    chain_status_codes: Optional[List[int]] = Field(None, description="Chain status codes")
    extracted_links: Optional[List[str]] = Field(None, description="Extracted links")
    program_name: str = Field(..., description="Program name")
    typosquat_domain: Optional[str] = Field(None, description="Typosquat domain name to associate with this URL")
    typosquat_domain_id: Optional[str] = Field(None, description="Typosquat domain ID to associate with this URL")
    typosquat_certificate_id: Optional[str] = Field(None, description="Typosquat certificate ID to associate with this URL")
    notes: Optional[str] = Field(None, description="Notes")
    # TLS data for SSL certificate processing (not stored in URL table)
    tls: Optional[Dict[str, Any]] = Field(None, description="TLS/SSL certificate data from httpx for certificate creation")
    
    @classmethod
    def validate_typosquat_domain_required(cls, values):
        """Ensure either typosquat_domain or typosquat_domain_id is provided"""
        if not values.get('typosquat_domain') and not values.get('typosquat_domain_id'):
            raise ValueError("Either typosquat_domain or typosquat_domain_id must be provided")
        return values

@router.post("/typosquat-url/search", response_model=Dict[str, Any])
async def search_typosquat_urls(
    request: TyposquatURLSearchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Search typosquat URLs with filtering and pagination"""
    try:
        # Resolve programs within user access
        accessible = get_user_accessible_programs(current_user)
        requested_program = request.program
        
        programs: Optional[List[str]] = None
        if current_user.is_superuser or "admin" in current_user.roles:
            programs = [requested_program] if requested_program else None
        else:
            allowed = accessible or []
            if not allowed:
                return {
                    "status": "success",
                    "pagination": {
                        "total_items": 0,
                        "total_pages": 1,
                        "current_page": request.page,
                        "page_size": request.page_size,
                        "has_next": False,
                        "has_previous": False,
                    },
                    "items": [],
                }
            if requested_program:
                if requested_program not in allowed:
                    return {
                        "status": "success",
                        "pagination": {
                            "total_items": 0,
                            "total_pages": 1,
                            "current_page": request.page,
                            "page_size": request.page_size,
                            "has_next": False,
                            "has_previous": False,
                        },
                        "items": [],
                    }
                programs = [requested_program]
            else:
                programs = allowed

        skip = (request.page - 1) * request.page_size

        # Build search parameters
        search_params = {}
        if request.search:
            search_params["search"] = request.search
        if request.exact_match:
            search_params["exact_match"] = request.exact_match
        if request.protocol:
            search_params["protocol"] = request.protocol
        if request.status_code:
            search_params["status_code"] = request.status_code
        if request.only_root:
            search_params["only_root"] = True
        if request.technology_text:
            search_params["technology_text"] = request.technology_text
        if request.technology:
            search_params["technology"] = request.technology
        if programs:
            search_params["programs"] = programs

        # Get URLs from repository
        result = await TyposquatFindingsRepository.search_typosquat_urls(
            search_params=search_params,
            sort_by=request.sort_by or "url",
            sort_dir=request.sort_dir or "asc",
            limit=request.page_size,
            skip=skip
        )

        urls = result.get("items", [])
        total_count = result.get("total_count", 0)
        total_pages = (total_count + request.page_size - 1) // request.page_size if request.page_size > 0 else 1

        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": request.page,
                "page_size": request.page_size,
                "has_next": request.page < total_pages,
                "has_previous": request.page > 1,
            },
            "items": urls or [],
        }

    except Exception as e:
        logger.error(f"Error searching typosquat URLs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error searching typosquat URLs: {str(e)}"
        )

@router.post("/typosquat-url", response_model=Dict[str, Any])
async def create_typosquat_url(
    request: TyposquatURLCreateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a new typosquat URL or update if exists with merged data"""
    try:
        logger.info(f"Creating or updating typosquat URL: {request.url}")
        
        # Validate that a typosquat domain is provided
        if not request.typosquat_domain and not request.typosquat_domain_id:
            raise HTTPException(
                status_code=400,
                detail="Either typosquat_domain or typosquat_domain_id must be provided"
            )
        
        # Convert Pydantic model to dictionary for repository
        url_data = request.model_dump()
        
        # Use create_or_update function from repository
        url_id, was_created, typosquat_domain_id = await TyposquatFindingsRepository.create_or_update_typosquat_url(url_data)
        
        # Domain was filtered out -- return 200 so callers don't retry
        if url_id is None and was_created is False and typosquat_domain_id is None:
            logger.info(f"Typosquat URL skipped (domain filtered): {request.url}")
            return {
                "status": "filtered",
                "message": "Typosquat URL skipped - domain did not pass filtering",
                "url_id": None,
                "was_created": False
            }

        if not url_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create/update typosquat URL - no ID returned"
            )
        
        if typosquat_domain_id:
            try:
                risk_result = await TyposquatFindingsRepository.calculate_single_typosquat_risk_score(typosquat_domain_id)
                if risk_result.get('status') == 'success':
                    logger.info(f"Risk score recalculated for domain {typosquat_domain_id} after URL insert: {risk_result.get('risk_score')}")
                else:
                    logger.warning(f"Failed to recalculate risk score for domain {typosquat_domain_id}: {risk_result.get('message')}")
            except Exception as risk_error:
                logger.error(f"Error recalculating risk score for domain {typosquat_domain_id}: {risk_error}")
            
        logger.info(f"Successfully created/updated typosquat URL with ID: {url_id}")
        return {
            "status": "success",
            "message": f"Typosquat URL {'created' if was_created else 'updated'} successfully",
            "url_id": url_id,
            "was_created": was_created
        }
        
    except Exception as e:
        logger.error(f"Error in create_typosquat_url: {str(e)}")
        logger.error(f"URL data: {request.model_dump()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create/update typosquat URL: {str(e)}"
        )

@router.get("/typosquat-url", response_model=List[Dict[str, Any]])
async def get_typosquat_urls_by_domain(
    domain: Optional[str] = Query(None, description="Filter by typosquat domain"),
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    limit: int = Query(100, description="Maximum number of URLs to return"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get typosquat URLs filtered by domain and/or program"""
    try:
        logger.info(f"Fetching typosquat URLs for domain: {domain}, program: {program_name}")
        
        urls = await TyposquatFindingsRepository.get_typosquat_urls_by_domain(
            domain=domain,
            program_name=program_name,
            limit=limit
        )
        
        return urls
        
    except Exception as e:
        logger.error(f"Error fetching typosquat URLs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch typosquat URLs: {str(e)}"
        )

@router.get("/typosquat-url/{url_id}", response_model=Dict[str, Any])
async def get_typosquat_url_by_id(
    url_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a specific typosquat URL by ID"""
    try:
        logger.info(f"Fetching typosquat URL with ID: {url_id}")
        
        url = await TyposquatFindingsRepository.get_typosquat_url_by_id(url_id)
        
        if not url:
            raise HTTPException(
                status_code=404,
                detail="Typosquat URL not found"
            )
        
        return url
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching typosquat URL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch typosquat URL: {str(e)}"
        )

@router.delete("/typosquat-url/batch", response_model=Dict[str, Any])
async def delete_typosquat_urls_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple typosquat URLs by their IDs"""
    try:
        # Extract asset_ids from request data
        asset_ids = request_data.get("asset_ids", [])
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No URL IDs provided")
        
        result = await TyposquatFindingsRepository.delete_typosquat_urls_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for typosquat URLs",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting typosquat URLs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/typosquat-urls/{url_id}", response_model=Dict[str, Any])
async def delete_typosquat_url(
    url_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a typosquat URL by ID"""
    try:
        logger.info(f"Deleting typosquat URL with ID: {url_id}")
        
        success = await TyposquatFindingsRepository.delete_typosquat_url(url_id)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Typosquat URL not found or could not be deleted"
            )
        
        return {
            "status": "success",
            "message": "Typosquat URL deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting typosquat URL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete typosquat URL: {str(e)}"
        )

@router.put("/typosquat-url/{url_id}/notes", response_model=Dict[str, Any])
async def update_typosquat_url_notes(
    url_id: str,
    request: NotesUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update notes for a typosquat URL"""
    try:
        logger.info(f"Updating notes for typosquat URL: {url_id}")
        
        success = await TyposquatFindingsRepository.update_typosquat_url_notes(url_id, request.notes)
        
        if not success:
            raise HTTPException(status_code=404, detail="Typosquat URL not found")
        
        return {
            "status": "success",
            "message": "Notes updated successfully",
            "data": {
                "notes": request.notes
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating typosquat URL notes {url_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update typosquat URL notes: {str(e)}")

@router.get("/typosquat-certificates/{certificate_id}", response_model=Dict[str, Any])
async def get_typosquat_certificate_by_id(
    certificate_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a specific typosquat certificate by ID"""
    try:
        logger.info(f"Fetching typosquat certificate with ID: {certificate_id}")
        
        certificate = await TyposquatFindingsRepository.get_typosquat_certificate_by_id(certificate_id)
        
        if not certificate:
            raise HTTPException(
                status_code=404,
                detail="Typosquat certificate not found"
            )
        
        return certificate
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching typosquat certificate {certificate_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch typosquat certificate: {str(e)}"
        )

@router.post("/typosquat-screenshot", response_model=Dict[str, Any])
async def upload_typosquat_screenshot(
    file: UploadFile = File(...),
    program_name: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    workflow_id: Optional[str] = Form(None),
    step_name: Optional[str] = Form(None),
    extracted_text: Optional[str] = Form(None),
    source_created_at: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Upload a screenshot for a typosquat domain"""
    try:
        logger.debug(f"upload_typosquat_screenshot called with file {file.filename}")
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Check file size (limit to 10MB)
        file_size_limit = 10 * 1024 * 1024  # 10MB
        if file.size and file.size > file_size_limit:
            raise HTTPException(status_code=400, detail="File size too large. Maximum size is 10MB")
        
        # Validate content type
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
            )
        
        # Read file content
        file_content = await file.read()
        
        logger.info(f"Uploading typosquat screenshot: {file.filename} ({len(file_content)} bytes)")
        
        # Store the screenshot using repository method
        file_id = await TyposquatFindingsRepository.store_typosquat_screenshot(
            image_data=file_content,
            filename=file.filename,
            content_type=file.content_type,
            program_name=program_name,
            url=url,
            workflow_id=workflow_id,
            step_name=step_name,
            extracted_text=extracted_text,
            source_created_at=source_created_at,
            source=source
        )
        
        if not file_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to store typosquat screenshot - no file ID returned"
            )
        
        logger.info(f"Successfully stored typosquat screenshot with file_id: {file_id}")
        
        return {
            "status": "success",
            "message": "Typosquat screenshot uploaded successfully",
            "file_id": file_id,
            "filename": file.filename,
            "file_size": len(file_content),
            "content_type": file.content_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading typosquat screenshot: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading typosquat screenshot: {str(e)}"
        )

@router.delete("/typosquat-screenshot/batch", response_model=Dict[str, Any])
async def delete_typosquat_screenshots_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple typosquat screenshots by their IDs"""
    try:
        # Extract asset_ids from request data
        asset_ids = request_data.get("asset_ids", [])
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No screenshot IDs provided")
        
        result = await TyposquatFindingsRepository.delete_typosquat_screenshots_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for typosquat screenshots",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting typosquat screenshots: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/typosquat-screenshot/{file_id}")
async def get_typosquat_screenshot(
    file_id: str,
    thumbnail: Optional[int] = Query(None, ge=50, le=800, description="Generate thumbnail with max dimension (50-800px)"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a typosquat screenshot by file ID"""
    try:
        # Get screenshot data
        screenshot_data = await TyposquatFindingsRepository.get_typosquat_screenshot(file_id)
        
        if not screenshot_data:
            raise HTTPException(status_code=404, detail="Typosquat screenshot not found")
        
        # Check if user has access to this program
        if screenshot_data.get("metadata", {}).get("program_name"):
            accessible_programs = get_user_accessible_programs(current_user)
            if accessible_programs and screenshot_data["metadata"]["program_name"] not in accessible_programs:
                raise HTTPException(status_code=404, detail="Typosquat screenshot not found")
        
        image_data = screenshot_data["file_content"]
        content_type = screenshot_data["content_type"]
        filename = screenshot_data["filename"]
        
        # Handle thumbnail generation if requested
        if thumbnail:
            try:
                from PIL import Image
                
                # Open the image with PIL
                img = Image.open(io.BytesIO(image_data))
                
                # Calculate new dimensions maintaining aspect ratio
                img.thumbnail((thumbnail, thumbnail), Image.Resampling.LANCZOS)
                
                # Save as JPEG for better compression
                output = io.BytesIO()
                # Convert RGBA to RGB if necessary for JPEG
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                img.save(output, format='JPEG', quality=85, optimize=True)
                image_data = output.getvalue()
                content_type = "image/jpeg"
                filename = f"thumb_{thumbnail}_{filename.rsplit('.', 1)[0]}.jpg"
                
            except ImportError:
                logger.warning("PIL not available, cannot generate thumbnail")
                # Fall back to original image if thumbnail generation fails
                pass
            except Exception as e:
                logger.error(f"Error generating thumbnail: {str(e)}")
                # Fall back to original image if thumbnail generation fails
                pass
        
        # Return the screenshot as a streaming response
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            io.BytesIO(image_data),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Length": str(len(image_data)),
                "Cache-Control": "public, max-age=3600" if thumbnail else "public, max-age=86400"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting typosquat screenshot {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/typosquat-screenshot/search", response_model=Dict[str, Any])
async def search_typosquat_screenshots(
    request: TyposquatScreenshotSearchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Search typosquat screenshots with filtering and pagination"""
    try:
        # Resolve programs within user access
        accessible = get_user_accessible_programs(current_user)
        requested_program = request.program
        
        programs: Optional[List[str]] = None
        if current_user.is_superuser or "admin" in current_user.roles:
            programs = [requested_program] if requested_program else None
        else:
            allowed = accessible or []
            if not allowed:
                return {
                    "status": "success",
                    "pagination": {
                        "total_items": 0,
                        "total_pages": 1,
                        "current_page": request.page,
                        "page_size": request.page_size,
                        "has_next": False,
                        "has_previous": False,
                    },
                    "items": [],
                }
            if requested_program:
                if requested_program not in allowed:
                    return {
                        "status": "success",
                        "pagination": {
                            "total_items": 0,
                            "total_pages": 1,
                            "current_page": request.page,
                            "page_size": request.page_size,
                            "has_next": False,
                            "has_previous": False,
                        },
                        "items": [],
                    }
                programs = [requested_program]
            else:
                programs = allowed

        skip = (request.page - 1) * request.page_size

        # Build search parameters
        search_params = {}
        if request.search_url:
            search_params["search_url"] = request.search_url
        if request.url_equals:
            search_params["url_equals"] = request.url_equals
        if request.typosquat_type:
            search_params["typosquat_type"] = request.typosquat_type
        if request.exclude_parked:
            search_params["exclude_parked"] = True
        if programs:
            search_params["programs"] = programs

        # Get screenshots from repository
        result = await TyposquatFindingsRepository.search_typosquat_screenshots(
            search_params=search_params,
            sort_by=request.sort_by or "created_at",
            sort_dir=request.sort_dir or "desc",
            limit=request.page_size,
            skip=skip
        )

        screenshots = result.get("items", [])
        total_count = result.get("total_count", 0)
        total_pages = (total_count + request.page_size - 1) // request.page_size if request.page_size > 0 else 1

        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": request.page,
                "page_size": request.page_size,
                "has_next": request.page < total_pages,
                "has_previous": request.page > 1,
            },
            "items": screenshots or [],
        }

    except Exception as e:
        logger.error(f"Error searching typosquat screenshots: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error searching typosquat screenshots: {str(e)}"
        )

@router.get("/typosquat-screenshot", response_model=Dict[str, Any])
async def list_typosquat_screenshots(
    program_name: Optional[str] = Query(None),
    url: Optional[str] = Query(None),
    workflow_id: Optional[str] = Query(None),
    step_name: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    skip: int = Query(0, ge=0),
    sort: Optional[str] = Query(None, description="Sort field, prefix with '-' for descending (e.g., '-upload_date')")
):
    """List typosquat screenshots with optional filtering and pagination"""
    try:
        # Parse sort parameter
        sort_dict = None
        if sort:
            if sort.startswith('-'):
                sort_dict = {sort[1:]: -1}
            else:
                sort_dict = {sort: 1}
        
        # Get screenshots from repository
        screenshots = await TyposquatFindingsRepository.list_typosquat_screenshots(
            program_name=program_name,
            url=url,
            workflow_id=workflow_id,
            step_name=step_name,
            limit=limit,
            skip=skip,
            sort=sort_dict
        )
        
        # Calculate pagination metadata
        total_count = len(screenshots)  # This is a simple count, could be optimized with a separate count query
        current_page = skip // limit + 1 if limit > 0 else 1
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
        
        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": current_page,
                "page_size": limit,
                "has_next": current_page < total_pages,
                "has_previous": current_page > 1
            },
            "items": screenshots
        }
        
    except Exception as e:
        logger.error(f"Error listing typosquat screenshots: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== TYPOSQUAT CERTIFICATE ENDPOINTS =====

# Pydantic models for typosquat certificate requests
class TyposquatCertificateCreateRequest(BaseModel):
    subject_dn: str = Field(..., description="Subject Distinguished Name")
    subject_cn: str = Field(..., description="Subject Common Name")
    subject_alternative_names: Optional[List[str]] = Field(None, description="Subject Alternative Names")
    valid_from: str = Field(..., description="Valid from date (ISO format)")
    valid_until: str = Field(..., description="Valid until date (ISO format)")
    issuer_dn: str = Field(..., description="Issuer Distinguished Name")
    issuer_cn: str = Field(..., description="Issuer Common Name")
    issuer_organization: Optional[List[str]] = Field(None, description="Issuer Organization")
    serial_number: str = Field(..., description="Serial number")
    fingerprint_hash: str = Field(..., description="Fingerprint hash")
    program_name: str = Field(..., description="Program name")
    typosquat_domain: Optional[str] = Field(None, description="Typosquat domain name")
    typosquat_domain_id: Optional[str] = Field(None, description="Typosquat domain ID")
    notes: Optional[str] = Field(None, description="Notes")

class TyposquatCertificateUpdateRequest(BaseModel):
    subject_dn: Optional[str] = Field(None, description="Subject Distinguished Name")
    subject_cn: Optional[str] = Field(None, description="Subject Common Name")
    subject_alternative_names: Optional[List[str]] = Field(None, description="Subject Alternative Names")
    valid_from: Optional[str] = Field(None, description="Valid from date (ISO format)")
    valid_until: Optional[str] = Field(None, description="Valid until date (ISO format)")
    issuer_dn: Optional[str] = Field(None, description="Issuer Distinguished Name")
    issuer_cn: Optional[str] = Field(None, description="Issuer Common Name")
    issuer_organization: Optional[List[str]] = Field(None, description="Issuer Organization")
    fingerprint_hash: Optional[str] = Field(None, description="Fingerprint hash")
    notes: Optional[str] = Field(None, description="Notes")

@router.post("/typosquat-certificate", response_model=Dict[str, Any])
async def create_typosquat_certificate(
    request: TyposquatCertificateCreateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Create a new typosquat certificate"""
    try:
        logger.info(f"Creating typosquat certificate for domain: {request.subject_cn}")
        
        # Convert Pydantic model to dictionary for repository
        certificate_data = request.model_dump()
        
        # Convert date strings to datetime objects
        if certificate_data.get('valid_from'):
            try:
                certificate_data['valid_from'] = datetime.fromisoformat(certificate_data['valid_from'].replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid valid_from date format. Use ISO format.")
        
        if certificate_data.get('valid_until'):
            try:
                certificate_data['valid_until'] = datetime.fromisoformat(certificate_data['valid_until'].replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid valid_until date format. Use ISO format.")
        
        # Create the certificate using repository method
        certificate_id = await TyposquatFindingsRepository.create_or_update_typosquat_certificate(certificate_data)
        
        if not certificate_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create typosquat certificate - no ID returned"
            )
            
        logger.info(f"Successfully created typosquat certificate with ID: {certificate_id}")
        
        return {
            "status": "success",
            "message": "Typosquat certificate created successfully",
            "certificate_id": certificate_id
        }
        
    except Exception as e:
        logger.error(f"Error in create_typosquat_certificate: {str(e)}")
        logger.error(f"Certificate data: {request.model_dump()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create typosquat certificate: {str(e)}"
        )

@router.get("/typosquat-certificate/{certificate_id}", response_model=Dict[str, Any])
async def get_typosquat_certificate(
    certificate_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a typosquat certificate by ID"""
    try:
        certificate = await TyposquatFindingsRepository.get_typosquat_certificate_by_id(certificate_id)
        
        if not certificate:
            raise HTTPException(status_code=404, detail=f"Typosquat certificate {certificate_id} not found")
        
        return {
            "status": "success",
            "data": certificate
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting typosquat certificate {certificate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/typosquat-certificate", response_model=Dict[str, Any])
async def list_typosquat_certificates(
    program_name: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """List typosquat certificates with optional filtering and pagination"""
    try:
        # Get certificates from repository
        certificates = await TyposquatFindingsRepository.list_typosquat_certificates(
            program_name=program_name,
            limit=limit,
            skip=skip
        )
        
        # Calculate pagination metadata
        total_count = len(certificates)  # This is a simple count, could be optimized with a separate count query
        current_page = skip // limit + 1 if limit > 0 else 1
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
        
        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": current_page,
                "page_size": limit,
                "has_next": current_page < total_pages,
                "has_previous": current_page > 1
            },
            "items": certificates
        }
        
    except Exception as e:
        logger.error(f"Error listing typosquat certificates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/typosquat-certificate/{certificate_id}", response_model=Dict[str, Any])
async def update_typosquat_certificate(
    certificate_id: str,
    request: TyposquatCertificateUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update a typosquat certificate"""
    try:
        logger.info(f"Updating typosquat certificate: {certificate_id}")
        
        # Convert Pydantic model to dictionary for repository
        update_data = request.model_dump(exclude_unset=True)
        
        # Convert date strings to datetime objects
        if update_data.get('valid_from'):
            try:
                update_data['valid_from'] = datetime.fromisoformat(update_data['valid_from'].replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid valid_from date format. Use ISO format.")
        
        if update_data.get('valid_until'):
            try:
                update_data['valid_until'] = datetime.fromisoformat(update_data['valid_until'].replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid valid_until date format. Use ISO format.")
        
        # Update the certificate using repository method
        success = await TyposquatFindingsRepository.update_typosquat_certificate(certificate_id, update_data)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Typosquat certificate {certificate_id} not found")
        
        logger.info(f"Successfully updated typosquat certificate: {certificate_id}")
        
        return {
            "status": "success",
            "message": "Typosquat certificate updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating typosquat certificate {certificate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/typosquat-certificate/{certificate_id}", response_model=Dict[str, Any])
async def delete_typosquat_certificate(
    certificate_id: str,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a typosquat certificate by its ID"""
    try:
        deleted = await TyposquatFindingsRepository.delete_typosquat_certificate(certificate_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Typosquat certificate {certificate_id} not found")
        
        return {
            "status": "success",
            "message": f"Typosquat certificate {certificate_id} deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting typosquat certificate {certificate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== RECORDEDFUTURE DATA UPDATE ENDPOINT =====

class RecordedFutureDataUpdateRequest(BaseModel):
    recordedfuture_data: Dict[str, Any] = Field(..., description="Updated RecordedFuture data")

@router.patch("/typosquat/{finding_id}/recordedfuture-data", response_model=Dict[str, Any])
async def update_typosquat_recordedfuture_data(
    finding_id: str,
    request: RecordedFutureDataUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update the RecordedFuture data field for a typosquat finding"""
    try:
        logger.info(f"Updating RecordedFuture data for finding: {finding_id}")

        # Validate that the finding exists
        existing_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        if not existing_finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        # Update only the recordedfuture_data field
        update_data = {
            "recordedfuture_data": request.recordedfuture_data
        }

        success = await TyposquatFindingsRepository.update_typosquat_domain(finding_id, update_data)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update RecordedFuture data for finding {finding_id}"
            )

        logger.info(f"Successfully updated RecordedFuture data for finding {finding_id}")

        return {
            "status": "success",
            "message": f"RecordedFuture data updated successfully for finding {finding_id}",
            "finding_id": finding_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating RecordedFuture data for finding {finding_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update RecordedFuture data: {str(e)}"
        )


class ThreatStreamDataUpdateRequest(BaseModel):
    threatstream_data: Dict[str, Any] = Field(..., description="Updated ThreatStream data")


@router.patch("/typosquat/{finding_id}/threatstream-data", response_model=Dict[str, Any])
async def update_typosquat_threatstream_data(
    finding_id: str,
    request: ThreatStreamDataUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Update the threatstream_data JSONB field for a typosquat finding (runner / internal enrichment)."""
    try:
        logger.info(f"Updating ThreatStream data for finding: {finding_id}")

        existing_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        if not existing_finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        update_data = {"threatstream_data": request.threatstream_data}
        success = await TyposquatFindingsRepository.update_typosquat_domain(finding_id, update_data)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update ThreatStream data for finding {finding_id}",
            )

        return {
            "status": "success",
            "message": f"ThreatStream data updated successfully for finding {finding_id}",
            "finding_id": finding_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating ThreatStream data for finding {finding_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update ThreatStream data: {str(e)}",
        )


class RecordedFutureDerivedColumnsUpdateRequest(BaseModel):
    """WHOIS/DNS columns extracted from RecordedFuture panels (matches runner RF adapter)."""

    domain_registered: Optional[bool] = None
    whois_registrar: Optional[str] = None
    whois_creation_date: Optional[str] = None
    whois_expiration_date: Optional[str] = None
    whois_registrant_name: Optional[str] = None
    whois_registrant_country: Optional[str] = None
    whois_admin_email: Optional[str] = None
    dns_a_records: Optional[List[str]] = None
    dns_mx_records: Optional[List[str]] = None


@router.patch("/typosquat/{finding_id}/recordedfuture-derived-columns", response_model=Dict[str, Any])
async def update_typosquat_recordedfuture_derived_columns(
    finding_id: str,
    request: RecordedFutureDerivedColumnsUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Patch typosquat root columns populated from RecordedFuture WHOIS/DNS enrichment."""
    try:
        logger.info(f"Updating RecordedFuture-derived columns for finding: {finding_id}")

        existing_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        if not existing_finding:
            raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

        update_data = request.model_dump(exclude_none=True)
        if not update_data:
            return {
                "status": "success",
                "message": "No column updates provided",
                "finding_id": finding_id,
            }

        success = await TyposquatFindingsRepository.update_typosquat_domain(finding_id, update_data)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update derived columns for finding {finding_id}",
            )

        return {
            "status": "success",
            "message": f"RecordedFuture-derived columns updated for finding {finding_id}",
            "finding_id": finding_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating RecordedFuture-derived columns for finding {finding_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update derived columns: {str(e)}",
        )

# ===== DASHBOARD ENDPOINTS =====

_DASHBOARD_CUSTOM_RANGE_MAX_DAYS = 731


@router.get("/typosquat/dashboard/kpis", response_model=Dict[str, Any])
async def get_typosquat_dashboard_kpis(
    days: int = Query(30, description="Number of days to look back for trends"),
    single_date: Optional[str] = Query(None, description="Single date for analysis (YYYY-MM-DD format)"),
    date_from: Optional[str] = Query(None, description="Custom range start (YYYY-MM-DD), inclusive; use with date_to"),
    date_to: Optional[str] = Query(None, description="Custom range end (YYYY-MM-DD), inclusive; use with date_from"),
    program: Optional[str] = Query(None, description="Filter by program name"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get KPIs for typosquat domain dashboard"""
    try:
        parsed_date_from: Optional[str] = None
        parsed_date_to: Optional[str] = None
        if (date_from is not None and str(date_from).strip()) or (date_to is not None and str(date_to).strip()):
            df_raw = date_from.strip() if date_from else None
            dt_raw = date_to.strip() if date_to else None
            if (df_raw and not dt_raw) or (dt_raw and not df_raw):
                raise HTTPException(
                    status_code=422,
                    detail="Both date_from and date_to are required for a custom range",
                )
            try:
                d_from = datetime.strptime(df_raw, "%Y-%m-%d").date()
                d_to = datetime.strptime(dt_raw, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail="date_from and date_to must be valid dates in YYYY-MM-DD format",
                )
            if d_from > d_to:
                raise HTTPException(
                    status_code=422,
                    detail="date_from must be on or before date_to",
                )
            span_inclusive = (d_to - d_from).days + 1
            if span_inclusive > _DASHBOARD_CUSTOM_RANGE_MAX_DAYS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Custom date range cannot exceed {_DASHBOARD_CUSTOM_RANGE_MAX_DAYS} days",
                )
            parsed_date_from = d_from.isoformat()
            parsed_date_to = d_to.isoformat()

        # Check user program access
        accessible_programs = get_user_accessible_programs(current_user)
        if accessible_programs and program and program not in accessible_programs:
            raise HTTPException(status_code=403, detail="Access denied to this program")

        # Get dashboard data from repository
        dashboard_data = await TyposquatFindingsRepository.get_dashboard_kpis(
            days=days,
            single_date=single_date,
            program=program,
            accessible_programs=accessible_programs,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
        )

        filters: Dict[str, Any] = {
            "days": days,
            "single_date": single_date,
            "program": program,
        }
        if parsed_date_from and parsed_date_to:
            filters["date_from"] = parsed_date_from
            filters["date_to"] = parsed_date_to

        return {
            "status": "success",
            "data": dashboard_data,
            "filters": filters,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting typosquat dashboard KPIs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== BATCH PROCESSING ENDPOINTS =====

@router.post("/apex-domains/process-queued", response_model=Dict[str, Any])
async def process_queued_apex_domains(current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """Process all queued apex domains for batch typosquat analysis.

    This endpoint processes any apex domains that have been queued for batch processing.
    It's designed to be called periodically to ensure no domains get stuck in the queue.
    """
    try:
        logger.info("Processing queued apex domains for batch analysis")

        # Process all queued domains (non-blocking operation)
        await TyposquatFindingsRepository.process_all_queued_domains()

        return {
            "status": "success",
            "message": "Queued apex domains processing initiated"
        }

    except Exception as e:
        logger.error(f"Error processing queued apex domains: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== AI ANALYSIS ENDPOINTS =====

class AIAnalyzeBatchRequest(BaseModel):
    program_name: str = Field(..., description="Program to analyze findings for")
    batch_size: int = Field(50, ge=1, le=500, description="Max findings to analyze")
    concurrency: int = Field(3, ge=1, le=10, description="Parallel Ollama requests")
    model: Optional[str] = Field(None, description="Override Ollama model")
    reanalyze_after_days: Optional[int] = Field(None, ge=1, description="Re-analyze findings older than N days")
    apply_auto_actions: bool = Field(False, description="Apply auto-actions after analysis based on program settings")


@router.post("/typosquat/ai-analysis/batch", response_model=Dict[str, Any])
async def create_ai_analysis_batch_job(
    request: AIAnalysisBatchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Create a background job to run AI analysis on typosquat findings.

    Submits to K8s runner for load isolation. Check job status via /jobs/{job_id}/status.
    """
    if not request.finding_ids:
        raise HTTPException(status_code=400, detail="No finding IDs provided")

    findings = []
    for finding_id in request.finding_ids:
        finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
        if not finding:
            logger.warning(f"Typosquat finding {finding_id} not found, skipping")
            continue
        finding_program = finding.get("program_name")
        if finding_program:
            accessible = get_user_accessible_programs(current_user)
            if accessible and finding_program not in accessible:
                continue
        findings.append(finding)

    if not findings:
        raise HTTPException(status_code=404, detail="No valid typosquat findings found")

    job_id = str(uuid.uuid4())
    job_payload = {
        "job_id": job_id,
        "job_type": "ai_analysis_batch",
        "finding_ids": request.finding_ids,
        "user_id": getattr(current_user, "id", "unknown"),
        "model": request.model,
        "force": request.force,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    job_created = await JobRepository.create_job(job_id, "ai_analysis_batch", job_payload)
    if not job_created:
        raise HTTPException(status_code=500, detail="Failed to create job status record")

    try:
        job_submission_service = JobSubmissionService()
        job_submission_service.create_ai_analysis_batch_job(job_id, job_payload)
        logger.info(f"Submitted AI analysis batch job {job_id} to Kubernetes")
    except Exception as e:
        logger.error(f"Failed to submit job to Kubernetes: {str(e)}")
        await JobRepository.update_job_status(job_id, "failed", 0, f"Failed to submit: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")

    return {
        "status": "processing",
        "message": f"AI analysis batch job started for {len(request.finding_ids)} findings",
        "job_id": job_id,
        "finding_ids": request.finding_ids,
    }


@router.post("/typosquat/ai-analyze/{finding_id}", response_model=Dict[str, Any])
async def ai_analyze_finding(
    finding_id: str,
    force: bool = Query(False, description="Re-analyze even if already analyzed"),
    model: Optional[str] = Query(None, description="Override Ollama model"),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Trigger AI analysis for a single typosquat finding.

    Creates a runner job for load isolation. Returns job_id for status tracking.
    """
    current_finding = await TyposquatFindingsRepository.get_typosquat_by_id(finding_id)
    if not current_finding:
        raise HTTPException(status_code=404, detail=f"Typosquat finding {finding_id} not found")

    if current_finding.get("ai_analysis") and not force:
        return {
            "status": "already_analyzed",
            "finding_id": finding_id,
            "ai_analysis": current_finding["ai_analysis"],
        }

    # Delegate to batch endpoint (single finding)
    from models.job import AIAnalysisBatchRequest
    request = AIAnalysisBatchRequest(
        finding_ids=[finding_id],
        model=model,
        force=force,
    )
    result = await create_ai_analysis_batch_job(request, current_user)
    result["finding_id"] = finding_id
    return result


@router.post("/typosquat/ai-analyze-batch", response_model=Dict[str, Any])
async def ai_analyze_batch(
    request: AIAnalyzeBatchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Trigger batch AI analysis for unanalyzed findings in a program.

    Creates a runner job for load isolation. Use apply_auto_actions endpoint
    after job completes if auto-actions are needed.
    """
    accessible = get_user_accessible_programs(current_user)
    if not current_user.is_superuser and "admin" not in current_user.roles:
        if accessible and request.program_name not in accessible:
            raise HTTPException(status_code=403, detail=f"Access denied to program '{request.program_name}'")

    program = await ProgramRepository.get_program_by_name(request.program_name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{request.program_name}' not found")

    program_id = str(program["id"]) if isinstance(program.get("id"), str) else str(program["id"])
    finding_ids = await TyposquatFindingsRepository.get_unanalyzed_ai_finding_ids(
        program_id=program_id,
        batch_size=request.batch_size,
        reanalyze_after_days=request.reanalyze_after_days,
    )

    if not finding_ids:
        return {
            "status": "success",
            "message": "No unanalyzed findings for this program",
            "program_name": request.program_name,
            "finding_count": 0,
        }

    batch_request = AIAnalysisBatchRequest(
        finding_ids=finding_ids,
        model=request.model,
        force=bool(request.reanalyze_after_days),
    )
    result = await create_ai_analysis_batch_job(batch_request, current_user)
    result["program_name"] = request.program_name
    result["batch_size"] = request.batch_size
    if request.apply_auto_actions:
        result["note"] = "Run apply_auto_actions endpoint after job completes for auto-dismiss/monitor"
    return result

