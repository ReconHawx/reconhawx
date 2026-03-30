#!/usr/bin/env bash

# Wordlist Routes Test Runner
# This script runs the wordlist routes test suite

set -e

echo "🔧 Wordlist Routes Test Runner"
echo "=============================="

# Check if we're in the right directory
if [ ! -f "test_wordlist_routes.py" ]; then
    echo "❌ Error: test_wordlist_routes.py not found in current directory"
    echo "   Please run this script from the src/api directory"
    exit 1
fi

# Check if API server is running
echo "🔍 Checking if API server is running..."
if ! curl -s http://localhost:8001/ | grep -q "healthy" 2>/dev/null; then
    echo "❌ Error: API server is not running on http://localhost:8001"
    echo ""
    echo "To start the API server:"
    echo "1. Make sure you're in the src/api directory"
    echo "2. Run: uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"
    echo ""
    echo "Or if using Docker/Kubernetes:"
    echo "1. Start your development environment"
    echo "2. Port forward the API service: kubectl port-forward svc/api 8001:8001"
    echo ""
    exit 1
fi

echo "✅ API server is running"

# Check if httpx is installed
echo "🔍 Checking dependencies..."
if ! python3 -c "import httpx" 2>/dev/null; then
    echo "❌ Error: httpx is not installed"
    echo "   Installing httpx..."
    pip install httpx>=0.25.0
fi

echo "✅ Dependencies are available"

# Check if PostgreSQL database is accessible
echo "🔍 Checking PostgreSQL database connection..."
if ! python3 -c "
import os
import sys
sys.path.insert(0, 'app')
from db_postgres import test_connection
try:
    test_connection()
    print('Database connection successful')
except Exception as e:
    print(f'Database connection failed: {e}')
    sys.exit(1)
" 2>/dev/null; then
    echo "❌ Error: Cannot connect to PostgreSQL database"
    echo ""
    echo "Please ensure:"
    echo "1. PostgreSQL is running"
    echo "2. Database credentials are correct in environment variables"
    echo "3. Database 'recon_db' exists"
    echo ""
    echo "Environment variables needed:"
    echo "- POSTGRES_USER"
    echo "- POSTGRES_PASSWORD" 
    echo "- POSTGRES_HOST"
    echo "- POSTGRES_PORT"
    echo "- POSTGRES_DB"
    echo ""
    exit 1
fi

echo "✅ Database connection successful"

# Run the tests
echo ""
echo "🚀 Running Wordlist Routes Tests..."
echo "==================================="

python3 test_wordlist_routes.py

echo ""
echo "✅ Test execution completed" 