from sqlalchemy import or_, desc
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from models.postgres import NucleiTemplate
from db import get_db_session
from utils.nuclei_template_parser import extract_template_metadata

logger = logging.getLogger(__name__)

class NucleiTemplateRepository:
    """PostgreSQL repository for nuclei templates operations"""
    
    @staticmethod
    async def create_template(template_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new nuclei template"""
        async with get_db_session() as db:
            try:
                # Extract metadata from YAML content
                is_valid, metadata, error_message = extract_template_metadata(template_data.get('content'))
                if not is_valid or metadata is None:
                    logger.error(f"Invalid template content: {error_message}")
                    return None
                
                # Check if template with same ID already exists
                existing = db.query(NucleiTemplate).filter(NucleiTemplate.template_id == metadata.get('id')).first()
                if existing:
                    logger.warning(f"Template with ID {metadata.get('id')} already exists")
                    return None
                
                # Create nuclei template
                nuclei_template = NucleiTemplate(
                    template_id=metadata.get('id'),
                    name=metadata.get('name', ''),
                    author=metadata.get('author', ''),
                    severity=metadata.get('severity', ''),
                    description=metadata.get('description', ''),
                    tags=metadata.get('tags', []),
                    yaml_content=template_data.get('content')
                )
                
                db.add(nuclei_template)
                db.commit()
                db.refresh(nuclei_template)
                
                logger.info(f"Created nuclei template with ID: {nuclei_template.template_id}")
                return NucleiTemplateRepository._template_to_dict(nuclei_template)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating nuclei template: {str(e)}")
                raise
    
    @staticmethod
    async def get_template(template_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific nuclei template by ID"""
        async with get_db_session() as db:
            try:
                template = db.query(NucleiTemplate).filter(NucleiTemplate.template_id == template_id).first()
                
                if template:
                    return NucleiTemplateRepository._template_to_dict(template)
                
                return None
                
            except Exception as e:
                logger.error(f"Error fetching nuclei template {template_id}: {str(e)}")
                raise
    
    @staticmethod
    async def list_templates(
        skip: int = 0, 
        limit: int = 100, 
        tags: Optional[List[str]] = None,
        severity: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """List nuclei templates with optional filtering"""
        async with get_db_session() as db:
            try:
                query = db.query(NucleiTemplate)
                
                # Apply filters
                if tags:
                    # Filter by tags (any of the provided tags)
                    tag_conditions = []
                    for tag in tags:
                        tag_conditions.append(NucleiTemplate.tags.contains([tag]))
                    query = query.filter(or_(*tag_conditions))
                
                if severity:
                    query = query.filter(NucleiTemplate.severity == severity)
                
                if search:
                    # Search in name, description, or content
                    search_conditions = [
                        NucleiTemplate.name.ilike(f'%{search}%'),
                        NucleiTemplate.description.ilike(f'%{search}%'),
                        NucleiTemplate.yaml_content.ilike(f'%{search}%'),
                        NucleiTemplate.author.ilike(f'%{search}%')
                    ]
                    query = query.filter(or_(*search_conditions))
                
                # Get total count
                total = query.count()
                
                # Apply pagination and sorting
                templates = query.order_by(desc(NucleiTemplate.created_at)).offset(skip).limit(limit).all()
                
                result = []
                for template in templates:
                    result.append(NucleiTemplateRepository._template_to_dict(template))
                
                return {
                    "templates": result,
                    "total": total,
                    "skip": skip,
                    "limit": limit
                }
                
            except Exception as e:
                logger.error(f"Error listing nuclei templates: {str(e)}")
                return {"templates": [], "total": 0, "skip": skip, "limit": limit}
    
    @staticmethod
    async def update_template(template_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a nuclei template"""
        async with get_db_session() as db:
            try:
                template = db.query(NucleiTemplate).filter(NucleiTemplate.template_id == template_id).first()
                if not template:
                    logger.warning(f"Template with ID {template_id} not found")
                    return None
                
                # If content is being updated, extract new metadata
                if 'content' in update_data:
                    is_valid, metadata, error_message = extract_template_metadata(update_data['content'])
                    if not is_valid or metadata is None:
                        logger.error(f"Invalid template content: {error_message}")
                        return None
                    
                    # Update with extracted metadata
                    template.template_id = metadata.get('id', template.template_id)
                    template.name = metadata.get('name', template.name)
                    template.author = metadata.get('author', template.author)
                    template.severity = metadata.get('severity', template.severity)
                    template.description = metadata.get('description', template.description)
                    template.tags = metadata.get('tags', template.tags)
                    template.yaml_content = update_data['content']
                
                # Update other fields
                if 'name' in update_data and 'content' not in update_data:
                    template.name = update_data['name']
                if 'author' in update_data and 'content' not in update_data:
                    template.author = update_data['author']
                if 'severity' in update_data and 'content' not in update_data:
                    template.severity = update_data['severity']
                if 'description' in update_data and 'content' not in update_data:
                    template.description = update_data['description']
                if 'tags' in update_data and 'content' not in update_data:
                    template.tags = update_data['tags']
                
                template.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(template)
                
                logger.info(f"Updated nuclei template with ID: {template_id}")
                return NucleiTemplateRepository._template_to_dict(template)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating nuclei template {template_id}: {str(e)}")
                raise
    
    @staticmethod
    async def delete_template(template_id: str) -> bool:
        """Delete a nuclei template from database"""
        async with get_db_session() as db:
            try:
                template = db.query(NucleiTemplate).filter(NucleiTemplate.template_id == template_id).first()
                if not template:
                    logger.warning(f"Template with ID {template_id} not found")
                    return False
                
                db.delete(template)
                db.commit()
                logger.info(f"Deleted nuclei template with ID: {template_id}")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting nuclei template {template_id}: {str(e)}")
                raise
    
    @staticmethod
    async def get_template_by_name(name: str) -> Optional[Dict[str, Any]]:
        """Get a nuclei template by name"""
        async with get_db_session() as db:
            try:
                # Try exact match first
                template = db.query(NucleiTemplate).filter(NucleiTemplate.name == name).first()
                
                if template:
                    return NucleiTemplateRepository._template_to_dict(template)
                
                # If exact match fails, try case-insensitive match
                template = db.query(NucleiTemplate).filter(NucleiTemplate.name.ilike(name)).first()
                
                if template:
                    return NucleiTemplateRepository._template_to_dict(template)
                
                # If still no match, try partial match
                template = db.query(NucleiTemplate).filter(NucleiTemplate.name.ilike(f"%{name}%")).first()
                
                if template:
                    return NucleiTemplateRepository._template_to_dict(template)
                
                return None
                
            except Exception as e:
                logger.error(f"Error fetching nuclei template by name {name}: {str(e)}")
                raise
        
    @staticmethod
    def _template_to_dict(template: NucleiTemplate) -> Dict[str, Any]:
        """Convert NucleiTemplate model to dictionary"""
        return {
            'id': template.template_id,
            'name': template.name,
            'author': template.author,
            'severity': template.severity,
            'description': template.description,
            'tags': template.tags,
            'content': template.yaml_content,
            'created_at': template.created_at.isoformat() if template.created_at else None,
            'updated_at': template.updated_at.isoformat() if template.updated_at else None
        } 