from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List, Literal, Union
from urllib.parse import unquote
from repository import SubdomainAssetsRepository, ProgramRepository
from pydantic import BaseModel, Field
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs, require_admin_or_manager
from models.user_postgres import UserResponse
import logging


logger = logging.getLogger(__name__)

router = APIRouter()

# Typed subdomain search model
class SubdomainSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Fuzzy search on subdomain name")
    exact_match: Optional[str] = Field(None, description="Exact match on subdomain name")
    apex_domain: Optional[Union[str, List[str]]] = Field(None, description="Apex domain name(s)")
    wildcard: Optional[bool] = Field(None, description="Filter by wildcard flag")
    has_ips: Optional[bool] = Field(None, description="Filter subdomains that have any IPs")
    ip: Optional[Union[str, List[str]]] = Field(None, description="Filter subdomains that resolve to specific IP address(es)")
    has_cname: Optional[bool] = Field(None, description="Filter by presence of CNAME record")
    cname_contains: Optional[str] = Field(None, description="Substring match on CNAME record")
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Literal['name','apex_domain','program_name','is_wildcard','updated_at','ip_count','cname_record'] = 'updated_at'
    sort_dir: Literal['asc','desc'] = 'desc'
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/subdomain/search", response_model=Dict[str, Any])
async def search_subdomains_typed(request: SubdomainSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
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
            # Unrestricted; honor requested programs if present, else None for no filter
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
                # Intersect
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

        # Compute pagination offset
        skip = (request.page - 1) * request.page_size

        result = await SubdomainAssetsRepository.search_subdomains_typed(
            search=request.search,
            exact_match=request.exact_match,
            apex_domain=request.apex_domain,
            wildcard=request.wildcard,
            has_ips=request.has_ips,
            ip=request.ip,
            has_cname=request.has_cname,
            cname_contains=request.cname_contains,
            programs=programs,
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
        logger.error(f"Error executing typed subdomain search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed subdomain search: {str(e)}")

# Pydantic models for domain import functionality
class DomainImportData(BaseModel):
    name: str = Field(..., description="Domain name")
    program_name: Optional[str] = Field(None, description="Program name")
    is_wildcard: Optional[bool] = Field(False, description="Whether domain is wildcard")
    ip: Optional[List[str]] = Field(None, description="IP addresses")
    cname_record: Optional[str] = Field(None, description="CNAME record")
    notes: Optional[str] = Field(None, description="Investigation notes")

class DomainImportRequest(BaseModel):
    domains: List[DomainImportData] = Field(..., description="List of domains to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing domains")
    validate_domains: Optional[bool] = Field(True, description="Whether to validate domain names")

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

@router.get("/subdomain", response_model=Dict[str, Any])
async def get_specific_subdomain(id: Optional[str] = Query(None), current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """List domains filtered by user program permissions, or return a single domain when 'id' is provided"""
    try:
        # Unified single fetch by ID if provided
        if id:
            domain = await SubdomainAssetsRepository.get_domain_by_id(id)
            if not domain:
                raise HTTPException(status_code=404, detail=f"Domain {id} not found")
            domain_program = domain.get("program_name")
            if domain_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and domain_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"Domain {id} not found")
            return {"status": "success", "data": domain}

    except Exception as e:
        logger.error(f"Error fetching subdomain: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subdomain/name/{domain_name}", response_model=Dict[str, Any])
async def get_subdomain_by_name(domain_name: str, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """Get a subdomain by its exact name"""
    try:
        accessible = get_user_accessible_programs(current_user)
        programs = None if (current_user.is_superuser or "admin" in current_user.roles) else (accessible or [])
        if programs is not None and len(programs) == 0:
            raise HTTPException(status_code=404, detail=f"Domain {domain_name} not found")
        domain = await SubdomainAssetsRepository.get_domain_by_name(
            unquote(domain_name) if "%" in domain_name else domain_name,
            programs=programs
        )
        if not domain:
            raise HTTPException(status_code=404, detail=f"Domain {domain_name} not found")
        return {"status": "success", "data": domain}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching subdomain by name: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/subdomain/import", response_model=Dict[str, Any])
async def import_domains(request: DomainImportRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Import multiple domains from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of domain objects and imports them into the database.
    It supports:
    - Validation of domain names
    - Merging with existing domain data
    - Batch processing for efficiency
    - Program-based filtering based on user permissions
    """
    try:
        import re
        # Validate domain names if requested
        if request.validate_domains:
            domain_pattern = re.compile(
                r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
            )
            
            invalid_domains = []
            for domain_data in request.domains:
                if not domain_pattern.match(domain_data.name):
                    invalid_domains.append(domain_data.name)
            
            if invalid_domains:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid domain names: {', '.join(invalid_domains[:10])}{'...' if len(invalid_domains) > 10 else ''}"
                )
        
        # Filter domains by user program permissions
        allowed_domains = []
        for domain_data in request.domains:
            # If user has program restrictions, check if they can access this program
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if domain_data.program_name and domain_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import domain {domain_data.name} to unauthorized program {domain_data.program_name}")
                    continue
            allowed_domains.append(domain_data)
        
        if not allowed_domains:
            raise HTTPException(
                status_code=403,
                detail="No domains to import - all domains belong to programs you don't have access to"
            )
        
        # Process domains in batches for better performance
        imported_count = 0
        errors = []
        
        for domain_data in allowed_domains:
            try:
                # Convert Pydantic model to dict for repository
                domain_dict = {
                    "name": domain_data.name.lower().strip(),  # Normalize domain name
                    "program_name": domain_data.program_name,
                    "is_wildcard": domain_data.is_wildcard or False,
                    "ip": domain_data.ip or [],
                    "cname_record": domain_data.cname_record,
                    "notes": domain_data.notes
                }
                
                
                # Remove None values and empty strings, but keep empty lists and valid lists
                domain_dict = {k: v for k, v in domain_dict.items() if v is not None and v != ""}
                
                # Use create_or_update_subdomain which handles merging automatically
                domain_id, _action, _event_data, _apex_event = await SubdomainAssetsRepository.create_or_update_subdomain(
                    domain_dict
                )
                if domain_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated domain: {domain_dict['name']}")
                else:
                    errors.append(f"Failed to create/update domain: {domain_dict['name']}")
                        
            except Exception as e:
                error_msg = f"Error processing domain {domain_data.name}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create program if it doesn't exist and domains were processed
        if imported_count > 0:
            for domain_data in allowed_domains:
                if domain_data.program_name:
                    program = await ProgramRepository.get_program_by_name(domain_data.program_name)
                    if not program:
                        program_data = {"name": domain_data.program_name}
                        await ProgramRepository.create_program(program_data)
                        logger.info(f"Created new program: {domain_data.program_name}")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Import completed: {imported_count} processed",
            "data": {
                "processed_count": imported_count,
                "total_processed": len(allowed_domains),
                "total_submitted": len(request.domains)
            }
        }
        
        # Add errors to response if any occurred
        if errors:
            response_data["data"]["errors"] = errors[:10]  # Limit error list
            response_data["data"]["error_count"] = len(errors)
            
        # Adjust status if there were significant errors
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no domains were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        logger.info(f"Domain import completed by user {current_user.username}: {response_data['message']}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in domain import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing domains: {str(e)}"
        )

# Domain notes endpoints
@router.put("/subdomain/{domain_id}/notes", response_model=Dict[str, Any])
async def update_domain_notes(domain_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for a domain/subdomain"""
    try:
        success = await SubdomainAssetsRepository.update_domain(domain_id, {"notes": request.notes})
        
        if not success:
            raise HTTPException(status_code=404, detail="Domain not found")
        
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
        logger.error(f"Error updating domain notes {domain_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/subdomain/batch", response_model=Dict[str, Any])
async def delete_domains_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple domains/subdomains by their IDs"""
    try:
        # Extract asset_ids from request data
        asset_ids = request_data.get("asset_ids", [])
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No asset IDs provided")
        
        result = await SubdomainAssetsRepository.delete_subdomains_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for domain/subdomain assets",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting domain/subdomain assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/subdomain/{domain_id}", response_model=Dict[str, Any])
async def delete_domain(
    domain_id: str, 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a specific domain/subdomain by its ID"""
    try:
        deleted = await SubdomainAssetsRepository.delete_subdomain(domain_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Domain with ID {domain_id} not found")
        
        return {
            "status": "success",
            "message": f"Domain {domain_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting domain {domain_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/subdomain/distinct/{field_name}", response_model=List[str])
async def get_distinct_subdomain_field_values(
    field_name: str,
    query: Optional[DistinctRequest] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Get distinct values for a specified field in subdomain assets, optionally applying a filter.
    Allowed fields: name, apex_domain, wildcard_types.
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
        distinct_values = await SubdomainAssetsRepository.get_distinct_values(field_name, filter_data)
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