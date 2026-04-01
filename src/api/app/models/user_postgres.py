from pydantic import BaseModel, Field, field_validator
from typing import Dict, Optional, List, Union
from datetime import datetime

class UserResponse(BaseModel):
    """User response model for PostgreSQL"""
    id: str
    username: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    roles: List[str] = ["user"]
    program_permissions: Union[Dict[str, str], List[str]] = {}  # program_name -> permission_level
    rf_uhash: Optional[str] = None
    hackerone_api_token: Optional[str] = None
    hackerone_api_user: Optional[str] = None
    intigriti_api_token: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    must_change_password: bool = False

class LoginRequest(BaseModel):
    """Login request model"""
    username: str
    password: str

    @field_validator('username', 'password')
    @classmethod
    def sanitize(cls, v: str) -> str:
        # Reject null bytes (crashes PostgreSQL)
        if '\x00' in v:
            raise ValueError('Invalid characters in input')
        # Reject empty / whitespace-only
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        # Cap length before it reaches bcrypt (72-byte truncation) or DB
        if len(v) > 128:
            raise ValueError('Input too long')
        return v.strip()

    @field_validator('username')
    @classmethod
    def username_format(cls, v: str) -> str:
        # Restrict to sane character set — adjust regex to your needs
        import re
        if not re.match(r'^[a-zA-Z0-9_.\-@]+$', v):
            raise ValueError('Invalid characters in username')
        return v

class LoginResponse(BaseModel):
    """Login response model"""
    access_token: str
    refresh_token: str
    user: UserResponse
    expires_in: int = 900  # 15 minutes in seconds
    message: str = "Login successful"

class APIToken(BaseModel):
    """API Token model"""
    id: str
    user_id: str
    token: str = Field(..., max_length=255)
    name: str = Field(default="Legacy Token")
    description: Optional[str] = Field(None, max_length=500)
    permissions: List[str] = Field(default_factory=list)
    is_active: bool = Field(default=True)
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

class APITokenCreateRequest(BaseModel):
    """API Token creation request model"""
    name: str = Field(..., max_length=100, min_length=1)
    description: Optional[str] = Field(None, max_length=500)
    expires_in_days: int = Field(default=90, ge=1, le=365)
    permissions: List[str] = Field(default_factory=list)

class APITokenResponse(BaseModel):
    """API Token response model (without actual token)"""
    id: str
    name: str = Field(default="Legacy Token")
    description: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    is_active: bool = Field(default=True)
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

class APITokenCreateResponse(BaseModel):
    """API Token creation response model (includes actual token)"""
    token: str
    token_info: APITokenResponse

class APITokenListResponse(BaseModel):
    """API Token list response model"""
    tokens: List[APITokenResponse]

class UserCreateRequest(BaseModel):
    """User creation request model"""
    username: str = Field(..., max_length=150, min_length=1)
    email: Optional[str] = Field(None, max_length=254)
    password: str = Field(..., min_length=4)
    first_name: Optional[str] = Field(None, max_length=150)
    last_name: Optional[str] = Field(None, max_length=150)
    roles: List[str] = Field(default_factory=lambda: ["user"])
    program_permissions: Union[Dict[str, str], List[str]] = Field(default_factory=dict, description="Dict mapping program names to permission levels (analyst/manager)")
    is_superuser: bool = Field(default=False)
    is_active: bool = Field(default=True)
    rf_uhash: Optional[str] = None
    hackerone_api_token: Optional[str] = None
    hackerone_api_user: Optional[str] = None
    intigriti_api_token: Optional[str] = None
    force_password_change: bool = Field(
        default=True,
        description="When true, user must change password after first login",
    )

class UserUpdateRequest(BaseModel):
    """User update request model"""
    email: Optional[str] = Field(None, max_length=254)
    first_name: Optional[str] = Field(None, max_length=150)
    last_name: Optional[str] = Field(None, max_length=150)
    roles: Optional[List[str]] = None
    program_permissions: Optional[Union[Dict[str, str], List[str]]] = Field(None, description="Dict mapping program names to permission levels (analyst/manager)")
    is_superuser: Optional[bool] = None
    is_active: Optional[bool] = None
    rf_uhash: Optional[str] = None
    hackerone_api_token: Optional[str] = None
    hackerone_api_user: Optional[str] = None
    intigriti_api_token: Optional[str] = None
    must_change_password: Optional[bool] = None

class PasswordChangeRequest(BaseModel):
    """Password change request model"""
    new_password: str = Field(..., min_length=4)

class OwnPasswordChangeRequest(BaseModel):
    """Authenticated user changes their own password"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=4)

class UserListResponse(BaseModel):
    """User list response model"""
    users: List[UserResponse]
    total: int
    page: int
    limit: int

class RefreshTokenRequest(BaseModel):
    """Refresh token request model"""
    refresh_token: str

class RefreshTokenResponse(BaseModel):
    """Refresh token response model"""
    access_token: str
    expires_in: int = 900  # 15 minutes in seconds
    message: str = "Token refreshed successfully"

class LogoutRequest(BaseModel):
    """Logout request model"""
    refresh_token: str

class UserAssignmentResponse(BaseModel):
    """Simplified user response for assignment dropdowns"""
    id: str
    username: str
    email: Optional[str] = None