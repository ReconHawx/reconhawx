import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Alert,
  Button,
  Spinner,
  Form,
  Badge,
  Table,
  Modal
} from 'react-bootstrap';
import { adminAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

import './SystemMaintenance.css';

function formatBytes(n) {
  if (n == null || Number.isNaN(n)) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  if (n < 1024 ** 3) return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(n / 1024 ** 3).toFixed(2)} GiB`;
}

const CLUSTER_QUEUE_NAMES = [
  'runner-cluster-queue',
  'worker-cluster-queue',
  'ai-analysis-cluster-queue'
];

/** True when maintenance Hold is set on all queues (admitted jobs keep running; no new admissions). */
function allClusterQueuesOnHold(policies) {
  if (!policies || typeof policies !== 'object') return false;
  return CLUSTER_QUEUE_NAMES.every((n) => policies[n] === 'Hold');
}

function isDrainQuiescent(d) {
  if (!d) return false;
  const w = d.active_kueue_workloads_count ?? 0;
  const j = d.running_batch_jobs_count ?? 0;
  return w === 0 && j === 0;
}

/** Normalize API stopPolicy (null, missing, or legacy string "None"). */
function isStopPolicyUnset(policy) {
  return policy == null || policy === '' || policy === 'None';
}

function StopPolicyBadge({ policy }) {
  if (isStopPolicyUnset(policy)) {
    return (
      <Badge bg="light" text="dark" className="border maintenance-policy-badge-unset">
        No stop policy
      </Badge>
    );
  }
  const p = String(policy);
  if (p === 'Hold') {
    return (
      <Badge bg="warning" text="dark">
        Hold
      </Badge>
    );
  }
  if (p === 'HoldAndDrain') {
    return (
      <Badge bg="danger">
        HoldAndDrain
      </Badge>
    );
  }
  return <Badge bg="info">{p}</Badge>;
}

function DrainStatusPanel({ drainStatus }) {
  const policies = drainStatus.cluster_queue_stop_policies || {};
  const queueRows = CLUSTER_QUEUE_NAMES.map((name) => ({
    name,
    policy: policies[name]
  }));
  const wCount = drainStatus.active_kueue_workloads_count ?? 0;
  const jCount = drainStatus.running_batch_jobs_count ?? 0;
  const workloads = Array.isArray(drainStatus.active_kueue_workloads)
    ? drainStatus.active_kueue_workloads
    : [];
  const batchJobs = Array.isArray(drainStatus.running_batch_jobs) ? drainStatus.running_batch_jobs : [];

  return (
    <div className="small">
      <Table responsive bordered size="sm" className="mb-3 maintenance-drain-table">
        <thead>
          <tr>
            <th scope="col">ClusterQueue</th>
            <th scope="col">Stop policy</th>
          </tr>
        </thead>
        <tbody>
          {queueRows.map(({ name, policy }) => (
            <tr key={name}>
              <td>
                <code className="small">{name}</code>
              </td>
              <td>
                <StopPolicyBadge policy={policy} />
              </td>
            </tr>
          ))}
        </tbody>
      </Table>

      <dl className="row mb-2">
        <dt className="col-sm-5 col-md-4">Active Kueue workloads</dt>
        <dd className="col-sm-7 col-md-8 mb-0">
          <span className={wCount > 0 ? 'fw-semibold text-warning' : 'text-success'}>{wCount}</span>
          {wCount > 0 ? <span className="text-muted ms-1">(still draining or queued)</span> : null}
        </dd>
        <dt className="col-sm-5 col-md-4">Running batch Jobs</dt>
        <dd className="col-sm-7 col-md-8 mb-0">
          <span className={jCount > 0 ? 'fw-semibold text-warning' : 'text-success'}>{jCount}</span>
          {jCount > 0 ? <span className="text-muted ms-1">(excluding restore Job)</span> : null}
        </dd>
      </dl>

      {workloads.length > 0 ? (
        <details className="mb-2">
          <summary className="text-muted" role="button">
            Workload names ({workloads.length})
          </summary>
          <ul className="mb-0 mt-1 ps-3">
            {workloads.map((n) => (
              <li key={n}>
                <code className="small">{n}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {batchJobs.length > 0 ? (
        <details className="mb-0">
          <summary className="text-muted" role="button">
            Batch Job names ({batchJobs.length})
          </summary>
          <ul className="mb-0 mt-1 ps-3">
            {batchJobs.map((n) => (
              <li key={n}>
                <code className="small">{n}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

const MAINTENANCE_DRAIN_POLL_MS = 5000;
const MAINTENANCE_DRAIN_TIMEOUT_MS = 30 * 60 * 1000;

function SystemMaintenance() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [backupFormat, setBackupFormat] = useState('custom');
  const [backupLoading, setBackupLoading] = useState(false);

  const [maintEnabled, setMaintEnabled] = useState(false);
  const [maintMessage, setMaintMessage] = useState('');
  const [maintEnvOverride, setMaintEnvOverride] = useState(false);
  const [maintSaving, setMaintSaving] = useState(false);
  const [showMaintActivateModal, setShowMaintActivateModal] = useState(false);
  const [maintActivateProgress, setMaintActivateProgress] = useState('');

  const [drainStatus, setDrainStatus] = useState(null);
  const [drainLoading, setDrainLoading] = useState(false);

  const [jobStageFile, setJobStageFile] = useState(null);
  const [jobStagingId, setJobStagingId] = useState('');
  const [jobStageLoading, setJobStageLoading] = useState(false);
  const [jobConfirm, setJobConfirm] = useState('');
  const [jobName, setJobName] = useState('');
  const [jobRunLoading, setJobRunLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const [jobPollLoading, setJobPollLoading] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await adminAPI.getDatabaseBackupStatus();
      setStatus(data);
    } catch (err) {
      setStatus(null);
      setError(err?.response?.data?.detail || 'Failed to load database status');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMaintenanceSettings = useCallback(async () => {
    try {
      const data = await adminAPI.getMaintenanceSettings();
      const s = data?.settings || {};
      setMaintEnabled(!!s.enabled);
      setMaintMessage(s.message || '');
      setMaintEnvOverride(!!data?.effective?.env_override_active);
    } catch (err) {
      /* non-fatal */
    }
  }, []);

  usePageTitle(formatPageTitle('System Maintenance'));

  useEffect(() => {
    loadStatus();
    loadMaintenanceSettings();
  }, [loadStatus, loadMaintenanceSettings]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await adminAPI.kueueDrainStatus();
        if (!cancelled) setDrainStatus(d);
      } catch {
        /* ignore — user can refresh drain card */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const canRestore = useMemo(() => {
    const apiMaintOn = status?.maintenance_effective === true;
    if (!apiMaintOn || !drainStatus) return false;
    if (!allClusterQueuesOnHold(drainStatus.cluster_queue_stop_policies)) return false;
    if (!isDrainQuiescent(drainStatus)) return false;
    return true;
  }, [status?.maintenance_effective, drainStatus]);

  const handleDownload = async () => {
    setError('');
    setSuccess('');
    setBackupLoading(true);
    try {
      const { blob, filename } = await adminAPI.downloadDatabaseBackup(backupFormat);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      setSuccess(`Download started: ${filename}`);
    } catch (err) {
      const d = err?.response?.data;
      const msg =
        (typeof d?.detail === 'string' && d.detail) ||
        (d?.detail && JSON.stringify(d.detail)) ||
        err?.message ||
        'Backup failed';
      setError(msg);
    } finally {
      setBackupLoading(false);
    }
  };

  const applyMaintenanceSettings = async (enabled) => {
    setMaintSaving(true);
    setError('');
    try {
      await adminAPI.putMaintenanceSettings({
        enabled,
        message: maintMessage
      });
      setSuccess(
        enabled ? 'Maintenance mode is now active.' : 'Maintenance mode is now deactivated.'
      );
      await loadMaintenanceSettings();
      await loadStatus();
    } catch (err) {
      const d = err?.response?.data;
      setError(
        (typeof d?.detail === 'string' && d.detail) ||
          (d?.detail && JSON.stringify(d.detail)) ||
          'Failed to update maintenance settings'
      );
    } finally {
      setMaintSaving(false);
    }
  };

  const confirmActivateMaintenance = async () => {
    setMaintSaving(true);
    setError('');
    setMaintActivateProgress('');
    const deadline = Date.now() + MAINTENANCE_DRAIN_TIMEOUT_MS;
    try {
      setMaintActivateProgress('Applying Hold to all ClusterQueues (running jobs continue)…');
      await adminAPI.kueueHoldClusterQueues();

      let d;
      setMaintActivateProgress('Waiting for Kueue workloads and batch jobs to finish (running jobs can still call the API)…');
      do {
        d = await adminAPI.kueueDrainStatus();
        setDrainStatus(d);
        if (isDrainQuiescent(d) && allClusterQueuesOnHold(d.cluster_queue_stop_policies)) {
          break;
        }
        if (Date.now() > deadline) {
          throw new Error(
            'Timed out waiting for queues to drain. Check drain status below; you can retry activation or finish manually.'
          );
        }
        const w = d.active_kueue_workloads_count ?? 0;
        const j = d.running_batch_jobs_count ?? 0;
        setMaintActivateProgress(
          `Waiting for Kueue workloads and batch jobs to finish (${w} active workload(s), ${j} running batch job(s))…`
        );
        await sleep(MAINTENANCE_DRAIN_POLL_MS);
      } while (true);

      setMaintActivateProgress('Enabling API maintenance mode (503 for non-admin traffic)…');
      await adminAPI.putMaintenanceSettings({
        enabled: true,
        message: maintMessage
      });

      setShowMaintActivateModal(false);
      setMaintActivateProgress('');
      setSuccess(
        'System maintenance is active: Kueue is holding and drained, and API maintenance is on. You may restore the database when ready.'
      );
      await loadMaintenanceSettings();
      await loadStatus();
      try {
        const latest = await adminAPI.kueueDrainStatus();
        setDrainStatus(latest);
      } catch {
        /* ignore */
      }
    } catch (err) {
      const msg =
        err?.message ||
        (typeof err?.response?.data?.detail === 'string' && err.response.data.detail) ||
        (err?.response?.data?.detail && JSON.stringify(err.response.data.detail)) ||
        'Failed to activate system maintenance';
      setError(msg);
      try {
        const latest = await adminAPI.kueueDrainStatus();
        setDrainStatus(latest);
      } catch {
        /* ignore */
      }
    } finally {
      setMaintSaving(false);
      setMaintActivateProgress('');
    }
  };

  const deactivateMaintenance = async () => {
    await applyMaintenanceSettings(false);
  };

  const refreshDrain = async () => {
    setDrainLoading(true);
    setError('');
    try {
      const d = await adminAPI.kueueDrainStatus();
      setDrainStatus(d);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : 'Drain status failed'
      );
    } finally {
      setDrainLoading(false);
    }
  };

  const runApplyHold = async () => {
    setError('');
    try {
      await adminAPI.kueueHoldClusterQueues();
      setSuccess('Kueue ClusterQueues set to Hold (no new work; running jobs continue).');
      await refreshDrain();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Apply Hold failed');
    }
  };

  const runClearStop = async () => {
    setError('');
    try {
      await adminAPI.kueueClearStopPolicy();
      setSuccess('Kueue stopPolicy cleared on all four cluster queues.');
      await refreshDrain();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Clear stop policy failed');
    }
  };

  const handleStageJob = async () => {
    if (!canRestore) {
      setError(
        'Staging is only allowed after Kueue is on Hold, drained, and API maintenance is active.'
      );
      return;
    }
    if (!jobStageFile) {
      setError('Choose a dump file to stage for the Job.');
      return;
    }
    setJobStageLoading(true);
    setError('');
    try {
      const res = await adminAPI.stageDatabaseRestore(jobStageFile);
      setJobStagingId(res.staging_id);
      setSuccess(`Staged ${formatBytes(res.bytes)} — staging_id ready for Job.`);
      setJobStageFile(null);
      const el = document.getElementById('job-stage-file');
      if (el) el.value = '';
    } catch (err) {
      const d = err?.response?.data;
      setError(
        (typeof d?.detail === 'string' && d.detail) ||
          (d?.detail && JSON.stringify(d.detail)) ||
          'Stage failed'
      );
    } finally {
      setJobStageLoading(false);
    }
  };

  const handleCreateJob = async () => {
    if (!canRestore) {
      setError(
        'Restore jobs are only allowed after Kueue is on Hold, drained, and API maintenance is active.'
      );
      return;
    }
    if (!jobStagingId) {
      setError('Stage a dump first.');
      return;
    }
    if (jobConfirm !== 'RESTORE_DATABASE') {
      setError('Type RESTORE_DATABASE to create the restore Job.');
      return;
    }
    setJobRunLoading(true);
    setError('');
    try {
      const res = await adminAPI.createDatabaseRestoreJob(jobStagingId, jobConfirm);
      setJobName(res.job_name);
      setSuccess(`Job created: ${res.job_name}`);
      setJobStatus(null);
    } catch (err) {
      const d = err?.response?.data;
      setError(
        (typeof d?.detail === 'string' && d.detail) ||
          (d?.detail && JSON.stringify(d.detail)) ||
          'Create Job failed'
      );
    } finally {
      setJobRunLoading(false);
    }
  };

  const pollJob = async () => {
    if (!jobName) return;
    setJobPollLoading(true);
    setError('');
    try {
      const s = await adminAPI.getDatabaseRestoreJobStatus(jobName);
      setJobStatus(s);
    } catch (err) {
      const d = err?.response?.data;
      setError(
        (typeof d?.detail === 'string' && d.detail) ||
          (d?.detail && JSON.stringify(d.detail)) ||
          'Job status failed'
      );
    } finally {
      setJobPollLoading(false);
    }
  };

  const toolsOk =
    status?.pg_dump_available &&
    status?.pg_restore_available;

  const kueueAllHold = useMemo(
    () => allClusterQueuesOnHold(drainStatus?.cluster_queue_stop_policies),
    [drainStatus?.cluster_queue_stop_policies]
  );

  return (
    <Container className="mt-4">
      <Row className="mb-3 align-items-center">
        <Col>
          <h4 className="mb-0">System maintenance</h4>
          <p className="text-muted small mb-0 mt-1">
            Superuser-only. Pause Kueue (Hold: no new admissions, running jobs finish), then gate the API for upgrades or DB
            restore. Prefer cluster Job restore in production; see docs for Redis/NATS after restore.
          </p>
        </Col>
        <Col xs="auto">
          <Button size="sm" variant="outline-secondary" onClick={loadStatus} disabled={loading}>
            {loading ? <Spinner animation="border" size="sm" /> : 'Refresh status'}
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
          <Card className="mb-4">
            <Card.Header>Status</Card.Header>
            <Card.Body className="p-0">
              <Table borderless responsive className="mb-0 small">
                <tbody>
                  <tr>
                    <td className="text-muted w-25">pg_dump / pg_restore</td>
                    <td>
                      {toolsOk ? (
                        <Badge bg="success">Available</Badge>
                      ) : (
                        <Badge bg="warning" text="dark">
                          Missing in container (install postgresql-client in API image)
                        </Badge>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td className="text-muted">Database</td>
                    <td>
                      <code>{status?.database_name}</code> @ <code>{status?.postgres_host}</code>:
                      {status?.postgres_port}
                    </td>
                  </tr>
                  <tr>
                    <td className="text-muted">Size</td>
                    <td>{formatBytes(status?.database_size_bytes)}</td>
                  </tr>
                  <tr>
                    <td className="text-muted">Server</td>
                    <td className="text-break">{status?.server_version || '—'}</td>
                  </tr>
                  <tr>
                    <td className="text-muted">Maintenance (effective)</td>
                    <td>
                      {status?.maintenance_effective ? (
                        <Badge bg="warning" text="dark">
                          On
                        </Badge>
                      ) : (
                        <Badge bg="secondary">Off</Badge>
                      )}
                      {status?.maintenance_env_override ? (
                        <span className="ms-2 text-muted">(env override)</span>
                      ) : null}
                    </td>
                  </tr>
                  <tr>
                    <td className="text-muted">Database restore gated</td>
                    <td>
                      {canRestore ? (
                        <Badge bg="success">Ready (maint + Hold + drained)</Badge>
                      ) : (
                        <Badge bg="secondary">Not ready</Badge>
                      )}
                    </td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>

          <Card className="mb-4">
            <Card.Header>System maintenance (Kueue + API)</Card.Header>
            <Card.Body>
              <p className="small text-muted mb-3">
                <strong>Activate</strong> applies Kueue <code>Hold</code> to all ClusterQueues, waits until
                Kueue workloads and batch jobs finish (so runners can still reach the API), then turns on API
                maintenance (503 for non-admin traffic). <code>/admin/database/</code> and{' '}
                <code>/status</code> stay available. Optional <code>MAINTENANCE_MODE</code> env still forces
                maintenance (break-glass). Use <strong>Deactivate</strong> to clear API maintenance only;
                clear Kueue stop policy in the section below if you need new jobs admitted.
              </p>
              {maintEnvOverride ? (
                <Alert variant="warning" className="py-2 small">
                  Environment <code>MAINTENANCE_MODE</code> is active; turn it off on the Deployment to
                  rely on the DB toggle only.
                </Alert>
              ) : null}
              <Form.Group className="mb-3">
                <Form.Label>Optional message (shown in 503 JSON)</Form.Label>
                <Form.Control
                  value={maintMessage}
                  onChange={(e) => setMaintMessage(e.target.value)}
                  placeholder="We are restoring the database…"
                  disabled={maintEnvOverride}
                />
              </Form.Group>
              <div className="d-flex flex-wrap gap-2 align-items-center">
                {maintEnvOverride ? (
                  <Button variant="secondary" size="sm" disabled>
                    Controlled by deployment env
                  </Button>
                ) : maintEnabled ? (
                  <Button
                    variant="success"
                    size="sm"
                    onClick={deactivateMaintenance}
                    disabled={maintSaving}
                  >
                    {maintSaving ? <Spinner animation="border" size="sm" /> : 'Deactivate Maintenance Mode'}
                  </Button>
                ) : (
                  <Button
                    variant="warning"
                    size="sm"
                    onClick={() => setShowMaintActivateModal(true)}
                    disabled={maintSaving}
                  >
                    Activate Maintenance Mode
                  </Button>
                )}
              </div>
            </Card.Body>
          </Card>

          <Modal
            show={showMaintActivateModal}
            onHide={() => !maintSaving && setShowMaintActivateModal(false)}
            backdrop={maintSaving ? 'static' : true}
            keyboard={!maintSaving}
            centered
          >
            <Modal.Header closeButton>
              <Modal.Title>Activate maintenance mode?</Modal.Title>
            </Modal.Header>
            <Modal.Body>
              <p className="mb-2">
                This will (1) set all ClusterQueues to Kueue <code>Hold</code> (no new admissions; already running jobs
                keep going), (2) wait until active Kueue workloads and running batch jobs finish, then (3) enable API
                maintenance so most routes return <strong>503</strong>. Until step (3), running jobs can still use the API.
              </p>
              <p className="mb-2 small text-muted">
                Drain wait can take up to 30 minutes before failing. Set the optional message above for
                custom 503 text.
              </p>
              {maintActivateProgress ? (
                <Alert variant="info" className="mb-0 py-2 small">
                  {maintActivateProgress}
                </Alert>
              ) : null}
            </Modal.Body>
            <Modal.Footer>
              <Button
                variant="secondary"
                onClick={() => setShowMaintActivateModal(false)}
                disabled={maintSaving}
              >
                Cancel
              </Button>
              <Button variant="warning" onClick={confirmActivateMaintenance} disabled={maintSaving}>
                {maintSaving ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-2" />
                    Activating…
                  </>
                ) : (
                  'Activate Maintenance Mode'
                )}
              </Button>
            </Modal.Footer>
          </Modal>

          <Card className="mb-4">
            <Card.Header>Kueue (Hold)</Card.Header>
            <Card.Body>
              <p className="small text-muted">
                Applies Kueue <strong>Hold</strong> on all four ClusterQueues: new work is not admitted; workloads already
                admitted keep running until they finish. (<code>HoldAndDrain</code> is different — it evicts running jobs.)
                Activation runs this automatically first; use these controls for manual adjustments without enabling API
                maintenance.
              </p>
              <div className="d-flex flex-wrap gap-2 mb-3 align-items-center">
                {!kueueAllHold ? (
                  <Button size="sm" variant="warning" onClick={runApplyHold}>
                    Apply Hold
                  </Button>
                ) : (
                  <Button size="sm" variant="outline-danger" onClick={runClearStop}>
                    Clear stop policy
                  </Button>
                )}
                <Button size="sm" variant="outline-secondary" onClick={refreshDrain} disabled={drainLoading}>
                  {drainLoading ? <Spinner animation="border" size="sm" /> : 'Refresh drain status'}
                </Button>
              </div>
              {drainStatus ? (
                <div className="maintenance-drain-panel p-2 rounded border">
                  <DrainStatusPanel drainStatus={drainStatus} />
                </div>
              ) : null}
            </Card.Body>
          </Card>

          <Card className="mb-4 border-primary">
            <Card.Header>Cluster restore (Kubernetes Job)</Card.Header>
            <Card.Body>
              <p className="small text-muted">
                Stage a custom-format dump, then create a Job that pulls it with cluster credentials and
                runs <code>pg_restore</code>. Requires <code>internal-service-secret</code> and API RBAC
                to create Jobs.
              </p>
              {!canRestore ? (
                <Alert variant="warning" className="small py-2">
                  Restore is <strong>locked</strong> until API maintenance is <strong>on</strong>, all four
                  ClusterQueues are on <code>Hold</code>, and there are no active Kueue workloads or running batch jobs.
                  Use <strong>Activate Maintenance Mode</strong> (or align Kueue + API manually), then refresh drain
                  status.
                </Alert>
              ) : null}
              <Row>
                <Col md={6}>
                  <Form.Group className="mb-2">
                    <Form.Label>1. Stage dump</Form.Label>
                    <Form.Control
                      id="job-stage-file"
                      type="file"
                      accept=".dump,application/octet-stream"
                      disabled={!canRestore || jobStageLoading}
                      onChange={(e) => setJobStageFile(e.target.files?.[0] || null)}
                    />
                  </Form.Group>
                  <Button
                    size="sm"
                    variant="outline-primary"
                    className="mb-3"
                    onClick={handleStageJob}
                    disabled={!canRestore || jobStageLoading}
                  >
                    {jobStageLoading ? <Spinner size="sm" animation="border" /> : 'Upload / stage'}
                  </Button>
                  {jobStagingId ? (
                    <p className="small">
                      <strong>staging_id:</strong> <code>{jobStagingId}</code>
                    </p>
                  ) : null}
                </Col>
                <Col md={6}>
                  <Form.Group className="mb-2">
                    <Form.Label>2. Confirm Job</Form.Label>
                    <Form.Control
                      value={jobConfirm}
                      onChange={(e) => setJobConfirm(e.target.value)}
                      placeholder="RESTORE_DATABASE"
                      autoComplete="off"
                      disabled={!canRestore}
                    />
                  </Form.Group>
                  <Button
                    size="sm"
                    variant="danger"
                    className="mb-2"
                    onClick={handleCreateJob}
                    disabled={!canRestore || jobRunLoading || !jobStagingId}
                  >
                    {jobRunLoading ? <Spinner size="sm" animation="border" /> : 'Create restore Job'}
                  </Button>
                  {jobName ? (
                    <div className="small mt-2">
                      <div>
                        <strong>job:</strong> <code>{jobName}</code>
                      </div>
                      <Button
                        size="sm"
                        variant="outline-secondary"
                        className="mt-2"
                        onClick={pollJob}
                        disabled={jobPollLoading}
                      >
                        {jobPollLoading ? <Spinner size="sm" animation="border" /> : 'Poll status'}
                      </Button>
                    </div>
                  ) : null}
                </Col>
              </Row>
              {jobStatus?.found ? (
                <pre className="maintenance-json-pre">
                  {JSON.stringify(
                    {
                      phase: jobStatus.phase,
                      active: jobStatus.active,
                      succeeded: jobStatus.succeeded,
                      failed: jobStatus.failed,
                      conditions: jobStatus.conditions
                    },
                    null,
                    2
                  )}
                </pre>
              ) : null}
            </Card.Body>
          </Card>

          <Card className="mb-4">
            <Card.Header>Backup</Card.Header>
            <Card.Body>
              <p className="small text-muted">
                Downloads a logical dump of the application database. Use <strong>custom</strong> format for{' '}
                <strong>Cluster restore (Job)</strong> above.
              </p>
              <Form.Group className="mb-3">
                <Form.Label>Format</Form.Label>
                <Form.Select
                  value={backupFormat}
                  onChange={(e) => setBackupFormat(e.target.value)}
                  disabled={!toolsOk || backupLoading}
                >
                  <option value="custom">Custom (pg_dump -Fc, for Job restore)</option>
                  <option value="plain">Plain SQL (-Fp)</option>
                </Form.Select>
              </Form.Group>
              <Button variant="primary" onClick={handleDownload} disabled={!toolsOk || backupLoading}>
                {backupLoading ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-2" />
                    Preparing…
                  </>
                ) : (
                  'Download backup'
                )}
              </Button>
            </Card.Body>
          </Card>
        </>
      )}
    </Container>
  );
}

export default SystemMaintenance;
