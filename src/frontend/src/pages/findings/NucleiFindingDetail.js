import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom';
import { Button } from 'react-bootstrap';
import AceEditor from 'react-ace';
import api from '../../services/api';
import NotesSection from '../../components/NotesSection';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

// Import Ace editor modes and themes
import 'ace-builds/src-noconflict/mode-yaml';
import 'ace-builds/src-noconflict/theme-github';
import 'ace-builds/src-noconflict/ext-language_tools';

// Template Content Section Component
const TemplateContentSection = ({ templatePath }) => {
  const [templateContent, setTemplateContent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadTemplateContent = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const content = await api.nucleiTemplates.getOfficialTemplateContent(templatePath);
      setTemplateContent(content);
    } catch (err) {
      console.error('Error loading template content:', err);
      setError('Failed to load template content');
    } finally {
      setLoading(false);
    }
  }, [templatePath]);

  // Load template content automatically when component mounts
  useEffect(() => {
    loadTemplateContent();
  }, [templatePath, loadTemplateContent]);

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      // Could add a toast notification here
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  if (loading) {
    return (
      <div className="text-center">
        <div className="spinner-border spinner-border-sm" role="status">
          <span className="visually-hidden">Loading...</span>
        </div>
        <span className="ms-2">Loading template content...</span>
      </div>
    );
  }

  if (!templateContent) {
    return (
      <div className="text-center text-muted">
        <i className="bi bi-file-text me-2"></i>
        No template content available
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-warning" role="alert">
        <i className="bi bi-exclamation-triangle me-2"></i>
        {error}
        <button 
          className="btn btn-sm btn-outline-warning ms-2" 
          onClick={loadTemplateContent}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h6 className="mb-0">
          <i className="bi bi-file-code me-2"></i>
          Template: {templatePath}
          {templatePath && templatePath.endsWith('.yaml') && (
            <span className="badge bg-secondary ms-2">YAML</span>
          )}
        </h6>
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={() => copyToClipboard(templateContent)}
          title="Copy template content to clipboard"
        >
          <i className="bi bi-clipboard"></i> Copy Template
        </button>
      </div>
      <div className="bg-light rounded" style={{ height: '400px' }}>
        <AceEditor
          mode="yaml"
          theme="github"
          name="template_content_editor"
          value={templateContent}
          readOnly={true}
          setOptions={{
            useWorker: false,
            enableBasicAutocompletion: false,
            enableLiveAutocompletion: false,
            enableSnippets: false,
            showLineNumbers: true,
            tabSize: 2,
            showPrintMargin: false,
            highlightActiveLine: false,
          }}
          style={{
            width: '100%',
            height: '400px',
            fontSize: '0.875em',
          }}
        />
      </div>
    </div>
  );
};

const NucleiFindingDetail = () => {
  const { findingId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [finding, setFinding] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [templateContentExpanded, setTemplateContentExpanded] = useState(false);

  usePageTitle(formatPageTitle(finding?.name || finding?.template_id, 'Nuclei'));

  const severityColors = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: 'secondary',
    info: 'primary',
    unknown: 'dark'
  };

  useEffect(() => {
    const loadFinding = async () => {
      try {
        setLoading(true);
        setError(null);
        
        // Prefer unified GET-by-id endpoint
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        if (idParam) {
          const data = await api.findings.nuclei.getByIdUnified(idParam);
          setFinding(data);
        } else if (findingId) {
          const response = await api.findings.nuclei.getById(findingId);
          setFinding(response.data);
        }
      } catch (err) {
        console.error('Error loading nuclei finding:', err);
        if (err.response?.status === 404) {
          setError('Nuclei finding not found');
        } else {
          setError('Failed to load nuclei finding details');
        }
      } finally {
        setLoading(false);
      }
    };

    // Load if we have either a findingId param or an id query param
    if (findingId || new URLSearchParams(location.search).get('id')) {
      loadFinding();
    }
  }, [findingId, location.search]);

  const formatNucleiDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      // Could add a toast notification here
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const handleNotesUpdate = (newNotes) => {
    // Update the finding object with new notes
    setFinding(prev => ({ ...prev, notes: newNotes }));
  };

  const handleDelete = async () => {
    try {
      setDeleting(true);
      // Use the ID from query params if available, otherwise use findingId
      const params = new URLSearchParams(location.search);
      const idParam = params.get('id');
      const deleteId = idParam || findingId;
      
      await api.findings.nuclei.delete(deleteId);
      setShowDeleteModal(false);
      navigate('/findings/nuclei');
    } catch (err) {
      console.error('Error deleting nuclei finding:', err);
      alert('Failed to delete nuclei finding: ' + (err.response?.data?.detail || err.message));
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
          <p className="mt-2">Loading nuclei finding details...</p>
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
          <Link to="/findings/nuclei" className="btn btn-outline-danger">
            Back to Nuclei Findings
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
          <p className="mb-0">The requested nuclei finding could not be found.</p>
          <hr />
          <Link to="/findings/nuclei" className="btn btn-outline-warning">
            Back to Nuclei Findings
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container-fluid mt-4">
      {/* Header */}
      <div className="row mb-4">
        <div className="col">
          <nav aria-label="breadcrumb">
            <ol className="breadcrumb">
              <li className="breadcrumb-item">
                <Link to="/findings/nuclei">Nuclei Findings</Link>
              </li>
              <li className="breadcrumb-item active" aria-current="page">
                {finding.name || finding.template_id}
              </li>
            </ol>
          </nav>
          
          <div className="d-flex justify-content-between align-items-start">
            <div>
              <h2>{finding.name || finding.template_id}</h2>
              <p className="text-muted mb-2">
                Nuclei finding discovered on {formatNucleiDate(finding.created_at)}
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

              <Button variant="outline-primary" onClick={() => navigate('/findings/nuclei')}>
                ← Back to Nuclei Findings
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="row">
        {/* Main Details */}
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
                    {finding.severity?.toUpperCase() || 'UNKNOWN'}
                  </span>
                </dd>
                <dt className="col-sm-3">Template ID</dt>
                <dd className="col-sm-9">
                  <code>{finding.template_id}</code>
                  <button
                    className="btn btn-sm btn-outline-secondary ms-2"
                    onClick={() => copyToClipboard(finding.template_id)}
                    title="Copy to clipboard"
                  >
                    📋
                  </button>
                </dd>
                <dt className="col-sm-3">Template Path</dt>
                <dd className="col-sm-9">
                  {finding.template_path || <span className="text-muted">N/A</span>}
                </dd>
                <dt className="col-sm-3">Tags</dt>
                <dd className="col-sm-9">
                  {finding.tags.join(', ') || <span className="text-muted">N/A</span>}
                </dd>
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

                <dt className="col-sm-3">Protocol</dt>
                <dd className="col-sm-9">
                  {finding.protocol || <span className="text-muted">N/A</span>}
                </dd>
                <dt className="col-sm-3">Matched At</dt>
                <dd className="col-sm-9">
                  {finding.matched_at || <span className="text-muted">N/A</span>}
                </dd>
                <dt className="col-sm-3">Extracted Results</dt>
                <dd className="col-sm-9">
                  {finding.extracted_results.join(', ') || <span className="text-muted">N/A</span>}
                </dd>
                {finding.matcher_name && (
                  <>
                    <dt className="col-sm-3">Matcher</dt>
                    <dd className="col-sm-9">{finding.matcher_name}</dd>
                  </>
                )}

                {finding.description && (
                  <>
                    <dt className="col-sm-3">Description</dt>
                    <dd className="col-sm-9">{finding.description}</dd>
                  </>
                )}
              </dl>
            </div>
          </div>

          {/* Response/Output */}
          {(finding.response || finding.curl_command) && (
            <div className="card dashboard-panel mt-4">
              <div className="card-header">
                <h5 className="card-title mb-0">Response Details</h5>
              </div>
              <div className="card-body">
                {finding.curl_command && (
                  <div className="mb-3">
                    <h6>cURL Command</h6>
                    <div className="bg-light p-3 rounded">
                      <code className="small d-block">{finding.curl_command}</code>
                      <button
                        className="btn btn-sm btn-outline-secondary mt-2"
                        onClick={() => copyToClipboard(finding.curl_command)}
                      >
                        <i className="bi bi-clipboard"></i> Copy cURL
                      </button>
                    </div>
                  </div>
                )}

                {finding.response && (
                  <div>
                    <h6>Response</h6>
                    <div className="bg-light p-3 rounded" style={{ maxHeight: '400px', overflowY: 'auto' }}>
                      <pre className="small mb-0">{finding.response}</pre>
                      <button
                        className="btn btn-sm btn-outline-secondary mt-2"
                        onClick={() => copyToClipboard(finding.response)}
                      >
                        <i className="bi bi-clipboard"></i> Copy Response
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Template Content */}
          {finding.template_path && (
            <div className="card dashboard-panel mt-4">
              <div className="card-header">
                <h5 className="card-title mb-0">
                  <button
                    className="btn btn-link text-decoration-none p-0 border-0"
                    type="button"
                    onClick={() => setTemplateContentExpanded(!templateContentExpanded)}
                  >
                    <i className={`bi ${templateContentExpanded ? 'bi-chevron-up' : 'bi-chevron-down'} me-2`}></i>
                    Template Content
                  </button>
                </h5>
              </div>
              {templateContentExpanded && (
                <div className="card-body">
                  <TemplateContentSection templatePath={finding.template_path} />
                </div>
              )}
            </div>
          )}

          {/* Extracted Data */}
          {finding.extracted && Object.keys(finding.extracted).length > 0 && (
            <div className="card dashboard-panel mt-4">
              <div className="card-header">
                <h5 className="card-title mb-0">Extracted Data</h5>
              </div>
              <div className="card-body">
                <pre className="small">{JSON.stringify(finding.extracted, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="col-lg-4">
          {/* Metadata */}
          <div className="card dashboard-panel">
            <div className="card-header">
              <h5 className="card-title mb-0">Metadata</h5>
            </div>
            <div className="card-body">
              <dl className="row small">
                <dt className="col-6">Created</dt>
                <dd className="col-6">{formatNucleiDate(finding.created_at)}</dd>

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
              </dl>
            </div>
          </div>

          {/* Related Assets */}
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

                {finding.ip && (
                  <div className="list-group-item px-0">
                    <div className="d-flex justify-content-between align-items-center">
                      <div>
                        <h6 className="mb-1">IP Address</h6>
                        <p className="mb-1 small">{finding.ip}</p>
                      </div>
                      <Link
                        to={`/assets/ips?exact_match=${encodeURIComponent(finding.ip)}`}
                        className="btn btn-sm btn-outline-primary"
                      >
                        View
                      </Link>
                    </div>
                  </div>
                )}

                {finding.ip && finding.port && (
                  <div className="list-group-item px-0">
                    <div className="d-flex justify-content-between align-items-center">
                      <div>
                        <h6 className="mb-1">Service</h6>
                        <p className="mb-1 small">{finding.ip}:{finding.port}</p>
                      </div>
                      <Link
                        to={`/assets/services?exact_match=${finding.ip}:${finding.port}`}
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

          {/* Notes Section */}
          <div className="mt-4">
            <NotesSection
              assetType="nuclei finding"
              assetId={finding.id}
              currentNotes={finding.notes || ''}
              apiUpdateFunction={api.findings.nuclei.updateNotes}
              onNotesUpdate={handleNotesUpdate}
              cardClassName="dashboard-panel"
            />
          </div>

          {/* Template Documentation */}
          <div className="card dashboard-panel mt-4">
            <div className="card-header">
              <h5 className="card-title mb-0">Template Information</h5>
            </div>
            <div className="card-body">
              <div className="d-grid">
                <button 
                  className="btn btn-outline-secondary"
                  onClick={() => window.open(`https://nuclei-templates.github.io/nuclei-templates/${finding.template_id}/`, '_blank')}
                >
                  <i className="bi bi-info-circle"></i> View Template Documentation
                </button>
              </div>
              <small className="text-muted mt-2 d-block">
                View the official template documentation and details
              </small>
            </div>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <div className={`modal fade ${showDeleteModal ? 'show' : ''}`} 
           style={{ display: showDeleteModal ? 'block' : 'none' }}
           tabIndex="-1">
        <div className="modal-dialog">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">Delete Nuclei Finding</h5>
              <button type="button" className="btn-close" onClick={() => setShowDeleteModal(false)}></button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to delete this nuclei finding?</p>
              <p className="text-muted">
                <strong>Finding:</strong> {finding?.name || finding?.template_id}<br />
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

export default NucleiFindingDetail;