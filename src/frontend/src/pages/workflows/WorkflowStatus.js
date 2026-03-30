import React, { useState, useEffect, useCallback } from 'react';
import { Container, Row, Col, Card, Table, Badge, Button, Spinner, Alert, Pagination, ButtonGroup, Modal } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { workflowAPI } from '../../services/api';
import { formatDate, calculateDuration } from '../../utils/dateUtils';

// Add some custom styles for sortable headers
const sortableHeaderStyle = {
  cursor: 'pointer',
  userSelect: 'none'
};

function WorkflowStatus() {
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [stoppingWorkflows, setStoppingWorkflows] = useState(new Set());
  const [showStopModal, setShowStopModal] = useState(false);
  const [workflowToStop, setWorkflowToStop] = useState(null);
  const [sortField, setSortField] = useState('started_at');
  const [sortOrder, setSortOrder] = useState('desc');

  const loadExecutions = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      const response = await workflowAPI.getWorkflowStatus(currentPage, 25, null, sortField, sortOrder);
      
      
      setExecutions(response.executions || []);
      setTotalPages(response.total_pages || 1);
      setError(null);
    } catch (err) {
      setError('Failed to load workflow executions: ' + err.message);
      setExecutions([]);
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [currentPage, sortField, sortOrder]);

  useEffect(() => {
    loadExecutions();
  }, [loadExecutions]);

  useEffect(() => {
    let interval;
    if (autoRefresh) {
      interval = setInterval(() => {
        loadExecutions(false); // Don't show loading spinner for auto-refresh
      }, 30000); // Refresh every 30 seconds
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, loadExecutions]);

  const handleStopWorkflow = (execution) => {
    setWorkflowToStop(execution);
    setShowStopModal(true);
  };

  const confirmStopWorkflow = async () => {
    if (!workflowToStop) return;

    const workflowId = workflowToStop.id;
    setStoppingWorkflows(prev => new Set([...prev, workflowId]));
    setShowStopModal(false);

    try {
      const response = await workflowAPI.stopWorkflow(workflowId);
      
      if (response.status === 'success') {
        // Show success message and refresh data
        setError(null);
        await loadExecutions(false);
      } else if (response.status === 'stopping') {
        // Workflow is being stopped in the background
        setError(null);
        // Workflow is being stopped in the background
        setError(null);
        // Refresh data to show the "stopping" status
        await loadExecutions(false);
        // Keep the workflow in stopping state for a while to show progress
        setTimeout(() => {
          setStoppingWorkflows(prev => {
            const newSet = new Set(prev);
            newSet.delete(workflowId);
            return newSet;
          });
        }, 5000); // Keep showing stopping state for 5 seconds
        return; // Don't clear stopping state immediately
      } else if (response.status === 'already_finished') {
        // Workflow already finished, just refresh
        await loadExecutions(false);
      }
    } catch (err) {
      setError(`Failed to stop workflow: ${err.message}`);
    } finally {
      setStoppingWorkflows(prev => {
        const newSet = new Set(prev);
        newSet.delete(workflowId);
        return newSet;
      });
      setWorkflowToStop(null);
    }
  };

  const canStopWorkflow = (status) => {
    const stoppableStatuses = ['running', 'started', 'pending'];
    return stoppableStatuses.includes(status?.toLowerCase());
  };

  const getStatusBadge = (status) => {
    const statusMap = {
      'running': 'primary',
      'started': 'primary',
      'completed': 'success',
      'success': 'success',
      'failed': 'danger',
      'pending': 'warning',
      'cancelled': 'secondary',
      'stopped': 'secondary',
      'stopping': 'warning',
      'unknown': 'secondary'
    };
    return statusMap[status?.toLowerCase()] || 'secondary';
  };

  const formatDateWithStatus = (dateString, status) => {
    if (!dateString) return 'Not started';
    
    // Check if workflow hasn't actually started
    if (status === 'pending' || status === 'queued') {
      return 'Pending';
    }
    
    return formatDate(dateString);
  };

  const formatDurationWithStatus = (startTime, endTime, status) => {
    // Status values that indicate workflow hasn't started executing yet
    const notStartedStatuses = ['pending', 'queued', 'created', 'scheduled'];
    
    // Check if workflow hasn't actually started yet
    if (!startTime || notStartedStatuses.includes(status?.toLowerCase())) {
      return 'Not started';
    }
    
    const duration = calculateDuration(startTime, endTime);
    if (duration === 'Not started') return duration;
    
    // Handle negative durations (clock skew, timezone issues)
    if (duration === 'Invalid duration') {
      // For running workflows, show as just started to handle minor clock differences
      if (['running', 'started'].includes(status?.toLowerCase())) {
        return 'Just started';
      }
      return 'Not started';
    }
    
    return duration;
  };

  const handlePageChange = (page) => {
    setCurrentPage(page);
  };

  const handleSort = (field) => {
    if (sortField === field) {
      // Toggle sort order if clicking the same field
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      // Set new field and default to desc order
      setSortField(field);
      setSortOrder('desc');
    }
    setCurrentPage(1); // Reset to first page when sorting
  };

  const getSortIcon = (field) => {
    if (sortField !== field) {
      return <span className="text-muted">↕</span>;
    }
    return sortOrder === 'asc' ? <span>↑</span> : <span>↓</span>;
  };

  if (loading && executions.length === 0) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading workflow executions...</p>
        </div>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <div>
              <h1>📊 Workflow Status</h1>
              <p className="text-muted">Monitor workflow execution status and progress</p>
            </div>
            <div>
              <Button
                variant={autoRefresh ? 'success' : 'outline-secondary'}
                onClick={() => setAutoRefresh(!autoRefresh)}
                className="me-2"
              >
                {autoRefresh ? '🔄 Auto-refresh ON' : '⏸️ Auto-refresh OFF'}
              </Button>
              <Button variant="outline-primary" onClick={() => loadExecutions()}>
                🔄 Refresh
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <div>
                <h5 className="mb-0">Recent Workflow Executions</h5>
                <small className="text-muted">
                  Sorted by: {sortField.replace('_', ' ')} ({sortOrder === 'asc' ? 'ascending' : 'descending'})
                </small>
              </div>
              {loading && (
                <Spinner animation="border" size="sm" />
              )}
            </Card.Header>
            <Card.Body className="p-0">
              {executions.length === 0 ? (
                <div className="text-center p-4">
                  <p className="text-muted mb-3">No workflow executions found.</p>
                  <Button as={Link} to="/workflows/run" variant="outline-primary">
                    Run a workflow
                  </Button>
                </div>
              ) : (
                <>
                  <Table responsive hover className="mb-0">
                    <thead>
                      <tr>
                        <th 
                          style={sortableHeaderStyle}
                          onClick={() => handleSort('workflow_name')}
                        >
                          Workflow {getSortIcon('workflow_name')}
                        </th>
                        <th 
                          style={sortableHeaderStyle}
                          onClick={() => handleSort('program_name')}
                        >
                          Program {getSortIcon('program_name')}
                        </th>
                        <th 
                          style={sortableHeaderStyle}
                          onClick={() => handleSort('status')}
                        >
                          Status {getSortIcon('status')}
                        </th>
                        <th 
                          style={sortableHeaderStyle}
                          onClick={() => handleSort('started_at')}
                        >
                          Started {getSortIcon('started_at')}
                        </th>
                        <th>Duration</th>
                        <th 
                          style={sortableHeaderStyle}
                          onClick={() => handleSort('progress')}
                        >
                          Progress {getSortIcon('progress')}
                        </th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {executions.map((execution) => (
                        <tr key={execution.id}>
                          <td>
                            <strong>{execution.workflow_name}</strong>
                            <br />
                            <small className="text-muted">
                              ID: {execution.id}
                            </small>
                          </td>
                          <td>
                            <Badge bg="primary">{execution.program_name}</Badge>
                          </td>
                          <td>
                            <Badge bg={getStatusBadge(execution.status)}>
                              {execution.status || 'unknown'}
                            </Badge>
                          </td>
                          <td>
                            <small>{formatDateWithStatus(execution.started_at, execution.status)}</small>
                          </td>
                          <td>
                            <small>{formatDurationWithStatus(execution.started_at, execution.completed_at, execution.status)}</small>
                          </td>
                          <td>
                            {execution.progress && (
                              <div>
                                <div className="progress" style={{ height: '10px' }}>
                                  <div
                                    className="progress-bar"
                                    role="progressbar"
                                    style={{ width: `${execution.progress.percentage || 0}%` }}
                                  ></div>
                                </div>
                                <small className="text-muted">
                                  {execution.progress.completed || 0}/{execution.progress.total || 0} tasks
                                </small>
                              </div>
                            )}
                          </td>
                          <td>
                            <ButtonGroup size="sm">
                              <Button
                                as={Link}
                                to={`/workflows/status/${execution.id}`}
                                variant="outline-primary"
                              >
                                📄 Details
                              </Button>
                              {canStopWorkflow(execution.status) && (
                                <Button
                                  variant="outline-danger"
                                  onClick={() => handleStopWorkflow(execution)}
                                  disabled={stoppingWorkflows.has(execution.id)}
                                >
                                  {stoppingWorkflows.has(execution.id) ? (
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
                      ))}
                    </tbody>
                  </Table>

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="d-flex justify-content-center p-3">
                      <Pagination>
                        <Pagination.First
                          onClick={() => handlePageChange(1)}
                          disabled={currentPage === 1}
                        />
                        <Pagination.Prev
                          onClick={() => handlePageChange(currentPage - 1)}
                          disabled={currentPage === 1}
                        />
                        
                        {[...Array(Math.min(5, totalPages))].map((_, idx) => {
                          const page = currentPage <= 3 ? idx + 1 : currentPage - 2 + idx;
                          if (page > totalPages) return null;
                          
                          return (
                            <Pagination.Item
                              key={page}
                              active={page === currentPage}
                              onClick={() => handlePageChange(page)}
                            >
                              {page}
                            </Pagination.Item>
                          );
                        })}
                        
                        <Pagination.Next
                          onClick={() => handlePageChange(currentPage + 1)}
                          disabled={currentPage === totalPages}
                        />
                        <Pagination.Last
                          onClick={() => handlePageChange(totalPages)}
                          disabled={currentPage === totalPages}
                        />
                      </Pagination>
                    </div>
                  )}
                </>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Stop Workflow Confirmation Modal */}
      <Modal show={showStopModal} onHide={() => setShowStopModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Stop Workflow</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to stop this workflow?</p>
                     {workflowToStop && (
             <div className="card border">
               <div className="card-body">
                 <strong>Workflow:</strong> {workflowToStop.workflow_name}<br />
                 <strong>Program:</strong> {workflowToStop.program_name}<br />
                 <strong>Status:</strong> <Badge bg={getStatusBadge(workflowToStop.status)}>{workflowToStop.status}</Badge><br />
                 <small className="text-muted">ID: {workflowToStop.id}</small>
               </div>
             </div>
           )}
          <div className="mt-3">
            <Alert variant="warning" className="mb-0">
              <strong>⚠️ Warning:</strong> This will immediately stop all running tasks and cancel pending jobs. This action cannot be undone.
            </Alert>
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowStopModal(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirmStopWorkflow}>
            ⏹️ Stop Workflow
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default WorkflowStatus;