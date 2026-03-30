from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
import os
import secrets
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
REFRESH_SECRET_KEY = os.getenv("REFRESH_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))  # Reduced to 15 minutes
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify password using bcrypt.
    """
    try:
        if not password or not hashed_password:
            return False
        if len(password) > 72:
            return False  # or use a prehash strategy
        if '\x00' in password:
            return False
        
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
            
    except Exception as e:
        print(f"Password verification error: {e}")
        return False

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def generate_access_token(data: dict):
    """Create short-lived JWT access token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str):
    """Decode and verify JWT access token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        username: Optional[str] = payload.get("sub")
        if username is None:
            return None
        return payload
    except JWTError:
        return None

def decode_refresh_token(token: str):
    """Decode and verify JWT refresh token"""
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        username: Optional[str] = payload.get("sub")
        if username is None:
            return None
        return payload
    except JWTError:
        return None

def generate_refresh_token_value():
    """Generate cryptographically secure refresh token value"""
    return f"recon_refresh_{secrets.token_urlsafe(32)}"

def hash_token_sha256(token: str) -> str:
    """Hash a token using SHA256 for database storage and lookup."""
    import hashlib
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def hash_refresh_token(token: str) -> str:
    """Hash refresh token using SHA256 for database lookup efficiency"""
    return hash_token_sha256(token)

def verify_refresh_token_hash(token: str, stored_hash: str) -> bool:
    """Verify refresh token by comparing SHA256 hashes"""
    import hashlib
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    return token_hash == stored_hash

def validate_secret_keys():
    """Validate that required JWT secret keys are configured. Call at startup."""
    if not SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is not set. "
            "The API cannot start without a signing key."
        )
    if len(SECRET_KEY) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is too short (minimum 32 characters). "
            "Use a cryptographically random value."
        )

def get_password_hash_format(hashed_password: str) -> str:
    """Determine the password hash format"""
    if not hashed_password:
        return "unknown"
    
    if hashed_password.startswith('$2b$') or hashed_password.startswith('$2a$'):
        return "bcrypt"
    else:
        return "unknown"