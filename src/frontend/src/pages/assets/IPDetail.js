import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Table, Collapse, Modal } from 'react-bootstrap';
import { ipAPI, domainAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function IPDetail() {
  const { ipAddress } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [ip, setIp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    json: false
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [relatedSubdomains, setRelatedSubdomains] = useState([]);
  const [subdomainsLoading, setSubdomainsLoading] = useState(false);
  const [subdomainsError, setSubdomainsError] = useState(null);

  usePageTitle(formatPageTitle(ip?.ip, 'IP'));

  useEffect(() => {
    const fetchIp = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        if (idParam) {
          const data = await ipAPI.getById(idParam);
          setIp(data);
          // Fetch related subdomains for this IP
          if (data && data.ip) {
            await fetchRelatedSubdomains(data.ip);
          }
        } else if (ipAddress) {
          const decodedIpAddress = decodeURIComponent(ipAddress);
          const response = await ipAPI.getByAddress(decodedIpAddress);
          setIp(response);
          // Fetch related subdomains for this IP
          await fetchRelatedSubdomains(decodedIpAddress);
        } else {
          setError('IP id is required');
          setIp(null);
        }
        setError(null);
      } catch (err) {
        setError('Failed to fetch IP details: ' + err.message);
        setIp(null);
      } finally {
        setLoading(false);
      }
    };
    
    if (ipAddress || new URLSearchParams(location.search).get('id')) {
      fetchIp();
    }
  }, [ipAddress, location.search]);

  const formatIPDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const handleNotesUpdate = (newNotes) => {
    // Update the IP object with new notes
    setIp(prev => ({ ...prev, notes: newNotes }));
  };

  // Toggle expanded sections
  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // Copy JSON to clipboard
  const copyJsonToClipboard = () => {
    if (ip) {
      navigator.clipboard.writeText(JSON.stringify(ip, null, 2));
    }
  };

  // Delete IP handlers
  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!ip) return;
    
    try {
      setDeleting(true);
      await ipAPI.delete(ip.id);
      setShowDeleteModal(false);
      navigate('/assets/ips');
    } catch (err) {
      setError('Failed to delete IP: ' + err.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  // Fetch related subdomains that resolve to this IP
  const fetchRelatedSubdomains = async (ipAddress) => {
    try {
      setSubdomainsLoading(true);
      setSubdomainsError(null);
      const response = await domainAPI.getSubdomainsByIP(ipAddress, 1, 50); // Get up to 50 subdomains
      setRelatedSubdomains(response.items || []);
    } catch (err) {
      setSubdomainsError('Failed to fetch related subdomains: ' + err.message);
      setRelatedSubdomains([]);
    } finally {
      setSubdomainsLoading(false);
    }
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading IP details...</p>
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
        <Button variant="outline-primary" onClick={() => navigate('/assets/ips')}>
          ← Back to IPs
        </Button>
      </Container>
    );
  }

  if (!ip) {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>IP Not Found</Alert.Heading>
          The requested IP address could not be found.
        </Alert>
        <Button variant="outline-primary" onClick={() => navigate('/assets/ips')}>
          ← Back to IPs
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
              <h1>🖥️ {ip.ip}</h1>
              <p className="text-muted">IP address details and reconnaissance information</p>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={handleDeleteClick}
                className="me-2"
              >
                🗑️ Delete
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/assets/ips')}>
                ← Back to IPs
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={handleDeleteCancel} centered>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete IP Address</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this IP address?</p>
          <p><strong>IP Address:</strong> {ip.ip}</p>
          <p className="text-danger">
            <strong>Warning:</strong> This action cannot be undone. The IP address will be permanently removed from the database.
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
              'Delete IP Address'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      <Row>
        <Col md={6}>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">📋 Basic Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>IP Address:</strong></td>
                    <td><code>{ip.ip}</code></td>
                  </tr>
                  <tr>
                    <td><strong>Program:</strong></td>
                    <td>
                      {ip.program_name ? (
                        <Badge bg="primary">{ip.program_name}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Service Provider:</strong></td>
                    <td>
                      {ip.service_provider ? (
                        <Badge bg="info">{ip.service_provider}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td className="text-muted">{formatIPDate(ip.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Last Updated:</strong></td>
                    <td className="text-muted">{formatIPDate(ip.updated_at)}</td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>

        <Col md={6}>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">🌐 DNS Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>PTR Records:</strong></td>
                    <td>
                      {ip.ptr ? (
                        <Badge bg="light" text="dark" className="me-1 mb-1">
                          {ip.ptr}
                        </Badge>
                      ) : (
                        <span className="text-muted">No PTR record</span>
                      )}
                    </td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Related Subdomains Section */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">🔗 Related Subdomains</h5>
            </Card.Header>
            <Card.Body>
              {subdomainsLoading ? (
                <div className="text-center py-3">
                  <Spinner animation="border" size="sm" />
                  <p className="mt-2 text-muted">Loading related subdomains...</p>
                </div>
              ) : subdomainsError ? (
                <Alert variant="warning">
                  <Alert.Heading>Error Loading Subdomains</Alert.Heading>
                  {subdomainsError}
                </Alert>
              ) : relatedSubdomains.length === 0 ? (
                <Alert variant="info">
                  <Alert.Heading>No Related Subdomains</Alert.Heading>
                  No subdomains were found that resolve to this IP address.
                </Alert>
              ) : (
                <div>
                  <p className="text-muted mb-3">
                    Found {relatedSubdomains.length} subdomain{relatedSubdomains.length !== 1 ? 's' : ''} that resolve to this IP address:
                  </p>
                  <Table striped bordered hover responsive>
                    <thead>
                      <tr>
                        <th>Domain Name</th>
                        <th>Program</th>
                        <th>Apex Domain</th>
                        <th>Wildcard</th>
                        <th>CNAME</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {relatedSubdomains.map((subdomain) => (
                        <tr key={subdomain.id}>
                          <td>
                            <code>{subdomain.name}</code>
                          </td>
                          <td>
                            {subdomain.program_name ? (
                              <Badge bg="primary">{subdomain.program_name}</Badge>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                          <td>
                            {subdomain.apex_domain ? (
                              <Badge bg="info">{subdomain.apex_domain}</Badge>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                          <td>
                            {subdomain.is_wildcard ? (
                              <Badge bg="warning" text="dark">Yes</Badge>
                            ) : (
                              <Badge bg="secondary">No</Badge>
                            )}
                          </td>
                          <td>
                            {subdomain.cname_record ? (
                              <code>{subdomain.cname_record}</code>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                          <td>
                            <Button
                              variant="outline-primary"
                              size="sm"
                              onClick={() => navigate(`/assets/subdomains/details?id=${encodeURIComponent(subdomain.id)}`)}
                            >
                              View Details
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <NotesSection
            assetType="IP address"
            assetId={ip._id}
            currentNotes={ip.notes || ''}
            apiUpdateFunction={ipAPI.updateNotes}
            onNotesUpdate={handleNotesUpdate}
            cardClassName="dashboard-panel"
          />
        </Col>
      </Row>

      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">🔍 Additional Information</h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={6}>
                  <h6>Discovery Information</h6>
                  <ul className="list-unstyled">
                    <li><strong>Object ID:</strong> <code>{ip._id}</code></li>
                                    <li><strong>First Discovered:</strong> {formatIPDate(ip.created_at)}</li>
                <li><strong>Last Seen:</strong> {formatIPDate(ip.updated_at)}</li>
                  </ul>
                </Col>
                <Col md={6}>
                  <h6>Statistics</h6>
                  <ul className="list-unstyled">
                    <li><strong>PTR Record:</strong> {ip.ptr ? 'Yes' : 'No'}</li>
                    <li><strong>Has Service Provider:</strong> {ip.service_provider ? 'Yes' : 'No'}</li>
                  </ul>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Full IP JSON */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h6 className="mb-0">Full IP (JSON)</h6>
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
                  {JSON.stringify(ip, null, 2)}
                </pre>
              </Card.Body>
            </Collapse>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default IPDetail;