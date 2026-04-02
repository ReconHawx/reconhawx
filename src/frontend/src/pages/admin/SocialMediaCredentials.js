import React, { useState, useEffect, useCallback } from 'react';
import { Container, Card, Table, Button, Modal, Form, Alert, Spinner, Badge, Row, Col } from 'react-bootstrap';
import { socialMediaCredentialsAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function SocialMediaCredentials() {
  usePageTitle(formatPageTitle('Social Media Credentials'));
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [selectedCredential, setSelectedCredential] = useState(null);
  const [platformFilter, setPlatformFilter] = useState('');
  
  const [formData, setFormData] = useState({
    name: '',
    platform: 'facebook',
    username: '',
    email: '',
    password: '',
    is_active: true
  });

  const fetchCredentials = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await socialMediaCredentialsAPI.list(platformFilter || null);
      setCredentials(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch credentials');
      console.error('Error fetching credentials:', err);
    } finally {
      setLoading(false);
    }
  }, [platformFilter]);

  useEffect(() => {
    fetchCredentials();
  }, [fetchCredentials]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      await socialMediaCredentialsAPI.create(formData);
      setSuccess('Credential created successfully');
      setShowCreateModal(false);
      resetForm();
      fetchCredentials();
    } catch (err) {
      setError(err.message || 'Failed to create credential');
    }
  };

  const handleEdit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      await socialMediaCredentialsAPI.update(selectedCredential.id, formData);
      setSuccess('Credential updated successfully');
      setShowEditModal(false);
      resetForm();
      setSelectedCredential(null);
      fetchCredentials();
    } catch (err) {
      setError(err.message || 'Failed to update credential');
    }
  };

  const handleDelete = async () => {
    setError(null);
    setSuccess(null);
    try {
      await socialMediaCredentialsAPI.delete(selectedCredential.id);
      setSuccess('Credential deleted successfully');
      setShowDeleteModal(false);
      setSelectedCredential(null);
      fetchCredentials();
    } catch (err) {
      setError(err.message || 'Failed to delete credential');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      platform: 'facebook',
      username: '',
      email: '',
      password: '',
      is_active: true
    });
  };

  const openEditModal = (credential) => {
    setSelectedCredential(credential);
    setFormData({
      name: credential.name,
      platform: credential.platform,
      username: credential.username || '',
      email: credential.email || '',
      password: '', // Don't populate password
      is_active: credential.is_active
    });
    setShowEditModal(true);
  };

  const openDeleteModal = (credential) => {
    setSelectedCredential(credential);
    setShowDeleteModal(true);
  };

  const getPlatformBadgeVariant = (platform) => {
    switch (platform?.toLowerCase()) {
      case 'facebook': return 'primary';
      case 'instagram': return 'danger';
      case 'twitter':
      case 'x': return 'info';
      case 'linkedin': return 'primary';
      default: return 'secondary';
    }
  };

  if (loading) {
    return (
      <Container fluid className="mt-4">
        <div className="text-center">
          <Spinner animation="border" />
          <p className="mt-2">Loading credentials...</p>
        </div>
      </Container>
    );
  }

  return (
    <Container fluid className="mt-4">
      <Card>
        <Card.Header>
          <Row className="align-items-center">
            <Col>
              <h4>Social Media Credentials</h4>
            </Col>
            <Col xs="auto">
              <Button variant="primary" onClick={() => { resetForm(); setShowCreateModal(true); }}>
                Create Credential
              </Button>
            </Col>
          </Row>
        </Card.Header>
        <Card.Body>
          {error && <Alert variant="danger" onClose={() => setError(null)} dismissible>{error}</Alert>}
          {success && <Alert variant="success" onClose={() => setSuccess(null)} dismissible>{success}</Alert>}
          
          {/* Platform Filter */}
          <Row className="mb-3">
            <Col md={3}>
              <Form.Group>
                <Form.Label>Filter by Platform</Form.Label>
                <Form.Select
                  value={platformFilter}
                  onChange={(e) => setPlatformFilter(e.target.value)}
                >
                  <option value="">All Platforms</option>
                  <option value="facebook">Facebook</option>
                  <option value="instagram">Instagram</option>
                  <option value="twitter">Twitter</option>
                  <option value="linkedin">LinkedIn</option>
                </Form.Select>
              </Form.Group>
            </Col>
          </Row>

          {/* Credentials Table */}
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>Name</th>
                <th>Platform</th>
                <th>Username</th>
                <th>Email</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {credentials.length === 0 ? (
                <tr>
                  <td colSpan="6" className="text-center">No credentials found</td>
                </tr>
              ) : (
                credentials.map((cred) => (
                  <tr key={cred.id}>
                    <td>{cred.name}</td>
                    <td>
                      <Badge bg={getPlatformBadgeVariant(cred.platform)}>
                        {cred.platform}
                      </Badge>
                    </td>
                    <td>{cred.username || '-'}</td>
                    <td>{cred.email || '-'}</td>
                    <td>
                      <Badge bg={cred.is_active ? 'success' : 'secondary'}>
                        {cred.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td>
                      <Button
                        variant="outline-primary"
                        size="sm"
                        className="me-2"
                        onClick={() => openEditModal(cred)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="outline-danger"
                        size="sm"
                        onClick={() => openDeleteModal(cred)}
                      >
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>
        </Card.Body>
      </Card>

      {/* Create Modal */}
      <Modal show={showCreateModal} onHide={() => { setShowCreateModal(false); resetForm(); }}>
        <Modal.Header closeButton>
          <Modal.Title>Create Social Media Credential</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleCreate}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Name *</Form.Label>
              <Form.Control
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Platform *</Form.Label>
              <Form.Select
                value={formData.platform}
                onChange={(e) => setFormData({ ...formData, platform: e.target.value })}
                required
              >
                <option value="facebook">Facebook</option>
                <option value="instagram">Instagram</option>
                <option value="twitter">Twitter</option>
                <option value="linkedin">LinkedIn</option>
              </Form.Select>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Username</Form.Label>
              <Form.Control
                type="text"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Email</Form.Label>
              <Form.Control
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Password</Form.Label>
              <Form.Control
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Active"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              />
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => { setShowCreateModal(false); resetForm(); }}>
              Cancel
            </Button>
            <Button variant="primary" type="submit">
              Create
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal show={showEditModal} onHide={() => { setShowEditModal(false); resetForm(); setSelectedCredential(null); }}>
        <Modal.Header closeButton>
          <Modal.Title>Edit Social Media Credential</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleEdit}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Name *</Form.Label>
              <Form.Control
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Platform *</Form.Label>
              <Form.Select
                value={formData.platform}
                onChange={(e) => setFormData({ ...formData, platform: e.target.value })}
                required
              >
                <option value="facebook">Facebook</option>
                <option value="instagram">Instagram</option>
                <option value="twitter">Twitter</option>
                <option value="linkedin">LinkedIn</option>
              </Form.Select>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Username</Form.Label>
              <Form.Control
                type="text"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Email</Form.Label>
              <Form.Control
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Password (leave blank to keep current)</Form.Label>
              <Form.Control
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="Enter new password or leave blank"
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Active"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              />
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => { setShowEditModal(false); resetForm(); setSelectedCredential(null); }}>
              Cancel
            </Button>
            <Button variant="primary" type="submit">
              Update
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Delete Modal */}
      <Modal show={showDeleteModal} onHide={() => { setShowDeleteModal(false); setSelectedCredential(null); }}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Credential</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          Are you sure you want to delete the credential "{selectedCredential?.name}"? This action cannot be undone.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => { setShowDeleteModal(false); setSelectedCredential(null); }}>
            Cancel
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            Delete
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default SocialMediaCredentials;

