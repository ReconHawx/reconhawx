from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List, Literal, Union
from repository import ProgramRepository, UrlAssetsRepository
from pydantic import BaseModel, Field
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs, require_admin_or_manager
from models.user_postgres import UserResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Typed URLs search
class URLsSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Substring search on full URL")
    exact_match: Optional[str] = Field(None, description="Exact match on full URL")
    protocol: Optional[Literal['http','https']] = Field(None, description="Protocol filter")
    status_code: Optional[int] = Field(None, description="HTTP status code filter")
    hostname: Optional[str] = Field(None, description="Hostname filter")
    only_root: Optional[bool] = Field(None, description="Only path = '/' ")
    technology_text: Optional[str] = Field(None, description="Substring search in technologies")
    technology: Optional[str] = Field(None, description="Exact match technology")
    port: Optional[int] = Field(None, description="Port filter")
    unusual_ports: Optional[bool] = Field(None, description="Show only unusual ports (not 80/443)")
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Literal['url','http_status_code','program_name','updated_at','technologies','port'] = 'url'
    sort_dir: Literal['asc','desc'] = 'asc'
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/url/search", response_model=Dict[str, Any])
async def search_urls_typed(request: URLsSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
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
        result = await UrlAssetsRepository.search_urls_typed(
            search=request.search,
            exact_match=request.exact_match,
            protocol=request.protocol,
            hostname=request.hostname,
            status_code=request.status_code,
            only_root=request.only_root,
            technology_text=request.technology_text,
            technology=request.technology,
            port=request.port,
            unusual_ports=request.unusual_ports,
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
        logger.error(f"Error executing typed URLs search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed URLs search: {str(e)}")

# Pydantic models for URL import functionality
class URLImportData(BaseModel):
    url: str = Field(..., description="URL")
    program_name: Optional[str] = Field(None, description="Program name")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    title: Optional[str] = Field(None, description="Page title")
    content_length: Optional[int] = Field(None, description="Content length")
    content_type: Optional[str] = Field(None, description="Content type")
    techs: Optional[List[str]] = Field(None, description="Technologies")
    notes: Optional[str] = Field(None, description="Investigation notes")

class URLImportRequest(BaseModel):
    urls: List[URLImportData] = Field(..., description="List of URLs to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing URLs")
    validate_urls: Optional[bool] = Field(True, description="Whether to validate URL format")

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

@router.get("/url", response_model=Dict[str, Any])
async def get_specific_url(id: Optional[str] = Query(None), current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """List URLs filtered by user program permissions, or return a single URL when 'id' is provided"""
    try:
        if id:
            url_doc = await UrlAssetsRepository.get_url_by_id(id)
            if not url_doc:
                raise HTTPException(status_code=404, detail=f"URL {id} not found")
            url_program = url_doc.get("program_name")
            if url_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and url_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"URL {id} not found")
            return {"status": "success", "data": url_doc}

    except Exception as e:
        logger.error(f"Error listing URLs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/url/import", response_model=Dict[str, Any])
async def import_urls(request: URLImportRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Import multiple URLs from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of URL objects and imports them into the database.
    It supports validation, merging, and batch processing.
    """
    try:
        from urllib.parse import urlparse
        # Validate URLs if requested
        if request.validate_urls:
            invalid_urls = []
            for url_data in request.urls:
                try:
                    parsed = urlparse(url_data.url)
                    if not parsed.scheme or not parsed.netloc:
                        invalid_urls.append(url_data.url)
                except Exception:
                    invalid_urls.append(url_data.url)
            
            if invalid_urls:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid URLs: {', '.join(invalid_urls[:10])}{'...' if len(invalid_urls) > 10 else ''}"
                )
        
        # Filter URLs by user program permissions
        allowed_urls = []
        for url_data in request.urls:
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if url_data.program_name and url_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import URL {url_data.url} to unauthorized program {url_data.program_name}")
                    continue
            allowed_urls.append(url_data)
        
        if not allowed_urls:
            raise HTTPException(
                status_code=403,
                detail="No URLs to import - all URLs belong to programs you don't have access to"
            )
        
        # Process URLs in batches
        imported_count = 0
        errors = []
        
        for url_data in allowed_urls:
            try:
                url_dict = {
                    "url": url_data.url.strip(),
                    "program_name": url_data.program_name,
                    "status_code": url_data.status_code,
                    "title": url_data.title,
                    "content_length": url_data.content_length,
                    "content_type": url_data.content_type,
                    "techs": url_data.techs or [],
                    "notes": url_data.notes
                }
                
                # Remove None values, empty strings, and string "null" values
                url_dict = {k: v for k, v in url_dict.items() if v is not None and v != "" and v != "null"}
                
                # Use create_or_update_url which handles merging automatically
                url_id = await UrlAssetsRepository.create_or_update_url(url_dict)
                if url_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated URL: {url_dict['url']}")
                else:
                    errors.append(f"Failed to create/update URL: {url_dict['url']}")
                        
            except Exception as e:
                error_msg = f"Error processing URL {url_data.url}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create programs if needed
        if imported_count > 0:
            for url_data in allowed_urls:
                if url_data.program_name:
                    program = await UrlAssetsRepository.get_program_by_name(url_data.program_name)
                    if not program:
                        program_data = {"name": url_data.program_name}
                        await ProgramRepository.create_program(program_data)
                        logger.info(f"Created new program: {url_data.program_name}")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Import completed: {imported_count} processed",
            "data": {
                "processed_count": imported_count,
                "total_processed": len(allowed_urls),
                "total_submitted": len(request.urls)
            }
        }
        
        if errors:
            response_data["data"]["errors"] = errors[:10]
            response_data["data"]["error_count"] = len(errors)
            
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no URLs were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        #logger.info(f"URL import completed by user {current_user.username}: {response_data['message']}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in URL import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing URLs: {str(e)}"
        )

# URL notes endpoints
@router.put("/url/{url_id}/notes", response_model=Dict[str, Any])
async def update_url_notes(url_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for a URL"""
    try:
        success = await UrlAssetsRepository.update_url(url_id, {"notes": request.notes})
        
        if not success:
            raise HTTPException(status_code=404, detail="URL not found")
        
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
        logger.error(f"Error updating URL notes {url_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/url/batch", response_model=Dict[str, Any])
async def delete_urls_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple URLs by their IDs"""
    try:
        # Extract asset_ids from request data
        asset_ids = request_data.get("asset_ids", [])
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No asset IDs provided")
        
        result = await UrlAssetsRepository.delete_urls_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for URL assets",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting URL assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/url/{url_id}", response_model=Dict[str, Any])
async def delete_url(
    url_id: str, 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a specific URL by its ID"""
    try:
        deleted = await UrlAssetsRepository.delete_url(url_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"URL with ID {url_id} not found")
        
        return {
            "status": "success",
            "message": f"URL {url_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting URL {url_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/url/distinct/{field_name}", response_model=List[str])
async def get_distinct_url_field_values(
    field_name: str,
    query: Optional[DistinctRequest] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Get distinct values for a specified field in URL assets, optionally applying a filter.
    Allowed fields: hostname, scheme, technologies, extracted_links, content_type, title, port.
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
        distinct_values = await UrlAssetsRepository.get_distinct_values(field_name, filter_data)
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

# Extracted Links management endpoints
class ExtractedLinksRequest(BaseModel):
    links: List[str] = Field(..., description="List of extracted links to add")

@router.post("/url/{url_id}/extracted_links", response_model=Dict[str, Any])
async def add_extracted_links(
    url_id: str,
    request: ExtractedLinksRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Add extracted links to a URL"""
    try:
        # Verify URL exists and user has access
        url_doc = await UrlAssetsRepository.get_url_by_id(url_id)
        if not url_doc:
            raise HTTPException(status_code=404, detail=f"URL {url_id} not found")

        url_program = url_doc.get("program_name")
        if url_program:
            accessible_programs = get_user_accessible_programs(current_user)
            if accessible_programs and url_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"URL {url_id} not found")

        # Add extracted links
        success = await UrlAssetsRepository.add_extracted_links(url_id, request.links)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to add extracted links")

        return {
            "status": "success",
            "message": f"Added {len(request.links)} extracted links to URL",
            "data": {
                "url_id": url_id,
                "links_added": len(request.links)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding extracted links to URL {url_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/url/{url_id}/extracted_links", response_model=Dict[str, Any])
async def get_extracted_links(
    url_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get extracted links for a URL"""
    try:
        # Verify URL exists and user has access
        url_doc = await UrlAssetsRepository.get_url_by_id(url_id)
        if not url_doc:
            raise HTTPException(status_code=404, detail=f"URL {url_id} not found")

        url_program = url_doc.get("program_name")
        if url_program:
            accessible_programs = get_user_accessible_programs(current_user)
            if accessible_programs and url_program not in accessible_programs:
                raise HTTPException(status_code=404, detail=f"URL {url_id} not found")

        return {
            "status": "success",
            "data": {
                "url_id": url_id,
                "url": url_doc.get("url"),
                "extracted_links": url_doc.get("extracted_links", [])
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting extracted links for URL {url_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/url/technologies/summary", response_model=Dict[str, Any])
async def get_technologies_summary(
    program: Optional[str] = Query(None, description="Filter by program name"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(25, ge=1, le=100, description="Number of technologies per page"),
    search: Optional[str] = Query(None, description="Search filter for technology name"),
    sort_by: Optional[Literal['name', 'count']] = Query('count', description="Sort by field"),
    sort_order: Optional[Literal['asc', 'desc']] = Query('desc', description="Sort order"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Get all technologies with their counts and associated URLs.
    Much more efficient than fetching all URLs and parsing client-side.
    Respects user program permissions and optional program filter.
    Supports pagination, search, and sorting for better performance with large datasets.
    """
    try:
        # Get accessible programs for the user
        accessible_programs = get_user_accessible_programs(current_user)
        
        # Determine program filter based on permissions and request
        program_filter = None
        
        if program:
            # User requested specific program - verify they have access
            if accessible_programs and program not in accessible_programs:
                # User doesn't have access to requested program
                if not (current_user.is_superuser or "admin" in current_user.roles):
                    return {
                        "status": "success",
                        "items": [],
                        "pagination": {
                            "total_items": 0,
                            "total_pages": 0,
                            "current_page": page,
                            "page_size": page_size,
                            "has_next": False,
                            "has_prev": False
                        }
                    }
            # Filter to just the requested program
            program_filter = [program]
        elif not (current_user.is_superuser or "admin" in current_user.roles):
            # Non-admin without specific program request - use their accessible programs
            program_filter = accessible_programs if accessible_programs else []
            if not program_filter:
                return {
                    "status": "success",
                    "items": [],
                    "pagination": {
                        "total_items": 0,
                        "total_pages": 0,
                        "current_page": page,
                        "page_size": page_size,
                        "has_next": False,
                        "has_prev": False
                    }
                }
        
        # Get technologies with URLs from repository (with pagination, search, and sort)
        result = await UrlAssetsRepository.get_technologies_with_urls(
            program_filter=program_filter,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return {
            "status": "success",
            **result  # Spread items and pagination
        }
        
    except Exception as e:
        logger.error(f"Error getting technologies summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))