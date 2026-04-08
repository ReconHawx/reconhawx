import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Table, Collapse, Modal } from 'react-bootstrap';
import { typosquatAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';
import ScreenshotsViewer from '../../components/ScreenshotsViewer';
import { usePageTitle, formatPageTitle, truncateTitle } from '../../hooks/usePageTitle';

function TyposquatUrlDetails() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [url, setUrl] = useState(null);
  const [urls, setUrls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    json: false
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [viewMode, setViewMode] = useState('detail'); // 'detail' or 'list'

  // Certificate state
  const [certificate, setCertificate] = useState(null);
  const [certificateLoading, setCertificateLoading] = useState(false);

  const domainParam = new URLSearchParams(location.search).get('domain');
  usePageTitle(
    viewMode === 'list' && domainParam
      ? formatPageTitle(`URLs · ${domainParam}`, 'Typosquat')
      : formatPageTitle(url?.url ? truncateTitle(url.url) : null, 'Typosquat URL')
  );

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        const domainParam = params.get('domain');
        
        if (idParam) {
          // Detail view - fetch specific URL
          setViewMode('detail');
          const response = await typosquatAPI.getUrlById(idParam);
          setUrl(response);
          setUrls([]);
        } else if (domainParam) {
          // List view - fetch URLs for domain
          setViewMode('list');
          const response = await typosquatAPI.getUrlsByDomain(domainParam);
          setUrls(response || []);
          setUrl(null);
        } else if (id) {
          // Detail view - fetch specific URL from URL params
          setViewMode('detail');
          const response = await typosquatAPI.getUrlById(id);
          setUrl(response);
          setUrls([]);
        } else {
          setError('No ID or domain parameter provided');
          setUrl(null);
          setUrls([]);
        }
        setError(null);
      } catch (err) {
        setError('Failed to fetch data: ' + err.message);
        setUrl(null);
        setUrls([]);
      } finally {
        setLoading(false);
      }
    };

    if (id || new URLSearchParams(location.search).get('id') || new URLSearchParams(location.search).get('domain')) {
      fetchData();
    }
  }, [id, location.search]);

  // Fetch certificate data when URL is loaded in detail view
  useEffect(() => {
    const fetchCertificate = async () => {
      if (viewMode === 'detail' && url?.typosquat_certificate_id) {
        try {
          setCertificateLoading(true);
          // Note: You'll need to add this API endpoint to fetch certificate by ID
          const response = await typosquatAPI.getCertificateById(url.typosquat_certificate_id);
          setCertificate(response);
        } catch (err) {
          console.error('Error fetching certificate:', err);
          setCertificate(null);
        } finally {
          setCertificateLoading(false);
        }
      }
    };

    fetchCertificate();
  }, [url?.typosquat_certificate_id, viewMode]);

  const formatUrlDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const handleNotesUpdate = (newNotes) => {
    setUrl(prev => ({ ...prev, notes: newNotes }));
  };

  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!url) return;
    
    try {
      setDeleting(true);
      await typosquatAPI.deleteUrl(url.id || url._id);
      setShowDeleteModal(false);
      navigate('/findings/typosquat');
    } catch (err) {
      setError('Failed to delete typosquat URL: ' + err.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const copyJsonToClipboard = () => {
    if (url) {
      navigator.clipboard.writeText(JSON.stringify(url, null, 2));
    }
  };

  // Copy URL to clipboard
  const handleCopyUrl = async () => {
    if (url?.url) {
      try {
        await navigator.clipboard.writeText(url.url);
      } catch (err) {
        console.error('Failed to copy URL:', err);
      }
    }
  };

  // Copy defanged URL to clipboard
  const handleCopyDefangedUrl = async () => {
    if (url?.url) {
      try {
        const defanged = url.url.replace(/\./g, '[.]');
        await navigator.clipboard.writeText(defanged);
      } catch (err) {
        console.error('Failed to copy defanged URL:', err);
      }
    }
  };

  const parseUrl = (urlString) => {
    try {
      const urlObj = new URL(urlString);
      return {
        protocol: urlObj.protocol,
        hostname: urlObj.hostname,
        port: urlObj.port || (urlObj.protocol === 'https:' ? '443' : '80'),
        pathname: urlObj.pathname,
        search: urlObj.search
      };
    } catch (e) {
      return null;
    }
  };

  const getStatusBadgeVariant = (statusCode) => {
    if (!statusCode) return 'secondary';
    if (statusCode < 300) return 'success';
    if (statusCode < 400) return 'info';
    if (statusCode < 500) return 'warning';
    return 'danger';
  };

  const truncateUrl = (url, maxLength = 70) => {
    if (!url || url.length <= maxLength) return url;
    return url.substring(0, maxLength) + '...';
  };

  const renderRedirectChain = () => {
    if (url.redirect_chain && Array.isArray(url.redirect_chain) && url.redirect_chain.length > 0) {
      return (
        <ul className="list-unstyled mb-0">
          {url.redirect_chain.map((step, idx) => (
            <li key={idx} className="mb-2 d-flex align-items-center flex-wrap">
              <Badge bg="secondary" className="me-2" style={{ minWidth: '50px' }}>
                {step.method || 'GET'}
              </Badge>
              <Badge bg="secondary" className="me-2 text-break" title={step.url} style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {truncateUrl(step.url)}
              </Badge>
              <i className="fas fa-arrow-right mx-2 text-muted"></i>
              <Badge bg={getStatusBadgeVariant(step.status_code)} className="me-2">
                {step.status_code || 'N/A'}
              </Badge>
              {step.location && (
                <>
                  <span className="text-muted me-2">→</span>
                  <a 
                    href={step.location} 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="text-break"
                    title={step.location}
                  >
                    {truncateUrl(step.location)}
                  </a>
                </>
              )}
            </li>
          ))}
        </ul>
      );
    }
    
    if (url.final_url && url.final_url !== url.url) {
      return (
        <ul className="list-unstyled mb-0">
          <li className="mb-2 d-flex align-items-center flex-wrap">
            <Badge bg="secondary" className="me-2" style={{ minWidth: '50px' }}>
              {url.http_method || 'GET'}
            </Badge>
            <Badge bg="light" text="dark" className="me-2 text-break" title={url.url} style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {truncateUrl(url.url)}
            </Badge>
            <i className="fas fa-arrow-right mx-2 text-muted"></i>
            <Badge bg={getStatusBadgeVariant(url.http_status_code)} className="me-2">
              {url.http_status_code || 'N/A'}
            </Badge>
            <span className="text-muted me-2">→</span>
            <a 
              href={url.final_url} 
              target="_blank" 
              rel="noopener noreferrer" 
              className="text-break"
              title={url.final_url}
            >
              {truncateUrl(url.final_url)}
            </a>
          </li>
        </ul>
      );
    }
    
    return (
      <Alert variant="info" className="py-2 mb-0">
        No redirect chain recorded.
      </Alert>
    );
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading typosquat URL details...</p>
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
        <Button variant="outline-danger" onClick={() => navigate(-1)}>
          Go Back
        </Button>
      </Container>
    );
  }

  if (!url && viewMode === 'detail') {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>URL Not Found</Alert.Heading>
          The requested typosquat URL could not be found.
        </Alert>
        <Button variant="outline-warning" onClick={() => navigate(-1)}>
          Go Back
        </Button>
      </Container>
    );
  }

  // List view - show URLs for a domain
  if (viewMode === 'list') {
    const domainParam = new URLSearchParams(location.search).get('domain');
    
    return (
      <Container fluid className="p-4">
        <Row className="mb-4">
          <Col>
            <div className="d-flex justify-content-between align-items-center">
              <div>
                <h1>🔗 Typosquat URLs for Domain</h1>
                <p className="text-muted">URLs associated with: <strong>{domainParam}</strong></p>
              </div>
              <div>
                <Button variant="outline-primary" onClick={() => navigate('/findings/typosquat')}>
                  ← Back to Typosquat Findings
                </Button>
              </div>
            </div>
          </Col>
        </Row>

        {urls.length > 0 ? (
          <Card>
            <Card.Header>
              <h5 className="mb-0">Found {urls.length} URL(s)</h5>
            </Card.Header>
            <Card.Body>
                              <div className="table-responsive">
                  <Table hover size="sm">
                    <thead className="table-light">
                      <tr>
                        <th>URL</th>
                        <th>Status Code</th>
                        <th>Content Type</th>
                        <th>Response Time</th>
                        <th>Technologies</th>
                      </tr>
                    </thead>
                  <tbody>
                    {urls.map((urlData) => (
                      <tr key={urlData.id || urlData._id}>
                        <td>
                          <div className="text-break" style={{ maxWidth: '300px' }}>
                            <button
                              onClick={() => navigate(`/findings/typosquat-urls/details?id=${urlData.id || urlData._id}`)}
                              className="btn btn-link text-decoration-none text-primary p-0 border-0 bg-transparent"
                              style={{ cursor: 'pointer' }}
                              title="Click to view URL details"
                            >
                              {urlData.url}
                            </button>
                          </div>
                        </td>
                        <td>
                          {urlData.http_status_code ? (
                            <Badge bg={
                              urlData.http_status_code >= 200 && urlData.http_status_code < 300 ? 'success' :
                              urlData.http_status_code >= 300 && urlData.http_status_code < 400 ? 'warning' :
                              urlData.http_status_code >= 400 ? 'danger' : 'secondary'
                            }>
                              {urlData.http_status_code}
                            </Badge>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {urlData.content_type ? (
                            <code className="small">{urlData.content_type}</code>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {urlData.response_time_ms ? (
                            <span>{urlData.response_time_ms} ms</span>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {urlData.technologies && urlData.technologies.length > 0 ? (
                            <div>
                              {urlData.technologies.slice(0, 3).map((tech, idx) => (
                                <Badge key={idx} bg="info" className="me-1 mb-1 small">
                                  {tech}
                                </Badge>
                              ))}
                              {urlData.technologies.length > 3 && (
                                <Badge bg="secondary" className="small">
                                  +{urlData.technologies.length - 3} more
                                </Badge>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td>
                          {/* Actions column removed - URL is now clickable */}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            </Card.Body>
          </Card>
        ) : (
          <Alert variant="info">
            <i className="fas fa-info-circle me-2"></i>
            No typosquat URLs found for domain <strong>{domainParam}</strong>.
          </Alert>
        )}
      </Container>
    );
  }

  // Detail view - show specific URL details
  const parsedUrl = parseUrl(url.url);

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <div>
              <h1>🔗 Typosquat URL Details</h1>
              <p className="text-muted">Typosquat URL information and reconnaissance data</p>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={handleDeleteClick}
                className="me-2"
              >
                🗑️ Delete
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/findings/typosquat')}>
                ← Back to Typosquat URLs
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={handleDeleteCancel} centered>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete Typosquat URL</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this typosquat URL?</p>
          <p><strong>URL:</strong> {url.url}</p>
          <p className="text-danger">
            <strong>Warning:</strong> This action cannot be undone. The URL will be permanently removed from the database.
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
              'Delete URL'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      <Row>
        <Col md={8}>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">🌐 URL Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>Full URL:</strong></td>
                    <td>
                      <div className="d-flex align-items-center">
                        <span className="me-2 text-break">{url.url}</span>
                        {url.url && (
                          <div>
                            <Button
                              variant="outline-secondary"
                              size="sm"
                              onClick={handleCopyUrl}
                              className="me-1"
                              title="Copy URL"
                            >
                              📋
                            </Button>
                            <Button
                              variant="outline-secondary"
                              size="sm"
                              onClick={handleCopyDefangedUrl}
                              title="Copy defanged URL"
                            >
                              🛡️
                            </Button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                  {parsedUrl && (
                    <>
                      <tr>
                        <td><strong>Protocol:</strong></td>
                        <td>
                          <Badge bg={parsedUrl.protocol === 'https:' ? 'success' : 'warning'}>
                            {parsedUrl.protocol.replace(':', '')}
                          </Badge>
                        </td>
                      </tr>
                      <tr>
                        <td><strong>Hostname:</strong></td>
                        <td>
                          <a href={`/findings/typosquat/details?id=${url.typosquat_domain_id}`} target="_blank" rel="noopener noreferrer" className="text-break">
                            {parsedUrl.hostname}
                          </a>
                        </td>
                        {/* <td><code>{parsedUrl.hostname}</code></td> */}
                      </tr>
                      <tr>
                        <td><strong>Port:</strong></td>
                        <td><code>{parsedUrl.port}</code></td>
                      </tr>
                      <tr>
                        <td><strong>Path:</strong></td>
                        <td><code>{parsedUrl.pathname || '/'}</code></td>
                      </tr>
                      {parsedUrl.search && (
                        <tr>
                          <td><strong>Query:</strong></td>
                          <td><code className="text-break">{parsedUrl.search}</code></td>
                        </tr>
                      )}
                    </>
                  )}
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>

        <Col md={4}>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">📋 Basic Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>Program:</strong></td>
                    <td>
                      {url.program_name ? (
                        <Badge bg="primary">{url.program_name}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Status Code:</strong></td>
                    <td>
                      {url.http_status_code ? (
                        <Badge bg={getStatusBadgeVariant(url.http_status_code)}>
                          {url.http_status_code}
                        </Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Content Length:</strong></td>
                    <td>
                      {url.content_length ? (
                        <span>{url.content_length} bytes</span>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr> 
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td className="text-muted">{formatUrlDate(url.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Last Updated:</strong></td>
                    <td className="text-muted">{formatUrlDate(url.updated_at)}</td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Technologies */}
      {url.technologies && url.technologies.length > 0 && (
        <Row>
          <Col>
            <Card className="dashboard-panel mb-4">
              <Card.Header>
                <h5 className="mb-0">⚙️ Technologies</h5>
              </Card.Header>
              <Card.Body>
                <div>
                  {url.technologies.map((tech, idx) => (
                    <Badge key={idx} bg="info" className="me-1 mb-1">
                      {tech}
                    </Badge>
                  ))}
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Redirect Chain Section */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">🔄 Redirect Chain</h5>
            </Card.Header>
            <Card.Body>
              {renderRedirectChain()}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Content Information */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header>
              <h5 className="mb-0">📄 Content Information</h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={6}>
                  <Table borderless size="sm">
                    <tbody>
                      {url.title && (
                        <tr>
                          <td><strong>Page Title:</strong></td>
                          <td className="text-break">{url.title}</td>
                        </tr>
                      )}
                      {url.content_type && (
                        <tr>
                          <td><strong>Content Type:</strong></td>
                          <td><code>{url.content_type}</code></td>
                        </tr>
                      )}
                      {url.line_count && (
                        <tr>
                          <td><strong>Line Count:</strong></td>
                          <td>{url.line_count}</td>
                        </tr>
                      )}
                      {url.word_count && (
                        <tr>
                          <td><strong>Word Count:</strong></td>
                          <td>{url.word_count}</td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </Col>
                <Col md={6}>
                  <Table borderless size="sm">
                    <tbody>
                      {url.body_preview && (
                        <tr>
                          <td><strong>Body Preview:</strong></td>
                          <td>
                            <div className="text-break" style={{ maxHeight: '100px', overflow: 'hidden' }}>
                              {url.body_preview}
                            </div>
                          </td>
                        </tr>
                      )}
                      {url.response_body_hash && (
                        <tr>
                          <td><strong>Body Hash:</strong></td>
                          <td><code className="small">{url.response_body_hash}</code></td>
                        </tr>
                      )}
                      {url.favicon_hash && (
                        <tr>
                          <td><strong>Favicon Hash:</strong></td>
                          <td><code className="small">{url.favicon_hash}</code></td>
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

      {/* Certificate Information */}
      {viewMode === 'detail' && url?.typosquat_certificate_id && (
        <Row>
          <Col>
            <Card className="dashboard-panel mb-4">
              <Card.Header>
                <h5 className="mb-0">🔒 SSL Certificate Information</h5>
              </Card.Header>
              <Card.Body>
                {certificateLoading ? (
                  <div className="text-center">
                    <Spinner animation="border" size="sm" />
                    <span className="ms-2">Loading certificate information...</span>
                  </div>
                ) : certificate ? (
                  <Row>
                    <Col md={6}>
                      <Table borderless size="sm">
                        <tbody>
                          <tr>
                            <td><strong>Subject DN:</strong></td>
                            <td className="text-break">
                              <code>{certificate.subject_dn || 'N/A'}</code>
                            </td> 
                          </tr>
                          <tr>
                            <td><strong>Issuer Organization:</strong></td>
                            <td className="text-break">
                              <code>{certificate.issuer_organization || 'N/A'}</code>
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Issuer DN:</strong></td>
                            <td className="text-break">
                              <code>{certificate.issuer_dn || 'N/A'}</code>
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Fingerprint:</strong></td>
                            <td>
                              <code className="small">{certificate.fingerprint_hash || 'N/A'}</code>
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Serial Number:</strong></td>
                            <td>
                              <code className="small">{certificate.serial_number || 'N/A'}</code>
                            </td>
                          </tr>
                        </tbody>
                      </Table>
                    </Col>
                    <Col md={6}>
                      <Table borderless size="sm">
                        <tbody>
                          <tr>
                            <td><strong>Valid From:</strong></td>
                            <td>
                              {certificate.valid_from ? (
                                <Badge bg="success">{formatUrlDate(certificate.valid_from)}</Badge>
                              ) : (
                                <span className="text-muted">N/A</span>
                              )}
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Valid Until:</strong></td>
                            <td>
                              {certificate.valid_until ? (
                                <Badge bg={
                                  new Date(certificate.valid_until) < new Date() ? 'danger' : 'success'
                                }>
                                  {formatUrlDate(certificate.valid_until)}
                                </Badge>
                              ) : (
                                <span className="text-muted">N/A</span>
                              )}
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Status:</strong></td>
                            <td>
                              {certificate.valid_until ? (
                                new Date(certificate.valid_until) < new Date() ? (
                                  <Badge bg="danger">Expired</Badge>
                                ) : (
                                  <Badge bg="success">Valid</Badge>
                                )
                              ) : (
                                <span className="text-muted">Unknown</span>
                              )}
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Created:</strong></td>
                            <td className="text-muted">
                              {formatUrlDate(certificate.created_at)}
                            </td>
                          </tr>
                        </tbody>
                      </Table>
                    </Col>
                  </Row>
                ) : (
                  <Alert variant="warning" className="py-2 mb-0">
                    <i className="fas fa-exclamation-triangle me-2"></i>
                    Certificate information not available or failed to load.
                  </Alert>
                )}
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Screenshots Section */}
      {viewMode === 'detail' && (
        <Row>
          <Col>
            <Card className="dashboard-panel mb-4">
              <Card.Header>
                <h5 className="mb-0">📸 Screenshots</h5>
              </Card.Header>
              <Card.Body>
                <ScreenshotsViewer url={url?.url} programName={url?.program_name} />
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Notes Section */}
      <Row>
        <Col>
          <NotesSection
            assetType="Typosquat URL"
            assetId={url._id}
            currentNotes={url.notes || ''}
            apiUpdateFunction={typosquatAPI.updateUrlNotes}
            onNotesUpdate={handleNotesUpdate}
            cardClassName="dashboard-panel"
          />
        </Col>
      </Row>

      {/* Full URL JSON */}
      <Row>
        <Col>
          <Card className="dashboard-panel mb-4">
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h6 className="mb-0">Full URL (JSON)</h6>
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
                  {JSON.stringify(url, null, 2)}
                </pre>
              </Card.Body>
            </Collapse>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default TyposquatUrlDetails;
