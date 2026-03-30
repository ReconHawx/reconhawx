from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List, Literal, Union
from repository import ProgramRepository, ApexDomainAssetsRepository
from pydantic import BaseModel, Field
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs, require_admin_or_manager
from models.user_postgres import UserResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Pydantic models for apex domain import functionality
class ApexDomainImportData(BaseModel):
    name: str = Field(..., description="Apex domain name")
    program_name: Optional[str] = Field(None, description="Program name")
    cname: Optional[str] = Field(None, description="CNAME record")
    ip: Optional[List[str]] = Field(None, description="IP addresses")
    whois_data: Optional[Dict[str, Any]] = Field(None, description="WHOIS data")
    notes: Optional[str] = Field(None, description="Investigation notes")

class ApexDomainImportRequest(BaseModel):
    apex_domains: List[ApexDomainImportData] = Field(..., description="List of apex domains to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing apex domains")
    validate_domains: Optional[bool] = Field(True, description="Whether to validate domain names")

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

# Typed Apex Domains search
class ApexDomainsSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Substring search on apex domain name")
    exact_match: Optional[str] = Field(None, description="Exact match on apex domain name")
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Literal['name','program_name','updated_at','created_at'] = 'name'
    sort_dir: Literal['asc','desc'] = 'asc'
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/apex-domain/search", response_model=Dict[str, Any])
async def search_apex_domains_typed(request: ApexDomainsSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    try:
        # Determine program access and intersect with requested program(s) if provided
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
        result = await ApexDomainAssetsRepository.search_apex_domains_typed(
            search=request.search,
            exact_match=request.exact_match,
            program=programs if programs is not None else None,
            sort_by=request.sort_by,
            sort_dir=request.sort_dir,
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
        logger.error(f"Error executing typed apex domains search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed apex domains search: {str(e)}")

@router.get("/apex-domain", response_model=Dict[str, Any])
async def get_specific_apex_domain(id: Optional[str] = Query(None), current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """List apex domains filtered by user program permissions, or return a single apex domain when 'id' is provided"""
    try:
        if id:
            apex_domain = await ApexDomainAssetsRepository.get_apex_domain_by_id(id)
            if not apex_domain:
                raise HTTPException(status_code=404, detail=f"Apex domain {id} not found")
            apex_program = apex_domain.get("program_name")
            if apex_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and apex_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"Apex domain {id} not found")
            return {"status": "success", "data": apex_domain}

    except Exception as e:
        logger.error(f"Error listing apex domains: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apex-domain/import", response_model=Dict[str, Any])
async def import_apex_domains(request: ApexDomainImportRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Import multiple apex domains from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of apex domain objects and imports them into the database.
    It supports:
    - Validation of apex domain names
    - Merging with existing apex domain data
    - Batch processing for efficiency
    - Program-based filtering based on user permissions
    """
    try:
        import re
        # Validate apex domain names if requested
        if request.validate_domains:
            domain_pattern = re.compile(
                r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
            )
            
            invalid_domains = []
            for apex_domain_data in request.apex_domains:
                if not domain_pattern.match(apex_domain_data.name):
                    invalid_domains.append(apex_domain_data.name)
            
            if invalid_domains:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid apex domain names: {', '.join(invalid_domains[:10])}{'...' if len(invalid_domains) > 10 else ''}"
                )
        
        # Filter apex domains by user program permissions
        allowed_apex_domains = []
        for apex_domain_data in request.apex_domains:
            # If user has program restrictions, check if they can access this program
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if apex_domain_data.program_name and apex_domain_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import apex domain {apex_domain_data.name} to unauthorized program {apex_domain_data.program_name}")
                    continue
            allowed_apex_domains.append(apex_domain_data)
        
        if not allowed_apex_domains:
            raise HTTPException(
                status_code=403,
                detail="No apex domains to import - all apex domains belong to programs you don't have access to"
            )
        
        # Process apex domains in batches for better performance
        imported_count = 0
        errors = []
        
        for apex_domain_data in allowed_apex_domains:
            try:
                # Convert Pydantic model to dict for repository
                apex_domain_dict = {
                    "name": apex_domain_data.name.lower().strip(),  # Normalize apex domain name
                    "program_name": apex_domain_data.program_name,
                    #"cname": apex_domain_data.cname,
                    #"ip": apex_domain_data.ip or [],
                    "whois_data": apex_domain_data.whois_data,
                    "notes": apex_domain_data.notes
                }
                
                # Remove None values and empty strings, but keep empty lists and valid lists
                apex_domain_dict = {k: v for k, v in apex_domain_dict.items() if v is not None and v != ""}
                
                # Use create_or_update_apex_domain which handles merging automatically
                apex_domain_id = await ApexDomainAssetsRepository.create_or_update_apex_domain(apex_domain_dict)
                if apex_domain_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated apex domain: {apex_domain_dict['name']}")
                else:
                    errors.append(f"Failed to create/update apex domain: {apex_domain_dict['name']}")
                        
            except Exception as e:
                error_msg = f"Error processing apex domain {apex_domain_data.name}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create program if it doesn't exist and apex domains were processed
        if imported_count > 0:
            for apex_domain_data in allowed_apex_domains:
                if apex_domain_data.program_name:
                    program = await ApexDomainAssetsRepository.get_program_by_name(apex_domain_data.program_name)
                    if not program:
                        program_data = {"name": apex_domain_data.program_name}
                        await ProgramRepository.create_program(program_data)
                        logger.info(f"Created new program: {apex_domain_data.program_name}")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Import completed: {imported_count} processed",
            "data": {
                "processed_count": imported_count,
                "total_processed": len(allowed_apex_domains),
                "total_submitted": len(request.apex_domains)
            }
        }
        
        # Add errors to response if any occurred
        if errors:
            response_data["data"]["errors"] = errors[:10]  # Limit error list
            response_data["data"]["error_count"] = len(errors)
            
        # Adjust status if there were significant errors
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no apex domains were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        logger.info(f"Apex domain import completed by user {current_user.username}: {response_data['message']}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in apex domain import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing apex domains: {str(e)}"
        )

@router.put("/apex-domain/{apex_domain_id}/notes", response_model=Dict[str, Any])
async def update_apex_domain_notes(apex_domain_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for an apex domain"""
    try:
        success = await ApexDomainAssetsRepository.update_apex_domain(apex_domain_id, {"notes": request.notes})
        
        if not success:
            raise HTTPException(status_code=404, detail="Apex domain not found")
        
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
        logger.error(f"Error updating apex domain notes {apex_domain_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/apex-domain/batch", response_model=Dict[str, Any])
async def delete_apex_domains_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple apex domains by their IDs"""
    try:
        # Extract asset_ids and options from request data
        asset_ids = request_data.get("asset_ids", [])
        delete_subdomains = request_data.get("delete_subdomains", False)
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No asset IDs provided")
        
        # Handle special case for apex domain deletion with subdomains
        if delete_subdomains:
            result = await ApexDomainAssetsRepository.delete_apex_domains_with_subdomains(asset_ids)
        else:
            result = await ApexDomainAssetsRepository.delete_apex_domains_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for apex domain assets",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting apex domain assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/apex-domain/{apex_domain_id}", response_model=Dict[str, Any])
async def delete_apex_domain(
    apex_domain_id: str, 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a specific apex domain by its ID"""
    try:
        deleted = await ApexDomainAssetsRepository.delete_apex_domain(apex_domain_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Apex domain with ID {apex_domain_id} not found")
        
        return {
            "status": "success",
            "message": f"Apex domain {apex_domain_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting apex domain {apex_domain_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apex-domain/distinct/{field_name}", response_model=List[str])
async def get_distinct_apex_domain_field_values(
    field_name: str,
    query: Optional[DistinctRequest] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Get distinct values for a specified field in apex domain assets, optionally applying a filter.
    Allowed fields: name.
    """
    try:
        # Start from incoming filter (legacy shape used by frontend: { filter: { program_name: ... } })
        incoming_filter: Dict[str, Any] = {}
        if query and isinstance(query.filter, dict):
            incoming_filter = dict(query.filter)

        # Determine requested programs (support both typed 'program' and legacy 'filter.program_name')
        requested_programs: Optional[List[str]] = None
        if query and query.program is not None:
            if isinstance(query.program, str) and query.program.strip():
                requested_programs = [query.program.strip()]
            elif isinstance(query.program, list):
                requested_programs = [p for p in query.program if isinstance(p, str) and p.strip()]
        elif "program_name" in incoming_filter:
            pn = incoming_filter.get("program_name")
            if isinstance(pn, str) and pn.strip():
                requested_programs = [pn.strip()]
            elif isinstance(pn, list):
                requested_programs = [p for p in pn if isinstance(p, str) and p.strip()]

        # Enforce program scoping by intersecting with user's accessible programs
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

        # Build effective filter_data to pass to repository
        filter_data: Dict[str, Any] = dict(incoming_filter)
        # Normalize program_name in filter_data based on resolved programs
        if programs is not None:
            filter_data["program_name"] = programs
        else:
            # If admin with no explicit program filter, remove any stray program_name
            if "program_name" in filter_data:
                filter_data.pop("program_name", None)

        # Get distinct values using the repository method
        distinct_values = await ApexDomainAssetsRepository.get_distinct_values(field_name, filter_data)
        # Filter out None values to comply with List[str] response model
        return [value for value in distinct_values if value is not None]

    except ValueError as ve:
        logger.error(f"Value error getting distinct values for {field_name}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting distinct values for field '{field_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving distinct values for field '{field_name}'"
        )
