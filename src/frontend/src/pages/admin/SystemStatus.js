import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Table,
  Badge,
  Spinner,
  Alert,
  Button,
  Tabs,
  Tab,
} from 'react-bootstrap';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { adminAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';
import { EventStatsInner } from './EventStats';
import { CTMonitorInner } from './CTMonitor';

const STATUS_VARIANT = {
  available: 'success',
  progressing: 'warning',
  degraded: 'danger',
};

const TAB_DEPLOYMENTS = 'deployments';
const TAB_EVENTS = 'events';
const TAB_CT = 'ct-monitor';

const TAB_TITLES = {
  [TAB_DEPLOYMENTS]: 'Deployments',
  [TAB_EVENTS]: 'Event queue',
  [TAB_CT]: 'CT Monitor',
};

function SystemStatus() {
  const { isSuperuser, isAdmin } = useAuth();
  const superuser = isSuperuser();
  const admin = isAdmin();
  const [searchParams, setSearchParams] = useSearchParams();

  const allowedTabs = useMemo(() => {
    if (superuser) return [TAB_DEPLOYMENTS, TAB_EVENTS, TAB_CT];
    if (admin) return [TAB_EVENTS];
    return [];
  }, [superuser, admin]);

  const defaultTab = superuser ? TAB_DEPLOYMENTS : TAB_EVENTS;

  const activeTab = useMemo(() => {
    const t = searchParams.get('tab');
    if (t && allowedTabs.includes(t)) return t;
    return defaultTab;
  }, [searchParams, allowedTabs, defaultTab]);

  usePageTitle(formatPageTitle('System Status', TAB_TITLES[activeTab] || ''));

  useEffect(() => {
    const t = searchParams.get('tab');
    if (!allowedTabs.length) return;
    if (!t || !allowedTabs.includes(t)) {
      setSearchParams({ tab: defaultTab }, { replace: true });
    }
  }, [allowedTabs, defaultTab, searchParams, setSearchParams]);

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
    if (!superuser || activeTab !== TAB_DEPLOYMENTS) {
      return;
    }
    loadStatus();
  }, [superuser, activeTab, loadStatus]);

  const handleTabSelect = (k) => {
    if (k) setSearchParams({ tab: k });
  };

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

  const deploymentsBody =
    loading && !data ? (
      <div className="text-center py-5">
        <Spinner animation="border" />
      </div>
    ) : (
        <>
          <Row className="mb-3 align-items-center">
            <Col xs="auto" className="ms-auto">
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
                          <td>
                            <code>{imageName(svc.image)}</code>
                          </td>
                          <td>
                            {version ? <code>{version}</code> : <span className="text-muted">—</span>}
                          </td>
                          <td>
                            <Badge bg={STATUS_VARIANT[svc.status] || 'secondary'}>{svc.status}</Badge>
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
        </>
      );

  if (!admin) {
    return (
      <Container className="mt-4">
        <Alert variant="danger">You do not have access to System Status.</Alert>
      </Container>
    );
  }

  return (
    <Container className="mt-4">
      <Row className="mb-3">
        <Col>
          <h4 className="mb-0">System Status</h4>
        </Col>
      </Row>

      <Tabs activeKey={activeTab} onSelect={handleTabSelect} className="mb-3">
        {superuser && (
          <Tab eventKey={TAB_DEPLOYMENTS} title="Deployments">
            {deploymentsBody}
          </Tab>
        )}
        <Tab eventKey={TAB_EVENTS} title="Event queue">
          <EventStatsInner embedded />
        </Tab>
        {superuser && (
          <Tab eventKey={TAB_CT} title="CT Monitor">
            <CTMonitorInner embedded />
          </Tab>
        )}
      </Tabs>
    </Container>
  );
}

export default SystemStatus;
