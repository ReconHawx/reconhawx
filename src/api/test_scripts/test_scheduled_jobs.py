#!/usr/bin/env python3
"""
Scheduled Jobs API Test Suite - Dummy Batch Focus

This script tests the scheduled jobs API endpoints specifically for dummy batch jobs.
It uses the common auth manager for authentication.

Usage:
    python test_scheduled_jobs.py
"""

import asyncio
import httpx
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

# Import the common managers
from common_auth_manager import create_auth_session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ScheduledJobsTester:
    """Test class for scheduled jobs API endpoints - Dummy Batch Focus"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.created_jobs: List[str] = []
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def _resolve_test_program_name(self, auth_headers: dict) -> Optional[str]:
        """Pick a program the test user can schedule jobs for (prefers manager)."""
        try:
            response = await self.client.get(f"{self.base_url}/programs", headers=auth_headers)
            if response.status_code != 200:
                return None
            data = response.json()
            programs = data.get("programs_with_permissions") or []
            for p in programs:
                if p.get("permission_level") == "manager" or p.get("permission") == "manager":
                    return p.get("name")
            if programs:
                return programs[0].get("name")
        except Exception:
            pass
        return None

    async def test_create_one_time_dummy_job(self, auth_headers: dict) -> bool:
        """Test creating a one-time dummy batch job"""
        logger.info("Testing create one-time dummy batch job")
        
        try:
            program_name = await self._resolve_test_program_name(auth_headers)
            if not program_name:
                logger.error("❌ No accessible program for scheduled job test")
                return False
            job_data = {
                "job_type": "dummy_batch",
                "job_data": {
                    "items": ["item1", "item2", "item3", "item4", "item5"]
                },
                "schedule": {
                    "schedule_type": "once",
                    "start_time": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
                },
                "name": f"Test Dummy Job {uuid.uuid4().hex[:8]}",
                "description": "A test dummy batch job created via API",
                "tags": ["test", "dummy", "batch"],
                "program_name": program_name,
            }
            
            response = await self.client.post(
                f"{self.base_url}/scheduled-jobs",
                headers=auth_headers,
                json=job_data
            )
            
            if response.status_code == 200:
                data = response.json()
                schedule_id = data.get('schedule_id')
                logger.info("✅ Create one-time dummy job successful")
                logger.info(f"   Schedule ID: {schedule_id}")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Next Run: {data.get('next_run')}")
                pids = data.get("program_ids") or []
                if not pids:
                    logger.error("❌ Response missing program_ids")
                    return False
                
                if schedule_id:
                    self.created_jobs.append(schedule_id)
                
                return True
            else:
                logger.error(f"❌ Create one-time dummy job failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Create one-time dummy job test failed with exception: {str(e)}")
            return False
    
    async def test_create_recurring_dummy_job(self, auth_headers: dict) -> bool:
        """Test creating a recurring dummy batch job"""
        logger.info("Testing create recurring dummy batch job")
        
        try:
            program_name = await self._resolve_test_program_name(auth_headers)
            if not program_name:
                logger.error("❌ No accessible program for scheduled job test")
                return False
            job_data = {
                "job_type": "dummy_batch",
                "job_data": {
                    "items": ["recurring-item1", "recurring-item2", "recurring-item3"]
                },
                "schedule": {
                    "schedule_type": "recurring",
                    "start_time": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
                    "recurring_schedule": {
                        "interval_hours": 2,
                        "max_executions": 3,
                        "end_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
                    }
                },
                "name": f"Test Recurring Dummy Job {uuid.uuid4().hex[:8]}",
                "description": "A test recurring dummy batch job created via API",
                "tags": ["test", "recurring", "dummy"],
                "program_name": program_name,
            }
            
            response = await self.client.post(
                f"{self.base_url}/scheduled-jobs",
                headers=auth_headers,
                json=job_data
            )
            
            if response.status_code == 200:
                data = response.json()
                schedule_id = data.get('schedule_id')
                logger.info("✅ Create recurring dummy job successful")
                logger.info(f"   Schedule ID: {schedule_id}")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Next Run: {data.get('next_run')}")
                
                if schedule_id:
                    self.created_jobs.append(schedule_id)
                
                return True
            else:
                logger.error(f"❌ Create recurring dummy job failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Create recurring dummy job test failed with exception: {str(e)}")
            return False
    
    async def test_list_scheduled_jobs(self, auth_headers: dict) -> bool:
        """Test listing all scheduled jobs"""
        logger.info("Testing list scheduled jobs")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/scheduled-jobs",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                data = response.json()
                jobs = data if isinstance(data, list) else data.get('items', [])
                logger.info("✅ List scheduled jobs successful")
                logger.info(f"   Found {len(jobs)} scheduled jobs")
                
                for job in jobs[:5]:  # Show first 5 jobs
                    logger.info(f"     - {job.get('name')} ({job.get('schedule_id')}) - {job.get('status')}")
                
                return True
            else:
                logger.error(f"❌ List scheduled jobs failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ List scheduled jobs test failed with exception: {str(e)}")
            return False
    
    async def test_get_job_details(self, auth_headers: dict, schedule_id: str) -> bool:
        """Test getting details of a specific scheduled job"""
        logger.info(f"Testing get job details: {schedule_id}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/scheduled-jobs/{schedule_id}",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Get job details successful")
                logger.info(f"   Name: {data.get('name')}")
                logger.info(f"   Type: {data.get('job_type')}")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Next Run: {data.get('next_run')}")
                logger.info(f"   Total Executions: {data.get('total_executions')}")
                return True
            else:
                logger.error(f"❌ Get job details failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get job details test failed with exception: {str(e)}")
            return False
    
    async def test_update_job(self, auth_headers: dict, schedule_id: str) -> bool:
        """Test updating a scheduled job"""
        logger.info(f"Testing update job: {schedule_id}")
        
        try:
            update_data = {
                "name": f"Updated Dummy Job {uuid.uuid4().hex[:8]}",
                "description": "This dummy job was updated via API testing",
                "tags": ["test", "updated", "dummy", "api-testing"]
            }
            
            response = await self.client.put(
                f"{self.base_url}/scheduled-jobs/{schedule_id}",
                headers=auth_headers,
                json=update_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update job successful")
                logger.info(f"   New Name: {data.get('name')}")
                logger.info(f"   New Description: {data.get('description')}")
                logger.info(f"   New Tags: {data.get('tags')}")
                return True
            else:
                logger.error(f"❌ Update job failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update job test failed with exception: {str(e)}")
            return False
    
    async def test_enable_disable_job(self, auth_headers: dict, schedule_id: str) -> bool:
        """Test enabling and disabling a scheduled job"""
        logger.info(f"Testing enable/disable job: {schedule_id}")
        
        try:
            # Test disable
            response = await self.client.post(
                f"{self.base_url}/scheduled-jobs/{schedule_id}/disable",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                logger.info("✅ Disable job successful")
            else:
                logger.error(f"❌ Disable job failed with status {response.status_code}")
                return False
            
            # Test enable
            response = await self.client.post(
                f"{self.base_url}/scheduled-jobs/{schedule_id}/enable",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                logger.info("✅ Enable job successful")
                return True
            else:
                logger.error(f"❌ Enable job failed with status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Enable/disable job test failed with exception: {str(e)}")
            return False
    
    async def test_run_job_now(self, auth_headers: dict, schedule_id: str) -> bool:
        """Test running a job immediately"""
        logger.info(f"Testing run job now: {schedule_id}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/scheduled-jobs/{schedule_id}/run-now",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Run job now successful")
                logger.info(f"   Message: {data.get('message')}")
                logger.info(f"   Triggered At: {data.get('triggered_at')}")
                return True
            else:
                logger.error(f"❌ Run job now failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Run job now test failed with exception: {str(e)}")
            return False
    
    async def test_get_execution_history(self, auth_headers: dict, schedule_id: str) -> bool:
        """Test getting execution history for a scheduled job"""
        logger.info(f"Testing get execution history: {schedule_id}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/scheduled-jobs/{schedule_id}/executions",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                data = response.json()
                executions = data if isinstance(data, list) else data.get('items', [])
                logger.info("✅ Get execution history successful")
                logger.info(f"   Found {len(executions)} execution records")
                
                for execution in executions[:3]:  # Show first 3 executions
                    logger.info(f"     - {execution.get('execution_id')} - {execution.get('status')} - {execution.get('started_at')}")
                
                return True
            else:
                logger.error(f"❌ Get execution history failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get execution history test failed with exception: {str(e)}")
            return False
    
    async def test_delete_job(self, auth_headers: dict, schedule_id: str) -> bool:
        """Test deleting a scheduled job"""
        logger.info(f"Testing delete job: {schedule_id}")
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/scheduled-jobs/{schedule_id}",
                headers=auth_headers
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

async def run_dummy_batch_tests():
    """Run dummy batch focused scheduled jobs tests"""
    logger.info("🚀 Starting Dummy Batch Scheduled Jobs API Test Suite")
    logger.info("=" * 60)
    
    # Create authenticated session
    async with create_auth_session() as auth_manager:
        logger.info("🔐 Using authenticated session")
        
        async with ScheduledJobsTester() as tester:
            # Get auth headers for authenticated requests
            auth_headers = auth_manager.get_auth_headers()
            
            test_results = []
            
            # Test 1: Create one-time dummy job
            logger.info("\n📝 Test 1: Create One-Time Dummy Job")
            result = await tester.test_create_one_time_dummy_job(auth_headers)
            test_results.append(("Create One-Time Dummy Job", result))
            
            # Test 2: Create recurring dummy job
            logger.info("\n📝 Test 2: Create Recurring Dummy Job")
            result = await tester.test_create_recurring_dummy_job(auth_headers)
            test_results.append(("Create Recurring Dummy Job", result))
            
            # Test 3: List scheduled jobs
            logger.info("\n📝 Test 3: List Scheduled Jobs")
            result = await tester.test_list_scheduled_jobs(auth_headers)
            test_results.append(("List Scheduled Jobs", result))
            
            # Test individual job operations if we have created jobs
            if tester.created_jobs:
                test_job_id = tester.created_jobs[0]
                
                # Test 4: Get job details
                logger.info("\n📝 Test 4: Get Job Details")
                result = await tester.test_get_job_details(auth_headers, test_job_id)
                test_results.append(("Get Job Details", result))
                
                # Test 5: Update job
                logger.info("\n📝 Test 5: Update Job")
                result = await tester.test_update_job(auth_headers, test_job_id)
                test_results.append(("Update Job", result))
                
                # Test 6: Enable/disable job
                logger.info("\n📝 Test 6: Enable/Disable Job")
                result = await tester.test_enable_disable_job(auth_headers, test_job_id)
                test_results.append(("Enable/Disable Job", result))
                
                # Test 7: Run job now
                logger.info("\n📝 Test 7: Run Job Now")
                result = await tester.test_run_job_now(auth_headers, test_job_id)
                test_results.append(("Run Job Now", result))
                
                # Wait a bit for execution to start
                logger.info("\n⏳ Waiting 3 seconds for job execution to start...")
                await asyncio.sleep(3)
                
                # Test 8: Get execution history
                logger.info("\n📝 Test 8: Get Execution History")
                result = await tester.test_get_execution_history(auth_headers, test_job_id)
                test_results.append(("Get Execution History", result))
                
                # Test 9: Delete job
                # logger.info(f"\n📝 Test 9: Delete Job")
                # result = await tester.test_delete_job(auth_headers, test_job_id)
                # test_results.append(("Delete Job", result))
            else:
                logger.warning("⚠️  No jobs were created, skipping individual job tests")
            
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
            
            logger.info("")
            logger.info(f"🎯 Overall Result: {passed}/{total} tests passed")
            
            if passed == total:
                logger.info("🎉 All tests passed! Dummy batch scheduled jobs API is working correctly.")
                return True
            else:
                logger.error(f"💥 {total - passed} test(s) failed. Check the logs above for details.")
                return False

if __name__ == "__main__":
    asyncio.run(run_dummy_batch_tests()) 