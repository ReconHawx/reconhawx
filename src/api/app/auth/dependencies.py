from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
from datetime import datetime
from auth.utils import decode_access_token
from models.user_postgres import UserResponse
from repository import AuthRepository
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[UserResponse]:
    """
    Get current authenticated user from JWT token or API token
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    auth_repo = AuthRepository()
    
    # Try API token authentication first (if token starts with "recon_")
    if token.startswith("recon_"):
        # Check if this is an internal service token
        if token.startswith("recon_internal_"):
            try:
                from services.internal_token_service import InternalTokenService
                token_service = InternalTokenService()
                token_data = await token_service.validate_token(token)
                
                if token_data:
                    # Create internal service user
                    internal_user = UserResponse(
                        id=f"internal-service-{token_data['id']}",
                        username=f"internal-service-{token_data['name']}",
                        email="internal-service@recon.local",
                        is_active=True,
                        is_superuser=True,  # Give full permissions to internal services
                        is_admin=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        program_permissions=[]
                    )
                    return internal_user
                else:
                    logger.warning(f"Invalid internal service token attempted: {token[:30]}...")
                    return None
            except Exception as e:
                logger.error(f"Error validating internal service token: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
        
        # Try regular API token authentication
        try:
            # Find API token in database
            token_doc = await auth_repo.get_api_token_by_value(token)
            if not token_doc:
                logger.warning("Invalid API token attempted")
                return None
            
            # Check if token is active
            if not token_doc.get("is_active", True):
                logger.warning("Inactive API token attempted")
                return None
            
            # Check if token is expired
            expires_at = token_doc.get("expires_at")
            if expires_at:
                # Convert string to datetime if needed
                if isinstance(expires_at, str):
                    try:
                        expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid expires_at format: {expires_at}")
                        expires_at = None
                
                if expires_at and datetime.utcnow() > expires_at:
                    logger.warning("Expired API token attempted")
                    return None
            
            # Update last used timestamp
            await auth_repo.update_api_token_last_used(token_doc["id"])
            
            # Find associated user
            user_doc = await auth_repo.get_user_by_id_or_username(token_doc["user_id"])
            if not user_doc:
                logger.error("User not found for API token")
                return None
            
            # Check if user is active
            if not user_doc.get("is_active", True):
                logger.warning(f"API token used by inactive user: {user_doc.get('username')}")
                return None
            
            # Create UserResponse (without password)
            user_data = {k: v for k, v in dict(user_doc).items() if k != "password"}
            user_response = UserResponse(**user_data)
            
            # Add token permissions to user context for permission checking
            # This allows us to enforce token-specific permissions
            if hasattr(user_response, '__dict__'):
                user_response.__dict__['_token_permissions'] = token_doc.get("permissions", [])
            
            return user_response
            
        except Exception as e:
            logger.error(f"Error authenticating API token: {e}")
            return None
    
    # Fall back to JWT token authentication (stateless)
    try:
        # Decode the JWT token (validates signature and expiration)
        payload = decode_access_token(token)
        if not payload:
            return None
        
        username = payload.get("sub")
        if not username:
            return None
        
        # Find user in database to get current user data
        user_doc = await auth_repo.get_user_by_username(username)
        if not user_doc:
            return None
        
        # Check if user is still active
        if not user_doc.get("is_active", True):
            logger.warning(f"JWT token used by inactive user: {username}")
            return None
        
        # Create UserResponse (without password)
        user_data = {k: v for k, v in dict(user_doc).items() if k != "password"}
        return UserResponse(**user_data)
        
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        return None

async def require_authentication(current_user: Optional[UserResponse] = Depends(get_current_user)) -> UserResponse:
    """
    Require user to be authenticated
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user

async def require_admin(current_user: UserResponse = Depends(require_authentication)) -> UserResponse:
    """
    Require user to have admin privileges (is_staff or is_superuser)
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

async def require_superuser(current_user: UserResponse = Depends(require_authentication)) -> UserResponse:
    """
    Require user to have superuser privileges
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required"
        )
    return current_user

async def require_admin_or_manager(current_user: UserResponse = Depends(require_authentication)) -> UserResponse:
    """
    Require user to have admin privileges (is_superuser) or be a program manager
    """
    # Superusers/admins always have access
    if current_user.is_superuser or "admin" in current_user.roles:
        return current_user
    
    # Check if user has manager permissions for any program
    program_permissions = current_user.program_permissions or {}
    
    if isinstance(program_permissions, list):
        # Old format: list of program names - treat as analyst level
        # Users with old format don't have manager permissions
        pass
    elif isinstance(program_permissions, dict):
        # New format: dict of program -> permission level
        # Check if user has manager level for any program
        for program_name, permission_level in program_permissions.items():
            if permission_level == "manager":
                return current_user
    
    # If we get here, user doesn't have required permissions
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges or program manager permissions required"
    )

def optional_authentication(current_user: Optional[UserResponse] = Depends(get_current_user)) -> Optional[UserResponse]:
    """
    Optional authentication - returns user if authenticated, None otherwise
    """
    return current_user

def require_permission(permission: str):
    """
    Create a dependency that requires a specific permission for API token users
    JWT users are allowed through (inherit user permissions)
    """
    async def check_permission(current_user: UserResponse = Depends(require_authentication)) -> UserResponse:
        # If user has token permissions (API token user), check them
        if hasattr(current_user, '_token_permissions'):
            token_permissions = getattr(current_user, '_token_permissions', [])
            if permission not in token_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API token missing required permission: {permission}"
                )
        
        # JWT users and superusers always pass permission checks
        return current_user
    
    return check_permission

def get_user_accessible_programs(user: UserResponse) -> List[str]:
    """
    Get list of programs the user has access to.
    Returns empty list for no restrictions (superusers/admins have access to all).
    Returns specific programs for regular users with program_permissions.
    Note: Empty list has different meanings for different user types!
    """
    # Superusers and admins have access to all programs (no restrictions)
    if user.is_superuser or "admin" in user.roles:
        return []  # Empty list means "no restrictions" for superusers/admins
    
    # Regular users are restricted to their program_permissions
    # Handle both old list format and new dict format
    program_permissions = user.program_permissions or {}
    
    if isinstance(program_permissions, list):
        # Old format: list of program names
        return program_permissions
    elif isinstance(program_permissions, dict):
        # New format: dict of program -> permission level
        return list(program_permissions.keys())
    else:
        return []  # Empty list means "no access" for regular users

def filter_by_user_programs(base_filter: dict, user: UserResponse) -> dict:
    """
    Add program filtering to a query filter based on user permissions.

    Security hardening:
    - Always enforce the program restriction at the TOP LEVEL as `program_name` to
      ensure downstream query utilities (`apply_program_filter`, `handle_empty_program_filter`)
      consistently pick it up.
    - Normalize any provided `program_name` condition to either a string equality or
      a `$in` list. Unsupported operators (like `$eq`) will be normalized so they
      cannot accidentally bypass enforcement.
    """
    # Unrestricted access for superusers/admins
    if user.is_superuser or "admin" in user.roles:
        return base_filter

    # Resolve accessible program names
    program_permissions = user.program_permissions or {}
    if isinstance(program_permissions, list):
        accessible_programs = program_permissions
    elif isinstance(program_permissions, dict):
        accessible_programs = list(program_permissions.keys())
    else:
        accessible_programs = []

    # No access → force empty result
    if not accessible_programs:
        return {"program_name": {"$in": []}}

    # Start from a shallow copy so we can normalize at top level
    new_filter = dict(base_filter or {})

    # Compute the final top-level program filter to enforce (always as a dict)
    final_program_filter: dict
    if "program_name" not in new_filter:
        # Caller did not provide a program filter → enforce allowed set
        final_program_filter = {"$in": accessible_programs}
    else:
        requested = new_filter["program_name"]
        if isinstance(requested, str):
            # Simple equality provided → normalize to $in
            final_program_filter = {"$in": [requested]} if requested in accessible_programs else {"$in": []}
        elif isinstance(requested, dict):
            # Normalize to supported forms only
            if "$in" in requested and isinstance(requested["$in"], list):
                allowed = [p for p in requested["$in"] if p in accessible_programs]
                final_program_filter = {"$in": allowed} if allowed else {"$in": []}
            elif "$eq" in requested:
                # Normalize $eq to direct equality
                value = requested["$eq"]
                final_program_filter = {"$in": [value]} if value in accessible_programs else {"$in": []}
            else:
                # Any other operator → fall back to enforcing allowed set
                final_program_filter = {"$in": accessible_programs}
        else:
            # Unknown type → enforce allowed set
            final_program_filter = {"$in": accessible_programs}

    # Enforce at top-level to avoid relying on nested $and composition
    new_filter["program_name"] = final_program_filter
    return new_filter

def check_program_permission(user: UserResponse, program_name: str, required_level: str = "analyst") -> bool:
    """
    Check if user has the required permission level for a specific program.
    
    Args:
        user: The user to check permissions for
        program_name: Name of the program to check
        required_level: Required permission level ("analyst" or "manager")
    
    Returns:
        True if user has required permission level or higher, False otherwise
    """
    # Superusers and admins have full access to all programs
    if user.is_superuser or "admin" in user.roles:
        return True
    
    # Check user's program permissions
    program_permissions = user.program_permissions or {}
    
    if isinstance(program_permissions, list):
        # Old format: list of program names - treat as analyst level
        user_level = "analyst" if program_name in program_permissions else None
    elif isinstance(program_permissions, dict):
        # New format: dict of program -> permission level
        user_level = program_permissions.get(program_name)
    else:
        user_level = None
    
    if not user_level:
        return False
    
    # Permission hierarchy: manager > analyst
    if required_level == "analyst":
        return user_level in ["analyst", "manager"]
    elif required_level == "manager":
        return user_level == "manager"
    
    return False

async def check_program_permission_by_id(user: UserResponse, program_id: str, required_level: str = "analyst") -> bool:
    """
    Check if user has the required permission level for a specific program by ID.
    
    Args:
        user: The user to check permissions for
        program_id: ID of the program to check
        required_level: Required permission level ("analyst" or "manager")
    
    Returns:
        True if user has required permission level or higher, False otherwise
    """
    # Superusers and admins have full access to all programs
    if user.is_superuser or "admin" in user.roles:
        return True
    
    # Get user's accessible program names
    accessible_program_names = get_user_accessible_programs(user)
    
    # If user has no program permissions, deny access
    if not accessible_program_names:
        return False
    
    # Convert program_id to program_name by looking it up in the database
    try:
        from repository import ProgramRepository
        program_data = await ProgramRepository.get_program(program_id)
        
        if not program_data:
            logger.warning(f"Program with ID {program_id} not found")
            return False
        
        program_name = program_data.get("name")
        if not program_name:
            logger.warning(f"Program with ID {program_id} has no name")
            return False
        
        # Check if user has access to this specific program
        if program_name not in accessible_program_names:
            return False
        
        # Check permission level if required
        if required_level == "manager":
            # For manager level, check if user has manager permissions for this program
            program_permissions = user.program_permissions or {}
            
            if isinstance(program_permissions, dict):
                user_level = program_permissions.get(program_name, "analyst")
                return user_level in ["manager", "admin"]
            else:
                # Old format: list of program names - treat as analyst level only
                return False
        
        # For analyst level, just having the program in accessible_program_names is enough
        return True
        
    except Exception as e:
        logger.error(f"Error checking program permission by ID {program_id}: {str(e)}")
        return False

def get_user_program_permission_level(user: UserResponse, program_name: str) -> Optional[str]:
    """
    Get the user's permission level for a specific program.
    
    Returns:
        Permission level string ("analyst" or "manager"), or None if no access
    """
    # Superusers and admins have manager-level access to all programs
    if user.is_superuser or "admin" in user.roles:
        return "manager"
    
    # Check user's program permissions
    program_permissions = user.program_permissions or {}
    
    if isinstance(program_permissions, list):
        # Old format: list of program names - treat as analyst level
        return "analyst" if program_name in program_permissions else None
    elif isinstance(program_permissions, dict):
        # New format: dict of program -> permission level
        return program_permissions.get(program_name)
    else:
        return None

async def get_internal_service_user() -> Optional[UserResponse]:
    """
    Get internal service user for service-to-service authentication
    This allows internal services (like workers) to authenticate without user credentials
    """
    import os
    from services.internal_token_service import InternalTokenService
    
    # Check for internal service API key
    internal_api_key = os.getenv("INTERNAL_SERVICE_API_KEY")
    if not internal_api_key:
        logger.warning("INTERNAL_SERVICE_API_KEY not configured")
        return None
    
    # Validate the internal service token
    token_service = InternalTokenService()
    token_data = await token_service.validate_token(internal_api_key)
    
    if not token_data:
        logger.warning("Invalid INTERNAL_SERVICE_API_KEY provided")
        return None
    
    # Create a special internal service user
    internal_user = UserResponse(
        id=f"internal-service-{token_data['id']}",
        username=f"internal-service-{token_data['name']}",
        email="internal-service@recon.local",
        is_active=True,
        is_superuser=True,  # Give full permissions to internal services
        is_admin=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        program_permissions=[]
    )
    
    logger.info(f"Internal service authenticated with token: {token_data['name']}")
    return internal_user

async def require_internal_service_or_authentication(
    internal_user: Optional[UserResponse] = Depends(get_internal_service_user),
    current_user: Optional[UserResponse] = Depends(get_current_user)
) -> UserResponse:
    """
    Require either internal service authentication or regular user authentication
    This allows both internal services and regular users to access the endpoint

    Priority: User authentication takes precedence over internal service authentication
    when both are available, to ensure proper action logging for user actions.
    """
    # Prioritize user authentication for proper action logging
    if current_user:
        logger.info(f"User {current_user.username} authenticated")
        return current_user

    if internal_user:
        return internal_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required"
    )

def get_current_user_from_middleware(request: Request) -> UserResponse:
    """
    Extract the current user from middleware-set request state.
    This dependency assumes authentication middleware has already run.
    """
    current_user = getattr(request.state, 'current_user', None)
    if not current_user:
        logger.error("current_user not found in request.state - middleware may not be configured correctly")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user


def require_internal_service_identity(
    current_user: UserResponse = Depends(get_current_user_from_middleware),
) -> UserResponse:
    """
    Restrict route to internal service tokens (e.g. ct-monitor), not interactive JWT users.
    Internal tokens resolve to usernames like internal-service-<name>.
    """
    if not str(current_user.username).startswith("internal-service-"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal service authentication required",
        )
    return current_user