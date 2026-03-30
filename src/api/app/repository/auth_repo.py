from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, or_
from db import get_db_session
from models.postgres import User, APIToken, UserProgramPermission
from models.refresh_token import RefreshToken
from auth.utils import verify_password, hash_password, hash_refresh_token, hash_token_sha256
import logging
import secrets
import bcrypt

logger = logging.getLogger(__name__)
DUMMY_HASH = bcrypt.hashpw(b"dummy password", bcrypt.gensalt()).decode()
class AuthRepository:
    """PostgreSQL repository for authentication and user management"""
    
    async def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with username and password
        
        Args:
            username: Username to authenticate
            password: Plain text password
            
        Returns:
            User data if authentication successful, None otherwise
        """
        try:
            async with get_db_session() as db:
                user = db.query(User).filter(User.username == username).first()
                if '\x00' in username or '\x00' in password:
                    return None
                if not username or not password:
                    return None
                if not user:
                    verify_password(password, DUMMY_HASH)
                    return None

                # Verify password
                if not verify_password(password, user.password_hash):
                    return None

                # Check if user is active
                if not user.is_active:
                    return None
                # Update last login
                user.last_login = datetime.now(timezone.utc)
                db.commit()
                db.refresh(user)
                
                return user.to_dict()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error during authentication for {username}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error during authentication for {username}: {str(e)}")
            raise
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by ID
        
        Args:
            user_id: User UUID string
            
        Returns:
            User data or None if not found
        """
        try:
            async with get_db_session() as db:
                user = db.query(User).filter(User.id == user_id).first()
                return user.to_dict() if user else None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {str(e)}")
            raise
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username
        
        Args:
            username: Username to find
            
        Returns:
            User data or None if not found
        """
        try:
            async with get_db_session() as db:
                user = db.query(User).filter(User.username == username).first()
                return user.to_dict() if user else None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user by username {username}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {str(e)}")
            raise
    
    async def get_users(self, page: int = 1, limit: int = 25, search: Optional[str] = None) -> Dict[str, Any]:
        """
        Get paginated list of users with optional search
        
        Args:
            page: Page number (1-based)
            limit: Number of users per page
            search: Optional search term for username, email, first_name, last_name
            
        Returns:
            Dictionary with users list and pagination info
        """
        try:
            async with get_db_session() as db:
                query = db.query(User)
                
                # Apply search filter
                if search:
                    search_filter = or_(
                        User.username.ilike(f"%{search}%"),
                        User.email.ilike(f"%{search}%"),
                        User.first_name.ilike(f"%{search}%"),
                        User.last_name.ilike(f"%{search}%")
                    )
                    query = query.filter(search_filter)
                
                # Get total count
                total = query.count()
                
                # Apply ordering first, then pagination
                skip = (page - 1) * limit
                users = query.order_by(User.username).offset(skip).limit(limit).all()
                
                return {
                    "users": [user.to_dict() for user in users],
                    "total": total,
                    "page": page,
                    "limit": limit
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting users: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting users: {str(e)}")
            raise
    
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new user
        
        Args:
            user_data: User data dictionary
            
        Returns:
            Created user data
        """
        try:
            async with get_db_session() as db:
                # Check if username already exists
                existing_user = db.query(User).filter(User.username == user_data["username"]).first()
                if existing_user:
                    raise ValueError("Username already exists")
                
                # Check if email already exists (if provided)
                if user_data.get("email"):
                    existing_email = db.query(User).filter(User.email == user_data["email"]).first()
                    if existing_email:
                        raise ValueError("Email already exists")
                
                # Hash password
                hashed_password = hash_password(user_data["password"])
                
                # Handle program permissions separately
                program_permissions = user_data.pop("program_permissions", {})
                
                # Create user
                new_user = User(
                    username=user_data["username"],
                    email=user_data.get("email"),
                    password_hash=hashed_password,
                    first_name=user_data.get("first_name"),
                    last_name=user_data.get("last_name"),
                    is_active=user_data.get("is_active", True),
                    is_superuser=user_data.get("is_superuser", False),
                    roles=user_data.get("roles", ["user"]),
                    rf_uhash=user_data.get("rf_uhash"),
                    hackerone_api_token=user_data.get("hackerone_api_token"),
                    hackerone_api_user=user_data.get("hackerone_api_user"),
                    intigriti_api_token=user_data.get("intigriti_api_token")
                )
                
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                
                # Add program permissions if provided
                if program_permissions:
                    await self._update_user_program_permissions(db, new_user, program_permissions)
                    db.commit()
                    db.refresh(new_user)
                
                return new_user.to_dict()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error creating user: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise
    
    async def update_user(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user data
        
        Args:
            user_id: User UUID string
            update_data: Data to update
            
        Returns:
            Updated user data
        """
        try:
            async with get_db_session() as db:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    raise ValueError("User not found")
                
                # Check email uniqueness if updating email
                if "email" in update_data and update_data["email"]:
                    existing_email = db.query(User).filter(
                        and_(User.email == update_data["email"], User.id != user_id)
                    ).first()
                    if existing_email:
                        raise ValueError("Email already exists")
                
                # Handle program permissions separately
                program_permissions = update_data.pop("program_permissions", None)
                
                # Update regular fields
                for field, value in update_data.items():
                    if hasattr(user, field):
                        setattr(user, field, value)
                
                # Update program permissions if provided
                if program_permissions is not None:
                    await self._update_user_program_permissions(db, user, program_permissions)
                
                db.commit()
                db.refresh(user)
                
                return user.to_dict()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error updating user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {str(e)}")
            raise
    
    async def _update_user_program_permissions(self, db: Session, user: User, program_permissions: Dict[str, str]):
        """
        Update user program permissions
        
        Args:
            db: Database session
            user: User object
            program_permissions: Dict mapping program names to permission levels
        """
        try:
            # Import Program model
            from models.postgres import Program
            
            # Clear existing permissions
            db.query(UserProgramPermission).filter(UserProgramPermission.user_id == user.id).delete()
            
            # Add new permissions
            for program_name, permission_level in program_permissions.items():
                # Find program by name
                program = db.query(Program).filter(Program.name == program_name).first()
                if program:
                    permission = UserProgramPermission(
                        user_id=user.id,
                        program_id=program.id,
                        permission_level=permission_level
                    )
                    db.add(permission)
                else:
                    logger.warning(f"Program '{program_name}' not found for user {user.username}")
                    
        except Exception as e:
            logger.error(f"Error updating program permissions for user {user.username}: {str(e)}")
            raise
    
    async def delete_user(self, user_id: str) -> bool:
        """
        Delete user
        
        Args:
            user_id: User UUID string
            
        Returns:
            True if deleted, False if not found
        """
        try:
            async with get_db_session() as db:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    return False
                
                # Delete associated API tokens
                db.query(APIToken).filter(APIToken.user_id == user_id).delete()
                
                # Delete user
                db.delete(user)
                db.commit()
                
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {str(e)}")
            raise
    
    async def change_user_password(self, user_id: str, new_password: str) -> bool:
        """
        Change user password
        
        Args:
            user_id: User UUID string
            new_password: New plain text password
            
        Returns:
            True if password changed, False if user not found
        """
        try:
            async with get_db_session() as db:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    return False
                
                # Hash new password
                user.password_hash = hash_password(new_password)
                db.commit()
                
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error changing password for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error changing password for user {user_id}: {str(e)}")
            raise
    
    async def create_api_token(self, user_id: str, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create API token for user.
        The plaintext token is returned once; only the SHA-256 hash is persisted.
        
        Args:
            user_id: User UUID string
            token_data: Token data dictionary
            
        Returns:
            Created token data with actual token value (only time it's available)
        """
        try:
            async with get_db_session() as db:
                api_token_value = f"recon_{secrets.token_hex(32)}"
                token_hash = hash_token_sha256(api_token_value)
                
                expires_at = datetime.now(timezone.utc) + timedelta(days=token_data.get("expires_in_days", 365))
                
                api_token = APIToken(
                    user_id=user_id,
                    token_hash=token_hash,
                    name=token_data["name"],
                    description=token_data.get("description"),
                    permissions=token_data.get("permissions", []),
                    is_active=True,
                    expires_at=expires_at
                )
                
                db.add(api_token)
                db.commit()
                db.refresh(api_token)
                
                token_dict = api_token.to_dict()
                token_dict["token"] = api_token_value
                
                return token_dict
                
        except SQLAlchemyError as e:
            logger.error(f"Database error creating API token for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating API token for user {user_id}: {str(e)}")
            raise
    
    async def get_user_api_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all API tokens for a user
        
        Args:
            user_id: User UUID string
            
        Returns:
            List of API token data (without actual token values)
        """
        try:
            async with get_db_session() as db:
                tokens = db.query(APIToken).filter(
                    and_(APIToken.user_id == user_id, APIToken.is_active == True)
                ).order_by(APIToken.created_at.desc()).all()
                
                return [token.to_dict() for token in tokens]
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting API tokens for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting API tokens for user {user_id}: {str(e)}")
            raise
    
    async def delete_api_token(self, token_id: str, user_id: str) -> bool:
        """
        Delete API token (user can only delete their own tokens)
        
        Args:
            token_id: Token UUID string
            user_id: User UUID string (for verification)
            
        Returns:
            True if deleted, False if not found or access denied
        """
        try:
            async with get_db_session() as db:
                token = db.query(APIToken).filter(
                    and_(APIToken.id == token_id, APIToken.user_id == user_id)
                ).first()
                
                if not token:
                    return False
                
                db.delete(token)
                db.commit()
                
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting API token {token_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting API token {token_id}: {str(e)}")
            raise
    
    # Web login token methods removed - JWT tokens are stateless and don't need database storage
    
    async def get_api_token_by_value(self, token_value: str) -> Optional[Dict[str, Any]]:
        """
        Get API token by its plaintext value.
        Hashes the value and looks up the stored hash.
        
        Args:
            token_value: The plaintext token value
            
        Returns:
            Token data or None if not found
        """
        try:
            async with get_db_session() as db:
                token_hash = hash_token_sha256(token_value)
                token = db.query(APIToken).filter(APIToken.token_hash == token_hash).first()
                return token.to_dict() if token else None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting API token by value: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting API token by value: {str(e)}")
            raise
    
    async def update_api_token_last_used(self, token_id: str) -> bool:
        """
        Update the last_used_at timestamp for an API token
        
        Args:
            token_id: Token UUID string
            
        Returns:
            True if updated, False if not found
        """
        try:
            async with get_db_session() as db:
                token = db.query(APIToken).filter(APIToken.id == token_id).first()
                if not token:
                    return False
                
                token.last_used_at = datetime.now(timezone.utc)
                db.commit()
                
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error updating API token last used {token_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error updating API token last used {token_id}: {str(e)}")
            raise
    
    async def get_user_by_id_or_username(self, user_id_or_username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by ID (UUID) or username, handling both formats
        
        Args:
            user_id_or_username: User UUID string or username
            
        Returns:
            User data or None if not found
        """
        try:
            async with get_db_session() as db:
                # First try to find by UUID
                try:
                    import uuid
                    user_uuid = uuid.UUID(user_id_or_username)
                    user = db.query(User).filter(User.id == user_uuid).first()
                    if user:
                        return user.to_dict()
                except ValueError:
                    # Not a valid UUID, try as username
                    pass
                
                # Try as username
                user = db.query(User).filter(User.username == user_id_or_username).first()
                return user.to_dict() if user else None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user by ID or username {user_id_or_username}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting user by ID or username {user_id_or_username}: {str(e)}")
            raise

    # ========== REFRESH TOKEN METHODS ==========
    
    async def store_refresh_token(self, user_id: str, token_value: str, 
                                 expires_at: datetime, device_info: str = None, 
                                 ip_address: str = None) -> Dict[str, Any]:
        """
        Create a new refresh token record
        
        Args:
            user_id: User UUID string
            token_value: Plain text token value to hash
            expires_at: Token expiration datetime
            device_info: Optional device/browser information
            ip_address: Optional IP address where token was created
            
        Returns:
            Created refresh token data
        """
        try:
            async with get_db_session() as db:
                token_hash = hash_refresh_token(token_value)
                
                refresh_token = RefreshToken(
                    user_id=user_id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                    device_info=device_info,
                    ip_address=ip_address
                )
                
                db.add(refresh_token)
                db.commit()
                db.refresh(refresh_token)
                
                return {
                    "id": str(refresh_token.id),
                    "user_id": str(refresh_token.user_id),
                    "expires_at": refresh_token.expires_at,
                    "device_info": refresh_token.device_info,
                    "ip_address": str(refresh_token.ip_address) if refresh_token.ip_address else None
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error creating refresh token for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating refresh token for user {user_id}: {str(e)}")
            raise

    async def get_refresh_token_by_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get refresh token by hash
        
        Args:
            token_hash: Hashed token value
            
        Returns:
            Refresh token data or None if not found
        """
        try:
            async with get_db_session() as db:
                # Use timezone-aware datetime for comparison
                current_time = datetime.now(timezone.utc)
                
                token = db.query(RefreshToken).filter(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.is_revoked == False,
                    RefreshToken.expires_at > current_time
                ).first()
                
                if token:
                    return {
                        "id": str(token.id),
                        "user_id": str(token.user_id),
                        "expires_at": token.expires_at,
                        "device_info": token.device_info,
                        "ip_address": str(token.ip_address) if token.ip_address else None
                    }
                return None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting refresh token by hash: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting refresh token by hash: {str(e)}")
            raise

    async def revoke_refresh_token(self, token_id: str) -> bool:
        """
        Revoke a refresh token
        
        Args:
            token_id: Refresh token UUID string
            
        Returns:
            True if revoked, False if not found
        """
        try:
            async with get_db_session() as db:
                token = db.query(RefreshToken).filter(RefreshToken.id == token_id).first()
                if token:
                    token.is_revoked = True
                    db.commit()
                    return True
                return False
                
        except SQLAlchemyError as e:
            logger.error(f"Database error revoking refresh token {token_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error revoking refresh token {token_id}: {str(e)}")
            raise

    async def revoke_all_user_refresh_tokens(self, user_id: str) -> bool:
        """
        Revoke all refresh tokens for a user (logout from all devices)
        
        Args:
            user_id: User UUID string
            
        Returns:
            True if all tokens revoked, False if error
        """
        try:
            async with get_db_session() as db:
                tokens = db.query(RefreshToken).filter(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked == False
                ).all()
                
                for token in tokens:
                    token.is_revoked = True
                
                db.commit()
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error revoking all refresh tokens for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error revoking all refresh tokens for user {user_id}: {str(e)}")
            raise

    async def update_refresh_token_last_used(self, token_id: str) -> bool:
        """
        Update the last_used_at timestamp for a refresh token
        
        Args:
            token_id: Refresh token UUID string
            
        Returns:
            True if updated, False if not found
        """
        try:
            async with get_db_session() as db:
                token = db.query(RefreshToken).filter(RefreshToken.id == token_id).first()
                if not token:
                    return False
                
                token.last_used_at = datetime.now(timezone.utc)
                db.commit()
                
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error updating refresh token last used {token_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error updating refresh token last used {token_id}: {str(e)}")
            raise

    async def get_all_refresh_tokens(self) -> List[Dict[str, Any]]:
        """Get all refresh tokens across all users (for debugging only)"""
        try:
            async with get_db_session() as db:
                tokens = db.query(RefreshToken).all()

                return [
                    {
                        "id": str(token.id),
                        "user_id": str(token.user_id),
                        "expires_at": token.expires_at,
                        "is_revoked": token.is_revoked,
                        "created_at": token.created_at,
                        "last_used_at": token.last_used_at,
                        "device_info": token.device_info,
                        "ip_address": str(token.ip_address) if token.ip_address else None,
                        "token_hash": token.token_hash,
                        "token_hash_prefix": token.token_hash[:20] + "..." if token.token_hash else None
                    }
                    for token in tokens
                ]

        except Exception as e:
            logger.error(f"Error getting all refresh tokens: {str(e)}")
            return []

    async def get_users_with_program_access(self, program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get users who have access to a specific program for assignment purposes

        Args:
            program_name: Optional program name to filter by. If None, returns all active users.

        Returns:
            List of user dicts with id, username, and email fields
        """
        try:
            async with get_db_session() as db:
                from models.postgres import Program

                if program_name:
                    # Get users who are superusers OR have explicit permissions for this program
                    query = db.query(User).outerjoin(
                        UserProgramPermission,
                        User.id == UserProgramPermission.user_id
                    ).outerjoin(
                        Program,
                        UserProgramPermission.program_id == Program.id
                    ).filter(
                        User.is_active == True
                    ).filter(
                        or_(
                            User.is_superuser == True,
                            Program.name == program_name
                        )
                    ).distinct()
                else:
                    # Return all active users if no program specified
                    query = db.query(User).filter(User.is_active == True)

                users = query.order_by(User.username).all()

                return [
                    {
                        "id": str(user.id),
                        "username": user.username,
                        "email": user.email
                    }
                    for user in users
                ]

        except SQLAlchemyError as e:
            logger.error(f"Database error getting users with program access: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting users with program access: {str(e)}")
            raise

    async def find_refresh_token_by_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """
        Find a refresh token by its hash (efficient database lookup)

        Args:
            token_hash: SHA256 hash of the token value

        Returns:
            Refresh token data or None if not found
        """
        try:
            async with get_db_session() as db:
                # Use timezone-aware datetime for comparison
                current_time = datetime.now(timezone.utc)

                token = db.query(RefreshToken).filter(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.is_revoked == False,
                    RefreshToken.expires_at > current_time
                ).first()

                if token:
                    return {
                        "id": str(token.id),
                        "user_id": str(token.user_id),
                        "expires_at": token.expires_at,
                        "device_info": token.device_info,
                        "ip_address": str(token.ip_address) if token.ip_address else None
                    }
                return None

        except SQLAlchemyError as e:
            logger.error(f"Database error finding refresh token by hash: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error finding refresh token by hash: {str(e)}")
            raise