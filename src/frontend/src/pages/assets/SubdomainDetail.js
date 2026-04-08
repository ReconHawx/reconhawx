import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Table, Collapse, Modal } from 'react-bootstrap';
import { domainAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function SubdomainDetail() {
  const { domainName } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [domain, setDomain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    json: false
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  usePageTitle(formatPageTitle(domain?.name, 'Subdomain'));

  useEffect(() => {
    const fetchDomain = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        if (idParam) {
          const data = await domainAPI.getById(idParam);
          setDomain(data);
        } else {
          const decodedDomainName = decodeURIComponent(domainName || '');
          const response = await domainAPI.getByName(decodedDomainName);
          setDomain(response);
        }
        setError(null);
      } catch (err) {
        setError('Failed to fetch domain details: ' + err.message);
        setDomain(null);
      } finally {
        setLoading(false);
      }
    };

    if (domainName || new URLSearchParams(location.search).get('id')) {
      fetchDomain();
    }
  }, [domainName, location.search]);

  const formatSubdomainDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const handleNotesUpdate = (newNotes) => {
    // Update the domain object with new notes
    setDomain(prev => ({ ...prev, notes: newNotes }));
  };

  // Toggle expanded sections
  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // Copy to clipboard helper
  const copyToClipboard = (text) => {
    if (text) navigator.clipboard.writeText(text);
  };

  // Copy JSON to clipboard
  const copyJsonToClipboard = () => {
    if (domain) {
      navigator.clipboard.writeText(JSON.stringify(domain, null, 2));
    }
  };

  // Normalize IP list: supports both [{ip, ip_id}, ...] and ["1.2.3.4", ...]
  const getIpList = () => {
    if (!domain?.ip || !Array.isArray(domain.ip)) return [];
    return domain.ip.map((item) =>
      typeof item === 'object' && item?.ip != null
        ? { ip: item.ip, ip_id: item.ip_id || null }
        : { ip: String(item), ip_id: null }
    );
  };

  // Delete domain handlers
  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!domain) return;
    
    try {
      setDeleting(true);
      await domainAPI.delete(domain.id || domain._id);
      setShowDeleteModal(false);
      navigate('/assets/domains');
    } catch (err) {
      setError('Failed to delete domain: ' + err.message);
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
          <p className="mt-2">Loading domain details...</p>
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
        <Button variant="outline-primary" onClick={() => navigate('/assets/domains')}>
          ← Back to Domains
        </Button>
      </Container>
    );
  }

  if (!domain) {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>Domain Not Found</Alert.Heading>
          The requested domain could not be found.
        </Alert>
        <Button variant="outline-primary" onClick={() => navigate('/assets/domains')}>
          ← Back to Domains
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
              <h1>🌐 {domain.name}</h1>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={handleDeleteClick}
                className="me-2"
              >
                🗑️ Delete Domain
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/assets/domains')}>
                ← Back to Domains
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={handleDeleteCancel} centered>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete Domain</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this domain?</p>
          <p><strong>Domain Name:</strong> {domain.name}</p>
          <p className="text-danger">
            <strong>Warning:</strong> This action cannot be undone. The domain will be permanently removed from the database.
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
              'Delete Domain'
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
                    <td><strong>Domain Name:</strong></td>
                    <td>{domain.name}</td>
                  </tr>
                  <tr>
                    <td><strong>Program:</strong></td>
                    <td>
                      {domain.program_name ? (
                        <Badge bg="primary">{domain.program_name}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Type:</strong></td>
                    <td>
                      {domain.is_wildcard ? (
                        <Badge bg="warning" text="dark">Wildcard</Badge>
                      ) : (
                        <Badge bg="success">Regular</Badge>
                      )}
                    </td>
                  </tr>
                  {domain.wildcard_type && (
                    <tr>
                      <td><strong>Wildcard Type:</strong></td>
                      <td>
                        <Badge bg="info">{domain.wildcard_type}</Badge>
                      </td>
                    </tr>
                  )}
                  <tr>
                    <td><strong>Apex Domain:</strong></td>
                    <td>
                      {domain.apex_domain ? (
                        <code>{domain.apex_domain}</code>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td className="text-muted">{formatSubdomainDate(domain.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Last Updated:</strong></td>
                    <td className="text-muted">{formatSubdomainDate(domain.updated_at)}</td>
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
                    <td><strong>CNAME:</strong></td>
                    <td>
                      {domain.cname_record ? (
                        <code>{domain.cname_record}</code>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>IP Addresses:</strong></td>
                    <td>
                      {getIpList().length > 0 ? (
                        <div>
                          {getIpList().map((item, idx) => (
                            <span key={idx} className="d-inline-flex align-items-center me-1 mb-1">
                              {item.ip_id ? (
                                <Badge as={Link} to={`/assets/ips/details?id=${item.ip_id}`} bg="secondary" className="text-decoration-none me-1">
                                  {item.ip}
                                </Badge>
                              ) : (
                                <Badge bg="secondary" className="me-1">
                                  {item.ip}
                                </Badge>
                              )}
                              <Button
                                variant="outline-secondary"
                                size="sm"
                                className="ms-1"
                                onClick={() => copyToClipboard(item.ip)}
                                title="Copy to clipboard"
                              >
                                📋
                              </Button>
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted">No IP addresses resolved</span>
                      )}
                    </td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <NotesSection
            assetType="domain"
            assetId={domain.id || domain._id}
            currentNotes={domain.notes || ''}
            apiUpdateFunction={domainAPI.updateNotes}
            onNotesUpdate={handleNotesUpdate}
            cardClassName="dashboard-panel"
          />
        </Col>
      </Row>

      {/* Full Domain JSON */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h6 className="mb-0">Full Domain (JSON)</h6>
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
                  {JSON.stringify(domain, null, 2)}
                </pre>
              </Card.Body>
            </Collapse>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default SubdomainDetail;