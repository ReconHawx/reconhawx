import React, { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Table,
  Badge,
  Spinner,
  Alert,
  Button
} from 'react-bootstrap';
import { adminAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

const STATUS_VARIANT = {
  available: 'success',
  progressing: 'warning',
  degraded: 'danger',
};

function SystemStatus() {
  usePageTitle(formatPageTitle('System Status'));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadStatus = useCallback(async (showSpinner = true) => {
    try {
      if (showSpinner) setLoading(true);
      setError('');
      const response = await adminAPI.getSystemStatus();
      setData(response);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load system status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const imageTag = (image) => {
    if (!image) return 'unknown';
    const parts = image.split(':');
    return parts.length > 1 ? parts[parts.length - 1] : 'latest';
  };

  const imageName = (image) => {
    if (!image) return 'unknown';
    const parts = image.split(':');
    const name = parts[0];
    const segments = name.split('/');
    return segments[segments.length - 1];
  };

  const displayVersion = (svc) => {
    if (svc.app_version) return svc.app_version;
    const tag = imageTag(svc.image);
    return tag !== 'latest' ? tag : null;
  };

  if (loading && !data) {
    return (
      <Container className="mt-4 text-center">
        <Spinner animation="border" />
      </Container>
    );
  }

  return (
    <Container className="mt-4">
      <Row className="mb-3 align-items-center">
        <Col>
          <h4 className="mb-0">System Status</h4>
        </Col>
        <Col xs="auto">
          {data?.app_version && (
            <Badge bg="primary" className="me-2" style={{ fontSize: '0.9rem' }}>
              v{data.app_version}
            </Badge>
          )}
          <Button size="sm" variant="outline-secondary" onClick={() => loadStatus(true)} disabled={loading}>
            {loading ? <Spinner animation="border" size="sm" /> : 'Refresh'}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger">{error}</Alert>}

      <Card>
        <Card.Body className="p-0">
          <Table striped hover responsive className="mb-0">
            <thead>
              <tr>
                <th>Service</th>
                <th>Image</th>
                <th>Version</th>
                <th>Status</th>
                <th>Replicas</th>
              </tr>
            </thead>
            <tbody>
              {data?.services?.length ? (
                data.services.map((svc) => {
                  const version = displayVersion(svc);
                  return (
                    <tr key={svc.name}>
                      <td className="fw-semibold">{svc.name}</td>
                      <td><code>{imageName(svc.image)}</code></td>
                      <td>
                        {version
                          ? <code>{version}</code>
                          : <span className="text-muted">—</span>}
                      </td>
                      <td>
                        <Badge bg={STATUS_VARIANT[svc.status] || 'secondary'}>
                          {svc.status}
                        </Badge>
                      </td>
                      <td>
                        {svc.ready_replicas}/{svc.desired_replicas}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} className="text-center text-muted py-4">
                    No deployments found
                  </td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card.Body>
      </Card>
    </Container>
  );
}

export default SystemStatus;
