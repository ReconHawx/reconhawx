from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List, Literal, Union
from repository import ProgramRepository, ServiceAssetsRepository
from pydantic import BaseModel, Field
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs, require_admin_or_manager
from models.user_postgres import UserResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Typed Services search
class ServicesSearchRequest(BaseModel):
    ip_port_text: Optional[str] = Field(None, description="Substring match on 'ip:port' string")
    search_ip: Optional[str] = Field(None, description="Substring match on IP address")
    exact_match_ip: Optional[str] = Field(None, description="Exact match on IP address")
    exact_match: Optional[str] = Field(None, description="Exact match on 'ip:port' string")
    port: Optional[int] = Field(None, description="Exact port match")
    protocol: Optional[Literal['tcp','udp']] = Field(None, description="Protocol filter")
    service_name: Optional[str] = Field(None, description="Exact service name match")
    service_text: Optional[str] = Field(None, description="Text search across service fields")
    ip_port_or: Optional[bool] = Field(False, description="When both search_ip and port are provided, match IP OR port instead of AND")
    exclude_common_ports: Optional[bool] = Field(False, description="Exclude common ports (80, 443, 21, etc.); show only uncommon ports like 8080, 8443")
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Literal['ip','port','service_name','protocol','banner','program_name','updated_at'] = 'ip'
    sort_dir: Literal['asc','desc'] = 'asc'
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/service/search", response_model=Dict[str, Any])
async def search_services_typed(request: ServicesSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
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
        result = await ServiceAssetsRepository.search_services_typed(
            ip_port_text=request.ip_port_text,
            search_ip=request.search_ip,
            exact_match_ip=request.exact_match_ip,
            exact_match=request.exact_match,
            port=request.port,
            protocol=request.protocol,
            service_name=request.service_name,
            service_text=request.service_text,
            ip_port_or=bool(request.ip_port_or),
            exclude_common_ports=bool(request.exclude_common_ports),
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
        logger.error(f"Error executing typed services search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed services search: {str(e)}")

    Field(..., description="List of URLs to import")
    Field(True, description="Whether to merge with existing data")
    Field(False, description="Whether to update existing URLs")
    Field(True, description="Whether to validate URL format")

# Pydantic models for service import functionality
class ServiceImportData(BaseModel):
    ip: str = Field(..., description="IP address")
    port: int = Field(..., description="Port number")
    program_name: Optional[str] = Field(None, description="Program name")
    service: Optional[str] = Field(None, description="Service name")
    protocol: Optional[str] = Field(None, description="Protocol")
    banner: Optional[str] = Field(None, description="Service banner")
    product: Optional[str] = Field(None, description="Product name")
    version: Optional[str] = Field(None, description="Version")
    notes: Optional[str] = Field(None, description="Investigation notes")

class ServiceImportRequest(BaseModel):
    services: List[ServiceImportData] = Field(..., description="List of services to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing services")
    validate_services: Optional[bool] = Field(True, description="Whether to validate service data")

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

@router.get("/service", response_model=Dict[str, Any])
async def get_specific_service(id: Optional[str] = Query(None), current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """List services filtered by user program permissions, or return a single service when 'id' is provided"""
    try:
        if id:
            service = await ServiceAssetsRepository.get_service_by_id(id)
            if not service:
                raise HTTPException(status_code=404, detail=f"Service {id} not found")
            service_program = service.get("program_name")
            if service_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and service_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"Service {id} not found")
            return {"status": "success", "data": service}

    except Exception as e:
        logger.error(f"Error listing services: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/service/import", response_model=Dict[str, Any])
async def import_services(request: ServiceImportRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Import multiple services from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of service objects and imports them into the database.
    It supports validation, merging, and batch processing.
    """
    try:
        import ipaddress
        # Validate services if requested
        if request.validate_services:
            invalid_services = []
            for service_data in request.services:
                try:
                    # Validate IP address
                    ipaddress.ip_address(service_data.ip)
                    # Validate port range
                    if not (1 <= service_data.port <= 65535):
                        invalid_services.append(f"{service_data.ip}:{service_data.port} (invalid port)")
                except ValueError:
                    invalid_services.append(f"{service_data.ip}:{service_data.port} (invalid IP)")
            
            if invalid_services:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid services: {', '.join(invalid_services[:10])}{'...' if len(invalid_services) > 10 else ''}"
                )
        
        # Filter services by user program permissions
        allowed_services = []
        for service_data in request.services:
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if service_data.program_name and service_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import service {service_data.ip}:{service_data.port} to unauthorized program {service_data.program_name}")
                    continue
            allowed_services.append(service_data)
        
        if not allowed_services:
            raise HTTPException(
                status_code=403,
                detail="No services to import - all services belong to programs you don't have access to"
            )
        
        # Process services in batches
        imported_count = 0
        errors = []
        
        for service_data in allowed_services:
            try:
                service_dict = {
                    "ip": service_data.ip.strip(),
                    "port": service_data.port,
                    "program_name": service_data.program_name,
                    "service": service_data.service,
                    "protocol": service_data.protocol,
                    "banner": service_data.banner,
                    "product": service_data.product,
                    "version": service_data.version,
                    "notes": service_data.notes
                }
                
                # Remove None values and empty strings
                service_dict = {k: v for k, v in service_dict.items() if v is not None and v != ""}
                
                # Use create_or_update_service which handles merging automatically
                service_id = await ServiceAssetsRepository.create_or_update_service(service_dict)
                if service_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated service: {service_dict['ip']}:{service_dict['port']}")
                else:
                    errors.append(f"Failed to create/update service: {service_dict['ip']}:{service_dict['port']}")
                        
            except Exception as e:
                error_msg = f"Error processing service {service_data.ip}:{service_data.port}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create programs if needed
        if imported_count > 0:
            for service_data in allowed_services:
                if service_data.program_name:
                    program = await ProgramRepository.get_program_by_name(service_data.program_name)
                    if not program:
                        program_data = {"name": service_data.program_name}
                        await ProgramRepository.create_program(program_data)
                        logger.info(f"Created new program: {service_data.program_name}")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Import completed: {imported_count} processed",
            "data": {
                "processed_count": imported_count,
                "total_processed": len(allowed_services),
                "total_submitted": len(request.services)
            }
        }
        
        if errors:
            response_data["data"]["errors"] = errors[:10]
            response_data["data"]["error_count"] = len(errors)
            
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no services were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        logger.info(f"Service import completed by user {current_user.username}: {response_data['message']}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in service import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing services: {str(e)}"
        )

@router.get("/service/{ip}/{port}", response_model=Dict[str, Any])
async def get_service_by_ip_port(ip: str, port: int, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """Get a service by IP and port if user has access to its program"""
    try:
        # Repository method now handles both int and string port formats
        service = await ServiceAssetsRepository.get_service_by_ip_port(ip, port)
        
        logger.info(f"Service query for {ip}:{port} - Found: {service is not None}")
        
        if not service:
            raise HTTPException(status_code=404, detail=f"Service {ip}:{port} not found")
        
        # Check if user has access to this service's program
        service_program = service.get("program_name")
        if service_program:
            accessible_programs = get_user_accessible_programs(current_user)
            # For superusers/admins, accessible_programs is empty (meaning no restrictions)
            if accessible_programs and service_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"Service {ip}:{port} not found")
        
        return {
            "status": "success",
            "data": service,  # Keep data field for backward compatibility
            "items": [service]  # Keep items field for consistency with other endpoints
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting service {ip}:{port}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Service notes endpoints
@router.put("/service/{service_id}/notes", response_model=Dict[str, Any])
async def update_service_notes(service_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for a service"""
    try:
        success = await ServiceAssetsRepository.update_service(service_id, {"notes": request.notes})
        
        if not success:
            raise HTTPException(status_code=404, detail="Service not found")
        
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
        logger.error(f"Error updating service notes {service_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/service/batch", response_model=Dict[str, Any])
async def delete_services_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple services by their IDs"""
    try:
        # Extract asset_ids from request data
        asset_ids = request_data.get("asset_ids", [])
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No asset IDs provided")
        
        result = await ServiceAssetsRepository.delete_services_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for service assets",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting service assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/service/{service_id}", response_model=Dict[str, Any])
async def delete_service(
    service_id: str, 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a specific service by its ID"""
    try:
        deleted = await ServiceAssetsRepository.delete_service(service_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Service with ID {service_id} not found")
        
        return {
            "status": "success",
            "message": f"Service {service_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting service {service_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/service/distinct/{field_name}", response_model=List[str])
async def get_distinct_service_field_values(
    field_name: str,
    query: Optional[DistinctRequest] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Get distinct values for a specified field in service assets, optionally applying a filter.
    Allowed fields: service_name, port, protocol, product, version.
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
        distinct_values = await ServiceAssetsRepository.get_distinct_values(field_name, filter_data)
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