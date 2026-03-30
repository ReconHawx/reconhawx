#!/usr/bin/env bash

# Test script for Domain Scope Validation
# Tests that domains are properly validated against program scope before creation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🚀 Starting Domain Scope Validation Tests${NC}"

# Check if API is running
echo -e "${YELLOW}Checking if API is running...${NC}"
if ! curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "${RED}❌ API is not running on http://localhost:8001${NC}"
    echo -e "${YELLOW}Please start the API first:${NC}"
    echo -e "  cd src/api && python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"
    exit 1
fi

echo -e "${GREEN}✅ API is running${NC}"

# Run the domain scope validation tests
echo -e "${YELLOW}Running domain scope validation tests...${NC}"
cd "$(dirname "$0")"

if python3 test_domain_scope_validation.py; then
    echo -e "${GREEN}✅ All Domain Scope Validation Tests Passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Domain Scope Validation Tests Failed!${NC}"
    exit 1
fi 