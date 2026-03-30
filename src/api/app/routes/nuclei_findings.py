from fastapi import APIRouter, HTTPException, Query, Depends, Request, BackgroundTasks
from typing import Dict, Any, Optional, List, Union
from models.findings import NucleiFinding
from repository import NucleiFindingsRepository
from repository import ProgramRepository
from urllib.parse import urlparse
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

# Pydantic model for nuclei processing response
class NucleiProcessingResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    processing_mode: str  # Always "unified_async"
    summary: Dict[str, Any]

@router.post("/nuclei", include_in_schema=True, response_model=NucleiProcessingResponse)
async def receive_nuclei_findings(request: Request, background_tasks: BackgroundTasks):
    """
    Receive nuclei findings from workflow runner using unified processing.

    Dedicated endpoint for nuclei findings that:
    - Processes only nuclei findings asynchronously
    - Uses intelligent batching based on actual load
    - Publishes events uniformly

    Supports workflow integration by accepting optional workflow context:
    - workflow_id: ID of the workflow these findings belong to
    - execution_id: ID of the workflow execution
    - step_name: Name of the workflow step
    """
    try:
        data = await request.json()
        logger.info(f"Received nuclei data with keys: {list(data.keys())}")

        # Validate required fields
        program_name = data.get("program_name")
        if not program_name:
            raise HTTPException(status_code=400, detail="program_name is required")

        # Extract and prepare nuclei data only
        nuclei_data = await _extract_nuclei_data(data)

        # Calculate total nuclei count
        total_nuclei = len(nuclei_data.get("nuclei", []))
        logger.info(f"Extracted {total_nuclei} nuclei findings")

        if total_nuclei == 0:
            raise HTTPException(status_code=400, detail="No nuclei findings provided for processing")

        # Use unified findings processor - always async, never blocks API
        job_id = await unified_findings_processor.process_findings_unified(
            nuclei_data, program_name
        )

        logger.info(f"Started unified nuclei processing job {job_id} with {total_nuclei} findings")

        return NucleiProcessingResponse(
            status="processing",
            message=f"Started unified processing of {total_nuclei} nuclei findings",
            job_id=job_id,
            processing_mode="unified_async",
            summary={
                "total_findings": total_nuclei,
                "finding_types": {"nuclei": total_nuclei},
                "processing_method": "unified_async"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating nuclei processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start nuclei processing: {str(e)}")

async def _extract_nuclei_data(data: Dict[str, Any]) -> Dict[str, List]:
    """Extract and prepare nuclei findings data from the request"""
    nuclei_data = {"nuclei": []}
    
    if "findings" in data:
        findings = data["findings"]
        
        # Process nuclei findings
        if "nuclei" in findings:
            logger.info("Processing nuclei findings")
            for finding in findings["nuclei"]:
                if isinstance(finding, dict):
                    # Add program name to finding if available
                    if "program_name" in data:
                        finding["program_name"] = data["program_name"]
                    try:
                        # Map template_name to name if name is not present
                        if "template_name" in finding and "name" not in finding:
                            finding["name"] = finding["template_name"]
                        nuclei_data["nuclei"].append(finding)
                    except Exception as e:
                        logger.error(f"Error processing nuclei finding: {str(e)}")
                        logger.error(f"Finding data: {finding}")
                        continue
    
    return nuclei_data

@router.post("/nuclei/distinct/{field_name}", response_model=List[str])
async def get_nuclei_distinct_typed(
    field_name: str,
    request: Optional[Dict[str, Any]] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    try:
        # Resolve requested program(s) from typed body or legacy filter body
        requested_programs: Optional[List[str]] = None
        if request:
            # Typed format: { program: 'x' | ['x','y'] }
            program_field = request.get("program")
            if isinstance(program_field, str) and program_field.strip():
                requested_programs = [program_field.strip()]
            elif isinstance(program_field, list):
                requested_programs = [p for p in program_field if isinstance(p, str) and p.strip()]

            # Legacy format: { filter: { program_name: 'x' | ['x','y'] } }
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

        values = await NucleiFindingsRepository.get_distinct_nuclei_values_typed(field_name, programs)
        return values
    except ValueError as ve:
        logger.error(f"Value error getting nuclei distinct '{field_name}': {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting nuclei distinct '{field_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving distinct nuclei values for '{field_name}'")

# Typed nuclei search request
class NucleiSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Fuzzy search on finding name")
    exact_match: Optional[str] = Field(None, description="Exact match on finding name")
    severity: Optional[str] = Field(None, description="Filter by severity")
    tags: Optional[str] = Field(None, description="Filter by tags")
    tags_include: Optional[List[str]] = Field(None, description="Include findings with any of these tags")
    tags_exclude: Optional[List[str]] = Field(None, description="Exclude findings with any of these tags")
    template_contains: Optional[str] = Field(None, description="Substring match on template_id")
    template_exact: Optional[str] = Field(None, description="Exact match on template_id")
    hostname_contains: Optional[str] = Field(None, description="Substring match on hostname")
    extracted_results_exact: Optional[str] = Field(None, description="Exact match on any value in extracted_results array")
    extracted_results_contains: Optional[str] = Field(None, description="Substring match on any value in extracted_results array")
    program: Optional[Union[List[str], str]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Optional[str] = Field("created_at")
    sort_dir: Optional[str] = Field("desc")
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/nuclei/search", response_model=Dict[str, Any])
async def search_nuclei_typed(request: NucleiSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
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

        result = await NucleiFindingsRepository.search_nuclei_typed(
            search=request.search,
            exact_match=request.exact_match,
            severity=request.severity,
            tags=request.tags,
            tags_include=request.tags_include,
            tags_exclude=request.tags_exclude,
            template_contains=request.template_contains,
            template_exact=request.template_exact,
            hostname_contains=request.hostname_contains,
            extracted_results_exact=request.extracted_results_exact,
            extracted_results_contains=request.extracted_results_contains,
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
        logger.error(f"Error executing typed nuclei search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed nuclei search: {str(e)}")

@router.post("/nuclei", response_model=NucleiFinding)
async def create_nuclei_finding(
    finding: NucleiFinding
):
    """Create a new nuclei finding or update if exists with merged data"""
    try:
        # Extract hostname from URL if type is http
        if finding.type == "http" and finding.url:
            finding.hostname = urlparse(finding.url).hostname
        else:
            finding.hostname = finding.url.split(":")[0] if finding.url else None

        # Determine protocol and service
        if finding.type == "http":
            finding.protocol = "tcp"
        elif finding.type == "tcp":
            finding.protocol = "tcp"
            if finding.template_id == "openssh-detect":
                finding.scheme = "ssh"

        logger.info(f"Creating or updating nuclei finding for URL: {finding.url}")
        
        # Convert Pydantic model to dictionary for repository
        finding_dict = finding.model_dump()
        logger.debug(f"Finding dict: {finding_dict}")
        # Store the nuclei finding
        inserted_id = await NucleiFindingsRepository.create_or_update_nuclei_finding(finding_dict)
        
        if not inserted_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create nuclei finding - no ID returned"
            )
            
        # Fetch and return the created finding
        created_finding = await NucleiFindingsRepository.get_nuclei_by_id(inserted_id)
        if not created_finding:
            raise HTTPException(
                status_code=404,
                detail=f"Nuclei finding not found after creation with ID {inserted_id}"
            )
            
        logger.info(f"Successfully created/updated nuclei finding with ID: {inserted_id}")
        return NucleiFinding(**created_finding)
        
    except Exception as e:
        logger.error(f"Error in create_nuclei_finding: {str(e)}")
        logger.error(f"Finding data: {finding.model_dump()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create/update nuclei finding: {str(e)}"
        )

@router.post("/nuclei/create-or-update", response_model=NucleiFinding)
async def create_or_update_nuclei_finding(
    finding: NucleiFinding
):
    """Create a new nuclei finding or update if exists with merged data"""
    try:
        # Extract hostname from URL if type is http
        if finding.type == "http" and finding.url:
            finding.hostname = urlparse(finding.url).hostname
        else:
            finding.hostname = finding.url.split(":")[0] if finding.url else None

        # Determine protocol and service
        if finding.type == "http":
            finding.protocol = "tcp"
        elif finding.type == "tcp":
            finding.protocol = "tcp"
            if finding.template_id == "openssh-detect":
                finding.scheme = "ssh"

        logger.info(f"Creating or updating nuclei finding for URL: {finding.url}")
        
        # Convert Pydantic model to dictionary for repository
        finding_dict = finding.model_dump()
        logger.debug(f"Finding dict: {finding_dict}")
        
        # Use create_or_update function
        inserted_id = await NucleiFindingsRepository.create_or_update_nuclei_finding(finding_dict)
        
        if not inserted_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create/update nuclei finding - no ID returned"
            )
            
        # Fetch and return the created/updated finding
        created_finding = await NucleiFindingsRepository.get_nuclei_by_id(inserted_id)
        if not created_finding:
            raise HTTPException(
                status_code=404,
                detail=f"Nuclei finding not found after create/update with ID {inserted_id}"
            )
            
        logger.info(f"Successfully created/updated nuclei finding with ID: {inserted_id}")
        return NucleiFinding(**created_finding)
        
    except Exception as e:
        logger.error(f"Error in create_or_update_nuclei_finding: {str(e)}")
        logger.error(f"Finding data: {finding.model_dump()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create/update nuclei finding: {str(e)}"
        )

# Pydantic models for nuclei findings import functionality
class NucleiFindingImportData(BaseModel):
    url: str = Field(..., description="Target URL")
    template_id: str = Field(..., description="Nuclei template ID")
    template_url: Optional[str] = Field(None, description="Template URL")
    template_path: Optional[str] = Field(None, description="Template file path")
    name: str = Field(..., description="Finding name")
    severity: str = Field(..., description="Finding severity")
    type: str = Field(..., description="Finding type")
    tags: Optional[List[str]] = Field(None, description="Finding tags")
    description: Optional[str] = Field(None, description="Finding description")
    matched_at: Optional[str] = Field(None, description="When the finding was matched")
    matcher_name: Optional[str] = Field(None, description="Matcher name")
    ip: Optional[str] = Field(None, description="IP address")
    hostname: Optional[str] = Field(None, description="Hostname")
    port: Optional[int] = Field(None, description="Port number")
    scheme: Optional[str] = Field(None, description="URL scheme")
    protocol: Optional[str] = Field(None, description="Protocol")
    matched_line: Optional[str] = Field(None, description="Matched line content")
    extracted_results: Optional[List[str]] = Field(None, description="Extracted results")
    info: Optional[Dict[str, Any]] = Field(None, description="Additional info data")
    program_name: str = Field(..., description="Program name")
    notes: Optional[str] = Field(None, description="Investigation notes")

class NucleiFindingImportRequest(BaseModel):
    findings: List[NucleiFindingImportData] = Field(..., description="List of nuclei findings to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing findings")
    validate_findings: Optional[bool] = Field(True, description="Whether to validate finding data")

@router.post("/nuclei/import", response_model=Dict[str, Any])
async def import_nuclei_findings(
    request: NucleiFindingImportRequest, 
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Import multiple nuclei findings from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of nuclei finding objects and imports them into the database.
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
                    logger.warning(f"User {current_user.username} attempted to import finding {finding_data.name} to unauthorized program {finding_data.program_name}")
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
                # Convert Pydantic model to dict for repository
                finding_dict = {
                    "url": finding_data.url.strip(),
                    "template_id": finding_data.template_id.strip(),
                    "template_url": finding_data.template_url,
                    "template_path": finding_data.template_path,
                    "name": finding_data.name.strip(),
                    "severity": finding_data.severity.strip().lower(),
                    "type": finding_data.type.strip().lower(),
                    "tags": finding_data.tags or [],
                    "description": finding_data.description,
                    "matched_at": finding_data.matched_at,
                    "matcher_name": finding_data.matcher_name,
                    "ip": finding_data.ip,
                    "hostname": finding_data.hostname,
                    "port": finding_data.port,
                    "scheme": finding_data.scheme,
                    "protocol": finding_data.protocol,
                    "matched_line": finding_data.matched_line,
                    "extracted_results": finding_data.extracted_results or [],
                    "info": finding_data.info or {},
                    "program_name": finding_data.program_name.strip(),
                    "notes": finding_data.notes
                }
                
                # Remove None values, empty strings, and string "null" values, but keep empty lists and valid lists
                finding_dict = {k: v for k, v in finding_dict.items() if v is not None and v != "" and v != "null"}
                
                # Use create_or_update_nuclei_finding which handles merging automatically
                finding_id = await NucleiFindingsRepository.create_or_update_nuclei_finding(finding_dict)
                if finding_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated finding: {finding_dict['name']} for {finding_dict['url']}")
                else:
                    errors.append(f"Failed to create/update finding: {finding_dict['name']} for {finding_dict['url']}")
                        
            except Exception as e:
                error_msg = f"Error processing finding {finding_data.name} for {finding_data.url}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create program if it doesn't exist and findings were processed
        if imported_count > 0:
            for finding_data in allowed_findings:
                if finding_data.program_name:
                    # Check if program exists, if not create it
                    from repository import ProgramRepository
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
        
        logger.info(f"Nuclei findings import completed by user {current_user.username}: {response_data['message']}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in nuclei findings import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing nuclei findings: {str(e)}"
        )

@router.get("/nuclei", response_model=Dict[str, Any])
async def get_all_nuclei(
    severity: Optional[str] = None,
    id: Optional[str] = Query(None),
    limit: int = 1000000,
    skip: int = 0,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    try:
        # If an id is provided, return a single finding by id
        if id:
            finding = await NucleiFindingsRepository.get_nuclei_by_id(id)
            if not finding:
                raise HTTPException(status_code=404, detail=f"Nuclei finding {id} not found")
            finding_program = finding.get("program_name")
            if finding_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and finding_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"Nuclei finding {id} not found")
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
        
        # Use query-based filtering to get nuclei user has access to
        total_count = await NucleiFindingsRepository.get_nuclei_query_count(filtered_query)
        nuclei_findings = await NucleiFindingsRepository.execute_nuclei_query(
            filtered_query,
            limit=limit,
            skip=skip,
            sort={"updated_at": -1}
        )
        
        # Calculate pagination metadata
        page_size = limit if limit else len(nuclei_findings)
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
            "items": nuclei_findings
        }
    except Exception as e:
        logger.error(f"Error listing nuclei findings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Define the expected response model for stats
class NucleiSeverityStats(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0

# GET endpoint for DETAILED program stats counts
@router.get("/nuclei/stats/{program_name}", response_model=NucleiSeverityStats)
async def get_program_nuclei_stats_detailed_get(program_name: str, current_user: UserResponse = Depends(get_current_user_from_middleware)): # Removed asset_type param
    """
    Get detailed counts of nuclei for a specific program.
    Provides breakdowns for resolved/unresolved domains/IPs and root/non-root URLs.
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
        detailed_stats = await NucleiFindingsRepository.get_nuclei_stats_by_severity(combined_filter)
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

@router.get("/nuclei/{finding_id}", response_model=Dict[str, Any])
async def get_nuclei_finding_by_id(finding_id: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """Get a single nuclei finding by its ID"""
    try:
        finding = await NucleiFindingsRepository.get_nuclei_by_id(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail=f"Nuclei finding {finding_id} not found")
        
        # Check if user has access to this finding's program
        finding_program = finding.get("program_name")
        if finding_program:
            accessible_programs = get_user_accessible_programs(current_user)
            # For superusers/admins, accessible_programs is empty (meaning no restrictions)
            if accessible_programs and finding_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"Nuclei finding {finding_id} not found")
        
        return {
            "status": "success",
            "data": finding,  # Keep data field for backward compatibility
            "items": [finding]  # Keep items field for consistency with other endpoints
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting nuclei finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Pydantic models for update requests
class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="New status value")
    assigned_to: Optional[str] = Field(None, description="User assigned to investigate")

class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

# Status update endpoints
@router.put("/nuclei/{finding_id}/status", response_model=Dict[str, Any])
async def update_nuclei_status(finding_id: str, request: StatusUpdateRequest):
    """Update the status and optionally the assigned user for a nuclei finding"""
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
        success = await NucleiFindingsRepository.update_nuclei_finding(finding_id, update_data)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Nuclei finding {finding_id} not found")
        
        # Return updated data
        updated_finding = await NucleiFindingsRepository.get_nuclei_by_id(finding_id)
        
        if not updated_finding:
            raise HTTPException(status_code=404, detail=f"Nuclei finding {finding_id} not found after update")
        
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
        logger.error(f"Error updating nuclei status {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Notes update endpoints
@router.put("/nuclei/{finding_id}/notes", response_model=Dict[str, Any])
async def update_nuclei_notes(finding_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for a nuclei finding"""
    try:
        # Update the finding
        update_data = {"notes": request.notes}
        success = await NucleiFindingsRepository.update_nuclei_finding(finding_id, update_data)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Nuclei finding {finding_id} not found")
        
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
        logger.error(f"Error updating nuclei notes {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/nuclei/batch", response_model=Dict[str, Any])
async def delete_nuclei_findings_batch(
    finding_ids: List[str], 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple nuclei findings by their IDs"""
    try:
        if not finding_ids:
            raise HTTPException(status_code=400, detail="No finding IDs provided")
        
        result = await NucleiFindingsRepository.delete_nuclei_findings_batch(finding_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for nuclei findings",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting nuclei findings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/nuclei/{finding_id}", response_model=Dict[str, Any])
async def delete_nuclei_finding(finding_id: str, current_user: UserResponse = Depends(require_admin_or_manager)):
    """Delete a nuclei finding by its ID"""
    try:
        deleted = await NucleiFindingsRepository.delete_nuclei_finding(finding_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Nuclei finding {finding_id} not found")
        
        return {
            "status": "success",
            "message": f"Nuclei finding {finding_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting nuclei finding {finding_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))