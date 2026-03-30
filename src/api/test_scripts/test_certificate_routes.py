#!/usr/bin/env python3
"""
Certificate Routes Test Suite

This script tests the certificate-related endpoints in the assets API:
- Create certificates via receive_asset endpoint
- Get certificate by subject DN
- Get certificates by program
- Query certificates with filters
- Update certificate notes
- Delete certificates
- Verify operations

Usage:
    python test_certificate_routes.py
"""

import asyncio
import httpx
import logging
import uuid
from typing import Optional

# Import the common managers
from common_auth_manager import TestAuthManager
from common_program_manager import create_test_program
from common_auth_manager import create_auth_session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CertificateRouteTester:
    """Test class for certificate-related API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_manager: Optional[TestAuthManager] = None
        self.created_certificate_id: Optional[str] = None
        self.test_program: Optional[str] = None
        self.test_subject_dn = f"CN=test-{uuid.uuid4().hex[:8]}.example.com, O=Test Organization, C=US"
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def test_create_certificate(self, auth_headers: dict) -> bool:
        """Test creating a certificate via POST /assets (receive_asset endpoint)"""
        logger.info(f"Testing certificate creation: {self.test_subject_dn}")
        
        try:
            # Prepare asset data for the receive_asset endpoint
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "certificate": [
                        {
                            "subject_dn": self.test_subject_dn,
                            "issuer_dn": "CN=Test CA, O=Test Certificate Authority, C=US",
                            "subject_an": [f"test-{uuid.uuid4().hex[:8]}.example.com", "*.test.example.com"],
                            "not_valid_before": "2024-01-01T00:00:00Z",
                            "not_valid_after": "2025-01-01T00:00:00Z",
                            "signature_algorithm": "sha256WithRSAEncryption",
                            "serial_number": f"1234567890{uuid.uuid4().hex[:8]}",
                            "fingerprint_hash": f"sha256:{uuid.uuid4().hex}",
                            "notes": "Test certificate for API testing"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                headers=auth_headers,
                json=asset_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Certificate creation successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Certificate creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Certificate creation test failed with exception: {str(e)}")
            return False
    
    async def test_get_certificate_by_subject_dn(self) -> bool:
        """Test getting a certificate by subject DN via POST /assets/certificate/by-subject-dn"""
        logger.info(f"Testing get certificate by subject DN: {self.test_subject_dn}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/assets/certificate/by-subject-dn",
                json={"subject_dn": self.test_subject_dn},
            headers=self.auth_manager.get_auth_headers() if self.auth_manager else {})
            
            if response.status_code == 200:
                data = response.json()
                cert_data = data.get('data', {})
                logger.info("✅ Get certificate by subject DN successful")
                logger.info(f"   Subject DN: {cert_data.get('subject_dn')}")
                logger.info(f"   Issuer DN: {cert_data.get('issuer_dn')}")
                logger.info(f"   Signature Algorithm: {cert_data.get('signature_algorithm')}")
                logger.info(f"   Serial Number: {cert_data.get('serial_number')}")
                
                # Store the certificate ID for later tests
                self.created_certificate_id = cert_data.get('id') or cert_data.get('_id')
                if self.created_certificate_id:
                    logger.info(f"   Certificate ID: {self.created_certificate_id}")
                else:
                    logger.warning("   ⚠️  No certificate ID found in response")
                    logger.debug(f"   Response structure: {data}")
                
                return True
            else:
                logger.error(f"❌ Get certificate by subject DN failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get certificate by subject DN test failed with exception: {str(e)}")
            return False
    
    async def test_get_program_certificates(self) -> bool:
        """Test getting certificates for a specific program via GET /assets/certificate/{program_name}"""
        logger.info(f"Testing get program certificates: {self.test_program}")
        
        try:
            response = await self.client.get(
                f"{self.base_url}/assets/certificate/{self.test_program}",
                params={"limit": 100},
            headers=self.auth_manager.get_auth_headers() if self.auth_manager else {})
            
            if response.status_code == 200:
                data = response.json()
                certificates = data.get('items', [])
                pagination = data.get('pagination', {})
                logger.info("✅ Get program certificates successful")
                logger.info(f"   Found {len(certificates)} certificates in program {self.test_program}")
                logger.info(f"   Total items: {pagination.get('total_items', 0)}")
                
                # Check if our test certificate is in the list
                test_cert_found = any(c.get('subject_dn') == self.test_subject_dn for c in certificates)
                if test_cert_found:
                    logger.info("   ✅ Test certificate found in program list")
                    return True
                else:
                    logger.error("   ❌ Test certificate not found in program list")
                    logger.error(f"   Looking for: {self.test_subject_dn}")
                    available_certs = [c.get('subject_dn') for c in certificates[:5]]  # Show first 5 certs
                    logger.error(f"   Available certificates (first 5): {available_certs}")
                    return False
            else:
                logger.error(f"❌ Get program certificates failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get program certificates test failed with exception: {str(e)}")
            return False
    
    async def test_query_certificates(self) -> bool:
        """Test querying certificates via POST /assets/certificate/query"""
        logger.info("Testing certificate query")
        
        try:
            # Prepare query data
            query_data = {
                "filter": {
                    "program_name": self.test_program,
                    "subject_dn": {"$regex": "test-", "$options": "i"}
                },
                "limit": 100,
                "page": 1,
                "sort": {"subject_dn": 1}
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets/certificate/query",
                json=query_data,
            headers=self.auth_manager.get_auth_headers() if self.auth_manager else {})
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                pagination = data.get('pagination', {})
                
                logger.info("✅ Certificate query successful")
                logger.info(f"   Found {len(items)} items")
                logger.info(f"   Total items: {pagination.get('total_items', 0)}")
                logger.info(f"   Current page: {pagination.get('current_page', 0)}")
                logger.info(f"   Total pages: {pagination.get('total_pages', 0)}")
                
                # Check if our test certificate is in the results
                test_cert_found = any(item.get('subject_dn') == self.test_subject_dn for item in items)
                if test_cert_found:
                    logger.info("   ✅ Test certificate found in query results")
                else:
                    logger.warning("   ⚠️  Test certificate not found in query results")
                
                return True
            else:
                logger.error(f"❌ Certificate query failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Certificate query test failed with exception: {str(e)}")
            return False
    
    async def test_update_certificate_notes(self, auth_headers: dict) -> bool:
        """Test updating certificate notes via PUT /assets/certificate/{certificate_id}/notes"""
        logger.info(f"Testing update certificate notes: {self.created_certificate_id}")
        
        if not self.created_certificate_id:
            logger.error("❌ No certificate ID available")
            return False
        
        try:
            # Prepare notes update data
            notes_data = {
                "notes": "Updated notes for test certificate - API testing completed successfully!"
            }
            
            response = await self.client.put(
                f"{self.base_url}/assets/certificate/{self.created_certificate_id}/notes",
                headers=auth_headers,
                json=notes_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Update certificate notes successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                logger.info(f"   Notes: {data.get('data', {}).get('notes')}")
                return True
            else:
                logger.error(f"❌ Update certificate notes failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Update certificate notes test failed with exception: {str(e)}")
            return False
    
    async def test_verify_certificate_update(self) -> bool:
        """Test verifying the certificate was updated correctly"""
        logger.info(f"Testing verify certificate update: {self.test_subject_dn}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/assets/certificate/by-subject-dn",
                json={"subject_dn": self.test_subject_dn}
            )
            
            if response.status_code == 200:
                data = response.json()
                cert_data = data.get('data', {})
                notes = cert_data.get('notes', '')
                
                logger.info("✅ Verify certificate update successful")
                logger.info(f"   Subject DN: {cert_data.get('subject_dn')}")
                logger.info(f"   Notes: {notes}")
                
                # Check if notes were updated
                if "API testing completed successfully" in notes:
                    logger.info("   ✅ Notes were updated correctly")
                    return True
                else:
                    logger.error("   ❌ Notes were not updated correctly")
                    return False
            else:
                logger.error(f"❌ Verify certificate update failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify certificate update test failed with exception: {str(e)}")
            return False
    
    async def test_delete_certificate(self, auth_headers: dict) -> bool:
        """Test deleting a certificate via DELETE /assets/certificate/{certificate_id}"""
        logger.info(f"Testing delete certificate: {self.created_certificate_id}")
        
        if not self.created_certificate_id:
            logger.error("❌ No certificate ID available")
            return False
        
        try:
            response = await self.client.delete(
                f"{self.base_url}/assets/certificate/{self.created_certificate_id}",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Delete certificate successful")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Message: {data.get('message')}")
                return True
            else:
                logger.error(f"❌ Delete certificate failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Delete certificate test failed with exception: {str(e)}")
            return False
    
    async def test_verify_certificate_deletion(self) -> bool:
        """Test verifying the certificate was deleted correctly"""
        logger.info(f"Testing verify certificate deletion: {self.test_subject_dn}")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/assets/certificate/by-subject-dn",
                json={"subject_dn": self.test_subject_dn}
            )
            
            if response.status_code == 404:
                logger.info("✅ Verify certificate deletion successful - certificate not found (404)")
                return True
            elif response.status_code == 200:
                logger.error("❌ Certificate still exists after deletion")
                return False
            else:
                logger.warning(f"⚠️  Unexpected status when verifying deletion: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verify certificate deletion test failed with exception: {str(e)}")
            return False

async def run_certificate_tests():
    """Run all certificate route tests"""
    logger.info("🚀 Starting Certificate Routes Test Suite")
    logger.info("=" * 60)
    
    # Create a test program with proper scope
    async with create_test_program(scope_pattern=".*example\\.com") as test_program_name:
        logger.info(f"📋 Using test program: {test_program_name}")
        
        # Create authenticated session
        async with create_auth_session() as auth_manager:
            logger.info("🔐 Using authenticated session")
            
            async with CertificateRouteTester() as tester:
                # Set the test program name
                tester.test_program = test_program_name
                
                # Get auth headers for authenticated requests
                auth_headers = auth_manager.get_auth_headers()
                
                test_results = []
                
                # Test 1: Create certificate
                logger.info("\n📝 Test 1: Create Certificate")
                result = await tester.test_create_certificate(auth_headers)
                test_results.append(("Create Certificate", result))
                
                if not result:
                    logger.error("❌ Certificate creation failed, cannot continue with other tests")
                    return False
                
                # Test 2: Get certificate by subject DN
                logger.info("\n📝 Test 2: Get Certificate by Subject DN")
                result = await tester.test_get_certificate_by_subject_dn()
                test_results.append(("Get Certificate by Subject DN", result))
                
                # Test 3: Get program certificates
                logger.info("\n📝 Test 3: Get Program Certificates")
                result = await tester.test_get_program_certificates()
                test_results.append(("Get Program Certificates", result))
                
                # Test 4: Query certificates
                logger.info("\n📝 Test 4: Query Certificates")
                result = await tester.test_query_certificates()
                test_results.append(("Query Certificates", result))
                
                # Test 5: Update certificate notes
                logger.info("\n📝 Test 5: Update Certificate Notes")
                result = await tester.test_update_certificate_notes(auth_headers)
                test_results.append(("Update Certificate Notes", result))
                
                # Test 6: Verify certificate update
                logger.info("\n📝 Test 6: Verify Certificate Update")
                result = await tester.test_verify_certificate_update()
                test_results.append(("Verify Certificate Update", result))
                
                # Test 7: Delete certificate
                logger.info("\n📝 Test 7: Delete Certificate")
                result = await tester.test_delete_certificate(auth_headers)
                test_results.append(("Delete Certificate", result))
                
                # Test 8: Verify certificate deletion
                logger.info("\n📝 Test 8: Verify Certificate Deletion")
                result = await tester.test_verify_certificate_deletion()
                test_results.append(("Verify Certificate Deletion", result))
                
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
                    logger.info("🎉 All tests passed! Certificate routes are working correctly.")
                    return True
                else:
                    logger.error(f"💥 {total - passed} test(s) failed. Check the logs above for details.")
                    return False

if __name__ == "__main__":
    asyncio.run(run_certificate_tests()) 