#!/usr/bin/env python3
"""
Service Routes Test Suite

This script tests the service-related endpoints in the assets API:
- Create services via receive_asset endpoint
- Get service by IP and port
- Get services by program
- Query services with filters
- Update service notes
- Delete services
- Verify operations

Usage:
    python test_service_routes.py
"""

import asyncio
import httpx
import logging
from typing import Optional

# Import the common program manager
from common_auth_manager import TestAuthManager
from common_program_manager import create_test_program

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ServiceRouteTester:
    """Test class for service-related API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_manager: Optional[TestAuthManager] = None
        self.created_service_id: Optional[str] = None
        self.test_program: Optional[str] = None
        self.test_ip = "192.168.1.100"
        self.test_port = 8080
        
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
    
    async def test_create_service(self) -> bool:
        """Test creating a service via POST /assets (receive_asset endpoint)"""
        logger.info(f"Testing service creation: {self.test_ip}:{self.test_port}")
        
        try:
            # Prepare asset data for the receive_asset endpoint
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "service": [
                        {
                            "ip": self.test_ip,
                            "port": self.test_port,
                            "service": "http",
                            "protocol": "tcp",
                            "banner": "HTTP/1.1 200 OK\r\nServer: nginx/1.18.0\r\n",
                            "product": "nginx",
                            "version": "1.18.0",
                            "notes": "Test service for API testing"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Service creation successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                
                # Check if there were any errors in the response
                if data.get('status') == 'error' or 'error' in data.get('message', '').lower():
                    logger.error("❌ Service creation returned error in response")
                    logger.error(f"   Response: {response.text}")
                    return False
                

                
                return True
            else:
                logger.error(f"❌ Service creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Service creation test failed with exception: {str(e)}")
            return False
    
    async def test_get_service_by_ip_port(self) -> bool:
        """Test getting a service by IP and port via GET /assets/service/{ip}/{port}"""
        logger.info(f"Testing get service by IP and port: {self.test_ip}:{self.test_port}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/service/{self.test_ip}/{self.test_port}",
            headers=self.auth_manager.get_auth_headers() if self.auth_manager else {})
            
            if response.status_code == 200:
                data = response.json()
                service_data = data.get('data', {})
                logger.info("✅ Get service by IP and port successful")
                logger.info(f"   IP: {service_data.get('ip')}")
                logger.info(f"   Port: {service_data.get('port')}")
                logger.info(f"   Service: {service_data.get('service')}")
                logger.info(f"   Protocol: {service_data.get('protocol')}")
                logger.info(f"   Banner: {service_data.get('banner', '')[:50]}...")
                
                # Store the service ID for later tests
                self.created_service_id = service_data.get('id') or service_data.get('_id')
                if self.created_service_id:
                    logger.info(f"   Service ID: {self.created_service_id}")
                else:
                    logger.warning("   ⚠️  No service ID found in response")
                    logger.debug(f"   Response structure: {data}")
                
                return True
            else:
                logger.error(f"❌ Get service by IP and port failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get service by IP and port test failed with exception: {str(e)}")
            return False
    
    async def test_get_program_services(self) -> bool:
        """Test getting services for a specific program via POST /assets/service/search"""
        logger.info(f"Testing get program services: {self.test_program}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/assets/service/search",
                json={
                    "program": self.test_program,
                    "page": 1,
                    "page_size": 100
                },
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                services = data.get('items', [])
                pagination = data.get('pagination', {})
                logger.info("✅ Get program services successful")
                logger.info(f"   Found {len(services)} services in program {self.test_program}")
                logger.info(f"   Total items: {pagination.get('total_items', 0)}")
                
                # Check if our test service is in the list
                # Handle different IP formats (with/without CIDR notation)
                test_service_found = False
                for s in services:
                    service_ip = s.get('ip', '')
                    service_port = s.get('port')
                    
                    # Check if IP matches (with or without CIDR)
                    ip_matches = (service_ip == self.test_ip or 
                                service_ip == f"{self.test_ip}/32" or
                                service_ip.startswith(f"{self.test_ip}/"))
                    
                    # Check if port matches
                    port_matches = service_port == self.test_port
                    
                    if ip_matches and port_matches:
                        test_service_found = True
                        break
                
                if test_service_found:
                    logger.info("   ✅ Test service found in program list")
                    return True
                else:
                    logger.error("   ❌ Test service not found in program list")
                    logger.error(f"   Looking for: IP={self.test_ip}, Port={self.test_port}")
                    available_services = [f"{s.get('ip')}:{s.get('port')}" for s in services]
                    logger.error(f"   Available services: {available_services}")
                    return False
            else:
                logger.error(f"❌ Get program services failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get program services test failed with exception: {str(e)}")
            return False
    
    async def test_query_services(self) -> bool:
        """Test querying services via POST /assets/service/search"""
        logger.info("Testing service query")
        
        try:
            # Prepare query data
            query_data = {
                "program": self.test_program,
                "search_ip": self.test_ip,
                "page": 1,
                "page_size": 100,
                "sort_by": "port",
                "sort_dir": "asc"
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets/service/search",
                json=query_data,
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Service query successful")
                logger.info(f"   Found {len(items)} items")
                logger.info(f"   Total items: {pagination.get('total_items', 0)}")
                logger.info(f"   Current page: {pagination.get('current_page', 0)}")
                logger.info(f"   Total pages: {pagination.get('total_pages', 0)}")
                
                # Check if our test service is in the results
                test_service_found = any(item.get('ip') == self.test_ip and item.get('port') == self.test_port for item in items)
                if test_service_found:
                    logger.info("   ✅ Test service found in query results")
                    return True
                else:
                    logger.error("   ❌ Test service not found in query results")
                    logger.error(f"   Looking for: IP={self.test_ip}, Port={self.test_port}")
                    available_services = [f"{item.get('ip')}:{item.get('port')}" for item in items]
                    logger.error(f"   Available services: {available_services}")
                    return False
            else:
                logger.error(f"❌ Service query failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Service query test failed with exception: {str(e)}")
            return False
    
    async def test_update_service_notes(self) -> bool:
        """Test updating service notes via PUT /assets/service/{service_id}/notes"""
        logger.info(f"Testing update service notes: {self.created_service_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.created_service_id:
            logger.error("❌ No auth token or service ID available")
            return False
        
        try:
            # Prepare notes update data
            notes_data = {
                "notes": "Updated notes for test service - API testing completed successfully!"
            }
            
            response = await self.client.put(
                f"{self.base_url}/assets/service/{self.created_service_id}/notes",
                headers=self.auth_manager.get_auth_headers(),
                json=notes_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update service notes successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                logger.info(f"   Notes: {data.get('data', {}).get('notes')}")
                return True
            else:
                logger.error(f"❌ Update service notes failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update service notes test failed with exception: {str(e)}")
            return False
    
    async def test_verify_service_update(self) -> bool:
        """Test verifying the service was updated correctly"""
        logger.info(f"Testing verify service update: {self.test_ip}:{self.test_port}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/service/{self.test_ip}/{self.test_port}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                service_data = data.get('data', {})
                notes = service_data.get('notes', '')
                
                logger.info("✅ Verify service update successful")
                logger.info(f"   IP: {service_data.get('ip')}")
                logger.info(f"   Port: {service_data.get('port')}")
                logger.info(f"   Notes: {notes}")
                
                # Check if notes were updated
                if "API testing completed successfully" in notes:
                    logger.info("   ✅ Notes were updated correctly")
                    return True
                else:
                    logger.error("   ❌ Notes were not updated correctly")
                    return False
            else:
                logger.error(f"❌ Verify service update failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify service update test failed with exception: {str(e)}")
            return False
    
    async def test_delete_service(self) -> bool:
        """Test deleting a service via DELETE /assets/service/{service_id}"""
        logger.info(f"Testing delete service: {self.created_service_id}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.created_service_id:
            logger.error("❌ No auth token or service ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/assets/service/{self.created_service_id}",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete service successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete service failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete service test failed with exception: {str(e)}")
            return False
    
    async def test_verify_service_deletion(self) -> bool:
        """Test verifying the service was deleted correctly"""
        logger.info(f"Testing verify service deletion: {self.test_ip}:{self.test_port}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/service/{self.test_ip}/{self.test_port}",
                headers=self.auth_manager.get_auth_headers() if self.auth_manager else {}
            )
            
            if response.status_code == 404:
                logger.info("✅ Verify service deletion successful - service not found (404)")
                return True
            elif response.status_code == 200:
                logger.error("❌ Service still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify service deletion test failed with exception: {str(e)}")
            return False

async def run_service_tests():
    """Run all service route tests"""
    logger.info("🚀 Starting Service Routes Test Suite")
    logger.info("=" * 60)
    
    # Create a test program with proper scope
    async with create_test_program(scope_pattern=".*example\\.com") as test_program_name:
        logger.info(f"📋 Using test program: {test_program_name}")
        
        async with ServiceRouteTester() as tester:
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
            
            # Test 2: Create service
            logger.info("\n📝 Test 2: Create Service")
            result = await tester.test_create_service()
            test_results.append(("Create Service", result))
            
            if not result:
                logger.error("❌ Service creation failed, cannot continue with other tests")
                return False
            
            # Test 3: Get service by IP and port
            logger.info("\n📝 Test 3: Get Service by IP and Port")
            result = await tester.test_get_service_by_ip_port()
            test_results.append(("Get Service by IP and Port", result))
            
            # Test 4: Get program services
            logger.info("\n📝 Test 4: Get Program Services")
            result = await tester.test_get_program_services()
            test_results.append(("Get Program Services", result))
            
            # Test 5: Query services
            logger.info("\n📝 Test 5: Query Services")
            result = await tester.test_query_services()
            test_results.append(("Query Services", result))
            
            # Test 6: Update service notes
            logger.info("\n📝 Test 6: Update Service Notes")
            result = await tester.test_update_service_notes()
            test_results.append(("Update Service Notes", result))
            
            # Test 7: Verify service update
            logger.info("\n📝 Test 7: Verify Service Update")
            result = await tester.test_verify_service_update()
            test_results.append(("Verify Service Update", result))
            
            # Test 8: Delete service
            logger.info("\n📝 Test 8: Delete Service")
            result = await tester.test_delete_service()
            test_results.append(("Delete Service", result))
            
            # Test 9: Verify service deletion
            logger.info("\n📝 Test 9: Verify Service Deletion")
            result = await tester.test_verify_service_deletion()
            test_results.append(("Verify Service Deletion", result))
            
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
                logger.info("🎉 All tests passed! Service routes are working correctly.")
                return True
            else:
                logger.error(f"💥 {total - passed} test(s) failed. Check the logs above for details.")
                return False

if __name__ == "__main__":
    asyncio.run(run_service_tests()) 