#!/usr/bin/env python3
"""
Common Auth Manager for Test Scripts

This module provides a common interface for authentication across all test scripts.
It handles login, token management, and session cleanup.

Usage:
    from common_auth_manager import TestAuthManager
    
    async with TestAuthManager() as auth_manager:
        await auth_manager.login()
        # Use auth_manager.auth_token for authenticated requests
        # Session will be automatically cleaned up when context exits
"""

import httpx
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestAuthManager:
    """Manages authentication for test scripts"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_token: Optional[str] = None
        self.user_info: Optional[Dict[str, Any]] = None
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def login(self, username: str = "admin", password: str = "password") -> bool:
        """Login to get authentication token"""
        logger.info(f"Logging in with username: {username}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get('token')  # API returns 'token', not 'access_token'
                self.user_info = data.get('user', {})
                user_id = self.user_info.get('id') or self.user_info.get('_id')
                
                logger.info("✅ Login successful")
                logger.info(f"   User ID: {user_id}")
                logger.info(f"   Username: {self.user_info.get('username')}")
                logger.info(f"   Token: {self.auth_token[:20]}..." if self.auth_token else "No token")
                return True
            else:
                logger.error(f"❌ Login failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login failed with exception: {str(e)}")
            return False
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests"""
        if not self.auth_token:
            return {}
        return {"Authorization": f"Bearer {self.auth_token}"}
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self.auth_token is not None
    
    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get user information"""
        return self.user_info

@asynccontextmanager
async def create_auth_session(base_url: str = "http://localhost:8001", username: str = "admin", password: str = "password"):
    """
    Context manager for creating and managing authentication sessions.
    
    Args:
        base_url: API base URL
        username: Username for login
        password: Password for login
    
    Yields:
        TestAuthManager: Authenticated auth manager instance
        
    Example:
        async with create_auth_session() as auth_manager:
            # Use auth_manager.auth_token for authenticated requests
            headers = auth_manager.get_auth_headers()
            response = await client.get("/some/endpoint", headers=headers)
    """
    manager = TestAuthManager(base_url)
    try:
        await manager.__aenter__()
        success = await manager.login(username, password)
        if not success:
            raise Exception("Failed to authenticate")
        yield manager
    finally:
        await manager.__aexit__(None, None, None)

# Convenience function for backward compatibility
async def get_auth_session(base_url: str = "http://localhost:8001", username: str = "admin", password: str = "password") -> TestAuthManager:
    """
    Create an authenticated session and return the auth manager.
    Note: This function does NOT automatically clean up the session.
    Use the context manager version for automatic cleanup.
    
    Args:
        base_url: API base URL
        username: Username for login
        password: Password for login
    
    Returns:
        TestAuthManager: Authenticated auth manager instance
    """
    manager = TestAuthManager(base_url)
    await manager.__aenter__()
    success = await manager.login(username, password)
    if not success:
        raise Exception("Failed to authenticate")
    # Note: We don't call __aexit__ here, so cleanup must be done manually
    return manager
