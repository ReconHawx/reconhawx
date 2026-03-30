from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List, Literal, Union
from repository import ProgramRepository, IPAssetsRepository
from pydantic import BaseModel, Field
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs, require_admin_or_manager
from models.user_postgres import UserResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Typed IPs search
class IPsSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Substring match on ip address")
    exact_match: Optional[str] = Field(None, description="Exact match on ip address")
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program(s) within user's access scope")
    has_ptr: Optional[bool] = Field(None, description="Filter IPs with/without PTR records")
    ptr_contains: Optional[str] = Field(None, description="Substring match on PTR record")
    has_service_provider: Optional[bool] = Field(None, description="Filter IPs with/without service provider")
    service_provider: Optional[Union[str, List[str]]] = Field(None, description="Service provider filter")
    sort_by: Literal['ip_address','program_name','ptr_record','service_provider','updated_at'] = 'ip_address'
    sort_dir: Literal['asc','desc'] = 'asc'
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/ip/search", response_model=Dict[str, Any])
async def search_ips_typed(request: IPsSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    try:
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
        result = await IPAssetsRepository.search_ips_typed(
            search=request.search,
            exact_match=request.exact_match,
            program=programs if programs is not None else None,
            has_ptr=request.has_ptr,
            ptr_contains=request.ptr_contains,
            has_service_provider=request.has_service_provider,
            service_provider=request.service_provider,
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
        logger.error(f"Error executing typed IP search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed IP search: {str(e)}")

# Pydantic models for IP import functionality
class IPImportData(BaseModel):
    ip: str = Field(..., description="IP address")
    program_name: Optional[str] = Field(None, description="Program name")
    ptr: Optional[str] = Field(None, description="PTR record")
    service_provider: Optional[str] = Field(None, description="Service provider")
    country: Optional[str] = Field(None, description="Country")
    city: Optional[str] = Field(None, description="City")
    notes: Optional[str] = Field(None, description="Investigation notes")

class IPImportRequest(BaseModel):
    ips: List[IPImportData] = Field(..., description="List of IPs to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing IPs")
    validate_ips: Optional[bool] = Field(True, description="Whether to validate IP addresses")

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

class BatchIPCheckRequest(BaseModel):
    ips: List[str] = Field(..., description="List of IP addresses to check")
    program: Optional[Union[str, List[str]]] = Field(None, description="Program(s) to check IPs in")

@router.get("/ip", response_model=Dict[str, Any])
async def get_specific_ip(id: Optional[str] = Query(None), current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """List IPs filtered by user program permissions, or return a single IP when 'id' is provided"""
    try:
        if id:
            ip = await IPAssetsRepository.get_ip_by_id(id)
            if not ip:
                raise HTTPException(status_code=404, detail=f"IP {id} not found")
            ip_program = ip.get("program_name")
            if ip_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and ip_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"IP {id} not found")
            return {"status": "success", "data": ip}

    except Exception as e:
        logger.error(f"Error listing IPs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ip/import", response_model=Dict[str, Any])
async def import_ips(request: IPImportRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Import multiple IP addresses from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of IP objects and imports them into the database.
    It supports validation, merging, and batch processing.
    """
    try:
        import ipaddress
        # Validate IP addresses if requested
        if request.validate_ips:
            invalid_ips = []
            for ip_data in request.ips:
                try:
                    ipaddress.ip_address(ip_data.ip)
                except ValueError:
                    invalid_ips.append(ip_data.ip)
            
            if invalid_ips:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid IP addresses: {', '.join(invalid_ips[:10])}{'...' if len(invalid_ips) > 10 else ''}"
                )
        
        # Filter IPs by user program permissions
        allowed_ips = []
        for ip_data in request.ips:
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if ip_data.program_name and ip_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import IP {ip_data.ip} to unauthorized program {ip_data.program_name}")
                    continue
            allowed_ips.append(ip_data)
        
        if not allowed_ips:
            raise HTTPException(
                status_code=403,
                detail="No IPs to import - all IPs belong to programs you don't have access to"
            )
        
        # Process IPs in batches
        imported_count = 0
        errors = []
        
        for ip_data in allowed_ips:
            try:
                ip_dict = {
                    "ip": ip_data.ip.strip(),
                    "program_name": ip_data.program_name,
                    "ptr": ip_data.ptr,
                    "service_provider": ip_data.service_provider,
                    "country": ip_data.country,
                    "city": ip_data.city,
                    "notes": ip_data.notes
                }
                
                # Remove None values and empty strings
                ip_dict = {k: v for k, v in ip_dict.items() if v is not None and v != ""}
                
                # Use create_or_update_ip which handles merging automatically
                ip_id = await IPAssetsRepository.create_or_update_ip(ip_dict)
                if ip_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated IP: {ip_dict['ip']}")
                else:
                    errors.append(f"Failed to create/update IP: {ip_dict['ip']}")
                        
            except Exception as e:
                error_msg = f"Error processing IP {ip_data.ip}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create programs if needed
        if imported_count > 0:
            for ip_data in allowed_ips:
                if ip_data.program_name:
                    program = await IPAssetsRepository.get_program_by_name(ip_data.program_name)
                    if not program:
                        program_data = {"name": ip_data.program_name}
                        await ProgramRepository.create_program(program_data)
                        logger.info(f"Created new program: {ip_data.program_name}")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Import completed: {imported_count} processed",
            "data": {
                "processed_count": imported_count,
                "total_processed": len(allowed_ips),
                "total_submitted": len(request.ips)
            }
        }
        
        if errors:
            response_data["data"]["errors"] = errors[:10]
            response_data["data"]["error_count"] = len(errors)
            
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no IPs were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        logger.info(f"IP import completed by user {current_user.username}: {response_data['message']}")
        return response_data

    except HTTPException:
        raise

@router.post("/ip/batch-check", response_model=Dict[str, Any])
async def batch_check_ips(request: BatchIPCheckRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Check if multiple IP addresses exist in the database for a given program.
    Optimized for batch processing of large numbers of IPs.
    """
    try:
        # Get accessible programs for the user
        accessible = get_user_accessible_programs(current_user)

        # Determine which programs to search in
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
                    "resolved_ips": [],
                    "total_checked": len(request.ips),
                    "total_found": 0
                }
            if requested_programs:
                programs = [p for p in requested_programs if p in allowed]
                if not programs:
                    return {
                        "status": "success",
                        "resolved_ips": [],
                        "total_checked": len(request.ips),
                        "total_found": 0
                    }
            else:
                programs = allowed

        # Check which IPs exist in the database
        resolved_ips = await IPAssetsRepository.batch_check_ips_exist(request.ips, programs)

        logger.info(f"Batch IP check completed: checked {len(request.ips)} IPs, found {len(resolved_ips)} existing")

        return {
            "status": "success",
            "resolved_ips": list(resolved_ips),
            "total_checked": len(request.ips),
            "total_found": len(resolved_ips)
        }

    except Exception as e:
        logger.error(f"Error in batch IP check: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error checking IPs in batch: {str(e)}")

# IP notes endpoints  
@router.put("/ip/{ip_id}/notes", response_model=Dict[str, Any])
async def update_ip_notes(ip_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for an IP"""
    try:
        success = await IPAssetsRepository.update_ip(ip_id, {"notes": request.notes})
        
        if not success:
            raise HTTPException(status_code=404, detail="IP not found")
        
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
        logger.error(f"Error updating IP notes {ip_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/ip/batch", response_model=Dict[str, Any])
async def delete_ips_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple IPs by their IDs"""
    try:
        # Extract asset_ids from request data
        asset_ids = request_data.get("asset_ids", [])
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No asset IDs provided")
        
        result = await IPAssetsRepository.delete_ips_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for IP assets",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting IP assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/ip/{ip_id}", response_model=Dict[str, Any])
async def delete_ip(
    ip_id: str, 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a specific IP by its ID"""
    try:
        deleted = await IPAssetsRepository.delete_ip(ip_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"IP with ID {ip_id} not found")
        
        return {
            "status": "success",
            "message": f"IP {ip_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting IP {ip_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ip/distinct/{field_name}", response_model=List[str])
async def get_distinct_ip_field_values(
    field_name: str,
    query: Optional[DistinctRequest] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Get distinct values for a specified field in IP assets, optionally applying a filter.
    Allowed fields: ip, ptr_record, service_provider.
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
        distinct_values = await IPAssetsRepository.get_distinct_values(field_name, filter_data)
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