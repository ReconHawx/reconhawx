#!/usr/bin/env python3
"""
Nuclei Template Routes Test Suite

This script tests the nuclei template-related endpoints in the admin API:
- Upload nuclei templates
- Get nuclei templates
- Update nuclei templates
- Delete nuclei templates
- Verify operations

Usage:
    python test_nuclei_template_routes.py
"""

import asyncio
import httpx
import logging
import uuid
from typing import Optional
from pathlib import Path

# Import the common auth manager
from common_auth_manager import TestAuthManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NucleiTemplateRouteTester:
    """Test class for nuclei template-related API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_manager: Optional[TestAuthManager] = None
        self.created_template_id: Optional[str] = None
        self.test_template_content = f"""id: test-template-{uuid.uuid4().hex[:8]}
info:
  name: Test Nuclei Template
  author: test-author
  severity: medium
  description: Test template for API testing
  tags: test,api,vulnerability
requests:
  - method: GET
    path:
      - "{{{{BaseURL}}}}/test"
    matchers:
      - type: word
        words:
          - "test response"
"""
        
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
                if self.auth_manager.auth_token:
                    logger.info(f"   Token: {self.auth_manager.auth_token[:20]}...")
                return True
            else:
                logger.error("❌ Login failed using TestAuthManager")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login test failed with exception: {str(e)}")
            return False
    
    async def test_upload_nuclei_template(self) -> bool:
        """Test uploading a nuclei template"""
        logger.info("Testing nuclei template upload")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            # Create a temporary template file
            template_file = Path("test_template.yaml")
            template_file.write_text(self.test_template_content)
            
            # Prepare form data for upload
            files = {
                'file': ('test_template.yaml', template_file.read_bytes(), 'text/yaml')
            }
            
            response = await self.client.post(
                f"{self.base_url}/admin/nuclei-templates",
                files=files,
                headers=self.auth_manager.get_auth_headers()
            )
            
            # Clean up temporary file
            template_file.unlink()
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Nuclei template upload successful")
                logger.info(f"   Template ID: {data.get('template_id')}")
                logger.info(f"   Name: {data.get('name')}")
                logger.info(f"   Author: {data.get('author')}")
                
                # Store the template ID for later tests
                self.created_template_id = data.get('template_id')
                if self.created_template_id:
                    logger.info(f"   Stored template ID: {self.created_template_id}")
                
                return True
            else:
                logger.error(f"❌ Nuclei template upload failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Nuclei template upload test failed with exception: {str(e)}")
            return False
    
    async def test_get_nuclei_template_by_id(self) -> bool:
        """Test getting a nuclei template by ID"""
        logger.info(f"Testing get nuclei template by ID: {self.created_template_id}")
        
        if not self.created_template_id:
            logger.error("❌ No template ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/admin/nuclei-templates/{self.created_template_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                template_data = data.get('data', {})
                logger.info("✅ Get nuclei template by ID successful")
                logger.info(f"   Template ID: {template_data.get('template_id')}")
                logger.info(f"   Name: {template_data.get('name')}")
                logger.info(f"   Author: {template_data.get('author')}")
                logger.info(f"   Severity: {template_data.get('severity')}")
                
                return True
            else:
                logger.error(f"❌ Get nuclei template by ID failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get nuclei template by ID test failed with exception: {str(e)}")
            return False
    
    async def test_get_all_nuclei_templates(self) -> bool:
        """Test getting all nuclei templates"""
        logger.info("Testing get all nuclei templates")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/admin/nuclei-templates",
                params={"limit": 100},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                templates = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Get all nuclei templates successful")
                logger.info(f"   Total templates: {pagination.get('total', 0)}")
                logger.info(f"   Current page: {pagination.get('page', 1)}")
                logger.info(f"   Page size: {pagination.get('limit', 100)}")
                logger.info(f"   Returned templates: {len(templates)}")
                
                return True
            else:
                logger.error(f"❌ Get all nuclei templates failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get all nuclei templates test failed with exception: {str(e)}")
            return False
    
    async def test_query_nuclei_templates(self) -> bool:
        """Test querying nuclei templates with filters"""
        logger.info("Testing query nuclei templates with filters")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/admin/nuclei-templates",
                params={
                    "severity": "medium",
                    "author": "test-author",
                    "limit": 50
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                templates = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Query nuclei templates successful")
                logger.info(f"   Severity filter: medium")
                logger.info(f"   Author filter: test-author")
                logger.info(f"   Found templates: {len(templates)}")
                logger.info(f"   Total matching: {pagination.get('total', 0)}")
                
                return True
            else:
                logger.error(f"❌ Query nuclei templates failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Query nuclei templates test failed with exception: {str(e)}")
            return False
    
    async def test_update_nuclei_template(self) -> bool:
        """Test updating a nuclei template"""
        logger.info(f"Testing update nuclei template: {self.created_template_id}")
        
        if not self.created_template_id:
            logger.error("❌ No template ID available")
            return False
        
        try:
            update_data = {
                "description": "Updated test template description - API testing completed successfully!"
            }
            
            response = await self.client.patch(
                f"{self.base_url}/admin/nuclei-templates/{self.created_template_id}",
                json=update_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update nuclei template successful")
                logger.info(f"   New description: {data.get('description')}")
                return True
            else:
                logger.error(f"❌ Update nuclei template failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update nuclei template test failed with exception: {str(e)}")
            return False
    
    async def test_verify_nuclei_template_update(self) -> bool:
        """Test verifying that nuclei template update was applied correctly"""
        logger.info(f"Testing verify nuclei template update: {self.created_template_id}")
        
        if not self.created_template_id:
            logger.error("❌ No template ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/admin/nuclei-templates/{self.created_template_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                template_data = data.get('data', {})
                
                logger.info("✅ Verify nuclei template update successful")
                logger.info(f"   Template ID: {template_data.get('template_id')}")
                logger.info(f"   Description: {template_data.get('description')}")
                
                # Verify the update was applied
                if 'API testing completed successfully' in template_data.get('description', ''):
                    logger.info("✅ Description update verified successfully")
                    return True
                else:
                    logger.error("❌ Description update not properly applied")
                    return False
            else:
                logger.error(f"❌ Verify nuclei template update failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify nuclei template update test failed with exception: {str(e)}")
            return False
    
    async def test_delete_nuclei_template(self) -> bool:
        """Test deleting a nuclei template"""
        logger.info(f"Testing delete nuclei template: {self.created_template_id}")
        
        if not self.created_template_id:
            logger.error("❌ No template ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/admin/nuclei-templates/{self.created_template_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete nuclei template successful")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete nuclei template failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete nuclei template test failed with exception: {str(e)}")
            return False
    
    async def test_verify_nuclei_template_deletion(self) -> bool:
        """Test verifying that nuclei template was properly deleted"""
        logger.info(f"Testing verify nuclei template deletion: {self.created_template_id}")
        
        if not self.created_template_id:
            logger.error("❌ No template ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/admin/nuclei-templates/{self.created_template_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 404:
                logger.info("✅ Nuclei template properly deleted (404 Not Found)")
                return True
            elif response.status_code == 200:
                logger.error("❌ Nuclei template still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify nuclei template deletion test failed with exception: {str(e)}")
            return False

async def run_nuclei_template_tests():
    """Run all nuclei template route tests"""
    logger.info("🚀 Starting Nuclei Template Routes Test Suite")
    logger.info("=" * 60)
    
    async with NucleiTemplateRouteTester() as tester:
        test_results = []
        
        # Test 1: Login (needed for authenticated endpoints)
        logger.info("\n📝 Test 1: Login")
        result = await tester.test_login()
        test_results.append(("Login", result))
        
        if not result:
            logger.error("❌ Login failed, cannot continue with other tests")
            return False
        
        # Test 2: Upload nuclei template
        logger.info("\n📝 Test 2: Upload Nuclei Template")
        result = await tester.test_upload_nuclei_template()
        test_results.append(("Upload Nuclei Template", result))
        
        if not result:
            logger.error("❌ Nuclei template upload failed, cannot continue with other tests")
            return False
        
        # Test 3: Get nuclei template by ID
        logger.info("\n📝 Test 3: Get Nuclei Template by ID")
        result = await tester.test_get_nuclei_template_by_id()
        test_results.append(("Get Nuclei Template by ID", result))
        
        # Test 4: Get all nuclei templates
        logger.info("\n📝 Test 4: Get All Nuclei Templates")
        result = await tester.test_get_all_nuclei_templates()
        test_results.append(("Get All Nuclei Templates", result))
        
        # Test 5: Query nuclei templates
        logger.info("\n📝 Test 5: Query Nuclei Templates")
        result = await tester.test_query_nuclei_templates()
        test_results.append(("Query Nuclei Templates", result))
        
        # Test 6: Update nuclei template
        logger.info("\n📝 Test 6: Update Nuclei Template")
        result = await tester.test_update_nuclei_template()
        test_results.append(("Update Nuclei Template", result))
        
        # Test 7: Verify nuclei template update
        logger.info("\n📝 Test 7: Verify Nuclei Template Update")
        result = await tester.test_verify_nuclei_template_update()
        test_results.append(("Verify Nuclei Template Update", result))
        
        # Test 8: Delete nuclei template
        logger.info("\n📝 Test 8: Delete Nuclei Template")
        result = await tester.test_delete_nuclei_template()
        test_results.append(("Delete Nuclei Template", result))
        
        # Test 9: Verify nuclei template deletion
        logger.info("\n📝 Test 9: Verify Nuclei Template Deletion")
        result = await tester.test_verify_nuclei_template_deletion()
        test_results.append(("Verify Nuclei Template Deletion", result))
        
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
            logger.info("🎉 All tests passed! Nuclei template routes are working correctly.")
        else:
            logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
        
        return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_nuclei_template_tests())
    exit(0 if success else 1) 