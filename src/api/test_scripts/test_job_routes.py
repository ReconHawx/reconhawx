#!/usr/bin/env python3
"""
Job Routes Test Suite

This script tests the job-related endpoints in the jobs API:
- Create jobs
- Get job by ID
- Get all jobs
- Query jobs with filters
- Update job status
- Delete jobs
- Verify operations

Usage:
    python test_job_routes.py
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

class JobRouteTester:
    """Test class for job-related API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_manager: Optional[TestAuthManager] = None
        self.created_job_id: Optional[str] = None
        self.test_program: Optional[str] = None
        self.test_workflow_id = f"test-workflow-{uuid.uuid4().hex[:8]}"
        
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
    
    async def test_create_job(self) -> bool:
        """Test creating a job via POST /jobs"""
        logger.info(f"Testing job creation: {self.test_workflow_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            # Prepare job data
            job_data = {
                "workflow_id": self.test_workflow_id,
                "program_name": self.test_program,
                "status": "pending",
                "priority": "medium",
                "parameters": {
                    "target": "test.example.com",
                    "scan_type": "full"
                },
                "notes": "Test job for API testing"
            }
            
            response = await self.client.post(
                f"{self.base_url}/jobs",
                json=job_data,
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Job creation successful")
                logger.info(f"   Workflow ID: {data.get('workflow_id')}")
                logger.info(f"   Program: {data.get('program_name')}")
                logger.info(f"   Status: {data.get('status')}")
                
                # Store the job ID for later tests
                self.created_job_id = data.get('id') or data.get('_id')
                if self.created_job_id:
                    logger.info(f"   Job ID: {self.created_job_id}")
                else:
                    logger.warning("   ⚠️  No job ID found in response")
                
                return True
            else:
                logger.error(f"❌ Job creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Job creation test failed with exception: {str(e)}")
            return False
    
    async def test_get_job_by_id(self) -> bool:
        """Test getting a job by ID via GET /jobs/{job_id}"""
        logger.info(f"Testing get job by ID: {self.created_job_id}")
        
        if not self.created_job_id:
            logger.error("❌ No job ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/jobs/{self.created_job_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                job_data = data.get('data', {})
                logger.info("✅ Get job by ID successful")
                logger.info(f"   Workflow ID: {job_data.get('workflow_id')}")
                logger.info(f"   Program: {job_data.get('program_name')}")
                logger.info(f"   Status: {job_data.get('status')}")
                logger.info(f"   Priority: {job_data.get('priority')}")
                
                return True
            else:
                logger.error(f"❌ Get job by ID failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get job by ID test failed with exception: {str(e)}")
            return False
    
    async def test_get_all_jobs(self) -> bool:
        """Test getting all jobs via GET /jobs"""
        logger.info("Testing get all jobs")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/jobs",
                params={"limit": 100},
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                jobs = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Get all jobs successful")
                logger.info(f"   Total jobs: {pagination.get('total', 0)}")
                logger.info(f"   Current page: {pagination.get('page', 1)}")
                logger.info(f"   Page size: {pagination.get('limit', 100)}")
                logger.info(f"   Returned jobs: {len(jobs)}")
                
                return True
            else:
                logger.error(f"❌ Get all jobs failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get all jobs test failed with exception: {str(e)}")
            return False
    
    async def test_query_jobs_with_filters(self) -> bool:
        """Test querying jobs with filters via GET /jobs"""
        logger.info("Testing query jobs with filters")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/jobs",
                params={
                    "program_name": self.test_program,
                    "status": "pending",
                    "limit": 50
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                jobs = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Query jobs with filters successful")
                logger.info(f"   Program filter: {self.test_program}")
                logger.info(f"   Status filter: pending")
                logger.info(f"   Found jobs: {len(jobs)}")
                logger.info(f"   Total matching: {pagination.get('total', 0)}")
                
                return True
            else:
                logger.error(f"❌ Query jobs with filters failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Query jobs with filters test failed with exception: {str(e)}")
            return False
    
    async def test_update_job_status(self) -> bool:
        """Test updating job status via PATCH /jobs/{job_id}"""
        logger.info(f"Testing update job status: {self.created_job_id}")
        
        if not self.created_job_id:
            logger.error("❌ No job ID available")
            return False
        
        try:
            update_data = {
                "status": "running"
            }
            
            response = await self.client.patch(
                f"{self.base_url}/jobs/{self.created_job_id}",
                json=update_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update job status successful")
                logger.info(f"   New status: {data.get('status')}")
                return True
            else:
                logger.error(f"❌ Update job status failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update job status test failed with exception: {str(e)}")
            return False
    
    async def test_update_job_notes(self) -> bool:
        """Test updating job notes via PATCH /jobs/{job_id}"""
        logger.info(f"Testing update job notes: {self.created_job_id}")
        
        if not self.created_job_id:
            logger.error("❌ No job ID available")
            return False
        
        try:
            update_data = {
                "notes": "Updated test notes for job - API testing completed successfully!"
            }
            
            response = await self.client.patch(
                f"{self.base_url}/jobs/{self.created_job_id}",
                json=update_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update job notes successful")
                logger.info(f"   New notes: {data.get('notes')}")
                return True
            else:
                logger.error(f"❌ Update job notes failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update job notes test failed with exception: {str(e)}")
            return False
    
    async def test_verify_job_update(self) -> bool:
        """Test verifying that job updates were applied correctly"""
        logger.info(f"Testing verify job updates: {self.created_job_id}")
        
        if not self.created_job_id:
            logger.error("❌ No job ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/jobs/{self.created_job_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                job_data = data.get('data', {})
                
                logger.info("✅ Verify job updates successful")
                logger.info(f"   Status: {job_data.get('status')}")
                logger.info(f"   Notes: {job_data.get('notes')}")
                
                # Verify the updates were applied
                if job_data.get('status') == 'running' and 'API testing completed successfully' in job_data.get('notes', ''):
                    logger.info("✅ All updates verified successfully")
                    return True
                else:
                    logger.error("❌ Updates not properly applied")
                    return False
            else:
                logger.error(f"❌ Verify job updates failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify job updates test failed with exception: {str(e)}")
            return False
    
    async def test_delete_job(self) -> bool:
        """Test deleting job via DELETE /jobs/{job_id}"""
        logger.info(f"Testing delete job: {self.created_job_id}")
        
        if not self.created_job_id:
            logger.error("❌ No job ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/jobs/{self.created_job_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete job successful")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete job failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete job test failed with exception: {str(e)}")
            return False
    
    async def test_verify_job_deletion(self) -> bool:
        """Test verifying that job was properly deleted"""
        logger.info(f"Testing verify job deletion: {self.created_job_id}")
        
        if not self.created_job_id:
            logger.error("❌ No job ID available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/jobs/{self.created_job_id}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 404:
                logger.info("✅ Job properly deleted (404 Not Found)")
                return True
            elif response.status_code == 200:
                logger.error("❌ Job still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify job deletion test failed with exception: {str(e)}")
            return False

async def run_job_tests():
    """Run all job route tests"""
    logger.info("🚀 Starting Job Routes Test Suite")
    logger.info("=" * 60)
    
    # Create a test program with proper scope
    async with create_test_program(scope_pattern=".*example\\.com") as test_program_name:
        logger.info(f"📋 Using test program: {test_program_name}")
        
        async with JobRouteTester() as tester:
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
            
            # Test 2: Create job
            logger.info("\n📝 Test 2: Create Job")
            result = await tester.test_create_job()
            test_results.append(("Create Job", result))
            
            if not result:
                logger.error("❌ Job creation failed, cannot continue with other tests")
                return False
            
            # Test 3: Get job by ID
            logger.info("\n📝 Test 3: Get Job by ID")
            result = await tester.test_get_job_by_id()
            test_results.append(("Get Job by ID", result))
            
            # Test 4: Get all jobs
            logger.info("\n📝 Test 4: Get All Jobs")
            result = await tester.test_get_all_jobs()
            test_results.append(("Get All Jobs", result))
            
            # Test 5: Query jobs with filters
            logger.info("\n📝 Test 5: Query Jobs with Filters")
            result = await tester.test_query_jobs_with_filters()
            test_results.append(("Query Jobs with Filters", result))
            
            # Test 6: Update job status
            logger.info("\n📝 Test 6: Update Job Status")
            result = await tester.test_update_job_status()
            test_results.append(("Update Job Status", result))
            
            # Test 7: Update job notes
            logger.info("\n📝 Test 7: Update Job Notes")
            result = await tester.test_update_job_notes()
            test_results.append(("Update Job Notes", result))
            
            # Test 8: Verify job update
            logger.info("\n📝 Test 8: Verify Job Update")
            result = await tester.test_verify_job_update()
            test_results.append(("Verify Job Update", result))
            
            # Test 9: Delete job
            logger.info("\n📝 Test 9: Delete Job")
            result = await tester.test_delete_job()
            test_results.append(("Delete Job", result))
            
            # Test 10: Verify job deletion
            logger.info("\n📝 Test 10: Verify Job Deletion")
            result = await tester.test_verify_job_deletion()
            test_results.append(("Verify Job Deletion", result))
            
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
                logger.info("🎉 All tests passed! Job routes are working correctly.")
            else:
                logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
            
            return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_job_tests())
    exit(0 if success else 1) 