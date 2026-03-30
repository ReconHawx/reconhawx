#!/usr/bin/env python3
"""
Test script to verify that typosquat distinct field queries work correctly
for nested JSON fields like info.whois.registrar, info.geoip.country, etc.
"""

import requests
import sys

# Configuration
API_BASE_URL = "http://localhost:8001"
TEST_PROGRAM = "test-program"

def test_typosquat_distinct_fields():
    """Test the typosquat distinct field endpoints"""
    
    print("Testing typosquat distinct field queries...")
    
    # Fields to test
    test_fields = [
        "typo_domain", 
        "program_name",
        "fuzzers",
        "info.country",
        "info.registrar", 
        "info.http.status_code",
        "info.geoip.country",
        "info.whois.registrar"
    ]
    
    results = {}
    
    for field_name in test_fields:
        print(f"\nTesting field: {field_name}")
        
        try:
            # Make the API call
            url = f"{API_BASE_URL}/findings/typosquat/distinct/{field_name}"
            response = requests.post(url, json={"filter": {}})
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ SUCCESS: {len(data)} distinct values found")
                results[field_name] = "SUCCESS"
            else:
                print(f"  ❌ FAILED: HTTP {response.status_code}")
                print(f"  Error: {response.text}")
                results[field_name] = f"FAILED: HTTP {response.status_code}"
                
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")
            results[field_name] = f"ERROR: {str(e)}"
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY:")
    print("="*50)
    
    success_count = 0
    for field_name, result in results.items():
        status = "✅" if "SUCCESS" in result else "❌"
        print(f"{status} {field_name}: {result}")
        if "SUCCESS" in result:
            success_count += 1
    
    print(f"\nTotal: {success_count}/{len(test_fields)} fields working correctly")
    
    if success_count == len(test_fields):
        print("🎉 All tests passed!")
        return True
    else:
        print("⚠️  Some tests failed!")
        return False

def test_with_program_filter():
    """Test distinct queries with program filter"""
    
    print("\n" + "="*50)
    print("Testing with program filter...")
    print("="*50)
    
    test_fields = [
        "info.whois.registrar",
        "info.geoip.country", 
        "info.http.status_code"
    ]
    
    for field_name in test_fields:
        print(f"\nTesting field: {field_name} with program filter")
        
        try:
            url = f"{API_BASE_URL}/findings/typosquat/distinct/{field_name}"
            filter_data = {"filter": {"program_name": TEST_PROGRAM}}
            response = requests.post(url, json=filter_data)
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ SUCCESS: {len(data)} distinct values found")
            else:
                print(f"  ❌ FAILED: HTTP {response.status_code}")
                print(f"  Error: {response.text}")
                
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")

if __name__ == "__main__":
    print("Typosquat Distinct Field Query Test")
    print("="*50)
    
    # Test basic functionality
    success = test_typosquat_distinct_fields()
    
    # Test with filters
    test_with_program_filter()
    
    if not success:
        sys.exit(1) 