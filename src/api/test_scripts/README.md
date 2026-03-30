# API Test Scripts

This directory contains test scripts for the Recon API endpoints. All test scripts now use a common program manager to create and clean up test programs automatically.

## Common Program Manager

The `common_program_manager.py` module provides a centralized way to create and manage test programs across all test scripts. It ensures that:

1. Each test script creates its own unique test program
2. Programs are created with proper scope patterns
3. Programs are automatically cleaned up after tests complete
4. Authentication is handled consistently

### Features

- **Automatic Program Creation**: Creates unique test programs with proper scope patterns
- **Automatic Cleanup**: Programs are deleted after tests complete (even if tests fail)
- **Authentication**: Handles login and token management
- **Context Manager**: Provides easy-to-use context manager for automatic cleanup
- **Flexible Scope**: Configurable domain regex patterns for program scope

### Usage

#### Using the Context Manager (Recommended)

```python
from common_program_manager import create_test_program

async def run_tests():
    async with create_test_program(scope_pattern=".*example\\.com") as program_name:
        # Use program_name in your tests
        await run_my_tests(program_name)
        # Program is automatically deleted when context exits
```

#### Using the TestProgramManager Class

```python
from common_program_manager import TestProgramManager

async def run_tests():
    async with TestProgramManager() as manager:
        program_name = await manager.create_test_program(scope_pattern=".*example\\.com")
        # Use program_name in your tests
        await run_my_tests(program_name)
        # Program is automatically deleted when context exits
```

## Test Scripts

### Certificate Routes Test (`test_certificate_routes.py`)

Tests certificate-related endpoints:
- Create certificates via receive_asset endpoint
- Get certificate by subject DN
- Get certificates by program
- Query certificates with filters
- Update certificate notes
- Delete certificates
- Verify operations

**Usage:**
```bash
cd src/api/test_scripts
python test_certificate_routes.py
```

### Nuclei Findings Routes Test (`test_nuclei_routes.py`)

Tests nuclei findings-related endpoints:
- Create nuclei findings
- Get nuclei finding by ID
- Get all nuclei findings
- Query nuclei findings with filters
- Get nuclei stats
- Get distinct field values
- Update nuclei status and notes
- Delete nuclei findings
- Verify operations

**Usage:**
```bash
cd src/api/test_scripts
python test_nuclei_routes.py
```

### Subdomain Routes Test (`test_subdomain_routes.py`)

Tests subdomain-related endpoints:
- Create subdomains via receive_asset endpoint
- Get subdomain by name
- Get program subdomains
- Query subdomains with filters
- Update subdomain notes
- Delete subdomains
- Verify operations

**Usage:**
```bash
cd src/api/test_scripts
python test_subdomain_routes.py
```

### URL Routes Test (`test_url_routes.py`)

Tests URL-related endpoints:
- Create URLs via receive_asset endpoint
- Get URL by URL string
- Get URLs by program
- Query URLs with filters
- Update URL notes
- Delete URLs
- Verify operations

**Usage:**
```bash
cd src/api/test_scripts
python test_url_routes.py
```

### Screenshot Routes Test (`test_screenshot_routes.py`)

Tests screenshot-related endpoints:
- Upload screenshots
- Check screenshot existence
- Get screenshots by file ID
- List screenshots with filters
- Get screenshot metadata
- Get screenshot duplicate stats
- Delete screenshots
- Verify operations

**Usage:**
```bash
cd src/api/test_scripts
python test_screenshot_routes.py
```

### Service Routes Test (`test_service_routes.py`)

Tests service-related endpoints:
- Create services via receive_asset endpoint
- Get service by IP and port
- Get services by program
- Query services with filters
- Update service notes
- Delete services
- Verify operations

**Usage:**
```bash
cd src/api/test_scripts
python test_service_routes.py
```

### Program Manager Test (`test_program_manager.py`)

Tests the common program manager functionality:
- Direct TestProgramManager usage
- Context manager usage
- Program creation and cleanup

**Usage:**
```bash
cd src/api/test_scripts
python test_program_manager.py
```

## Prerequisites

1. **API Server Running**: Ensure the API server is running on `http://localhost:8001`
2. **Database Setup**: Ensure the PostgreSQL database is properly configured
3. **Admin User**: Ensure an admin user exists with username "admin" and password "password"
4. **Dependencies**: Install required Python packages:
   ```bash
   pip install httpx asyncio
   ```

## Test Program Scope

All test scripts create programs with the scope pattern `.*example\.com`, which allows testing with domains like:
- `test-abc123.example.com`
- `api.example.com`
- `www.example.com`

## Program Cleanup

Programs are automatically deleted after tests complete, even if tests fail. This ensures:
- No leftover test data in the database
- Clean test environment for each run
- No conflicts between test runs

## Authentication

The common program manager handles authentication automatically:
1. Logs in with admin credentials
2. Stores the authentication token
3. Uses the token for program creation and deletion
4. Handles authentication errors gracefully

## Error Handling

All test scripts include comprehensive error handling:
- Detailed logging of all operations
- Clear success/failure indicators
- Graceful handling of API errors
- Automatic cleanup on failures

## Logging

All test scripts use structured logging with:
- Timestamps
- Log levels (INFO, ERROR, WARNING)
- Clear operation descriptions
- Success/failure indicators with emojis

## Example Output

```
🚀 Starting Certificate Routes Test Suite
============================================================
📋 Using test program: test-a1b2c3d4
📝 Test 1: Login
✅ Login successful for user: admin
📝 Test 2: Create Certificate
✅ Certificate creation successful
...
📊 Test Results Summary
============================================================
✅ PASS - Login
✅ PASS - Create Certificate
...
🎯 Overall Result: 9/9 tests passed
🎉 All tests passed! Certificate routes are working correctly.
```

## Troubleshooting

### Common Issues

1. **API Server Not Running**
   - Error: Connection refused
   - Solution: Start the API server with `./scripts/start_dev_minikube.sh`

2. **Authentication Failed**
   - Error: Login failed with status 401
   - Solution: Ensure admin user exists with correct credentials

3. **Database Connection Issues**
   - Error: Database connection failed
   - Solution: Check PostgreSQL configuration and ensure database is running

4. **Program Creation Failed**
   - Error: Program creation failed with status 409
   - Solution: Check if program name already exists (should be unique)

### Debug Mode

To enable debug logging, modify the logging configuration in any test script:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Contributing

When adding new test scripts:

1. Import the common program manager:
   ```python
   from common_program_manager import create_test_program
   ```

2. Use the context manager pattern:
   ```python
   async with create_test_program(scope_pattern=".*example\\.com") as program_name:
       # Your test code here
   ```

3. Follow the existing logging and error handling patterns
4. Ensure all tests clean up after themselves
5. Add comprehensive documentation for new test scripts 