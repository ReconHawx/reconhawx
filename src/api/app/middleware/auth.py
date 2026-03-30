from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from auth.dependencies import get_current_user
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for protecting API endpoints
    """
    
    def __init__(self, app, public_paths: Optional[list] = None):
        super().__init__(app)
        self.security = HTTPBearer(auto_error=False)
        
        # Public paths that don't require authentication
        # Note: Use exact matches for root and specific endpoints
        self.public_paths = public_paths or [
            "/status",
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/auth/login",
            "/auth/refresh",
            "/nuclei-templates/raw"
        ]
        
        # Handle root path separately to avoid matching all paths
        self.public_exact_paths = ["/"]
    
    async def dispatch(self, request: Request, call_next):
        # Check if the path requires authentication
        path = request.url.path
        
        # Allow exact public paths without authentication
        if path in self.public_exact_paths:
            return await call_next(request)
            
        # Allow prefix public paths without authentication  
        if any(path.startswith(public_path) for public_path in self.public_paths):
            return await call_next(request)
        
        # All other paths require authentication (secure by default)
        # Extract authorization header
        auth_header = request.headers.get("authorization")

        # Support token via query param for image assets where browsers can't set headers (e.g., <img src=...>)
        # Restrict this behavior to screenshots endpoints only
        if (not auth_header or not auth_header.startswith("Bearer ")) and (path.startswith("/assets/screenshot") or path.startswith("/findings/typosquat-screenshot")):
            token_qp = request.query_params.get("token") or request.query_params.get("auth") or request.query_params.get("api_token")
            if token_qp:
                auth_header = f"Bearer {token_qp}"
        
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required", "status": "error"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        try:
            # Create credentials object for dependency
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=auth_header.split(" ")[1]
            )
            
            # Verify the token using our auth dependency
            current_user = await get_current_user(credentials)
            
            if not current_user:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or expired token", "status": "error"},
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Add user to request state for use in endpoints
            request.state.current_user = current_user
            
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication failed", "status": "error"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Continue to the endpoint
        return await call_next(request)