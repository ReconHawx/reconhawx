#!/usr/bin/env python3
"""
Screenshot Routes Test Suite

This script tests the screenshot-related endpoints in the assets API:
- Upload screenshots
- Check screenshot existence
- Get screenshots by file ID
- List screenshots with filters
- Get screenshot metadata
- Get screenshot duplicate stats
- Delete screenshots
- Verify operations

Usage:
    python test_screenshot_routes.py
"""

import asyncio
import httpx
import logging
import uuid
from typing import Optional
from io import BytesIO
from PIL import Image

# Import the common program manager and auth manager
from common_program_manager import create_test_program
from common_auth_manager import TestAuthManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ScreenshotRouteTester:
    """Test class for screenshot-related API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_manager: Optional[TestAuthManager] = None
        self.created_file_id: Optional[str] = None
        self.test_program: Optional[str] = None
        self.test_url = f"https://test-{uuid.uuid4().hex[:8]}.example.com"
        self.test_workflow_id = f"test-workflow-{uuid.uuid4().hex[:8]}"
        self.test_step_name = "screenshot-test"
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def create_test_image(self):
        """Create a simple test image"""
        # Create a 100x100 red image
        img = Image.new('RGB', (100, 100), color='red')
        img_io = BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return img_io.getvalue()
    
    async def test_login(self, username: str = "admin", password: str = "password") -> bool:
        """Test user authentication using TestAuthManager"""
        logger.info(f"Testing login with {username}")
        
        try:
            # Use TestAuthManager for authentication
            self.auth_manager = TestAuthManager(self.base_url)
            await self.auth_manager.__aenter__()
            success = await self.auth_manager.login(username, password)
            
            if success:
                logger.info("✅ Login successful using TestAuthManager")
                logger.info(f"   User ID: {self.auth_manager.get_user_info().get('id') or self.auth_manager.get_user_info().get('_id')}")
                logger.info(f"   Username: {self.auth_manager.get_user_info().get('username')}")
                logger.info(f"   Token: {self.auth_manager.auth_token[:20]}..." if self.auth_manager.auth_token else "No token")
                return True
            else:
                logger.error("❌ Login failed using TestAuthManager")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login test failed with exception: {str(e)}")
            return False

    async def test_upload_screenshot(self) -> bool:
        """Test screenshot upload"""
        logger.info(f"Testing screenshot upload: {self.test_url}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            # Create test image data
            image_data = self.create_test_image()
            
            # Prepare form data for upload
            files = {
                'file': ('test_screenshot.png', image_data, 'image/png')
            }
            data = {
                'url': self.test_url,
                'program_name': self.test_program,
                'workflow_id': self.test_workflow_id,
                'step_name': self.test_step_name
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets/screenshots",
                files=files,
                data=data,
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Screenshot upload successful")
                logger.info(f"   URL: {data.get('url')}")
                logger.info(f"   File ID: {data.get('file_id')}")
                logger.info(f"   Program: {data.get('program_name')}")
                logger.info(f"   Workflow: {data.get('workflow_id')}")
                
                # Store the file ID for later tests
                self.created_file_id = data.get('file_id')
                if self.created_file_id:
                    logger.info(f"   Stored file ID: {self.created_file_id}")
                
                return True
            else:
                logger.error(f"❌ Screenshot upload failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Screenshot upload test failed with exception: {str(e)}")
            return False
    
    async def test_check_screenshot_exists(self) -> bool:
        """Test checking if screenshot exists"""
        logger.info(f"Testing screenshot existence check: {self.test_url}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/screenshots/exists",
                params={"url": self.test_url},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                exists = data.get('exists', False)
                logger.info("✅ Screenshot existence check successful")
                logger.info(f"   URL: {self.test_url}")
                logger.info(f"   Exists: {exists}")
                
                if exists:
                    logger.info("   ✅ Screenshot found in database")
                    return True
                else:
                    logger.warning("   ⚠️  Screenshot not found in database")
                    return False
            else:
                logger.error(f"❌ Screenshot existence check failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Screenshot existence check test failed with exception: {str(e)}")
            return False
    
    async def test_get_screenshot_by_file_id(self) -> bool:
        """Test getting screenshot by file ID"""
        logger.info(f"Testing get screenshot by file ID: {self.created_file_id}")
        
        if not self.created_file_id:
            logger.error("❌ No file ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/screenshots/{self.created_file_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                screenshot_data = data.get('data', {})
                logger.info("✅ Get screenshot by file ID successful")
                logger.info(f"   URL: {screenshot_data.get('url')}")
                logger.info(f"   File ID: {screenshot_data.get('file_id')}")
                logger.info(f"   Program: {screenshot_data.get('program_name')}")
                logger.info(f"   Workflow: {screenshot_data.get('workflow_id')}")
                logger.info(f"   Step: {screenshot_data.get('step_name')}")
                
                return True
            else:
                logger.error(f"❌ Get screenshot by file ID failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get screenshot by file ID test failed with exception: {str(e)}")
            return False
    
    async def test_list_screenshots(self) -> bool:
        """Test listing screenshots with filters"""
        logger.info("Testing list screenshots with filters")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/screenshots",
                params={
                    "program_name": self.test_program,
                    "limit": 100
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                screenshots = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ List screenshots successful")
                logger.info(f"   Program filter: {self.test_program}")
                logger.info(f"   Found screenshots: {len(screenshots)}")
                logger.info(f"   Total in program: {pagination.get('total', 0)}")
                
                return True
            else:
                logger.error(f"❌ List screenshots failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ List screenshots test failed with exception: {str(e)}")
            return False
    
    async def test_get_screenshot_metadata(self) -> bool:
        """Test getting screenshot metadata"""
        logger.info(f"Testing get screenshot metadata: {self.created_file_id}")
        
        if not self.created_file_id:
            logger.error("❌ No file ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/screenshots/{self.created_file_id}/metadata",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                metadata = data.get('metadata', {})
                logger.info("✅ Get screenshot metadata successful")
                logger.info(f"   File ID: {metadata.get('file_id')}")
                logger.info(f"   File size: {metadata.get('file_size')}")
                logger.info(f"   Content type: {metadata.get('content_type')}")
                logger.info(f"   Created at: {metadata.get('created_at')}")
                
                return True
            else:
                logger.error(f"❌ Get screenshot metadata failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get screenshot metadata test failed with exception: {str(e)}")
            return False
    
    async def test_get_screenshot_duplicate_stats(self) -> bool:
        """Test getting screenshot duplicate statistics"""
        logger.info("Testing get screenshot duplicate statistics")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/screenshots/duplicates/stats",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                stats = data.get('stats', {})
                logger.info("✅ Get screenshot duplicate stats successful")
                logger.info(f"   Total screenshots: {stats.get('total', 0)}")
                logger.info(f"   Unique screenshots: {stats.get('unique', 0)}")
                logger.info(f"   Duplicate groups: {stats.get('duplicate_groups', 0)}")
                logger.info(f"   Space saved: {stats.get('space_saved', 0)} bytes")
                
                return True
            else:
                logger.error(f"❌ Get screenshot duplicate stats failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get screenshot duplicate stats test failed with exception: {str(e)}")
            return False
    
    async def test_delete_screenshot(self) -> bool:
        """Test deleting screenshot"""
        logger.info(f"Testing delete screenshot: {self.created_file_id}")
        
        if not self.created_file_id:
            logger.error("❌ No file ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/assets/screenshots/{self.created_file_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete screenshot successful")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete screenshot failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete screenshot test failed with exception: {str(e)}")
            return False
    
    async def test_verify_screenshot_deletion(self) -> bool:
        """Test verifying that screenshot was properly deleted"""
        logger.info(f"Testing verify screenshot deletion: {self.created_file_id}")
        
        if not self.created_file_id:
            logger.error("❌ No file ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/screenshots/{self.created_file_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 404:
                logger.info("✅ Screenshot properly deleted (404 Not Found)")
                return True
            elif response.status_code == 200:
                logger.error("❌ Screenshot still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify screenshot deletion test failed with exception: {str(e)}")
            return False

async def run_screenshot_tests():
    """Run all screenshot route tests"""
    logger.info("🚀 Starting Screenshot Routes Test Suite")
    logger.info("=" * 60)
    
    # Create a test program with proper scope
    async with create_test_program(scope_pattern=".*example\\.com") as test_program_name:
        logger.info(f"📋 Using test program: {test_program_name}")
        
        async with ScreenshotRouteTester() as tester:
            # Set the test program name
            tester.test_program = test_program_name
            
            test_results = []
            
            # Test 1: Login (needed for authenticated endpoints)
            logger.info("\n📝 Test 1: Login")
            result = await tester.test_login()
            test_results.append(("Login", result))
            
            if not result:
                logger.error("❌ Login failed, cannot continue with other tests")
                return False
            
            # Test 2: Upload screenshot
            logger.info("\n📝 Test 2: Upload Screenshot")
            result = await tester.test_upload_screenshot()
            test_results.append(("Upload Screenshot", result))
            
            if not result:
                logger.error("❌ Screenshot upload failed, cannot continue with other tests")
                return False
            
            # Test 3: Check screenshot exists
            logger.info("\n📝 Test 3: Check Screenshot Exists")
            result = await tester.test_check_screenshot_exists()
            test_results.append(("Check Screenshot Exists", result))
            
            # Test 4: Get screenshot by file ID
            logger.info("\n📝 Test 4: Get Screenshot by File ID")
            result = await tester.test_get_screenshot_by_file_id()
            test_results.append(("Get Screenshot by File ID", result))
            
            # Test 5: List screenshots
            logger.info("\n📝 Test 5: List Screenshots")
            result = await tester.test_list_screenshots()
            test_results.append(("List Screenshots", result))
            
            # Test 6: Get screenshot metadata
            logger.info("\n📝 Test 6: Get Screenshot Metadata")
            result = await tester.test_get_screenshot_metadata()
            test_results.append(("Get Screenshot Metadata", result))
            
            # Test 7: Get screenshot duplicate stats
            logger.info("\n📝 Test 7: Get Screenshot Duplicate Stats")
            result = await tester.test_get_screenshot_duplicate_stats()
            test_results.append(("Get Screenshot Duplicate Stats", result))
            
            # Test 8: Delete screenshot
            logger.info("\n📝 Test 8: Delete Screenshot")
            result = await tester.test_delete_screenshot()
            test_results.append(("Delete Screenshot", result))
            
            # Test 9: Verify screenshot deletion
            logger.info("\n📝 Test 9: Verify Screenshot Deletion")
            result = await tester.test_verify_screenshot_deletion()
            test_results.append(("Verify Screenshot Deletion", result))
            
            # Summary
            logger.info("\n" + "=" * 60)
            logger.info("📊 Test Results Summary")
            logger.info("=" * 60)
            
            passed = 0
            total = len(test_results)
            
            for test_name, result in test_results:
                status = "✅ PASS" if result else "❌ FAIL"
                logger.info(f"{status} - {test_name}")
                if result:
                    passed += 1
            
            logger.info(f"\n🎯 Overall Result: {passed}/{total} tests passed")
            
            if passed == total:
                logger.info("🎉 All tests passed! Screenshot routes are working correctly.")
            else:
                logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
            
            return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_screenshot_tests())
    exit(0 if success else 1) 