from fastapi import APIRouter, HTTPException, Query, Depends, Path, Body, Response
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import logging
import os
import subprocess
from pathlib import Path as PathLib
import yaml
import json

from auth.dependencies import get_current_user_from_middleware
from repository import NucleiTemplateRepository

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic models for request/response
class NucleiTemplateCreate(BaseModel):
    content: str = Field(..., description="YAML content of the nuclei template")

class NucleiTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Template name")
    author: Optional[str] = Field(None, description="Template author")
    severity: Optional[str] = Field(None, description="Template severity")
    description: Optional[str] = Field(None, description="Template description")
    tags: Optional[List[str]] = Field(None, description="Template tags")
    content: Optional[str] = Field(None, description="YAML content of the nuclei template")

class NucleiTemplateResponse(BaseModel):
    id: str
    name: str
    author: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class NucleiTemplateCreateResponse(BaseModel):
    status: str
    message: str
    template: NucleiTemplateResponse

class NucleiTemplateUpdateResponse(BaseModel):
    status: str
    message: str
    template: NucleiTemplateResponse

class NucleiTemplateListResponse(BaseModel):
    templates: List[NucleiTemplateResponse]
    total: int
    skip: int
    limit: int

# Initialize PostgreSQL repository
NucleiTemplateRepository = NucleiTemplateRepository

@router.post("", response_model=NucleiTemplateCreateResponse)
@router.post("/", response_model=NucleiTemplateCreateResponse)
async def create_nuclei_template(
    template: NucleiTemplateCreate,
    current_user = Depends(get_current_user_from_middleware)
):
    """Create a new nuclei template"""
    try:
        logger.debug(f"Creating nuclei template by user: {current_user.username}")
        
        # Convert Pydantic model to dictionary for repository
        template_dict = template.model_dump()
        
        # Create the template using PostgreSQL repository
        created_template = await NucleiTemplateRepository.create_template(template_dict)
        
        if not created_template:
            raise HTTPException(
                status_code=400,
                detail="Failed to create nuclei template - template may already exist or content is invalid"
            )
        
        logger.debug(f"Successfully created nuclei template with ID: {created_template['id']}")
        
        return NucleiTemplateCreateResponse(
            status="success",
            message=f"Nuclei template created successfully with ID: {created_template['id']}",
            template=NucleiTemplateResponse(**created_template)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating nuclei template: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create nuclei template: {str(e)}"
        )

@router.get("", response_model=NucleiTemplateListResponse)
@router.get("/", response_model=NucleiTemplateListResponse)
async def list_nuclei_templates(
    skip: int = Query(0, ge=0, description="Number of templates to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of templates to return"),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags to filter by"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    search: Optional[str] = Query(None, description="Search term for template name, description, or content"),
    current_user = Depends(get_current_user_from_middleware)
):
    """List nuclei templates with optional filtering"""
    try:
        logger.debug(f"Listing nuclei templates by user: {current_user.username}")
        
        # Parse tags if provided
        tags_list = None
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Get templates using PostgreSQL repository
        result = await NucleiTemplateRepository.list_templates(
            skip=skip,
            limit=limit,
            tags=tags_list,
            severity=severity,
            search=search
        )
        
        # Convert to response format
        templates = [NucleiTemplateResponse(**template) for template in result["templates"]]
        
        return NucleiTemplateListResponse(
            templates=templates,
            total=result["total"],
            skip=result["skip"],
            limit=result["limit"]
        )
        
    except Exception as e:
        logger.error(f"Error listing nuclei templates: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list nuclei templates: {str(e)}"
        )

@router.get("/raw/{template_id}.yaml")
async def get_nuclei_template_raw(
    template_id: str = Path(..., description="ID of the nuclei template to retrieve"),
    #current_user = Depends(get_current_user_from_middleware)
):
    """Get raw YAML content of a nuclei template"""
    try:
        logger.debug(f"Getting raw YAML for nuclei template: {template_id}")
        
        # Get template using PostgreSQL repository
        template = await NucleiTemplateRepository.get_template(template_id)
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Nuclei template {template_id} not found"
            )
        
        # Return raw YAML content with proper content type
        return Response(
            content=template["content"],
            media_type="text/yaml",
            headers={"Content-Disposition": f"attachment; filename={template_id}.yaml"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting raw YAML for nuclei template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get nuclei template YAML: {str(e)}"
        )

@router.get("/{template_id}", response_model=NucleiTemplateResponse)
async def get_nuclei_template(
    template_id: str = Path(..., description="ID of the nuclei template to retrieve"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Get a specific nuclei template by ID"""
    try:
        logger.debug(f"Getting nuclei template {template_id} by user: {current_user.username}")
        
        # Get template using PostgreSQL repository
        template = await NucleiTemplateRepository.get_template(template_id)
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Nuclei template {template_id} not found"
            )
        
        return NucleiTemplateResponse(**template)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting nuclei template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get nuclei template: {str(e)}"
        )

@router.put("/{template_id}", response_model=NucleiTemplateUpdateResponse)
@router.put("/{template_id}/", response_model=NucleiTemplateUpdateResponse)
async def update_nuclei_template(
    template_id: str = Path(..., description="ID of the nuclei template to update"),
    update_data: NucleiTemplateUpdate = Body(...),
    current_user = Depends(get_current_user_from_middleware)
):
    """Update a nuclei template"""
    try:
        logger.debug(f"Updating nuclei template {template_id} by user: {current_user.username}")
        
        # Convert Pydantic model to dictionary for repository
        update_dict = update_data.model_dump(exclude_unset=True)
        
        # Update template using PostgreSQL repository
        updated_template = await NucleiTemplateRepository.update_template(template_id, update_dict)
        
        if not updated_template:
            raise HTTPException(
                status_code=404,
                detail=f"Nuclei template {template_id} not found"
            )
        
        logger.debug(f"Successfully updated nuclei template {template_id}")
        
        return NucleiTemplateUpdateResponse(
            status="success",
            message=f"Nuclei template {template_id} updated successfully",
            template=NucleiTemplateResponse(**updated_template)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating nuclei template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update nuclei template: {str(e)}"
        )

@router.delete("/{template_id}", response_model=Dict[str, str])
@router.delete("/{template_id}/", response_model=Dict[str, str])
async def delete_nuclei_template(
    template_id: str = Path(..., description="ID of the nuclei template to delete"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Delete a nuclei template"""
    try:
        logger.debug(f"Deleting nuclei template {template_id} by user: {current_user.username}")
        
        # Delete template using PostgreSQL repository
        deleted = await NucleiTemplateRepository.delete_template(template_id)
        
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Nuclei template {template_id} not found"
            )
        
        logger.debug(f"Successfully deleted nuclei template {template_id}")
        
        return {
            "status": "success",
            "message": f"Nuclei template {template_id} deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting nuclei template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete nuclei template: {str(e)}"
        )

@router.get("/name/{template_name}", response_model=NucleiTemplateResponse)
async def get_nuclei_template_by_name(
    template_name: str = Path(..., description="Name of the nuclei template to retrieve"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Get a nuclei template by name"""
    try:
        logger.debug(f"Getting nuclei template by name '{template_name}' by user: {current_user.username}")
        
        # Get template by name using PostgreSQL repository
        template = await NucleiTemplateRepository.get_template_by_name(template_name)
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Nuclei template with name '{template_name}' not found"
            )
        
        return NucleiTemplateResponse(**template)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting nuclei template by name '{template_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get nuclei template by name: {str(e)}"
        )

@router.get("/check/{template_id}/exists", response_model=Dict[str, Any])
async def check_template_exists(
    template_id: str = Path(..., description="ID of the nuclei template to check"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Check if a nuclei template exists"""
    try:
        logger.debug(f"Checking existence of nuclei template {template_id} by user: {current_user.username}")
        
        # Check template existence using PostgreSQL repository
        template = await NucleiTemplateRepository.get_template(template_id)
        
        return {
            "exists": template is not None,
            "template_id": template_id,
            "active": template.get("is_active", False) if template else False
        }
        
    except Exception as e:
        logger.error(f"Error checking existence of nuclei template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check template existence: {str(e)}"
        )

# ===== OFFICIAL TEMPLATES ENDPOINTS =====
# These endpoints remain largely unchanged as they work with the filesystem

@router.get("/official/tree", response_model=Dict[str, Any])
async def get_official_templates_tree(
    current_user = Depends(get_current_user_from_middleware)
):
    """Get the complete tree structure of official templates"""
    try:
        logger.debug(f"Getting official templates tree by user: {current_user.username}")
        
        # Try to serve pre-generated tree JSON file first
        tree_json_path = "/opt/nuclei-templates-tree.json"
        
        if os.path.exists(tree_json_path):
            try:
                with open(tree_json_path, 'r', encoding='utf-8') as f:
                    tree_data = json.load(f)
                
                logger.debug(f"Serving pre-generated tree JSON ({os.path.getsize(tree_json_path):,} bytes)")
                return tree_data
                
            except Exception as e:
                logger.warning(f"Failed to read pre-generated tree JSON: {e}, falling back to dynamic generation")
        
        # Fallback to dynamic generation if pre-generated file doesn't exist or is invalid
        logger.debug("Pre-generated tree JSON not found, generating dynamically...")
        tree = await _get_templates_tree()
        return tree
        
    except Exception as e:
        logger.error(f"Error getting official templates tree: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get templates tree: {str(e)}"
        )


@router.get("/official/{path:path}")
async def get_official_nuclei_template_raw(
    path: str = Path(..., description="Path to the official nuclei template file"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Get raw YAML content of an official nuclei template by path"""
    try:
        logger.debug(f"Getting raw YAML for official nuclei template: {path}")
        
        # Construct the full file path
        repo_path = "/opt/nuclei-templates"
        file_path = os.path.join(repo_path, path)
        
        # Security check: ensure the path is within the repo directory
        if not os.path.abspath(file_path).startswith(os.path.abspath(repo_path)):
            raise HTTPException(
                status_code=400,
                detail="Invalid template path"
            )
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"Official nuclei template {path} not found"
            )
        
        # Check if it's a YAML file
        if not (file_path.endswith('.yaml') or file_path.endswith('.yml')):
            raise HTTPException(
                status_code=400,
                detail="File is not a valid nuclei template (must be .yaml or .yml)"
            )
        
        # Read and return the file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading official template file {file_path}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read template file: {str(e)}"
            )
        
        # Return raw YAML content with proper content type
        filename = os.path.basename(file_path)
        return Response(
            content=content,
            media_type="text/yaml",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting raw YAML for official nuclei template {path}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get official nuclei template YAML: {str(e)}"
        )

@router.get("/official/structure", response_model=Dict[str, Any])
async def get_official_templates_structure(
    current_user = Depends(get_current_user_from_middleware)
):
    """Get the structure of official nuclei templates repository"""
    try:
        logger.debug(f"Getting official templates structure by user: {current_user.username}")
        
        structure = await _get_templates_structure()
        return structure
        
    except Exception as e:
        logger.error(f"Error getting official templates structure: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get official templates structure: {str(e)}"
        )

@router.get("/official/categories", response_model=List[str])
async def get_official_template_categories(
    current_user = Depends(get_current_user_from_middleware)
):
    """Get list of available template categories"""
    try:
        logger.debug(f"Getting official template categories by user: {current_user.username}")
        
        categories = await _get_template_categories()
        return categories
        
    except Exception as e:
        logger.error(f"Error getting official template categories: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get template categories: {str(e)}"
        )

@router.get("/official/category/{category_name}", response_model=Dict[str, Any])
async def get_official_templates_by_category(
    category_name: str = Path(..., description="Name of the template category"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Get templates from a specific category"""
    try:
        logger.debug(f"Getting official templates for category '{category_name}' by user: {current_user.username}")
        
        templates = await _get_templates_by_category(category_name)
        return templates
        
    except Exception as e:
        logger.error(f"Error getting templates for category '{category_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get templates for category: {str(e)}"
        )

@router.get("/official/folder/{path:path}", response_model=Dict[str, Any])
async def get_official_templates_by_folder(
    path: str = Path(..., description="Folder path within the repository"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Get templates from a specific folder path"""
    try:
        logger.debug(f"Getting official templates for folder '{path}' by user: {current_user.username}")
        
        templates = await _get_templates_by_folder(path)
        return templates
        
    except Exception as e:
        logger.error(f"Error getting templates for folder '{path}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get templates for folder: {str(e)}"
        )

@router.get("/official/search", response_model=Dict[str, Any])
async def search_official_templates(
    query: str = Query(..., description="Search query for template name, description, or tags"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results to return"),
    current_user = Depends(get_current_user_from_middleware)
):
    """Search official nuclei templates"""
    try:
        
        results = await _search_templates(query, limit)
        return results
        
    except Exception as e:
        logger.error(f"Error searching official templates: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search templates: {str(e)}"
        )

@router.post("/official/update", response_model=Dict[str, str])
async def update_official_templates(
    current_user = Depends(get_current_user_from_middleware)
):
    """Update the official nuclei templates repository"""
    try:
        logger.debug(f"Updating official templates by user: {current_user.username}")
        
        await _update_nuclei_repo()
        
        return {
            "status": "success",
            "message": "Official nuclei templates repository updated successfully"
        }
        
    except Exception as e:
        logger.error(f"Error updating official templates: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update official templates: {str(e)}"
        )

@router.post("/official/setup", response_model=Dict[str, str])
async def setup_official_templates(
    current_user = Depends(get_current_user_from_middleware)
):
    """Setup the official nuclei templates repository"""
    try:
        logger.debug(f"Setting up official templates by user: {current_user.username}")
        
        await _ensure_nuclei_repo()
        
        return {
            "status": "success",
            "message": "Official nuclei templates repository setup completed"
        }
        
    except Exception as e:
        logger.error(f"Error setting up official templates: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to setup official templates: {str(e)}"
        )

@router.post("/official/generate-tree", response_model=Dict[str, str])
async def generate_official_templates_tree(
    current_user = Depends(get_current_user_from_middleware)
):
    """Generate the tree JSON file for official templates"""
    try:
        logger.debug(f"Generating official templates tree by user: {current_user.username}")
        
        # Run the tree generation script
        result = subprocess.run([
            "python3", "/app/generate_nuclei_tree.py"
        ], capture_output=True, text=True, check=True)
        
        if result.returncode == 0:
            # Check if file was created
            tree_json_path = "/opt/nuclei-templates-tree.json"
            if os.path.exists(tree_json_path):
                file_size = os.path.getsize(tree_json_path)
                return {
                    "status": "success",
                    "message": f"Tree JSON generated successfully ({file_size:,} bytes)"
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Tree generation completed but file was not created"
                )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Tree generation failed: {result.stderr}"
            )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error generating tree: {e.stderr}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate tree: {e.stderr}"
        )
    except Exception as e:
        logger.error(f"Error generating official templates tree: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate tree: {str(e)}"
        )

@router.get("/official/status", response_model=Dict[str, Any])
async def get_official_templates_status(
    current_user = Depends(get_current_user_from_middleware)
):
    """Get the status of the official nuclei templates repository"""
    try:
        logger.debug(f"Getting official templates status by user: {current_user.username}")
        
        repo_path = "/opt/nuclei-templates"
        
        if not os.path.exists(repo_path):
            # Check tree JSON file even if repo doesn't exist
            tree_json_path = "/opt/nuclei-templates-tree.json"
            tree_json_info = None
            if os.path.exists(tree_json_path):
                tree_json_info = {
                    "exists": True,
                    "size": os.path.getsize(tree_json_path),
                    "path": tree_json_path
                }
            else:
                tree_json_info = {
                    "exists": False,
                    "size": None,
                    "path": tree_json_path
                }
            
            return {
                "status": "not_setup",
                "message": "Official templates repository not setup",
                "repo_path": repo_path,
                "last_commit": None,
                "template_count": 0,
                "tree_json": tree_json_info
            }
        
        # Get last commit date
        try:
            last_commit = await _get_repo_last_commit_date()
        except Exception:
            last_commit = None
        
        # Count templates
        template_count = 0
        for root, dirs, files in os.walk(repo_path):
            for file in files:
                if file.endswith('.yaml') or file.endswith('.yml'):
                    template_count += 1
        
        # Check tree JSON file
        tree_json_path = "/opt/nuclei-templates-tree.json"
        tree_json_info = None
        if os.path.exists(tree_json_path):
            tree_json_info = {
                "exists": True,
                "size": os.path.getsize(tree_json_path),
                "path": tree_json_path
            }
        else:
            tree_json_info = {
                "exists": False,
                "size": None,
                "path": tree_json_path
            }
        
        return {
            "status": "ready",
            "message": "Official templates repository is ready",
            "repo_path": repo_path,
            "last_commit": last_commit,
            "template_count": template_count,
            "tree_json": tree_json_info
        }
        
    except Exception as e:
        logger.error(f"Error getting official templates status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get templates status: {str(e)}"
        )

# ===== HELPER FUNCTIONS FOR OFFICIAL TEMPLATES =====

async def _ensure_nuclei_repo():
    """Ensure the nuclei templates repository is cloned"""
    repo_path = "/opt/nuclei-templates"
    
    if not os.path.exists(repo_path):
        logger.debug("Cloning nuclei templates repository...")
        subprocess.run([
            "git", "clone", 
            "https://github.com/projectdiscovery/nuclei-templates.git",
            repo_path
        ], check=True)
        logger.debug("Nuclei templates repository cloned successfully")
    else:
        logger.debug("Nuclei templates repository already exists")

async def _update_nuclei_repo():
    """Update the nuclei templates repository"""
    repo_path = "/opt/nuclei-templates"
    
    if not os.path.exists(repo_path):
        await _ensure_nuclei_repo()
        return
    
    logger.debug("Updating nuclei templates repository...")
    subprocess.run([
        "git", "-C", repo_path, "pull", "origin", "main"
    ], check=True)
    logger.debug("Nuclei templates repository updated successfully")

async def _get_templates_structure():
    """Get the structure of the templates repository"""
    repo_path = "/opt/nuclei-templates"
    
    if not os.path.exists(repo_path):
        return {"error": "Repository not found"}
    
    structure = {}
    for root, dirs, files in os.walk(repo_path):
        rel_path = os.path.relpath(root, repo_path)
        if rel_path == ".":
            rel_path = ""
        
        structure[rel_path] = {
            "directories": dirs,
            "files": [f for f in files if f.endswith(('.yaml', '.yml'))]
        }
    
    return structure

async def _get_template_categories():
    """Get list of template categories (top-level directories)"""
    repo_path = "/opt/nuclei-templates"
    
    if not os.path.exists(repo_path):
        return []
    
    categories = []
    for item in os.listdir(repo_path):
        item_path = os.path.join(repo_path, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            categories.append(item)
    
    return sorted(categories)

async def _get_templates_by_category(category_name: str):
    """Get templates from a specific category"""
    repo_path = "/opt/nuclei-templates"
    category_path = os.path.join(repo_path, category_name)
    
    if not os.path.exists(category_path):
        return {"error": f"Category '{category_name}' not found"}
    
    templates = []
    for root, dirs, files in os.walk(category_path):
        for file in files:
            if file.endswith(('.yaml', '.yml')):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                
                try:
                    template_info = await _extract_template_info(PathLib(file_path))
                    template_info["path"] = rel_path
                    templates.append(template_info)
                except Exception as e:
                    logger.warning(f"Error extracting info from {file_path}: {e}")
                    templates.append({
                        "path": rel_path,
                        "name": file,
                        "error": str(e)
                    })
    
    return {
        "category": category_name,
        "templates": templates,
        "count": len(templates)
    }

async def _get_templates_by_folder(folder_path: str):
    """Get templates from a specific folder path"""
    repo_path = "/opt/nuclei-templates"
    full_path = os.path.join(repo_path, folder_path)
    
    if not os.path.exists(full_path):
        return {"error": f"Folder '{folder_path}' not found"}
    
    templates = []
    for file in os.listdir(full_path):
        file_path = os.path.join(full_path, file)
        if os.path.isfile(file_path) and file.endswith(('.yaml', '.yml')):
            rel_path = os.path.relpath(file_path, repo_path)
            
            try:
                template_info = await _extract_template_info(PathLib(file_path))
                template_info["path"] = rel_path
                templates.append(template_info)
            except Exception as e:
                logger.warning(f"Error extracting info from {file_path}: {e}")
                templates.append({
                    "path": rel_path,
                    "name": file,
                    "error": str(e)
                })
    
    return {
        "folder": folder_path,
        "templates": templates,
        "count": len(templates)
    }

async def _search_templates(query: str, limit: int = 50):
    """Search templates by name, description, or tags"""
    repo_path = "/opt/nuclei-templates"
    
    if not os.path.exists(repo_path):
        return {"error": "Repository not found"}
    
    results = []
    query_lower = query.lower()
    
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith(('.yaml', '.yml')):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                
                try:
                    template_info = await _extract_template_info(PathLib(file_path))
                    template_info["path"] = rel_path
                    
                    # Check if template matches search query
                    if (query_lower in template_info.get("name", "").lower() or
                        query_lower in template_info.get("description", "").lower() or
                        any(query_lower in tag.lower() for tag in template_info.get("tags", []))):
                        results.append(template_info)
                        
                        if len(results) >= limit:
                            break
                            
                except Exception as e:
                    logger.warning(f"Error extracting info from {file_path}: {e}")
                    continue
        
        if len(results) >= limit:
            break
    
    return {
        "query": query,
        "results": results,
        "count": len(results)
    }

async def _get_templates_tree():
    """Get the complete tree structure of templates"""
    repo_path = "/opt/nuclei-templates"
    
    if not os.path.exists(repo_path):
        return {"error": "Repository not found"}
    
    async def build_tree(path: PathLib):
        """Recursively build tree structure"""
        try:
            if path.is_file():
                if path.suffix in ['.yaml', '.yml']:
                    try:
                        template_info = await _extract_template_info(path)
                        return {
                            "type": "file",
                            "name": path.name,
                            "template": template_info
                        }
                    except Exception as e:
                        logger.warning(f"Error processing template file {path}: {e}")
                        return {
                            "type": "file",
                            "name": path.name,
                            "error": str(e)
                        }
                else:
                    return None
            elif path.is_dir():
                children = []
                try:
                    for child in sorted(path.iterdir()):
                        if not child.name.startswith('.'):
                            child_tree = await build_tree(child)
                            if child_tree:
                                children.append(child_tree)
                except Exception as e:
                    logger.warning(f"Error reading directory {path}: {e}")
                    children = []
                
                return {
                    "type": "directory",
                    "name": path.name,
                    "children": children,
                    "file_count": sum(_count_files(child) for child in children),
                    "folder_count": sum(_count_folders(child) for child in children)
                }
            return None
        except Exception as e:
            logger.warning(f"Error building tree for {path}: {e}")
            return None
    
    try:
        tree = await build_tree(PathLib(repo_path))
        if tree is None:
            return {"error": "Failed to build tree structure"}
        return tree
    except Exception as e:
        logger.error(f"Error building templates tree: {e}")
        return {"error": f"Failed to build tree structure: {str(e)}"}

def _count_folders(tree):
    """Count folders in tree structure"""
    if not tree:
        return 0
    if tree.get("type") == "directory":
        return 1 + sum(_count_folders(child) for child in tree.get("children", []))
    return 0

def _count_files(tree):
    """Count files in tree structure"""
    if not tree:
        return 0
    if tree.get("type") == "file":
        return 1
    elif tree.get("type") == "directory":
        return sum(_count_files(child) for child in tree.get("children", []))
    return 0

async def _extract_template_info(template_file: PathLib):
    """Extract basic information from a nuclei template file"""
    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse YAML
        template_data = yaml.safe_load(content)
        
        if not template_data:
            return {"name": template_file.name, "error": "Empty or invalid YAML"}
        
        # Ensure template_data is a dictionary
        if not isinstance(template_data, dict):
            return {"name": template_file.name, "error": "Template data is not a dictionary"}
        
        # Extract basic info with safe navigation
        info = {
            "id": template_data.get("id", ""),
            "name": template_data.get("info", {}).get("name", template_file.name) if isinstance(template_data.get("info"), dict) else template_file.name,
            "author": template_data.get("info", {}).get("author", "") if isinstance(template_data.get("info"), dict) else "",
            "severity": template_data.get("info", {}).get("severity", "") if isinstance(template_data.get("info"), dict) else "",
            "description": template_data.get("info", {}).get("description", "") if isinstance(template_data.get("info"), dict) else "",
            "tags": template_data.get("info", {}).get("tags", []) if isinstance(template_data.get("info"), dict) else [],
            "reference": template_data.get("info", {}).get("reference", []) if isinstance(template_data.get("info"), dict) else [],
            "classification": template_data.get("info", {}).get("classification", {}) if isinstance(template_data.get("info"), dict) else {}
        }
        
        return info
        
    except Exception as e:
        return {
            "name": template_file.name,
            "error": f"Failed to parse template: {str(e)}"
        }

async def _get_repo_last_commit_date():
    """Get the last commit date of the repository"""
    repo_path = "/opt/nuclei-templates"
    
    if not os.path.exists(repo_path):
        return None
    
    try:
        result = subprocess.run([
            "git", "-C", repo_path, "log", "-1", "--format=%cd", "--date=iso"
        ], capture_output=True, text=True, check=True)
        
        return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Error getting last commit date: {e}")
        return None 