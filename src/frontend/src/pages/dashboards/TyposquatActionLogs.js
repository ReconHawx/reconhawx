import React, { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Form,
  Alert,
  Spinner,
  Badge,
  Button,
  InputGroup
} from 'react-bootstrap';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import api from '../../services/api';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

const LogLevelBadge = ({ level }) => {
  const variants = {
    'status_change': 'info',
    'assignment_change': 'primary',
    'phishlabs_incident_created': 'danger',
    'google_safe_browsing_reported': 'warning',
    'default': 'secondary'
  };

  const variant = variants[level] || variants['default'];

  return <Badge bg={variant} className="me-2">{level.replace('_', ' ').toUpperCase()}</Badge>;
};

const LogEntry = ({ log, index }) => {
  const [expanded, setExpanded] = useState(false);

  const parseJsonSafely = (jsonString) => {
    if (!jsonString) return null;
    try {
      return JSON.parse(jsonString);
    } catch {
      return jsonString;
    }
  };

  const formatLogMessage = (log) => {
    const metadata = parseJsonSafely(log.metadata);
    const oldValue = parseJsonSafely(log.old_value);
    const newValue = parseJsonSafely(log.new_value);

    // Get domain name - prioritize entity_details, then metadata, then fallback
    const domain = log.entity_details?.typo_domain || metadata?.typo_domain || metadata?.domain || 'unknown domain';
    const user = log.user?.username || 'System';
    const program = log.entity_details?.program_name || metadata?.program_name || '';

    const programText = program ? ` [${program}]` : '';

    switch (log.action_type) {
      case 'status_change':
        return `${user} changed status of ${domain}${programText} from "${oldValue?.status}" to "${newValue?.status}"${metadata?.comment ? ` - ${metadata.comment}` : ''}`;

      case 'assignment_change':
        const fromUser = oldValue?.assigned_to_username || 'unassigned';
        const toUser = newValue?.assigned_to_username || 'unassigned';
        return `${user} changed assignment of ${domain}${programText} from "${fromUser}" to "${toUser}"`;

      case 'phishlabs_incident_created':
        return `${user} created PhishLabs incident ${newValue?.phishlabs_incident_id} for ${domain}${programText}${metadata?.job_id ? ` via job ${metadata.job_id}` : ''}`;

      case 'google_safe_browsing_reported':
        return `${user} reported ${domain}${programText} to Google Safe Browsing (ref: ${newValue?.gsb_reference_id})${metadata?.job_id ? ` via job ${metadata.job_id}` : ''}`;

      default:
        return `${user} performed ${log.action_type} on ${domain}${programText}`;
    }
  };

  const getLogDetails = (log) => {
    const details = [];
    const metadata = parseJsonSafely(log.metadata);
    const oldValue = parseJsonSafely(log.old_value);
    const newValue = parseJsonSafely(log.new_value);

    if (oldValue && typeof oldValue === 'object') {
      details.push({ label: 'Previous Value', value: JSON.stringify(oldValue, null, 2) });
    }

    if (newValue && typeof newValue === 'object') {
      details.push({ label: 'New Value', value: JSON.stringify(newValue, null, 2) });
    }

    if (metadata && typeof metadata === 'object') {
      details.push({ label: 'Metadata', value: JSON.stringify(metadata, null, 2) });
    }

    return details;
  };

  const logDetails = getLogDetails(log);

  return (
    <div className={`log-entry border-start border-3 border-${index % 2 === 0 ? 'primary' : 'secondary'} ps-3 mb-3`}>
      <div className="d-flex align-items-start justify-content-between">
        <div className="flex-grow-1">
          <div className="d-flex align-items-center mb-2">
            <LogLevelBadge level={log.action_type} />
            <small className="text-muted font-monospace">
              {formatDate(log.created_at, 'yyyy-MM-dd HH:mm:ss')}
            </small>
            <small className="text-muted ms-2">
              {log.entity_details?.typo_domain ? (
                <>Domain: <strong>{log.entity_details.typo_domain}</strong></>
              ) : (
                <>Entity: {log.entity_id.substring(0, 8)}...</>
              )}
            </small>
            {log.entity_details?.program_name && (
              <small className="text-muted ms-2">
                Program: <span className="badge bg-secondary">{log.entity_details.program_name}</span>
              </small>
            )}
          </div>

          <div className="log-message mb-2">
            <code className="bg-light p-2 rounded d-block">
              {formatLogMessage(log)}
            </code>
          </div>

          {logDetails.length > 0 && (
            <div className="log-actions">
              <Button
                variant="outline-secondary"
                size="sm"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? 'Hide Details' : 'Show Details'}
              </Button>
            </div>
          )}
        </div>
      </div>

      {expanded && logDetails.length > 0 && (
        <div className="log-details mt-3 p-3 bg-light rounded">
          {logDetails.map((detail, idx) => (
            <div key={idx} className="mb-3">
              <strong className="d-block text-dark">{detail.label}:</strong>
              <pre className="bg-white p-2 rounded border font-monospace small overflow-auto" style={{maxHeight: '200px'}}>
                {detail.value}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ConsoleControls = ({
  searchTerm,
  setSearchTerm,
  actionTypeFilter,
  setActionTypeFilter,
  entityIdFilter,
  setEntityIdFilter,
  onRefresh,
  loading,
  autoRefresh,
  setAutoRefresh
}) => {
  const actionTypes = [
    'status_change',
    'assignment_change',
    'phishlabs_incident_created',
    'google_safe_browsing_reported'
  ];

  return (
    <Card className="mb-4 bg-dark text-light">
      <Card.Header className="bg-dark border-secondary">
        <div className="d-flex justify-content-between align-items-center">
          <h5 className="mb-0 text-light">
            <span className="me-2">🖥️</span>
            Console Controls
          </h5>
          <div className="d-flex gap-2">
            <Form.Check
              type="switch"
              id="auto-refresh-switch"
              label="Auto Refresh"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="text-light"
            />
            <Button
              variant="outline-light"
              size="sm"
              onClick={onRefresh}
              disabled={loading}
            >
              {loading ? <Spinner size="sm" animation="border" /> : '🔄 Refresh'}
            </Button>
          </div>
        </div>
      </Card.Header>
      <Card.Body className="bg-dark">
        <Row>
          <Col md={4}>
            <Form.Group className="mb-3">
              <Form.Label className="text-light">Search Logs</Form.Label>
              <InputGroup>
                <InputGroup.Text className="bg-secondary border-secondary text-light">
                  🔍
                </InputGroup.Text>
                <Form.Control
                  type="text"
                  placeholder="Search messages, entities..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="bg-secondary border-secondary text-light"
                />
              </InputGroup>
            </Form.Group>
          </Col>
          <Col md={4}>
            <Form.Group className="mb-3">
              <Form.Label className="text-light">Action Type</Form.Label>
              <Form.Select
                value={actionTypeFilter}
                onChange={(e) => setActionTypeFilter(e.target.value)}
                className="bg-secondary border-secondary text-light"
              >
                <option value="">All Actions</option>
                {actionTypes.map(type => (
                  <option key={type} value={type}>
                    {type.replace('_', ' ').toUpperCase()}
                  </option>
                ))}
              </Form.Select>
            </Form.Group>
          </Col>
          <Col md={4}>
            <Form.Group className="mb-3">
              <Form.Label className="text-light">Entity ID Filter</Form.Label>
              <Form.Control
                type="text"
                placeholder="Enter entity ID..."
                value={entityIdFilter}
                onChange={(e) => setEntityIdFilter(e.target.value)}
                className="bg-secondary border-secondary text-light"
              />
            </Form.Group>
          </Col>
        </Row>
      </Card.Body>
    </Card>
  );
};

function TyposquatActionLogs() {
  usePageTitle(formatPageTitle('Typosquat Action Logs'));
  const { selectedProgram } = useProgramFilter();

  // State
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [actionTypeFilter, setActionTypeFilter] = useState('');
  const [entityIdFilter, setEntityIdFilter] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  // Fetch logs
  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await api.findings.typosquat.getAllActionLogs({
        program: selectedProgram,
        action_type: actionTypeFilter || undefined,
        entity_id: entityIdFilter || undefined,
        search: searchTerm || undefined,
        limit: 100
      });

      if (response.status === 'success') {
        setLogs(response.data.action_logs || []);
        setLastRefresh(new Date());
      } else {
        setError('Failed to load action logs');
      }
    } catch (err) {
      console.error('Error fetching action logs:', err);
      setError(err.response?.data?.detail || 'Error loading action logs');
    } finally {
      setLoading(false);
    }
  }, [selectedProgram, actionTypeFilter, entityIdFilter, searchTerm]);

  // Auto refresh effect
  useEffect(() => {
    let interval;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchLogs();
      }, 5000); // Refresh every 5 seconds
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, fetchLogs]);

  // Initial load and filter changes
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Filter logs based on search term
  const filteredLogs = logs.filter(log => {
    const searchLower = searchTerm.toLowerCase();
    return (
      log.action_type.toLowerCase().includes(searchLower) ||
      log.entity_id.toLowerCase().includes(searchLower) ||
      (log.old_value && log.old_value.toLowerCase().includes(searchLower)) ||
      (log.new_value && log.new_value.toLowerCase().includes(searchLower)) ||
      (log.metadata && log.metadata.toLowerCase().includes(searchLower))
    );
  });

  const getLogStats = () => {
    const total = filteredLogs.length;
    const actionTypes = {};
    filteredLogs.forEach(log => {
      actionTypes[log.action_type] = (actionTypes[log.action_type] || 0) + 1;
    });

    return { total, actionTypes };
  };

  const stats = getLogStats();

  if (error) {
    return (
      <Container className="mt-4">
        <Alert variant="danger">{error}</Alert>
      </Container>
    );
  }

  return (
    <Container fluid className="mt-4">
      <Row className="mb-4">
        <Col md={8}>
          <h2>📋 Typosquat Action Logs Console</h2>
          <p className="text-muted">
            Real-time view of typosquat finding actions and status changes
          </p>
        </Col>
        <Col md={4} className="text-end">
          <div className="d-flex flex-column align-items-end">
            <div className="mb-2">
              <Badge bg="info" className="me-2">
                {stats.total} Total Logs
              </Badge>
              <Badge bg="secondary">
                Last refresh: {lastRefresh.toLocaleTimeString()}
              </Badge>
            </div>
            <div>
              {Object.entries(stats.actionTypes).map(([type, count]) => (
                <Badge key={type} bg="outline-primary" className="me-1 mb-1">
                  {type}: {count}
                </Badge>
              ))}
            </div>
          </div>
        </Col>
      </Row>

      <ConsoleControls
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        actionTypeFilter={actionTypeFilter}
        setActionTypeFilter={setActionTypeFilter}
        entityIdFilter={entityIdFilter}
        setEntityIdFilter={setEntityIdFilter}
        onRefresh={fetchLogs}
        loading={loading}
        autoRefresh={autoRefresh}
        setAutoRefresh={setAutoRefresh}
      />

      <Row>
        <Col md={12}>
          <Card>
            <Card.Header className="bg-dark text-light">
              <h5 className="mb-0">
                <span className="me-2">📊</span>
                Action Log Stream
                {loading && <Spinner size="sm" animation="border" className="ms-2" />}
              </h5>
            </Card.Header>
            <Card.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              {loading && logs.length === 0 ? (
                <div className="text-center py-5">
                  <Spinner animation="border" role="status">
                    <span className="visually-hidden">Loading...</span>
                  </Spinner>
                  <div className="mt-2">Loading action logs...</div>
                </div>
              ) : filteredLogs.length === 0 ? (
                <div className="text-center py-5 text-muted">
                  <h5>No logs found</h5>
                  <p>Try adjusting your filters or search terms</p>
                </div>
              ) : (
                <div className="log-container">
                  {filteredLogs.map((log, index) => (
                    <LogEntry key={log.id} log={log} index={index} />
                  ))}
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <style jsx>{`
        .log-entry {
          font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
          transition: all 0.2s ease;
        }

        .log-entry:hover {
          background-color: #f8f9fa;
          border-radius: 8px;
          padding: 8px;
          margin-left: -8px;
          margin-right: -8px;
        }

        .log-message {
          line-height: 1.4;
        }

        .log-details pre {
          font-size: 0.85em;
        }

        .console-badge {
          font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
          font-size: 0.75em;
        }
      `}</style>
    </Container>
  );
}

export default TyposquatActionLogs;