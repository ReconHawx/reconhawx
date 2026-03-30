from sqlalchemy import and_
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from models.postgres import SocialMediaCredentials
from db import get_db_session

logger = logging.getLogger(__name__)

class SocialMediaCredentialsRepository:
    """PostgreSQL repository for social media credentials operations"""
    
    @staticmethod
    async def create_credential(credential_data: Dict[str, Any]) -> str:
        """Create a new social media credential set"""
        async with get_db_session() as db:
            try:
                credential = SocialMediaCredentials(
                    name=credential_data.get('name'),
                    platform=credential_data.get('platform'),
                    username=credential_data.get('username'),
                    email=credential_data.get('email'),
                    password=credential_data.get('password'),
                    is_active=credential_data.get('is_active', True)
                )
                
                db.add(credential)
                db.commit()
                db.refresh(credential)
                
                logger.info(f"Created social media credential set with ID: {credential.id}")
                return str(credential.id)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating social media credential: {str(e)}")
                raise
    
    @staticmethod
    async def get_credential_by_id(credential_id: str) -> Optional[Dict[str, Any]]:
        """Get a credential set by ID"""
        async with get_db_session() as db:
            try:
                credential = db.query(SocialMediaCredentials).filter(
                    SocialMediaCredentials.id == credential_id
                ).first()
                
                if not credential:
                    return None
                
                return credential.to_dict()
                
            except Exception as e:
                logger.error(f"Error getting social media credential {credential_id}: {str(e)}")
                raise
    
    @staticmethod
    async def get_active_by_platform(platform: str) -> Optional[Dict[str, Any]]:
        """Get active credentials for a specific platform"""
        async with get_db_session() as db:
            try:
                credential = db.query(SocialMediaCredentials).filter(
                    and_(
                        SocialMediaCredentials.platform == platform,
                        SocialMediaCredentials.is_active == True
                    )
                ).first()
                
                if not credential:
                    return None
                
                return credential.to_dict()
                
            except Exception as e:
                logger.error(f"Error getting active credentials for platform {platform}: {str(e)}")
                raise
    
    @staticmethod
    async def list_all_credentials(platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all credential sets, optionally filtered by platform"""
        async with get_db_session() as db:
            try:
                query = db.query(SocialMediaCredentials)
                
                if platform:
                    query = query.filter(SocialMediaCredentials.platform == platform)
                
                credentials = query.all()
                
                return [cred.to_dict() for cred in credentials]
                
            except Exception as e:
                logger.error(f"Error listing social media credentials: {str(e)}")
                raise
    
    @staticmethod
    async def update_credential(credential_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a credential set"""
        async with get_db_session() as db:
            try:
                credential = db.query(SocialMediaCredentials).filter(
                    SocialMediaCredentials.id == credential_id
                ).first()
                
                if not credential:
                    return None
                
                if 'name' in update_data:
                    credential.name = update_data['name']
                
                if 'username' in update_data:
                    credential.username = update_data['username']
                
                if 'email' in update_data:
                    credential.email = update_data['email']
                
                if 'password' in update_data:
                    credential.password = update_data['password']
                
                if 'is_active' in update_data:
                    credential.is_active = update_data['is_active']
                
                credential.updated_at = datetime.utcnow()
                
                db.commit()
                db.refresh(credential)
                
                return credential.to_dict()
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating social media credential {credential_id}: {str(e)}")
                raise
    
    @staticmethod
    async def delete_credential(credential_id: str) -> bool:
        """Delete a credential set"""
        async with get_db_session() as db:
            try:
                credential = db.query(SocialMediaCredentials).filter(
                    SocialMediaCredentials.id == credential_id
                ).first()
                
                if not credential:
                    return False
                
                db.delete(credential)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting social media credential {credential_id}: {str(e)}")
                raise

