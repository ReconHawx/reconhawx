#!/usr/bin/env python3
"""
Test script for Domain Scope Validation
Tests that domains are properly validated against program scope before creation

Note: The /assets endpoint uses batch processing and is designed to be resilient.
When a domain is out of scope, it is rejected (logged as error) but the API
still returns HTTP 200 to indicate the batch processing succeeded. This allows
workflows to continue even if some assets are invalid.
"""

import asyncio
from common_auth_manager import TestAuthManager
import logging
import httpx
import uuid
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DomainScopeValidationTester:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
        self.auth_manager: Optional[TestAuthManager] = None
        self.test_program = f"test-scope-{uuid.uuid4().hex[:8]}"
        self.scoped_domain = f"test-{uuid.uuid4().hex[:8]}.testscope.com"
        self.out_of_scope_domain = f"test-{uuid.uuid4().hex[:8]}.evil.com"
        
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
    
    async def test_create_program_with_scope(self) -> bool:
        """Test creating a program with domain scope restrictions"""
        logger.info(f"Testing program creation with domain scope: {self.test_program}")
        
        try:
            program_data = {
                "name": self.test_program,
                "domain_regex": [r".*\.testscope\.com$", r"^testscope\.com$"],  # Allow testscope.com and its subdomains
                "cidr_list": ["192.168.1.0/24"],
                "safe_registrar": [],
                "safe_ssl_issuer": []
            }
            
            response = await self.client.post(
                f"{self.base_url}/programs",
                json=program_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Program creation successful")
                logger.info(f"   Program ID: {data.get('id')}")
                return True
            else:
                logger.error(f"❌ Program creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Program creation test failed with exception: {str(e)}")
            return False
    
    async def test_create_domain_in_scope(self) -> bool:
        """Test creating a domain that is in scope (should succeed)"""
        logger.info(f"Testing domain creation in scope: {self.scoped_domain}")
        
        try:
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "domain": [
                        {
                            "name": self.scoped_domain,
                            "apex_domain": "testscope.com",
                            "is_wildcard": False,
                            "notes": "Test domain in scope"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Domain creation in scope successful")
                logger.info(f"   Status: {data.get('status')}")
                
                # Verify the domain WAS actually stored by querying the API
                domain_check_response = await self.client.get(
                    f"{self.base_url}/assets/domain/name/{self.scoped_domain}"
                )
                
                if domain_check_response.status_code == 200:
                    domain_data = domain_check_response.json()
                    logger.info("✅ Domain in scope was properly stored in database")
                    logger.info(f"   Domain ID: {domain_data.get('id')}")
                    return True
                elif domain_check_response.status_code == 404:
                    logger.error("❌ Domain in scope was not stored in database")
                    return False
                else:
                    logger.error(f"❌ Unexpected response when checking domain: {domain_check_response.status_code}")
                    return False
            else:
                logger.error(f"❌ Domain creation in scope failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Domain creation in scope test failed with exception: {str(e)}")
            return False
    
    async def test_create_domain_out_of_scope(self) -> bool:
        """Test creating a domain that is out of scope (should be rejected but API returns 200)"""
        logger.info(f"Testing domain creation out of scope: {self.out_of_scope_domain}")
        
        try:
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "domain": [
                        {
                            "name": self.out_of_scope_domain,
                            "apex_domain": "evil.com",
                            "is_wildcard": False,
                            "notes": "Test domain out of scope"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data
            )
            
            # API should return 200 (batch processing succeeds) but domain should be rejected
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ API returned 200 (batch processing succeeded)")
                logger.info(f"   Response: {data}")
                
                # Verify the domain was NOT actually stored by querying the API
                domain_check_response = await self.client.get(
                    f"{self.base_url}/assets/domain/name/{self.out_of_scope_domain}"
                )
                
                if domain_check_response.status_code == 404:
                    logger.info("✅ Domain out of scope was properly rejected (not found in database)")
                    return True
                elif domain_check_response.status_code == 200:
                    logger.error("❌ Domain out of scope was incorrectly stored in database")
                    return False
                else:
                    logger.error(f"❌ Unexpected response when checking domain: {domain_check_response.status_code}")
                    return False
            else:
                logger.error(f"❌ API should return 200 for batch processing, got {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Domain creation out of scope test failed with exception: {str(e)}")
            return False
    
    async def test_create_apex_domain_in_scope(self) -> bool:
        """Test creating an apex domain that is in scope (should succeed)"""
        logger.info("Testing apex domain creation in scope: testscope.com")
        
        try:
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "apex_domain": [
                        {
                            "name": "testscope.com",
                            "notes": "Test apex domain in scope"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Apex domain creation in scope successful")
                logger.info(f"   Status: {data.get('status')}")
                
                # Verify the apex domain WAS actually stored by querying the API
                # Note: We'll check if it exists in the program's apex domains
                apex_domains_response = await self.client.get(
                    f"{self.base_url}/assets/apex-domain/{self.test_program}"
                )
                
                if apex_domains_response.status_code == 200:
                    apex_domains_data = apex_domains_response.json()
                    apex_domains = apex_domains_data.get('items', [])
                    
                    logger.info(f"   Debug: Found {len(apex_domains)} apex domains in program")
                    logger.info(f"   Debug: Apex domains: {[d.get('name') for d in apex_domains]}")
                    
                    # Check if our apex domain is in the list
                    found_apex_domain = any(domain.get('name') == 'testscope.com' for domain in apex_domains)
                    
                    if found_apex_domain:
                        logger.info("✅ Apex domain in scope was properly stored in database")
                        return True
                    else:
                        logger.error("❌ Apex domain in scope was not stored in database")
                        logger.error("   Expected: testscope.com")
                        logger.error(f"   Found: {[d.get('name') for d in apex_domains]}")
                        return False
                else:
                    logger.error(f"❌ Failed to query apex domains: {apex_domains_response.status_code}")
                    return False
            else:
                logger.error(f"❌ Apex domain creation in scope failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Apex domain creation in scope test failed with exception: {str(e)}")
            return False
    
    async def test_create_apex_domain_out_of_scope(self) -> bool:
        """Test creating an apex domain that is out of scope (should be rejected but API returns 200)"""
        logger.info("Testing apex domain creation out of scope: evil.com")
        
        try:
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "apex_domain": [
                        {
                            "name": "evil.com",
                            "notes": "Test apex domain out of scope"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data
            )
            
            # API should return 200 (batch processing succeeds) but apex domain should be rejected
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ API returned 200 (batch processing succeeded)")
                logger.info(f"   Response: {data}")
                
                # Verify the apex domain was NOT actually stored by querying the API
                apex_domains_response = await self.client.get(
                    f"{self.base_url}/assets/apex-domain/{self.test_program}"
                )
                
                if apex_domains_response.status_code == 200:
                    apex_domains_data = apex_domains_response.json()
                    apex_domains = apex_domains_data.get('items', [])
                    
                    # Check if our out-of-scope apex domain is NOT in the list
                    found_evil_domain = any(domain.get('name') == 'evil.com' for domain in apex_domains)
                    
                    if not found_evil_domain:
                        logger.info("✅ Apex domain out of scope was properly rejected (not found in database)")
                        return True
                    else:
                        logger.error("❌ Apex domain out of scope was incorrectly stored in database")
                        return False
                else:
                    logger.error(f"❌ Failed to query apex domains: {apex_domains_response.status_code}")
                    return False
            else:
                logger.error(f"❌ API should return 200 for batch processing, got {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Apex domain creation out of scope test failed with exception: {str(e)}")
            return False
    
    async def test_create_url_in_scope(self) -> bool:
        """Test creating a URL that is in scope (should succeed)"""
        logger.info(f"Testing URL creation in scope: https://{self.scoped_domain}")
        
        try:
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "url": [
                        {
                            "url": f"https://{self.scoped_domain}/test",
                            "hostname": self.scoped_domain,
                            "scheme": "https",
                            "path": "/test",
                            "http_status_code": 200,
                            "notes": "Test URL in scope"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ URL creation in scope successful")
                logger.info(f"   Status: {data.get('status')}")
                
                # Verify the URL WAS actually stored by querying the API
                url_check_response = await self.client.post(
                    f"{self.base_url}/assets/url/by-url",
                    json={"url": f"https://{self.scoped_domain}/test"}
                )
                
                if url_check_response.status_code == 200:
                    url_data = url_check_response.json()
                    logger.info("✅ URL in scope was properly stored in database")
                    logger.info(f"   URL ID: {url_data.get('id')}")
                    return True
                elif url_check_response.status_code == 404:
                    logger.error("❌ URL in scope was not stored in database")
                    return False
                else:
                    logger.error(f"❌ Unexpected response when checking URL: {url_check_response.status_code}")
                    return False
            else:
                logger.error(f"❌ URL creation in scope failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ URL creation in scope test failed with exception: {str(e)}")
            return False
    
    async def test_create_url_out_of_scope(self) -> bool:
        """Test creating a URL that is out of scope (should be rejected but API returns 200)"""
        logger.info(f"Testing URL creation out of scope: https://{self.out_of_scope_domain}")
        
        try:
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "url": [
                        {
                            "url": f"https://{self.out_of_scope_domain}/test",
                            "hostname": self.out_of_scope_domain,
                            "scheme": "https",
                            "path": "/test",
                            "http_status_code": 200,
                            "notes": "Test URL out of scope"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data
            )
            
            # API should return 200 (batch processing succeeds) but URL should be rejected
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ API returned 200 (batch processing succeeded)")
                logger.info(f"   Response: {data}")
                
                # Verify the URL was NOT actually stored by querying the API
                url_check_response = await self.client.post(
                    f"{self.base_url}/assets/url/by-url",
                    json={"url": f"https://{self.out_of_scope_domain}/test"}
                )
                
                if url_check_response.status_code == 404:
                    logger.info("✅ URL out of scope was properly rejected (not found in database)")
                    return True
                elif url_check_response.status_code == 200:
                    logger.error("❌ URL out of scope was incorrectly stored in database")
                    return False
                else:
                    logger.error(f"❌ Unexpected response when checking URL: {url_check_response.status_code}")
                    return False
            else:
                logger.error(f"❌ API should return 200 for batch processing, got {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ URL creation out of scope test failed with exception: {str(e)}")
            return False

    async def test_url_hostname_scope_validation(self) -> bool:
        """Test URL hostname scope validation specifically"""
        logger.info("Testing URL hostname scope validation")
        
        try:
            # Test URLs with different hostnames
            test_urls = [
                {
                    "url": "https://valid-subdomain.testscope.com/path1",
                    "hostname": "valid-subdomain.testscope.com",
                    "expected_result": "success",
                    "description": "Valid subdomain in scope"
                },
                {
                    "url": "https://evil-subdomain.evil.com/path2", 
                    "hostname": "evil-subdomain.evil.com",
                    "expected_result": "error",
                    "description": "Invalid subdomain out of scope"
                },
                {
                    "url": "https://testscope.com/path3",
                    "hostname": "testscope.com", 
                    "expected_result": "success",
                    "description": "Valid apex domain in scope"
                },
                {
                    "url": "https://malicious.com/path4",
                    "hostname": "malicious.com",
                    "expected_result": "error", 
                    "description": "Invalid apex domain out of scope"
                }
            ]
            
            for i, test_case in enumerate(test_urls):
                logger.info(f"   Testing {test_case['description']}: {test_case['url']}")
                
                asset_data = {
                    "program_name": self.test_program,
                    "assets": {
                        "url": [
                            {
                                "url": test_case["url"],
                                "hostname": test_case["hostname"],
                                "scheme": "https",
                                "path": test_case["url"].split("/", 3)[-1] if "/" in test_case["url"][8:] else "/",
                                "http_status_code": 200,
                                "notes": f"Test URL: {test_case['description']}"
                            }
                        ]
                    }
                }
                
                response = await self.client.post(
                    f"{self.base_url}/assets",
                    json=asset_data
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if the result matches expected
                    if 'results' in data and len(data['results']) > 0:
                        result = data['results'][0]
                        actual_status = result.get('status')
                        
                        if actual_status == test_case['expected_result']:
                            logger.info(f"   ✅ {test_case['description']}: {actual_status}")
                            
                            # Verify database state
                            url_check_response = await self.client.post(
                                f"{self.base_url}/assets/url/by-url",
                                json={"url": test_case["url"]}
                            )
                            
                            if test_case['expected_result'] == 'success':
                                if url_check_response.status_code == 200:
                                    logger.info("      ✅ URL properly stored in database")
                                else:
                                    logger.error("      ❌ URL should be stored but not found")
                                    return False
                            else:  # expected_result == 'error'
                                if url_check_response.status_code == 404:
                                    logger.info("      ✅ URL properly rejected (not in database)")
                                else:
                                    logger.error("      ❌ URL should be rejected but found in database")
                                    return False
                        else:
                            logger.error(f"   ❌ {test_case['description']}: expected {test_case['expected_result']}, got {actual_status}")
                            logger.error(f"      Error message: {result.get('message', 'No message')}")
                            return False
                    else:
                        logger.error(f"   ❌ No results in response for {test_case['description']}")
                        return False
                else:
                    logger.error(f"   ❌ API request failed for {test_case['description']}: {response.status_code}")
                    return False
            
            logger.info("✅ All URL hostname scope validation tests passed")
            return True
                
        except Exception as e:
            logger.error(f"❌ URL hostname scope validation test failed with exception: {str(e)}")
            return False

    async def test_batch_domain_creation_mixed_scope(self) -> bool:
        """Test creating multiple domains in a single batch - some in scope, some out of scope"""
        logger.info("Testing batch domain creation with mixed scope")
        
        try:
            # Generate unique domain names
            in_scope_1 = f"in-scope-1.{uuid.uuid4().hex[:8]}.testscope.com"
            out_of_scope_1 = f"out-of-scope-1.{uuid.uuid4().hex[:8]}.evil.com"
            in_scope_2 = f"in-scope-2.{uuid.uuid4().hex[:8]}.testscope.com"
            out_of_scope_2 = f"out-of-scope-2.{uuid.uuid4().hex[:8]}.malicious.com"
            
            asset_data = {
                "program_name": self.test_program,
                "assets": {
                    "domain": [
                        {
                            "name": in_scope_1,
                            "apex_domain": "testscope.com",
                            "is_wildcard": False,
                            "notes": "Test domain in scope 1"
                        },
                        {
                            "name": out_of_scope_1,
                            "apex_domain": "evil.com",
                            "is_wildcard": False,
                            "notes": "Test domain out of scope 1"
                        },
                        {
                            "name": in_scope_2,
                            "apex_domain": "testscope.com",
                            "is_wildcard": False,
                            "notes": "Test domain in scope 2"
                        },
                        {
                            "name": out_of_scope_2,
                            "apex_domain": "malicious.com",
                            "is_wildcard": False,
                            "notes": "Test domain out of scope 2"
                        }
                    ]
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/assets",
                json=asset_data
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Batch domain creation successful")
                logger.info(f"   Status: {data.get('status')}")
                
                # Check the detailed results if available
                if 'results' in data:
                    logger.info(f"   Detailed results: {data.get('results')}")
                    
                    # Verify in-scope domains were created
                    in_scope_domains = [in_scope_1, in_scope_2]
                    
                    for domain_name in in_scope_domains:
                        domain_check_response = await self.client.get(
                            f"{self.base_url}/assets/domain/name/{domain_name}"
                        )
                        if domain_check_response.status_code == 200:
                            logger.info(f"✅ In-scope domain {domain_name} was properly stored")
                        else:
                            logger.error(f"❌ In-scope domain {domain_name} was not stored")
                            return False
                    
                    # Verify out-of-scope domains were NOT created
                    out_of_scope_domains = [out_of_scope_1, out_of_scope_2]
                    
                    for domain_name in out_of_scope_domains:
                        domain_check_response = await self.client.get(
                            f"{self.base_url}/assets/domain/name/{domain_name}"
                        )
                        if domain_check_response.status_code == 404:
                            logger.info(f"✅ Out-of-scope domain {domain_name} was properly rejected")
                        else:
                            logger.error(f"❌ Out-of-scope domain {domain_name} was incorrectly stored")
                            return False
                    
                    return True
                else:
                    logger.warning("⚠️  No detailed results in response, but batch processing succeeded")
                    return True
            else:
                logger.error(f"❌ Batch domain creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Batch domain creation test failed with exception: {str(e)}")
            return False

    async def cleanup_test_data(self) -> bool:
        """Clean up all test data created during testing"""
        logger.info(f"🧹 Cleaning up test data for program: {self.test_program}")
        
        try:
            # Delete the test program (this should cascade delete all associated assets)
            response = await self.client.delete(
                f"{self.base_url}/programs/{self.test_program}"
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Successfully deleted test program: {self.test_program}")
                return True
            elif response.status_code == 404:
                logger.info(f"ℹ️  Test program {self.test_program} was already deleted or doesn't exist")
                return True
            else:
                logger.warning(f"⚠️  Failed to delete test program {self.test_program}: {response.status_code}")
                logger.warning(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {str(e)}")
            return False

async def run_domain_scope_validation_tests():
    """Run all domain scope validation tests"""
    logger.info("🚀 Starting Domain Scope Validation Test Suite")
    logger.info("=" * 60)
    
    async with DomainScopeValidationTester() as tester:
        test_results = []
        
        # Test 1: Login (needed for some endpoints)
        logger.info("\n📝 Test 1: Login")
        result = await tester.test_login()
        test_results.append(("Login", result))
        
        if not result:
            logger.error("❌ Login failed, cannot continue with other tests")
            return False
        
        # Test 2: Create program with scope
        logger.info("\n📝 Test 2: Create Program with Scope")
        result = await tester.test_create_program_with_scope()
        test_results.append(("Create Program with Scope", result))
        
        if not result:
            logger.error("❌ Program creation failed, cannot continue with other tests")
            return False
        
        # Test 3: Domain creation in scope
        logger.info("\n📝 Test 3: Domain Creation in Scope")
        result = await tester.test_create_domain_in_scope()
        test_results.append(("Domain Creation in Scope", result))
        
        if not result:
            logger.error("❌ Domain creation in scope failed, cannot continue with other tests")
            return False
        
        # Test 4: Domain creation out of scope
        logger.info("\n📝 Test 4: Domain Creation Out of Scope")
        result = await tester.test_create_domain_out_of_scope()
        test_results.append(("Domain Creation Out of Scope", result))
        
        # Test 5: Apex domain creation in scope
        logger.info("\n📝 Test 5: Apex Domain Creation in Scope")
        result = await tester.test_create_apex_domain_in_scope()
        test_results.append(("Apex Domain Creation in Scope", result))
        
        if not result:
            logger.error("❌ Apex domain creation in scope failed, cannot continue with other tests")
            return False
        
        # Test 6: Apex domain creation out of scope
        logger.info("\n📝 Test 6: Apex Domain Creation Out of Scope")
        result = await tester.test_create_apex_domain_out_of_scope()
        test_results.append(("Apex Domain Creation Out of Scope", result))
        
        # Test 7: URL creation in scope
        logger.info("\n📝 Test 7: URL Creation in Scope")
        result = await tester.test_create_url_in_scope()
        test_results.append(("URL Creation in Scope", result))
        
        if not result:
            logger.error("❌ URL creation in scope failed, cannot continue with other tests")
            return False
        
        # Test 8: URL creation out of scope
        logger.info("\n📝 Test 8: URL Creation Out of Scope")
        result = await tester.test_create_url_out_of_scope()
        test_results.append(("URL Creation Out of Scope", result))
        
        # Test 9: URL hostname scope validation
        logger.info("\n📝 Test 9: URL Hostname Scope Validation")
        result = await tester.test_url_hostname_scope_validation()
        test_results.append(("URL Hostname Scope Validation", result))
        
        # Test 10: Batch domain creation with mixed scope
        logger.info("\n📝 Test 10: Batch Domain Creation with Mixed Scope")
        result = await tester.test_batch_domain_creation_mixed_scope()
        test_results.append(("Batch Domain Creation with Mixed Scope", result))
        
        # Test 11: Cleanup test data
        logger.info("\n📝 Test 11: Cleanup Test Data")
        result = await tester.cleanup_test_data()
        test_results.append(("Cleanup Test Data", result))
        
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
            logger.info("🎉 All tests passed! Domain scope validation is working correctly.")
        else:
            logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
        
        return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_domain_scope_validation_tests())
    exit(0 if success else 1) 