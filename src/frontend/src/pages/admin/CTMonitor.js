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

export function CTMonitorInner({ embedded = false }) {
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
    if (
      !window.confirm(
        'Are you sure you want to stop the CT monitor? This will stop typosquat detection and CT asset discovery for all programs.'
      )
    ) {
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

  const Outer = embedded ? 'div' : Container;
  const outerProps = embedded ? {} : { fluid: true };

  const typosquatFeatureEnabled =
    status?.any_program_ct_typosquat_enabled ??
    (Array.isArray(status?.programs_ct_enabled) && status.programs_ct_enabled.length > 0);

  const assetFeatureEnabled =
    status?.any_program_ct_asset_monitoring_enabled ??
    (Array.isArray(status?.programs_asset_enabled) && status.programs_asset_enabled.length > 0);

  const assetPrograms = Array.isArray(status?.programs_asset_enabled) ? status.programs_asset_enabled : [];
  const indexedApexRoots = assetPrograms.reduce(
    (sum, row) => sum + (Array.isArray(row.apex_roots) ? row.apex_roots.length : 0),
    0
  );

  const formatApexRoots = (roots) => {
    if (!Array.isArray(roots) || roots.length === 0) return '—';
    const joined = roots.join(', ');
    if (joined.length <= 80) return joined;
    return `${joined.slice(0, 77)}…`;
  };

  if (loading && !status) {
    return (
      <Outer {...outerProps}>
        <Row className={`justify-content-center ${embedded ? 'py-4' : 'mt-5'}`}>
          <Col md="auto">
            <Spinner animation="border" role="status">
              <span className="visually-hidden">Loading...</span>
            </Spinner>
          </Col>
        </Row>
      </Outer>
    );
  }

  return (
    <Outer {...outerProps}>
      <Row className="mb-4">
        <Col>
          {!embedded && (
            <>
              <h2>🔍 CT Monitor</h2>
            </>
          )}
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
          <Card className="rh-elevated-card">
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
                  <p className="mb-2">
                    <strong>Features:</strong>{' '}
                    <Badge bg={typosquatFeatureEnabled ? 'success' : 'secondary'} className="me-1">
                      Typosquat {typosquatFeatureEnabled ? 'on' : 'off'}
                    </Badge>
                    <Badge bg={assetFeatureEnabled ? 'success' : 'secondary'} className="me-1">
                      Asset discovery {assetFeatureEnabled ? 'on' : 'off'}
                    </Badge>
                    {typeof status?.ct_fetch_active === 'boolean' && (
                      <Badge bg={status.ct_fetch_active ? 'info' : 'secondary'}>
                        Ingestion {status.ct_fetch_active ? 'active' : 'idle'}
                      </Badge>
                    )}
                  </p>
                  <p className="mb-1">
                    <strong>Certificate TLDs:</strong>{' '}
                    {status?.ingestion_tld_filter_enabled || status?.config?.ingestion_tld_filter_enabled ? (
                      <span className="text-muted small">filtered at ingestion</span>
                    ) : (
                      <Badge bg="info">All TLDs (filter disabled)</Badge>
                    )}
                  </p>
                  {(status?.ingestion_tld_filter_enabled || status?.config?.ingestion_tld_filter_enabled) && (
                    <p className="small font-monospace mb-2" style={{ wordBreak: 'break-all' }}>
                      {(status?.config?.ingestion_tld_union || []).length > 0
                        ? status.config.ingestion_tld_union.join(', ')
                        : '—'}
                    </p>
                  )}
                  <p className="small text-muted mb-0">
                    Certificates stream from self-hosted certstream-server (
                    {status?.certstream_url || 'ws://certstream:4000/'}). Enable typosquat monitoring on each
                    program&apos;s Typosquat tab; enable asset discovery on the Scope tab. Config reloads on startup
                    and when CT-related program settings are saved. Global stats interval: System Settings → CT monitor.
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
          <Col md={6} className="mb-3 mb-md-0">
            <Card className="rh-elevated-card h-100">
              <Card.Header>
                <h5 className="mb-0">Typosquat programs</h5>
              </Card.Header>
              <Card.Body className="p-0">
                {!Array.isArray(status.programs_ct_enabled) ? (
                  <p className="text-muted p-3 mb-0">
                    Typosquat program settings are not in this status response (deploy an updated ct-monitor build).
                  </p>
                ) : status.programs_ct_enabled.length === 0 ? (
                  <p className="text-muted p-3 mb-0">No programs have typosquat CT monitoring enabled.</p>
                ) : (
                  <Table striped bordered hover responsive className="mb-0">
                    <thead>
                      <tr>
                        <th>Program</th>
                        <th>Similarity threshold</th>
                        <th>Certificate TLDs</th>
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
                            {row.tld_allowlist === 'all' ? (
                              <span className="text-muted">All</span>
                            ) : (
                              <code className="small" style={{ wordBreak: 'break-all' }}>
                                {Array.isArray(row.tld_allowlist)
                                  ? row.tld_allowlist.join(', ') || '—'
                                  : '—'}
                              </code>
                            )}
                          </td>
                          <td>
                            {row.matcher_active ? (
                              <Badge bg="success">Active</Badge>
                            ) : (
                              <OverlayTrigger
                                placement="top"
                                overlay={
                                  <Tooltip id={`tip-${row.program_name}`}>
                                    No protected domains or keywords yet — configure on the program Typosquat tab
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
          <Col md={6}>
            <Card className="rh-elevated-card h-100">
              <Card.Header>
                <h5 className="mb-0">Asset discovery programs</h5>
              </Card.Header>
              <Card.Body className="p-0">
                {!Array.isArray(status.programs_asset_enabled) ? (
                  <p className="text-muted p-3 mb-0">
                    Asset discovery program settings are not in this status response (deploy an updated ct-monitor build).
                  </p>
                ) : status.programs_asset_enabled.length === 0 ? (
                  <p className="text-muted p-3 mb-0">No programs have CT asset discovery enabled.</p>
                ) : (
                  <Table striped bordered hover responsive className="mb-0">
                    <thead>
                      <tr>
                        <th>Program</th>
                        <th>Apex roots</th>
                      </tr>
                    </thead>
                    <tbody>
                      {status.programs_asset_enabled.map((row) => {
                        const roots = Array.isArray(row.apex_roots) ? row.apex_roots : [];
                        const display = formatApexRoots(roots);
                        return (
                          <tr key={row.program_name}>
                            <td>
                              <Link to={`/programs/${encodeURIComponent(row.program_name)}`}>
                                {row.program_name}
                              </Link>
                            </td>
                            <td>
                              {roots.length === 0 ? (
                                <span className="text-muted">—</span>
                              ) : (
                                <OverlayTrigger
                                  placement="top"
                                  overlay={
                                    <Tooltip id={`apex-${row.program_name}`}>
                                      {roots.join(', ')}
                                    </Tooltip>
                                  }
                                >
                                  <span>
                                    <Badge bg="secondary" className="me-1">
                                      {roots.length}
                                    </Badge>
                                    <code className="small" style={{ wordBreak: 'break-all' }}>
                                      {display}
                                    </code>
                                  </span>
                                </OverlayTrigger>
                              )}
                            </td>
                          </tr>
                        );
                      })}
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
          <Row className="mb-4">
            <Col>
              <Card className="rh-elevated-card">
                <Card.Header>
                  <h5 className="mb-0">Certificate pipeline</h5>
                </Card.Header>
                <Card.Body>
                  <Row>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.total_received)}
                        label="Certificates Received"
                        tooltip="Total CT log entries fetched from Certificate Transparency logs, including entries that could not be parsed or had no domains."
                        className="text-primary"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.processed)}
                        label="Certificates Processed"
                        tooltip="Certificates successfully parsed and passed to matching (typosquat and asset discovery share this pipeline)."
                        className="text-info"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.filtered_by_tld)}
                        label="Filtered by TLD"
                        tooltip="Certificates parsed but dropped because no SAN matched the configured ingestion TLD filter."
                        className="text-warning"
                      />
                    </Col>
                    <Col md={3}>
                      <StatBox
                        value={formatNumber(status.stats?.errors)}
                        label="Errors"
                        tooltip="Parsing, network, and other processing errors in the CertStream consumer."
                        className="text-secondary"
                      />
                    </Col>
                  </Row>
                  <Row className="mt-3">
                    <Col md={3}>
                      <StatBox
                        value={status.stats?.certs_per_second?.toFixed(2) || '0.00'}
                        label="Certs/Second"
                        tooltip="Average rate of certificates received from CertStream."
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
                    {status.stats?.certstream_queue_size != null && (
                      <Col md={3}>
                        <StatBox
                          value={formatNumber(status.stats.certstream_queue_size)}
                          label="Queue Size"
                          tooltip={`Certificates waiting in the asyncio queue (max ${formatNumber(status.stats?.certstream_queue_maxsize)}).`}
                          className="text-warning"
                        />
                      </Col>
                    )}
                    {status.stats?.queue_drops != null && (
                      <Col md={3}>
                        <StatBox
                          value={formatNumber(status.stats.queue_drops)}
                          label="Queue Drops"
                          tooltip="Certificates dropped because the processing queue exceeded its high-water mark."
                          className="text-danger"
                        />
                      </Col>
                    )}
                  </Row>
                  {(status.stats?.match_in_flight != null || status.stats?.match_concurrency != null) && (
                    <Row className="mt-3">
                      {status.stats?.match_in_flight != null && (
                        <Col md={3}>
                          <StatBox
                            value={formatNumber(status.stats.match_in_flight)}
                            label="Match In Flight"
                            tooltip="Certificate match workers currently processing."
                            className="text-secondary"
                          />
                        </Col>
                      )}
                      {status.stats?.match_concurrency != null && (
                        <Col md={3}>
                          <StatBox
                            value={formatNumber(status.stats.match_concurrency)}
                            label="Match Concurrency"
                            tooltip="Configured parallel certificate match workers."
                            className="text-secondary"
                          />
                        </Col>
                      )}
                    </Row>
                  )}
                </Card.Body>
              </Card>
            </Col>
          </Row>

          <Row className="mb-4">
            <Col>
              <Card className="rh-elevated-card">
                <Card.Header>
                  <h5 className="mb-0">Typosquat detection</h5>
                </Card.Header>
                <Card.Body>
                  <Row>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.matches_found)}
                        label="Matches Found"
                        tooltip="Certificates whose domains matched protected domains or typosquat rules."
                        className="text-success"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.alerts_published)}
                        label="Alerts Published"
                        tooltip="Alerts successfully published to NATS (events.typosquat.ct_alert), triggering typosquat workflows."
                        className="text-danger"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.skipped_existing)}
                        label="Skipped (Existing)"
                        tooltip="Matches skipped because the typosquat domain already exists in the database (Redis-cached API check)."
                        className="text-warning"
                      />
                    </Col>
                  </Row>
                  <Row className="mt-3">
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.cache_hits)}
                        label="Dedup Cache Hits"
                        tooltip="Typosquat existence checks answered from Redis without calling the API."
                        className="text-info"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.cache_misses)}
                        label="Dedup Cache Misses"
                        tooltip="Typosquat existence checks that required an API lookup."
                        className="text-info"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.similarity_skipped)}
                        label="Similarity Skipped"
                        tooltip="Candidate domains skipped because similarity to protected domains was below the program threshold."
                        className="text-secondary"
                      />
                    </Col>
                  </Row>
                </Card.Body>
              </Card>
            </Col>
          </Row>

          <Row className="mb-4">
            <Col>
              <Card className="rh-elevated-card">
                <Card.Header>
                  <h5 className="mb-0">Asset discovery</h5>
                </Card.Header>
                <Card.Body>
                  <Row>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.asset_matches)}
                        label="Scope Matches"
                        tooltip="Certificate SANs that matched a program's in-scope patterns (before dedup and submission)."
                        className="text-success"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.assets_submitted)}
                        label="Assets Submitted"
                        tooltip="Subdomain hostnames successfully POSTed to /assets (inserted even when unresolved)."
                        className="text-primary"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.asset_dedup_hits)}
                        label="Dedup Hits"
                        tooltip="Scope matches skipped because the hostname was recently submitted (Redis dedup)."
                        className="text-info"
                      />
                    </Col>
                  </Row>
                  <Row className="mt-3">
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.batches_posted)}
                        label="Batches Posted"
                        tooltip="Successful batched POST /assets requests to the API."
                        className="text-secondary"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.post_failures)}
                        label="Post Failures"
                        tooltip="Failed asset submission batches (hostnames remain eligible for retry on next sighting)."
                        className="text-danger"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.buffered)}
                        label="Buffered"
                        tooltip="Hostnames currently waiting in the per-program submit buffer before the next flush."
                        className="text-warning"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.stats?.asset_events_published)}
                        label="Events Published"
                        tooltip="NATS events.assets.ct_subdomain.discovered messages published for notification handlers."
                        className="text-primary"
                      />
                    </Col>
                  </Row>
                </Card.Body>
              </Card>
            </Col>
          </Row>

          <Row className="mb-4">
            <Col md={6} className="mb-3 mb-md-0">
              <Card className="rh-elevated-card h-100">
                <Card.Header>
                  <h5 className="mb-0">Typosquat protection</h5>
                </Card.Header>
                <Card.Body>
                  <Row>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.protected_domains?.total)}
                        label="Protected Domains"
                        tooltip="Protected domains across typosquat-enabled programs (used for variation and similarity matching)."
                        className="text-primary"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.protected_domains?.variations)}
                        label="Variations Generated"
                        tooltip="Pre-generated dnstwist variations used for O(1) typosquat lookup."
                        className="text-info"
                      />
                    </Col>
                    <Col md={4}>
                      <StatBox
                        value={formatNumber(status.protected_domains?.programs)}
                        label="Programs with Domains"
                        tooltip="Programs with protected domains loaded for typosquat matching."
                        className="text-success"
                      />
                    </Col>
                  </Row>
                </Card.Body>
              </Card>
            </Col>
            <Col md={6}>
              <Card className="rh-elevated-card h-100">
                <Card.Header>
                  <h5 className="mb-0">Asset scope coverage</h5>
                </Card.Header>
                <Card.Body>
                  <Row>
                    <Col md={6}>
                      <StatBox
                        value={formatNumber(assetPrograms.length)}
                        label="Programs"
                        tooltip="Programs with CT asset discovery enabled and valid in-scope rules."
                        className="text-primary"
                      />
                    </Col>
                    <Col md={6}>
                      <StatBox
                        value={formatNumber(indexedApexRoots)}
                        label="Indexed Apex Roots"
                        tooltip="Total registrable apex domains indexed for scope prefiltering across asset-enabled programs."
                        className="text-info"
                      />
                    </Col>
                  </Row>
                  <p className="text-muted small mb-0 mt-3">
                    Matching uses scope patterns configured on each program&apos;s Scope tab. The API re-checks scope
                    when subdomains are ingested.
                  </p>
                </Card.Body>
              </Card>
            </Col>
          </Row>

        </>
      )}
    </Outer>
  );
}

function CTMonitor() {
  usePageTitle(formatPageTitle('CT Monitor'));
  return <CTMonitorInner embedded={false} />;
}

export default CTMonitor;

