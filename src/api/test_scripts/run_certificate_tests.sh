#!/usr/bin/env bash

# Certificate Routes Test Runner
# This script runs the certificate routes test suite

set -e

echo "🔐 Certificate Routes Test Runner"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "test_certificate_routes.py" ]; then
    echo "❌ Error: test_certificate_routes.py not found in current directory"
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

# Run the tests
echo ""
echo "🚀 Running Certificate Routes Tests..."
echo "======================================"

python3 test_certificate_routes.py

echo ""
echo "✅ Test execution completed" 