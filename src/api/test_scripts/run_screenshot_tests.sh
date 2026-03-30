#!/usr/bin/env bash

# Screenshot API Test Runner
# Tests the PostgreSQL-based screenshot functionality

set -e

echo "🚀 Screenshot API Test Runner"
echo "=============================="

# Check if we're in the right directory
if [ ! -f "test_screenshot_routes.py" ]; then
    echo "❌ Error: test_screenshot_routes.py not found in current directory"
    echo "   Please run this script from the src/api directory"
    exit 1
fi

# Check if API server is running
echo "🔍 Checking if API server is running..."
if ! curl -s http://localhost:8001/ > /dev/null 2>&1; then
    echo "❌ Error: API server is not running on http://localhost:8001"
    echo "   Please start the API server first:"
    echo "   cd src/api && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001"
    exit 1
fi
echo "✅ API server is running"

# Check if required Python packages are installed
echo "🔍 Checking Python dependencies..."
python3 -c "import httpx, PIL" 2>/dev/null || {
    echo "❌ Error: Missing required Python packages"
    echo "   Please install: pip install httpx pillow"
    exit 1
}
echo "✅ Python dependencies are available"

# Check if API endpoints are accessible
echo "🔍 Checking API endpoints..."
if ! curl -s http://localhost:8001/ > /dev/null 2>&1; then
    echo "❌ Error: API server is not responding"
    echo "   Please start the API server first:"
    echo "   cd src/api && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001"
    exit 1
fi
echo "✅ API server is responding"

# Note: Database initialization should be done separately if needed
echo "ℹ️  Note: Database tables should be initialized before running tests"
echo "   Run: python3 init_screenshot_db.py (if needed)"

# Run the tests
echo "🧪 Running screenshot API tests..."
echo "=============================="

python3 test_screenshot_routes.py

echo ""
echo "🎉 Screenshot tests completed!"
echo "==============================" 