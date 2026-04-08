import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Button, Badge } from 'react-bootstrap';
import api from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

const WPScanFindingDetail = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [finding, setFinding] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  usePageTitle(formatPageTitle(finding?.title || finding?.item_name, 'WPScan'));

  const severityColors = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: 'secondary',
    info: 'primary',
    unknown: 'dark'
  };

  const itemTypeColors = {
    wordpress: 'primary',
    plugin: 'success',
    theme: 'info',
    finding: 'warning',
    enumeration: 'secondary'
  };

  useEffect(() => {
    const loadFinding = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        if (idParam) {
          const data = await api.findings.wpscan.getByIdUnified(idParam);
          setFinding(data);
        } else {
          setError('Finding ID not provided');
        }
      } catch (err) {
        console.error('Error loading WPScan finding:', err);
        if (err.response?.status === 404) {
          setError('WPScan finding not found');
        } else {
          setError('Failed to load WPScan finding details');
        }
      } finally {
        setLoading(false);
      }
    };

    const params = new URLSearchParams(location.search);
    if (params.get('id')) {
      loadFinding();
    }
  }, [location.search]);

  const formatWPScanDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const handleNotesUpdate = (newNotes) => {
    setFinding(prev => ({ ...prev, notes: newNotes }));
  };

  const handleDelete = async () => {
    try {
      setDeleting(true);
      const params = new URLSearchParams(location.search);
      const idParam = params.get('id');
      
      await api.findings.wpscan.delete(idParam);
      setShowDeleteModal(false);
      navigate('/findings/wpscan');
    } catch (err) {
      console.error('Error deleting WPScan finding:', err);
      alert('Failed to delete WPScan finding: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="container-fluid mt-4">
        <div className="text-center">
          <div className="spinner-border" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
          <p className="mt-2">Loading WPScan finding details...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container-fluid mt-4">
        <div className="alert alert-danger" role="alert">
          <h5 className="alert-heading">Error</h5>
          <p className="mb-0">{error}</p>
          <hr />
          <Link to="/findings/wpscan" className="btn btn-outline-danger">
            Back to WPScan Findings
          </Link>
        </div>
      </div>
    );
  }

  if (!finding) {
    return (
      <div className="container-fluid mt-4">
        <div className="alert alert-warning" role="alert">
          <h5 className="alert-heading">Not Found</h5>
          <p className="mb-0">The requested WPScan finding could not be found.</p>
          <hr />
          <Link to="/findings/wpscan" className="btn btn-outline-warning">
            Back to WPScan Findings
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container-fluid mt-4">
      <div className="row mb-4">
        <div className="col">
          <nav aria-label="breadcrumb">
            <ol className="breadcrumb">
              <li className="breadcrumb-item">
                <Link to="/findings/wpscan">WPScan Findings</Link>
              </li>
              <li className="breadcrumb-item active" aria-current="page">
                {finding.title || finding.item_name}
              </li>
            </ol>
          </nav>
          
          <div className="d-flex justify-content-between align-items-start">
            <div>
              <h2>{finding.title || finding.item_name}</h2>
              <p className="text-muted mb-2">
                WPScan finding discovered on {formatWPScanDate(finding.created_at)}
              </p>
            </div>
            <div>
              <Button 
                variant="outline-danger" 
                onClick={() => setShowDeleteModal(true)}
                className="me-2"
              >
                🗑️ Delete
              </Button>
              <Button variant="outline-primary" onClick={() => navigate('/findings/wpscan')}>
                ← Back to WPScan Findings
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="row">
        <div className="col-lg-8">
          <div className="card dashboard-panel">
            <div className="card-header">
              <h5 className="card-title mb-0">Finding Details</h5>
            </div>
            <div className="card-body">
              <dl className="row">
                <dt className="col-sm-3">Severity</dt>
                <dd className="col-sm-9">
                  <span className={`badge bg-${severityColors[finding.severity?.toLowerCase()] || 'secondary'}`}>
                    {finding.severity?.toUpperCase() || 'N/A'}
                  </span>
                </dd>

                <dt className="col-sm-3">Item Name</dt>
                <dd className="col-sm-9">
                  <code>{finding.item_name}</code>
                  <button
                    className="btn btn-sm btn-outline-secondary ms-2"
                    onClick={() => copyToClipboard(finding.item_name)}
                    title="Copy to clipboard"
                  >
                    📋
                  </button>
                </dd>

                <dt className="col-sm-3">Item Type</dt>
                <dd className="col-sm-9">
                  <span className={`badge bg-${itemTypeColors[finding.item_type] || 'secondary'}`}>
                    {finding.item_type || 'N/A'}
                  </span>
                </dd>

                <dt className="col-sm-3">Vulnerability Type</dt>
                <dd className="col-sm-9">
                  {finding.vulnerability_type || <span className="text-muted">N/A</span>}
                </dd>

                {finding.title && (
                  <>
                    <dt className="col-sm-3">Title</dt>
                    <dd className="col-sm-9">{finding.title}</dd>
                  </>
                )}

                {finding.description && (
                  <>
                    <dt className="col-sm-3">Description</dt>
                    <dd className="col-sm-9">
                      <div style={{ whiteSpace: 'pre-wrap' }}>{finding.description}</div>
                    </dd>
                  </>
                )}

                {finding.fixed_in && (
                  <>
                    <dt className="col-sm-3">Fixed In</dt>
                    <dd className="col-sm-9">
                      <Badge bg="success">{finding.fixed_in}</Badge>
                    </dd>
                  </>
                )}

                <dt className="col-sm-3">URL</dt>
                <dd className="col-sm-9">
                  {finding.url ? (
                    <div>
                      <a href={finding.url} target="_blank" rel="noopener noreferrer" className="text-decoration-none">
                        {finding.url}
                        <i className="bi bi-box-arrow-up-right ms-1 small"></i>
                      </a>
                      <button
                        className="btn btn-sm btn-outline-secondary ms-2"
                        onClick={() => copyToClipboard(finding.url)}
                        title="Copy to clipboard"
                      >
                        📋
                      </button>
                    </div>
                  ) : (
                    <span className="text-muted">N/A</span>
                  )}
                </dd>

                <dt className="col-sm-3">Hostname</dt>
                <dd className="col-sm-9">
                  {finding.hostname || <span className="text-muted">N/A</span>}
                </dd>

                <dt className="col-sm-3">Port</dt>
                <dd className="col-sm-9">
                  {finding.port || <span className="text-muted">N/A</span>}
                </dd>

                <dt className="col-sm-3">Scheme</dt>
                <dd className="col-sm-9">
                  {finding.scheme || <span className="text-muted">N/A</span>}
                </dd>
              </dl>
            </div>
          </div>

          {/* Vulnerability Information */}
          {(finding.cve_ids?.length > 0 || finding.references?.length > 0) && (
            <div className="card dashboard-panel mt-4">
              <div className="card-header">
                <h5 className="card-title mb-0">Vulnerability Information</h5>
              </div>
              <div className="card-body">
                {finding.cve_ids && finding.cve_ids.length > 0 && (
                  <div className="mb-3">
                    <h6>CVE IDs</h6>
                    <div>
                      {finding.cve_ids.map((cve, idx) => (
                        <Badge key={idx} bg="danger" className="me-2 mb-2">
                          <a 
                            href={`https://cve.mitre.org/cgi-bin/cvename.cgi?name=${cve}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-white text-decoration-none"
                          >
                            {cve}
                          </a>
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {finding.references && finding.references.length > 0 && (
                  <div>
                    <h6>References</h6>
                    <ul className="list-unstyled">
                      {finding.references.map((ref, idx) => (
                        <li key={idx} className="mb-2">
                          <a 
                            href={ref} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="text-decoration-none"
                          >
                            {ref}
                            <i className="bi bi-box-arrow-up-right ms-1 small"></i>
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Enumeration Data */}
          {finding.enumeration_data && Object.keys(finding.enumeration_data).length > 0 && (
            <div className="card dashboard-panel mt-4">
              <div className="card-header">
                <h5 className="card-title mb-0">Enumeration Data</h5>
              </div>
              <div className="card-body">
                {finding.enumeration_data.wordpress_version && (
                  <div className="mb-3">
                    <h6>WordPress Version</h6>
                    <Badge bg="primary">{finding.enumeration_data.wordpress_version}</Badge>
                  </div>
                )}

                {finding.enumeration_data.plugins && finding.enumeration_data.plugins.length > 0 && (
                  <div className="mb-3">
                    <h6>Discovered Plugins ({finding.enumeration_data.plugins.length})</h6>
                    <div>
                      {finding.enumeration_data.plugins.map((plugin, idx) => {
                        const version = finding.enumeration_data.plugin_versions?.[plugin];
                        return (
                          <Badge key={idx} bg="success" className="me-2 mb-2">
                            {plugin}{version ? ` (${version})` : ''}
                          </Badge>
                        );
                      })}
                    </div>
                  </div>
                )}

                {finding.enumeration_data.themes && finding.enumeration_data.themes.length > 0 && (
                  <div className="mb-3">
                    <h6>Discovered Themes ({finding.enumeration_data.themes.length})</h6>
                    <div>
                      {finding.enumeration_data.themes.map((theme, idx) => {
                        const version = finding.enumeration_data.theme_versions?.[theme];
                        return (
                          <Badge key={idx} bg="info" className="me-2 mb-2">
                            {theme}{version ? ` (${version})` : ''}
                          </Badge>
                        );
                      })}
                    </div>
                  </div>
                )}

                {finding.enumeration_data.users && finding.enumeration_data.users.length > 0 && (
                  <div className="mb-3">
                    <h6>Enumerated Users ({finding.enumeration_data.users.length})</h6>
                    <div>
                      {finding.enumeration_data.users.map((user, idx) => (
                        <Badge key={idx} bg="warning" className="me-2 mb-2">
                          {user}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Show raw JSON if there are other fields */}
                {Object.keys(finding.enumeration_data).some(key => 
                  !['wordpress_version', 'plugins', 'plugin_versions', 'themes', 'theme_versions', 'users'].includes(key)
                ) && (
                  <div className="mt-3">
                    <h6>Additional Data</h6>
                    <pre className="small bg-light p-3 rounded" style={{ maxHeight: '300px', overflowY: 'auto' }}>
                      {JSON.stringify(finding.enumeration_data, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="col-lg-4">
          <div className="card dashboard-panel">
            <div className="card-header">
              <h5 className="card-title mb-0">Metadata</h5>
            </div>
            <div className="card-body">
              <dl className="row small">
                <dt className="col-6">Created</dt>
                <dd className="col-6">{formatWPScanDate(finding.created_at)}</dd>

                <dt className="col-6">Updated</dt>
                <dd className="col-6">{formatWPScanDate(finding.updated_at)}</dd>

                <dt className="col-6">Finding ID</dt>
                <dd className="col-6">
                  <code className="small">{finding.id}</code>
                  <button
                    className="btn btn-sm btn-outline-secondary ms-1"
                    onClick={() => copyToClipboard(finding.id)}
                    title="Copy to clipboard"
                  >
                    <i className="bi bi-clipboard small"></i>
                  </button>
                </dd>

                {finding.status && (
                  <>
                    <dt className="col-6">Status</dt>
                    <dd className="col-6">
                      <Badge bg="secondary">{finding.status}</Badge>
                    </dd>
                  </>
                )}

                {finding.assigned_to && (
                  <>
                    <dt className="col-6">Assigned To</dt>
                    <dd className="col-6">{finding.assigned_to}</dd>
                  </>
                )}

                <dt className="col-6">Program</dt>
                <dd className="col-6">
                  <Badge bg="secondary">{finding.program_name || 'N/A'}</Badge>
                </dd>
              </dl>
            </div>
          </div>

          <div className="card dashboard-panel mt-4">
            <div className="card-header">
              <h5 className="card-title mb-0">Related Assets</h5>
            </div>
            <div className="card-body">
              <div className="list-group list-group-flush">
                {finding.hostname && (
                  <div className="list-group-item px-0">
                    <div className="d-flex justify-content-between align-items-center">
                      <div>
                        <h6 className="mb-1">Domain</h6>
                        <p className="mb-1 small">{finding.hostname}</p>
                      </div>
                      <Link
                        to={`/assets/domains?exact_match=${encodeURIComponent(finding.hostname)}`}
                        className="btn btn-sm btn-outline-primary"
                      >
                        View
                      </Link>
                    </div>
                  </div>
                )}

                {finding.url && (
                  <div className="list-group-item px-0">
                    <div className="d-flex justify-content-between align-items-center">
                      <div>
                        <h6 className="mb-1">URL</h6>
                        <p className="mb-1 small">{finding.url}</p>
                      </div>
                      <Link
                        to={`/assets/urls?exact_match=${encodeURIComponent(finding.url)}`}
                        className="btn btn-sm btn-outline-primary"
                      >
                        View
                      </Link>
                    </div>
                  </div>
                )}

                {finding.hostname && finding.port && (
                  <div className="list-group-item px-0">
                    <div className="d-flex justify-content-between align-items-center">
                      <div>
                        <h6 className="mb-1">Service</h6>
                        <p className="mb-1 small">{finding.hostname}:{finding.port}</p>
                      </div>
                      <Link
                        to={`/assets/services?exact_match=${finding.hostname}:${finding.port}`}
                        className="btn btn-sm btn-outline-primary"
                      >
                        View
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4">
            <NotesSection
              assetType="wpscan finding"
              assetId={finding.id}
              currentNotes={finding.notes || ''}
              apiUpdateFunction={api.findings.wpscan.updateNotes}
              onNotesUpdate={handleNotesUpdate}
              cardClassName="dashboard-panel"
            />
          </div>
        </div>
      </div>

      <div className={`modal fade ${showDeleteModal ? 'show' : ''}`} 
           style={{ display: showDeleteModal ? 'block' : 'none' }}
           tabIndex="-1">
        <div className="modal-dialog">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">Delete WPScan Finding</h5>
              <button type="button" className="btn-close" onClick={() => setShowDeleteModal(false)}></button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to delete this WPScan finding?</p>
              <p className="text-muted">
                <strong>Finding:</strong> {finding?.title || finding?.item_name}<br />
                <strong>Item Type:</strong> {finding?.item_type}<br />
                <strong>Hostname:</strong> {finding?.hostname}<br />
                <strong>URL:</strong> {finding?.url}
              </p>
              <p className="text-danger">
                <i className="bi bi-exclamation-triangle"></i>
                This action cannot be undone.
              </p>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" onClick={() => setShowDeleteModal(false)}>
                Cancel
              </button>
              <button 
                type="button" 
                className="btn btn-danger" 
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? (
                  <>
                    <span className="spinner-border spinner-border-sm me-2" role="status"></span>
                    Deleting...
                  </>
                ) : (
                  <>
                    <i className="bi bi-trash"></i> Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
      {showDeleteModal && <div className="modal-backdrop fade show"></div>}
    </div>
  );
};

export default WPScanFindingDetail;

