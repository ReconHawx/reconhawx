#!/usr/bin/env python3
"""
URL Routes Test Suite

This script tests the URL-related endpoints in the assets API:
- Create URLs via receive_asset endpoint
- Get URL by URL string
- Get URLs by program
- Query URLs with filters
- Update URL notes
- Delete URLs
- Verify operations

Usage:
    python test_url_routes.py
"""

import asyncio
import httpx
import logging
import uuid
from typing import Optional

# Import the common program manager and auth manager
from common_program_manager import create_test_program
from common_auth_manager import TestAuthManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class URLRouteTester:
    """Test class for URL-related API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_manager: Optional[TestAuthManager] = None
        self.created_url_id: Optional[str] = None
        self.test_program: Optional[str] = None
        self.test_url = f"https://test-{uuid.uuid4().hex[:8]}.example.com/api/test"
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
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
    
    async def test_create_url(self) -> bool:
        """Test creating a URL via POST /assets (receive_asset endpoint)"""
        logger.info(f"Testing URL creation: {self.test_url}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            # Prepare asset data for the receive_asset endpoint
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "url": [
                        {
                            "url": self.test_url,
                            "status_code": 200,
                            "title": "Test API Page",
                            "content_length": 1024,
                            "content_type": "text/html",
                            "headers": {
                                "server": "nginx",
                                "x-powered-by": "Express"
                            },
                            "technologies": ["nginx", "express", "nodejs"],
                            "notes": "Test URL for API testing"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data,
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ URL creation successful")
                logger.info(f"   URL: {self.test_url}")
                logger.info(f"   Program: {self.test_program}")
                
                # Store the URL ID for later tests
                if 'url' in data and data['url']:
                    self.created_url_id = data['url'][0].get('id') or data['url'][0].get('_id')
                    if self.created_url_id:
                        logger.info(f"   URL ID: {self.created_url_id}")
                    else:
                        logger.warning("   ⚠️  No URL ID found in response")
                else:
                    logger.warning("   ⚠️  No URL data in response")
                
                return True
            else:
                logger.error(f"❌ URL creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ URL creation test failed with exception: {str(e)}")
            return False
    
    async def test_get_url_by_url_string(self) -> bool:
        """Test getting URL by URL string via POST /assets/url/search with exact_match"""
        logger.info(f"Testing get URL by URL string: {self.test_url}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/assets/url/search",
                json={
                    "exact_match": self.test_url,
                    "program": self.test_program,
                    "page": 1,
                    "page_size": 10
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                urls = data.get('items', [])
                
                if urls:
                    url_data = urls[0]  # Should be the exact match
                    logger.info("✅ Get URL by URL string successful")
                    logger.info(f"   URL: {url_data.get('url')}")
                    logger.info(f"   Status Code: {url_data.get('status_code')}")
                    logger.info(f"   Title: {url_data.get('title')}")
                    logger.info(f"   Program: {url_data.get('program_name')}")
                    
                    # Store the URL ID for later tests
                    self.created_url_id = url_data.get('id') or url_data.get('_id')
                    if self.created_url_id:
                        logger.info(f"   URL ID: {self.created_url_id}")
                    else:
                        logger.warning("   ⚠️  No URL ID found in response")
                    
                    return True
                else:
                    logger.error("   ❌ No URLs found with exact match")
                    return False
            else:
                logger.error(f"❌ Get URL by URL string failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get URL by URL string test failed with exception: {str(e)}")
            return False
    
    async def test_get_urls_by_program(self) -> bool:
        """Test getting URLs by program via POST /assets/url/search"""
        logger.info(f"Testing get URLs by program: {self.test_program}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/assets/url/search",
                json={
                    "program": self.test_program,
                    "page": 1,
                    "page_size": 100
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                urls = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Get URLs by program successful")
                logger.info(f"   Program: {self.test_program}")
                logger.info(f"   Found URLs: {len(urls)}")
                logger.info(f"   Total in program: {pagination.get('total', 0)}")
                
                # Check if our test URL is in the list and store its ID
                test_url_found = False
                for u in urls:
                    if u.get('url') == self.test_url:
                        test_url_found = True
                        # Store the URL ID for later tests
                        self.created_url_id = u.get('id') or u.get('_id')
                        if self.created_url_id:
                            logger.info("   ✅ Test URL found in program list")
                            logger.info(f"   URL ID: {self.created_url_id}")
                        else:
                            logger.warning("   ⚠️  No URL ID found in response")
                        break
                
                if test_url_found:
                    return True
                else:
                    logger.error("   ❌ Test URL not found in program list")
                    logger.error(f"   Looking for: {self.test_url}")
                    available_urls = [u.get('url') for u in urls[:5]]  # Show first 5 URLs
                    logger.error(f"   Available URLs (first 5): {available_urls}")
                    return False
            else:
                logger.error(f"❌ Get URLs by program failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get URLs by program test failed with exception: {str(e)}")
            return False
    
    async def test_query_urls_with_filters(self) -> bool:
        """Test querying URLs with filters via POST /assets/url/search"""
        logger.info("Testing query URLs with filters")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/assets/url/search",
                json={
                    "program": self.test_program,
                    "status_code": 200,
                    "page": 1,
                    "page_size": 50
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                urls = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Query URLs with filters successful")
                logger.info(f"   Program filter: {self.test_program}")
                logger.info(f"   Status code filter: 200")
                logger.info(f"   Content type filter: text/html")
                logger.info(f"   Found URLs: {len(urls)}")
                logger.info(f"   Total matching: {pagination.get('total', 0)}")
                
                return True
            else:
                logger.error(f"❌ Query URLs with filters failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Query URLs with filters test failed with exception: {str(e)}")
            return False
    
    async def test_update_url_notes(self) -> bool:
        """Test updating URL notes"""
        logger.info(f"Testing update URL notes: {self.created_url_id}")
        
        if not self.created_url_id:
            logger.error("❌ No URL ID available")
            return False
        
        try:
            update_data = {
                "notes": "Updated test notes for URL - API testing completed successfully!"
            }
            
            response = await self.client.put(
                f"{self.base_url}/assets/url/{self.created_url_id}/notes",
                json=update_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update URL notes successful")
                logger.info(f"   New notes: {data.get('notes')}")
                return True
            else:
                logger.error(f"❌ Update URL notes failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update URL notes test failed with exception: {str(e)}")
            return False
    
    async def test_verify_url_update(self) -> bool:
        """Test verifying that URL update was applied correctly"""
        logger.info(f"Testing verify URL update: {self.created_url_id}")
        
        if not self.created_url_id:
            logger.error("❌ No URL ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/url",
                params={"id": self.created_url_id},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                url_data = data.get('data', {})
                
                logger.info("✅ Verify URL update successful")
                logger.info(f"   URL: {url_data.get('url')}")
                logger.info(f"   Notes: {url_data.get('notes')}")
                
                # Verify the update was applied
                if 'API testing completed successfully' in url_data.get('notes', ''):
                    logger.info("✅ Notes update verified successfully")
                    return True
                else:
                    logger.error("❌ Notes update not properly applied")
                    return False
            else:
                logger.error(f"❌ Verify URL update failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify URL update test failed with exception: {str(e)}")
            return False
    
    async def test_delete_url(self) -> bool:
        """Test deleting URL"""
        logger.info(f"Testing delete URL: {self.created_url_id}")
        
        if not self.created_url_id:
            logger.error("❌ No URL ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/assets/url/{self.created_url_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete URL successful")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete URL failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete URL test failed with exception: {str(e)}")
            return False
    
    async def test_verify_url_deletion(self) -> bool:
        """Test verifying that URL was properly deleted"""
        logger.info(f"Testing verify URL deletion: {self.created_url_id}")
        
        if not self.created_url_id:
            logger.error("❌ No URL ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/url",
                params={"id": self.created_url_id},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 404:
                logger.info("✅ URL properly deleted (404 Not Found)")
                return True
            elif response.status_code == 200:
                logger.error("❌ URL still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify URL deletion test failed with exception: {str(e)}")
            return False

async def run_url_tests():
    """Run all URL route tests"""
    logger.info("🚀 Starting URL Routes Test Suite")
    logger.info("=" * 60)
    
    # Create a test program with proper scope
    async with create_test_program(scope_pattern=".*example\\.com") as test_program_name:
        logger.info(f"📋 Using test program: {test_program_name}")
        
        async with URLRouteTester() as tester:
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
            
            # Test 2: Create URL
            logger.info("\n📝 Test 2: Create URL")
            result = await tester.test_create_url()
            test_results.append(("Create URL", result))
            
            if not result:
                logger.error("❌ URL creation failed, cannot continue with other tests")
                return False
            
            # Test 3: Get URL by URL string
            logger.info("\n📝 Test 3: Get URL by URL String")
            result = await tester.test_get_url_by_url_string()
            test_results.append(("Get URL by URL String", result))
            
            # Test 4: Get URLs by program
            logger.info("\n📝 Test 4: Get URLs by Program")
            result = await tester.test_get_urls_by_program()
            test_results.append(("Get URLs by Program", result))
            
            # Test 5: Query URLs with filters
            logger.info("\n📝 Test 5: Query URLs with Filters")
            result = await tester.test_query_urls_with_filters()
            test_results.append(("Query URLs with Filters", result))
            
            # Test 6: Update URL notes
            logger.info("\n📝 Test 6: Update URL Notes")
            result = await tester.test_update_url_notes()
            test_results.append(("Update URL Notes", result))
            
            # Test 7: Verify URL update
            logger.info("\n📝 Test 7: Verify URL Update")
            result = await tester.test_verify_url_update()
            test_results.append(("Verify URL Update", result))
            
            # Test 8: Delete URL
            logger.info("\n📝 Test 8: Delete URL")
            result = await tester.test_delete_url()
            test_results.append(("Delete URL", result))
            
            # Test 9: Verify URL deletion
            logger.info("\n📝 Test 9: Verify URL Deletion")
            result = await tester.test_verify_url_deletion()
            test_results.append(("Verify URL Deletion", result))
            
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
                logger.info("🎉 All tests passed! URL routes are working correctly.")
            else:
                logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
            
            return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_url_tests())
    exit(0 if success else 1) 