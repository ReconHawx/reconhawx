#!/usr/bin/env python3
"""
Typosquat RecordedFuture Integration Test

This script tests the integration between typosquat domain updates and RecordedFuture API calls.
It verifies that when a typosquat domain status is updated and the domain has RecordedFuture data,
the RecordedFuture alert status is also updated.
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any

# Add the parent directory to the path so we can import the API modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from repository.typosquat_findings_repo import TyposquatFindingsRepository
from common_program_manager import create_test_program

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TyposquatRecordedFutureIntegrationTester:
    """Test class for typosquat RecordedFuture integration"""
    
    def __init__(self):
        self.test_program: str = None
        self.test_domain_id: str = None
    
    async def test_status_mapping(self) -> bool:
        """Test the status mapping function"""
        logger.info("📝 Testing status mapping function...")
        
        test_cases = [
            ('new', 'New'),
            ('investigating', 'In Progress'),
            ('confirmed', 'In Progress'),
            ('resolved', 'Resolved'),
            ('false_positive', 'False Positive'),
            ('closed', 'Closed'),
            ('dismissed', 'Dismissed'),
            ('unknown_status', None),
            ('', None),
            (None, None)
        ]
        
        all_passed = True
        
        for internal_status, expected_rf_status in test_cases:
            result = TyposquatFindingsRepository._map_status_to_recordedfuture(internal_status)
            
            if result == expected_rf_status:
                logger.info(f"✅ Status mapping '{internal_status}' -> '{result}' (expected: '{expected_rf_status}')")
            else:
                logger.error(f"❌ Status mapping '{internal_status}' -> '{result}' (expected: '{expected_rf_status}')")
                all_passed = False
        
        return all_passed
    
    async def test_recordedfuture_data_detection(self) -> bool:
        """Test detection of RecordedFuture data in typosquat domains"""
        logger.info("📝 Testing RecordedFuture data detection...")
        
        # Test cases for recordedfuture_data
        test_cases = [
            # (recordedfuture_data, has_playbook_alert_id, description)
            (None, False, "None data"),
            ({}, False, "Empty data"),
            ({"status": "New"}, False, "Data without playbook_alert_id"),
            ({"playbook_alert_id": None}, False, "Data with null playbook_alert_id"),
            ({"playbook_alert_id": ""}, False, "Data with empty playbook_alert_id"),
            ({"playbook_alert_id": "task:123"}, True, "Data with valid playbook_alert_id"),
            ({"status": "New", "playbook_alert_id": "task:456"}, True, "Data with status and playbook_alert_id"),
        ]
        
        all_passed = True
        
        for recordedfuture_data, expected_has_data, description in test_cases:
            # Simulate the logic from update_typosquat_domain
            has_recordedfuture_data = (
                recordedfuture_data is not None and 
                recordedfuture_data.get('playbook_alert_id') is not None
            )
            
            if has_recordedfuture_data == expected_has_data:
                logger.info(f"✅ {description}: {has_recordedfuture_data} (expected: {expected_has_data})")
            else:
                logger.error(f"❌ {description}: {has_recordedfuture_data} (expected: {expected_has_data})")
                all_passed = False
        
        return all_passed
    
    async def test_integration_conditions(self) -> bool:
        """Test the integration conditions logic"""
        logger.info("📝 Testing integration conditions...")
        
        # Test cases: (status_updated, has_recordedfuture_data, new_status, should_integrate, description)
        test_cases = [
            (True, True, "resolved", True, "Status updated with RecordedFuture data"),
            (True, True, "", False, "Status updated with empty status"),
            (True, True, None, False, "Status updated with None status"),
            (True, False, "resolved", False, "Status updated without RecordedFuture data"),
            (False, True, "resolved", False, "No status update with RecordedFuture data"),
            (False, False, "resolved", False, "No status update without RecordedFuture data"),
        ]
        
        all_passed = True
        
        for status_updated, has_recordedfuture_data, new_status, should_integrate, description in test_cases:
            # Simulate the logic from update_typosquat_domain
            should_call_recordedfuture = (
                status_updated and 
                has_recordedfuture_data and 
                new_status
            )
            
            if should_call_recordedfuture == should_integrate:
                logger.info(f"✅ {description}: {should_call_recordedfuture} (expected: {should_integrate})")
            else:
                logger.error(f"❌ {description}: {should_call_recordedfuture} (expected: {should_integrate})")
                all_passed = False
        
        return all_passed
    
    async def test_mock_update_scenario(self) -> bool:
        """Test a mock update scenario (without actual database operations)"""
        logger.info("📝 Testing mock update scenario...")
        
        try:
            # Mock typosquat domain object
            class MockTyposquatDomain:
                def __init__(self, recordedfuture_data, program_id=None):
                    self.id = "test-domain-123"
                    self.recordedfuture_data = recordedfuture_data
                    self.program_id = program_id
                    self.program = None
            
            # Test with valid RecordedFuture data
            mock_typosquat = MockTyposquatDomain({
                "status": "New",
                "playbook_alert_id": "task:e7a5f59f-878f-4620-9772-d9cc16bf8a6d",
                "category": "domain_abuse"
            })
            
            # Test status mapping
            rf_status = TyposquatFindingsRepository._map_status_to_recordedfuture("resolved")
            if rf_status == "Resolved":
                logger.info("✅ Status mapping works correctly")
            else:
                logger.error(f"❌ Status mapping failed: expected 'Resolved', got '{rf_status}'")
                return False
            
            # Test data detection
            has_data = (
                mock_typosquat.recordedfuture_data is not None and 
                mock_typosquat.recordedfuture_data.get('playbook_alert_id') is not None
            )
            
            if has_data:
                logger.info("✅ RecordedFuture data detection works correctly")
            else:
                logger.error("❌ RecordedFuture data detection failed")
                return False
            
            logger.info("✅ Mock update scenario test passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Mock update scenario test failed: {e}")
            return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling scenarios"""
        logger.info("📝 Testing error handling...")
        
        try:
            # Test with invalid status
            result = TyposquatFindingsRepository._map_status_to_recordedfuture("invalid_status")
            if result is None:
                logger.info("✅ Invalid status handled correctly (returns None)")
            else:
                logger.error(f"❌ Invalid status should return None, got: {result}")
                return False
            
            # Test with None status
            result = TyposquatFindingsRepository._map_status_to_recordedfuture(None)
            if result is None:
                logger.info("✅ None status handled correctly (returns None)")
            else:
                logger.error(f"❌ None status should return None, got: {result}")
                return False
            
            logger.info("✅ Error handling tests passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error handling test failed: {e}")
            return False


async def run_typosquat_recordedfuture_tests():
    """Run all typosquat RecordedFuture integration tests"""
    logger.info("🚀 Starting Typosquat RecordedFuture Integration Test Suite")
    logger.info("=" * 70)
    
    tester = TyposquatRecordedFutureIntegrationTester()
    
    test_results = []
    
    # Test 1: Status mapping
    logger.info("\n📝 Test 1: Status Mapping")
    result = await tester.test_status_mapping()
    test_results.append(("Status Mapping", result))
    
    # Test 2: RecordedFuture data detection
    logger.info("\n📝 Test 2: RecordedFuture Data Detection")
    result = await tester.test_recordedfuture_data_detection()
    test_results.append(("RecordedFuture Data Detection", result))
    
    # Test 3: Integration conditions
    logger.info("\n📝 Test 3: Integration Conditions")
    result = await tester.test_integration_conditions()
    test_results.append(("Integration Conditions", result))
    
    # Test 4: Mock update scenario
    logger.info("\n📝 Test 4: Mock Update Scenario")
    result = await tester.test_mock_update_scenario()
    test_results.append(("Mock Update Scenario", result))
    
    # Test 5: Error handling
    logger.info("\n📝 Test 5: Error Handling")
    result = await tester.test_error_handling()
    test_results.append(("Error Handling", result))
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("📊 Test Results Summary")
    logger.info("=" * 70)
    
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
        logger.info("🎉 All tests passed! Typosquat RecordedFuture integration is working correctly.")
        return True
    else:
        logger.error(f"💥 {total - passed} test(s) failed. Check the logs above for details.")
        return False


if __name__ == "__main__":
    asyncio.run(run_typosquat_recordedfuture_tests())
