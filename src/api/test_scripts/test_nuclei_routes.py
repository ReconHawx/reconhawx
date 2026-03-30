#!/usr/bin/env python3
"""
Nuclei Findings Routes Test Suite

This script tests the nuclei findings-related endpoints in the findings API:
- Create nuclei findings
- Get nuclei finding by ID
- Get all nuclei findings
- Query nuclei findings with filters
- Get nuclei stats
- Get distinct field values
- Update nuclei status and notes
- Delete nuclei findings
- Verify operations

Usage:
    python test_nuclei_routes.py
"""

import asyncio
import httpx
import logging
import uuid
from typing import Optional
from datetime import datetime, timezone

# Import the common program manager and auth manager
from common_program_manager import create_test_program
from common_auth_manager import TestAuthManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NucleiRouteTester:
    """Test class for nuclei findings-related API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_manager: Optional[TestAuthManager] = None
        self.created_finding_id: Optional[str] = None
        self.test_program: Optional[str] = None
        self.test_url = f"https://test-{uuid.uuid4().hex[:8]}.example.com"
        self.test_template_id = f"test-template-{uuid.uuid4().hex[:8]}"
        
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
    
    async def test_create_nuclei_finding(self) -> bool:
        """Test creating a nuclei finding via POST /findings/nuclei"""
        logger.info(f"Testing nuclei finding creation: {self.test_url}")
        
        try:
            # Prepare nuclei finding data
            finding_data = {
                "url": self.test_url,
                "template_id": self.test_template_id,
                "template_url": "https://github.com/projectdiscovery/nuclei-templates",
                "name": "Test Nuclei Finding",
                "severity": "medium",
                "type": "http",
                "tags": ["test", "api", "vulnerability"],
                "description": "Test nuclei finding for API testing",
                "matched_at": datetime.now(timezone.utc).isoformat(),
                "matcher_name": "test-matcher",
                "ip": "192.168.1.100",
                "port": 443,
                "matched_line": "Test matched line content",
                "program_name": self.test_program,
                "hostname": "test.example.com",
                "scheme": "https",
                "protocol": "tcp",
                "extracted_results": ["result1", "result2"],
                "info": {
                    "test_key": "test_value",
                    "nested": {"key": "value"}
                },
                "notes": "Test notes for nuclei finding"
            }
            
            response = await self.client.post(
                f"{self.base_url}/findings/nuclei",
                json=finding_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Nuclei finding creation successful")
                logger.info(f"   URL: {data.get('url')}")
                logger.info(f"   Template ID: {data.get('template_id')}")
                logger.info(f"   Severity: {data.get('severity')}")
                logger.info(f"   Name: {data.get('name')}")
                
                # Store the finding ID for later tests
                self.created_finding_id = data.get('id') or data.get('_id')
                if self.created_finding_id:
                    logger.info(f"   Finding ID: {self.created_finding_id}")
                else:
                    logger.warning("   ⚠️  No finding ID found in response")
                    logger.debug(f"   Response structure: {data}")
                
                return True
            else:
                logger.error(f"❌ Nuclei finding creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Nuclei finding creation test failed with exception: {str(e)}")
            return False
    
    async def test_get_nuclei_finding_by_id(self) -> bool:
        """Test getting a nuclei finding by ID via GET /findings/nuclei/{finding_id}"""
        logger.info(f"Testing get nuclei finding by ID: {self.created_finding_id}")
        
        if not self.created_finding_id:
            logger.error("❌ No finding ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei/{self.created_finding_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                finding_data = data.get('data', {})
                logger.info("✅ Get nuclei finding by ID successful")
                logger.info(f"   URL: {finding_data.get('url')}")
                logger.info(f"   Template ID: {finding_data.get('template_id')}")
                logger.info(f"   Severity: {finding_data.get('severity')}")
                logger.info(f"   Name: {finding_data.get('name')}")
                logger.info(f"   Type: {finding_data.get('type')}")
                logger.info(f"   Program: {finding_data.get('program_name')}")
                
                return True
            else:
                logger.error(f"❌ Get nuclei finding by ID failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get nuclei finding by ID test failed with exception: {str(e)}")
            return False
    
    async def test_get_all_nuclei_findings(self) -> bool:
        """Test getting all nuclei findings via GET /findings/nuclei"""
        logger.info("Testing get all nuclei findings")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei",
                params={"limit": 100},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                findings = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Get all nuclei findings successful")
                logger.info(f"   Total findings: {pagination.get('total', 0)}")
                logger.info(f"   Current page: {pagination.get('page', 1)}")
                logger.info(f"   Page size: {pagination.get('limit', 100)}")
                logger.info(f"   Returned findings: {len(findings)}")
                
                return True
            else:
                logger.error(f"❌ Get all nuclei findings failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get all nuclei findings test failed with exception: {str(e)}")
            return False
    
    async def test_query_nuclei_findings(self) -> bool:
        """Test querying nuclei findings with filters via GET /findings/nuclei"""
        logger.info("Testing query nuclei findings with filters")
        
        try:
            # Query with program filter
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei",
                params={
                    "program_name": self.test_program,
                    "limit": 50
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                findings = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Query nuclei findings successful")
                logger.info(f"   Program filter: {self.test_program}")
                logger.info(f"   Found findings: {len(findings)}")
                logger.info(f"   Total in program: {pagination.get('total', 0)}")
                
                return True
            else:
                logger.error(f"❌ Query nuclei findings failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Query nuclei findings test failed with exception: {str(e)}")
            return False
    
    async def test_get_nuclei_stats(self) -> bool:
        """Test getting nuclei findings statistics via GET /findings/nuclei/stats"""
        logger.info("Testing get nuclei findings statistics")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei/stats",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                stats = data.get('stats', {})
                
                logger.info("✅ Get nuclei stats successful")
                logger.info(f"   Total findings: {stats.get('total', 0)}")
                logger.info(f"   By severity: {stats.get('by_severity', {})}")
                logger.info(f"   By type: {stats.get('by_type', {})}")
                
                return True
            else:
                logger.error(f"❌ Get nuclei stats failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get nuclei stats test failed with exception: {str(e)}")
            return False
    
    async def test_get_program_nuclei_stats(self) -> bool:
        """Test getting program-specific nuclei findings statistics"""
        logger.info("Testing get program-specific nuclei findings statistics")
        
        if not self.test_program:
            logger.error("❌ No test program available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei/stats",
                params={"program_name": self.test_program},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                stats = data.get('stats', {})
                
                logger.info("✅ Get program nuclei stats successful")
                logger.info(f"   Program: {self.test_program}")
                logger.info(f"   Total findings: {stats.get('total', 0)}")
                logger.info(f"   By severity: {stats.get('by_severity', {})}")
                
                return True
            else:
                logger.error(f"❌ Get program nuclei stats failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get program nuclei stats test failed with exception: {str(e)}")
            return False
    
    async def test_get_distinct_nuclei_values(self) -> bool:
        """Test getting distinct field values for nuclei findings"""
        logger.info("Testing get distinct nuclei field values")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei/distinct",
                params={"field": "severity"},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                values = data.get('values', [])
                
                logger.info("✅ Get distinct nuclei values successful")
                logger.info(f"   Field: severity")
                logger.info(f"   Distinct values: {values}")
                
                return True
            else:
                logger.error(f"❌ Get distinct nuclei values failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get distinct nuclei values test failed with exception: {str(e)}")
            return False
    
    async def test_update_nuclei_status(self) -> bool:
        """Test updating nuclei finding status via PATCH /findings/nuclei/{finding_id}"""
        logger.info(f"Testing update nuclei finding status: {self.created_finding_id}")
        
        if not self.created_finding_id:
            logger.error("❌ No finding ID available")
            return False
        
        try:
            update_data = {
                "status": "false_positive"
            }
            
            response = await self.client.patch(
                f"{self.base_url}/findings/nuclei/{self.created_finding_id}",
                json=update_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update nuclei finding status successful")
                logger.info(f"   New status: {data.get('status')}")
                return True
            else:
                logger.error(f"❌ Update nuclei finding status failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update nuclei finding status test failed with exception: {str(e)}")
            return False
    
    async def test_update_nuclei_notes(self) -> bool:
        """Test updating nuclei finding notes via PATCH /findings/nuclei/{finding_id}"""
        logger.info(f"Testing update nuclei finding notes: {self.created_finding_id}")
        
        if not self.created_finding_id:
            logger.error("❌ No finding ID available")
            return False
        
        try:
            update_data = {
                "notes": "Updated test notes for nuclei finding"
            }
            
            response = await self.client.patch(
                f"{self.base_url}/findings/nuclei/{self.created_finding_id}",
                json=update_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update nuclei finding notes successful")
                logger.info(f"   New notes: {data.get('notes')}")
                return True
            else:
                logger.error(f"❌ Update nuclei finding notes failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update nuclei finding notes test failed with exception: {str(e)}")
            return False
    
    async def test_verify_nuclei_update(self) -> bool:
        """Test verifying that nuclei finding updates were applied correctly"""
        logger.info(f"Testing verify nuclei finding updates: {self.created_finding_id}")
        
        if not self.created_finding_id:
            logger.error("❌ No finding ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei/{self.created_finding_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                finding_data = data.get('data', {})
                
                logger.info("✅ Verify nuclei finding updates successful")
                logger.info(f"   Status: {finding_data.get('status')}")
                logger.info(f"   Notes: {finding_data.get('notes')}")
                
                # Verify the updates were applied
                if finding_data.get('status') == 'false_positive' and 'Updated test notes' in finding_data.get('notes', ''):
                    logger.info("✅ All updates verified successfully")
                    return True
                else:
                    logger.error("❌ Updates not properly applied")
                    return False
            else:
                logger.error(f"❌ Verify nuclei finding updates failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify nuclei finding updates test failed with exception: {str(e)}")
            return False
    
    async def test_delete_nuclei_finding(self) -> bool:
        """Test deleting nuclei finding via DELETE /findings/nuclei/{finding_id}"""
        logger.info(f"Testing delete nuclei finding: {self.created_finding_id}")
        
        if not self.created_finding_id:
            logger.error("❌ No finding ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/findings/nuclei/{self.created_finding_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete nuclei finding successful")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete nuclei finding failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete nuclei finding test failed with exception: {str(e)}")
            return False
    
    async def test_verify_nuclei_deletion(self) -> bool:
        """Test verifying that nuclei finding was properly deleted"""
        logger.info(f"Testing verify nuclei finding deletion: {self.created_finding_id}")
        
        if not self.created_finding_id:
            logger.error("❌ No finding ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/findings/nuclei/{self.created_finding_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 404:
                logger.info("✅ Nuclei finding properly deleted (404 Not Found)")
                return True
            elif response.status_code == 200:
                logger.error("❌ Nuclei finding still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify nuclei finding deletion test failed with exception: {str(e)}")
            return False

async def run_nuclei_tests():
    """Run all nuclei findings route tests"""
    logger.info("🚀 Starting Nuclei Findings Routes Test Suite")
    logger.info("=" * 60)
    
    # Create a test program with proper scope
    async with create_test_program(scope_pattern=".*example\\.com") as test_program_name:
        logger.info(f"📋 Using test program: {test_program_name}")
        
        async with NucleiRouteTester() as tester:
            # Set the test program name
            tester.test_program = test_program_name
            
            test_results = []
            
            # Test 1: Login (needed for some endpoints)
            logger.info("\n📝 Test 1: Login")
            result = await tester.test_login()
            test_results.append(("Login", result))
            
            if not result:
                logger.error("❌ Login failed, cannot continue with other tests")
                return False
            
            # Test 2: Create nuclei finding
            logger.info("\n📝 Test 2: Create Nuclei Finding")
            result = await tester.test_create_nuclei_finding()
            test_results.append(("Create Nuclei Finding", result))
            
            if not result:
                logger.error("❌ Nuclei finding creation failed, cannot continue with other tests")
                return False
            
            # Test 3: Get nuclei finding by ID
            logger.info("\n📝 Test 3: Get Nuclei Finding by ID")
            result = await tester.test_get_nuclei_finding_by_id()
            test_results.append(("Get Nuclei Finding by ID", result))
            
            # Test 4: Get all nuclei findings
            logger.info("\n📝 Test 4: Get All Nuclei Findings")
            result = await tester.test_get_all_nuclei_findings()
            test_results.append(("Get All Nuclei Findings", result))
            
            # Test 5: Query nuclei findings
            logger.info("\n📝 Test 5: Query Nuclei Findings")
            result = await tester.test_query_nuclei_findings()
            test_results.append(("Query Nuclei Findings", result))
            
            # Test 6: Get nuclei stats
            logger.info("\n📝 Test 6: Get Nuclei Stats")
            result = await tester.test_get_nuclei_stats()
            test_results.append(("Get Nuclei Stats", result))
            
            # Test 7: Get program nuclei stats
            logger.info("\n📝 Test 7: Get Program Nuclei Stats")
            result = await tester.test_get_program_nuclei_stats()
            test_results.append(("Get Program Nuclei Stats", result))
            
            # Test 8: Get distinct nuclei field values
            logger.info("\n📝 Test 8: Get Distinct Nuclei Field Values")
            result = await tester.test_get_distinct_nuclei_values()
            test_results.append(("Get Distinct Nuclei Field Values", result))
            
            # Test 9: Update nuclei finding status
            logger.info("\n📝 Test 9: Update Nuclei Finding Status")
            result = await tester.test_update_nuclei_status()
            test_results.append(("Update Nuclei Finding Status", result))
            
            # Test 10: Update nuclei finding notes
            logger.info("\n📝 Test 10: Update Nuclei Finding Notes")
            result = await tester.test_update_nuclei_notes()
            test_results.append(("Update Nuclei Finding Notes", result))
            
            # Test 11: Verify nuclei finding update
            logger.info("\n📝 Test 11: Verify Nuclei Finding Update")
            result = await tester.test_verify_nuclei_update()
            test_results.append(("Verify Nuclei Finding Update", result))
            
            # Test 12: Delete nuclei finding
            logger.info("\n📝 Test 12: Delete Nuclei Finding")
            result = await tester.test_delete_nuclei_finding()
            test_results.append(("Delete Nuclei Finding", result))
            
            # Test 13: Verify nuclei finding deletion
            logger.info("\n📝 Test 13: Verify Nuclei Finding Deletion")
            result = await tester.test_verify_nuclei_deletion()
            test_results.append(("Verify Nuclei Finding Deletion", result))
            
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
                logger.info("🎉 All tests passed! Nuclei findings routes are working correctly.")
            else:
                logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
            
            return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_nuclei_tests())
    exit(0 if success else 1) 