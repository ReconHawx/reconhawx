import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Table, Collapse, Modal } from 'react-bootstrap';
import { domainAPI, apexDomainAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function ApexDomainDetail() {
  const { apexDomainName } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [apexDomain, setApexDomain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    json: false
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  usePageTitle(formatPageTitle(apexDomain?.name, 'Apex Domain'));

  useEffect(() => {
    const fetchApexDomain = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        if (idParam) {
          const data = await apexDomainAPI.getById(idParam);
          setApexDomain(data);
          setError(null);
        } else {
          const decodedApexDomainName = decodeURIComponent(apexDomainName || '');
          // Query for the specific apex domain by name (fallback)
          const filter = { name: decodedApexDomainName };
          const response = await domainAPI.searchSubdomains({ ...filter, page_size: 1, page: 1 });
          if (response.status === 'success' && response.items && response.items.length > 0) {
            setApexDomain(response.items[0]);
            setError(null);
          } else {
            throw new Error('Apex domain not found');
          }
        }
      } catch (err) {
        setError('Failed to fetch apex domain details: ' + err.message);
        setApexDomain(null);
      } finally {
        setLoading(false);
      }
    };

    if (apexDomainName || new URLSearchParams(location.search).get('id')) {
      fetchApexDomain();
    }
  }, [apexDomainName, location.search]);

  const formatApexDomainDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const handleNotesUpdate = (newNotes) => {
    // Update the apex domain object with new notes
    setApexDomain(prev => ({ ...prev, notes: newNotes }));
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
    if (apexDomain) {
      navigator.clipboard.writeText(JSON.stringify(apexDomain, null, 2));
    }
  };

  // Delete apex domain handlers
  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!apexDomain) return;
    
    try {
      setDeleting(true);
      // Delete apex domain (subdomains will be handled by the backend)
      await apexDomainAPI.delete(apexDomain.id || apexDomain._id);
      setShowDeleteModal(false);
      navigate('/assets/apex-domains');
    } catch (err) {
      setError('Failed to delete apex domain: ' + err.message);
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
          <p className="mt-2">Loading apex domain details...</p>
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
        <Button variant="outline-primary" onClick={() => navigate('/assets/apex-domains')}>
          ← Back to Apex Domains
        </Button>
      </Container>
    );
  }

  if (!apexDomain) {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>Apex Domain Not Found</Alert.Heading>
          The requested apex domain could not be found.
        </Alert>
        <Button variant="outline-primary" onClick={() => navigate('/assets/apex-domains')}>
          ← Back to Apex Domains
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
              <h1>🌐 {apexDomain.name}</h1>
              <p className="text-muted">Apex domain details and WHOIS information</p>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={handleDeleteClick}
                className="me-2"
              >
                🗑️ Delete
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/assets/apex-domains')}>
                ← Back to Apex Domains
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={handleDeleteCancel} centered>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete Apex Domain</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this apex domain?</p>
          <p><strong>Apex Domain Name:</strong> {apexDomain.name}</p>
          
          <Alert variant="warning" className="mt-3">
            <i className="bi bi-exclamation-triangle"></i>
            <strong>Warning:</strong> This action cannot be undone. The apex domain will be permanently removed from the database.
          </Alert>
          
          <Alert variant="danger" className="mt-3">
            <i className="bi bi-exclamation-triangle-fill"></i>
            <strong>Critical:</strong> Deleting this apex domain will also remove ALL associated subdomains and their related assets:
            <ul className="mb-0 mt-2">
              <li>All subdomains under {apexDomain.name}</li>
              <li>IP addresses linked to those subdomains</li>
              <li>URLs associated with those subdomains</li>
              <li>Services running on those subdomains</li>
              <li>Certificates for those subdomains</li>
            </ul>
            <p className="mb-0 mt-2"><strong>This is a destructive operation that will permanently remove all related data!</strong></p>
          </Alert>
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
              'Delete Apex Domain + All Subdomains'
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
                    <td><strong>Apex Domain:</strong></td>
                    <td>{apexDomain.name}</td>
                  </tr>
                  <tr>
                    <td><strong>Program:</strong></td>
                    <td>
                      {apexDomain.program_name ? (
                        <Badge bg="primary">{apexDomain.program_name}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Asset Type:</strong></td>
                    <td>
                      <Badge bg="info">Apex Domain</Badge>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td className="text-muted">{formatApexDomainDate(apexDomain.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Last Updated:</strong></td>
                    <td className="text-muted">{formatApexDomainDate(apexDomain.updated_at)}</td>
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
                      {apexDomain.cname ? (
                        <code>{apexDomain.cname}</code>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>IP Addresses:</strong></td>
                    <td>
                      {apexDomain.ip && apexDomain.ip.length > 0 ? (
                        <div>
                          {apexDomain.ip.map((ip, idx) => (
                            <Badge key={idx} bg="secondary" className="me-1 mb-1">
                              {ip}
                            </Badge>
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

      {/* WHOIS Information — legacy whois_data object or column fields from workflow/API */}
      {(apexDomain.whois_data ||
        apexDomain.whois_status ||
        apexDomain.whois_registrar ||
        apexDomain.whois_creation_date ||
        apexDomain.whois_expiration_date ||
        apexDomain.whois_updated_date ||
        (apexDomain.whois_name_servers && apexDomain.whois_name_servers.length > 0) ||
        apexDomain.whois_error ||
        apexDomain.whois_checked_at) && (
        <Row>
          <Col>
            <Card className="dashboard-panel mb-4">
              <Card.Header>
                <h5 className="mb-0">📋 WHOIS Information</h5>
              </Card.Header>
              <Card.Body>
                <Row>
                  <Col md={6}>
                    <Table borderless>
                      <tbody>
                        <tr>
                          <td><strong>Registrar:</strong></td>
                          <td>
                            {(apexDomain.whois_data?.registrar ?? apexDomain.whois_registrar) ? (
                              <span>{apexDomain.whois_data?.registrar ?? apexDomain.whois_registrar}</span>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Creation Date:</strong></td>
                          <td>
                            {(apexDomain.whois_data?.creation_date ?? apexDomain.whois_creation_date) ? (
                              <span>{formatApexDomainDate(apexDomain.whois_data?.creation_date ?? apexDomain.whois_creation_date)}</span>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Expiration Date:</strong></td>
                          <td>
                            {(apexDomain.whois_data?.expiration_date ?? apexDomain.whois_expiration_date) ? (
                              <span>{formatApexDomainDate(apexDomain.whois_data?.expiration_date ?? apexDomain.whois_expiration_date)}</span>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                        </tr>
                        {apexDomain.whois_checked_at && (
                          <tr>
                            <td><strong>WHOIS checked:</strong></td>
                            <td className="text-muted">{formatApexDomainDate(apexDomain.whois_checked_at)}</td>
                          </tr>
                        )}
                        {apexDomain.whois_response_source && (
                          <tr>
                            <td><strong>Response source:</strong></td>
                            <td><code>{apexDomain.whois_response_source}</code></td>
                          </tr>
                        )}
                      </tbody>
                    </Table>
                  </Col>
                  <Col md={6}>
                    <Table borderless>
                      <tbody>
                        <tr>
                          <td><strong>Updated Date:</strong></td>
                          <td>
                            {(apexDomain.whois_data?.updated_date ?? apexDomain.whois_updated_date) ? (
                              <span>{formatApexDomainDate(apexDomain.whois_data?.updated_date ?? apexDomain.whois_updated_date)}</span>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Status:</strong></td>
                          <td>
                            {(() => {
                              const st = apexDomain.whois_data?.status ?? apexDomain.whois_status;
                              if (!st) return <span className="text-muted">-</span>;
                              if (Array.isArray(st)) {
                                return (
                                  <div>
                                    {st.map((status, idx) => (
                                      <Badge key={idx} bg="success" className="me-1 mb-1">
                                        {status}
                                      </Badge>
                                    ))}
                                  </div>
                                );
                              }
                              return <Badge bg="success">{st}</Badge>;
                            })()}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Name Servers:</strong></td>
                          <td>
                            {(() => {
                              const ns = apexDomain.whois_data?.name_servers ?? apexDomain.whois_name_servers;
                              if (!ns) return <span className="text-muted">-</span>;
                              if (Array.isArray(ns)) {
                                return (
                                  <div>
                                    {ns.map((n, idx) => (
                                      <Badge key={idx} bg="info" className="me-1 mb-1">
                                        {n}
                                      </Badge>
                                    ))}
                                  </div>
                                );
                              }
                              return <Badge bg="info">{ns}</Badge>;
                            })()}
                          </td>
                        </tr>
                        {apexDomain.whois_error && (
                          <tr>
                            <td><strong>WHOIS error:</strong></td>
                            <td className="text-danger small">{apexDomain.whois_error}</td>
                          </tr>
                        )}
                      </tbody>
                    </Table>
                  </Col>
                </Row>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Related Assets */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">🔗 Related Assets</h5>
            </Card.Header>
            <Card.Body>
              <Button 
                variant="outline-primary" 
                onClick={() => navigate(`/assets/subdomains?apex_domain=${encodeURIComponent(apexDomain.name)}`)}
              >
                🔍 View Subdomains for {apexDomain.name}
              </Button>
              <p className="text-muted mt-2">
                View all subdomains that belong to this apex domain.
              </p>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <NotesSection
            assetType="apex_domain"
            assetId={apexDomain.id || apexDomain._id}
            currentNotes={apexDomain.notes || ''}
            apiUpdateFunction={apexDomainAPI.updateNotes}
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
                    <li><strong>Object ID:</strong> <code>{apexDomain._id}</code></li>
                                    <li><strong>First Discovered:</strong> {formatApexDomainDate(apexDomain.created_at)}</li>
                <li><strong>Last Seen:</strong> {formatApexDomainDate(apexDomain.updated_at)}</li>
                  </ul>
                </Col>
                <Col md={6}>
                  <h6>Statistics</h6>
                  <ul className="list-unstyled">
                    <li><strong>IP Addresses Count:</strong> {apexDomain.ip ? apexDomain.ip.length : 0}</li>
                    <li><strong>Has CNAME:</strong> {apexDomain.cname ? 'Yes' : 'No'}</li>
                    <li>
                      <strong>WHOIS Data Available:</strong>{' '}
                      {apexDomain.whois_data ||
                      apexDomain.whois_status ||
                      apexDomain.whois_registrar
                        ? 'Yes'
                        : 'No'}
                    </li>
                  </ul>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Full Apex Domain JSON */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h6 className="mb-0">Full Apex Domain (JSON)</h6>
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
                  {JSON.stringify(apexDomain, null, 2)}
                </pre>
              </Card.Body>
            </Collapse>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default ApexDomainDetail; 