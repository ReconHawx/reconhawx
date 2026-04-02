import React, { useState, useEffect } from 'react';
import { 
  Container, 
  Row, 
  Col, 
  Card, 
  Button, 
  Alert, 
  Spinner, 
  Table,
  Badge,
  OverlayTrigger,
  Tooltip
} from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { ctMonitorAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function CTMonitor() {
  usePageTitle(formatPageTitle('CT Monitor'));
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    let interval;
    if (autoRefresh && status?.status === 'running') {
      interval = setInterval(() => {
        loadStatus(false); // Don't show loading spinner for auto-refresh
      }, 5000); // Refresh every 5 seconds when running
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, status?.status]);

  const loadStatus = async (showLoading = true) => {
    try {
      if (showLoading) {
        setLoading(true);
      }
      setError('');
      const response = await ctMonitorAPI.getStatus();
      setStatus(response);
    } catch (err) {
      setError('Failed to load CT monitor status: ' + (err.response?.data?.detail || err.message));
      setStatus(null);
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  };

  const handleStart = async () => {
    try {
      setActionLoading(true);
      setError('');
      setSuccess('');
      
      await ctMonitorAPI.start();
      setSuccess('CT monitor started successfully');
      await loadStatus();
    } catch (err) {
      setError('Failed to start CT monitor: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    if (!window.confirm('Are you sure you want to stop the CT monitor? This will stop monitoring for typosquat certificates.')) {
      return;
    }

    try {
      setActionLoading(true);
      setError('');
      setSuccess('');
      
      await ctMonitorAPI.stop();
      setSuccess('CT monitor stopped successfully');
      await loadStatus();
    } catch (err) {
      setError('Failed to stop CT monitor: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const formatNumber = (num) => {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString();
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '0s';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    const parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);
    
    return parts.join(' ');
  };

  // Helper component for stat boxes with tooltips
  const StatBox = ({ value, label, tooltip, className = "text-primary" }) => {
    const tooltipElement = (
      <Tooltip id={`tooltip-${label.replace(/\s+/g, '-').toLowerCase()}`}>
        {tooltip}
      </Tooltip>
    );

    return (
      <OverlayTrigger placement="top" overlay={tooltipElement}>
        <div className="text-center p-3 border rounded" style={{ cursor: 'help' }}>
          <h3 className={className}>{value}</h3>
          <p className="text-muted mb-0">{label}</p>
        </div>
      </OverlayTrigger>
    );
  };

  if (loading && !status) {
    return (
      <Container fluid>
        <Row className="justify-content-center mt-5">
          <Col md="auto">
            <Spinner animation="border" role="status">
              <span className="visually-hidden">Loading...</span>
            </Spinner>
          </Col>
        </Row>
      </Container>
    );
  }

  return (
    <Container fluid>
      <Row className="mb-4">
        <Col>
          <h2>🔍 CT Monitor</h2>
          <p className="text-muted">Monitor Certificate Transparency logs for typosquatting detection</p>
        </Col>
        <Col xs="auto">
          <div className="d-flex gap-2 align-items-center">
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => loadStatus()}
              disabled={loading}
            >
              <i className="fas fa-sync-alt"></i> Refresh
            </Button>
            {status?.status === 'running' && (
              <Button
                variant={autoRefresh ? 'success' : 'outline-success'}
                size="sm"
                onClick={() => setAutoRefresh(!autoRefresh)}
              >
                <i className={`fas fa-${autoRefresh ? 'pause' : 'play'}`}></i> {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
              </Button>
            )}
          </div>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" dismissible onClose={() => setSuccess('')}>
          {success}
        </Alert>
      )}

      {/* Status and Control Card */}
      <Row className="mb-4">
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">Service Status</h5>
              <Badge bg={status?.status === 'running' ? 'success' : 'secondary'}>
                {status?.status === 'running' ? 'Running' : 'Stopped'}
              </Badge>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={6}>
                  <p><strong>CT Source:</strong> {status?.ct_source || 'N/A'}</p>
                  <p className="mb-1">
                    <strong>Ingestion TLD union:</strong>{' '}
                    <span className="text-muted small">
                      (certificates must match one of these TLDs before per-program matching)
                    </span>
                  </p>
                  <p className="small font-monospace mb-2" style={{ wordBreak: 'break-all' }}>
                    {(status?.config?.ingestion_tld_union || []).length > 0
                      ? status.config.ingestion_tld_union.join(', ')
                      : '—'}
                  </p>
                  <p className="small text-muted mb-0">
                    Per-program similarity and TLD allowlists are configured on each program (Typosquat tab)
                    and listed below. Global poll intervals are under System Settings → CT monitor.
                  </p>
                </Col>
                <Col md={6} className="text-end">
                  <div className="d-flex gap-2 justify-content-end">
                    {status?.status === 'running' ? (
                      <Button
                        variant="danger"
                        onClick={handleStop}
                        disabled={actionLoading}
                      >
                        {actionLoading ? (
                          <>
                            <Spinner size="sm" className="me-2" />
                            Stopping...
                          </>
                        ) : (
                          <>
                            <i className="fas fa-stop"></i> Stop Monitoring
                          </>
                        )}
                      </Button>
                    ) : (
                      <Button
                        variant="success"
                        onClick={handleStart}
                        disabled={actionLoading}
                      >
                        {actionLoading ? (
                          <>
                            <Spinner size="sm" className="me-2" />
                            Starting...
                          </>
                        ) : (
                          <>
                            <i className="fas fa-play"></i> Start Monitoring
                          </>
                        )}
                      </Button>
                    )}
                  </div>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {status && (
        <Row className="mb-4">
          <Col>
            <Card>
              <Card.Header>
                <h5 className="mb-0">Programs with CT monitoring enabled</h5>
              </Card.Header>
              <Card.Body className="p-0">
                {!Array.isArray(status.programs_ct_enabled) ? (
                  <p className="text-muted p-3 mb-0">
                    Per-program settings are not in this status response (deploy an updated ct-monitor build).
                  </p>
                ) : status.programs_ct_enabled.length === 0 ? (
                  <p className="text-muted p-3 mb-0">No programs have CT monitoring enabled.</p>
                ) : (
                  <Table striped bordered hover responsive className="mb-0">
                    <thead>
                      <tr>
                        <th>Program</th>
                        <th>Similarity threshold</th>
                        <th>TLD allowlist (effective)</th>
                        <th>Matcher</th>
                      </tr>
                    </thead>
                    <tbody>
                      {status.programs_ct_enabled.map((row) => (
                        <tr key={row.program_name}>
                          <td>
                            <Link to={`/programs/${encodeURIComponent(row.program_name)}`}>
                              {row.program_name}
                            </Link>
                          </td>
                          <td>{typeof row.similarity_threshold === 'number' ? row.similarity_threshold : '—'}</td>
                          <td>
                            <code className="small" style={{ wordBreak: 'break-all' }}>
                              {(row.tld_allowlist || []).join(', ') || '—'}
                            </code>
                          </td>
                          <td>
                            {row.matcher_active ? (
                              <Badge bg="success">Active</Badge>
                            ) : (
                              <OverlayTrigger
                                placement="top"
                                overlay={
                                  <Tooltip id={`tip-${row.program_name}`}>
                                    No protected domains or keywords yet — add assets on the program Typosquat tab
                                    to start matching.
                                  </Tooltip>
                                }
                              >
                                <span>
                                  <Badge bg="secondary">Idle</Badge>
                                </span>
                              </OverlayTrigger>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )}
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {status && (
        <>
          {/* Processing Statistics */}
          <Row className="mb-4">
            <Col>
              <Card>
                <Card.Header>
                  <h5 className="mb-0">Processing Statistics</h5>
                </Card.Header>
                <Card.Body>
                  <Row>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.total_received)}
                        label="Certificates Received"
                        tooltip="Total number of CT log entries fetched from Certificate Transparency logs. This includes all entries, even those that couldn't be parsed or had no domains."
                        className="text-primary"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.processed)}
                        label="Certificates Processed"
                        tooltip="Certificates that were successfully parsed and had at least one domain matching the TLD filter. These certificates are checked for typosquatting against protected domains."
                        className="text-info"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.filtered_by_tld)}
                        label="Filtered by TLD"
                        tooltip="Certificates that were successfully parsed but had no domains matching the configured TLD filter (e.g., only .ru or .cn domains when filter is com,net,org). These are skipped before matching."
                        className="text-warning"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.matches_found)}
                        label="Matches Found"
                        tooltip="Number of certificates that matched protected domains (typosquatting detected). These certificates contain domains that look similar to your protected domains."
                        className="text-success"
                      />
                    </Col>
                  </Row>
                  <Row className="mt-3">
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.alerts_published)}
                        label="Alerts Published"
                        tooltip="Number of alerts successfully published to NATS. Each match generates an alert that triggers automatic typosquat analysis workflows."
                        className="text-danger"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.errors)}
                        label="Errors"
                        tooltip="Number of errors encountered during processing. This includes parsing errors, network errors, and other exceptions."
                        className="text-secondary"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={status.stats?.certs_per_second?.toFixed(2) || '0.00'}
                        label="Certs/Second"
                        tooltip="Average processing rate: certificates received per second. Higher rates indicate better performance."
                        className="text-primary"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatDuration(status.stats?.runtime_seconds)}
                        label="Runtime"
                        tooltip="How long the CT monitor service has been running since it was started."
                        className="text-info"
                      />
                    </Col>
                  </Row>
                </Card.Body>
              </Card>
            </Col>
          </Row>

          {/* Domain Protection */}
          <Row className="mb-4">
            <Col>
              <Card>
                <Card.Header>
                  <h5 className="mb-0">Domain Protection</h5>
                </Card.Header>
                <Card.Body>
                  <Row>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.protected_domains?.total)}
                        label="Protected Domains"
                        tooltip="Total number of protected domains across all programs. These are domains from protected_domains, seed_domains, and root_domains settings that are monitored for typosquatting."
                        className="text-primary"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.protected_domains?.variations)}
                        label="Variations Generated"
                        tooltip="Total number of typosquat variations pre-generated using dnstwist. These variations are used for fast O(1) lookup matching against certificate domains."
                        className="text-info"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.protected_domains?.programs)}
                        label="Programs Monitored"
                        tooltip="Number of programs that have protected domains configured and are actively being monitored for typosquatting."
                        className="text-success"
                      />
                    </Col>
                  </Row>
                </Card.Body>
              </Card>
            </Col>
          </Row>

          {/* CT Log Connections */}
          {status.ct_logs && status.ct_logs.length > 0 && (
            <Row className="mb-4">
              <Col>
                <Card>
                  <Card.Header>
                    <h5 className="mb-0">CT Log Connections</h5>
                  </Card.Header>
                  <Card.Body>
                    <Table striped bordered hover responsive>
                      <thead>
                        <tr>
                          <th>Log Name</th>
                          <th>Operator</th>
                          <th>Tree Size</th>
                          <th>Last Index</th>
                          <th>Errors</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {status.ct_logs.map((log, idx) => (
                          <tr key={idx}>
                            <td>{log.name}</td>
                            <td>{log.operator || 'Unknown'}</td>
                            <td>{formatNumber(log.tree_size)}</td>
                            <td>{formatNumber(log.last_index)}</td>
                            <td>
                              <Badge bg={log.errors === 0 ? 'success' : log.errors < 10 ? 'warning' : 'danger'}>
                                {log.errors}
                              </Badge>
                            </td>
                            <td>
                              <Badge bg={log.connected ? 'success' : 'danger'}>
                                {log.connected ? 'Connected' : 'Disconnected'}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </Card.Body>
                </Card>
              </Col>
            </Row>
          )}
        </>
      )}
    </Container>
  );
}

export default CTMonitor;

