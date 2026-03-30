from fastapi import APIRouter, HTTPException, Path, Body, Query, Depends, status
from typing import Dict, Any, Optional, Literal, List
from pydantic import BaseModel, Field
import logging
from models.program import APIProgram
from repository import ProgramRepository, EventHandlerConfigRepository
from auth.dependencies import (
    get_current_user_from_middleware,
    check_program_permission,
    get_user_accessible_programs,
    require_internal_service_identity,
)
from services.ct_monitor_client import sync_ct_monitor_program_config
from models.user_postgres import UserResponse
from services.hackerone_service import HackerOneService
from services.yeswehack_service import YesWeHackService
from services.intigriti_service import IntigritiService
from services.bugcrowd_service import BugcrowdService

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryFilter(BaseModel):
    filter: Dict[str, Any]
    limit: Optional[int] = None
    skip: Optional[int] = 0

# Typed program search model
class ProgramSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Fuzzy search on program name")
    exact_match: Optional[str] = Field(None, description="Exact match on program name")
    has_domains: Optional[bool] = Field(None, description="Filter programs that have any domains")
    has_ips: Optional[bool] = Field(None, description="Filter programs that have any IPs")
    has_workflows: Optional[bool] = Field(None, description="Filter programs that have any workflows")
    has_findings: Optional[bool] = Field(None, description="Filter programs that have any findings")
    sort_by: Literal['name', 'domain_count', 'ip_count', 'workflow_count', 'findings_count', 'created_at', 'updated_at'] = 'updated_at'
    sort_dir: Literal['asc', 'desc'] = 'desc'
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

class HackerOneImportRequest(BaseModel):
    program_handle: str = Field(..., min_length=1, description="HackerOne program handle (e.g., 'twitter', 'shopify')")

class HackerOneImportResponse(BaseModel):
    status: str = Field(..., description="Status of the import operation")
    program_name: str = Field(..., description="Name of the created program")
    message: str = Field(..., description="Detailed message about the import")
    scope_summary: Dict[str, int] = Field(..., description="Summary of imported scope items")

class YesWeHackImportRequest(BaseModel):
    program_slug: str = Field(..., min_length=1, description="YesWeHack program slug (e.g., 'swiss-post')")
    jwt_token: str = Field(..., min_length=20, description="YesWeHack JWT authentication token")

class YesWeHackImportResponse(BaseModel):
    status: str = Field(..., description="Status of the import operation")
    program_name: str = Field(..., description="Name of the created program")
    message: str = Field(..., description="Detailed message about the import")
    scope_summary: Dict[str, int] = Field(..., description="Summary of imported scope items")

class IntigritiImportRequest(BaseModel):
    program_handle: str = Field(..., min_length=1, description="Intigriti program handle (e.g., 'uzleuven', 'innovapost')")

class IntigritiImportResponse(BaseModel):
    status: str = Field(..., description="Status of the import operation")
    program_name: str = Field(..., description="Name of the created program")
    message: str = Field(..., description="Detailed message about the import")
    scope_summary: Dict[str, int] = Field(..., description="Summary of imported scope items")

class BugcrowdImportRequest(BaseModel):
    program_code: str = Field(..., min_length=1, description="Bugcrowd program code (e.g., 'tesla', 'paypal')")
    session_token: str = Field(..., min_length=20, description="Bugcrowd session token (_bugcrowd_session cookie)")

class BugcrowdImportResponse(BaseModel):
    status: str = Field(..., description="Status of the import operation")
    program_name: str = Field(..., description="Name of the created program")
    message: str = Field(..., description="Detailed message about the import")
    scope_summary: Dict[str, int] = Field(..., description="Summary of imported scope items")

@router.post("", include_in_schema=True, response_model=Dict[str, str])
@router.post("/", include_in_schema=True, response_model=Dict[str, str])
async def create_program(
    program: APIProgram,
    restore_from_archive: bool = Query(
        False,
        description=(
            "If true, attempts to restore assets from archive for this program name instead of "
            "creating anew. Fails if program already exists."
        ),
    ),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Create a new program, optionally restoring from archive via query parameter."""
    try:
        # API-side guard: only superusers or admins can create programs
        if not (current_user.is_superuser or (current_user.roles and "admin" in current_user.roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrative privileges required to create programs",
            )

        program_dict = program.model_dump(by_alias=True, exclude_none=True)
        
        logger.info(f"Attempting to create program: {program_dict.get('name')}, Restore: {restore_from_archive}")
        
        # Pass program data and restore flag separately to repository
        program_id = await ProgramRepository.create_program(program_dict, restore_from_archive=restore_from_archive)
        
        if program_id is not None and program_dict.get("ct_monitoring_enabled"):
            await sync_ct_monitor_program_config()

        if program_id is None:
             # This might happen if validation (like scope check) fails in the repo
             # Or if restore was attempted but nothing was found (depends on repo implementation)
             # For now, assume success if no exception is raised and ID is returned
             logger.warning(f"Program creation/restoration for '{program_dict.get('name')}' resulted in None ID, possibly skipped.")
             # Consider returning a different status or message
             raise HTTPException(status_code=400, detail="Program creation skipped or failed validation.")

        return {"id": program_id, "status": "success"}
    except HTTPException:
        # Re-raise HTTPExceptions (e.g., our 403 guard) without converting to 500
        raise
    except ValueError as ve: # Catch specific errors like duplicate or failed validation
        logger.warning(f"Validation error creating program: {str(ve)}")
        raise HTTPException(status_code=409, detail=str(ve)) # 409 Conflict might be appropriate
    except Exception as e:
        logger.exception(f"Error creating program: {str(e)}") # Use exception for stack trace
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

@router.get("", include_in_schema=True, response_model=Dict[str, Any])
@router.get("/", include_in_schema=True, response_model=Dict[str, Any])
async def list_programs(current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """List programs accessible to the current user"""
    try:
        all_programs = await ProgramRepository.list_programs()
        
        # Check if user has unrestricted access (superuser or admin)
        if current_user.is_superuser or "admin" in current_user.roles:
            # Superusers and admins see all programs
            program_names = [program.get("name") for program in all_programs if program.get("name")]
        else:
            # Regular users see only their permitted programs
            program_permissions = current_user.program_permissions or {}
            
            if isinstance(program_permissions, list):
                # Old format: list of program names
                accessible_program_names = program_permissions
            elif isinstance(program_permissions, dict):
                # New format: dict of program -> permission level
                accessible_program_names = list(program_permissions.keys())
            else:
                accessible_program_names = []
                
            program_names = [program.get("name") for program in all_programs 
                           if program.get("name") and program.get("name") in accessible_program_names]
        
        # Build a lookup for program data by name
        program_data_by_name = {p.get("name"): p for p in all_programs if p.get("name")}
        
        # Add permission levels for regular users
        programs_with_permissions = []
        if current_user.is_superuser or "admin" in current_user.roles:
            # Superusers/admins have manager access to all programs
            programs_with_permissions = [
                {
                    "name": name, 
                    "permission_level": "manager",
                    "protected_domains": program_data_by_name.get(name, {}).get("protected_domains", []),
                    "ct_monitoring_enabled": bool(
                        program_data_by_name.get(name, {}).get("ct_monitoring_enabled", False)
                    ),
                } 
                for name in program_names
            ]
        else:
            # Regular users - include their actual permission levels
            program_permissions = current_user.program_permissions or {}
            
            if isinstance(program_permissions, list):
                # Old format: list of program names - treat as analyst level
                programs_with_permissions = [
                    {
                        "name": name, 
                        "permission_level": "analyst",
                        "protected_domains": program_data_by_name.get(name, {}).get("protected_domains", []),
                        "ct_monitoring_enabled": bool(
                            program_data_by_name.get(name, {}).get("ct_monitoring_enabled", False)
                        ),
                    } 
                    for name in program_names
                ]
            elif isinstance(program_permissions, dict):
                # New format: dict of program -> permission level
                programs_with_permissions = [
                    {
                        "name": name, 
                        "permission_level": program_permissions.get(name, "analyst"),
                        "protected_domains": program_data_by_name.get(name, {}).get("protected_domains", []),
                        "ct_monitoring_enabled": bool(
                            program_data_by_name.get(name, {}).get("ct_monitoring_enabled", False)
                        ),
                    } 
                    for name in program_names if name is not None
                ]
            else:
                programs_with_permissions = []
        
        return {
            "status": "success",
            "programs": program_names,
            "programs_with_permissions": programs_with_permissions
        }
    except Exception as e:
        logger.error(f"Error listing programs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ct-monitoring/any-enabled", response_model=Dict[str, Any])
async def get_ct_monitoring_any_enabled(
    _user: UserResponse = Depends(require_internal_service_identity),
):
    """Return whether any program has CT monitoring enabled (internal services only)."""
    try:
        any_enabled = await ProgramRepository.any_ct_monitoring_enabled()
        return {"status": "success", "any_enabled": any_enabled}
    except Exception as e:
        logger.error(f"Error checking ct_monitoring_enabled: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/id/{program_id}", response_model=Dict[str, Any])
async def get_program_by_id(program_id: str):
    """Get program by ID (for backward compatibility)"""
    try:
        program = await ProgramRepository.get_program(program_id)
        if not program:
            logger.warning(f"Program not found with ID: {program_id}")
            raise HTTPException(status_code=404, detail=f"Program with ID {program_id} not found")
        
        return program
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error fetching program: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{program_name}", response_model=Dict[str, Any])
async def get_program(program_name: str = Path(..., min_length=1)):
    """Get program by name"""
    try:
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            logger.warning(f"Program not found with name: {program_name}")
            raise HTTPException(status_code=404, detail=f"Program with name {program_name} not found")
        
        return program
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error fetching program: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{program_name}", include_in_schema=True, response_model=Dict[str, str])
@router.put("/{program_name}/", include_in_schema=True, response_model=Dict[str, str])
async def update_program(
    program_name: str = Path(..., min_length=1),
    update_data: Dict[str, Any] = Body(...),
    overwrite: bool = Query(False, description="Whether to overwrite list fields or append to them"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update a program by name
    
    Args:
        program_name: Name of the program to update
        update_data: Data to update
        overwrite: If True, replace entire lists instead of appending. Defaults to False.
    """
    try:
        # Check if user has manager-level access to this program
        if not check_program_permission(current_user, program_name, "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager-level access required to edit program settings"
            )
        # First, check if the program exists
        existing_program = await ProgramRepository.get_program_by_name(program_name)
        if not existing_program:
            logger.warning(f"Program not found with name: {program_name}")
            raise HTTPException(status_code=404, detail=f"Program with name {program_name} not found")
        
        # Remove id field if present to avoid immutable field error
        update_data.pop('id', None)

        # For PostgreSQL, we need to handle list fields differently
        # If overwrite is True, we replace the entire list
        # If overwrite is False, we merge the lists (add unique values)
        if not overwrite:
            # Merge lists by adding unique values
            for field in ['domain_regex', 'out_of_scope_regex', 'cidr_list', 'safe_registrar', 'safe_ssl_issuer', 'protected_domains', 'protected_subdomain_prefixes']:
                if field in update_data and isinstance(update_data[field], list):
                    existing_list = existing_program.get(field, [])
                    if isinstance(existing_list, list):
                        # Add new values that don't already exist
                        for item in update_data[field]:
                            if item not in existing_list:
                                existing_list.append(item)
                        update_data[field] = existing_list
        
        success = await ProgramRepository.update_program(existing_program["id"], update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update program")
        
        # Sync notification handlers when notification_settings changed
        if "notification_settings" in update_data:
            try:
                from services.notification_handler_templates import sync_notification_handlers_for_program
                await sync_notification_handlers_for_program(
                    existing_program["id"],
                    program_name,
                    update_data["notification_settings"],
                )
            except Exception as e:
                logger.warning(f"Failed to sync notification handlers for {program_name}: {e}")

        ct_related = {
            "ct_monitoring_enabled",
            "protected_domains",
            "protected_subdomain_prefixes",
            "ct_monitor_program_settings",
        }
        if update_data.keys() & ct_related and (
            "ct_monitoring_enabled" in update_data
            or existing_program.get("ct_monitoring_enabled")
        ):
            await sync_ct_monitor_program_config()
        
        logger.info(f"Successfully updated program: {program_name}")
        return {"status": "success", "message": f"Program {program_name} updated successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error updating program: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class EventHandlerConfigUpdateRequest(BaseModel):
    """Request model for updating program event handler config."""

    handlers: List[Dict[str, Any]] = Field(..., description="Array of handler configs")
    event_handler_addon_mode: Optional[bool] = Field(
        None,
        description="True: handlers are additive on top of global. False: legacy full snapshot. Omit to keep current.",
    )


@router.get("/{program_name}/event-handler-configs/global-template", response_model=Dict[str, Any])
async def get_global_event_handler_template(
    program_name: str = Path(..., min_length=1),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Get global handler config (reference only; program-specific handlers are normally additive)."""
    if not check_program_permission(current_user, program_name, "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager-level access required")
    handlers = await EventHandlerConfigRepository.get_global_handlers()
    return {"status": "success", "handlers": handlers}


@router.get("/{program_name}/event-handler-configs", response_model=Dict[str, Any])
async def get_program_event_handler_config(
    program_name: str = Path(..., min_length=1),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Get program event handler rows (manager only). null handlers if using global defaults only."""
    if not check_program_permission(current_user, program_name, "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager-level access required")
    program = await ProgramRepository.get_program_by_name(program_name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")
    addon_mode = bool(program.get("event_handler_addon_mode", False))
    config = await EventHandlerConfigRepository.get_program_config(program["id"])
    if config:
        return {
            "status": "success",
            "handlers": config["handlers"],
            "use_global": False,
            "event_handler_addon_mode": addon_mode,
        }
    return {
        "status": "success",
        "handlers": None,
        "use_global": True,
        "event_handler_addon_mode": False,
    }


@router.put("/{program_name}/event-handler-configs", response_model=Dict[str, Any])
async def update_program_event_handler_config(
    program_name: str = Path(..., min_length=1),
    request: EventHandlerConfigUpdateRequest = Body(...),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Set program event handler rows (manager only). See event_handler_addon_mode on the program."""
    if not check_program_permission(current_user, program_name, "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager-level access required")
    program = await ProgramRepository.get_program_by_name(program_name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")
    addon = request.event_handler_addon_mode
    if addon is None:
        addon = await EventHandlerConfigRepository.get_program_addon_mode(program["id"])
    cleaned = EventHandlerConfigRepository.filter_handlers_for_program_persist(request.handlers)
    if not cleaned and addon:
        await EventHandlerConfigRepository.delete_program_config(program["id"])
        return {"status": "success", "message": "No program-specific handlers; using global + system defaults"}
    await EventHandlerConfigRepository.set_program_config(
        program["id"], request.handlers, addon_mode=addon
    )
    return {"status": "success", "message": "Program event handler config updated"}


@router.delete("/{program_name}/event-handler-configs", response_model=Dict[str, Any])
async def delete_program_event_handler_config(
    program_name: str = Path(..., min_length=1),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Remove program event handler override - revert to global (manager only)."""
    if not check_program_permission(current_user, program_name, "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager-level access required")
    program = await ProgramRepository.get_program_by_name(program_name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{program_name}' not found")
    deleted = await EventHandlerConfigRepository.delete_program_config(program["id"])
    return {"status": "success", "message": "Reverted to global config" if deleted else "No override to remove"}


@router.delete("/{program_name}", include_in_schema=True, response_model=Dict[str, Any])
@router.delete("/{program_name}/", include_in_schema=True, response_model=Dict[str, Any])
async def delete_program(program_name: str = Path(..., min_length=1)):
    """Delete a program by name and archive associated assets/findings."""
    logger.info(f"Attempting to delete program: {program_name}")
    try:
        # Check if the program exists first
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            logger.warning(f"Program not found for deletion: {program_name}")
            raise HTTPException(status_code=404, detail=f"Program with name '{program_name}' not found")

        program_id = program.get("id")
        if not program_id:
             logger.error(f"Program '{program_name}' found but is missing an id.")
             raise HTTPException(status_code=500, detail="Internal error: Program data is inconsistent.")

        # Call the repository method to handle archiving and deletion
        archive_result = await ProgramRepository.archive_and_delete_program(program_id, program_name)
        
        logger.info(f"Successfully deleted program '{program_name}' and archived related data.")
        return {
            "status": "success",
            "message": f"Program '{program_name}' deleted successfully.",
            "archived_counts": archive_result
        }

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions directly
        logger.error(f"HTTP error during deletion of program '{program_name}': {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.exception(f"Unexpected error deleting program '{program_name}': {str(e)}") # Use logger.exception for stack trace
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@router.post("/search", response_model=Dict[str, Any])
async def search_programs_typed(request: ProgramSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """Search programs with typed parameters and pagination"""
    try:
        # Determine program access
        get_user_accessible_programs(current_user)
        
        # Compute pagination offset
        skip = (request.page - 1) * request.page_size

        # Execute search
        result = await ProgramRepository.search_programs_typed(
            search=request.search,
            exact_match=request.exact_match,
            has_domains=request.has_domains,
            has_ips=request.has_ips,
            has_workflows=request.has_workflows,
            has_findings=request.has_findings,
            sort_by=request.sort_by,
            sort_dir=request.sort_dir,
            limit=request.page_size,
            skip=skip,
        )

        # Apply user program filtering
        all_items = result.get("items", [])
        total_count = result.get("total_count", 0)
        
        if current_user.is_superuser or "admin" in current_user.roles:
            # Superusers and admins see all programs
            filtered_items = all_items
            filtered_count = total_count
        else:
            # Regular users see only their permitted programs
            program_permissions = current_user.program_permissions or {}
            
            if isinstance(program_permissions, list):
                # Old format: list of program names
                accessible_program_names = program_permissions
            elif isinstance(program_permissions, dict):
                # New format: dict of program -> permission level
                accessible_program_names = list(program_permissions.keys())
            else:
                accessible_program_names = []
                
            filtered_items = [
                program for program in all_items 
                if program.get("name") in accessible_program_names
            ]
            filtered_count = len(filtered_items)

        # Calculate pagination
        total_pages = (filtered_count + request.page_size - 1) // request.page_size if request.page_size > 0 else 1
        
        return {
            "status": "success",
            "pagination": {
                "total_items": filtered_count,
                "total_pages": total_pages,
                "current_page": request.page,
                "page_size": request.page_size,
                "has_next": request.page < total_pages,
                "has_previous": request.page > 1,
            },
            "items": filtered_items,
        }
    except Exception as e:
        logger.error(f"Error executing typed program search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed program search: {str(e)}")

@router.post("/import/hackerone", response_model=HackerOneImportResponse)
async def import_from_hackerone(
    request: HackerOneImportRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Import a program from HackerOne API
    
    This endpoint:
    1. Fetches the user's HackerOne API credentials
    2. Retrieves the program's structured scope from HackerOne
    3. Converts scope items (URLs and wildcards) to regex patterns
    4. Creates a new program with name H1_<handle>
    
    Args:
        request: Contains the HackerOne program handle
        current_user: Current authenticated user (injected)
        
    Returns:
        Import status with program name and scope summary
        
    Raises:
        HTTPException: 
            - 403: User doesn't have permission to create programs
            - 400: Missing HackerOne credentials or invalid program handle
            - 401: Invalid HackerOne API credentials
            - 404: Program not found on HackerOne
            - 409: Program already exists locally
            - 500: Other errors
    """
    try:
        # Check if user has permission to create programs
        if not (current_user.is_superuser or (current_user.roles and "admin" in current_user.roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrative privileges required to import programs",
            )
        
        # Check if user has HackerOne credentials configured
        if not current_user.hackerone_api_user or not current_user.hackerone_api_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="HackerOne API credentials not configured. Please add your credentials in your user profile settings.",
            )
        
        program_handle = request.program_handle.strip()
        program_name = f"H1_{program_handle}"
        
        # Check if program already exists
        existing_program = await ProgramRepository.get_program_by_name(program_name)
        if existing_program:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Program '{program_name}' already exists. Delete it first if you want to re-import.",
            )
        
        logger.info(f"Starting HackerOne import for program '{program_handle}' by user '{current_user.username}'")
        
        # Initialize HackerOne service with user's credentials
        h1_service = HackerOneService(
            username=current_user.hackerone_api_user,
            api_token=current_user.hackerone_api_token
        )
        
        # Fetch program scope from HackerOne
        logger.info(f"Fetching scope for program '{program_handle}' from HackerOne API...")
        scopes = await h1_service.fetch_program_scope(program_handle)
        
        if not scopes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scope data found for program '{program_handle}' on HackerOne. The program may not exist or may not have any structured scope defined.",
            )
        
        # Convert scope to regex patterns
        logger.info(f"Converting {len(scopes)} scope items to regex patterns...")
        in_scope_regexes, out_of_scope_regexes, summary = h1_service.convert_scope_to_regex(scopes)
        
        if not in_scope_regexes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No valid in-scope domains found for program '{program_handle}'. The program may not have any bounty-eligible URL/WILDCARD scopes.",
            )
        
        # Create program with converted scope
        program_data = {
            "name": program_name,
            "domain_regex": in_scope_regexes,
            "out_of_scope_regex": out_of_scope_regexes,
            "cidr_list": [],
            "safe_registrar": [],
            "safe_ssl_issuer": []
        }
        
        logger.info(f"Creating program '{program_name}' with {summary['in_scope']} in-scope and {summary['out_of_scope']} out-of-scope patterns...")
        program_id = await ProgramRepository.create_program(program_data, restore_from_archive=False)
        
        if not program_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create program. Please try again.",
            )
        
        logger.info(f"Successfully imported program '{program_name}' from HackerOne")
        
        return HackerOneImportResponse(
            status="success",
            program_name=program_name,
            message=f"Successfully imported program '{program_name}' with {summary['in_scope']} in-scope domains and {summary['out_of_scope']} out-of-scope domains.",
            scope_summary=summary
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as ve:
        # ValueError is raised by HackerOneService for known errors
        logger.warning(f"HackerOne import validation error: {str(ve)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception(f"Unexpected error importing from HackerOne: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while importing from HackerOne: {str(e)}"
        )

@router.post("/import/yeswehack", response_model=YesWeHackImportResponse)
async def import_from_yeswehack(
    request: YesWeHackImportRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Import a program from YesWeHack API
    
    This endpoint:
    1. Uses the provided JWT token to authenticate with YesWeHack
    2. Retrieves the program's scope details from YesWeHack
    3. Converts scope items (URLs and wildcards) to regex patterns
    4. Creates a new program with name YWH_<slug>
    
    Note: Unlike HackerOne, YesWeHack uses JWT tokens that are provided
    per-import rather than stored in user profile. The JWT should be
    stored in the frontend's localStorage for reuse.
    
    Args:
        request: Contains the YesWeHack program slug and JWT token
        current_user: Current authenticated user (injected)
        
    Returns:
        Import status with program name and scope summary
        
    Raises:
        HTTPException: 
            - 403: User doesn't have permission to create programs
            - 400: Invalid JWT or program slug
            - 401: Invalid YesWeHack JWT token
            - 404: Program not found on YesWeHack
            - 409: Program already exists locally
            - 500: Other errors
    """
    try:
        # Check if user has permission to create programs
        if not (current_user.is_superuser or (current_user.roles and "admin" in current_user.roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrative privileges required to import programs",
            )
        
        program_slug = request.program_slug.strip()
        program_name = f"YWH_{program_slug}"
        
        # Check if program already exists
        existing_program = await ProgramRepository.get_program_by_name(program_name)
        if existing_program:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Program '{program_name}' already exists. Delete it first if you want to re-import.",
            )
        
        logger.info(f"Starting YesWeHack import for program '{program_slug}' by user '{current_user.username}'")
        
        # Initialize YesWeHack service with provided JWT
        ywh_service = YesWeHackService(jwt_token=request.jwt_token)
        
        # Validate JWT is present
        if not ywh_service.validate_jwt():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JWT token provided. Please provide a valid YesWeHack JWT token.",
            )
        
        # Fetch program details from YesWeHack
        logger.info(f"Fetching program details for '{program_slug}' from YesWeHack API...")
        program_data = await ywh_service.fetch_program_details(program_slug)
        
        if not program_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data found for program '{program_slug}' on YesWeHack.",
            )
        
        # Extract scopes from program data
        scopes = program_data.get('scopes', [])
        
        if not scopes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No scopes found for program '{program_slug}' on YesWeHack.",
            )
        
        # Convert scopes to regex patterns and extract CIDR blocks
        logger.info(f"Converting {len(scopes)} scope items to regex patterns...")
        in_scope_regexes, out_of_scope_regexes, cidr_blocks, summary = ywh_service.convert_scopes_to_regex(scopes)
        
        if not in_scope_regexes and not cidr_blocks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No valid in-scope domains or CIDR blocks found for program '{program_slug}'. The program may not have any web application scopes.",
            )
        
        # Create program with converted scope
        program_create_data = {
            "name": program_name,
            "domain_regex": in_scope_regexes,
            "out_of_scope_regex": out_of_scope_regexes,
            "cidr_list": cidr_blocks,
            "safe_registrar": [],
            "safe_ssl_issuer": []
        }
        
        logger.info(f"Creating program '{program_name}' with {summary['in_scope']} in-scope, {summary['out_of_scope']} out-of-scope patterns, and {summary['cidr_blocks']} CIDR blocks...")
        program_id = await ProgramRepository.create_program(program_create_data, restore_from_archive=False)
        
        if not program_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create program. Please try again.",
            )
        
        logger.info(f"Successfully imported program '{program_name}' from YesWeHack")
        
        # Build descriptive message
        message_parts = []
        if summary['in_scope'] > 0:
            message_parts.append(f"{summary['in_scope']} in-scope domain{'s' if summary['in_scope'] != 1 else ''}")
        if summary['cidr_blocks'] > 0:
            message_parts.append(f"{summary['cidr_blocks']} CIDR block{'s' if summary['cidr_blocks'] != 1 else ''}")
        
        message = f"Successfully imported program '{program_name}' ({program_data.get('title', program_slug)})"
        if message_parts:
            message += f" with {' and '.join(message_parts)}."
        else:
            message += "."
        
        return YesWeHackImportResponse(
            status="success",
            program_name=program_name,
            message=message,
            scope_summary=summary
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as ve:
        # ValueError is raised by YesWeHackService for known errors
        logger.warning(f"YesWeHack import validation error: {str(ve)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception(f"Unexpected error importing from YesWeHack: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while importing from YesWeHack: {str(e)}"
        )

@router.post("/import/intigriti", response_model=IntigritiImportResponse)
async def import_from_intigriti(
    request: IntigritiImportRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Import a bug bounty program from Intigriti
    
    This endpoint:
    1. Searches for the program by handle on Intigriti
    2. Fetches the program's detailed scope
    3. Converts scope items (Url, Wildcard, IpRange) to regex patterns
    4. Creates a new program with the name `INTI_<handle>`
    
    **Requirements**:
    - User must have Intigriti API token configured in their profile
    - User must be superuser or admin
    - Program must not already exist
    
    **Scope Conversion**:
    - `Url` type → Exact domain regex
    - `Wildcard` type → Wildcard domain regex  
    - `IpRange` type → Added to cidr_list (comma-separated IPs or CIDR blocks)
    - Tier filtering: "Out Of Scope" and "No Bounty" → out_of_scope_regex
    """
    try:
        # Check user permissions
        if not (current_user.is_superuser or "admin" in current_user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers and admins can import programs from Intigriti."
            )
        
        # Check if user has Intigriti API token
        if not current_user.intigriti_api_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Intigriti API token not configured. Please add your Intigriti API token in your user profile settings."
            )
        
        logger.info(f"Starting Intigriti import for program handle: {request.program_handle}")
        
        # Initialize Intigriti service
        intigriti_service = IntigritiService(current_user.intigriti_api_token)
        
        # Find program by handle
        logger.info(f"Searching for Intigriti program by handle: {request.program_handle}")
        program = await intigriti_service.find_program_by_handle(request.program_handle)
        
        if not program:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Program with handle '{request.program_handle}' not found on Intigriti. Please check the program handle."
            )
        
        program_id = program.get("id")
        program_handle = program.get("handle")
        program_title = program.get("name")
        
        # Check if program already exists
        program_name = f"INTI_{program_handle}"
        existing_program = await ProgramRepository.get_program_by_name(program_name)
        
        if existing_program:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Program '{program_name}' already exists. Delete it first if you want to re-import."
            )
        
        # Fetch program details
        logger.info(f"Fetching Intigriti program details for ID: {program_id}")
        program_data = await intigriti_service.fetch_program_details(program_id)
        
        # Get domains/scopes
        domains_data = program_data.get("domains", {})
        scopes = domains_data.get("content", [])
        
        if not scopes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No scopes found for program '{program_handle}' on Intigriti."
            )
        
        # Convert scopes to regex patterns and extract IP ranges
        logger.info(f"Converting {len(scopes)} scope items to regex patterns...")
        in_scope_regexes, out_of_scope_regexes, ip_list, summary = intigriti_service.convert_scopes_to_regex(domains_data)
        
        if not in_scope_regexes and not ip_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No valid in-scope domains or IP ranges found for program '{program_handle}'. All scopes may be 'Out Of Scope' or 'No Bounty'."
            )
        
        # Create program with converted scope
        program_create_data = {
            "name": program_name,
            "domain_regex": in_scope_regexes,
            "out_of_scope_regex": out_of_scope_regexes,
            "cidr_list": ip_list,
            "safe_registrar": [],
            "safe_ssl_issuer": []
        }
        
        logger.info(f"Creating program '{program_name}' with {summary['in_scope']} in-scope, {summary['out_of_scope']} out-of-scope patterns, and {summary['ip_ranges']} IP ranges...")
        program_id = await ProgramRepository.create_program(program_create_data, restore_from_archive=False)
        
        if not program_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create program. Please try again."
            )
        
        logger.info(f"Successfully imported program '{program_name}' from Intigriti")
        
        # Build descriptive message
        message_parts = []
        if summary['in_scope'] > 0:
            message_parts.append(f"{summary['in_scope']} in-scope domain{'s' if summary['in_scope'] != 1 else ''}")
        if summary['ip_ranges'] > 0:
            message_parts.append(f"{summary['ip_ranges']} IP range{'s' if summary['ip_ranges'] != 1 else ''}")
        
        message = f"Successfully imported program '{program_name}' ({program_title})"
        if message_parts:
            message += f" with {' and '.join(message_parts)}."
        else:
            message += "."
        
        return IntigritiImportResponse(
            status="success",
            program_name=program_name,
            message=message,
            scope_summary=summary
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as ve:
        # ValueError is raised by IntigritiService for known errors
        logger.warning(f"Intigriti import validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error during Intigriti import: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during import: {str(e)}"
        )

@router.post("/import/bugcrowd", response_model=BugcrowdImportResponse)
async def import_from_bugcrowd(
    request: BugcrowdImportRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Import a bug bounty program from Bugcrowd
    
    This endpoint:
    1. Uses the provided session token to fetch program scope from Bugcrowd
    2. Retrieves target groups and individual targets
    3. Converts targets (website, api, other) to regex patterns
    4. Creates a new program with the name `BC_<program_code>`
    
    **Requirements**:
    - User must be superuser or admin
    - Must provide valid Bugcrowd session token
    - Program must not already exist
    
    **Scope Conversion**:
    - `website` category → Domain regex
    - `api` category → Domain regex
    - `other` category → Wildcard regex or IP list
    - In-scope vs Out-of-scope based on target group settings
    """
    try:
        # Check user permissions
        if not (current_user.is_superuser or "admin" in current_user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers and admins can import programs from Bugcrowd."
            )
        
        logger.info(f"Starting Bugcrowd import for program: {request.program_code}")
        
        # Initialize Bugcrowd service
        bugcrowd_service = BugcrowdService(request.session_token)
        
        # Validate session token
        if not bugcrowd_service.validate_session_token(request.session_token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Bugcrowd session token format."
            )
        
        # Check if program already exists
        program_name = f"BC_{request.program_code}"
        existing_program = await ProgramRepository.get_program_by_name(program_name)
        
        if existing_program:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Program '{program_name}' already exists. Delete it first if you want to re-import."
            )
        
        # Fetch program scope from Bugcrowd
        logger.info(f"Fetching Bugcrowd program scope for: {request.program_code}")
        scope_data = await bugcrowd_service.fetch_program_scope(request.program_code)
        
        if not scope_data.get("in_scope") and not scope_data.get("out_of_scope"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No scope found for program '{request.program_code}' on Bugcrowd."
            )
        
        # Convert scope to regex patterns and extract IP ranges
        logger.info("Converting scope to regex patterns...")
        in_scope_regexes, out_of_scope_regexes, ip_list, summary = bugcrowd_service.convert_targets_to_regex(scope_data)
        
        if not in_scope_regexes and not ip_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No valid in-scope domains or IP ranges found for program '{request.program_code}'."
            )
        
        # Create program with converted scope
        program_create_data = {
            "name": program_name,
            "domain_regex": in_scope_regexes,
            "out_of_scope_regex": out_of_scope_regexes,
            "cidr_list": ip_list,
            "safe_registrar": [],
            "safe_ssl_issuer": []
        }
        
        logger.info(f"Creating program '{program_name}' with {summary['in_scope']} in-scope, {summary['out_of_scope']} out-of-scope patterns, and {summary['ip_ranges']} IP ranges...")
        program_id = await ProgramRepository.create_program(program_create_data, restore_from_archive=False)
        
        if not program_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create program. Please try again."
            )
        
        logger.info(f"Successfully imported program '{program_name}' from Bugcrowd")
        
        # Build descriptive message
        message_parts = []
        if summary['in_scope'] > 0:
            message_parts.append(f"{summary['in_scope']} in-scope domain{'s' if summary['in_scope'] != 1 else ''}")
        if summary['ip_ranges'] > 0:
            message_parts.append(f"{summary['ip_ranges']} IP range{'s' if summary['ip_ranges'] != 1 else ''}")
        
        message = f"Successfully imported program '{program_name}'"
        if message_parts:
            message += f" with {' and '.join(message_parts)}."
        else:
            message += "."
        
        return BugcrowdImportResponse(
            status="success",
            program_name=program_name,
            message=message,
            scope_summary=summary
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as ve:
        # ValueError is raised by BugcrowdService for known errors
        logger.warning(f"Bugcrowd import validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error during Bugcrowd import: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during import: {str(e)}"
        )
