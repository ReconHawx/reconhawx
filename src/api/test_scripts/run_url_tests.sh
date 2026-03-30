#!/usr/bin/env bash

# URL Routes Test Runner
# This script runs the URL routes test suite

set -e

echo "🔗 URL Routes Test Runner"
echo "=========================="

# Check if test file exists
if [ ! -f "test_url_routes.py" ]; then
    echo "❌ Error: test_url_routes.py not found"
    echo "   Make sure you're in the correct directory (src/api/)"
    exit 1
fi

# Check if API server is running
echo "🔍 Checking API server health..."
if curl -s http://localhost:8001/ | grep -q "healthy"; then
    echo "✅ API server is running and healthy"
else
    echo "❌ API server is not responding"
    echo "   Please start the API server first:"
    echo "   kubectl port-forward svc/api 8001:8000"
    exit 1
fi

# Check if httpx is installed
echo "🔍 Checking dependencies..."
if python -c "import httpx" 2>/dev/null; then
    echo "✅ httpx is installed"
else
    echo "❌ httpx is not installed"
    echo "   Please install it: pip install httpx>=0.25.0"
    exit 1
fi

# Run the tests
echo ""
echo "🚀 Running URL routes tests..."
echo "================================"

python test_url_routes.py

echo ""
echo "✅ URL tests completed!" 