#!/usr/bin/env python3
"""
Test script for Wordlist Routes
Tests POST, GET, PUT, and DELETE operations for wordlist endpoints
"""

import asyncio
from common_auth_manager import TestAuthManager
import logging
import httpx
import uuid
import tempfile
import os
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WordlistRouteTester:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
        self.auth_manager: Optional[TestAuthManager] = None
        self.test_wordlist_name = f"test-wordlist-{uuid.uuid4().hex[:8]}"
        self.test_program = "h3xit"
        self.created_wordlist_id: Optional[str] = None
        self.test_file_content = b"test1\ntest2\ntest3\ntest4\ntest5\n"
        
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
    
    async def test_upload_wordlist(self) -> bool:
        """Test uploading a wordlist via POST /wordlists/"""
        logger.info(f"Testing wordlist upload: {self.test_wordlist_name}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth token available")
            return False
        
        try:
            # Create a temporary file for upload
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as temp_file:
                temp_file.write(self.test_file_content)
                temp_file_path = temp_file.name
            
            try:
                # Prepare form data for upload
                files = {
                    'file': ('test_wordlist.txt', self.test_file_content, 'text/plain')
                }
                data = {
                    'name': self.test_wordlist_name,
                    'description': 'Test wordlist for API testing',
                    'tags': 'test,api,wordlist',
                    'program_name': self.test_program
                }
                
                response = await self.client.post(
                    f"{self.base_url}/wordlists/",
                    headers=self.auth_manager.get_auth_headers(),
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    logger.info("✅ Wordlist upload successful")
                    logger.info(f"   ID: {response_data.get('id')}")
                    logger.info(f"   Name: {response_data.get('name')}")
                    logger.info(f"   Filename: {response_data.get('filename')}")
                    logger.info(f"   File Size: {response_data.get('file_size')}")
                    logger.info(f"   Word Count: {response_data.get('word_count')}")
                    logger.info(f"   Status: {response_data.get('status')}")
                    
                    # Store the wordlist ID for later tests
                    self.created_wordlist_id = response_data.get('id')
                    return True
                else:
                    logger.error(f"❌ Wordlist upload failed with status {response.status_code}")
                    logger.error(f"   Response: {response.text}")
                    return False
                    
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                
        except Exception as e:
            logger.error(f"❌ Wordlist upload test failed with exception: {str(e)}")
            return False
    
    async def test_list_wordlists(self) -> bool:
        """Test listing wordlists via GET /wordlists/"""
        logger.info("Testing list wordlists")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth token available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/wordlists/",
                headers=self.auth_manager.get_auth_headers(),
                params={
                    "limit": 100,
                    "skip": 0,
                    "active_only": True
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                wordlists = data.get('wordlists', [])
                total = data.get('total', 0)
                page = data.get('page', 1)
                limit = data.get('limit', 100)
                
                logger.info("✅ List wordlists successful")
                logger.info(f"   Found {len(wordlists)} wordlists")
                logger.info(f"   Total: {total}")
                logger.info(f"   Page: {page}")
                logger.info(f"   Limit: {limit}")
                
                # Check if our test wordlist is in the list
                test_wordlist_found = any(w.get('name') == self.test_wordlist_name for w in wordlists)
                if test_wordlist_found:
                    logger.info("   ✅ Test wordlist found in list")
                    return True
                else:
                    logger.error("   ❌ Test wordlist not found in list")
                    logger.error(f"   Looking for: {self.test_wordlist_name}")
                    available_wordlists = [w.get('name') for w in wordlists[:5]]  # Show first 5
                    logger.error(f"   Available wordlists (first 5): {available_wordlists}")
                    return False
            else:
                logger.error(f"❌ List wordlists failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ List wordlists test failed with exception: {str(e)}")
            return False
    
    async def test_get_wordlist_by_id(self) -> bool:
        """Test getting a wordlist by ID via GET /wordlists/{wordlist_id}"""
        logger.info(f"Testing get wordlist by ID: {self.created_wordlist_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.created_wordlist_id:
            logger.error("❌ No auth token or wordlist ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/wordlists/{self.created_wordlist_id}",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Get wordlist by ID successful")
                logger.info(f"   ID: {data.get('id')}")
                logger.info(f"   Name: {data.get('name')}")
                logger.info(f"   Description: {data.get('description')}")
                logger.info(f"   Filename: {data.get('filename')}")
                logger.info(f"   File Size: {data.get('file_size')}")
                logger.info(f"   Word Count: {data.get('word_count')}")
                logger.info(f"   Tags: {data.get('tags')}")
                logger.info(f"   Program: {data.get('program_name')}")
                logger.info(f"   Created By: {data.get('created_by')}")
                logger.info(f"   Is Active: {data.get('is_active')}")
                return True
            else:
                logger.error(f"❌ Get wordlist by ID failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get wordlist by ID test failed with exception: {str(e)}")
            return False
    
    async def test_download_wordlist(self) -> bool:
        """Test downloading a wordlist file via GET /wordlists/{wordlist_id}/download"""
        logger.info(f"Testing download wordlist: {self.created_wordlist_id}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/wordlists/{self.created_wordlist_id}/download",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                content = response.content
                logger.info("✅ Download wordlist successful")
                logger.info(f"   Content Length: {len(content)} bytes")
                logger.info(f"   Content Type: {response.headers.get('content-type')}")
                logger.info(f"   Content Disposition: {response.headers.get('content-disposition')}")
                
                # Verify content matches our test content
                if content == self.test_file_content:
                    logger.info("   ✅ Downloaded content matches original")
                    return True
                else:
                    logger.error("   ❌ Downloaded content does not match original")
                    logger.error(f"   Expected: {len(self.test_file_content)} bytes")
                    logger.error(f"   Got: {len(content)} bytes")
                    return False
            else:
                logger.error(f"❌ Download wordlist failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Download wordlist test failed with exception: {str(e)}")
            return False
    
    async def test_update_wordlist(self) -> bool:
        """Test updating a wordlist via PUT /wordlists/{wordlist_id}"""
        logger.info(f"Testing update wordlist: {self.created_wordlist_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.created_wordlist_id:
            logger.error("❌ No auth token or wordlist ID available")
            return False
        
        try:
            # Prepare update data
            update_data = {
                "name": f"{self.test_wordlist_name}-updated",
                "description": "Updated description for test wordlist",
                "tags": ["test", "api", "wordlist", "updated"],
                "is_active": True
            }
            
            response = await self.client.put(
                f"{self.base_url}/wordlists/{self.created_wordlist_id}",
                headers=self.auth_manager.get_auth_headers(),
                json=update_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update wordlist successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                logger.info(f"   Updated Name: {data.get('name')}")
                return True
            else:
                logger.error(f"❌ Update wordlist failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update wordlist test failed with exception: {str(e)}")
            return False
    
    async def test_verify_wordlist_update(self) -> bool:
        """Test verifying the wordlist was updated correctly"""
        logger.info(f"Testing verify wordlist update: {self.created_wordlist_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.created_wordlist_id:
            logger.error("❌ No auth token or wordlist ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/wordlists/{self.created_wordlist_id}",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Verify wordlist update successful")
                logger.info(f"   Name: {data.get('name')}")
                logger.info(f"   Description: {data.get('description')}")
                logger.info(f"   Tags: {data.get('tags')}")
                
                # Check if name was updated
                if data.get('name') == f"{self.test_wordlist_name}-updated":
                    logger.info("   ✅ Name was updated correctly")
                    return True
                else:
                    logger.error("   ❌ Name was not updated correctly")
                    return False
            else:
                logger.error(f"❌ Verify wordlist update failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify wordlist update test failed with exception: {str(e)}")
            return False
    
    async def test_search_wordlists(self) -> bool:
        """Test searching wordlists with filters"""
        logger.info("Testing search wordlists")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth token available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/wordlists/",
                headers=self.auth_manager.get_auth_headers(),
                params={
                    "search": "test-wordlist",
                    "program_name": self.test_program,
                    "tags": "test",
                    "limit": 100
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                wordlists = data.get('wordlists', [])
                total = data.get('total', 0)
                
                logger.info("✅ Search wordlists successful")
                logger.info(f"   Found {len(wordlists)} wordlists matching search")
                logger.info(f"   Total: {total}")
                
                # Check if our test wordlist is in the results
                test_wordlist_found = any(w.get('name') == f"{self.test_wordlist_name}-updated" for w in wordlists)
                if test_wordlist_found:
                    logger.info("   ✅ Test wordlist found in search results")
                    return True
                else:
                    logger.error("   ❌ Test wordlist not found in search results")
                    return False
            else:
                logger.error(f"❌ Search wordlists failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Search wordlists test failed with exception: {str(e)}")
            return False
    
    async def test_delete_wordlist(self) -> bool:
        """Test deleting a wordlist via DELETE /wordlists/{wordlist_id}"""
        logger.info(f"Testing delete wordlist: {self.created_wordlist_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.created_wordlist_id:
            logger.error("❌ No auth token or wordlist ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/wordlists/{self.created_wordlist_id}",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete wordlist successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete wordlist failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete wordlist test failed with exception: {str(e)}")
            return False
    
    async def test_verify_wordlist_deletion(self) -> bool:
        """Test verifying the wordlist was deleted correctly"""
        logger.info(f"Testing verify wordlist deletion: {self.created_wordlist_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.created_wordlist_id:
            logger.error("❌ No auth token or wordlist ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/wordlists/{self.created_wordlist_id}",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 404:
                logger.info("✅ Verify wordlist deletion successful - wordlist not found (404)")
                return True
            elif response.status_code == 200:
                logger.error("❌ Wordlist still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify wordlist deletion test failed with exception: {str(e)}")
            return False

async def run_wordlist_tests():
    """Run all wordlist route tests"""
    logger.info("🚀 Starting Wordlist Routes Test Suite")
    logger.info("=" * 60)
    
    async with WordlistRouteTester() as tester:
        test_results = []
        
        # Test 1: Login (needed for most endpoints)
        logger.info("\n📝 Test 1: Login")
        result = await tester.test_login()
        test_results.append(("Login", result))
        
        if not result:
            logger.error("❌ Login failed, cannot continue with other tests")
            return False
        
        # Test 2: Upload wordlist
        logger.info("\n📝 Test 2: Upload Wordlist")
        result = await tester.test_upload_wordlist()
        test_results.append(("Upload Wordlist", result))
        
        if not result:
            logger.error("❌ Wordlist upload failed, cannot continue with other tests")
            return False
        
        # Test 3: List wordlists
        logger.info("\n📝 Test 3: List Wordlists")
        result = await tester.test_list_wordlists()
        test_results.append(("List Wordlists", result))
        
        # Test 4: Get wordlist by ID
        logger.info("\n📝 Test 4: Get Wordlist by ID")
        result = await tester.test_get_wordlist_by_id()
        test_results.append(("Get Wordlist by ID", result))
        
        # Test 5: Download wordlist
        logger.info("\n📝 Test 5: Download Wordlist")
        result = await tester.test_download_wordlist()
        test_results.append(("Download Wordlist", result))
        
        # Test 6: Update wordlist
        logger.info("\n📝 Test 6: Update Wordlist")
        result = await tester.test_update_wordlist()
        test_results.append(("Update Wordlist", result))
        
        # Test 7: Verify wordlist update
        logger.info("\n📝 Test 7: Verify Wordlist Update")
        result = await tester.test_verify_wordlist_update()
        test_results.append(("Verify Wordlist Update", result))
        
        # Test 8: Search wordlists
        logger.info("\n📝 Test 8: Search Wordlists")
        result = await tester.test_search_wordlists()
        test_results.append(("Search Wordlists", result))
        
        # Test 9: Delete wordlist
        logger.info("\n📝 Test 9: Delete Wordlist")
        result = await tester.test_delete_wordlist()
        test_results.append(("Delete Wordlist", result))
        
        # Test 10: Verify wordlist deletion
        logger.info("\n📝 Test 10: Verify Wordlist Deletion")
        result = await tester.test_verify_wordlist_deletion()
        test_results.append(("Verify Wordlist Deletion", result))
        
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
            logger.info("🎉 All tests passed! Wordlist routes are working correctly.")
        else:
            logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
        
        return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_wordlist_tests())
    exit(0 if success else 1) 