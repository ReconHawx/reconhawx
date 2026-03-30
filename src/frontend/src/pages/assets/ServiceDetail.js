import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Table, Collapse, Modal } from 'react-bootstrap';
import { serviceAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';

function ServiceDetail() {
  const { ip, port } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [service, setService] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    json: false
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const fetchService = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        if (idParam) {
          const data = await serviceAPI.getById(idParam);
          setService(data);
        } else {
          const decodedIp = decodeURIComponent(ip || '');
          const decodedPort = decodeURIComponent(port || '');
          const response = await serviceAPI.getByIpPort(decodedIp, decodedPort);
          setService(response);
        }
        setError(null);
      } catch (err) {
        setError('Failed to fetch service details: ' + err.message);
        setService(null);
      } finally {
        setLoading(false);
      }
    };

    if ((ip && port) || new URLSearchParams(location.search).get('id')) {
      fetchService();
    }
  }, [ip, port, location.search]);

  const formatServiceDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const handleNotesUpdate = (newNotes) => {
    // Update the service object with new notes
    setService(prev => ({ ...prev, notes: newNotes }));
  };

  // Toggle expanded sections
  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // Copy to clipboard helpers
  const copyToClipboard = (text) => {
    if (text) navigator.clipboard.writeText(text);
  };

  const copyJsonToClipboard = () => {
    if (service) {
      navigator.clipboard.writeText(JSON.stringify(service, null, 2));
    }
  };

  // Delete service handlers
  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!service) return;
    
    try {
      setDeleting(true);
      await serviceAPI.delete(service.id || service._id);
      setShowDeleteModal(false);
      navigate('/assets/services');
    } catch (err) {
      setError('Failed to delete service: ' + err.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading service details...</p>
        </div>
      </Container>
    );
  }

  if (error) {
    return (
      <Container fluid className="p-4">
        <Alert variant="danger">
          <Alert.Heading>Error</Alert.Heading>
          {error}
        </Alert>
        <Button variant="outline-primary" onClick={() => navigate('/assets/services')}>
          ← Back to Services
        </Button>
      </Container>
    );
  }

  if (!service) {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>Service Not Found</Alert.Heading>
          The requested service could not be found.
        </Alert>
        <Button variant="outline-primary" onClick={() => navigate('/assets/services')}>
          ← Back to Services
        </Button>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <div>
              <h1>⚙️ {service.ip}:{service.port}</h1>
              <p className="text-muted">Service details and reconnaissance information</p>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={handleDeleteClick}
                className="me-2"
              >
                🗑️ Delete
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/assets/services')}>
                ← Back to Services
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={handleDeleteCancel} centered>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete Service</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this service?</p>
          <p><strong>Service:</strong> {service.ip}:{service.port}</p>
          <p className="text-danger">
            <strong>Warning:</strong> This action cannot be undone. The service will be permanently removed from the database.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={handleDeleteCancel} disabled={deleting}>
            Cancel
          </Button>
          <Button 
            variant="danger" 
            onClick={handleDeleteConfirm} 
            disabled={deleting}
          >
            {deleting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Deleting...
              </>
            ) : (
              'Delete Service'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      <Row>
        <Col>
          <Card className="mb-4">
            <Card.Header>
              <h5 className="mb-0">📋 Service Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>IP:Port:</strong></td>
                    <td>
                      <code>{service.ip}:{service.port}</code>
                      <Button variant="outline-secondary" size="sm" className="ms-2" onClick={() => copyToClipboard(`${service.ip}:${service.port}`)} title="Copy to clipboard">
                        📋
                      </Button>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>IP Address:</strong></td>
                    <td>
                      {service.ip_id ? (
                        <Link to={`/assets/ips/details?id=${service.ip_id}`}>{service.ip}</Link>
                      ) : (
                        <code>{service.ip}</code>
                      )}
                      <Button variant="outline-secondary" size="sm" className="ms-2" onClick={() => copyToClipboard(service.ip)} title="Copy to clipboard">
                        📋
                      </Button>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Port:</strong></td>
                    <td>
                      <code>{service.port}</code>
                      <Button variant="outline-secondary" size="sm" className="ms-2" onClick={() => copyToClipboard(String(service.port))} title="Copy to clipboard">
                        📋
                      </Button>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Protocol:</strong></td>
                    <td>
                      {service.protocol ? (
                        <Badge bg="info">{service.protocol.toUpperCase()}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Service Name:</strong></td>
                    <td>
                      {service.service_name ? (
                        <Badge bg="success">{service.service_name}</Badge>
                      ) : (
                        <span className="text-muted">Unknown</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Program:</strong></td>
                    <td>
                      {service.program_name ? (
                        <Badge bg="primary">{service.program_name}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td className="text-muted">{formatServiceDate(service.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Last Updated:</strong></td>
                    <td className="text-muted">{formatServiceDate(service.updated_at)}</td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {service.banner && (
        <Row>
          <Col>
            <Card className="mb-4">
              <Card.Header>
                <h5 className="mb-0">📄 Service Banner</h5>
              </Card.Header>
              <Card.Body>
                <pre className="bg-light p-3 rounded text-break">{service.banner}</pre>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {service.nerva_metadata && Object.keys(service.nerva_metadata).length > 0 && (
        <Row>
          <Col>
            <Card className="mb-4">
              <Card.Header>
                <h5 className="mb-0">🔬 Nerva Fingerprint Metadata</h5>
              </Card.Header>
              <Card.Body>
                <Table borderless size="sm" style={{ tableLayout: 'fixed' }}>
                  <colgroup>
                    <col style={{ width: '140px' }} />
                    <col style={{ width: 'auto' }} />
                  </colgroup>
                  <tbody>
                    {service.nerva_metadata.confidence && (
                      <tr>
                        <td className="text-nowrap"><strong>Confidence:</strong></td>
                        <td className="text-break"><Badge bg="secondary">{service.nerva_metadata.confidence}</Badge></td>
                      </tr>
                    )}
                    {service.nerva_metadata.cpes && service.nerva_metadata.cpes.length > 0 && (
                      <tr>
                        <td className="text-nowrap"><strong>CPEs:</strong></td>
                        <td className="text-break">
                          <ul className="list-unstyled mb-0">
                            {service.nerva_metadata.cpes.map((cpe, idx) => (
                              <li key={idx}><code className="small text-break">{cpe}</code></li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                    {service.nerva_metadata.passwordAuthEnabled !== undefined && (
                      <tr>
                        <td className="text-nowrap"><strong>Password Auth:</strong></td>
                        <td className="text-break">{service.nerva_metadata.passwordAuthEnabled ? 'Enabled' : 'Disabled'}</td>
                      </tr>
                    )}
                    {service.nerva_metadata.auth_methods && service.nerva_metadata.auth_methods.length > 0 && (
                      <tr>
                        <td className="text-nowrap"><strong>Auth Methods:</strong></td>
                        <td className="text-break">{service.nerva_metadata.auth_methods.join(', ')}</td>
                      </tr>
                    )}
                    {service.nerva_metadata.algo && (
                      <tr>
                        <td className="text-nowrap align-top"><strong>Algorithms:</strong></td>
                        <td className="text-break">
                          <pre className="bg-light p-2 rounded small mb-0" style={{ maxHeight: '200px', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {typeof service.nerva_metadata.algo === 'string'
                              ? service.nerva_metadata.algo
                              : JSON.stringify(service.nerva_metadata.algo, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                    {Object.entries(service.nerva_metadata).filter(([k]) => !['confidence', 'cpes', 'passwordAuthEnabled', 'auth_methods', 'algo', 'banner'].includes(k)).length > 0 && (
                      <tr>
                        <td colSpan={2} className="text-break">
                          <details>
                            <summary className="text-muted small">Other metadata</summary>
                            <pre className="bg-light p-2 rounded small mt-2 mb-0" style={{ maxHeight: '150px', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                              {JSON.stringify(
                                Object.fromEntries(
                                  Object.entries(service.nerva_metadata).filter(([k]) => !['confidence', 'cpes', 'passwordAuthEnabled', 'auth_methods', 'algo', 'banner'].includes(k))
                                ),
                                null,
                                2
                              )}
                            </pre>
                          </details>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </Table>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      <Row>
        <Col>
          <NotesSection
            assetType="service"
            assetId={service.id || service._id}
            currentNotes={service.notes || ''}
            apiUpdateFunction={serviceAPI.updateNotes}
            onNotesUpdate={handleNotesUpdate}
          />
        </Col>
      </Row>

      <Row>
        <Col>
          <Card>
            <Card.Header>
              <h5 className="mb-0">🔍 Additional Information</h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={6}>
                  <h6>Discovery Information</h6>
                  <ul className="list-unstyled">
                    <li><strong>Object ID:</strong> <code>{service._id}</code></li>
                                    <li><strong>First Discovered:</strong> {formatServiceDate(service.created_at)}</li>
                <li><strong>Last Seen:</strong> {formatServiceDate(service.updated_at)}</li>
                  </ul>
                </Col>
                <Col md={6}>
                  <h6>Service Statistics</h6>
                  <ul className="list-unstyled">
                    <li><strong>Has Banner:</strong> {service.banner ? 'Yes' : 'No'}</li>
                    <li><strong>Has Version Info:</strong> {service.version ? 'Yes' : 'No'}</li>
                    <li><strong>Protocol Type:</strong> {service.protocol || 'Unknown'}</li>
                  </ul>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Full Service JSON */}
      <Row>
        <Col>
          <Card className="mb-4">
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h6 className="mb-0">Full Service (JSON)</h6>
              <div>
                <Button
                  variant="outline-primary"
                  size="sm"
                  onClick={copyJsonToClipboard}
                  className="me-2"
                >
                  📋 Copy JSON
                </Button>
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={() => toggleSection('json')}
                >
                  {expandedSections.json ? 'Hide' : 'Show'}
                </Button>
              </div>
            </Card.Header>
            <Collapse in={expandedSections.json}>
              <Card.Body>
                <pre className="bg-dark text-light p-3 rounded" style={{ fontSize: '0.875rem', maxHeight: '500px', overflow: 'auto' }}>
                  {JSON.stringify(service, null, 2)}
                </pre>
              </Card.Body>
            </Collapse>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default ServiceDetail;