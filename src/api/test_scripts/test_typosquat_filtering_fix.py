#!/usr/bin/env python3
"""
Test script to verify that typosquat filtering works correctly
with various MongoDB-style filters converted to PostgreSQL.
"""

import requests
import sys

# Configuration
API_BASE_URL = "http://localhost:8001"
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInVzZXJfaWQiOiI1MTQ0MWE5MC01YWQxLTQ5Y2YtYjZmMy05YTI1OGJjYzhmNTQiLCJleHAiOjE3NTQ0ODYyMTZ9.KvdMdQ9wBCOJJQotzs0thxwmWR9VJvLsLQSZ0ZtcIKg"

def test_typosquat_filtering():
    """Test various typosquat filtering scenarios"""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    print("Testing typosquat filtering fixes...")
    
    # Test cases
    test_cases = [
        {
            "name": "Simple typo_domain regex",
            "filter": {"typo_domain": {"$regex": "des", "$options": "i"}},
            "expected_success": True
        },
        {
            "name": "Registrar regex filter",
            "filter": {"info.whois.registrar": {"$regex": "GoDaddy", "$options": "i"}},
            "expected_success": True
        },
        {
            "name": "IP address OR filter",
            "filter": {
                "$or": [
                    {"info.ip": {"$regex": "192", "$options": "i"}},
                    {"info.dns_a": {"$regex": "192", "$options": "i"}}
                ]
            },
            "expected_success": True
        },
        {
            "name": "Risk score range filter",
            "filter": {
                "info.risk_score": {
                    "$gte": 50,
                    "$lte": 100
                }
            },
            "expected_success": True
        },
        {
            "name": "Status not equal filter",
            "filter": {"status": {"$ne": "false_positive"}},
            "expected_success": True
        },
        {
            "name": "Complex combined filter",
            "filter": {
                "$and": [
                    {"typo_domain": {"$regex": "des", "$options": "i"}},
                    {"info.whois.registrar": {"$regex": "GoDaddy", "$options": "i"}}
                ]
            },
            "expected_success": True
        }
    ]
    
    results = {}
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        
        try:
            payload = {
                "filter": test_case["filter"],
                "limit": 5,
                "skip": 0
            }
            
            response = requests.post(
                f"{API_BASE_URL}/findings/typosquat/query",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                item_count = len(data.get('items', []))
                print(f"  ✅ SUCCESS: {item_count} results returned")
                results[test_case['name']] = "SUCCESS"
            else:
                print(f"  ❌ FAILED: HTTP {response.status_code}")
                print(f"  Error: {response.text}")
                results[test_case['name']] = f"FAILED: HTTP {response.status_code}"
                
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")
            results[test_case['name']] = f"ERROR: {str(e)}"
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY:")
    print("="*60)
    
    success_count = 0
    for test_name, result in results.items():
        status = "✅" if "SUCCESS" in result else "❌"
        print(f"{status} {test_name}: {result}")
        if "SUCCESS" in result:
            success_count += 1
    
    print(f"\nTotal: {success_count}/{len(test_cases)} tests passed")
    
    if success_count == len(test_cases):
        print("🎉 All filtering tests passed!")
        return True
    else:
        print("⚠️  Some filtering tests failed!")
        return False

if __name__ == "__main__":
    print("Typosquat Filtering Fix Test")
    print("="*60)
    
    success = test_typosquat_filtering()
    
    if not success:
        sys.exit(1) 