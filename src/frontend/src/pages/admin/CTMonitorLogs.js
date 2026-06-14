import React, { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Container,
  Form,
  Pagination,
  Row,
  Spinner,
  Table,
} from 'react-bootstrap';
import { adminAPI } from '../../services/api';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

const EVENT_TYPES = [
  ['', 'All events'],
  ['typosquat_alert', 'Typosquat alert'],
  ['typosquat_skip', 'Typosquat skip'],
  ['asset_match', 'Asset match'],
  ['asset_submission', 'Asset submission'],
];

const OUTCOMES = [
  ['', 'All outcomes'],
  ['published', 'Published'],
  ['skipped_existing', 'Skipped existing'],
  ['publish_failed', 'Publish failed'],
  ['matched', 'Matched'],
  ['skipped_legitimate_subdomain', 'Skipped legitimate subdomain'],
  ['skipped_protected_domain', 'Skipped protected domain'],
  ['queued', 'Queued'],
  ['dedup_skipped', 'Dedup skipped'],
  ['submitted', 'Submitted'],
  ['submit_failed', 'Submit failed'],
];

const OUTCOME_VARIANTS = {
  published: 'success',
  submitted: 'success',
  matched: 'info',
  queued: 'secondary',
  skipped_existing: 'warning',
  skipped_legitimate_subdomain: 'warning',
  skipped_protected_domain: 'warning',
  dedup_skipped: 'warning',
  publish_failed: 'danger',
  submit_failed: 'danger',
};

const EVENT_VARIANTS = {
  typosquat_alert: 'danger',
  typosquat_skip: 'warning',
  asset_match: 'info',
  asset_submission: 'primary',
};

function isoFromLocal(value) {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

function DetailBlock({ item }) {
  return (
    <pre
      className="mb-0 p-3 small"
      style={{
        backgroundColor: 'var(--bs-pre-bg)',
        color: 'var(--bs-pre-color)',
        border: '1px solid var(--bs-border-color)',
        borderRadius: '0.375rem',
        maxHeight: '320px',
        overflow: 'auto',
      }}
    >
      {JSON.stringify(item.details || {}, null, 2)}
    </pre>
  );
}

function TruncatedValue({ value, as = 'span', maxWidth = '12rem' }) {
  const Component = as;
  const displayValue = value || 'N/A';
  return (
    <Component
      title={String(displayValue)}
      style={{
        display: 'inline-block',
        maxWidth,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        verticalAlign: 'bottom',
      }}
    >
      {displayValue}
    </Component>
  );
}

export function CTMonitorLogsInner({ embedded = false }) {
  const [items, setItems] = useState([]);
  const [pagination, setPagination] = useState({
    total_items: 0,
    total_pages: 1,
    current_page: 1,
    page_size: 25,
  });
  const [filters, setFilters] = useState({
    search: '',
    program: '',
    event_type: '',
    outcome: '',
    match_type: '',
    priority: '',
    start_time: '',
    end_time: '',
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState({});

  const loadLogs = async (nextPage = page) => {
    try {
      setLoading(true);
      setError('');
      const payload = {
        page: nextPage,
        page_size: pageSize,
        sort_by: 'occurred_at',
        sort_dir: 'desc',
      };
      Object.entries(filters).forEach(([key, value]) => {
        const trimmed = typeof value === 'string' ? value.trim() : value;
        if (!trimmed) return;
        if (key === 'start_time' || key === 'end_time') {
          const iso = isoFromLocal(trimmed);
          if (iso) payload[key] = iso;
        } else {
          payload[key] = trimmed;
        }
      });

      const response = await adminAPI.searchCtMonitorLogs(payload);
      setItems(response.items || []);
      setPagination(response.pagination || {});
      setPage(nextPage);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load CT monitor logs');
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageSize]);

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const resetFilters = () => {
    setFilters({
      search: '',
      program: '',
      event_type: '',
      outcome: '',
      match_type: '',
      priority: '',
      start_time: '',
      end_time: '',
    });
    setPage(1);
  };

  const toggleExpanded = (id) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const totalPages = pagination.total_pages || 1;
  const Outer = embedded ? 'div' : Container;

  return (
    <Outer className={embedded ? '' : 'mt-4'}>
      {!embedded && (
        <Row className="mb-3">
          <Col>
            <h4 className="mb-0">CT Monitor Logs</h4>
          </Col>
        </Row>
      )}

      {error && <Alert variant="danger">{error}</Alert>}

      <Card className="rh-elevated-card mb-3">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col md={3}>
              <Form.Label>Search</Form.Label>
              <Form.Control
                value={filters.search}
                onChange={(e) => updateFilter('search', e.target.value)}
                placeholder="domain, issuer, fingerprint"
              />
            </Col>
            <Col md={2}>
              <Form.Label>Program</Form.Label>
              <Form.Control
                value={filters.program}
                onChange={(e) => updateFilter('program', e.target.value)}
                placeholder="Any"
              />
            </Col>
            <Col md={2}>
              <Form.Label>Event</Form.Label>
              <Form.Select
                value={filters.event_type}
                onChange={(e) => updateFilter('event_type', e.target.value)}
              >
                {EVENT_TYPES.map(([value, label]) => (
                  <option key={value || 'all'} value={value}>{label}</option>
                ))}
              </Form.Select>
            </Col>
            <Col md={2}>
              <Form.Label>Outcome</Form.Label>
              <Form.Select
                value={filters.outcome}
                onChange={(e) => updateFilter('outcome', e.target.value)}
              >
                {OUTCOMES.map(([value, label]) => (
                  <option key={value || 'all'} value={value}>{label}</option>
                ))}
              </Form.Select>
            </Col>
            <Col md={1}>
              <Form.Label>Priority</Form.Label>
              <Form.Control
                value={filters.priority}
                onChange={(e) => updateFilter('priority', e.target.value)}
                placeholder="Any"
              />
            </Col>
            <Col md={2}>
              <Form.Label>Match type</Form.Label>
              <Form.Control
                value={filters.match_type}
                onChange={(e) => updateFilter('match_type', e.target.value)}
                placeholder="Any"
              />
            </Col>
            <Col md={3}>
              <Form.Label>Start</Form.Label>
              <Form.Control
                type="datetime-local"
                value={filters.start_time}
                onChange={(e) => updateFilter('start_time', e.target.value)}
              />
            </Col>
            <Col md={3}>
              <Form.Label>End</Form.Label>
              <Form.Control
                type="datetime-local"
                value={filters.end_time}
                onChange={(e) => updateFilter('end_time', e.target.value)}
              />
            </Col>
            <Col md="auto">
              <Button onClick={() => loadLogs(1)} disabled={loading}>
                {loading ? <Spinner animation="border" size="sm" /> : 'Load'}
              </Button>
            </Col>
            <Col md="auto">
              <Button variant="outline-secondary" onClick={resetFilters} disabled={loading}>
                Reset
              </Button>
            </Col>
            <Col md="auto">
              <Form.Select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                aria-label="Page size"
              >
                {[25, 50, 100, 250].map((size) => (
                  <option key={size} value={size}>{size} / page</option>
                ))}
              </Form.Select>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <Card className="rh-elevated-card">
        <Card.Header className="d-flex align-items-center justify-content-between">
          <span>
            CT monitor events{' '}
            <span className="text-muted">({pagination.total_items || 0})</span>
          </span>
          <Button
            variant="outline-secondary"
            size="sm"
            onClick={() => loadLogs(page)}
            disabled={loading}
          >
            Refresh
          </Button>
        </Card.Header>
        <Card.Body className="p-0" style={{ overflowX: 'auto', maxWidth: '100%' }}>
          <Table
            striped
            hover
            className="mb-0 align-middle"
            style={{ tableLayout: 'fixed', minWidth: '1120px', width: '100%' }}
          >
            <colgroup>
              <col style={{ width: '7.5rem' }} />
              <col style={{ width: '7rem' }} />
              <col style={{ width: '7rem' }} />
              <col style={{ width: '9rem' }} />
              <col style={{ width: '19%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '8.5rem' }} />
              <col style={{ width: '12rem' }} />
              <col style={{ width: '5.5rem' }} />
            </colgroup>
            <thead>
              <tr>
                <th>Time</th>
                <th>Program</th>
                <th>Event</th>
                <th>Outcome</th>
                <th>Domain</th>
                <th>Protected</th>
                <th>Match</th>
                <th>Cert</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-4">
                    <Spinner animation="border" />
                  </td>
                </tr>
              ) : items.length ? (
                items.map((item) => (
                  <React.Fragment key={item.id}>
                    <tr>
                      <td className="text-nowrap">
                        {formatDate(item.occurred_at, 'MMM dd, HH:mm')}
                      </td>
                      <td>
                        <TruncatedValue value={item.program_name || 'Unknown'} maxWidth="6.25rem" />
                      </td>
                      <td>
                        <Badge bg={EVENT_VARIANTS[item.event_type] || 'secondary'}>
                          {item.event_type}
                        </Badge>
                      </td>
                      <td>
                        <Badge bg={OUTCOME_VARIANTS[item.outcome] || 'secondary'}>
                          {item.outcome}
                        </Badge>
                      </td>
                      <td>
                        <TruncatedValue value={item.domain} as="code" maxWidth="100%" />
                      </td>
                      <td>
                        {item.protected_domain ? (
                          <TruncatedValue value={item.protected_domain} as="code" maxWidth="100%" />
                        ) : (
                          <span className="text-muted">N/A</span>
                        )}
                      </td>
                      <td>
                        <TruncatedValue value={item.match_type} maxWidth="7.5rem" />
                        {item.similarity_score != null && (
                          <small className="text-muted">{Number(item.similarity_score).toFixed(3)}</small>
                        )}
                      </td>
                      <td>
                        <div className="small">
                          <TruncatedValue value={item.cert_issuer} maxWidth="10rem" />
                        </div>
                        {item.cert_fingerprint && (
                          <TruncatedValue
                            value={`${item.cert_fingerprint.slice(0, 12)}...`}
                            as="code"
                            maxWidth="10rem"
                          />
                        )}
                      </td>
                      <td className="text-end">
                        <Button
                          size="sm"
                          variant="outline-secondary"
                          onClick={() => toggleExpanded(item.id)}
                          aria-expanded={!!expanded[item.id]}
                        >
                          Details
                        </Button>
                      </td>
                    </tr>
                    <tr>
                      <td colSpan={9} className="p-0 border-0">
                        <Collapse in={!!expanded[item.id]}>
                          <div className="p-3">
                            <DetailBlock item={item} />
                          </div>
                        </Collapse>
                      </td>
                    </tr>
                  </React.Fragment>
                ))
              ) : (
                <tr>
                  <td colSpan={9} className="text-center text-muted py-4">
                    No CT monitor logs found
                  </td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card.Body>
      </Card>

      <div className="d-flex justify-content-between align-items-center mt-3">
        <div className="text-muted small">
          Page {pagination.current_page || page} of {totalPages}
        </div>
        <Pagination className="mb-0">
          <Pagination.Prev
            disabled={page <= 1 || loading}
            onClick={() => loadLogs(Math.max(1, page - 1))}
          />
          <Pagination.Next
            disabled={page >= totalPages || loading}
            onClick={() => loadLogs(Math.min(totalPages, page + 1))}
          />
        </Pagination>
      </div>
    </Outer>
  );
}

function CTMonitorLogs() {
  usePageTitle(formatPageTitle('System Status', 'CT Logs'));
  return <CTMonitorLogsInner />;
}

export default CTMonitorLogs;
