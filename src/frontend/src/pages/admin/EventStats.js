import React, { useState, useEffect } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Button,
  Alert,
  Spinner,
  Badge,
  OverlayTrigger,
  Tooltip,
  Form,
  Table,
  Collapse,
  Modal
} from 'react-bootstrap';
import { adminAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function EventStats() {
  usePageTitle(formatPageTitle('Event Stats'));
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [pendingMessages, setPendingMessages] = useState(null);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [showPending, setShowPending] = useState(false);
  const [pendingLimit, setPendingLimit] = useState(20);
  const [pendingSearchQuery, setPendingSearchQuery] = useState('');
  const [pendingMaxScan, setPendingMaxScan] = useState(5000);
  const [selectedSeqs, setSelectedSeqs] = useState([]);
  const [pendingActionLoading, setPendingActionLoading] = useState(false);
  const [showPurgeModal, setShowPurgeModal] = useState(false);
  const [purgeConfirmText, setPurgeConfirmText] = useState('');
  const [batches, setBatches] = useState(null);

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    let interval;
    if (autoRefresh) {
      interval = setInterval(() => {
        loadStats(false);
      }, 5000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh]);

  const loadStats = async (showLoading = true) => {
    try {
      if (showLoading) {
        setLoading(true);
      }
      setError('');
      const [statsResponse, batchesResponse] = await Promise.all([
        adminAPI.getEventStats(),
        adminAPI.getEventBatches().catch(() => ({ connected: false, batches: [], error: 'Failed to load' })),
      ]);
      setStats(statsResponse);
      setBatches(batchesResponse);
    } catch (err) {
      setError('Failed to load event stats: ' + (err.response?.data?.detail || err.message));
      setStats(null);
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  };

  const loadPending = async () => {
    try {
      setPendingLoading(true);
      const opts = {};
      if (pendingSearchQuery.trim()) {
        opts.search = pendingSearchQuery.trim();
        opts.max_scan = pendingMaxScan;
      }
      const response = await adminAPI.getEventPending(pendingLimit, opts);
      setPendingMessages(response);
      setSelectedSeqs([]);
      setShowPending(true);
    } catch (err) {
      setError('Failed to load pending messages: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPendingLoading(false);
    }
  };

  const toggleSeqSelected = (seq) => {
    setSelectedSeqs((prev) =>
      prev.includes(seq) ? prev.filter((s) => s !== seq) : [...prev, seq]
    );
  };

  const visibleSeqs = pendingMessages?.messages?.map((m) => m.seq) || [];
  const allVisibleSelected =
    visibleSeqs.length > 0 && visibleSeqs.every((s) => selectedSeqs.includes(s));

  const toggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      setSelectedSeqs((prev) => prev.filter((s) => !visibleSeqs.includes(s)));
    } else {
      setSelectedSeqs((prev) => [...new Set([...prev, ...visibleSeqs])]);
    }
  };

  const deleteMessagesBySeq = async (sequences, { skipConfirm = false } = {}) => {
    if (!sequences.length) return;
    if (
      !skipConfirm &&
      !window.confirm(
        `Delete ${sequences.length} message(s) from the JetStream queue? This cannot be undone.`
      )
    ) {
      return;
    }
    try {
      setPendingActionLoading(true);
      setError('');
      const result = await adminAPI.deleteEventMessages(sequences);
      if (result.failed?.length) {
        setError(
          `Some deletes failed: ${result.failed
            .map((f) => `${f.seq}: ${f.error}`)
            .slice(0, 5)
            .join('; ')}`
        );
      }
      await loadStats(false);
      await loadPending();
    } catch (err) {
      setError('Failed to delete messages: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPendingActionLoading(false);
    }
  };

  const runPurgeStream = async () => {
    if (purgeConfirmText !== 'PURGE_EVENTS') return;
    try {
      setPendingActionLoading(true);
      setError('');
      await adminAPI.purgeEventsStream('PURGE_EVENTS');
      setShowPurgeModal(false);
      setPurgeConfirmText('');
      await loadStats(false);
      if (showPending) {
        await loadPending();
      }
    } catch (err) {
      setError('Failed to purge stream: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPendingActionLoading(false);
    }
  };

  const formatNumber = (num) => {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString();
  };

  const formatPayloadPreview = (payload, maxLen = 500) => {
    if (typeof payload === 'object') {
      const s = JSON.stringify(payload, null, 2);
      return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
    }
    return String(payload || '').slice(0, 200);
  };

  const formatDuration = (seconds) => {
    if (seconds == null || seconds === undefined) return '—';
    const s = Math.floor(seconds);
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };

  const formatBytes = (bytes) => {
    if (bytes === null || bytes === undefined || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024;
      i++;
    }
    return `${size.toFixed(2)} ${units[i]}`;
  };

  const StatBox = ({ value, label, tooltip, className = 'text-primary' }) => {
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

  if (loading && !stats) {
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
          <h2>Event Queue Statistics</h2>
          <p className="text-muted">NATS JetStream EVENTS stream and notifier consumer metrics</p>
        </Col>
        <Col xs="auto">
          <div className="d-flex gap-2 align-items-center">
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => loadStats()}
              disabled={loading}
            >
              <i className="fas fa-sync-alt"></i> Refresh
            </Button>
            <Form.Check
              type="switch"
              id="auto-refresh-switch"
              label="Auto-refresh"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
          </div>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {stats && !stats.connected && (
        <Alert variant="warning">
          <strong>NATS unreachable.</strong> {stats.error || 'Could not connect to NATS JetStream.'}
        </Alert>
      )}

      {stats && (
        <>
          {/* Connection Status */}
          <Row className="mb-4">
            <Col>
              <Card>
                <Card.Header className="d-flex justify-content-between align-items-center">
                  <h5 className="mb-0">Connection Status</h5>
                  <Badge bg={stats.connected ? 'success' : 'danger'}>
                    {stats.connected ? 'Connected' : 'Disconnected'}
                  </Badge>
                </Card.Header>
              </Card>
            </Col>
          </Row>

          {/* Stream Statistics */}
          {stats.stream && (
            <Row className="mb-4">
              <Col>
                <Card>
                  <Card.Header>
                    <h5 className="mb-0">Stream: {stats.stream.name}</h5>
                  </Card.Header>
                  <Card.Body>
                    {stats.stream.error ? (
                      <Alert variant="warning">{stats.stream.error}</Alert>
                    ) : (
                      <Row>
                        <Col md={2}>
                          <StatBox
                            value={formatNumber(stats.stream.messages)}
                            label="Messages"
                            tooltip="Number of messages currently stored in the EVENTS stream"
                            className="text-primary"
                          />
                        </Col>
                        <Col md={2}>
                          <StatBox
                            value={formatBytes(stats.stream.bytes)}
                            label="Bytes"
                            tooltip="Total size in bytes of all messages in the stream"
                            className="text-info"
                          />
                        </Col>
                        <Col md={2}>
                          <StatBox
                            value={formatNumber(stats.stream.first_seq)}
                            label="First Seq"
                            tooltip="Sequence number of the oldest message in the stream"
                            className="text-secondary"
                          />
                        </Col>
                        <Col md={2}>
                          <StatBox
                            value={formatNumber(stats.stream.last_seq)}
                            label="Last Seq"
                            tooltip="Sequence number of the most recently added message"
                            className="text-secondary"
                          />
                        </Col>
                        <Col md={2}>
                          <StatBox
                            value={formatNumber(stats.stream.consumer_count)}
                            label="Consumers"
                            tooltip="Number of consumers attached to this stream"
                            className="text-success"
                          />
                        </Col>
                        <Col md={2}>
                          <StatBox
                            value={formatNumber(stats.stream.num_subjects)}
                            label="Subjects"
                            tooltip="Number of unique subjects in the stream"
                            className="text-warning"
                          />
                        </Col>
                      </Row>
                    )}
                  </Card.Body>
                </Card>
              </Col>
            </Row>
          )}

          {/* Consumer Statistics */}
          {stats.consumer && (
            <Row className="mb-4">
              <Col>
                <Card>
                  <Card.Header>
                    <h5 className="mb-0">Consumer: {stats.consumer.name}</h5>
                  </Card.Header>
                  <Card.Body>
                    {stats.consumer.error ? (
                      <Alert variant="warning">{stats.consumer.error}</Alert>
                    ) : (
                      <Row>
                        <Col md={4}>
                          <StatBox
                            value={formatNumber(stats.consumer.num_pending)}
                            label="Pending"
                            tooltip="Messages waiting to be delivered to this consumer"
                            className="text-warning"
                          />
                        </Col>
                        <Col md={4}>
                          <StatBox
                            value={formatNumber(stats.consumer.delivered_stream_seq)}
                            label="Delivered"
                            tooltip="Last stream sequence number delivered to this consumer"
                            className="text-info"
                          />
                        </Col>
                        <Col md={4}>
                          <StatBox
                            value={formatNumber(stats.consumer.ack_pending)}
                            label="Ack Pending"
                            tooltip="Messages delivered but not yet acknowledged"
                            className="text-primary"
                          />
                        </Col>
                      </Row>
                    )}
                  </Card.Body>
                </Card>
              </Col>
            </Row>
          )}

          {/* Event-Handler Batches (waiting in Redis) */}
          <Row className="mb-4">
            <Col>
              <Card>
                <Card.Header>
                  <h5 className="mb-0">Event-Handler Batches</h5>
                </Card.Header>
                <Card.Body>
                  <p className="text-muted small mb-3">
                    Batches accumulated by the event-handler, waiting to be flushed when <code>max_events</code> or <code>max_delay</code> is reached.
                  </p>
                  {batches?.error && !batches?.connected && (
                    <Alert variant="warning">Redis: {batches.error}</Alert>
                  )}
                  {batches?.connected && (
                    batches.batches?.length === 0 ? (
                      <Alert variant="info">No batches waiting.</Alert>
                    ) : (
                      <Table striped bordered hover size="sm" responsive>
                        <thead>
                          <tr>
                            <th>Handler</th>
                            <th>Program</th>
                            <th>Items</th>
                            <th>Age</th>
                            <th>Timeout</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {batches.batches?.map((b, idx) => {
                            const willFlushSoon = b.timeout_seconds != null && b.age_seconds >= b.timeout_seconds * 0.8;
                            const overdue = b.timeout_seconds != null && b.age_seconds >= b.timeout_seconds;
                            return (
                              <tr key={idx}>
                                <td><code>{b.handler_id}</code></td>
                                <td>{b.program_name}</td>
                                <td>{formatNumber(b.item_count)}</td>
                                <td>{formatDuration(b.age_seconds)}</td>
                                <td>{b.timeout_seconds != null ? formatDuration(b.timeout_seconds) : '—'}</td>
                                <td>
                                  {overdue ? (
                                    <Badge bg="warning">Flush due</Badge>
                                  ) : willFlushSoon ? (
                                    <Badge bg="info">Soon</Badge>
                                  ) : (
                                    <Badge bg="secondary">Waiting</Badge>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </Table>
                    )
                  )}
                </Card.Body>
              </Card>
            </Col>
          </Row>

          {/* Pending Messages (read-only load; delete/purge mutate stream) */}
          <Row className="mb-4">
            <Col>
              <Card>
                <Card.Header className="d-flex flex-wrap justify-content-between align-items-center gap-2">
                  <h5 className="mb-0">Pending Messages</h5>
                  <div className="d-flex flex-wrap gap-2 align-items-center">
                    <Form.Control
                      type="text"
                      size="sm"
                      style={{ width: '200px' }}
                      placeholder="Search subject / payload…"
                      value={pendingSearchQuery}
                      onChange={(e) => setPendingSearchQuery(e.target.value)}
                      disabled={!stats?.connected}
                    />
                    <Form.Control
                      type="number"
                      size="sm"
                      style={{ width: '88px' }}
                      min={1}
                      max={50000}
                      title="Max sequences to scan when searching"
                      value={pendingMaxScan}
                      onChange={(e) =>
                        setPendingMaxScan(
                          Math.min(50000, Math.max(1, parseInt(e.target.value) || 5000))
                        )
                      }
                      disabled={!stats?.connected}
                    />
                    <span className="small text-muted">max scan</span>
                    <Form.Control
                      type="number"
                      size="sm"
                      style={{ width: '70px' }}
                      min={1}
                      max={100}
                      value={pendingLimit}
                      onChange={(e) =>
                        setPendingLimit(Math.min(100, Math.max(1, parseInt(e.target.value) || 20)))
                      }
                      disabled={!stats?.connected}
                    />
                    <span className="small text-muted">rows</span>
                    <Button
                      variant="outline-primary"
                      size="sm"
                      onClick={loadPending}
                      disabled={pendingLoading || !stats?.connected}
                    >
                      {pendingLoading ? (
                        <>
                          <Spinner animation="border" size="sm" className="me-1" />
                          Loading...
                        </>
                      ) : (
                        <>Load</>
                      )}
                    </Button>
                    <Button
                      variant="outline-danger"
                      size="sm"
                      onClick={() => {
                        setPurgeConfirmText('');
                        setShowPurgeModal(true);
                      }}
                      disabled={!stats?.connected || pendingActionLoading}
                    >
                      Purge stream
                    </Button>
                  </div>
                </Card.Header>
                <Card.Body>
                  <Alert variant="secondary" className="small py-2 mb-3">
                    <strong>Load</strong> uses a direct stream read and does <strong>not</strong> consume
                    messages. <strong>Search</strong> scans up to <em>max scan</em> sequences (case-insensitive
                    match on subject and payload). <strong>Delete</strong> removes messages by JetStream
                    sequence; <strong>Purge stream</strong> deletes <em>all</em> messages in the EVENTS stream
                    (including in-flight / unacked). Prefer pausing consumers if you need a quiet window.
                  </Alert>
                  <Collapse in={showPending}>
                    <div>
                      {pendingMessages && (
                        <>
                          {pendingMessages.error && (
                            <Alert variant="warning">{pendingMessages.error}</Alert>
                          )}
                          {pendingMessages.pending_range && (
                            <p className="small text-muted mb-2">
                              Showing {pendingMessages.pending_range.shown} of{' '}
                              {formatNumber(pendingMessages.pending_range.total)} pending (seq{' '}
                              {pendingMessages.pending_range.start}–{pendingMessages.pending_range.end})
                              {pendingMessages.scan && (
                                <>
                                  {' '}
                                  · scanned {formatNumber(pendingMessages.scan.examined)} sequence(s)
                                  {pendingMessages.scan.truncated
                                    ? ' (limit reached — not all pending were searched)'
                                    : ''}
                                </>
                              )}
                            </p>
                          )}
                          {pendingMessages.messages?.length > 0 && (
                            <div className="d-flex flex-wrap gap-2 mb-2 align-items-center">
                              <Button
                                variant="outline-secondary"
                                size="sm"
                                onClick={toggleSelectAllVisible}
                                disabled={pendingActionLoading}
                              >
                                {allVisibleSelected ? 'Clear visible selection' : 'Select all visible'}
                              </Button>
                              <Button
                                variant="danger"
                                size="sm"
                                onClick={() => deleteMessagesBySeq(selectedSeqs)}
                                disabled={
                                  pendingActionLoading || selectedSeqs.length === 0 || !stats?.connected
                                }
                              >
                                Delete selected ({selectedSeqs.length})
                              </Button>
                            </div>
                          )}
                          {pendingMessages.messages?.length === 0 ? (
                            <Alert variant="info">No pending messages (or no matches).</Alert>
                          ) : (
                            <Table striped bordered hover size="sm" responsive>
                              <thead>
                                <tr>
                                  <th style={{ width: '40px' }}>
                                    <Form.Check
                                      type="checkbox"
                                      checked={allVisibleSelected}
                                      onChange={toggleSelectAllVisible}
                                      disabled={pendingActionLoading || visibleSeqs.length === 0}
                                      aria-label="Select all visible"
                                    />
                                  </th>
                                  <th>Seq</th>
                                  <th>Subject</th>
                                  <th>Time</th>
                                  <th>Payload (preview)</th>
                                  <th style={{ width: '90px' }}> </th>
                                </tr>
                              </thead>
                              <tbody>
                                {pendingMessages.messages?.map((msg, idx) => (
                                  <tr key={`${msg.seq}-${idx}`}>
                                    <td>
                                      <Form.Check
                                        type="checkbox"
                                        checked={selectedSeqs.includes(msg.seq)}
                                        onChange={() => toggleSeqSelected(msg.seq)}
                                        disabled={pendingActionLoading}
                                        aria-label={`Select seq ${msg.seq}`}
                                      />
                                    </td>
                                    <td>
                                      <code>{msg.seq}</code>
                                    </td>
                                    <td>
                                      <code className="small">{msg.subject}</code>
                                    </td>
                                    <td className="small">{msg.time || '—'}</td>
                                    <td>
                                      <pre
                                        className="mb-0 small"
                                        style={{
                                          maxHeight: '120px',
                                          overflow: 'auto',
                                          whiteSpace: 'pre-wrap',
                                          wordBreak: 'break-all',
                                        }}
                                      >
                                        {formatPayloadPreview(msg.payload)}
                                      </pre>
                                    </td>
                                    <td>
                                      <Button
                                        variant="outline-danger"
                                        size="sm"
                                        className="py-0 px-1"
                                        title="Delete this message"
                                        disabled={pendingActionLoading || !stats?.connected}
                                        onClick={() => deleteMessagesBySeq([msg.seq])}
                                      >
                                        Delete
                                      </Button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </Table>
                          )}
                        </>
                      )}
                    </div>
                  </Collapse>
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </>
      )}

      <Modal show={showPurgeModal} onHide={() => { setShowPurgeModal(false); setPurgeConfirmText(''); }} centered>
        <Modal.Header closeButton>
          <Modal.Title>Purge EVENTS stream</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p className="small">
            This removes <strong>all</strong> messages from the JetStream EVENTS stream, including messages
            already delivered but not yet acknowledged. Type <code className="user-select-all">PURGE_EVENTS</code>{' '}
            to confirm.
          </p>
          <Form.Control
            type="text"
            autoComplete="off"
            placeholder="PURGE_EVENTS"
            value={purgeConfirmText}
            onChange={(e) => setPurgeConfirmText(e.target.value)}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => { setShowPurgeModal(false); setPurgeConfirmText(''); }}>
            Cancel
          </Button>
          <Button
            variant="danger"
            disabled={purgeConfirmText !== 'PURGE_EVENTS' || pendingActionLoading}
            onClick={runPurgeStream}
          >
            {pendingActionLoading ? (
              <>
                <Spinner animation="border" size="sm" className="me-1" />
                Purging…
              </>
            ) : (
              'Purge'
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default EventStats;
