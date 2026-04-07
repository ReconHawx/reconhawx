import React, { useState, useEffect, useCallback } from 'react';
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
  Pagination
} from 'react-bootstrap';
import { jobAPI } from '../../services/api';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

export function JobManagementInner({ embedded = false }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalJobs, setTotalJobs] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [limit] = useState(25);
  
  // Filters
  const [jobTypeFilter, setJobTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  
  // Modal states
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  
  // Auto-refresh
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const response = await jobAPI.getAll(currentPage, limit, jobTypeFilter || null, statusFilter || null);

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
      setLoading(false);
    }
  }, [currentPage, limit, jobTypeFilter, statusFilter]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!autoRefresh) {
      return undefined;
    }
    const interval = setInterval(() => {
      loadJobs();
    }, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadJobs]);

  const handleDeleteJob = async (job) => {
    if (!window.confirm(`Are you sure you want to delete job "${job.job_id}"? This action cannot be undone.`)) {
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      
      await jobAPI.delete(job.job_id);
      setSuccess('Job deleted successfully');
      loadJobs();
    } catch (err) {
      setError('Failed to delete job: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const openDetailsModal = (job) => {
    setSelectedJob(job);
    setShowDetailsModal(true);
  };

  const getStatusBadge = (status) => {
    const variants = {
      'pending': 'secondary',
      'running': 'primary',
      'completed': 'success',
      'failed': 'danger',
      'cancelled': 'warning'
    };
    
    return <Badge bg={variants[status] || 'secondary'}>{status}</Badge>;
  };

  const getJobTypeBadge = (jobType) => {
    const variants = {
      'phishlabs_batch': 'info',
      'ai_analysis_batch': 'info',
      'workflow': 'primary',
      'scan': 'warning',
      'export': 'success'
    };
    
    return <Badge bg={variants[jobType] || 'secondary'}>{jobType}</Badge>;
  };

  const formatJobDate = (dateString) => {
    return formatDate(dateString, 'MMM dd, yyyy HH:mm:ss');
  };

  const clearFilters = () => {
    setJobTypeFilter('');
    setStatusFilter('');
    setCurrentPage(1);
  };

  const renderPagination = () => {
    if (totalPages <= 1) return null;

    const items = [];
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);

    // Previous button
    items.push(
      <Pagination.Prev
        key="prev"
        disabled={currentPage === 1}
        onClick={() => setCurrentPage(currentPage - 1)}
      />
    );

    // First page
    if (startPage > 1) {
      items.push(
        <Pagination.Item key={1} onClick={() => setCurrentPage(1)}>
          1
        </Pagination.Item>
      );
      if (startPage > 2) {
        items.push(<Pagination.Ellipsis key="ellipsis1" />);
      }
    }

    // Page numbers
    for (let page = startPage; page <= endPage; page++) {
      items.push(
        <Pagination.Item
          key={page}
          active={page === currentPage}
          onClick={() => setCurrentPage(page)}
        >
          {page}
        </Pagination.Item>
      );
    }

    // Last page
    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        items.push(<Pagination.Ellipsis key="ellipsis2" />);
      }
      items.push(
        <Pagination.Item key={totalPages} onClick={() => setCurrentPage(totalPages)}>
          {totalPages}
        </Pagination.Item>
      );
    }

    // Next button
    items.push(
      <Pagination.Next
        key="next"
        disabled={currentPage === totalPages}
        onClick={() => setCurrentPage(currentPage + 1)}
      />
    );

    return <Pagination className="justify-content-center">{items}</Pagination>;
  };

  const Outer = embedded ? 'div' : Container;
  const outerProps = embedded ? {} : { fluid: true };

  return (
    <Outer {...outerProps} className={embedded ? '' : 'mt-4'}>
      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h4 className="mb-0">{embedded ? 'Job monitoring' : 'Job Management'}</h4>
              <div className="d-flex align-items-center gap-3">
                <Form.Check
                  type="switch"
                  id="auto-refresh"
                  label="Auto-refresh"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                <Button 
                  variant="outline-secondary" 
                  size="sm"
                  onClick={loadJobs}
                  disabled={loading}
                >
                  {loading ? <Spinner animation="border" size="sm" /> : 'Refresh'}
                </Button>
              </div>
            </Card.Header>
            <Card.Body>
              {/* Alerts */}
              {error && <Alert variant="danger" dismissible onClose={() => setError('')}>{error}</Alert>}
              {success && <Alert variant="success" dismissible onClose={() => setSuccess('')}>{success}</Alert>}

              {/* Filters */}
              <Row className="mb-3">
                <Col md={4}>
                  <Form.Group>
                    <Form.Label>Job Type</Form.Label>
                    <Form.Select
                      value={jobTypeFilter}
                      onChange={(e) => setJobTypeFilter(e.target.value)}
                    >
                      <option value="">All Types</option>
                      <option value="phishlabs_batch">PhishLabs Batch</option>
                      <option value="ai_analysis_batch">AI Analysis Batch</option>
                      <option value="workflow">Workflow</option>
                      <option value="scan">Scan</option>
                      <option value="export">Export</option>
                    </Form.Select>
                  </Form.Group>
                </Col>
                <Col md={4}>
                  <Form.Group>
                    <Form.Label>Status</Form.Label>
                    <Form.Select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                    >
                      <option value="">All Statuses</option>
                      <option value="pending">Pending</option>
                      <option value="running">Running</option>
                      <option value="completed">Completed</option>
                      <option value="failed">Failed</option>
                      <option value="cancelled">Cancelled</option>
                    </Form.Select>
                  </Form.Group>
                </Col>
                <Col md={4} className="d-flex align-items-end">
                  <Button variant="outline-secondary" onClick={clearFilters}>
                    Clear Filters
                  </Button>
                </Col>
              </Row>

              {/* Jobs Table */}
              {loading ? (
                <div className="text-center py-4">
                  <Spinner animation="border" />
                  <p className="mt-2">Loading jobs...</p>
                </div>
              ) : (
                <>
                  <Table responsive striped hover>
                    <thead>
                      <tr>
                        <th>Job ID</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Progress</th>
                        <th>Message</th>
                        <th>Created</th>
                        <th>Updated</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.length === 0 ? (
                        <tr>
                          <td colSpan="8" className="text-center py-4">
                            No jobs found
                          </td>
                        </tr>
                      ) : (
                        jobs.map((job) => (
                          <tr key={job.job_id}>
                            <td>
                              <code className="small">{job.job_id.substring(0, 8)}...</code>
                            </td>
                            <td>{getJobTypeBadge(job.job_type)}</td>
                            <td>{getStatusBadge(job.status)}</td>
                            <td>
                              <ProgressBar 
                                now={job.progress} 
                                label={`${job.progress}%`}
                                variant={
                                  job.status === 'failed' ? 'danger' :
                                  job.status === 'completed' ? 'success' :
                                  'primary'
                                }
                              />
                            </td>
                            <td>
                              <span className="text-muted small" title={job.message}>
                                {job.message.length > 50 ? job.message.substring(0, 50) + '...' : job.message}
                              </span>
                            </td>
                                                  <td>{formatJobDate(job.created_at)}</td>
                      <td>{formatJobDate(job.updated_at)}</td>
                            <td>
                              <div className="d-flex gap-1">
                                <Button
                                  variant="outline-info"
                                  size="sm"
                                  onClick={() => openDetailsModal(job)}
                                >
                                  Details
                                </Button>
                                <Button
                                  variant="outline-danger"
                                  size="sm"
                                  onClick={() => handleDeleteJob(job)}
                                  disabled={actionLoading}
                                >
                                  Delete
                                </Button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </Table>

                  {/* Pagination */}
                  {renderPagination()}

                  {/* Summary */}
                  <div className="text-muted small mt-3">
                    Showing {((currentPage - 1) * limit) + 1} to {Math.min(currentPage * limit, totalJobs)} of {totalJobs} jobs
                  </div>
                </>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Job Details Modal */}
      <Modal show={showDetailsModal} onHide={() => setShowDetailsModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Job Details</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selectedJob && (
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
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDetailsModal(false)}>
            Close
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