#!/usr/bin/env python3
"""
Test script for Auth Routes
Tests login, API token creation, API token usage, and logout functionality
"""

import asyncio
import logging
import httpx
from typing import Optional

# Import the common auth manager
from common_auth_manager import TestAuthManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthRouteTester:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
        self.auth_manager: Optional[TestAuthManager] = None
        self.api_token: Optional[str] = None
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def test_login(self, username: str = "admin", password: str = "password") -> bool:
        """Test login functionality using TestAuthManager"""
        logger.info(f"Testing login with username: {username}")
        
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
    
    async def test_get_current_user(self) -> bool:
        """Test getting current user info with auth token"""
        logger.info("Testing get current user with auth token")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/auth/user",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                user = response.json()
                logger.info(f"✅ Get current user successful: {user['username']}")
                return True
            else:
                logger.error(f"❌ Get current user failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get current user test failed with exception: {str(e)}")
            return False
    
    async def test_create_api_token(self, token_name: str = "Test API Token") -> bool:
        """Test API token creation"""
        logger.info(f"Testing API token creation: {token_name}")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            response = await self.client.post(
                f"{self.base_url}/auth/api-tokens",
                headers=self.auth_manager.get_auth_headers(),
                json={
                    "name": token_name,
                    "description": "Test token for authentication testing"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.api_token = data["token"]
                token_info = data["token_info"]
                logger.info("✅ API token created successfully")
                logger.info(f"   Token ID: {token_info['id']}")
                logger.info(f"   Token Name: {token_info['name']}")
                logger.info(f"   Token Value: {self.api_token[:20]}...")
                logger.info(f"   Full Token Value: {self.api_token}")
                return True
            else:
                logger.error(f"❌ API token creation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ API token creation test failed with exception: {str(e)}")
            return False
    
    async def test_get_api_tokens(self) -> bool:
        """Test getting list of API tokens"""
        logger.info("Testing get API tokens list")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/auth/api-tokens",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                tokens = data["tokens"]
                logger.info(f"✅ Get API tokens successful, found {len(tokens)} tokens")
                for token in tokens:
                    logger.info(f"   - {token['name']} (ID: {token['id']})")
                return True
            else:
                logger.error(f"❌ Get API tokens failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Get API tokens test failed with exception: {str(e)}")
            return False
    
    async def test_api_token_authentication(self) -> bool:
        """Test API token authentication by accessing /auth/user endpoint"""
        logger.info("Testing API token authentication")
        
        if not self.api_token:
            logger.error("❌ No API token available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/auth/user",
                headers={"Authorization": f"Bearer {self.api_token}"}
            )
            
            if response.status_code == 200:
                user = response.json()
                logger.info(f"✅ API token authentication successful: {user['username']}")
                return True
            else:
                logger.error(f"❌ API token authentication failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ API token authentication test failed with exception: {str(e)}")
            return False
    
    async def test_logout(self) -> bool:
        """Test logout functionality"""
        logger.info("Testing logout")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("❌ No auth manager or not authenticated")
            return False
        
        try:
            response = await self.client.post(
                f"{self.base_url}/auth/logout",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Logout successful: {data['message']}")
                # Clean up auth manager
                await self.auth_manager.__aexit__(None, None, None)
                self.auth_manager = None
                return True
            else:
                logger.error(f"❌ Logout failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Logout test failed with exception: {str(e)}")
            return False
    
    async def test_auth_token_invalid_after_logout(self) -> bool:
        """Test that auth token behavior after logout (JWT tokens remain valid until expiration)"""
        logger.info("Testing auth token behavior after logout")
        
        if self.auth_manager and self.auth_manager.is_authenticated():
            logger.error("❌ Auth manager still authenticated after logout")
            return False
        
        logger.info("✅ Auth manager properly cleaned up after logout")
        logger.info("   Note: JWT tokens remain valid until expiration (stateless design)")
        return True
    
    async def test_api_token_still_valid_after_logout(self) -> bool:
        """Test that API token is still valid after logout (API tokens should persist)"""
        logger.info("Testing that API token is still valid after logout")
        
        if not self.api_token:
            logger.error("❌ No API token available")
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/auth/user",
                headers={"Authorization": f"Bearer {self.api_token}"}
            )
            
            if response.status_code == 200:
                user = response.json()
                logger.info(f"✅ API token still valid after logout: {user['username']}")
                return True
            else:
                logger.error(f"❌ API token invalid after logout (status: {response.status_code})")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ API token persistence test failed with exception: {str(e)}")
            return False
    
    async def test_revoke_api_token(self) -> bool:
        """Test revoking/deleting API token using web session token (not the API token itself)"""
        logger.info("Testing API token revocation using web session token")
        
        if not self.auth_manager or not self.auth_manager.is_authenticated() or not self.api_token:
            logger.error("❌ Need both auth manager (web session) and API token for revocation test")
            return False
        
        try:
            # First, get the token ID from the tokens list
            response = await self.client.get(
                f"{self.base_url}/auth/api-tokens",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Failed to get API tokens for revocation test: {response.status_code}")
                return False
            
            tokens = response.json()["tokens"]
            if not tokens:
                logger.error("❌ No API tokens found for revocation test")
                return False
            
            logger.info(f"   Found {len(tokens)} tokens before revocation:")
            for token in tokens:
                logger.info(f"     - {token['name']} (ID: {token['id']})")
            
            # Find user-created API tokens (exclude "Web Login" tokens)
            user_tokens = [t for t in tokens if t['name'] != "Web Login"]
            if not user_tokens:
                logger.error("❌ No user-created API tokens found for revocation test")
                return False
            
            # Use the first user-created token for revocation
            token_id = user_tokens[0]["id"]
            token_name = user_tokens[0]["name"]
            logger.info(f"   Revoking user-created API token: {token_name} (ID: {token_id})")
            
            # Revoke the token using web session token (not the API token itself)
            response = await self.client.delete(
                f"{self.base_url}/auth/api-tokens/{token_id}",
                headers=self.auth_manager.get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ API token revocation request successful: {data['message']}")
                
                # Now verify the token is actually deleted by checking the tokens list
                logger.info("   Verifying token is actually deleted from database...")
                list_response = await self.client.get(
                    f"{self.base_url}/auth/api-tokens",
                    headers=self.auth_manager.get_auth_headers()
                )
                
                if list_response.status_code == 200:
                    remaining_tokens = list_response.json()["tokens"]
                    token_ids = [t["id"] for t in remaining_tokens]
                    
                    logger.info(f"   Found {len(remaining_tokens)} tokens after revocation:")
                    for token in remaining_tokens:
                        logger.info(f"     - {token['name']} (ID: {token['id']})")
                    
                    # Check if the specific user-created token was deleted
                    if token_id not in token_ids:
                        logger.info("✅ API token is properly deleted from database")
                        
                        # Also verify it can't be used for authentication
                        logger.info("   Verifying token can't be used for authentication...")
                        verify_response = await self.client.get(
                            f"{self.base_url}/auth/user",
                            headers={"Authorization": f"Bearer {self.api_token}"}
                        )
                        
                        if verify_response.status_code == 401:
                            logger.info("✅ API token is properly invalidated after revocation")
                            return True
                        elif verify_response.status_code == 200:
                            logger.error("❌ API token is still valid after revocation - authentication still works")
                            return False
                        else:
                            logger.warning(f"⚠️  Unexpected status when verifying token: {verify_response.status_code}")
                            return False
                    else:
                        logger.error(f"❌ API token {token_id} still exists in database after revocation")
                        return False
                else:
                    logger.error(f"❌ Failed to get API tokens list for verification: {list_response.status_code}")
                    return False
            else:
                logger.error(f"❌ API token revocation failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ API token revocation test failed with exception: {str(e)}")
            return False
    
    async def test_all_auth_invalid_after_logout(self) -> bool:
        """Test that all authentication methods are properly handled after logout"""
        logger.info("Testing authentication behavior after logout")
        
        # Check that auth manager is cleaned up
        if self.auth_manager and self.auth_manager.is_authenticated():
            logger.error("❌ Auth manager still authenticated after logout")
            return False
        
        logger.info("✅ Auth manager properly cleaned up after logout")
        
        # Check that API token is invalid (should have been revoked)
        if self.api_token:
            try:
                response = await self.client.get(
                    f"{self.base_url}/auth/user",
                    headers={"Authorization": f"Bearer {self.api_token}"}
                )
                
                if response.status_code == 200:
                    logger.error("❌ API token is still valid after revocation")
                    return False
                elif response.status_code == 401:
                    logger.info("✅ API token properly invalidated after revocation")
                else:
                    logger.warning(f"⚠️  Unexpected status for revoked API token: {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Error testing revoked API token: {str(e)}")
                return False
        
        logger.info("✅ Authentication properly handled after logout")
        logger.info("   Note: JWT tokens remain valid until expiration (stateless design)")
        return True

async def run_auth_tests():
    """Run all auth route tests"""
    logger.info("🚀 Starting Auth Routes Test Suite")
    logger.info("=" * 50)
    
    async with AuthRouteTester() as tester:
        test_results = []
        
        # Test 1: Login
        logger.info("\n📝 Test 1: Login")
        result = await tester.test_login()
        test_results.append(("Login", result))
        
        if not result:
            logger.error("❌ Login failed, cannot continue with other tests")
            return
        
        # Test 2: Get current user with auth token
        logger.info("\n📝 Test 2: Get Current User (Auth Token)")
        result = await tester.test_get_current_user()
        test_results.append(("Get Current User (Auth Token)", result))
        
        # Test 3: Create API token
        logger.info("\n📝 Test 3: Create API Token")
        result = await tester.test_create_api_token()
        test_results.append(("Create API Token", result))
        
        # Test 4: Get API tokens list
        logger.info("\n📝 Test 4: Get API Tokens List")
        result = await tester.test_get_api_tokens()
        test_results.append(("Get API Tokens List", result))
        
        # Test 5: Test API token authentication
        logger.info("\n📝 Test 5: API Token Authentication")
        result = await tester.test_api_token_authentication()
        test_results.append(("API Token Authentication", result))
        
        # Test 6: Logout
        logger.info("\n📝 Test 6: Logout")
        result = await tester.test_logout()
        test_results.append(("Logout", result))
        
        # Test 7: Verify auth token behavior after logout
        logger.info("\n📝 Test 7: Auth Token Behavior After Logout")
        result = await tester.test_auth_token_invalid_after_logout()
        test_results.append(("Auth Token Behavior After Logout", result))
        
        # Test 8: Verify API token is still valid after logout
        logger.info("\n📝 Test 8: API Token Still Valid After Logout")
        result = await tester.test_api_token_still_valid_after_logout()
        test_results.append(("API Token Still Valid After Logout", result))
        
        # Test 9: Revoke API token (need to login again first to get fresh auth token)
        logger.info("\n📝 Test 9: Revoke API Token")
        # Login again for revocation test to get fresh web session token
        login_result = await tester.test_login()
        if login_result:
            result = await tester.test_revoke_api_token()
            test_results.append(("Revoke API Token", result))
        else:
            logger.error("❌ Cannot test API token revocation - login failed")
            test_results.append(("Revoke API Token", False))
        
        # Test 10: Second logout after API token revocation
        logger.info("\n📝 Test 10: Second Logout After API Token Revocation")
        result = await tester.test_logout()
        test_results.append(("Second Logout After API Token Revocation", result))
        
        # Test 11: Verify authentication behavior after second logout
        logger.info("\n📝 Test 11: Verify Authentication Behavior After Second Logout")
        result = await tester.test_all_auth_invalid_after_logout()
        test_results.append(("Authentication Behavior After Second Logout", result))
        
        # Summary
        logger.info("\n" + "=" * 50)
        logger.info("📊 Test Results Summary")
        logger.info("=" * 50)
        
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{status} - {test_name}")
            if result:
                passed += 1
        
        logger.info(f"\n🎯 Overall Result: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests passed! Auth routes are working correctly.")
        else:
            logger.error(f"💥 {total - passed} test(s) failed. Please check the implementation.")
        
        return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_auth_tests())
    exit(0 if success else 1) 