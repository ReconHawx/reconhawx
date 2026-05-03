import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Row,
  Col,
  Card,
  Table,
  Badge,
  Spinner,
  Alert,
  Button,
  Collapse,
} from 'react-bootstrap';
import { adminAPI } from '../../services/api';

function formatDurationSeconds(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm ? `${h}h ${rm}m` : `${h}h`;
}

function formatAgeSeconds(blockedAtUnix) {
  if (blockedAtUnix == null) return '—';
  const t =
    typeof blockedAtUnix === 'number'
      ? blockedAtUnix
      : parseFloat(String(blockedAtUnix));
  if (Number.isNaN(t)) return '—';
  const now = Date.now() / 1000;
  const delta = Math.max(0, Math.floor(now - t));
  return formatDurationSeconds(delta) + ' ago';
}

export function WorkerStatusInner({ embedded = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(() => new Set());

  const load = useCallback(async (showSpinner = true) => {
    try {
      if (showSpinner) setLoading(true);
      setError('');
      const res = await adminAPI.getWorkerStatus();
      setData(res);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load worker status');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleRow = useCallback((name) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const summary = useMemo(() => {
    const nodes = data?.nodes || [];
    let blockedSlots = 0;
    for (const n of nodes) blockedSlots += n.blocked_count || 0;
    return {
      nodeCount: nodes.length,
      blockedSlots,
      redisOk: !!data?.redis_connected,
      redisErr: data?.redis_error,
    };
  }, [data]);

  if (loading && !data) {
    return (
      <div className={`text-center py-5 ${embedded ? '' : ''}`}>
        <Spinner animation="border" />
      </div>
    );
  }

  const nodes = data?.nodes || [];

  return (
    <>
      <Row className="mb-3 align-items-center">
        <Col>
          {summary.redisOk ? (
            <Badge bg="success" className="me-2">
              Redis connected
            </Badge>
          ) : (
            <Badge bg="warning" text="dark" className="me-2">
              Redis disconnected
            </Badge>
          )}
          <span className="text-muted small">
            {summary.nodeCount} row(s) · {summary.blockedSlots} blocked target slot(s)
            {summary.redisErr ? ` · ${summary.redisErr}` : ''}
          </span>
        </Col>
        <Col xs="auto">
          <Button size="sm" variant="outline-secondary" onClick={() => load(true)} disabled={loading}>
            {loading ? <Spinner animation="border" size="sm" /> : 'Refresh'}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger">{String(error)}</Alert>}

      {!nodes.length && !error ? (
        <Alert variant="secondary">
          No worker nodes labeled <code>reconhawx.worker=true</code>, and no orphan WAF blocks in Redis.
        </Alert>
      ) : (
        <Card className="rh-elevated-card">
          <Card.Body className="p-0">
            <Table striped hover responsive className="mb-0 align-middle">
              <thead>
                <tr>
                  <th style={{ width: '44px' }} aria-label="Expand" />
                  <th>Node</th>
                  <th>Status</th>
                  <th>WAF blocked targets</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((row) => {
                  const isOpen = expanded.has(row.name);
                  const count = row.blocked_count || 0;
                  return (
                    <React.Fragment key={row.name}>
                      <tr>
                        <td>
                          <Button
                            variant="link"
                            size="sm"
                            className="p-0 text-decoration-none"
                            aria-expanded={isOpen}
                            onClick={() => toggleRow(row.name)}
                            disabled={count === 0}
                          >
                            {count === 0 ? '—' : isOpen ? '▼' : '▶'}
                          </Button>
                        </td>
                        <td className="fw-semibold">
                          <code>{row.name}</code>
                          {row.orphan ? (
                            <Badge bg="secondary" className="ms-2">
                              orphan blocks
                            </Badge>
                          ) : null}
                        </td>
                        <td>
                          {row.orphan ? (
                            <span className="text-muted">—</span>
                          ) : row.ready ? (
                            <Badge bg="success">Ready</Badge>
                          ) : (
                            <Badge bg="danger">Not ready</Badge>
                          )}
                        </td>
                        <td>
                          {count === 0 ? (
                            <span className="text-muted">0</span>
                          ) : (
                            <Badge bg="warning" text="dark">
                              {count}
                            </Badge>
                          )}
                        </td>
                      </tr>
                      <tr className="border-top-0">
                        <td colSpan={4} className="p-0 bg-transparent border-top-0">
                          <Collapse in={isOpen && count > 0}>
                            <div>
                              <div className="px-3 pb-3 pt-0">
                                <Table size="sm" bordered responsive className="mb-0 bg-body-secondary rounded">
                                  <thead>
                                    <tr>
                                      <th>Target</th>
                                      <th>Vendor</th>
                                      <th>Source</th>
                                      <th>Age</th>
                                      <th>TTL</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(row.targets || []).map((t, idx) => (
                                      <tr key={`${row.name}-${t.target}-${idx}`}>
                                        <td>
                                          <code className="small">{t.target || '—'}</code>
                                        </td>
                                        <td>{t.vendor ?? '—'}</td>
                                        <td>
                                          <code className="small">{t.source || '—'}</code>
                                        </td>
                                        <td>{formatAgeSeconds(t.blocked_at)}</td>
                                        <td>
                                          {t.ttl_seconds != null && t.ttl_seconds >= 0
                                            ? formatDurationSeconds(t.ttl_seconds)
                                            : '—'}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </Table>
                              </div>
                            </div>
                          </Collapse>
                        </td>
                      </tr>
                    </React.Fragment>
                  );
                })}
              </tbody>
            </Table>
          </Card.Body>
        </Card>
      )}
    </>
  );
}
