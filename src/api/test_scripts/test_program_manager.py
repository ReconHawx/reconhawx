#!/usr/bin/env python3
"""
Test script for the Common Program Manager

This script tests the common program manager functionality to ensure it works correctly
before using it in other test scripts.

Usage:
    python test_program_manager.py
"""

import asyncio
import logging
from common_program_manager import TestProgramManager, create_test_program

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_program_manager_direct():
    """Test the TestProgramManager class directly"""
    logger.info("🧪 Testing TestProgramManager class directly")
    
    async with TestProgramManager() as manager:
        # Test program creation
        program_name = await manager.create_test_program(scope_pattern=".*test\\.com")
        logger.info(f"✅ Created program: {program_name}")
        
        # The program should be automatically deleted when the context exits
        logger.info("✅ Context manager will handle cleanup")

async def test_program_manager_context():
    """Test the create_test_program context manager"""
    logger.info("🧪 Testing create_test_program context manager")
    
    async with create_test_program(scope_pattern=".*example\\.com") as program_name:
        logger.info(f"✅ Created program via context manager: {program_name}")
        # The program should be automatically deleted when the context exits
        logger.info("✅ Context manager will handle cleanup")

async def run_program_manager_tests():
    """Run all program manager tests"""
    logger.info("🚀 Starting Program Manager Test Suite")
    logger.info("=" * 60)
    
    test_results = []
    
    # Test 1: Direct TestProgramManager usage
    logger.info("\n📝 Test 1: Direct TestProgramManager Usage")
    try:
        await test_program_manager_direct()
        test_results.append(("Direct TestProgramManager Usage", True))
    except Exception as e:
        logger.error(f"❌ Direct TestProgramManager test failed: {str(e)}")
        test_results.append(("Direct TestProgramManager Usage", False))
    
    # Test 2: Context manager usage
    logger.info("\n📝 Test 2: Context Manager Usage")
    try:
        await test_program_manager_context()
        test_results.append(("Context Manager Usage", True))
    except Exception as e:
        logger.error(f"❌ Context manager test failed: {str(e)}")
        test_results.append(("Context Manager Usage", False))
    
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
        logger.info("🎉 All tests passed! Program manager is working correctly.")
        return True
    else:
        logger.error(f"💥 {total - passed} test(s) failed. Check the logs above for details.")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_program_manager_tests())
    exit(0 if success else 1) 