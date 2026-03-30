import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Button, 
  Modal, 
  Form, 
  Alert, 
  Table, 
  Badge,
  InputGroup,
  Spinner
} from 'react-bootstrap';
import { authAPI } from '../services/api';
import { formatDate, isExpired } from '../utils/dateUtils';

function ApiTokenManagement() {
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [newToken, setNewToken] = useState('');
  
  const [createForm, setCreateForm] = useState({
    name: '',
    description: '',
    expires_in_days: 90,
    permissions: []
  });

  const availablePermissions = [
    { value: 'read:assets', label: 'Read Assets' },
    { value: 'read:findings', label: 'Read Findings' },
    { value: 'read:programs', label: 'Read Programs' },
    { value: 'read:workflows', label: 'Read Workflows' },
    { value: 'write:workflows', label: 'Execute Workflows' }
  ];

  useEffect(() => {
    loadTokens();
  }, []);

  const loadTokens = async () => {
    try {
      setLoading(true);
      setError('');
      
      const response = await authAPI.getApiTokens();
      setTokens(response.tokens || []);
    } catch (err) {
      setError('Failed to load API tokens: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateToken = async (e) => {
    e.preventDefault();
    
    if (!createForm.name) {
      setError('Token name is required');
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      setNewToken('');
      
      const data = await authAPI.createApiToken(createForm);
      setNewToken(data.token);
      setSuccess('API token created successfully! Make sure to copy it now - you won\'t be able to see it again.');
      setCreateForm({
        name: '',
        description: '',
        expires_in_days: 90,
        permissions: []
      });
      loadTokens();
    } catch (err) {
      setError('Failed to create API token: ' + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRevokeToken = async (tokenId) => {
    if (!window.confirm('Are you sure you want to revoke this API token? This action cannot be undone.')) {
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      
      await authAPI.revokeApiToken(tokenId);

      setSuccess('API token revoked successfully');
      loadTokens();
    } catch (err) {
      setError('Failed to revoke API token: ' + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      setSuccess('Token copied to clipboard!');
    }).catch(() => {
      setError('Failed to copy token to clipboard');
    });
  };

  const formatTokenDate = (dateString) => {
    return formatDate(dateString, 'MMM dd, yyyy');
  };

  const isTokenExpired = (expiresAt) => {
    return isExpired(expiresAt);
  };

  const getTokenStatusBadge = (token) => {
    if (isTokenExpired(token.expires_at)) {
      return <Badge bg="danger">Expired</Badge>;
    }
    if (token.is_active) {
      return <Badge bg="success">Active</Badge>;
    }
    return <Badge bg="secondary">Inactive</Badge>;
  };

  return (
    <Card>
      <Card.Header className="d-flex justify-content-between align-items-center">
        <h5>🔑 API Tokens</h5>
        <Button 
          variant="primary" 
          size="sm"
          onClick={() => setShowCreateModal(true)}
          disabled={actionLoading}
        >
          ➕ Generate Token
        </Button>
      </Card.Header>
      
      <Card.Body>
        {error && (
          <Alert variant="danger" onClose={() => setError('')} dismissible>
            {error}
          </Alert>
        )}
        
        {success && (
          <Alert variant="success" onClose={() => setSuccess('')} dismissible>
            {success}
          </Alert>
        )}

        {newToken && (
          <Alert variant="info">
            <h6>Your new API token:</h6>
            <InputGroup>
              <Form.Control
                type="text"
                value={newToken}
                readOnly
                className="font-monospace"
              />
              <Button 
                variant="outline-secondary"
                onClick={() => copyToClipboard(newToken)}
              >
                📋 Copy
              </Button>
            </InputGroup>
            <small className="text-muted">
              <strong>Important:</strong> This token will not be shown again. Make sure to save it securely.
            </small>
          </Alert>
        )}

        <div className="mb-3">
          <p className="text-muted mb-2">
            API tokens allow you to authenticate with the reconnaissance platform APIs directly. 
            Use these tokens in the Authorization header: <code>Bearer &lt;your-token&gt;</code>
          </p>
          
          <h6>Available API Endpoints:</h6>
          <ul className="list-unstyled small text-muted">
            <li><code>POST /api/assets/domain/query</code> - Query domains</li>
            <li><code>POST /api/assets/ip/query</code> - Query IP addresses</li>
            <li><code>POST /api/assets/url/query</code> - Query URLs</li>
            <li><code>POST /api/assets/service/query</code> - Query services</li>
            <li><code>POST /api/findings/nuclei/query</code> - Query Nuclei findings</li>
            <li><code>POST /api/workflows/run</code> - Execute workflows (requires permission)</li>
          </ul>
        </div>

        {loading ? (
          <div className="text-center py-4">
            <Spinner animation="border" role="status">
              <span className="visually-hidden">Loading...</span>
            </Spinner>
          </div>
        ) : tokens.length === 0 ? (
          <div className="text-center py-4 text-muted">
            <p>No API tokens found. Generate your first token to get started.</p>
          </div>
        ) : (
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Status</th>
                <th>Permissions</th>
                <th>Created</th>
                <th>Expires</th>
                <th>Last Used</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((token) => (
                <tr key={token.id}>
                  <td><strong>{token.name}</strong></td>
                  <td>{token.description || '-'}</td>
                  <td>{getTokenStatusBadge(token)}</td>
                  <td>
                    {token.permissions && token.permissions.length > 0 ? (
                      <div>
                        {token.permissions.map((perm, idx) => (
                          <Badge key={idx} bg="secondary" className="me-1 mb-1">
                            {perm}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <Badge bg="secondary">No specific permissions</Badge>
                    )}
                  </td>
                  <td>{formatTokenDate(token.created_at)}</td>
                  <td>
                    <span className={isTokenExpired(token.expires_at) ? 'text-danger' : ''}>
                      {formatTokenDate(token.expires_at)}
                    </span>
                  </td>
                  <td>
                    {token.last_used_at ? formatTokenDate(token.last_used_at) : 'Never'}
                  </td>
                  <td>
                    <Button
                      variant="outline-danger"
                      size="sm"
                      onClick={() => handleRevokeToken(token.id)}
                      disabled={actionLoading}
                    >
                      🗑️ Revoke
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card.Body>

      {/* Create Token Modal */}
      <Modal show={showCreateModal} onHide={() => setShowCreateModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Generate New API Token</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleCreateToken}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Token Name *</Form.Label>
              <Form.Control
                type="text"
                value={createForm.name}
                onChange={(e) => setCreateForm({...createForm, name: e.target.value})}
                placeholder="e.g., My Integration Token"
                required
              />
              <Form.Text className="text-muted">
                A descriptive name to help you identify this token
              </Form.Text>
            </Form.Group>
            
            <Form.Group className="mb-3">
              <Form.Label>Description</Form.Label>
              <Form.Control
                as="textarea"
                rows={2}
                value={createForm.description}
                onChange={(e) => setCreateForm({...createForm, description: e.target.value})}
                placeholder="Optional description of what this token will be used for"
              />
            </Form.Group>
            
            <Form.Group className="mb-3">
              <Form.Label>Expires In</Form.Label>
              <Form.Select
                value={createForm.expires_in_days}
                onChange={(e) => setCreateForm({...createForm, expires_in_days: parseInt(e.target.value)})}
              >
                <option value={30}>30 days</option>
                <option value={90}>90 days</option>
                <option value={180}>6 months</option>
                <option value={365}>1 year</option>
              </Form.Select>
            </Form.Group>
            
            <Form.Group className="mb-3">
              <Form.Label>Permissions</Form.Label>
              <div>
                {availablePermissions.map((permission) => (
                  <Form.Check
                    key={permission.value}
                    type="checkbox"
                    label={permission.label}
                    checked={createForm.permissions.includes(permission.value)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setCreateForm({
                          ...createForm,
                          permissions: [...createForm.permissions, permission.value]
                        });
                      } else {
                        setCreateForm({
                          ...createForm,
                          permissions: createForm.permissions.filter(p => p !== permission.value)
                        });
                      }
                    }}
                  />
                ))}
              </div>
              <Form.Text className="text-muted">
                Select the specific permissions this token should have. If none are selected, 
                the token will inherit your user permissions.
              </Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? 'Generating...' : 'Generate Token'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </Card>
  );
}

export default ApiTokenManagement;