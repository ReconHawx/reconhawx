from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from db import get_db_session
from models.postgres import ReconTaskParameters, AwsCredentials, SystemSetting
from recon_task_defaults import (
    effective_parameters,
    recon_task_api_payload,
    recon_task_names_for_admin_list,
)
import logging

logger = logging.getLogger(__name__)

class AdminRepository:
    """PostgreSQL repository for admin-related operations"""
    
    async def get_recon_task_parameters(self, recon_task: str) -> Optional[Dict[str, Any]]:
        """
        Get parameters for a specific recon task
        
        Args:
            recon_task: Name of the recon task (e.g., "resolve_domain")
            
        Returns:
            Dictionary containing the task parameters or None if not found
        """
        try:
            async with get_db_session() as db:
                result = db.query(ReconTaskParameters).filter(
                    ReconTaskParameters.recon_task == recon_task
                ).first()
                
                if result:
                    return result.to_dict()
                
                return None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting recon task parameters for {recon_task}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting recon task parameters for {recon_task}: {str(e)}")
            raise
    
    async def set_recon_task_parameters(self, recon_task: str, parameters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Set parameters for a specific recon task
        
        Args:
            recon_task: Name of the recon task (e.g., "resolve_domain")
            parameters: Dictionary containing the task parameters
            
        Returns:
            Updated task parameters document
        """
        try:
            async with get_db_session() as db:
                # Check if parameters already exist
                existing = db.query(ReconTaskParameters).filter(
                    ReconTaskParameters.recon_task == recon_task
                ).first()
                
                if existing:
                    # Update existing parameters
                    existing.parameters = parameters
                    existing.updated_at = datetime.utcnow()
                    db.commit()
                    db.refresh(existing)
                    return existing.to_dict()
                else:
                    # Create new parameters
                    new_params = ReconTaskParameters(
                        recon_task=recon_task,
                        parameters=parameters
                    )
                    db.add(new_params)
                    db.commit()
                    db.refresh(new_params)
                    return new_params.to_dict()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error setting recon task parameters for {recon_task}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error setting recon task parameters for {recon_task}: {str(e)}")
            raise
    
    async def list_recon_task_parameters(self) -> List[Dict[str, Any]]:
        """
        List all known recon tasks with effective parameters (built-in + DB row if any).
        """
        try:
            async with get_db_session() as db:
                results = db.query(ReconTaskParameters).all()
                by_name = {r.recon_task: r.to_dict() for r in results}
            out: List[Dict[str, Any]] = []
            for name in recon_task_names_for_admin_list():
                out.append(recon_task_api_payload(name, by_name.get(name)))
            return out
                
        except SQLAlchemyError as e:
            logger.error(f"Database error listing recon task parameters: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error listing recon task parameters: {str(e)}")
            raise
    
    async def delete_recon_task_parameters(self, recon_task: str) -> bool:
        """
        Delete parameters for a specific recon task
        
        Args:
            recon_task: Name of the recon task to delete
            
        Returns:
            True if deleted, False if not found
        """
        try:
            async with get_db_session() as db:
                result = db.query(ReconTaskParameters).filter(
                    ReconTaskParameters.recon_task == recon_task
                ).first()
                
                if result:
                    db.delete(result)
                    db.commit()
                    return True
                
                return False
                
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting recon task parameters for {recon_task}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting recon task parameters for {recon_task}: {str(e)}")
            raise
    
    async def get_last_execution_threshold(self, recon_task: str) -> Optional[Any]:
        """
        Get the last execution threshold for a specific recon task

        Args:
            recon_task: Name of the recon task

        Returns:
            Stored threshold (int hours and/or str with d/w suffix), or None if missing
        """
        try:
            task_params = await self.get_recon_task_parameters(recon_task)
            stored = task_params.get("parameters") if task_params else None
            eff = effective_parameters(recon_task, stored)
            return eff.get("last_execution_threshold")
            
        except Exception as e:
            logger.error(f"Error getting last execution threshold for {recon_task}: {str(e)}")
            raise
    
    async def get_chunk_size(self, recon_task: str) -> Optional[int]:
        """
        Get the chunk size for a specific recon task

        Args:
            recon_task: Name of the recon task

        Returns:
            Chunk size (includes built-in default if no DB row)
        """
        try:
            task_params = await self.get_recon_task_parameters(recon_task)
            stored = task_params.get("parameters") if task_params else None
            eff = effective_parameters(recon_task, stored)
            v = eff.get("chunk_size")
            return int(v) if v is not None else None

        except Exception as e:
            logger.error(f"Error getting chunk size for {recon_task}: {str(e)}")
            raise

    # === AWS Credentials Methods ===

    async def list_aws_credentials(self) -> List[Dict[str, Any]]:
        """
        List all AWS credentials

        Returns:
            List of all AWS credentials
        """
        try:
            async with get_db_session() as db:
                results = db.query(AwsCredentials).all()
                return [result.to_dict() for result in results]

        except SQLAlchemyError as e:
            logger.error(f"Database error listing AWS credentials: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error listing AWS credentials: {str(e)}")
            raise

    async def get_aws_credential(self, credential_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific AWS credential by ID

        Args:
            credential_id: UUID of the credential

        Returns:
            Dictionary containing the AWS credential or None if not found
        """
        try:
            async with get_db_session() as db:
                result = db.query(AwsCredentials).filter(
                    AwsCredentials.id == credential_id
                ).first()

                if result:
                    return result.to_dict()

                return None

        except SQLAlchemyError as e:
            logger.error(f"Database error getting AWS credential {credential_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting AWS credential {credential_id}: {str(e)}")
            raise

    async def create_aws_credential(
        self,
        name: str,
        access_key: str,
        secret_access_key: str,
        default_region: str,
        is_active: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new AWS credential

        Args:
            name: Name for the credential set
            access_key: AWS access key ID
            secret_access_key: AWS secret access key
            default_region: Default AWS region
            is_active: Whether the credential is active

        Returns:
            Created AWS credential document
        """
        try:
            async with get_db_session() as db:
                new_credential = AwsCredentials(
                    name=name,
                    access_key=access_key,
                    secret_access_key=secret_access_key,
                    default_region=default_region,
                    is_active=is_active
                )
                db.add(new_credential)
                db.commit()
                db.refresh(new_credential)
                return new_credential.to_dict()

        except SQLAlchemyError as e:
            logger.error(f"Database error creating AWS credential: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating AWS credential: {str(e)}")
            raise

    async def update_aws_credential(
        self,
        credential_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing AWS credential

        Args:
            credential_id: UUID of the credential to update
            data: Dictionary containing fields to update

        Returns:
            Updated AWS credential document or None if not found
        """
        try:
            async with get_db_session() as db:
                credential = db.query(AwsCredentials).filter(
                    AwsCredentials.id == credential_id
                ).first()

                if not credential:
                    return None

                # Update allowed fields
                if 'name' in data:
                    credential.name = data['name']
                if 'access_key' in data:
                    credential.access_key = data['access_key']
                if 'secret_access_key' in data:
                    credential.secret_access_key = data['secret_access_key']
                if 'default_region' in data:
                    credential.default_region = data['default_region']
                if 'is_active' in data:
                    credential.is_active = data['is_active']

                credential.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(credential)
                return credential.to_dict()

        except SQLAlchemyError as e:
            logger.error(f"Database error updating AWS credential {credential_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error updating AWS credential {credential_id}: {str(e)}")
            raise

    async def delete_aws_credential(self, credential_id: str) -> bool:
        """
        Delete an AWS credential

        Args:
            credential_id: UUID of the credential to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            async with get_db_session() as db:
                credential = db.query(AwsCredentials).filter(
                    AwsCredentials.id == credential_id
                ).first()

                if credential:
                    db.delete(credential)
                    db.commit()
                    return True

                return False

        except SQLAlchemyError as e:
            logger.error(f"Database error deleting AWS credential {credential_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting AWS credential {credential_id}: {str(e)}")
            raise

    # === System Settings Methods ===

    async def get_system_setting(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a system setting by key.

        Args:
            key: Setting key (e.g. "ai_settings")

        Returns:
            Dict with key, value, updated_at or None if not found
        """
        try:
            async with get_db_session() as db:
                result = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                if result:
                    return result.to_dict()
                return None
        except SQLAlchemyError as e:
            logger.error(f"Database error getting system setting {key}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting system setting {key}: {str(e)}")
            raise

    async def set_system_setting(self, key: str, value: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Set (upsert) a system setting.

        Args:
            key: Setting key (e.g. "ai_settings")
            value: JSON-serializable value (will be stored as JSONB)

        Returns:
            Updated setting dict
        """
        try:
            async with get_db_session() as db:
                existing = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                if existing:
                    existing.value = value
                    existing.updated_at = datetime.utcnow()
                    db.commit()
                    db.refresh(existing)
                    return existing.to_dict()
                else:
                    new_setting = SystemSetting(key=key, value=value)
                    db.add(new_setting)
                    db.commit()
                    db.refresh(new_setting)
                    return new_setting.to_dict()
        except SQLAlchemyError as e:
            logger.error(f"Database error setting system setting {key}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error setting system setting {key}: {str(e)}")
            raise

    async def delete_system_setting(self, key: str) -> bool:
        """Delete a system setting row by key. Returns True if a row was deleted."""
        try:
            async with get_db_session() as db:
                result = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                if result:
                    db.delete(result)
                    db.commit()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting system setting {key}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting system setting {key}: {str(e)}")
            raise
