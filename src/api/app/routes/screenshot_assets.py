from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List, Literal, Union
from repository import ScreenshotRepository
from pydantic import BaseModel, Field
from auth.dependencies import get_current_user, get_user_accessible_programs
from models.user_postgres import UserResponse
import logging
import io
from PIL import Image

logger = logging.getLogger(__name__)

router = APIRouter()

# Typed Screenshots search
class ScreenshotsSearchRequest(BaseModel):
    search_url: Optional[str] = Field(None, description="Substring match on URL")
    exact_match: Optional[str] = Field(None, description="Exact match on URL")
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program(s) within user's access scope")
    sort_by: Literal['url','file_size','upload_date','last_captured_at'] = 'upload_date'
    sort_dir: Literal['asc','desc'] = 'desc'
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)

@router.post("/screenshot/search", response_model=Dict[str, Any])
async def search_screenshots_typed(request: ScreenshotsSearchRequest, current_user: UserResponse = Depends(get_current_user)):
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
        result = await ScreenshotRepository.search_screenshots_typed(
            search_url=request.search_url,
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
        logger.error(f"Error executing typed screenshots search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed screenshots search: {str(e)}")

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

@router.post("/screenshot", response_model=Dict[str, Any])
async def upload_screenshot(
    file: UploadFile = File(...),
    program_name: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    workflow_id: Optional[str] = Form(None),
    step_name: Optional[str] = Form(None),
    extracted_text: Optional[str] = Form(None),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Upload a screenshot to the dedicated screenshots database
    
    Args:
        file: The screenshot image file to upload
        program_name: Associated program name
        url: URL associated with the screenshot
        workflow_id: Workflow ID that generated the screenshot
        step_name: Step name that generated the screenshot
        bucket_type: Kept for backward compatibility (not used)
    """
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Only image files are allowed"
            )
        
        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        file_content = await file.read()
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=400,
                detail="File size too large. Maximum size is 10MB"
            )
        
        # Basic file validation
        if len(file_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="File is empty"
            )
        
        # Validate common image content types
        allowed_content_types = [
            'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 
            'image/bmp', 'image/webp', 'image/tiff', 'image/svg+xml'
        ]
        if file.content_type not in allowed_content_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported image type: {file.content_type}. Allowed types: {', '.join(allowed_content_types)}"
            )
        
        # Check if this is a duplicate before storing (per-URL deduplication)
        import hashlib
        image_hash = hashlib.sha256(file_content).hexdigest()
        existing_file_doc = await ScreenshotRepository._find_existing_screenshot_by_hash(image_hash, url)
        
        # Store the screenshot in the dedicated screenshots database
        file_id = await ScreenshotRepository.store_screenshot(
            image_data=file_content,
            filename=file.filename or "screenshot.png",
            content_type=file.content_type,
            program_name=program_name,
            url=url,
            workflow_id=workflow_id,
            step_name=step_name,
            extracted_text=extracted_text
        )
        
        # Determine if this was a duplicate for this URL
        is_duplicate = existing_file_doc is not None
        message = "Screenshot uploaded successfully" if not is_duplicate else "Duplicate screenshot detected for this URL, capture timestamp updated"
        
        return {
            "status": "success",
            "message": message,
            "data": {
                "file_id": file_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size": len(file_content),
                "program_name": program_name,
                "url": url,
                "workflow_id": workflow_id,
                "step_name": step_name,
                "is_duplicate": is_duplicate,
                "image_hash": image_hash
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/screenshot/{file_id}")
async def get_screenshot(
    file_id: str, 
    thumbnail: Optional[int] = Query(None, ge=50, le=800, description="Generate thumbnail with max dimension (50-800px)"),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Retrieve a screenshot from the dedicated screenshots database
    
    Args:
        file_id: GridFS file ID
        bucket_type: Kept for backward compatibility (not used)
        thumbnail: Generate thumbnail with max dimension in pixels (50-800)
    """
    try:
        # Get the screenshot from the dedicated database
        screenshot_data = await ScreenshotRepository.get_screenshot(file_id)
        
        if not screenshot_data:
            raise HTTPException(status_code=404, detail="Screenshot not found")
        
        image_data = screenshot_data["file_content"]
        content_type = screenshot_data["content_type"]
        filename = screenshot_data["filename"]
        
        # Generate thumbnail if requested
        if thumbnail:
            try:
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
                
            except Exception as e:
                logger.warning(f"Failed to generate thumbnail for {file_id}: {str(e)}")
                # Fall back to original image if thumbnail generation fails
        
        # Return the screenshot as a streaming response
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
        logger.error(f"Error retrieving screenshot {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/screenshot", response_model=Dict[str, Any])
async def list_screenshots(
    program_name: Optional[str] = Query(None),
    url: Optional[str] = Query(None),
    workflow_id: Optional[str] = Query(None),
    step_name: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    skip: int = Query(0, ge=0),
    sort: Optional[str] = Query(None, description="Sort field, prefix with '-' for descending (e.g., '-upload_date')")
):
    """
    List screenshots with optional filtering
    
    Args:
        program_name: Filter by program name
        url: Filter by URL
        workflow_id: Filter by workflow ID
        step_name: Filter by step name
        bucket_type: Kept for backward compatibility (not used)
        limit: Maximum number of results (1-100)
        skip: Number of results to skip
    """
    try:
        # Parse sort parameter
        sort_dict = {}
        if sort:
            if sort.startswith('-'):
                sort_dict[sort[1:]] = -1  # Descending
            else:
                sort_dict[sort] = 1  # Ascending
        
        # Get screenshots list from the dedicated database
        screenshots = await ScreenshotRepository.list_screenshots(
            program_name=program_name,
            url=url,
            workflow_id=workflow_id,
            step_name=step_name,
            limit=limit,
            skip=skip,
            sort=sort_dict
        )
        
        # Get total count for pagination
        total_count = await ScreenshotRepository.get_screenshots_count(
            program_name=program_name,
            url=url,
            workflow_id=workflow_id,
            step_name=step_name
        )
        
        # Calculate pagination metadata
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing screenshots: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/screenshot/batch", response_model=Dict[str, Any])
async def delete_screenshots_batch(
    screenshot_ids: List[str],
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Delete multiple screenshots from the screenshots database
    
    Args:
        screenshot_ids: List of screenshot IDs (metadata IDs) to delete
    """
    try:
        deleted_count = 0
        failed_ids = []
        
        for screenshot_id in screenshot_ids:
            try:
                deleted = await ScreenshotRepository.delete_screenshot(screenshot_id)
                if deleted:
                    deleted_count += 1
                else:
                    failed_ids.append(screenshot_id)
            except Exception as e:
                logger.error(f"Error deleting screenshot {screenshot_id}: {str(e)}")
                failed_ids.append(screenshot_id)
        
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} screenshots",
            "data": {
                "deleted_count": deleted_count,
                "failed_ids": failed_ids,
                "total_requested": len(screenshot_ids)
            }
        }
        
    except Exception as e:
        logger.error(f"Error in batch screenshot deletion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/screenshot/{screenshot_id}", response_model=Dict[str, Any])
async def delete_screenshot(
    screenshot_id: str, 
    bucket_type: str = Query("assets"),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Delete a screenshot from the screenshots database
    
    Args:
        screenshot_id: Screenshot ID (metadata ID)
        bucket_type: Kept for backward compatibility (not used)
    """
    try:
        # Delete the screenshot from the dedicated database
        deleted = await ScreenshotRepository.delete_screenshot(screenshot_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Screenshot not found")
        
        return {
            "status": "success",
            "message": "Screenshot deleted successfully",
            "data": {
                "screenshot_id": screenshot_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting screenshot {screenshot_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/screenshot/{screenshot_id}/metadata", response_model=Dict[str, Any])
async def get_screenshot_metadata(
    screenshot_id: str, 
    bucket_type: str = Query("assets"),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get screenshot metadata without downloading the file
    
    Args:
        screenshot_id: Screenshot ID (metadata ID)
        bucket_type: Kept for backward compatibility (not used)
    """
    try:
        # Get metadata from the dedicated database
        metadata = await ScreenshotRepository.get_screenshot_metadata(screenshot_id)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="Screenshot not found")
        
        return {
            "status": "success",
            "data": metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting screenshot metadata {screenshot_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/screenshot/stats/duplicates", response_model=Dict[str, Any])
async def get_screenshot_duplicate_stats(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get statistics about duplicate screenshots in the database
    
    Returns information about:
    - Total screenshots
    - Number of unique images
    - Number of duplicate groups
    - Potential space savings
    - Duplicate percentage
    """
    try:
        # Get duplicate statistics from the repository
        stats = await ScreenshotRepository.get_screenshot_duplicate_stats()
        
        return {
            "status": "success",
            "data": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting screenshot duplicate stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/screenshot/distinct/{field_name}", response_model=List[str])
async def get_distinct_screenshot_field_values(
    field_name: str,
    query: Optional[DistinctRequest] = None,
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Get distinct values for a specified field in screenshot assets, optionally applying a filter.
    Note: This is a placeholder implementation since screenshot model is not fully implemented.
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
        distinct_values = await ScreenshotRepository.get_distinct_values(field_name, filter_data)
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
