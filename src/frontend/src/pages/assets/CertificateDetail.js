import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Table, Collapse, Modal } from 'react-bootstrap';
import { certificateAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate, isExpired, isExpiringSoon } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle, truncateTitle } from '../../hooks/usePageTitle';

function CertificateDetail() {
  const { encodedSubjectDN } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [certificate, setCertificate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    json: false
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  usePageTitle(
    formatPageTitle(
      certificate?.subject_dn ? truncateTitle(certificate.subject_dn) : null,
      'Certificate'
    )
  );

  useEffect(() => {
    const fetchCertificate = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        if (idParam) {
          const data = await certificateAPI.getById(idParam);
          setCertificate(data);
        } else {
          const decodedSubjectDN = decodeURIComponent(encodedSubjectDN || '');
          const response = await certificateAPI.getBySubjectDN(decodedSubjectDN);
          setCertificate(response);
        }
        setError(null);
      } catch (err) {
        setError('Failed to fetch certificate details: ' + err.message);
        setCertificate(null);
      } finally {
        setLoading(false);
      }
    };

    if (encodedSubjectDN || new URLSearchParams(location.search).get('id')) {
      fetchCertificate();
    }
  }, [encodedSubjectDN, location.search]);

  const formatCertDetailDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const handleNotesUpdate = (newNotes) => {
    // Update the certificate object with new notes
    setCertificate(prev => ({ ...prev, notes: newNotes }));
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
    if (certificate) {
      navigator.clipboard.writeText(JSON.stringify(certificate, null, 2));
    }
  };

  // Delete certificate handlers
  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!certificate) return;
    
    try {
      setDeleting(true);
      await certificateAPI.delete(certificate.id || certificate._id);
      setShowDeleteModal(false);
      navigate('/assets/certificates');
    } catch (err) {
      setError('Failed to delete certificate: ' + err.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  const formatCertDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString, 'MMMM dd, yyyy');
  };

  const getCertificateStatusBadge = (cert) => {
    if (isExpired(cert.valid_until)) {
      return <Badge bg="danger">Expired</Badge>;
    } else if (isExpiringSoon(cert.valid_until)) {
      return <Badge bg="warning">Expires Soon</Badge>;
    } else {
      return <Badge bg="success">Valid</Badge>;
    }
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading certificate details...</p>
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
        <Button variant="outline-primary" onClick={() => navigate('/assets/certificates')}>
          ← Back to Certificates
        </Button>
      </Container>
    );
  }

  if (!certificate) {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>Certificate Not Found</Alert.Heading>
          The requested certificate could not be found.
        </Alert>
        <Button variant="outline-primary" onClick={() => navigate('/assets/certificates')}>
          ← Back to Certificates
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
              <h1>🔒 Certificate Details</h1>
              <p className="text-muted">SSL/TLS certificate information and analysis</p>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={handleDeleteClick}
                className="me-2"
              >
                🗑️ Delete
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/assets/certificates')}>
                ← Back to Certificates
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={handleDeleteCancel} centered>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete Certificate</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this certificate?</p>
          <p><strong>Subject DN:</strong> {certificate.subject_dn}</p>
          <p className="text-danger">
            <strong>Warning:</strong> This action cannot be undone. The certificate will be permanently removed from the database.
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
              'Delete Certificate'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      <Row>
        <Col md={8}>
          <Card className="mb-4">
            <Card.Header>
              <h5 className="mb-0">📜 Certificate Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>Subject DN:</strong></td>
                    <td className="text-break">{certificate.subject_dn}</td>
                  </tr>
                  <tr>
                    <td><strong>Issuer DN:</strong></td>
                    <td className="text-break">
                      {certificate.issuer_dn || <span className="text-muted">-</span>}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Serial Number:</strong></td>
                    <td>
                      {certificate.serial_number	 ? (
                        <code>{certificate.serial_number}</code>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Fingerprint Hash:</strong></td>
                    <td>
                      {certificate.fingerprint_hash ? (
                        <code className="text-break">{certificate.fingerprint_hash}</code>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
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
                    <td><strong>Status:</strong></td>
                    <td>{getCertificateStatusBadge(certificate)}</td>
                  </tr>
                  <tr>
                    <td><strong>Program:</strong></td>
                    <td>
                      {certificate.program_name ? (
                        <Badge bg="primary">{certificate.program_name}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
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
        <Col md={6}>
          <Card className="mb-4">
            <Card.Header>
              <h5 className="mb-0">📅 Validity Period</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>Valid From:</strong></td>
                    <td>{formatCertDate(certificate.valid_from)}</td>
                  </tr>
                  <tr>
                    <td><strong>Valid Until:</strong></td>
                    <td>
                      <span className={isExpired(certificate.valid_until) ? 'text-danger' : 
                                     isExpiringSoon(certificate.valid_until) ? 'text-warning' : ''}>
                        {formatCertDate(certificate.valid_until)}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>

        <Col md={6}>
          <Card className="mb-4">
            <Card.Header>
              <h5 className="mb-0">🕒 Discovery Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td><strong>First Discovered:</strong></td>
                    <td>{formatCertDetailDate(certificate.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Last Updated:</strong></td>
                    <td>{formatCertDetailDate(certificate.updated_at)}</td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {certificate.subject_an && certificate.subject_an.length > 0 && (
        <Row>
          <Col>
            <Card className="mb-4">
              <Card.Header>
                <h5 className="mb-0">🌐 Subject Alternative Names (SAN)</h5>
              </Card.Header>
              <Card.Body>
                <div>
                  {certificate.subject_an.map((san, idx) => (
                    <Badge key={idx} bg="secondary" className="me-1 mb-1">
                      {san}
                    </Badge>
                  ))}
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      <Row>
        <Col>
          <NotesSection
            assetType="certificate"
            assetId={certificate.id || certificate._id}
            currentNotes={certificate.notes || ''}
            apiUpdateFunction={certificateAPI.updateNotes}
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
                  <h6>Certificate Details</h6>
                  <ul className="list-unstyled">
                    <li><strong>Object ID:</strong> <code>{certificate._id}</code></li>
                    <li><strong>Has SAN Names:</strong> {certificate.subject_an && certificate.subject_an.length > 0 ? 'Yes' : 'No'}</li>
                    <li><strong>SAN Count:</strong> {certificate.subject_an ? certificate.subject_an.length : 0}</li>
                  </ul>
                </Col>
                <Col md={6}>
                  <h6>Security Information</h6>
                  <ul className="list-unstyled">
                    <li><strong>Is Valid:</strong> {!isExpired(certificate.valid_until) ? 'Yes' : 'No'}</li>
                    <li><strong>Expires Soon:</strong> {isExpiringSoon(certificate.valid_until) ? 'Yes' : 'No'}</li>
                  </ul>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Full Certificate JSON */}
      <Row>
        <Col>
          <Card className="mb-4">
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h6 className="mb-0">Full Certificate (JSON)</h6>
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
                  {JSON.stringify(certificate, null, 2)}
                </pre>
              </Card.Body>
            </Collapse>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default CertificateDetail;