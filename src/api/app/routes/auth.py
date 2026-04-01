from fastapi import APIRouter, HTTPException, status, Depends, Request
from datetime import timedelta, timezone
from typing import Optional, List
from models.user_postgres import (
    LoginRequest, LoginResponse, UserResponse, UserCreateRequest, UserUpdateRequest,
    PasswordChangeRequest, OwnPasswordChangeRequest, UserListResponse,
    APITokenCreateRequest, APITokenResponse, APITokenCreateResponse, APITokenListResponse,
    RefreshTokenRequest, RefreshTokenResponse, LogoutRequest, UserAssignmentResponse
)
from auth.utils import generate_access_token, generate_refresh_token_value, REFRESH_TOKEN_EXPIRE_DAYS, ACCESS_TOKEN_EXPIRE_MINUTES
from auth.dependencies import require_authentication, require_superuser
from repository import AuthRepository
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(login_data: LoginRequest, request: Request):
    """
    Authenticate user and return JWT access token + refresh token
    """
    try:
        auth_repo = AuthRepository()

        user_doc = await auth_repo.authenticate_user(login_data.username, login_data.password)

        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        access_token = generate_access_token(
            data={"sub": user_doc["username"], "user_id": user_doc["id"]}
        )

        refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_token = generate_refresh_token_value()

        device_info = request.headers.get("User-Agent", "Unknown")
        ip_address = request.client.host if request.client else None

        await auth_repo.store_refresh_token(
            user_id=user_doc["id"],
            token_value=refresh_token,
            expires_at=datetime.now(timezone.utc) + refresh_token_expires,
            device_info=device_info,
            ip_address=ip_address
        )

        user_response = UserResponse(**user_doc)

        # ✅ Sanitize username before logging
        safe_username = login_data.username.encode('unicode_escape').decode('ascii')
        logger.info(f"User {safe_username} logged in successfully from {ip_address}")

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_response,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    except HTTPException:
        raise

    except Exception:
        # ✅ Sanitize before logging, don't include raw username
        safe_username = login_data.username.encode('unicode_escape').decode('ascii')
        logger.error(f"Unexpected login error for user {safe_username}", exc_info=True)

        # ✅ Always 401, never 500 — don't leak that a crash occurred
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

@router.post("/logout")
async def logout(logout_data: LogoutRequest, current_user: UserResponse = Depends(require_authentication)):
    """Logout user and revoke refresh token"""
    try:
        auth_repo = AuthRepository()

        # Revoke the specific refresh token
        if logout_data.refresh_token:
            # Efficiently find and revoke the token by its hash
            from auth.utils import hash_refresh_token
            token_hash = hash_refresh_token(logout_data.refresh_token)

            # Query database directly for the token
            found_token = await auth_repo.find_refresh_token_by_hash(token_hash)

            if found_token:
                # Ensure the token belongs to the current user
                if found_token["user_id"] == current_user.id:
                    logger.debug(f"Found matching token: {found_token['id']}")
                    success = await auth_repo.revoke_refresh_token(found_token["id"])
                    logger.debug(f"Token revocation result: {success}")
                else:
                    logger.warning("Refresh token belongs to different user")
            else:
                logger.warning("No matching refresh token found")

        logger.debug(f"User {current_user.username} logged out successfully")
        return {"message": "Logout successful"}

    except Exception as e:
        logger.error(f"Logout error for user {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during logout"
        )

@router.get("/user", response_model=UserResponse)
async def get_current_user_info(current_user: UserResponse = Depends(require_authentication)):
    """
    Get current user information
    """
    return current_user


@router.post("/me/password", response_model=UserResponse)
async def change_own_password(
    body: OwnPasswordChangeRequest,
    current_user: UserResponse = Depends(require_authentication),
):
    """Change password for the authenticated user (validates current password)."""
    try:
        auth_repo = AuthRepository()
        updated = await auth_repo.change_own_password(
            current_user.id,
            body.current_password,
            body.new_password,
        )
        return UserResponse(**updated)
    except ValueError as e:
        msg = str(e)
        if msg == "Invalid current password":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=msg,
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=msg,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing own password for {current_user.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while changing password",
        )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(refresh_data: RefreshTokenRequest):
    """
    Refresh access token using refresh token
    """
    try:
        auth_repo = AuthRepository()

        # Efficiently find the refresh token by its hash
        from auth.utils import hash_refresh_token
        token_hash = hash_refresh_token(refresh_data.refresh_token)

        # Query database directly for the token (O(1) instead of O(n))
        found_token = await auth_repo.find_refresh_token_by_hash(token_hash)

        if not found_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found or expired"
            )

        # Get user to ensure they still exist and are active
        user_doc = await auth_repo.get_user_by_id(found_token["user_id"])
        if not user_doc or not user_doc.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found or inactive"
            )

        # Create new access token
        new_access_token = generate_access_token(
            data={"sub": user_doc["username"], "user_id": user_doc["id"]}
        )

        # Update last used timestamp
        await auth_repo.update_refresh_token_last_used(found_token["id"])

        logger.debug(f"Token refreshed for user {user_doc['username']}")

        return RefreshTokenResponse(
            access_token=new_access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60  # 15 minutes in seconds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token refresh"
        )

@router.post("/logout-all")
async def logout_all_devices(current_user: UserResponse = Depends(require_authentication)):
    """
    Logout user from all devices by revoking all refresh tokens
    """
    try:
        auth_repo = AuthRepository()
        
        # Revoke all refresh tokens for the user
        await auth_repo.revoke_all_user_refresh_tokens(current_user.id)
        
        logger.debug(f"User {current_user.username} logged out from all devices")
        
        return {"message": "Logged out from all devices successfully"}
        
    except Exception as e:
        logger.error(f"Logout all devices error for user {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during logout"
        )

# ========== USER MANAGEMENT ENDPOINTS (SUPERUSER ONLY) ==========

@router.get("/users/assignment", response_model=List[UserAssignmentResponse])
async def get_users_for_assignment(
    program: Optional[str] = None,
    current_user: UserResponse = Depends(require_authentication)
):
    """
    Get list of users with access to a specific program for assignment purposes.
    Returns simplified user data (id, username, email) for dropdown lists.
    Accessible to all authenticated users.

    Args:
        program: Optional program name to filter users by access permissions

    Returns:
        List of users who have access to the program (or all active users if no program specified)
    """
    try:
        auth_repo = AuthRepository()

        # Get users with program access from repository
        users_data = await auth_repo.get_users_with_program_access(program)

        # Convert to response models
        users = [UserAssignmentResponse(**user) for user in users_data]

        return users

    except Exception as e:
        logger.error(f"Error getting users for assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving users for assignment"
        )

@router.get("/users", response_model=UserListResponse)
async def get_users(
    page: int = 1,
    limit: int = 25,
    search: Optional[str] = None,
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get list of users (superuser only)
    """
    try:
        auth_repo = AuthRepository()
        
        # Get users from repository
        result = await auth_repo.get_users(page=page, limit=limit, search=search)
        
        # Convert to response models
        users = [UserResponse(**user) for user in result["users"]]
        
        return UserListResponse(
            users=users,
            total=result["total"],
            page=result["page"],
            limit=result["limit"]
        )
        
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving users"
        )

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreateRequest,
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Create new user (superuser only)
    """
    try:
        auth_repo = AuthRepository()
        
        # Prepare user data for repository
        user_dict = user_data.dict()
        
        # Create user
        created_user = await auth_repo.create_user(user_dict)
        
        logger.debug(f"User {user_data.username} created by superuser {current_user.username}")
        
        return UserResponse(**created_user)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating user"
        )

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Get specific user by ID (superuser only)
    """
    try:
        auth_repo = AuthRepository()
        
        # Get user from repository
        user_doc = await auth_repo.get_user_by_id(user_id)
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse(**user_doc)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving user"
        )

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdateRequest,
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Update user (superuser only)
    """
    try:
        auth_repo = AuthRepository()
        
        # Get existing user to check permissions
        existing_user = await auth_repo.get_user_by_id(user_id)
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-demotion from superuser
        if (existing_user["id"] == current_user.id and 
            user_data.is_superuser is False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove superuser privileges from yourself"
            )
        
        # Build update data (only include provided fields)
        update_data = {}
        if user_data.email is not None:
            update_data["email"] = user_data.email
        if user_data.first_name is not None:
            update_data["first_name"] = user_data.first_name
        if user_data.last_name is not None:
            update_data["last_name"] = user_data.last_name
        if user_data.roles is not None:
            update_data["roles"] = user_data.roles
        if user_data.program_permissions is not None:
            update_data["program_permissions"] = user_data.program_permissions
        if user_data.is_superuser is not None:
            update_data["is_superuser"] = user_data.is_superuser
        if user_data.is_active is not None:
            update_data["is_active"] = user_data.is_active
        if user_data.rf_uhash is not None:
            update_data["rf_uhash"] = user_data.rf_uhash
        if user_data.hackerone_api_token is not None:
            update_data["hackerone_api_token"] = user_data.hackerone_api_token
        if user_data.hackerone_api_user is not None:
            update_data["hackerone_api_user"] = user_data.hackerone_api_user
        if user_data.intigriti_api_token is not None:
            update_data["intigriti_api_token"] = user_data.intigriti_api_token
        if user_data.must_change_password is not None:
            update_data["must_change_password"] = user_data.must_change_password
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided"
            )
        
        # Update user
        updated_user = await auth_repo.update_user(user_id, update_data)
        
        logger.debug(f"User {existing_user['username']} updated by superuser {current_user.username}")
        
        return UserResponse(**updated_user)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating user"
        )

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Delete user (superuser only)
    """
    try:
        auth_repo = AuthRepository()
        
        # Get existing user to check permissions
        existing_user = await auth_repo.get_user_by_id(user_id)
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-deletion
        if existing_user["id"] == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete yourself"
            )
        
        # Delete user
        deleted = await auth_repo.delete_user(user_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user"
            )
        
        logger.debug(f"User {existing_user['username']} deleted by superuser {current_user.username}")
        
        return {"message": "User deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting user"
        )

@router.put("/users/{user_id}/password")
async def change_user_password(
    user_id: str,
    password_data: PasswordChangeRequest,
    current_user: UserResponse = Depends(require_superuser)
):
    """
    Change user password (superuser only)
    """
    try:
        auth_repo = AuthRepository()
        
        # Check if user exists
        existing_user = await auth_repo.get_user_by_id(user_id)
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Change password
        changed = await auth_repo.change_user_password(user_id, password_data.new_password)
        if not changed:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to change password"
            )
        
        logger.debug(f"Password changed for user {existing_user['username']} by superuser {current_user.username}")
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing password for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while changing password"
        )

# ========== API TOKEN MANAGEMENT ENDPOINTS ==========

@router.get("/api-tokens", response_model=APITokenListResponse)
async def get_api_tokens(current_user: UserResponse = Depends(require_authentication)):
    """
    Get list of API tokens for current user
    """
    try:
        auth_repo = AuthRepository()
        
        # Get tokens from repository
        tokens_data = await auth_repo.get_user_api_tokens(current_user.id)
        
        # Convert to response models
        tokens = []
        for token_data in tokens_data:
            try:
                token_response = APITokenResponse(**token_data)
                tokens.append(token_response)
            except Exception as e:
                logger.warning(f"Skipping invalid token document: {e}")
                continue
        
        return APITokenListResponse(tokens=tokens)
        
    except Exception as e:
        logger.error(f"Error getting API tokens for user {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving API tokens"
        )

@router.post("/api-tokens", response_model=APITokenCreateResponse)
async def create_api_token(
    token_data: APITokenCreateRequest,
    current_user: UserResponse = Depends(require_authentication)
):
    """
    Create new API token for current user
    """
    try:
        auth_repo = AuthRepository()
        
        # Prepare token data for repository
        token_dict = token_data.dict()
        
        # Create token
        created_token = await auth_repo.create_api_token(current_user.id, token_dict)
        
        # Extract token value and create response
        api_token_value = created_token.pop("token")
        token_info = APITokenResponse(**created_token)
        
        logger.debug(f"API token '{token_data.name}' created for user {current_user.username}")
        
        return APITokenCreateResponse(
            token=api_token_value,
            token_info=token_info
        )
        
    except Exception as e:
        logger.error(f"Error creating API token for user {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating API token"
        )

@router.delete("/api-tokens/{token_id}")
async def revoke_api_token(
    token_id: str,
    current_user: UserResponse = Depends(require_authentication)
):
    """
    Revoke/delete API token (user can only delete their own tokens)
    """
    try:
        auth_repo = AuthRepository()
        
        # Delete token
        deleted = await auth_repo.delete_api_token(token_id, current_user.id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API token not found or access denied"
            )
        
        logger.debug(f"API token '{token_id}' revoked by user {current_user.username}")
        
        return {"message": "API token revoked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking API token {token_id} for user {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while revoking API token"
        )