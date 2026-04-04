#!/usr/bin/env python3
"""
Test script for PostgreSQL Session Monitor
Tests basic functionality without running the full monitor
"""

import os
import sys
from monitor_pg_sessions import PostgresMonitor

# Configuration - Update these values for your environment
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "password"),
    "database": os.getenv("DATABASE_NAME", "reconhawx")
}

def test_connection():
    """Test database connection"""
    print("🔍 Testing database connection...")
    
    monitor = PostgresMonitor(DB_CONFIG)
    conn = monitor.get_connection()
    
    if conn:
        print("✅ Database connection successful!")
        return True
    else:
        print("❌ Database connection failed!")
        return False

def test_session_counts():
    """Test session count retrieval"""
    print("📊 Testing session count retrieval...")
    
    monitor = PostgresMonitor(DB_CONFIG)
    counts = monitor.get_session_counts()
    
    if counts:
        print("✅ Session counts retrieved successfully!")
        print(f"   Active: {counts.get('active', 'N/A')}")
        print(f"   Idle: {counts.get('idle', 'N/A')}")
        print(f"   Idle in Transaction: {counts.get('idle_tx', 'N/A')}")
        print(f"   Total: {counts.get('total', 'N/A')}")
        return True
    else:
        print("❌ Failed to retrieve session counts!")
        return False

def test_pool_status():
    """Test connection pool status retrieval"""
    print("🔌 Testing connection pool status...")
    
    monitor = PostgresMonitor(DB_CONFIG)
    pool_status = monitor.get_connection_pool_status()
    
    if pool_status:
        print("✅ Pool status retrieved successfully!")
        print(f"   Max Connections: {pool_status.get('max_connections', 'N/A')}")
        print(f"   Current Connections: {pool_status.get('current_connections', 'N/A')}")
        print(f"   Available Connections: {pool_status.get('available_connections', 'N/A')}")
        return True
    else:
        print("❌ Failed to retrieve pool status!")
        return False

def test_active_queries():
    """Test active queries retrieval"""
    print("🔄 Testing active queries retrieval...")
    
    monitor = PostgresMonitor(DB_CONFIG)
    queries = monitor.get_active_queries(limit=5)
    
    if queries is not None:
        print("✅ Active queries retrieved successfully!")
        print(f"   Found {len(queries)} active queries")
        return True
    else:
        print("❌ Failed to retrieve active queries!")
        return False

def test_database_stats():
    """Test database statistics retrieval"""
    print("📈 Testing database statistics...")
    
    monitor = PostgresMonitor(DB_CONFIG)
    stats = monitor.get_database_stats()
    
    if stats:
        print("✅ Database stats retrieved successfully!")
        print(f"   Database: {stats.get('datname', 'N/A')}")
        print(f"   Active Connections: {stats.get('active_connections', 'N/A')}")
        print(f"   Transactions Committed: {stats.get('transactions_committed', 'N/A')}")
        return True
    else:
        print("❌ Failed to retrieve database stats!")
        return False

def main():
    """Run all tests"""
    print("🧪 PostgreSQL Session Monitor - Test Suite")
    print("=" * 50)
    
    tests = [
        ("Database Connection", test_connection),
        ("Session Counts", test_session_counts),
        ("Connection Pool Status", test_pool_status),
        ("Active Queries", test_active_queries),
        ("Database Statistics", test_database_stats)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        print("-" * 30)
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"💥 {test_name}: ERROR - {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Monitor is ready to use.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
