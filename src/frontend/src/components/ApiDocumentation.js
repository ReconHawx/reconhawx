import React, { useState } from 'react';
import { Card, Button, Collapse, Alert, Badge } from 'react-bootstrap';

function ApiDocumentation() {
  const [showExamples, setShowExamples] = useState(false);

  const codeExamples = {
    curl: {
      queryDomains: `curl -X POST "https://recon-platform.com/api/assets/domain/query" \\
  -H "Authorization: Bearer YOUR_API_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "filter": {
      "program_name": "example-program"
    },
    "limit": 25,
    "page": 1,
    "sort": {
      "updated_at": -1
    }
  }'`,
      
      queryFindings: `curl -X POST "https://recon-platform.com/api/findings/nuclei/query" \\
  -H "Authorization: Bearer YOUR_API_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "filter": {
      "program_name": "example-program",
      "status": "new"
    },
    "limit": 50,
    "page": 1
  }'`,
      
      runWorkflow: `curl -X POST "https://recon-platform.com/api/workflows/run" \\
  -H "Authorization: Bearer YOUR_API_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "workflow_name": "subdomain-scan",
    "program_name": "example-program",
    "steps": [
      {
        "name": "resolve_domain",
        "type": "resolve_domain",
        "input": "example.com"
      }
    ]
  }'`
    },
    
    python: `import requests
import json

# Set up your API token
API_TOKEN = "YOUR_API_TOKEN"
BASE_URL = "https://recon-platform.com/api"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# Query domains
def query_domains(program_name=None, limit=25):
    payload = {
        "filter": {"program_name": program_name} if program_name else {},
        "limit": limit,
        "page": 1,
        "sort": {"updated_at": -1}
    }
    
    response = requests.post(
        f"{BASE_URL}/assets/domain/query",
        headers=headers,
        json=payload
    )
    
    return response.json()

# Query findings
def query_nuclei_findings(program_name=None, status=None):
    filter_obj = {}
    if program_name:
        filter_obj["program_name"] = program_name
    if status:
        filter_obj["status"] = status
    
    payload = {
        "filter": filter_obj,
        "limit": 50,
        "page": 1
    }
    
    response = requests.post(
        f"{BASE_URL}/findings/nuclei/query",
        headers=headers,
        json=payload
    )
    
    return response.json()

# Example usage
domains = query_domains("example-program")
findings = query_nuclei_findings("example-program", "new")`,

    javascript: `// Using fetch API
const API_TOKEN = 'YOUR_API_TOKEN';
const BASE_URL = 'https://recon-platform.com/api';

const headers = {
    'Authorization': \`Bearer \${API_TOKEN}\`,
    'Content-Type': 'application/json'
};

// Query domains
async function queryDomains(programName = null, limit = 25) {
    const payload = {
        filter: programName ? { program_name: programName } : {},
        limit: limit,
        page: 1,
        sort: { updated_at: -1 }
    };
    
    const response = await fetch(\`\${BASE_URL}/assets/domain/query\`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload)
    });
    
    return await response.json();
}

// Query findings
async function queryNucleiFindings(programName = null, status = null) {
    const filter = {};
    if (programName) filter.program_name = programName;
    if (status) filter.status = status;
    
    const payload = {
        filter: filter,
        limit: 50,
        page: 1
    };
    
    const response = await fetch(\`\${BASE_URL}/findings/nuclei/query\`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload)
    });
    
    return await response.json();
}

// Example usage
queryDomains('example-program').then(data => console.log(data));
queryNucleiFindings('example-program', 'new').then(data => console.log(data));`
  };

  const endpoints = [
    { method: 'POST', path: '/api/assets/domain/query', description: 'Query domains with filters', permission: 'read:assets' },
    { method: 'POST', path: '/api/assets/ip/query', description: 'Query IP addresses with filters', permission: 'read:assets' },
    { method: 'POST', path: '/api/assets/url/query', description: 'Query URLs with filters', permission: 'read:assets' },
    { method: 'POST', path: '/api/assets/service/query', description: 'Query services with filters', permission: 'read:assets' },
    { method: 'POST', path: '/api/assets/certificate/query', description: 'Query certificates with filters', permission: 'read:assets' },
    { method: 'POST', path: '/api/findings/nuclei/query', description: 'Query Nuclei findings with filters', permission: 'read:findings' },
    { method: 'POST', path: '/api/findings/typosquat/query', description: 'Query typosquat findings with filters', permission: 'read:findings' },
    { method: 'GET', path: '/api/programs', description: 'List all programs', permission: 'read:programs' },
    { method: 'POST', path: '/api/workflows/run', description: 'Execute a workflow', permission: 'write:workflows' },
    { method: 'GET', path: '/api/workflows/status', description: 'Get workflow execution status', permission: 'read:workflows' }
  ];

  return (
    <Card className="mt-3">
      <Card.Header className="d-flex justify-content-between align-items-center">
        <h6>📖 API Documentation</h6>
        <Button 
          variant="outline-primary" 
          size="sm"
          onClick={() => setShowExamples(!showExamples)}
        >
          {showExamples ? 'Hide' : 'Show'} Examples
        </Button>
      </Card.Header>
      
      <Collapse in={showExamples}>
        <Card.Body>
          <Alert variant="info">
            <h6>Authentication</h6>
            <p>Include your API token in the Authorization header:</p>
            <code>Authorization: Bearer YOUR_API_TOKEN</code>
          </Alert>

          <h6>Available Endpoints</h6>
          <div className="table-responsive mb-4">
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Endpoint</th>
                  <th>Description</th>
                  <th>Permission</th>
                </tr>
              </thead>
              <tbody>
                {endpoints.map((endpoint, idx) => (
                  <tr key={idx}>
                    <td>
                      <Badge bg={endpoint.method === 'GET' ? 'success' : 'primary'}>
                        {endpoint.method}
                      </Badge>
                    </td>
                    <td><code>{endpoint.path}</code></td>
                    <td>{endpoint.description}</td>
                    <td>
                      <Badge bg="secondary" className="small">
                        {endpoint.permission}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h6>Example: Query Domains with cURL</h6>
          <pre className="bg-light p-3 rounded">
            <code>{codeExamples.curl.queryDomains}</code>
          </pre>

          <h6>Example: Query Nuclei Findings with cURL</h6>
          <pre className="bg-light p-3 rounded">
            <code>{codeExamples.curl.queryFindings}</code>
          </pre>

          <h6>Example: Python Script</h6>
          <pre className="bg-light p-3 rounded">
            <code>{codeExamples.python}</code>
          </pre>

          <h6>Example: JavaScript/Node.js</h6>
          <pre className="bg-light p-3 rounded">
            <code>{codeExamples.javascript}</code>
          </pre>

          <Alert variant="warning">
            <h6>Rate Limiting</h6>
            <p>API requests are limited to 1000 requests per hour per token. Monitor your usage to avoid hitting rate limits.</p>
          </Alert>

          <Alert variant="info">
            <h6>Response Format</h6>
            <p>All API responses follow this format:</p>
            <pre className="mb-0">
{`{
  "status": "success",
  "items": [...],
  "total": 123,
  "page": 1,
  "limit": 25
}`}
            </pre>
          </Alert>
        </Card.Body>
      </Collapse>
    </Card>
  );
}

export default ApiDocumentation;