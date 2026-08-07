import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Table,
  Button,
  Alert,
  Spinner,
  Badge,
  Form,
  Modal,
  ProgressBar,
  Pagination,
  ButtonGroup,
  OverlayTrigger,
  Popover,
} from 'react-bootstrap';
import { jobAPI } from '../../services/api';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

const JOB_TYPE_OPTIONS = [
  { value: 'phishlabs_batch', label: 'PhishLabs batch' },
  { value: 'phishlabs_incidents_batch', label: 'PhishLabs incidents batch' },
  { value: 'ai_analysis_batch', label: 'AI analysis batch' },
  { value: 'gather_api_findings', label: 'Gather API findings' },
  { value: 'sync_recordedfuture_data', label: 'Sync RecordedFuture data' },
  { value: 'refresh_vendor_intel', label: 'Refresh vendor intel' },
  { value: 'dummy_batch', label: 'Dummy batch' },
  { value: 'typosquat_batch', label: 'Typosquat batch' },
];

const JOB_STATUS_OPTIONS = [
  'pending',
  'running',
  'stopping',
  'stopped',
  'completed',
  'failed',
  'cancelled',
];

function formatJobStatusLabel(status) {
  return status || 'unknown';
}

export function JobManagementInner({ embedded = false }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalJobs, setTotalJobs] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  const [jobIdFilter, setJobIdFilter] = useState('');
  const [jobTypeFilter, setJobTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [showPodOutput, setShowPodOutput] = useState(true);
  const [podOutputSearch, setPodOutputSearch] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [stoppingJobs, setStoppingJobs] = useState(new Set());
  const [showStopModal, setShowStopModal] = useState(false);
  const [jobToStop, setJobToStop] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [showBulkStopModal, setShowBulkStopModal] = useState(false);
  const selectAllCheckboxRef = useRef(null);

  const [autoRefresh, setAutoRefresh] = useState(false);


  const loadJobs = useCallback(
    async (showLoading = true) => {
      try {
        if (showLoading) setLoading(true);
        setError('');
        const response = await jobAPI.getAll(
          currentPage,
          pageSize,
          jobTypeFilter || null,
          statusFilter || null,
          jobIdFilter || null,
        );

        if (response.status === 'success') {
          setJobs(response.jobs);
          setTotalJobs(response.total);
          setTotalPages(response.total_pages);
        } else {
          setError('Failed to load jobs');
        }
      } catch (err) {
        setError('Failed to load jobs: ' + (err.response?.data?.detail || err.message));
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [currentPage, pageSize, jobTypeFilter, statusFilter, jobIdFilter],
  );

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const interval = setInterval(() => {
      loadJobs(false);
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadJobs]);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [currentPage, pageSize, jobIdFilter, jobTypeFilter, statusFilter]);

  const canStopJob = (status) => {
    const stoppableStatuses = ['running', 'pending'];
    return stoppableStatuses.includes(status?.toLowerCase());
  };

  const stoppableOnPage = useMemo(() => {
    return jobs.filter(
      (job) => canStopJob(job.status) && !stoppingJobs.has(job.job_id),
    );
  }, [jobs, stoppingJobs]);

  useEffect(() => {
    const el = selectAllCheckboxRef.current;
    if (!el) return;
    const ids = stoppableOnPage.map((job) => job.job_id);
    const selectedCount = ids.filter((id) => selectedIds.has(id)).length;
    el.indeterminate = selectedCount > 0 && selectedCount < ids.length;
  }, [stoppableOnPage, selectedIds]);

  const toggleRowSelection = (job) => {
    if (!canStopJob(job.status) || stoppingJobs.has(job.job_id)) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(job.job_id)) next.delete(job.job_id);
      else next.add(job.job_id);
      return next;
    });
  };

  const toggleSelectAllOnPage = () => {
    const ids = stoppableOnPage.map((job) => job.job_id);
    const allSelected = ids.length > 0 && ids.every((id) => selectedIds.has(id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const handleStopJob = (job) => {
    setJobToStop(job);
    setShowStopModal(true);
  };

  const handleOpenBulkStop = () => {
    if (selectedIds.size === 0) return;
    setShowBulkStopModal(true);
  };

  const confirmStopJob = async () => {
    if (!jobToStop) return;

    const jobId = jobToStop.job_id;
    setStoppingJobs((prev) => new Set(prev).add(jobId));
    setShowStopModal(false);

    try {
      setActionLoading(true);
      setError('');
      setSuccess('');

      const response = await jobAPI.stop(jobId);
      if (response.status === 'already_finished') {
        setSuccess(response.message || 'Job is already finished');
      } else {
        setSuccess(response.message || 'Job stop requested');
      }

      await loadJobs(false);

      setTimeout(() => {
        setStoppingJobs((prev) => {
          const next = new Set(prev);
          next.delete(jobId);
          return next;
        });
        loadJobs(false);
      }, 5000);
    } catch (err) {
      setError('Failed to stop job: ' + (err.response?.data?.detail || err.message));
      setStoppingJobs((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    } finally {
      setActionLoading(false);
      setJobToStop(null);
    }
  };

  const confirmBulkStopJobs = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;

    setStoppingJobs((prev) => new Set([...prev, ...ids]));
    setShowBulkStopModal(false);
    setActionLoading(true);
    setError('');
    setSuccess('');

    const results = await Promise.allSettled(ids.map((id) => jobAPI.stop(id)));
    const failures = [];
    results.forEach((result, i) => {
      const id = ids[i];
      if (result.status === 'rejected') {
        const msg = result.reason?.response?.data?.detail || result.reason?.message || String(result.reason);
        failures.push(`${id}: ${msg}`);
      }
    });

    if (failures.length > 0) {
      setError(`Failed to stop some jobs: ${failures.join('; ')}`);
    } else {
      setSuccess(`Stop requested for ${ids.length} job${ids.length === 1 ? '' : 's'}`);
    }

    await loadJobs(false);
    setSelectedIds(new Set());

    setTimeout(() => {
      setStoppingJobs((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.delete(id));
        return next;
      });
      loadJobs(false);
    }, 5000);

    setActionLoading(false);
  };

  const openDetailsModal = async (job) => {
    setShowDetailsModal(true);
    setSelectedJob(job);
    setShowPodOutput(true);
    setPodOutputSearch('');
    setDetailsLoading(true);
    setError('');

    try {
      const response = await jobAPI.getStatus(job.job_id);
      if (response.status === 'success' && response.job) {
        setSelectedJob(response.job);
      }
    } catch (err) {
      setError('Failed to load job details: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDetailsLoading(false);
    }
  };

  const downloadPodOutput = () => {
    if (!selectedJob?.runner_pod_output) return;
    const blob = new Blob([selectedJob.runner_pod_output], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `job-${selectedJob.job_id}-runner-output.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const highlightPodOutput = (text, searchTerm) => {
    if (!searchTerm || !text) return text;
    const escaped = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escaped})`, 'gi');
    const parts = text.split(regex);
    return parts.map((part, index) =>
      index % 2 === 1 ? <mark key={index}>{part}</mark> : part,
    );
  };

  const getStatusBadge = (status) => {
    const variants = {
      pending: 'warning',
      running: 'primary',
      stopping: 'warning',
      stopped: 'secondary',
      completed: 'success',
      failed: 'danger',
      cancelled: 'secondary',
    };
    return <Badge bg={variants[status] || 'secondary'}>{formatJobStatusLabel(status)}</Badge>;
  };

  const getJobTypeBadge = (jobType) => {
    const variants = {
      phishlabs_batch: 'info',
      phishlabs_incidents_batch: 'info',
      ai_analysis_batch: 'info',
      gather_api_findings: 'info',
      sync_recordedfuture_data: 'info',
      refresh_vendor_intel: 'info',
      dummy_batch: 'secondary',
      typosquat_batch: 'info',
    };
    return <Badge bg={variants[jobType] || 'secondary'}>{jobType}</Badge>;
  };

  const formatJobDate = (dateString) => formatDate(dateString, 'MMM dd, yyyy HH:mm:ss');

  const clearFilters = () => {
    setJobIdFilter('');
    setJobTypeFilter('');
    setStatusFilter('');
    setCurrentPage(1);
  };

  const handlePageChange = (page) => {
    setCurrentPage(page);
  };

  const pagerLabel = useMemo(() => {
    if (totalJobs === 0) return { from: 0, to: 0 };
    const from = (currentPage - 1) * pageSize + 1;
    const to = Math.min(currentPage * pageSize, totalJobs);
    return { from, to };
  }, [totalJobs, currentPage, pageSize]);

  const ColumnFilterPopover = ({ id, isActive, ariaLabel, placement = 'bottom', children }) => {
    const buttonVariant = isActive ? 'primary' : 'outline-secondary';
    const overlay = (
      <Popover id={id} style={{ minWidth: 280, maxWidth: 360 }} onClick={(e) => e.stopPropagation()}>
        <Popover.Body onClick={(e) => e.stopPropagation()}>{children}</Popover.Body>
      </Popover>
    );

    return (
      <OverlayTrigger trigger="click" rootClose placement={placement} overlay={overlay}>
        <Button
          size="sm"
          variant={buttonVariant}
          aria-label={ariaLabel}
          onClick={(e) => e.stopPropagation()}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="currentColor"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
            style={{ marginRight: 4 }}
          >
            <path d="M1.5 1.5a.5.5 0 0 0 0 1h13a.5.5 0 0 0 .4-.8L10 9.2V13a.5.5 0 0 1-.276.447l-2 1A.5.5 0 0 1 7 14V9.2L1.1 1.7a.5.5 0 0 0-.4-.2z" />
          </svg>
        </Button>
      </OverlayTrigger>
    );
  };

  const InlineTextFilter = ({ label, placeholder, initialValue, onApply, onClear }) => {
    const [localValue, setLocalValue] = useState(initialValue || '');
    useEffect(() => {
      setLocalValue(initialValue || '');
    }, [initialValue]);

    const applyNow = () => onApply(localValue);

    return (
      <div>
        <Form.Group>
          <Form.Label className="mb-1">{label}</Form.Label>
          <Form.Control
            type="text"
            placeholder={placeholder}
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applyNow();
            }}
          />
        </Form.Group>
        <div className="d-flex justify-content-end gap-2 mt-3">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setLocalValue('');
              onClear?.();
            }}
          >
            Clear
          </Button>
          <Button size="sm" variant="primary" onClick={applyNow}>
            Apply
          </Button>
        </div>
      </div>
    );
  };

  const Outer = embedded ? 'div' : Container;
  const outerProps = embedded ? {} : { fluid: true };

  return (
    <Outer {...outerProps} className={embedded ? '' : 'mt-4'}>
      <Row>
        <Col>
          <Card className={embedded ? '' : 'rh-elevated-card'}>
            <Card.Header className="d-flex flex-wrap justify-content-between align-items-center gap-2">
              <div className="d-flex align-items-center flex-wrap gap-2 flex-grow-1">
                <h5 className="mb-0">{embedded ? 'Job monitoring' : 'Job Management'}</h5>
                <Badge bg="secondary">Total: {totalJobs}</Badge>
                <Button
                  variant="link"
                  size="sm"
                  className="p-0"
                  onClick={clearFilters}
                  aria-label="Reset all filters"
                >
                  Reset filters
                </Button>
              </div>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                {selectedIds.size > 0 && (
                  <Button variant="outline-danger" size="sm" onClick={handleOpenBulkStop}>
                    ⏹️ Stop selected ({selectedIds.size})
                  </Button>
                )}
                <Button
                  variant={autoRefresh ? 'success' : 'outline-secondary'}
                  size="sm"
                  onClick={() => setAutoRefresh(!autoRefresh)}
                >
                  {autoRefresh ? '🔄 Auto-refresh ON' : '⏸️ OFF'}
                </Button>
                <Button variant="outline-primary" size="sm" onClick={() => loadJobs()} disabled={loading}>
                  🔄 Refresh
                </Button>
                {loading && <Spinner animation="border" size="sm" />}
              </div>
            </Card.Header>
            <Card.Body className="p-0">
              {error && (
                <Alert variant="danger" dismissible onClose={() => setError('')} className="m-3 mb-0">
                  {error}
                </Alert>
              )}
              {success && (
                <Alert variant="success" dismissible onClose={() => setSuccess('')} className="m-3 mb-0">
                  {success}
                </Alert>
              )}

              <Table responsive hover className="mb-0">
                <thead>
                  <tr>
                    <th style={{ width: '42px' }}>
                      <input
                        ref={selectAllCheckboxRef}
                        type="checkbox"
                        className="form-check-input"
                        checked={
                          stoppableOnPage.length > 0 &&
                          stoppableOnPage.every((job) => selectedIds.has(job.job_id))
                        }
                        onChange={toggleSelectAllOnPage}
                        disabled={stoppableOnPage.length === 0}
                        aria-label="Select all stoppable jobs on this page"
                      />
                    </th>
                    <th>
                      <div className="d-flex align-items-center gap-2">
                        <span>Job</span>
                        <ColumnFilterPopover
                          id="job-id-filter"
                          ariaLabel="Filter by job ID"
                          isActive={Boolean(jobIdFilter)}
                        >
                          <InlineTextFilter
                            label="Job ID contains"
                            placeholder="Substring…"
                            initialValue={jobIdFilter}
                            onApply={(val) => {
                              setJobIdFilter(val.trim());
                              setCurrentPage(1);
                            }}
                            onClear={() => {
                              setJobIdFilter('');
                              setCurrentPage(1);
                            }}
                          />
                        </ColumnFilterPopover>
                      </div>
                    </th>
                    <th>
                      <div className="d-flex align-items-center gap-2">
                        <span>Type</span>
                        <ColumnFilterPopover
                          id="job-type-filter"
                          ariaLabel="Filter by job type"
                          isActive={Boolean(jobTypeFilter)}
                        >
                          <Form.Group className="mb-2">
                            <Form.Label className="mb-1">Job type</Form.Label>
                            <Form.Select
                              size="sm"
                              value={jobTypeFilter}
                              onChange={(e) => {
                                setJobTypeFilter(e.target.value);
                                setCurrentPage(1);
                              }}
                            >
                              <option value="">All types</option>
                              {JOB_TYPE_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>
                                  {opt.label}
                                </option>
                              ))}
                            </Form.Select>
                          </Form.Group>
                          <div className="d-flex justify-content-end">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => {
                                setJobTypeFilter('');
                                setCurrentPage(1);
                              }}
                            >
                              Clear
                            </Button>
                          </div>
                        </ColumnFilterPopover>
                      </div>
                    </th>
                    <th>
                      <div className="d-flex align-items-center gap-2">
                        <span>Status</span>
                        <ColumnFilterPopover
                          id="job-status-filter"
                          ariaLabel="Filter by status"
                          isActive={Boolean(statusFilter)}
                        >
                          <Form.Group className="mb-2">
                            <Form.Label className="mb-1">Status</Form.Label>
                            <Form.Select
                              size="sm"
                              value={statusFilter}
                              onChange={(e) => {
                                setStatusFilter(e.target.value);
                                setCurrentPage(1);
                              }}
                            >
                              <option value="">All statuses</option>
                              {JOB_STATUS_OPTIONS.map((s) => (
                                <option key={s} value={s}>
                                  {formatJobStatusLabel(s)}
                                </option>
                              ))}
                            </Form.Select>
                          </Form.Group>
                          <div className="d-flex justify-content-end">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => {
                                setStatusFilter('');
                                setCurrentPage(1);
                              }}
                            >
                              Clear
                            </Button>
                          </div>
                        </ColumnFilterPopover>
                      </div>
                    </th>
                    <th>Progress</th>
                    <th>Message</th>
                    <th>Created</th>
                    <th>Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && jobs.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center py-5">
                        <Spinner animation="border" role="status">
                          <span className="visually-hidden">Loading...</span>
                        </Spinner>
                        <p className="mt-2 mb-0 text-muted small">Loading jobs...</p>
                      </td>
                    </tr>
                  ) : jobs.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center py-5">
                        <p className="text-muted mb-0">No jobs match the current filters.</p>
                      </td>
                    </tr>
                  ) : (
                    jobs.map((job) => {
                      const displayStatus = stoppingJobs.has(job.job_id) ? 'stopping' : job.status;
                      return (
                        <tr key={job.job_id}>
                          <td>
                            <Form.Check
                              type="checkbox"
                              checked={selectedIds.has(job.job_id)}
                              onChange={() => toggleRowSelection(job)}
                              disabled={
                                !canStopJob(job.status) || stoppingJobs.has(job.job_id)
                              }
                              aria-label={`Select job ${job.job_id}`}
                            />
                          </td>
                          <td>
                            <code className="small">{job.job_id}</code>
                          </td>
                          <td>{getJobTypeBadge(job.job_type)}</td>
                          <td>{getStatusBadge(displayStatus)}</td>
                          <td>
                            <ProgressBar
                              now={job.progress}
                              label={`${job.progress}%`}
                              variant={
                                job.status === 'failed'
                                  ? 'danger'
                                  : job.status === 'completed'
                                    ? 'success'
                                    : 'primary'
                              }
                              style={{ minWidth: '80px' }}
                            />
                          </td>
                          <td>
                            <span className="text-muted small" title={job.message}>
                              {job.message?.length > 50
                                ? `${job.message.substring(0, 50)}...`
                                : job.message}
                            </span>
                          </td>
                          <td>
                            <small>{formatJobDate(job.created_at)}</small>
                          </td>
                          <td>
                            <small>{formatJobDate(job.updated_at)}</small>
                          </td>
                          <td>
                            <ButtonGroup size="sm">
                              <Button variant="outline-primary" onClick={() => openDetailsModal(job)}>
                                📄 Details
                              </Button>
                              {canStopJob(job.status) && (
                                <Button
                                  variant="outline-danger"
                                  onClick={() => handleStopJob(job)}
                                  disabled={stoppingJobs.has(job.job_id) || actionLoading}
                                >
                                  {stoppingJobs.has(job.job_id) ? (
                                    <>
                                      <Spinner animation="border" size="sm" className="me-1" />
                                      Stopping...
                                    </>
                                  ) : (
                                    '⏹️ Stop'
                                  )}
                                </Button>
                              )}
                            </ButtonGroup>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </Table>

              <div className="text-center text-muted small p-3 pb-2 mb-0">
                Showing {pagerLabel.from} to {pagerLabel.to} of {totalJobs} jobs (Page {currentPage} of{' '}
                {Math.max(totalPages, 1)})
              </div>
              <div className="d-flex justify-content-center align-items-center gap-3 p-3 pt-0 flex-wrap">
                <Form.Select
                  size="sm"
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(parseInt(e.target.value, 10));
                    setCurrentPage(1);
                  }}
                  style={{ width: 'auto' }}
                  aria-label="Items per page"
                >
                  <option value={10}>10 per page</option>
                  <option value={25}>25 per page</option>
                  <option value={50}>50 per page</option>
                  <option value={100}>100 per page</option>
                </Form.Select>
                {totalPages > 1 && (
                  <Pagination className="mb-0">
                    <Pagination.First onClick={() => handlePageChange(1)} disabled={currentPage === 1} />
                    <Pagination.Prev
                      onClick={() => handlePageChange(currentPage - 1)}
                      disabled={currentPage === 1}
                    />
                    <Pagination.Item active>{currentPage}</Pagination.Item>
                    <Pagination.Next
                      onClick={() => handlePageChange(currentPage + 1)}
                      disabled={currentPage === totalPages}
                    />
                    <Pagination.Last
                      onClick={() => handlePageChange(totalPages)}
                      disabled={currentPage === totalPages}
                    />
                  </Pagination>
                )}
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Modal show={showDetailsModal} onHide={() => setShowDetailsModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Job Details</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {detailsLoading ? (
            <div className="text-center py-4">
              <Spinner animation="border" />
              <p className="mt-2 mb-0">Loading job details...</p>
            </div>
          ) : (
            selectedJob && (
              <div>
                <Row>
                  <Col md={6}>
                    <h6>Basic Information</h6>
                    <Table size="sm" borderless>
                      <tbody>
                        <tr>
                          <td><strong>Job ID:</strong></td>
                          <td><code>{selectedJob.job_id}</code></td>
                        </tr>
                        <tr>
                          <td><strong>Type:</strong></td>
                          <td>{getJobTypeBadge(selectedJob.job_type)}</td>
                        </tr>
                        <tr>
                          <td><strong>Status:</strong></td>
                          <td>{getStatusBadge(selectedJob.status)}</td>
                        </tr>
                        <tr>
                          <td><strong>Progress:</strong></td>
                          <td>{selectedJob.progress}%</td>
                        </tr>
                        <tr>
                          <td><strong>User ID:</strong></td>
                          <td><code>{selectedJob.user_id}</code></td>
                        </tr>
                      </tbody>
                    </Table>
                  </Col>
                  <Col md={6}>
                    <h6>Timestamps</h6>
                    <Table size="sm" borderless>
                      <tbody>
                        <tr>
                          <td><strong>Created:</strong></td>
                          <td>{formatJobDate(selectedJob.created_at)}</td>
                        </tr>
                        <tr>
                          <td><strong>Updated:</strong></td>
                          <td>{formatJobDate(selectedJob.updated_at)}</td>
                        </tr>
                      </tbody>
                    </Table>
                  </Col>
                </Row>

                <Row className="mt-3">
                  <Col>
                    <h6>Message</h6>
                    <p className="text-muted">{selectedJob.message}</p>
                  </Col>
                </Row>

                {selectedJob.results && (
                  <Row className="mt-3">
                    <Col>
                      <h6>Results</h6>
                      <pre className="bg-light p-3 rounded small">
                        {JSON.stringify(selectedJob.results, null, 2)}
                      </pre>
                    </Col>
                  </Row>
                )}

                {selectedJob.job_data && (
                  <Row className="mt-3">
                    <Col>
                      <h6>Job Data</h6>
                      <pre className="bg-light p-3 rounded small">
                        {JSON.stringify(selectedJob.job_data, null, 2)}
                      </pre>
                    </Col>
                  </Row>
                )}

                {selectedJob.runner_pod_output && (
                  <Row className="mt-3">
                    <Col>
                      <div className="d-flex justify-content-between align-items-center mb-2">
                        <h6 className="mb-0">Runner Pod Output</h6>
                        <div className="d-flex gap-2">
                          <Button
                            variant="outline-secondary"
                            size="sm"
                            onClick={() => setShowPodOutput((prev) => !prev)}
                          >
                            {showPodOutput ? 'Hide' : 'Show'}
                          </Button>
                          <Button variant="outline-primary" size="sm" onClick={downloadPodOutput}>
                            Download
                          </Button>
                        </div>
                      </div>
                      <div className="text-muted small mb-2">
                        {selectedJob.runner_pod_output.length} characters
                      </div>
                      {showPodOutput && (
                        <>
                          <Form.Control
                            type="search"
                            size="sm"
                            placeholder="Search output..."
                            value={podOutputSearch}
                            onChange={(e) => setPodOutputSearch(e.target.value)}
                            className="mb-2"
                          />
                          <pre
                            className="bg-light p-3 rounded small mb-0"
                            style={{ maxHeight: '600px', overflow: 'auto', whiteSpace: 'pre-wrap' }}
                          >
                            {highlightPodOutput(selectedJob.runner_pod_output, podOutputSearch)}
                          </pre>
                        </>
                      )}
                    </Col>
                  </Row>
                )}
              </div>
            )
          )}
        </Modal.Body>
        <Modal.Footer>
          {selectedJob && canStopJob(selectedJob.status) && (
            <Button
              variant="danger"
              onClick={() => handleStopJob(selectedJob)}
              disabled={actionLoading || stoppingJobs.has(selectedJob.job_id)}
            >
              {stoppingJobs.has(selectedJob.job_id) ? 'Stopping...' : '⏹️ Stop Job'}
            </Button>
          )}
          <Button variant="secondary" onClick={() => setShowDetailsModal(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={showStopModal} onHide={() => setShowStopModal(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Stop Job</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {jobToStop && (
            <div className="card rh-elevated-card border mb-3">
              <div className="card-body py-2">
                <strong>{jobToStop.job_type}</strong>
                <br />
                <small className="text-muted">ID: {jobToStop.job_id}</small>
                <br />
                {getStatusBadge(jobToStop.status)}
              </div>
            </div>
          )}
          <Alert variant="warning" className="mb-0">
            This will cancel the running Kubernetes job. Pod output captured so far will still be saved.
          </Alert>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowStopModal(false)} disabled={actionLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirmStopJob} disabled={actionLoading}>
            {actionLoading ? 'Stopping...' : '⏹️ Stop Job'}
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={showBulkStopModal} onHide={() => setShowBulkStopModal(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Stop jobs</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>
            Are you sure you want to stop <strong>{selectedIds.size}</strong> job
            {selectedIds.size === 1 ? '' : 's'}?
          </p>
          <div className="d-flex flex-column gap-2" style={{ maxHeight: '240px', overflowY: 'auto' }}>
            {[...selectedIds].map((id) => {
              const job = jobs.find((j) => j.job_id === id);
              return (
                <div key={id} className="card rh-elevated-card border">
                  <div className="card-body py-2">
                    <strong>{job?.job_type ?? 'Unknown'}</strong>
                    <br />
                    <small className="text-muted">ID: {id}</small>
                    {job && (
                      <>
                        <br />
                        {getStatusBadge(job.status)}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <Alert variant="warning" className="mb-0 mt-3">
            This will cancel the selected Kubernetes jobs. Pod output captured so far will still be saved.
          </Alert>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowBulkStopModal(false)} disabled={actionLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirmBulkStopJobs} disabled={actionLoading}>
            ⏹️ Stop {selectedIds.size} job{selectedIds.size === 1 ? '' : 's'}
          </Button>
        </Modal.Footer>
      </Modal>
    </Outer>
  );
}

function JobManagement() {
  usePageTitle(formatPageTitle('Job Management'));
  return <JobManagementInner embedded={false} />;
}

export default JobManagement;
