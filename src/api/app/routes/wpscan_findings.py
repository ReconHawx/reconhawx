from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Dict, Any, Optional, List, Union
from repository import WPScanFindingsRepository
from repository import ProgramRepository
import logging
from pydantic import BaseModel, Field
from auth.dependencies import filter_by_user_programs, require_admin_or_manager, get_current_user_from_middleware, get_user_accessible_programs
from models.user_postgres import UserResponse
from services.unified_findings_processor import unified_findings_processor

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryFilter(BaseModel):
    filter: Dict[str, Any]
    limit: Optional[int] = None
    skip: Optional[int] = 0
    sort: Optional[Dict[str, int]] = None

# Pydantic model for WPScan processing response
class WPScanProcessingResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    processing_mode: str  # Always "unified_async"
    summary: Dict[str, Any]

@router.post("/wpscan", include_in_schema=True, response_model=WPScanProcessingResponse)
async def receive_wpscan_findings(request: Request):
    """
    Receive WPScan findings from workflow runner using unified processing.

    Dedicated endpoint for WPScan findings that:
    - Processes only WPScan findings asynchronously
    - Uses intelligent batching based on actual load
    - Publishes events uniformly
    """
    try:
        data = await request.json()
        logger.info(f"Received WPScan data with keys: {list(data.keys())}")

        # Validate required fields
        program_name = data.get("program_name")
        if not program_name:
            raise HTTPException(status_code=400, detail="program_name is required")

        # Extract and prepare WPScan data only
        wpscan_data = await _extract_wpscan_data(data)

        # Calculate total WPScan count
        total_wpscan = len(wpscan_data.get("wpscan", []))
        logger.info(f"Extracted {total_wpscan} WPScan findings")

        if total_wpscan == 0:
            raise HTTPException(status_code=400, detail="No WPScan findings provided for processing")

        # Use unified findings processor - always async, never blocks API
        job_id = await unified_findings_processor.process_findings_unified(
            wpscan_data, program_name
        )

        logger.info(f"Started unified WPScan processing job {job_id} with {total_wpscan} findings")

        return WPScanProcessingResponse(
            status="processing",
            message=f"Started unified processing of {total_wpscan} WPScan findings",
            job_id=job_id,
            processing_mode="unified_async",
            summary={
                "total_findings": total_wpscan,
                "finding_types": {"wpscan": total_wpscan},
                "processing_method": "unified_async"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating WPScan processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start WPScan processing: {str(e)}")

async def _extract_wpscan_data(data: Dict[str, Any]) -> Dict[str, List]:
    """Extract and prepare WPScan findings data from the request"""
    wpscan_data = {"wpscan": []}
    
    if "findings" in data:
        findings = data["findings"]
        
        # Process WPScan findings
        if "wpscan" in findings:
            logger.info("Processing WPScan findings")
            for finding in findings["wpscan"]:
                if isinstance(finding, dict):
                    # Add program name to finding if available
                    if "program_name" in data:
                        finding["program_name"] = data["program_name"]
                    try:
                        wpscan_data["wpscan"].append(finding)
                    except Exception as e:
                        logger.error(f"Error processing WPScan finding: {str(e)}")
                        logger.error(f"Finding data: {finding}")
                        continue
    
    return wpscan_data

@router.post("/wpscan/distinct/{field_name}", response_model=List[str])
async def get_wpscan_distinct_typed(
    field_name: str,
    request: Optional[Dict[str, Any]] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    try:
        # Resolve requested program(s) from typed body or legacy filter body
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

        # Enforce program scoping
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

        values = await WPScanFindingsRepository.get_distinct_wpscan_values_typed(field_name, programs)
        return values
    except ValueError as ve:
        logger.error(f"Value error getting WPScan distinct '{field_name}': {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting WPScan distinct '{field_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving distinct WPScan values for '{field_name}'")

# Typed WPScan search request
class WPScanSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Fuzzy search on title, item_name, or description")
    exact_match: Optional[str] = Field(None, description="Exact match on item_name")
    severity: Optional[str] = Field(None, description="Filter by severity")
    item_type: Optional[str] = Field(None, description="Filter by item_type (wordpress/plugin/theme)")
    item_name_contains: Optional[str] = Field(None, description="Substring match on item_name")
    item_name_exact: Optional[str] = Field(None, description="Exact match on item_name")
    hostname_contains: Optional[str] = Field(None, description="Substring match on hostname")
    cve_ids_exact: Optional[str] = Field(None, description="Exact match on any value in cve_ids array")
    cve_ids_contains: Optional[str] = Field(None, description="Substring match on any value in cve_ids array")
    program: Optional[Union[List[str], str]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Optional[str] = Field("created_at")
    sort_dir: Optional[str] = Field("desc")
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/wpscan/search", response_model=Dict[str, Any])
async def search_wpscan_typed(request: WPScanSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
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
                    "severity_distribution": {},
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
                        "severity_distribution": {},
                        "items": [],
                    }
            else:
                programs = allowed

        skip = (request.page - 1) * request.page_size

        result = await WPScanFindingsRepository.search_wpscan_typed(
            search=request.search,
            exact_match=request.exact_match,
            severity=request.severity,
            item_type=request.item_type,
            item_name_contains=request.item_name_contains,
            item_name_exact=request.item_name_exact,
            hostname_contains=request.hostname_contains,
            cve_ids_exact=request.cve_ids_exact,
            cve_ids_contains=request.cve_ids_contains,
            programs=programs,
            sort_by=request.sort_by or "created_at",
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
            "severity_distribution": result.get("severity_distribution", {}),
            "items": result.get("items", []),
        }
    except Exception as e:
        logger.error(f"Error executing typed WPScan search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed WPScan search: {str(e)}")

@router.get("/wpscan", response_model=Dict[str, Any])
async def get_all_wpscan(
    severity: Optional[str] = None,
    id: Optional[str] = Query(None),
    limit: int = 1000000,
    skip: int = 0,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    try:
        # If an id is provided, return a single finding by id
        if id:
            finding = await WPScanFindingsRepository.get_wpscan_by_id(id)
            if not finding:
                raise HTTPException(status_code=404, detail=f"WPScan finding {id} not found")
            finding_program = finding.get("program_name")
            if finding_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and finding_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"WPScan finding {id} not found")
            return {"status": "success", "data": finding}

        # Create a filter based on user program permissions
        base_filter = {}
        if severity:
            base_filter["severity"] = severity
        
        filtered_query = filter_by_user_programs(base_filter, current_user)
        
        # If user has no program access, return empty result
        if "program_name" in filtered_query and filtered_query["program_name"].get("$in") == []:
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
        
        # Use query-based filtering to get WPScan user has access to
        total_count = await WPScanFindingsRepository.get_wpscan_query_count(filtered_query)
        wpscan_findings = await WPScanFindingsRepository.execute_wpscan_query(
            filtered_query,
            limit=limit,
            skip=skip,
            sort={"updated_at": -1}
        )
        
        # Calculate pagination metadata
        page_size = limit if limit else len(wpscan_findings)
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
            "items": wpscan_findings
        }
    except Exception as e:
        logger.error(f"Error listing WPScan findings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Define the expected response model for stats
class WPScanSeverityStats(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0

# GET endpoint for DETAILED program stats counts
@router.get("/wpscan/stats/{program_name}", response_model=WPScanSeverityStats)
async def get_program_wpscan_stats_detailed_get(program_name: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Get detailed counts of WPScan findings for a specific program.
    Provides breakdowns by severity.
    """
    try:
        # Check if program exists first
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")
        
        # Check if user has access to this program
        accessible_programs = get_user_accessible_programs(current_user)
        if accessible_programs and program_name not in accessible_programs:
            raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")

        # Base filter is just the program name
        combined_filter = {"program_name": program_name}
        detailed_stats = await WPScanFindingsRepository.get_wpscan_stats_by_severity(combined_filter)
        return detailed_stats

    except HTTPException:
        raise
    except ValueError as ve:
        logger.error(f"Value error calculating program WPScan stats for {program_name}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error calculating program WPScan stats for {program_name}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating program WPScan stats: {str(e)}"
        )

@router.get("/wpscan/{finding_id}", response_model=Dict[str, Any])
async def get_wpscan_finding_by_id(finding_id: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """Get a single WPScan finding by its ID"""
    try:
        finding = await WPScanFindingsRepository.get_wpscan_by_id(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail=f"WPScan finding {finding_id} not found")
        
        # Check if user has access to this finding's program
        finding_program = finding.get("program_name")
        if finding_program:
            accessible_programs = get_user_accessible_programs(current_user)
            if accessible_programs and finding_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"WPScan finding {finding_id} not found")
        
        return {
            "status": "success",
            "data": finding,
            "items": [finding]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting WPScan finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Pydantic models for update requests
class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="New status value")
    assigned_to: Optional[str] = Field(None, description="User assigned to investigate")

class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

# Status update endpoints
@router.put("/wpscan/{finding_id}/status", response_model=Dict[str, Any])
async def update_wpscan_status(finding_id: str, request: StatusUpdateRequest):
    """Update the status and optionally the assigned user for a WPScan finding"""
    try:
        # Validate status value
        valid_statuses = ['new', 'investigating', 'confirmed', 'resolved', 'false_positive']
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{request.status}'. Must be one of: {', '.join(valid_statuses)}"
            )
        
        # Prepare update data
        update_data = {"status": request.status}
        if request.assigned_to is not None:
            update_data["assigned_to"] = request.assigned_to
        
        # Update the finding
        success = await WPScanFindingsRepository.update_wpscan_finding(finding_id, update_data)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"WPScan finding {finding_id} not found")
        
        # Return updated data
        updated_finding = await WPScanFindingsRepository.get_wpscan_by_id(finding_id)
        
        if not updated_finding:
            raise HTTPException(status_code=404, detail=f"WPScan finding {finding_id} not found after update")
        
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
        logger.error(f"Error updating WPScan status {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Notes update endpoints
@router.put("/wpscan/{finding_id}/notes", response_model=Dict[str, Any])
async def update_wpscan_notes(finding_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for a WPScan finding"""
    try:
        # Update the finding
        update_data = {"notes": request.notes}
        success = await WPScanFindingsRepository.update_wpscan_finding(finding_id, update_data)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"WPScan finding {finding_id} not found")
        
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
        logger.error(f"Error updating WPScan notes {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/wpscan/batch", response_model=Dict[str, Any])
async def delete_wpscan_findings_batch(
    finding_ids: List[str], 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple WPScan findings by their IDs"""
    try:
        if not finding_ids:
            raise HTTPException(status_code=400, detail="No finding IDs provided")
        
        result = await WPScanFindingsRepository.delete_wpscan_findings_batch(finding_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for WPScan findings",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting WPScan findings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/wpscan/{finding_id}", response_model=Dict[str, Any])
async def delete_wpscan_finding(finding_id: str, current_user: UserResponse = Depends(require_admin_or_manager)):
    """Delete a WPScan finding by its ID"""
    try:
        deleted = await WPScanFindingsRepository.delete_wpscan_finding(finding_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"WPScan finding {finding_id} not found")
        
        return {
            "status": "success",
            "message": f"WPScan finding {finding_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting WPScan finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Pydantic models for WPScan findings import functionality
class WPScanFindingImportData(BaseModel):
    url: str = Field(..., description="Target URL")
    item_name: str = Field(..., description="Item name (plugin/theme name or 'WordPress')")
    item_type: str = Field(..., description="Item type (wordpress/plugin/theme)")
    vulnerability_type: Optional[str] = Field(None, description="Vulnerability type")
    severity: Optional[str] = Field(None, description="Finding severity")
    title: Optional[str] = Field(None, description="Finding title")
    description: Optional[str] = Field(None, description="Finding description")
    fixed_in: Optional[str] = Field(None, description="Fixed in version")
    references: Optional[List[str]] = Field(None, description="References")
    cve_ids: Optional[List[str]] = Field(None, description="CVE IDs")
    enumeration_data: Optional[Dict[str, Any]] = Field(None, description="Enumeration data")
    hostname: Optional[str] = Field(None, description="Hostname")
    port: Optional[int] = Field(None, description="Port number")
    scheme: Optional[str] = Field(None, description="URL scheme")
    program_name: str = Field(..., description="Program name")
    notes: Optional[str] = Field(None, description="Investigation notes")

class WPScanFindingImportRequest(BaseModel):
    findings: List[WPScanFindingImportData] = Field(..., description="List of WPScan findings to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing findings")
    validate_findings: Optional[bool] = Field(True, description="Whether to validate finding data")

@router.post("/wpscan/import", response_model=Dict[str, Any])
async def import_wpscan_findings(
    request: WPScanFindingImportRequest, 
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Import multiple WPScan findings from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of WPScan finding objects and imports them into the database.
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
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if finding_data.program_name and finding_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import finding {finding_data.item_name} to unauthorized program {finding_data.program_name}")
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
                finding_dict = finding_data.model_dump()
                
                # Remove None values, empty strings, and string "null" values
                finding_dict = {k: v for k, v in finding_dict.items() if v is not None and v != "" and v != "null"}
                
                finding_id = await WPScanFindingsRepository.create_or_update_wpscan_finding(finding_dict)
                if finding_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated finding: {finding_dict.get('item_name')} for {finding_dict.get('url')}")
                else:
                    errors.append(f"Failed to create/update finding: {finding_dict.get('item_name')} for {finding_dict.get('url')}")
                        
            except Exception as e:
                error_msg = f"Error processing finding {finding_data.item_name} for {finding_data.url}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create program if it doesn't exist and findings were processed
        if imported_count > 0:
            for finding_data in allowed_findings:
                if finding_data.program_name:
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
            response_data["data"]["errors"] = errors[:10]
            response_data["data"]["error_count"] = len(errors)
            
        # Adjust status if there were significant errors
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no findings were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        logger.info(f"WPScan findings import completed by user {current_user.username}: {response_data['message']}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in WPScan findings import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing WPScan findings: {str(e)}"
        )

@router.get("/job/{job_id}", response_model=Dict[str, Any])
async def get_findings_job_status(job_id: str):
    """Get the status of a unified findings processing job"""
    try:
        job_status = await unified_findings_processor.get_job_status(job_id)

        if not job_status:
            raise HTTPException(status_code=404, detail=f"Findings processing job {job_id} not found")

        return job_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting findings job status for {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
