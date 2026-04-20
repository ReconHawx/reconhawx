import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Modal,
  Row,
  Spinner,
  Table
} from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { adminAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

import './SystemUpgrade.css';

const CLUSTER_QUEUE_NAMES = ['runner-cluster-queue', 'worker-cluster-queue', 'ai-analysis-cluster-queue'];

function allClusterQueuesOnHold(policies) {
  if (!policies || typeof policies !== 'object') return false;
  return CLUSTER_QUEUE_NAMES.every((n) => policies[n] === 'Hold');
}

function formatBytes(n) {
  if (n == null || Number.isNaN(n)) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  if (n < 1024 ** 3) return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(n / 1024 ** 3).toFixed(2)} GiB`;
}

function SystemUpgrade() {
  usePageTitle(formatPageTitle('System upgrade'));

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [status, setStatus] = useState(null);
  const [drainStatus, setDrainStatus] = useState(null);

  const [version, setVersion] = useState('latest');
  const [stagingId, setStagingId] = useState('');
  const [stageFile, setStageFile] = useState(null);
  const [stageLoading, setStageLoading] = useState(false);
  const [kueueResync, setKueueResync] = useState(false);
  const [allowWithoutHold, setAllowWithoutHold] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [jobLoading, setJobLoading] = useState(false);
  const [jobName, setJobName] = useState('');
  const [jobStatus, setJobStatus] = useState(null);
  const [jobLog, setJobLog] = useState('');

  const kueueAllHold = useMemo(
    () => allClusterQueuesOnHold(drainStatus?.cluster_queue_stop_policies),
    [drainStatus?.cluster_queue_stop_policies]
  );

  const canStartUpgrade = allowWithoutHold || kueueAllHold;

  const loadDrain = useCallback(async () => {
    try {
      const d = await adminAPI.kueueDrainStatus();
      setDrainStatus(d);
    } catch {
      setDrainStatus(null);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const s = await adminAPI.getSystemUpgradeStatus();
      setStatus(s);
      await loadDrain();
    } catch (err) {
      const d = err?.response?.data;
      setError(
        (typeof d?.detail === 'string' && d.detail) ||
          (d?.detail && JSON.stringify(d.detail)) ||
          'Failed to load upgrade status'
      );
    } finally {
      setLoading(false);
    }
  }, [loadDrain]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  /** Resume watching a non-terminal upgrade Job after reload */
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const jobsRes = await adminAPI.listSystemUpgradeJobs();
        if (!alive) return;
        if (!Array.isArray(jobsRes.jobs) || jobsRes.jobs.length === 0) return;
        const top = jobsRes.jobs[0];
        const ph = top.phase;
        if (top.job_name && ph && ph !== 'succeeded' && ph !== 'failed') {
          setJobName((prev) => prev || top.job_name);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!jobName) return undefined;
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await adminAPI.getSystemUpgradeJobStatus(jobName);
        if (cancelled) return;
        setJobStatus(s);
        try {
          const lg = await adminAPI.getSystemUpgradeJobLogs(jobName, { tail_lines: 400 });
          if (!cancelled) setJobLog(lg.log || '');
        } catch {
          if (!cancelled) setJobLog('');
        }
      } catch {
        /* API may restart during upgrade */
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [jobName]);

  const handleStage = async () => {
    if (!stageFile) {
      setError('Choose a source tarball (.tar.gz).');
      return;
    }
    setStageLoading(true);
    setError('');
    try {
      const res = await adminAPI.stageSystemUpgrade(stageFile);
      setStagingId(res.staging_id);
      setSuccess(`Staged ${formatBytes(res.bytes)} — staging_id set.`);
      setStageFile(null);
      const el = document.getElementById('upgrade-stage-file');
      if (el) el.value = '';
    } catch (err) {
      const d = err?.response?.data;
      setError(
        (typeof d?.detail === 'string' && d.detail) ||
          (d?.detail && JSON.stringify(d.detail)) ||
          'Stage failed'
      );
    } finally {
      setStageLoading(false);
    }
  };

  const handleCreateJob = async () => {
    if (!canStartUpgrade) {
      setError('Put all ClusterQueues on Hold (System maintenance) or enable “allow without Hold”.');
      return;
    }
    if (confirmText !== 'UPGRADE_RECONHAWX') {
      setError('Type UPGRADE_RECONHAWX to confirm.');
      return;
    }
    const ver = version.trim();
    if (!/^(latest|\d+\.\d+\.\d+)$/.test(ver)) {
      setError('Version must be "latest" or semver x.y.z.');
      return;
    }
    setJobLoading(true);
    setError('');
    try {
      const body = {
        version: ver,
        kueue_resync_quotas: kueueResync,
        confirm: 'UPGRADE_RECONHAWX'
      };
      const sid = stagingId.trim();
      if (sid) body.staging_id = sid;
      const res = await adminAPI.createSystemUpgradeJob(body);
      setJobName(res.job_name);
      setShowConfirm(false);
      setConfirmText('');
      setSuccess(`Upgrade Job created: ${res.job_name}`);
      setJobStatus(null);
      setJobLog('');
    } catch (err) {
      const d = err?.response?.data;
      setError(
        (typeof d?.detail === 'string' && d.detail) ||
          (d?.detail && JSON.stringify(d.detail)) ||
          'Create upgrade Job failed'
      );
    } finally {
      setJobLoading(false);
    }
  };

  return (
    <Container className="mt-4 system-upgrade-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h4 className="mb-0">System upgrade</h4>
          <p className="text-muted small mb-0 mt-1">
            Superuser-only. Applies <code>kubernetes/base-update</code> from a GitHub release tarball (or staged upload)
            inside the cluster, then rolls API / frontend / event-handler / ct-monitor. See{' '}
            <Link to="/admin/system-maintenance">System maintenance</Link> to Hold Kueue first.
          </p>
        </Col>
        <Col xs="auto">
          <Button size="sm" variant="outline-secondary" onClick={loadStatus} disabled={loading}>
            {loading ? <Spinner animation="border" size="sm" /> : 'Refresh'}
          </Button>
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

      {loading && !status ? (
        <div className="text-center py-5">
          <Spinner animation="border" />
        </div>
      ) : (
        <>
          <Card className="mb-4 upgrade-section-card">
            <Card.Header>Versions</Card.Header>
            <Card.Body>
              <Table borderless size="sm" className="mb-0">
                <tbody>
                  <tr>
                    <td className="text-muted w-25">Cluster (ConfigMap)</td>
                    <td>
                      <code>{status?.cluster_version || '—'}</code>
                    </td>
                  </tr>
                  <tr>
                    <td className="text-muted">This API bundle</td>
                    <td>
                      <code>{status?.bundle_version || '—'}</code>
                    </td>
                  </tr>
                  <tr>
                    <td className="text-muted">GitHub latest</td>
                    <td>
                      <code>{status?.latest_release || '—'}</code>{' '}
                      {status?.github_reachable === false ? (
                        <Badge bg="secondary">unreachable</Badge>
                      ) : null}
                    </td>
                  </tr>
                  <tr>
                    <td className="text-muted">Repo</td>
                    <td>
                      <code>{status?.github_repo || '—'}</code>
                    </td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>

          <Card className="mb-4 upgrade-section-card">
            <Card.Header>Kueue</Card.Header>
            <Card.Body>
              <p className="small text-muted mb-2">
                Recommended: put all ClusterQueues on <strong>Hold</strong> on{' '}
                <Link to="/admin/system-maintenance">System maintenance</Link> before upgrading.
              </p>
              <Form.Check
                type="checkbox"
                id="allow-without-hold"
                label="Allow starting upgrade while ClusterQueues are not all on Hold (not recommended)"
                checked={allowWithoutHold}
                onChange={(e) => setAllowWithoutHold(e.target.checked)}
                className="mb-0"
              />
              {!kueueAllHold && !allowWithoutHold ? (
                <Alert variant="warning" className="mt-3 mb-0 py-2 small">
                  All ClusterQueues must be on Hold unless you check the box above.
                </Alert>
              ) : null}
              {drainStatus?.cluster_queue_stop_policies ? (
                <Table responsive size="sm" className="mt-3 mb-0 small">
                  <thead>
                    <tr>
                      <th>ClusterQueue</th>
                      <th>stopPolicy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {CLUSTER_QUEUE_NAMES.map((n) => (
                      <tr key={n}>
                        <td>
                          <code>{n}</code>
                        </td>
                        <td>{String(drainStatus.cluster_queue_stop_policies[n] ?? '—')}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : null}
            </Card.Body>
          </Card>

          <Card className="mb-4 upgrade-section-card">
            <Card.Header>Upgrade target</Card.Header>
            <Card.Body>
              <Form.Group className="mb-3">
                <Form.Label>Version</Form.Label>
                <Form.Control
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  placeholder='latest or e.g. 0.20.0'
                />
                <Form.Text className="text-muted">
                  With a staged tarball, the Job still uses this value for metadata; tarball content drives manifests.
                </Form.Text>
              </Form.Group>
              <Form.Group className="mb-3">
                <Form.Check
                  type="checkbox"
                  id="kueue-resync"
                  label="Run Kueue quota sync after apply (RECONHAWX_KUEUE_RESYNC_QUOTAS=1)"
                  checked={kueueResync}
                  onChange={(e) => setKueueResync(e.target.checked)}
                />
              </Form.Group>
              <hr />
              <h6 className="text-muted">Air-gapped: stage tarball</h6>
              <Form.Group className="mb-2">
                <Form.Control
                  id="upgrade-stage-file"
                  type="file"
                  accept=".tar.gz,.tgz,application/gzip"
                  onChange={(e) => setStageFile(e.target.files?.[0] || null)}
                />
              </Form.Group>
              <Button
                size="sm"
                variant="outline-primary"
                onClick={handleStage}
                disabled={stageLoading || !stageFile}
              >
                {stageLoading ? <Spinner animation="border" size="sm" /> : 'Upload & stage'}
              </Button>
              {stagingId ? (
                <p className="small mt-2 mb-0">
                  <code>staging_id</code>: {stagingId}
                </p>
              ) : null}
            </Card.Body>
          </Card>

          <Card className="mb-4 upgrade-section-card">
            <Card.Header>Run upgrade</Card.Header>
            <Card.Body>
              <Button
                variant="danger"
                disabled={!canStartUpgrade || jobLoading}
                onClick={() => {
                  setError('');
                  setShowConfirm(true);
                }}
              >
                Start upgrade…
              </Button>
              {jobName ? (
                <div className="mt-3">
                  <div className="small text-muted mb-1">Active / last Job</div>
                  <code>{jobName}</code>
                  {jobStatus ? (
                    <div className="mt-2 small">
                      <Badge bg={jobStatus.phase === 'succeeded' ? 'success' : jobStatus.phase === 'failed' ? 'danger' : 'info'}>
                        {jobStatus.phase || '—'}
                      </Badge>
                      {jobStatus.pod_name ? (
                        <span className="ms-2 text-muted">
                          pod <code>{jobStatus.pod_name}</code>
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {jobLog ? (
                    <pre className="mt-2 p-2 bg-light border rounded upgrade-log-pre">{jobLog}</pre>
                  ) : (
                    <p className="small text-muted mt-2 mb-0">Logs appear when the Job pod starts.</p>
                  )}
                  <p className="small text-warning mt-2 mb-0">
                    The API will restart during this Job; the page may briefly fail to load — it should recover.
                  </p>
                </div>
              ) : null}
            </Card.Body>
          </Card>

          {Array.isArray(status?.recent_upgrade_jobs) && status.recent_upgrade_jobs.length > 0 ? (
            <Card className="mb-4 upgrade-section-card">
              <Card.Header>Recent Jobs</Card.Header>
              <Card.Body className="p-0">
                <Table responsive size="sm" className="mb-0">
                  <thead>
                    <tr>
                      <th>Job</th>
                      <th>Phase</th>
                      <th>Started</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.recent_upgrade_jobs.map((j) => (
                      <tr key={j.job_name}>
                        <td>
                          <code className="small">{j.job_name}</code>
                        </td>
                        <td>{j.phase || '—'}</td>
                        <td className="small text-muted">{j.creation_timestamp || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Card.Body>
            </Card>
          ) : null}
        </>
      )}

      <Modal show={showConfirm} onHide={() => !jobLoading && setShowConfirm(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Confirm cluster upgrade</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p className="small">
            This creates a Kubernetes Job that runs <code>kubectl apply -k kubernetes/base-update/</code> and
            restarts application Deployments. Type <strong>UPGRADE_RECONHAWX</strong> to confirm.
          </p>
          <Form.Control
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="UPGRADE_RECONHAWX"
            autoComplete="off"
          />
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowConfirm(false)} disabled={jobLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={handleCreateJob} disabled={jobLoading}>
            {jobLoading ? <Spinner animation="border" size="sm" /> : 'Create Job'}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default SystemUpgrade;
