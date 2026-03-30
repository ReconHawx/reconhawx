#!/usr/bin/env bash

# Test script for Nuclei Template API routes
# Tests the PostgreSQL-based nuclei template endpoints

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8001}"
TEST_SCRIPT="test_nuclei_template_routes.py"

echo -e "${BLUE}🧪 Nuclei Template API Tests${NC}"
echo -e "${BLUE}========================${NC}"
echo ""

# Check if API is running
echo -e "${YELLOW}🔍 Checking if API is running at ${API_BASE_URL}...${NC}"
if ! curl -s --max-time 5 "${API_BASE_URL}/health" > /dev/null 2>&1; then
    echo -e "${RED}❌ API is not running at ${API_BASE_URL}${NC}"
    echo -e "${YELLOW}💡 Make sure the API is running with:${NC}"
    echo "   kubectl port-forward svc/api 8001:8000"
    echo "   or"
    echo "   cd src/api && python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"
    exit 1
fi
echo -e "${GREEN}✅ API is running${NC}"
echo ""

# Check if test script exists
if [ ! -f "$TEST_SCRIPT" ]; then
    echo -e "${RED}❌ Test script not found: $TEST_SCRIPT${NC}"
    exit 1
fi

# Check if required Python packages are installed
echo -e "${YELLOW}🔍 Checking Python dependencies...${NC}"
python3 -c "import aiohttp, asyncio" 2>/dev/null || {
    echo -e "${RED}❌ Missing required Python packages${NC}"
    echo -e "${YELLOW}💡 Install with: pip install aiohttp${NC}"
    exit 1
}
echo -e "${GREEN}✅ Python dependencies available${NC}"
echo ""

# Set environment variables for testing
export API_BASE_URL="$API_BASE_URL"

# Run the tests
echo -e "${YELLOW}🚀 Running Nuclei Template API tests...${NC}"
echo ""

if python3 "$TEST_SCRIPT"; then
    echo ""
    echo -e "${GREEN}🎉 All Nuclei Template tests passed!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}💥 Some Nuclei Template tests failed!${NC}"
    exit 1
fi 