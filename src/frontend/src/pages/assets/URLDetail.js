import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Table, Collapse, Modal, Image } from 'react-bootstrap';
import { urlAPI, screenshotAPI, serviceAPI, certificateAPI, domainAPI, API_BASE_URL } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import SitemapTree from '../../components/SitemapTree';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle, truncateTitle } from '../../hooks/usePageTitle';

function URLDetail() {
  const { encodedUrl } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [url, setUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [relatedUrls, setRelatedUrls] = useState([]);
  const [sitemapLoading, setSitemapLoading] = useState(false);
  const [screenshots, setScreenshots] = useState([]);
  const [screenshotsLoading, setScreenshotsLoading] = useState(false);
  const [showScreenshotModal, setShowScreenshotModal] = useState(false);
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    json: false
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [relatedCertificate, setRelatedCertificate] = useState(null);
  const [relatedServices, setRelatedServices] = useState([]);
  const [relatedSubdomain, setRelatedSubdomain] = useState(null);
  const [relatedAssetsLoading, setRelatedAssetsLoading] = useState(false);

  usePageTitle(formatPageTitle(url?.url ? truncateTitle(url.url) : null, 'URL'));

  // Function to fetch related assets (certificate, services, subdomain)
  const fetchRelatedAssets = async (urlData) => {
    const serviceIds = urlData?.service_ids || (urlData?.service_id ? [urlData.service_id] : []);
    if (!urlData?.certificate_id && serviceIds.length === 0 && !urlData?.subdomain_id) {
      return;
    }
    setRelatedAssetsLoading(true);
    try {
      const certPromise = urlData.certificate_id ? certificateAPI.getById(urlData.certificate_id) : Promise.resolve(null);
      const servicePromises = serviceIds.map(id => serviceAPI.getById(id));
      const subPromise = urlData.subdomain_id ? domainAPI.getById(urlData.subdomain_id) : Promise.resolve(null);
      const [certData, ...svcResults] = await Promise.allSettled([certPromise, ...servicePromises, subPromise]);
      setRelatedCertificate(certData.status === 'fulfilled' && certData.value ? certData.value : null);
      const services = svcResults
        .slice(0, -1)
        .filter(r => r.status === 'fulfilled' && r.value)
        .map(r => r.value);
      setRelatedServices(services);
      const subData = svcResults[svcResults.length - 1];
      setRelatedSubdomain(subData.status === 'fulfilled' && subData.value ? subData.value : null);
    } catch (err) {
      console.warn('Error fetching related assets:', err);
    } finally {
      setRelatedAssetsLoading(false);
    }
  };

  // Function to fetch screenshots for a URL
  const fetchScreenshots = async (targetUrl) => {
    try {
      setScreenshotsLoading(true);
      
      // Normalize the URL (remove trailing slash for consistency)
      const normalizedUrl = targetUrl.endsWith('/') ? targetUrl.slice(0, -1) : targetUrl;
      const urlWithSlash = normalizedUrl + '/';
      
      
      // Try the normalized URL first (without trailing slash)
      let data = await screenshotAPI.searchScreenshots({ exact_match: normalizedUrl, page: 1, page_size: 10 });
      
      if (data.items && data.items.length > 0) {
        setScreenshots(data.items);
        return;
      }
      
      // If no results, try with trailing slash
      data = await screenshotAPI.searchScreenshots({ exact_match: urlWithSlash, page: 1, page_size: 10 });
      setScreenshots(data.items || []);
      
    } catch (err) {
      console.warn('Error fetching screenshots:', err);
      setScreenshots([]);
    } finally {
      setScreenshotsLoading(false);
    }
  };
  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      // Could add a toast notification here
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  }
  useEffect(() => {
    const fetchUrl = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        const response = idParam
          ? await urlAPI.getById(idParam)
          : await urlAPI.getByUrl(decodeURIComponent(encodedUrl || ''));
        setUrl(response);
        setError(null);
        
        // Fetch related assets (certificate, services, subdomain)
        const hasServices = (response?.service_ids?.length > 0) || response?.service_id;
        if (response && (response.certificate_id || hasServices || response.subdomain_id)) {
          fetchRelatedAssets(response);
        }
        
        // Fetch screenshots for this URL
        if (response && response.url) {
          await fetchScreenshots(response.url);
        }
        
        // Fetch related URLs for sitemap
        if (response && response.url) {
          setSitemapLoading(true);
          try {
            const parsedUrl = parseUrl(response.url);
            if (parsedUrl) {
              // Use the port from the URL object if available, or from parsed URL
              const urlPort = response.port || parsedUrl.port;
              const scheme = response.scheme || parsedUrl.protocol.replace(':', '');
              const host = response.host || parsedUrl.hostname;
              
              
              const related = await urlAPI.getRelatedUrls(
                scheme,
                host,
                urlPort,
                response.url
              );
              
              setRelatedUrls(related);
            }
          } catch (sitemapErr) {
            console.warn('Failed to fetch related URLs for sitemap:', sitemapErr);
            setRelatedUrls([]);
          } finally {
            setSitemapLoading(false);
          }
        }
      } catch (err) {
        setError('Failed to fetch URL details: ' + err.message);
        setUrl(null);
      } finally {
        setLoading(false);
      }
    };

    if (encodedUrl || new URLSearchParams(location.search).get('id')) {
      fetchUrl();
    }
  }, [encodedUrl, location.search]);

  const formatUrlDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const handleNotesUpdate = (newNotes) => {
    // Update the URL object with new notes
    setUrl(prev => ({ ...prev, notes: newNotes }));
  };

  // Screenshot modal handlers
  const handleScreenshotClick = (screenshot) => {
    setSelectedScreenshot(screenshot);
    setShowScreenshotModal(true);
  };

  const handleCloseScreenshotModal = () => {
    setShowScreenshotModal(false);
    setSelectedScreenshot(null);
  };

  // Delete URL handlers
  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!url) return;
    
    try {
      setDeleting(true);
      await urlAPI.delete(url.id || url._id);
      setShowDeleteModal(false);
      navigate('/assets/urls');
    } catch (err) {
      setError('Failed to delete URL: ' + err.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  // Get screenshot image URL (include auth token for img src - browser can't set headers)
  const getScreenshotUrl = (screenshot) => {
    const baseUrl = `${API_BASE_URL}/assets/screenshot/${screenshot.file_id}`;
    const token = localStorage.getItem('access_token');
    if (token) {
      return `${baseUrl}?token=${encodeURIComponent(token)}`;
    }
    return baseUrl;
  };

  // Format screenshot metadata
  const formatScreenshotDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'N/A';
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
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
    if (url) {
      navigator.clipboard.writeText(JSON.stringify(url, null, 2));
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

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading URL details...</p>
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
        <Button variant="outline-primary" onClick={() => navigate('/assets/urls')}>
          ← Back to URLs
        </Button>
      </Container>
    );
  }

  if (!url) {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>URL Not Found</Alert.Heading>
          The requested URL could not be found.
        </Alert>
        <Button variant="outline-primary" onClick={() => navigate('/assets/urls')}>
          ← Back to URLs
        </Button>
      </Container>
    );
  }

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
    
    // Check if we have a detailed redirect_chain (array of objects)
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
              <Badge bg={getStatusBadgeVariant(step.http_status_code || step.status_code)} className="me-2">
                {step.http_status_code || step.status_code || 'N/A'}
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
    
    // Fallback: Check if we have final_url different from original URL
    if (url.final_url && url.final_url !== url.url) {
      return (
        <ul className="list-unstyled mb-0">
          <li className="mb-2 d-flex align-items-center flex-wrap">
            <Badge bg="secondary" className="me-2" style={{ minWidth: '50px' }}>
              {url.method || 'GET'}
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
    
    // Check for redirect_chains as simple string array (legacy format)
    if (url.redirect_chains && Array.isArray(url.redirect_chains) && url.redirect_chains.length > 0) {
      return (
        <ul className="list-unstyled mb-0">
          {url.redirect_chains.map((redirectUrl, idx) => (
            <li key={idx} className="mb-2 d-flex align-items-center flex-wrap">
              <Badge bg="secondary" className="me-2" style={{ minWidth: '50px' }}>
                GET
              </Badge>
              <a 
                href={redirectUrl} 
                target="_blank" 
                rel="noopener noreferrer" 
                className="text-break"
                title={redirectUrl}
              >
                {truncateUrl(redirectUrl)}
              </a>
              {idx < url.redirect_chains.length - 1 && (
                <i className="fas fa-arrow-right mx-2 text-muted"></i>
              )}
            </li>
          ))}
        </ul>
      );
    }
    
    // No redirect chain available
    return (
      <Alert variant="info" className="py-2 mb-0">
        No redirect chain recorded.
      </Alert>
    );
  };

  const parsedUrl = parseUrl(url.url);

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <div>
              <h1>🔗 URL Details</h1>
              <p className="text-muted">URL information and reconnaissance data</p>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={handleDeleteClick}
                className="me-2"
              >
                🗑️ Delete
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/assets/urls')}>
                ← Back to URLs
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={handleDeleteCancel} centered>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete URL</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this URL?</p>
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
          <Card className="mb-4">
            <Card.Header>
              <h5 className="mb-0">🌐 URL Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>Full URL:</strong></td>
                    <td>
                      <a href={url.url} target="_blank" rel="noopener noreferrer" className="text-break">
                        {url.url}
                      </a>
                      <button
                        className="btn btn-sm btn-outline-secondary ms-2"
                        onClick={() => copyToClipboard(url.url)}
                        title="Copy to clipboard"
                      >
                        📋
                      </button>
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
                        <td><code>{parsedUrl.hostname}</code></td>
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
          <Card className="mb-4">
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
                        <Badge bg={url.http_status_code < 300 ? 'success' : url.http_status_code < 400 ? 'warning' : 'danger'}>
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

      {/* Related Assets: Certificate, Services, Subdomain */}
      {(url.certificate_id || (url.service_ids && url.service_ids.length > 0) || url.service_id || url.subdomain_id) && (
        <Row>
          <Col>
            <Card className="mb-4">
              <Card.Header>
                <h5 className="mb-0">🔗 Related Assets</h5>
              </Card.Header>
              <Card.Body>
                {relatedAssetsLoading ? (
                  <div className="text-center py-3">
                    <Spinner animation="border" size="sm" />
                    <span className="ms-2">Loading related assets...</span>
                  </div>
                ) : (
                  <Row className="flex-nowrap overflow-x-auto g-2">
                    {url.certificate_id && (
                      <Col className="flex-shrink-0" style={{ minWidth: '220px' }}>
                        <Card className="h-100 border-0 bg-light">
                          <Card.Body>
                            <h6 className="text-uppercase small fw-semibold text-muted mb-2 pb-1 border-bottom">
                              <i className="fas fa-certificate me-2"></i>Certificate
                            </h6>
                            <p className="mb-1 small">
                              <Link to={`/assets/certificates/details?id=${encodeURIComponent(url.certificate_id)}`} className="text-decoration-none">
                                {relatedCertificate ? (relatedCertificate.subject_cn || relatedCertificate.subject_dn || (relatedCertificate.subject_an?.[0]) || 'N/A') : 'N/A'}
                              </Link>
                            </p>
                            {relatedCertificate?.valid_until && (
                              <p className="mb-2 small text-muted">
                                Valid until: {formatUrlDate(relatedCertificate.valid_until)}
                              </p>
                            )}
                          </Card.Body>
                        </Card>
                      </Col>
                    )}
                    {((url.service_ids || (url.service_id ? [url.service_id] : [])).length > 0) && (
                      <Col className="flex-shrink-0" style={{ minWidth: '220px' }}>
                        <Card className="h-100 border-0 bg-light">
                          <Card.Body>
                            <h6 className="text-uppercase small fw-semibold text-muted mb-2 pb-1 border-bottom">
                              <i className="fas fa-server me-2"></i>Services
                            </h6>
                            <div className="d-flex flex-column gap-1">
                              {(url.service_ids || (url.service_id ? [url.service_id] : [])).map((serviceId) => {
                                const svc = relatedServices.find(s => (s.id || s._id) === serviceId);
                                return (
                                  <Link key={serviceId} to={`/assets/services/details?id=${encodeURIComponent(serviceId)}`} className="text-decoration-none small">
                                    {svc ? `${svc.ip}:${svc.port}` : 'N/A'}
                                  </Link>
                                );
                              })}
                            </div>
                          </Card.Body>
                        </Card>
                      </Col>
                    )}
                    {(() => {
                      const uniqueIps = relatedServices
                        ? [...new Map(relatedServices.filter(s => s.ip_id).map(s => [s.ip_id, { ip_id: s.ip_id, ip: s.ip }])).values()]
                        : [];
                      return uniqueIps.length > 0 && (
                        <Col className="flex-shrink-0" style={{ minWidth: '220px' }}>
                          <Card className="h-100 border-0 bg-light">
                            <Card.Body>
                              <h6 className="text-uppercase small fw-semibold text-muted mb-2 pb-1 border-bottom">
                                <i className="fas fa-network-wired me-2"></i>IPs
                              </h6>
                              <div className="d-flex flex-column gap-1">
                                {uniqueIps.map(({ ip_id, ip }) => (
                                  <Link key={ip_id} to={`/assets/ips/details?id=${encodeURIComponent(ip_id)}`} className="text-decoration-none small">
                                    {ip}
                                  </Link>
                                ))}
                              </div>
                            </Card.Body>
                          </Card>
                        </Col>
                      );
                    })()}
                    {url.subdomain_id && (
                      <Col className="flex-shrink-0" style={{ minWidth: '220px' }}>
                        <Card className="h-100 border-0 bg-light">
                          <Card.Body>
                            <h6 className="text-uppercase small fw-semibold text-muted mb-2 pb-1 border-bottom">
                              <i className="fas fa-globe me-2"></i>Subdomain
                            </h6>
                            <p className="mb-0 small">
                              <Link to={`/assets/subdomains/details?id=${encodeURIComponent(url.subdomain_id)}`} className="text-decoration-none">
                                {relatedSubdomain ? relatedSubdomain.name : 'N/A'}
                              </Link>
                            </p>
                          </Card.Body>
                        </Card>
                      </Col>
                    )}
                  </Row>
                )}
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {url.technologies && url.technologies.length > 0 && (
        <Row>
          <Col>
            <Card className="mb-4">
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
          <Card className="mb-4">
            <Card.Header>
              <h5 className="mb-0">🔄 Redirect Chain</h5>
            </Card.Header>
            <Card.Body>
              {renderRedirectChain()}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Screenshots Section */}
      <Row>
        <Col>
          <Card className="mb-4">
            <Card.Header>
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">📸 Screenshots</h5>
                {screenshots.some(s => s.metadata?.capture_count > 1) && (
                  <Badge bg="info" className="small">
                    <i className="fas fa-copy me-1"></i>
                    Contains duplicates
                  </Badge>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {screenshotsLoading ? (
                <div className="text-center">
                  <Spinner animation="border" size="sm" />
                  <span className="ms-2">Loading screenshots...</span>
                </div>
              ) : screenshots.length > 0 ? (
                <Row>
                  {screenshots.map((screenshot, idx) => (
                    <Col key={idx} md={4} lg={3} className="mb-3">
                      <Card className={`h-100 ${screenshot.metadata?.capture_count > 1 ? 'border-info' : ''}`}>
                        <div 
                          style={{ 
                            height: '200px', 
                            overflow: 'hidden',
                            cursor: 'pointer',
                            position: 'relative'
                          }}
                          onClick={() => handleScreenshotClick(screenshot)}
                        >
                          <Image 
                            src={getScreenshotUrl(screenshot)} 
                            alt={`Screenshot of ${url.url}`}
                            style={{ 
                              width: '100%', 
                              height: '100%', 
                              objectFit: 'cover',
                              transition: 'transform 0.2s ease'
                            }}
                            onMouseEnter={(e) => e.target.style.transform = 'scale(1.05)'}
                            onMouseLeave={(e) => e.target.style.transform = 'scale(1)'}
                          />
                          <div 
                            className="position-absolute top-0 end-0 m-2"
                            style={{ 
                              backgroundColor: 'rgba(0,0,0,0.7)', 
                              color: 'white', 
                              padding: '4px 8px', 
                              borderRadius: '4px',
                              fontSize: '0.75rem'
                            }}
                          >
                            🔍 Click to view
                          </div>
                          {screenshot.metadata?.capture_count > 1 && (
                            <div 
                              className="position-absolute top-0 start-0 m-2"
                              style={{ 
                                backgroundColor: 'rgba(13, 202, 240, 0.9)', 
                                color: 'white', 
                                padding: '4px 8px', 
                                borderRadius: '4px',
                                fontSize: '0.75rem',
                                fontWeight: 'bold'
                              }}
                              title={`This screenshot has been captured ${screenshot.metadata.capture_count} times`}
                            >
                              📸 {screenshot.metadata.capture_count}x
                            </div>
                          )}
                        </div>
                        <Card.Body className="p-2">
                          <div className="small text-muted">
                            <div><strong>Size:</strong> {formatFileSize(screenshot.file_size)}</div>
                            <div><strong>First Captured:</strong> {formatScreenshotDate(screenshot.upload_date)}</div>
                            {screenshot.metadata?.last_captured_at && screenshot.metadata.last_captured_at !== screenshot.upload_date && (
                              <div><strong>Last Captured:</strong> {formatScreenshotDate(screenshot.metadata.last_captured_at)}</div>
                            )}
                            {screenshot.metadata?.capture_count && screenshot.metadata.capture_count > 1 && (
                              <div>
                                <strong>Captures:</strong> 
                                <Badge bg="info" className="ms-1 small">
                                  {screenshot.metadata.capture_count}x
                                </Badge>
                              </div>
                            )}
                          </div>
                        </Card.Body>
                      </Card>
                    </Col>
                  ))}
                </Row>
              ) : (
                <Alert variant="info" className="py-2 mb-0">
                  <i className="fas fa-info-circle me-2"></i>
                  No screenshots available for this URL.
                </Alert>
              )}
              
              {screenshots.length > 0 && screenshots.some(s => s.metadata?.capture_count > 1) && (
                <Alert variant="light" className="mt-3 py-2 small">
                  <i className="fas fa-info-circle me-2 text-info"></i>
                  <strong>Duplicate Detection:</strong> Screenshots marked with 📸 counts have been captured multiple times. 
                  Only one copy is stored to save space, but timestamps track when duplicates were detected.
                </Alert>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Sitemap Section */}
      <Row>
        <Col>
          <Card className="mb-4">
            <Card.Header>
              <h5 className="mb-0">🗺️ Sitemap</h5>
            </Card.Header>
            <Card.Body>
              {sitemapLoading ? (
                <div className="text-center">
                  <Spinner animation="border" size="sm" />
                  <span className="ms-2">Loading sitemap...</span>
                </div>
              ) : relatedUrls.length > 0 ? (
                <SitemapTree urls={relatedUrls} />
              ) : (
                <p className="text-muted mb-0">No other URLs found for this base path.</p>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <NotesSection
            assetType="URL"
            assetId={url._id}
            currentNotes={url.notes || ''}
            apiUpdateFunction={urlAPI.updateNotes}
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
                    <li><strong>Object ID:</strong> <code>{url._id}</code></li>
                                    <li><strong>First Discovered:</strong> {formatUrlDate(url.created_at)}</li>
                <li><strong>Last Seen:</strong> {formatUrlDate(url.updated_at)}</li>
                  </ul>
                </Col>
                <Col md={6}>
                  <h6>Statistics</h6>
                  <ul className="list-unstyled">
                    <li><strong>Technologies Count:</strong> {url.technologies ? url.technologies.length : 0}</li>
                    <li><strong>Has Redirects:</strong> {url.redirect_chains && url.redirect_chains.length > 0 ? 'Yes' : 'No'}</li>
                    <li><strong>Secure Protocol:</strong> {parsedUrl && parsedUrl.protocol === 'https:' ? 'Yes' : 'No'}</li>
                  </ul>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Full URL JSON */}
      <Row>
        <Col>
          <Card className="mb-4">
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

      {/* Screenshot Modal */}
      <Modal 
        show={showScreenshotModal} 
        onHide={handleCloseScreenshotModal} 
        size="xl"
        centered
      >
        <Modal.Header closeButton>
          <Modal.Title>📸 Screenshot Preview</Modal.Title>
        </Modal.Header>
        <Modal.Body className="text-center">
          {selectedScreenshot && (
            <>
              <div className="mb-3">
                <Image 
                  src={getScreenshotUrl(selectedScreenshot)} 
                  alt={`Screenshot of ${url.url}`}
                  style={{ 
                    maxWidth: '100%', 
                    maxHeight: '70vh',
                    border: '1px solid #dee2e6',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
                  }}
                  fluid
                />
              </div>
              <div className="text-start">
                <Row>
                  <Col md={6}>
                    <h6>📋 Screenshot Details</h6>
                    <Table borderless size="sm">
                      <tbody>
                        <tr>
                          <td><strong>URL:</strong></td>
                          <td className="text-break">{selectedScreenshot.metadata?.url || url.url}</td>
                        </tr>
                        <tr>
                          <td><strong>File Size:</strong></td>
                          <td>{formatFileSize(selectedScreenshot.file_size)}</td>
                        </tr>
                        <tr>
                          <td><strong>Content Type:</strong></td>
                          <td><code>{selectedScreenshot.content_type}</code></td>
                        </tr>
                        <tr>
                          <td><strong>Filename:</strong></td>
                          <td><code>{selectedScreenshot.filename}</code></td>
                        </tr>
                        {selectedScreenshot.metadata?.capture_count && (
                          <tr>
                            <td><strong>Capture Count:</strong></td>
                            <td>
                              <Badge bg={selectedScreenshot.metadata.capture_count > 1 ? "info" : "secondary"}>
                                {selectedScreenshot.metadata.capture_count}x
                              </Badge>
                              {selectedScreenshot.metadata.capture_count > 1 && (
                                <small className="text-muted ms-2">(duplicate detected)</small>
                              )}
                            </td>
                          </tr>
                        )}
                        {selectedScreenshot.metadata?.image_hash && (
                          <tr>
                            <td><strong>Image Hash:</strong></td>
                            <td>
                              <code className="small text-break">
                                {selectedScreenshot.metadata.image_hash.substring(0, 16)}...
                              </code>
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </Table>
                  </Col>
                  <Col md={6}>
                    <h6>⚙️ Workflow Information</h6>
                    <Table borderless size="sm">
                      <tbody>
                        <tr>
                          <td><strong>Program:</strong></td>
                          <td>
                            {selectedScreenshot.metadata?.program_name ? (
                              <Badge bg="primary">{selectedScreenshot.metadata.program_name}</Badge>
                            ) : (
                              <span className="text-muted">N/A</span>
                            )}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Step Name:</strong></td>
                          <td>
                            {selectedScreenshot.metadata?.step_name ? (
                              <Badge bg="secondary">{selectedScreenshot.metadata.step_name}</Badge>
                            ) : (
                              <span className="text-muted">N/A</span>
                            )}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Captured:</strong></td>
                          <td>
                            {selectedScreenshot.metadata?.capture_timestamps && selectedScreenshot.metadata.capture_timestamps.length > 1 ? (
                              <div className="small">
                                {selectedScreenshot.metadata.capture_timestamps.map((timestamp, idx) => (
                                  <div key={idx} className="text-muted">
                                    <Badge bg={idx === 0 ? "success" : "info"} className="me-2 small">
                                      {idx + 1}
                                    </Badge>
                                    {formatScreenshotDate(timestamp)}
                                    {idx === 0 && <span className="ms-2 small text-success">(First)</span>}
                                    {idx === selectedScreenshot.metadata.capture_timestamps.length - 1 && idx > 0 && (
                                      <span className="ms-2 small text-warning">(Latest)</span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div className="text-muted">
                                <Badge bg="success" className="me-2 small">1</Badge>
                                {formatScreenshotDate(selectedScreenshot.upload_date)}
                                <span className="ms-2 small text-success">(Single capture)</span>
                              </div>
                            )}
                          </td>
                        </tr>
                      </tbody>
                    </Table>
                  </Col>
                </Row>
              </div>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-primary" onClick={() => window.open(getScreenshotUrl(selectedScreenshot), '_blank')}>
            🔗 Open in New Tab
          </Button>
          <Button variant="secondary" onClick={handleCloseScreenshotModal}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default URLDetail;