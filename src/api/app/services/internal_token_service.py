import secrets
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.exc import SQLAlchemyError
from db import get_db
from models.postgres import InternalServiceToken
from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)

class InternalTokenService:
    """Service for managing internal service authentication tokens"""
    
    TOKEN_LENGTH = 64  # Length of generated tokens
    TOKEN_PREFIX = "recon_internal_"
    DEFAULT_TOKEN_NAME = "default-internal-service"
    
    def __init__(self):
        pass
    
    async def test_database_connection(self) -> bool:
        """Test database connection and verify table exists"""
        try:
            from db import engine
            
            logger.debug("Testing database connection...")
            
            # Test basic connection
            with engine.connect() as conn:
                logger.debug("Basic database connection successful")
                
                # Test if we can query the table
                try:
                    result = conn.execute(text("SELECT COUNT(*) FROM internal_service_tokens"))
                    count = result.scalar()
                    logger.debug(f"Successfully queried internal_service_tokens table, found {count} records")
                    return True
                except Exception as e:
                    logger.error(f"Error querying internal_service_tokens table: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    async def check_table_exists(self) -> bool:
        """Check if the internal_service_tokens table exists without creating it"""
        try:
            from db import engine
            
            logger.debug("Checking if internal_service_tokens table exists...")
            
            # Test database connection first
            with engine.connect() as conn:
                logger.debug("Database connection successful")
                
                # Check if table exists
                result = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'internal_service_tokens')"))
                table_exists = result.scalar()
                
                if table_exists:
                    logger.debug("internal_service_tokens table exists")
                    return True
                else:
                    logger.warning("internal_service_tokens table does not exist")
                    return False
                    
        except Exception as e:
            logger.error(f"Error checking if table exists: {e}")
            return False
    
    async def ensure_table_exists(self):
        """Ensure the internal_service_tokens table exists"""
        try:
            # Import here to avoid circular imports
            from db import engine
            from models.postgres import Base
            
            logger.debug("Checking if internal_service_tokens table exists...")
            
            # Test database connection first
            with engine.connect() as conn:
                logger.debug("Database connection successful")
                
                # Check if table exists
                result = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'internal_service_tokens')"))
                table_exists = result.scalar()
                
                if table_exists:
                    logger.debug("internal_service_tokens table already exists")
                else:
                    logger.debug("Creating internal_service_tokens table...")
                    # Create table if it doesn't exist using SQLAlchemy
                    Base.metadata.create_all(bind=engine, tables=[InternalServiceToken.__table__])
                    logger.debug("internal_service_tokens table created successfully")
                
        except SQLAlchemyError as e:
            logger.error(f"Database error ensuring internal_service_tokens table exists: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error ensuring table exists: {e}")
            raise
    
    def _generate_token(self) -> str:
        """Generate a cryptographically secure token"""
        secrets.token_bytes(self.TOKEN_LENGTH)
        token = secrets.token_urlsafe(self.TOKEN_LENGTH)
        return f"{self.TOKEN_PREFIX}{token}"
    
    def _hash_token(self, token: str) -> str:
        """Generate SHA-256 hash of token for storage"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    async def create_internal_token(
        self, 
        name: str, 
        description: Optional[str] = None,
        expires_in_days: Optional[int] = None
    ) -> str:
        """
        Create a new internal service token
        
        Args:
            name: Human-readable name for the token
            description: Optional description of the token purpose
            expires_in_days: Optional expiration in days from now
            
        Returns:
            The generated token (only returned once)
        """
        token = self._generate_token()
        token_hash = self._hash_token(token)
        
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        
        try:
            # Use a simple approach - create session, add object, commit, close
            db = SessionLocal()
            try:
                # Create new token record using ORM
                token_record = InternalServiceToken(
                    token_hash=token_hash,
                    name=name,
                    description=description,
                    expires_at=expires_at
                )
                
                db.add(token_record)
                db.commit()
                
                logger.debug(f"Created internal service token: {name}")
                return token
                
            finally:
                db.close()
                
        except SQLAlchemyError as e:
            logger.error(f"Error creating internal service token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating internal service token: {e}")
            raise
    
    def _get_db_session(self):
        """Get a database session with proper error handling"""
        try:
            db = get_db()
            return db
        except Exception as e:
            logger.error(f"Error getting database session: {e}")
            raise
    
    def _close_db_session(self, db):
        """Close database session with proper error handling"""
        try:
            if db:
                db.close()
        except Exception as e:
            logger.error(f"Error closing database session: {e}")
    
    def _commit_or_rollback(self, db, success: bool):
        """Commit or rollback database transaction with proper error handling"""
        try:
            if success:
                db.commit()
            else:
                db.rollback()
        except Exception as e:
            logger.error(f"Error during transaction handling: {e}")
            try:
                db.rollback()
                logger.debug("Rolled back transaction after error")
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate an internal service token
        
        Args:
            token: The token to validate
            
        Returns:
            Token metadata if valid, None if invalid
        """
        
        if not token.startswith(self.TOKEN_PREFIX):
            logger.warning(f"Token does not start with expected prefix: {self.TOKEN_PREFIX}")
            return None
            
        token_hash = self._hash_token(token)
        
        db = None
        success = False
        try:
            # Use synchronous database session since SQLAlchemy operations are synchronous
            db = get_db()
            
            # Find token by hash using ORM
            token_record = db.query(InternalServiceToken).filter(
                InternalServiceToken.token_hash == token_hash
            ).first()
            
            if not token_record:
                logger.warning("No token found with matching hash")
                # Debug: check what tokens exist in the database
                existing_tokens = db.query(InternalServiceToken).all()
                logger.debug(f"Found {len(existing_tokens)} existing tokens in database")
                for t in existing_tokens:
                    logger.debug(f"  Token: {t.name} (ID: {t.id}), Hash: {t.token_hash[:20]}..., Active: {t.is_active}")
                return None
            
            
            token_data = {
                "id": str(token_record.id),
                "name": token_record.name,
                "description": token_record.description,
                "is_active": token_record.is_active,
                "created_at": token_record.created_at,
                "expires_at": token_record.expires_at
            }
            
            # Check if token is active
            if not token_data["is_active"]:
                logger.warning(f"Inactive internal service token attempted: {token_data['name']}")
                return None
            
            # Check if token is expired
            if token_data["expires_at"] and datetime.now(timezone.utc) > token_data["expires_at"]:
                logger.warning(f"Expired internal service token attempted: {token_data['name']}")
                return None
            
            # Update last used timestamp
            #logger.debug("Updating last_used_at timestamp...")
            token_record.last_used_at = datetime.now(timezone.utc)
            
            # Mark success for commit
            success = True
            
            return token_data
            
        except SQLAlchemyError as e:
            # Check if it's a table not found error
            if "does not exist" in str(e).lower():
                logger.error("internal_service_tokens table does not exist - run migration or restart API to create it")
            else:
                logger.error(f"SQLAlchemy error validating internal service token: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error validating internal service token: {e}")
            return None
        finally:
            # Handle transaction
            if db:
                self._commit_or_rollback(db, success)
            
            # Close session
            self._close_db_session(db)
    
    async def get_or_create_default_token(self) -> str:
        """
        Get the default internal service token, creating it if it doesn't exist
        
        Returns:
            The default internal service token
        """
        db = None
        try:
            db = get_db()
            
            # Check if default token exists using ORM
            existing_token = db.query(InternalServiceToken).filter(
                InternalServiceToken.name == self.DEFAULT_TOKEN_NAME,
                InternalServiceToken.is_active == True
            ).first()
            
            if existing_token:
                logger.debug("Default internal service token already exists")
                # We can't return the actual token since it's hashed in the database
                # Return a special marker that indicates we need to create a new one
                return "existing-token-needs-rotation"
            
            # Create default token if it doesn't exist
            token = await self.create_internal_token(
                name=self.DEFAULT_TOKEN_NAME,
                description="Default internal service token for API-to-service communication"
            )
            
            logger.debug("Created default internal service token")
            return token
                
        except SQLAlchemyError as e:
            logger.error(f"Error getting/creating default internal service token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting/creating default internal service token: {e}")
            raise
        finally:
            self._close_db_session(db)
    
    async def rotate_token(self, token_id: str, name: Optional[str] = None) -> str:
        """
        Rotate an internal service token (deactivate old, create new)
        
        Args:
            token_id: ID of the token to rotate
            name: Optional new name for the rotated token
            
        Returns:
            The new token
        """
        db = None
        success = False
        try:
            db = get_db()
            
            # Get existing token info using ORM
            token_record = db.query(InternalServiceToken).filter(
                InternalServiceToken.id == token_id
            ).first()
            
            if not token_record:
                raise ValueError(f"Token with ID {token_id} not found")
            
            # Deactivate old token
            token_record.is_active = False
            token_record.updated_at = datetime.now(timezone.utc)
            
            # Mark success for commit
            success = True
            
            # Create new token
            new_name = name or f"{token_record.name}-rotated-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            expires_in_days = None
            if token_record.expires_at:
                days_until_expiry = (token_record.expires_at - datetime.now(timezone.utc)).days
                expires_in_days = max(1, days_until_expiry)
            
            new_token = await self.create_internal_token(
                name=new_name,
                description=token_record.description,
                expires_in_days=expires_in_days
            )
            
            logger.debug(f"Rotated internal service token: {token_record.name} -> {new_name}")
            return new_token
                
        except SQLAlchemyError as e:
            logger.error(f"Error rotating internal service token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error rotating internal service token: {e}")
            raise
        finally:
            # Handle transaction
            if db:
                self._commit_or_rollback(db, success)
            
            # Close session
            self._close_db_session(db)
    
    async def list_tokens(self) -> list:
        """List all internal service tokens (without token values)"""
        db = None
        try:
            db = get_db()
            
            # Get all tokens using ORM, ordered by creation date
            token_records = db.query(InternalServiceToken).order_by(
                InternalServiceToken.created_at.desc()
            ).all()
            
            tokens = []
            for token_record in token_records:
                tokens.append({
                    "id": str(token_record.id),
                    "name": token_record.name,
                    "description": token_record.description,
                    "is_active": token_record.is_active,
                    "created_at": token_record.created_at,
                    "updated_at": token_record.updated_at,
                    "last_used_at": token_record.last_used_at,
                    "expires_at": token_record.expires_at
                })
            
            return tokens
                
        except SQLAlchemyError as e:
            logger.error(f"Error listing internal service tokens: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing internal service tokens: {e}")
            raise
        finally:
            self._close_db_session(db)
    
    async def list_tokens_with_hashes(self) -> list:
        """List all internal service tokens with their hashes for debugging"""
        db = None
        try:
            db = get_db()
            
            # Get all tokens using ORM, ordered by creation date
            token_records = db.query(InternalServiceToken).order_by(
                InternalServiceToken.created_at.desc()
            ).all()
            
            tokens = []
            for token_record in token_records:
                tokens.append({
                    "id": str(token_record.id),
                    "name": token_record.name,
                    "description": token_record.description,
                    "is_active": token_record.is_active,
                    "created_at": token_record.created_at,
                    "updated_at": token_record.updated_at,
                    "last_used_at": token_record.last_used_at,
                    "expires_at": token_record.expires_at,
                    "token_hash": token_record.token_hash  # Include the hash for debugging
                })
            
            return tokens
                
        except SQLAlchemyError as e:
            logger.error(f"Error listing internal service tokens with hashes: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing internal service tokens with hashes: {e}")
            raise
        finally:
            self._close_db_session(db)
    
    async def deactivate_token(self, token_id: str) -> bool:
        """
        Deactivate an internal service token
        
        Args:
            token_id: ID of the token to deactivate
            
        Returns:
            True if successful
        """
        db = None
        success = False
        try:
            db = get_db()
            
            # Find and deactivate token using ORM
            token_record = db.query(InternalServiceToken).filter(
                InternalServiceToken.id == token_id
            ).first()
            
            if not token_record:
                logger.warning(f"No token found with ID: {token_id}")
                return False
            
            token_record.is_active = False
            token_record.updated_at = datetime.now(timezone.utc)
            
            # Mark success for commit
            success = True
            
            logger.debug(f"Deactivated internal service token: {token_id}")
            return True
                
        except SQLAlchemyError as e:
            logger.error(f"Error deactivating internal service token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deactivating internal service token: {e}")
            raise
        finally:
            # Handle transaction
            if db:
                self._commit_or_rollback(db, success)
            
            # Close session
            self._close_db_session(db)
    
    async def create_test_token(self) -> str:
        """Create a test token for debugging purposes"""
        try:
            logger.debug("Creating test token for debugging...")
            
            # Test database connection first
            if not await self.test_database_connection():
                logger.error("Database connection test failed, cannot create test token")
                return None
            
            # Create a test token
            token = await self.create_internal_token(
                name="test-debug-token",
                description="Test token for debugging internal service authentication",
                expires_in_days=30
            )
            
            logger.debug(f"Test token created successfully: {token[:20]}...")
            
            # Verify the token can be validated
            token_data = await self.validate_token(token)
            if token_data:
                logger.debug(f"Test token validation successful: {token_data['name']}")
            else:
                logger.error("Test token validation failed!")
            
            return token
            
        except Exception as e:
            logger.error(f"Error creating test token: {e}")
            return None