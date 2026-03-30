#!/usr/bin/env python3
"""
Common Program Manager for Test Scripts

This module provides a common interface for creating and managing test programs
across all test scripts. It handles program creation with proper scope patterns
and cleanup.

Usage:
    from common_program_manager import TestProgramManager
    
    async with TestProgramManager() as manager:
        program_name = await manager.create_test_program()
        # Run your tests here
        # Program will be automatically deleted when context exits
"""

import httpx
import logging
import uuid
from typing import Optional
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestProgramManager:
    """Manages test program creation and cleanup for test scripts"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_token: Optional[str] = None
        self.created_program_name: Optional[str] = None
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Always cleanup the created program
        if self.created_program_name:
            await self.delete_test_program()
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
                self.auth_token = data.get('token')
                user = data.get('user', {})
                logger.info(f"✅ Login successful for user: {user.get('username')}")
                return True
            else:
                logger.error(f"❌ Login failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login failed with exception: {str(e)}")
            return False
    
    async def create_test_program(self, scope_pattern: str = ".*example\\.com") -> str:
        """Create a test program with the specified scope pattern"""
        if not self.auth_token:
            # Try to login first
            if not await self.login():
                raise Exception("Failed to login and no auth token available")
        
        # Generate a unique program name
        program_name = f"test-{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Creating test program: {program_name}")
        
        try:
            # Prepare program data with scope pattern
            program_data = {
                "name": program_name,
                "domain_regex": [scope_pattern],
                "cidr_list": [],
                "safe_registrar": [],
                "safe_ssl_issuer": []
            }
            
            response = await self.client.post(
                f"{self.base_url}/programs",
                headers={"Authorization": f"Bearer {self.auth_token}"},
                json=program_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Test program created successfully")
                logger.info(f"   Program name: {program_name}")
                logger.info(f"   Program ID: {data.get('id')}")
                logger.info(f"   Scope pattern: {scope_pattern}")
                
                self.created_program_name = program_name
                return program_name
            else:
                logger.error(f"❌ Test program creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                raise Exception(f"Failed to create test program: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Test program creation failed with exception: {str(e)}")
            raise
    
    async def delete_test_program(self) -> bool:
        """Delete the created test program"""
        if not self.created_program_name:
            logger.warning("No test program to delete")
            return True
        
        if not self.auth_token:
            logger.warning("No auth token available for program deletion")
            return False
        
        logger.info(f"Deleting test program: {self.created_program_name}")
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/programs/{self.created_program_name}",
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Test program deleted successfully")
                logger.info(f"   Program name: {self.created_program_name}")
                logger.info(f"   Archived counts: {data.get('archived_counts', {})}")
                self.created_program_name = None
                return True
            else:
                logger.error(f"❌ Test program deletion failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Test program deletion failed with exception: {str(e)}")
            return False

@asynccontextmanager
async def create_test_program(base_url: str = "http://localhost:8001", scope_pattern: str = ".*example\\.com"):
    """
    Context manager for creating and automatically cleaning up test programs.
    
    Args:
        base_url: API base URL
        scope_pattern: Domain regex pattern for program scope
    
    Yields:
        str: The created program name
        
    Example:
        async with create_test_program() as program_name:
            # Use program_name in your tests
            await run_tests(program_name)
    """
    manager = TestProgramManager(base_url)
    try:
        await manager.__aenter__()
        program_name = await manager.create_test_program(scope_pattern)
        yield program_name
    finally:
        await manager.__aexit__(None, None, None)

# Convenience function for backward compatibility
async def get_test_program(base_url: str = "http://localhost:8001", scope_pattern: str = ".*example\\.com") -> str:
    """
    Create a test program and return its name.
    Note: This function does NOT automatically clean up the program.
    Use the context manager version for automatic cleanup.
    
    Args:
        base_url: API base URL
        scope_pattern: Domain regex pattern for program scope
    
    Returns:
        str: The created program name
    """
    manager = TestProgramManager(base_url)
    await manager.__aenter__()
    program_name = await manager.create_test_program(scope_pattern)
    # Note: We don't call __aexit__ here, so cleanup must be done manually
    return program_name, manager 