import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Container, Row, Col, Card, Table, Badge, Button, Spinner, Alert, Pagination, ButtonGroup, Modal, Tabs, Tab, Form, OverlayTrigger, Popover } from 'react-bootstrap';
import { Link, useSearchParams } from 'react-router-dom';
import { workflowAPI } from '../../services/api';
import { formatDate, calculateDuration } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';
import { useAuth } from '../../contexts/AuthContext';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { JobManagementInner } from '../admin/JobManagement';

const TAB_WORKFLOWS = 'workflows';
const TAB_JOBS = 'jobs';

// Add some custom styles for sortable headers
const sortableHeaderStyle = {
  cursor: 'pointer',
  userSelect: 'none'
};

/** Human-readable workflow result for list / modals (runner API `result` → `status`). */
export function formatWorkflowStatusLabel(status) {
  const k = (status || '').toLowerCase();
  const labels = {
    cancelled_waf: 'WAF cancelled',
    partial_waf: 'WAF partial',
  };
  return labels[k] || status || 'unknown';
}

export function WorkflowMonitoringPanel({ embedded = false }) {
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
  const [pageSize, setPageSize] = useState(25);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [showBulkStopModal, setShowBulkStopModal] = useState(false);
  const selectAllCheckboxRef = useRef(null);

  const { selectedProgram } = useProgramFilter();
  const [totalItems, setTotalItems] = useState(0);
  const [workflowNameFilter, setWorkflowNameFilter] = useState('');
  const [executionIdFilter, setExecutionIdFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const programScopeForList = useMemo(() => {
    if (!selectedProgram || !String(selectedProgram).trim()) return null;
    return String(selectedProgram).trim();
  }, [selectedProgram]);

  /** Populated via POST `/workflows/executions/distinct/status` (DB-backed). */
  const [distinctStatuses, setDistinctStatuses] = useState([]);
  const [distinctStatusesLoading, setDistinctStatusesLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setDistinctStatusesLoading(true);
        const body = {};
        if (programScopeForList) body.program = programScopeForList;
        const raw = await workflowAPI.getDistinctWorkflowExecutionStatuses(body);
        if (!cancelled) setDistinctStatuses(Array.isArray(raw) ? raw : []);
      } catch (e) {
        console.error('Failed to load workflow status filter values:', e);
        if (!cancelled) setDistinctStatuses([]);
      } finally {
        if (!cancelled) setDistinctStatusesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [programScopeForList]);

  /** Clear filter once options are loaded if value is not returned for this scope. */
  useEffect(() => {
    if (distinctStatusesLoading || !statusFilter) return;
    if (!distinctStatuses.includes(statusFilter)) {
      setStatusFilter('');
      setCurrentPage(1);
    }
  }, [distinctStatusesLoading, distinctStatuses, statusFilter]);

  const filters = useMemo(
    () => ({
      workflowName: workflowNameFilter,
      executionId: executionIdFilter,
      status: statusFilter,
    }),
    [workflowNameFilter, executionIdFilter, statusFilter],
  );

  const loadExecutions = useCallback(
    async (showLoading = true) => {
      try {
        if (showLoading) setLoading(true);
        const response = await workflowAPI.getWorkflowStatus(
          currentPage,
          pageSize,
          programScopeForList,
          sortField,
          sortOrder,
          filters,
        );

        setExecutions(response.executions || []);
        setTotalPages(response.total_pages || 1);
        setTotalItems(response.total_items ?? 0);
        setError(null);
      } catch (err) {
        setError(
          `Failed to load workflow executions: ${
            err.response?.data?.detail || err.message
          }`,
        );
        setExecutions([]);
        setTotalItems(0);
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [
      currentPage,
      pageSize,
      sortField,
      sortOrder,
      programScopeForList,
      filters,
    ],
  );

  useEffect(() => {
    setSelectedIds(new Set());
  }, [
    currentPage,
    sortField,
    sortOrder,
    pageSize,
    workflowNameFilter,
    executionIdFilter,
    statusFilter,
    selectedProgram,
  ]);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedProgram]);

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

  const stoppableOnPage = useMemo(() => {
    const stoppableStatuses = ['running', 'started', 'pending'];
    return executions.filter(
      (e) =>
        stoppableStatuses.includes(e.status?.toLowerCase()) &&
        !stoppingWorkflows.has(e.id)
    );
  }, [executions, stoppingWorkflows]);

  useEffect(() => {
    const el = selectAllCheckboxRef.current;
    if (!el) return;
    const ids = stoppableOnPage.map((e) => e.id);
    const selectedCount = ids.filter((id) => selectedIds.has(id)).length;
    el.indeterminate = selectedCount > 0 && selectedCount < ids.length;
  }, [stoppableOnPage, selectedIds]);

  const toggleRowSelection = (execution) => {
    if (!canStopWorkflow(execution.status) || stoppingWorkflows.has(execution.id)) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(execution.id)) next.delete(execution.id);
      else next.add(execution.id);
      return next;
    });
  };

  const toggleSelectAllOnPage = () => {
    const ids = stoppableOnPage.map((e) => e.id);
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

  const handleOpenBulkStop = () => {
    if (selectedIds.size === 0) return;
    setShowBulkStopModal(true);
  };

  const confirmBulkStopWorkflows = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;

    setStoppingWorkflows((prev) => new Set([...prev, ...ids]));
    setShowBulkStopModal(false);

    const results = await Promise.allSettled(ids.map((id) => workflowAPI.stopWorkflow(id)));
    const failures = [];
    results.forEach((result, i) => {
      const id = ids[i];
      if (result.status === 'rejected') {
        const msg = result.reason?.message || String(result.reason);
        failures.push(`${id}: ${msg}`);
      }
    });

    if (failures.length > 0) {
      setError(`Failed to stop some workflows: ${failures.join('; ')}`);
    } else {
      setError(null);
    }

    await loadExecutions(false);
    setSelectedIds(new Set());

    setTimeout(() => {
      setStoppingWorkflows((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.delete(id));
        return next;
      });
    }, 5000);
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
      'cancelled_waf': 'warning',
      'partial_waf': 'warning',
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
    const newOrder =
      sortField === field && sortOrder === 'asc' ? 'desc' : 'asc';
    setSortField(field);
    setSortOrder(newOrder);
    setCurrentPage(1);
  };

  const getSortIcon = (field) => {
    if (sortField !== field) {
      return <span className="text-muted">↕</span>;
    }
    return sortOrder === 'asc' ? <span>↑</span> : <span>↓</span>;
  };

  const clearFilters = () => {
    setWorkflowNameFilter('');
    setExecutionIdFilter('');
    setStatusFilter('');
    setCurrentPage(1);
  };

  const ColumnFilterPopover = ({
    id,
    isActive,
    ariaLabel,
    placement = 'bottom',
    children,
  }) => {
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

  const InlineTextFilter = ({
    label,
    placeholder,
    initialValue,
    onApply,
    onClear,
  }) => {
    const [localValue, setLocalValue] = useState(initialValue || '');
    useEffect(() => {
      setLocalValue(initialValue || '');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialValue]);

    const applyNow = () => {
      onApply(localValue);
    };

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

  const pagerLabel = useMemo(() => {
    if (totalItems === 0) {
      return { from: 0, to: 0 };
    }
    const from = (currentPage - 1) * pageSize + 1;
    const to = Math.min(currentPage * pageSize, totalItems);
    return { from, to };
  }, [totalItems, currentPage, pageSize]);

  const Outer = embedded ? 'div' : Container;
  const outerProps = embedded ? {} : { fluid: true };
  const outerClassName = embedded ? '' : 'p-4';

  return (
    <Outer {...outerProps} className={outerClassName}>
      <Row className="mb-4">
        <Col>
          <div>
            {!embedded && <h1>📊 Workflow Status</h1>}
            <p className={`text-muted ${embedded ? 'mb-0' : ''}`}>
              Monitor workflow execution status and progress. Use the global program filter in the header to
              narrow by program.
            </p>
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
            <Card.Header className="d-flex flex-wrap justify-content-between align-items-center gap-2">
              <div className="d-flex align-items-center flex-wrap gap-2 flex-grow-1">
                <h5 className="mb-0">Recent Workflow Executions</h5>
                <Badge bg="secondary">Total: {totalItems}</Badge>
                <Button
                  variant="link"
                  size="sm"
                  className="p-0"
                  onClick={clearFilters}
                  aria-label="Reset all filters"
                >
                  Reset filters
                </Button>
                <span className="text-muted small d-none d-xl-inline">
                  Sorted by {sortField.replace(/_/g, ' ')} ({sortOrder === 'asc' ? 'asc' : 'desc'})
                </span>
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
                  className="me-1"
                >
                  {autoRefresh ? '🔄 Auto-refresh ON' : '⏸️ OFF'}
                </Button>
                <Button variant="outline-primary" size="sm" onClick={() => loadExecutions()}>
                  🔄 Refresh
                </Button>
                {loading && <Spinner animation="border" size="sm" />}
              </div>
            </Card.Header>
            <Card.Body className="p-0">
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
                              stoppableOnPage.every((e) => selectedIds.has(e.id))
                            }
                            onChange={toggleSelectAllOnPage}
                            disabled={stoppableOnPage.length === 0}
                            aria-label="Select all stoppable workflows on this page"
                          />
                        </th>
                        <th style={sortableHeaderStyle} onClick={() => handleSort('workflow_name')}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Workflow {getSortIcon('workflow_name')}</span>
                            <ColumnFilterPopover
                              id="workflow-exec-filter"
                              ariaLabel="Filter by workflow name or execution ID"
                              isActive={Boolean(workflowNameFilter || executionIdFilter)}
                            >
                              <div>
                                <InlineTextFilter
                                  label="Workflow name contains"
                                  placeholder="Substring…"
                                  initialValue={workflowNameFilter}
                                  onApply={(val) => {
                                    setWorkflowNameFilter(val);
                                    setCurrentPage(1);
                                  }}
                                  onClear={() => setWorkflowNameFilter('')}
                                />
                                <div className="mt-3">
                                  <InlineTextFilter
                                    label="Execution ID contains"
                                    placeholder="Substring…"
                                    initialValue={executionIdFilter}
                                    onApply={(val) => {
                                      setExecutionIdFilter(val);
                                      setCurrentPage(1);
                                    }}
                                    onClear={() => setExecutionIdFilter('')}
                                  />
                                </div>
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th style={sortableHeaderStyle} onClick={() => handleSort('program_name')}>
                          Program {getSortIcon('program_name')}
                        </th>
                        <th style={sortableHeaderStyle} onClick={() => handleSort('status')}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Status {getSortIcon('status')}</span>
                            <ColumnFilterPopover
                              id="workflow-status-filter"
                              ariaLabel="Filter by status"
                              isActive={Boolean(statusFilter)}
                            >
                              <div>
                                <Form.Group className="mb-2">
                                  <Form.Label className="mb-1">Status</Form.Label>
                                  <Form.Select
                                    size="sm"
                                    disabled={distinctStatusesLoading}
                                    value={statusFilter}
                                    onChange={(e) => {
                                      setStatusFilter(e.target.value);
                                      setCurrentPage(1);
                                    }}
                                  >
                                    <option value="">
                                      {distinctStatusesLoading ? 'Loading statuses…' : 'All statuses'}
                                    </option>
                                    {distinctStatuses.map((s) => (
                                      <option key={s} value={s}>
                                        {formatWorkflowStatusLabel(s)}
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
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th style={sortableHeaderStyle} onClick={() => handleSort('started_at')}>
                          Started {getSortIcon('started_at')}
                        </th>
                        <th>Duration</th>
                        <th>Progress</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {loading && executions.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="text-center py-5">
                            <Spinner animation="border" role="status">
                              <span className="visually-hidden">Loading...</span>
                            </Spinner>
                            <p className="mt-2 mb-0 text-muted small">Loading workflow executions...</p>
                          </td>
                        </tr>
                      ) : executions.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="text-center py-5">
                            <p className="text-muted mb-3">No workflow executions match the current filters.</p>
                            <Button as={Link} to="/workflows/run" variant="outline-primary">
                              Run a workflow
                            </Button>
                          </td>
                        </tr>
                      ) : (
                        executions.map((execution) => (
                        <tr key={execution.id}>
                          <td>
                            <Form.Check
                              type="checkbox"
                              checked={selectedIds.has(execution.id)}
                              onChange={() => toggleRowSelection(execution)}
                              disabled={
                                !canStopWorkflow(execution.status) ||
                                stoppingWorkflows.has(execution.id)
                              }
                              aria-label={`Select workflow ${execution.workflow_name || execution.id}`}
                            />
                          </td>
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
                              {formatWorkflowStatusLabel(execution.status)}
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
                        ))
                      )}
                    </tbody>
                  </Table>

                  {/* Pagination + page size */}
                  <div className="text-center text-muted small p-3 pb-2 mb-0">
                    Showing {pagerLabel.from} to {pagerLabel.to} of {totalItems} executions (Page{' '}
                    {currentPage} of {Math.max(totalPages, 1)})
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
                    )}
                  </div>
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
             <div className="card rh-elevated-card border">
               <div className="card-body">
                 <strong>Workflow:</strong> {workflowToStop.workflow_name}<br />
                 <strong>Program:</strong> {workflowToStop.program_name}<br />
                 <strong>Status:</strong> <Badge bg={getStatusBadge(workflowToStop.status)}>{formatWorkflowStatusLabel(workflowToStop.status)}</Badge><br />
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

      {/* Bulk stop confirmation */}
      <Modal show={showBulkStopModal} onHide={() => setShowBulkStopModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Stop workflows</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>
            Are you sure you want to stop{' '}
            <strong>{selectedIds.size}</strong> workflow{selectedIds.size === 1 ? '' : 's'}?
          </p>
          <div
            className="d-flex flex-column gap-2"
            style={{ maxHeight: '240px', overflowY: 'auto' }}
          >
            {[...selectedIds].map((id) => {
              const ex = executions.find((e) => e.id === id);
              return (
                <div key={id} className="card rh-elevated-card border">
                  <div className="card-body py-2">
                    <strong>{ex?.workflow_name ?? 'Unknown'}</strong>
                    <br />
                    <small className="text-muted">ID: {id}</small>
                    {ex && (
                      <>
                        <br />
                        <Badge bg={getStatusBadge(ex.status)}>{formatWorkflowStatusLabel(ex.status)}</Badge>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3">
            <Alert variant="warning" className="mb-0">
              <strong>⚠️ Warning:</strong> This will immediately stop all running tasks and cancel pending jobs. This action cannot be undone.
            </Alert>
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowBulkStopModal(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirmBulkStopWorkflows}>
            ⏹️ Stop {selectedIds.size} workflow{selectedIds.size === 1 ? '' : 's'}
          </Button>
        </Modal.Footer>
      </Modal>
    </Outer>
  );
}

function WorkflowStatus() {
  const { isSuperuser } = useAuth();
  const superuser = isSuperuser();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');

  const activeTab = useMemo(() => {
    if (tabParam === TAB_JOBS && !superuser) return TAB_WORKFLOWS;
    if (tabParam === TAB_JOBS || tabParam === TAB_WORKFLOWS) return tabParam;
    return TAB_WORKFLOWS;
  }, [tabParam, superuser]);

  usePageTitle(
    formatPageTitle(
      'Status Monitor',
      activeTab === TAB_JOBS ? 'Job monitoring' : 'Workflow monitoring'
    )
  );

  useEffect(() => {
    if (tabParam === TAB_JOBS && !superuser) {
      setSearchParams({ tab: TAB_WORKFLOWS }, { replace: true });
    } else if (tabParam && tabParam !== TAB_JOBS && tabParam !== TAB_WORKFLOWS) {
      setSearchParams({ tab: TAB_WORKFLOWS }, { replace: true });
    }
  }, [tabParam, superuser, setSearchParams]);

  return (
    <Container fluid className="p-4">
      <Row className="mb-3">
        <Col>
          <h1 className="h3 mb-0">📈 Status Monitor</h1>
          <p className="text-muted small mb-0">Workflow runs and batch jobs</p>
        </Col>
      </Row>
      <Tabs activeKey={activeTab} onSelect={(k) => k && setSearchParams({ tab: k })} className="mb-3">
        <Tab eventKey={TAB_WORKFLOWS} title="Workflow monitoring">
          <WorkflowMonitoringPanel embedded />
        </Tab>
        {superuser && (
          <Tab eventKey={TAB_JOBS} title="Job monitoring">
            <JobManagementInner embedded />
          </Tab>
        )}
      </Tabs>
    </Container>
  );
}

export default WorkflowStatus;