import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Container, Card, Badge, Row, Col, Button, Alert, Spinner, Table, Modal } from 'react-bootstrap';
import { brokenLinksAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';

function BrokenLinkDetail() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const findingId = searchParams.get('id');
  
  const [finding, setFinding] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [updateSuccess, setUpdateSuccess] = useState(false);

  const fetchFinding = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await brokenLinksAPI.getById(findingId);
      setFinding(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch broken link finding');
      console.error('Error fetching broken link:', err);
    } finally {
      setLoading(false);
    }
  }, [findingId]);

  useEffect(() => {
    if (findingId) {
      fetchFinding();
    } else {
      setError('No finding ID provided');
      setLoading(false);
    }
  }, [findingId, fetchFinding]);

  const handleUpdateNotes = async (notes) => {
    setUpdating(true);
    setUpdateSuccess(false);
    try {
      await brokenLinksAPI.update(findingId, { notes });
      await fetchFinding();
      setUpdateSuccess(true);
      setTimeout(() => setUpdateSuccess(false), 3000);
    } catch (err) {
      setError(err.message || 'Failed to update notes');
    } finally {
      setUpdating(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await brokenLinksAPI.delete(findingId);
      navigate('/findings/broken-links');
    } catch (err) {
      setError(err.message || 'Failed to delete finding');
      setDeleting(false);
      setShowDeleteModal(false);
    }
  };

  const getLinkTypeBadgeVariant = (linkType) => {
    switch (linkType?.toLowerCase()) {
      case 'social_media': return 'primary';
      case 'general': return 'secondary';
      default: return 'secondary';
    }
  };

  const getStatusBadgeVariant = (status) => {
    switch (status) {
      case 'valid': return 'success';
      case 'broken': return 'danger';
      case 'error': return 'warning';
      case 'throttled': return 'info';
      default: return 'secondary';
    }
  };

  const getMediaTypeBadgeVariant = (mediaType) => {
    switch (mediaType?.toLowerCase()) {
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
          <p className="mt-2">Loading broken link details...</p>
        </div>
      </Container>
    );
  }

  if (error && !finding) {
    return (
      <Container fluid className="mt-4">
        <Alert variant="danger">{error}</Alert>
        <Button onClick={() => navigate('/findings/broken-links')}>Back to Broken Links</Button>
      </Container>
    );
  }

  if (!finding) {
    return (
      <Container fluid className="mt-4">
        <Alert variant="warning">Broken link finding not found</Alert>
        <Button onClick={() => navigate('/findings/broken-links')}>Back to Broken Links</Button>
      </Container>
    );
  }

  return (
    <Container fluid className="mt-4">
      <Card>
        <Card.Header>
          <Row className="align-items-center">
            <Col>
              <h4>Broken Link Details</h4>
            </Col>
            <Col xs="auto">
              <Button variant="outline-secondary" onClick={() => navigate('/findings/broken-links')}>
                Back to List
              </Button>
              <Button
                variant="danger"
                className="ms-2"
                onClick={() => setShowDeleteModal(true)}
              >
                Delete
              </Button>
            </Col>
          </Row>
        </Card.Header>
        <Card.Body>
          {error && <Alert variant="danger">{error}</Alert>}
          {updateSuccess && <Alert variant="success">Notes updated successfully</Alert>}
          
          <Row className="mb-3">
            <Col md={6}>
              <Card>
                <Card.Header>Basic Information</Card.Header>
                <Card.Body>
                  <Table borderless>
                    <tbody>
                      <tr>
                        <td><strong>Link Type:</strong></td>
                        <td>
                          <Badge bg={getLinkTypeBadgeVariant(finding.link_type)}>
                            {finding.link_type === 'social_media' ? 'Social Media' : 'General'}
                          </Badge>
                        </td>
                      </tr>
                      {finding.link_type === 'social_media' && (
                        <tr>
                          <td><strong>Media Type:</strong></td>
                          <td>
                            {finding.media_type && (
                              <Badge bg={getMediaTypeBadgeVariant(finding.media_type)}>
                                {finding.media_type}
                              </Badge>
                            )}
                          </td>
                        </tr>
                      )}
                      {finding.link_type === 'general' && (
                        <>
                          <tr>
                            <td><strong>Domain:</strong></td>
                            <td>{finding.domain || '-'}</td>
                          </tr>
                          <tr>
                            <td><strong>Reason:</strong></td>
                            <td>{finding.reason || '-'}</td>
                          </tr>
                        </>
                      )}
                      <tr>
                        <td><strong>Status:</strong></td>
                        <td>
                          <Badge bg={getStatusBadgeVariant(finding.status)}>
                            {finding.status}
                          </Badge>
                        </td>
                      </tr>
                      <tr>
                        <td><strong>URL:</strong></td>
                        <td>
                          {finding.url ? (
                            <a href={finding.url} target="_blank" rel="noopener noreferrer">
                              {finding.url}
                            </a>
                          ) : (
                            '-'
                          )}
                        </td>
                      </tr>
                      <tr>
                        <td><strong>Error Code:</strong></td>
                        <td>{finding.error_code || '-'}</td>
                      </tr>
                      <tr>
                        <td><strong>Checked At:</strong></td>
                        <td>{finding.checked_at ? formatDate(finding.checked_at) : '-'}</td>
                      </tr>
                      <tr>
                        <td><strong>Program:</strong></td>
                        <td>{finding.program_name || '-'}</td>
                      </tr>
                      <tr>
                        <td><strong>Created At:</strong></td>
                        <td>{finding.created_at ? formatDate(finding.created_at) : '-'}</td>
                      </tr>
                      <tr>
                        <td><strong>Updated At:</strong></td>
                        <td>{finding.updated_at ? formatDate(finding.updated_at) : '-'}</td>
                      </tr>
                    </tbody>
                  </Table>
                </Card.Body>
              </Card>
            </Col>
            <Col md={6}>
              {finding.response_data && (
                <Card className="mb-3">
                  <Card.Header>Response Data</Card.Header>
                  <Card.Body>
                    <pre style={{ maxHeight: '400px', overflow: 'auto', backgroundColor: '#f5f5f5', padding: '10px' }}>
                      {JSON.stringify(finding.response_data, null, 2)}
                    </pre>
                  </Card.Body>
                </Card>
              )}
            </Col>
          </Row>

          <Row>
            <Col>
              <NotesSection
                notes={finding.notes || ''}
                onUpdate={handleUpdateNotes}
                updating={updating}
                entityType="broken link"
              />
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Broken Link Finding</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          Are you sure you want to delete this broken link finding? This action cannot be undone.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={handleDelete} disabled={deleting}>
            {deleting ? 'Deleting...' : 'Delete'}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default BrokenLinkDetail;

