import React, { useState, useEffect, useCallback } from 'react';
import { Container, Row, Col, Card, Button, Table, Badge, Form, Dropdown, Modal, Alert } from 'react-bootstrap';
import { Link, useNavigate } from 'react-router-dom';
import { scheduledJobsAPI } from '../../services/api';
import { formatDate, formatRelativeTime } from '../../utils/dateUtils';
import { useAuth } from '../../contexts/AuthContext';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

const ScheduledJobs = () => {
  usePageTitle(formatPageTitle('Scheduled Jobs'));
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    status: '',
    jobType: ''
  });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [jobToDelete, setJobToDelete] = useState(null);
  const [actionLoading, setActionLoading] = useState({});
  
  const navigate = useNavigate();
  const { isSuperuser, isAdmin, user, hasProgramPermission } = useAuth();

  const hasAnyManagerPermission = () => {
    if (isSuperuser && isSuperuser()) return true;
    if (isAdmin && isAdmin()) return true;
    if (!user || !user.program_permissions) return false;
    const programPermissions = user.program_permissions || {};
    if (typeof programPermissions === 'object' && !Array.isArray(programPermissions)) {
      return Object.values(programPermissions).includes('manager');
    }
    return false;
  };

  const canManageJob = (job) => {
    if (isSuperuser && isSuperuser()) return true;
    if (isAdmin && isAdmin()) return true;
    const names =
      job?.program_names?.length > 0
        ? job.program_names
        : job?.program_name
          ? [job.program_name]
          : [];
    if (!names.length || !hasProgramPermission) return false;
    return names.every((n) => hasProgramPermission(n, 'manager'));
  };

  const loadJobs = useCallback(async () => {
    try {
      setLoading(true);
      const response = await scheduledJobsAPI.getAll(50, 0, filters.status || null, filters.jobType || null);
      setJobs(response || []);
      setError(null);
    } catch (err) {
      console.error('Error loading scheduled jobs:', err);
      setError('Failed to load scheduled jobs');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const handleDelete = async () => {
    if (!jobToDelete) return;
    
    try {
      setActionLoading(prev => ({ ...prev, [jobToDelete.schedule_id]: true }));
      await scheduledJobsAPI.delete(jobToDelete.schedule_id);
      setJobs(jobs.filter(job => job.schedule_id !== jobToDelete.schedule_id));
      setShowDeleteModal(false);
      setJobToDelete(null);
    } catch (err) {
      console.error('Error deleting job:', err);
      setError('Failed to delete scheduled job');
    } finally {
      setActionLoading(prev => ({ ...prev, [jobToDelete.schedule_id]: false }));
    }
  };

  const handleToggleStatus = async (scheduleId, shouldEnable) => {
    try {
      setActionLoading(prev => ({ ...prev, [scheduleId]: true }));
      setError(null); // Clear any previous errors

      if (shouldEnable) {
        await scheduledJobsAPI.enable(scheduleId);
      } else {
        await scheduledJobsAPI.disable(scheduleId);
      }

      // Reload jobs to get updated status
      await loadJobs();

    } catch (err) {
      console.error('Error toggling job status:', err);
      const action = shouldEnable ? 'enable' : 'disable';
      setError(`Failed to ${action} scheduled job: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [scheduleId]: false }));
    }
  };

  const handleRunNow = async (scheduleId) => {
    try {
      setActionLoading(prev => ({ ...prev, [scheduleId]: true }));
      await scheduledJobsAPI.runNow(scheduleId);
      // Reload jobs to get updated execution count
      await loadJobs();
    } catch (err) {
      console.error('Error running job:', err);
      setError('Failed to run job');
    } finally {
      setActionLoading(prev => ({ ...prev, [scheduleId]: false }));
    }
  };

  const getStatusBadge = (status) => {
    const variants = {
      'scheduled': 'primary',
      'running': 'warning',
      'completed': 'success',
      'failed': 'danger',
      'cancelled': 'secondary'
    };
    return <Badge bg={variants[status] || 'secondary'}>{status}</Badge>;
  };

  const getJobTypeLabel = (jobType) => {
    const labels = {
      'dummy_batch': 'Dummy Batch',
      'typosquat_batch': 'Typosquat Batch',
      'phishlabs_batch': 'PhishLabs Batch',
      'ai_analysis_batch': 'AI Analysis Batch',
      'workflow': 'Workflow'
    };
    return labels[jobType] || jobType;
  };

  // Calculate execution statistics for a job
  const getJobExecutionStats = (job) => {
    // If the job has execution count fields, use them
    if (job.total_executions !== undefined) {
      return {
        total: job.total_executions || 0,
        successful: job.successful_executions || 0,
        failed: job.failed_executions || 0
      };
    }
    
    // Otherwise, return default values
    return { total: 0, successful: 0, failed: 0 };
  };

  const getScheduleDescription = (schedule, lastRun, status) => {
    if (!schedule) return 'No schedule';
    
    const { schedule_type, recurring_schedule, cron_schedule } = schedule;
    
    switch (schedule_type) {
      case 'once':
        // For completed one-time jobs, show when it actually ran
        if (status === 'completed' && lastRun) {
          return `Once at ${formatDate(lastRun)} (executed)`;
        }
        // For pending one-time jobs, show when it's scheduled to run
        return `Once at ${formatDate(schedule.start_time)}`;
      case 'recurring':
        if (recurring_schedule) {
          if (recurring_schedule.interval_minutes) {
            return `Every ${recurring_schedule.interval_minutes} minutes`;
          } else if (recurring_schedule.interval_hours) {
            return `Every ${recurring_schedule.interval_hours} hours`;
          } else if (recurring_schedule.interval_days) {
            return `Every ${recurring_schedule.interval_days} days`;
          }
        }
        return 'Recurring schedule';
      case 'cron':
        if (cron_schedule) {
          return `Cron: ${cron_schedule.minute} ${cron_schedule.hour} ${cron_schedule.day_of_month} ${cron_schedule.month} ${cron_schedule.day_of_week}`;
        }
        return 'Cron schedule';
      default:
        return 'Unknown schedule';
    }
  };

  if (loading) {
    return (
      <Container fluid>
        <div className="d-flex justify-content-center align-items-center" style={{ height: '200px' }}>
          <div className="spinner-border" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
        </div>
      </Container>
    );
  }

  return (
    <Container fluid>
      <Row className="mb-3">
        <Col>
        <div className="container-fluid mt-4">
          <div className="row mb-4">
            <div className="col">
              <h2>⏰ Scheduled Jobs</h2>
              {hasAnyManagerPermission() && (
                <Button 
                  variant="primary" 
                  onClick={() => navigate('/scheduled-jobs/create')}
                >
                  ➕ Create New Job
                </Button>
              )}
            </div>
        </div>
        </div>
        </Col>
      </Row>

      {error && (
        <Row className="mb-3">
          <Col>
            <Alert variant="danger" onClose={() => setError(null)} dismissible>
              {error}
            </Alert>
          </Col>
        </Row>
      )}

      <Row className="mb-3">
        <Col md={6}>
          <Form.Group>
            <Form.Label>Filter by Status</Form.Label>
            <Form.Select
              value={filters.status}
              onChange={(e) => setFilters(prev => ({ ...prev, status: e.target.value }))}
            >
              <option value="">All Statuses</option>
              <option value="scheduled">Scheduled</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </Form.Select>
          </Form.Group>
        </Col>
        <Col md={6}>
          <Form.Group>
            <Form.Label>Filter by Job Type</Form.Label>
            <Form.Select
              value={filters.jobType}
              onChange={(e) => setFilters(prev => ({ ...prev, jobType: e.target.value }))}
            >
              <option value="">All Types</option>
              <option value="dummy_batch">Dummy Batch</option>
              <option value="typosquat_batch">Typosquat Batch</option>
              <option value="phishlabs_batch">PhishLabs Batch</option>
              <option value="ai_analysis_batch">AI Analysis Batch</option>
              <option value="workflow">Workflow</option>
            </Form.Select>
          </Form.Group>
        </Col>
      </Row>

      <Card>
        <Card.Body>
          {jobs.length === 0 ? (
            <div className="text-center py-4">
              <p className="text-muted">No scheduled jobs found</p>
              <Button variant="primary" onClick={() => navigate('/scheduled-jobs/create')}>
                Create Your First Job
              </Button>
            </div>
          ) : (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Programs</th>
                  <th>Schedule</th>
                  <th>Status</th>
                  <th>Next Run</th>
                  <th>Executions</th>
                  <th>Last Run</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.schedule_id}>
                    <td>
                      <Link to={`/scheduled-jobs/${job.schedule_id}`} className="text-decoration-none">
                        <strong>{job.name}</strong>
                      </Link>
                      {job.description && (
                        <div className="text-muted small">{job.description}</div>
                      )}
                    </td>
                    <td>{getJobTypeLabel(job.job_type)}</td>
                    <td>
                      {(job.program_names && job.program_names.length > 0
                        ? job.program_names
                        : job.program_name
                          ? [job.program_name]
                          : []
                      ).map((name) => (
                        <Badge key={name} bg="info" className="me-1 mb-1">
                          {name}
                        </Badge>
                      ))}
                      {!(
                        (job.program_names && job.program_names.length > 0) ||
                        job.program_name
                      ) && <span className="text-muted small">N/A</span>}
                    </td>
                    <td>
                      <small>{getScheduleDescription(job.schedule, job.last_run, job.status)}</small>
                    </td>
                    <td>
                      <div className="d-flex align-items-center gap-2">
                        {getStatusBadge(job.status)}
                        {job.schedule?.enabled ? (
                          <Badge bg="success" title="Schedule is active">✓ Enabled</Badge>
                        ) : (
                          <Badge bg="warning" text="dark" title="Schedule is paused">⏸ Disabled</Badge>
                        )}
                      </div>
                    </td>
                    <td>
                      {job.next_run ? (
                        <small>{formatDate(job.next_run)}</small>
                      ) : job.schedule?.schedule_type === 'once' && job.status === 'completed' ? (
                        <span className="text-muted small">One-time job completed</span>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td>
                      <div className="small">
                        {(() => {
                          const stats = getJobExecutionStats(job);
                          return (
                            <>
                              <div>Total: {stats.total}</div>
                              <div className="text-success">Success: {stats.successful}</div>
                              <div className="text-danger">Failed: {stats.failed}</div>
                            </>
                          );
                        })()}
                      </div>
                    </td>
                    <td>
                      {job.last_run ? (
                        <small>{formatRelativeTime(job.last_run)}</small>
                      ) : (
                        <span className="text-muted">Never</span>
                      )}
                    </td>
                    <td>
                      <Dropdown>
                        <Dropdown.Toggle variant="outline-secondary" size="sm">
                          Actions
                        </Dropdown.Toggle>
                          <Dropdown.Menu>
                            <Dropdown.Item as={Link} to={`/scheduled-jobs/${job.schedule_id}`}>
                              👁️ View Details
                            </Dropdown.Item>
                            {canManageJob(job) && (
                              <Dropdown.Item 
                                onClick={() => handleRunNow(job.schedule_id)}
                                disabled={actionLoading[job.schedule_id]}
                              >
                                ▶️ Run Now
                              </Dropdown.Item>
                            )}
                          {canManageJob(job) && (
                            <>
                              <Dropdown.Divider />
                              <Dropdown.Item
                                onClick={() => handleToggleStatus(job.schedule_id, !job.schedule?.enabled)}
                                disabled={actionLoading[job.schedule_id]}
                              >
                                {actionLoading[job.schedule_id] ? (
                                  <>🔄 {job.schedule?.enabled ? 'Disabling...' : 'Enabling...'}</>
                                ) : (
                                  job.schedule?.enabled ? '⏸️ Disable Schedule' : '▶️ Enable Schedule'
                                )}
                              </Dropdown.Item>
                            </>
                          )}
                          {canManageJob(job) && (
                            <>
                              <Dropdown.Divider />
                              <Dropdown.Item 
                                onClick={() => {
                                  setJobToDelete(job);
                                  setShowDeleteModal(true);
                                }}
                                className="text-danger"
                              >
                                🗑️ Delete
                              </Dropdown.Item>
                            </>
                          )}
                        </Dropdown.Menu>
                      </Dropdown>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Scheduled Job</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          Are you sure you want to delete the scheduled job "{jobToDelete?.name}"? 
          This action cannot be undone.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
            Cancel
          </Button>
          <Button 
            variant="danger" 
            onClick={handleDelete}
            disabled={actionLoading[jobToDelete?.schedule_id]}
          >
            Delete
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default ScheduledJobs; 