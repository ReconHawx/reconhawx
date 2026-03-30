from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Optional
import logging
import io

from repository import WordlistsRepository
from models.wordlist import (
    WordlistUpdate,
    WordlistResponse,
    WordlistListResponse,
    WordlistCreateResponse,
    WordlistUpdateResponse,
    DynamicWordlistCreate,
    DynamicWordlistCreateResponse
)
from auth.dependencies import get_current_user_from_middleware
from models.user_postgres import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize repository
wordlist_repository = WordlistsRepository()

# === WORDLIST MANAGEMENT ENDPOINTS ===

@router.post("", response_model=WordlistCreateResponse)
@router.post("/", response_model=WordlistCreateResponse)
async def upload_wordlist(
    file: UploadFile = File(..., description="Wordlist file to upload"),
    name: str = Form(..., description="Name for the wordlist"),
    description: Optional[str] = Form(None, description="Description of the wordlist"),
    tags: Optional[str] = Form(None, description="Comma-separated tags"),
    program_name: Optional[str] = Form(None, description="Program this wordlist belongs to"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Upload a new wordlist file"""
    try:
        # Validate file type
        if not file.content_type or file.content_type not in ['text/plain', 'text/csv']:
            raise HTTPException(
                status_code=400,
                detail="Only text files (.txt, .csv) are allowed"
            )
        
        # Validate file size (max 50MB)
        max_size = 50 * 1024 * 1024  # 50MB
        file_content = await file.read()
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=400,
                detail="File size too large. Maximum size is 50MB"
            )
        
        # Basic file validation
        if len(file_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="File is empty"
            )
        
        # Parse tags
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Filter by user program permissions
        if program_name and hasattr(current_user, 'program_permissions') and current_user.program_permissions:
            if program_name not in current_user.program_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to upload wordlists to program {program_name}"
                )
        
        # Create wordlist data
        wordlist_data = {
            'name': name,
            'description': description,
            'tags': tag_list,
            'program_name': program_name
        }
        
        # Store wordlist
        result = await wordlist_repository.create_wordlist(
            wordlist_data=wordlist_data,
            file_content=file_content,
            filename=file.filename or "wordlist.txt",
            content_type=file.content_type,
            created_by=current_user.username
        )
        
        if not result:
            raise HTTPException(
                status_code=400,
                detail="Failed to create wordlist. A wordlist with this name may already exist."
            )
        
        return WordlistCreateResponse(
            id=result["id"],
            name=result["name"],
            filename=result["filename"],
            file_size=result["file_size"],
            word_count=result["word_count"],
            status="success",
            message="Wordlist uploaded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading wordlist: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dynamic", response_model=DynamicWordlistCreateResponse)
async def create_dynamic_wordlist(
    wordlist_data: DynamicWordlistCreate,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Create a new dynamic wordlist.
    
    Dynamic wordlists generate their content on-the-fly from program assets.
    
    Supported dynamic types:
    - subdomain_prefixes: Extracts subdomain prefixes from program's subdomain assets
      (e.g., "sub1.domain.com" with apex "domain.com" yields "sub1")
    
    The wordlist content is generated each time it is downloaded, ensuring
    it always reflects the current state of program assets.
    """
    try:
        # Check program permissions
        if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
            if wordlist_data.program_name not in current_user.program_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to create wordlists for program {wordlist_data.program_name}"
                )
        
        # Parse tags
        tag_list = wordlist_data.tags or []
        
        # Create dynamic wordlist
        result = await wordlist_repository.create_dynamic_wordlist(
            name=wordlist_data.name,
            dynamic_type=wordlist_data.dynamic_type.value,
            program_name=wordlist_data.program_name,
            description=wordlist_data.description,
            tags=tag_list,
            created_by=current_user.username
        )
        
        if not result:
            raise HTTPException(
                status_code=400,
                detail="Failed to create dynamic wordlist. A wordlist with this name may already exist, or the program was not found."
            )
        
        return DynamicWordlistCreateResponse(
            id=result["id"],
            name=result["name"],
            dynamic_type=result["dynamic_type"],
            program_name=result["program_name"],
            word_count=result["word_count"],
            status="success",
            message=f"Dynamic wordlist created successfully with {result['word_count']} entries"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error creating dynamic wordlist: {error_msg}")
        import traceback
        traceback.print_exc()
        # Provide more helpful error messages
        if "migration" in error_msg.lower():
            raise HTTPException(status_code=500, detail=error_msg)
        raise HTTPException(status_code=500, detail=f"Error creating dynamic wordlist: {error_msg}")


@router.get("", response_model=WordlistListResponse)
@router.get("/", response_model=WordlistListResponse)
async def list_wordlists(
    skip: int = Query(0, ge=0, description="Number of wordlists to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of wordlists to return"),
    active_only: bool = Query(True, description="Return only active wordlists"),
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags to filter by"),
    search: Optional[str] = Query(None, description="Search term for wordlist name or description"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """List wordlists with optional filtering and pagination"""
    try:
        # Parse tags if provided
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Filter by user program permissions
        if program_name and hasattr(current_user, 'program_permissions') and current_user.program_permissions:
            if program_name not in current_user.program_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to access wordlists from program {program_name}"
                )
        
        # Get wordlists
        result = await wordlist_repository.list_wordlists(
            skip=skip,
            limit=limit,
            active_only=active_only,
            program_name=program_name,
            tags=tag_list,
            search=search
        )
        
        # Convert to response format
        wordlists = []
        for wordlist in result.get("wordlists", []):
            wordlists.append(WordlistResponse(**wordlist))
        
        return WordlistListResponse(
            wordlists=wordlists,
            total=result.get("total", 0),
            page=skip // limit + 1 if limit > 0 else 1,
            limit=limit
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing wordlists: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{wordlist_id}/download")
async def download_wordlist(
    wordlist_id: str#,
    #current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Download a wordlist file"""
    try:
        # Get wordlist metadata first to check permissions
        wordlist = await wordlist_repository.get_wordlist(wordlist_id)
        
        if not wordlist:
            raise HTTPException(
                status_code=404,
                detail="Wordlist not found"
            )
        
        # # Check program permissions
        # if wordlist.get("program_name") and hasattr(current_user, 'program_permissions') and current_user.program_permissions:
        #     if wordlist["program_name"] not in current_user.program_permissions:
        #         raise HTTPException(
        #             status_code=403,
        #             detail=f"You don't have permission to access this wordlist"
        #         )
        
        # Get file content
        file_data = await wordlist_repository.get_wordlist_file(wordlist_id)
        
        if not file_data:
            raise HTTPException(
                status_code=404,
                detail="Wordlist file not found"
            )
        
        # Return the file as a streaming response
        return StreamingResponse(
            io.BytesIO(file_data["content"]),
            media_type=file_data["content_type"],
            headers={
                "Content-Disposition": f"attachment; filename={file_data['filename']}",
                "Content-Length": str(file_data["file_size"])
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading wordlist {wordlist_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{wordlist_id}", response_model=WordlistResponse)
async def get_wordlist(
    wordlist_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Get a specific wordlist by ID"""
    try:
        wordlist = await wordlist_repository.get_wordlist(wordlist_id)
        
        if not wordlist:
            raise HTTPException(
                status_code=404,
                detail="Wordlist not found"
            )
        
        # Check program permissions
        if wordlist.get("program_name") and hasattr(current_user, 'program_permissions') and current_user.program_permissions:
            if wordlist["program_name"] not in current_user.program_permissions:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have permission to access this wordlist"
                )
        
        return WordlistResponse(**wordlist)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting wordlist {wordlist_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{wordlist_id}", response_model=WordlistUpdateResponse)
async def update_wordlist(
    wordlist_id: str,
    wordlist_data: WordlistUpdate,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Update wordlist metadata"""
    try:
        # Get existing wordlist to check permissions
        existing = await wordlist_repository.get_wordlist(wordlist_id)
        
        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Wordlist not found"
            )
        
        # Check program permissions
        if existing.get("program_name") and hasattr(current_user, 'program_permissions') and current_user.program_permissions:
            if existing["program_name"] not in current_user.program_permissions:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have permission to modify this wordlist"
                )
        
        # Check if user is admin or the creator
        if not current_user.is_superuser and existing.get("created_by") != current_user.username:
            raise HTTPException(
                status_code=403,
                detail="You can only modify wordlists you created"
            )
        
        # Update wordlist
        update_data = {}
        if wordlist_data.name is not None:
            update_data['name'] = wordlist_data.name
        if wordlist_data.description is not None:
            update_data['description'] = wordlist_data.description
        if wordlist_data.tags is not None:
            update_data['tags'] = wordlist_data.tags
        if wordlist_data.program_name is not None:
            update_data['program_name'] = wordlist_data.program_name
        if wordlist_data.is_active is not None:
            update_data['is_active'] = wordlist_data.is_active
        
        success = await wordlist_repository.update_wordlist(wordlist_id, update_data)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to update wordlist"
            )
        
        return WordlistUpdateResponse(
            id=wordlist_id,
            name=existing["name"],
            status="success",
            message="Wordlist updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating wordlist {wordlist_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{wordlist_id}")
async def delete_wordlist(
    wordlist_id: str,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """Delete a wordlist"""
    try:
        # Get existing wordlist to check permissions
        existing = await wordlist_repository.get_wordlist(wordlist_id)
        
        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Wordlist not found"
            )
        
        # Check program permissions
        if existing.get("program_name") and hasattr(current_user, 'program_permissions') and current_user.program_permissions:
            if existing["program_name"] not in current_user.program_permissions:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have permission to delete this wordlist"
                )
        
        # Check if user is admin or the creator
        if not current_user.is_superuser and existing.get("created_by") != current_user.username:
            raise HTTPException(
                status_code=403,
                detail="You can only delete wordlists you created"
            )
        
        # Delete wordlist
        success = await wordlist_repository.delete_wordlist(wordlist_id)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to delete wordlist"
            )
        
        return {
            "status": "success",
            "message": "Wordlist deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting wordlist {wordlist_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
