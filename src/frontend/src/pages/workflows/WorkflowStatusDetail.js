import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Button, Spinner, Alert, Modal, ButtonGroup, Form, InputGroup } from 'react-bootstrap';
import { workflowAPI } from '../../services/api';
import { formatDate, calculateDuration } from '../../utils/dateUtils';
import './WorkflowStatusDetail.css';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function WorkflowStatusDetail() {
  const { workflowId } = useParams();
  const [workflow, setWorkflow] = useState(null);
  const [logs, setLogs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stopping, setStopping] = useState(false);
  const [showStopModal, setShowStopModal] = useState(false);
  const [showRawData, setShowRawData] = useState(false);
  const [showWorkflowDefinition, setShowWorkflowDefinition] = useState(false);
  const [showTaskLogs, setShowTaskLogs] = useState(true);
  const [showPodOutput, setShowPodOutput] = useState(false);
  const [expandedTaskLogs, setExpandedTaskLogs] = useState(new Set());
  const [podOutputSearch, setPodOutputSearch] = useState('');
  const [podOutputMatchIndex, setPodOutputMatchIndex] = useState(0);
  const podOutputContainerRef = useRef(null);

  usePageTitle(formatPageTitle(logs?.workflow_name || workflowId, 'Workflow Run'));

  const loadWorkflowDetails = useCallback(async () => {
    try {
      setLoading(true);
      const [statusResponse, logsResponse] = await Promise.all([
        workflowAPI.getWorkflowStatusDetail(workflowId),
        workflowAPI.getWorkflowLogs(workflowId)
      ]);

      setWorkflow(statusResponse);
      setLogs(logsResponse);
      setError(null);
    } catch (err) {
      setError('Failed to load workflow details: ' + err.message);
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    loadWorkflowDetails();
  }, [workflowId, loadWorkflowDetails]);

  // Auto-scroll to current match when search term or match index changes
  useEffect(() => {
    if (podOutputSearch && logs?.runner_pod_output && podOutputContainerRef.current) {
      const matches = getSearchMatches(logs.runner_pod_output, podOutputSearch);
      if (matches.length > 0 && podOutputMatchIndex < matches.length) {
        setTimeout(() => {
          scrollToMatch(matches, podOutputMatchIndex, podOutputContainerRef, logs.runner_pod_output);
        }, 100);
      }
    }
  }, [podOutputSearch, podOutputMatchIndex, logs?.runner_pod_output]);

  const handleStopWorkflow = () => {
    setShowStopModal(true);
  };

  const confirmStopWorkflow = async () => {
    setStopping(true);
    setShowStopModal(false);

    try {
      const response = await workflowAPI.stopWorkflow(workflowId);
      
      if (response.status === 'success') {
        // Show success message and refresh data
        setError(null);
        await loadWorkflowDetails();
      } else if (response.status === 'stopping') {
        // Workflow is being stopped in the background
        setError(null);
        // Refresh data to show the "stopping" status
        await loadWorkflowDetails();
        // Keep the stopping state for a while to show progress
        setTimeout(() => {
          setStopping(false);
        }, 5000); // Keep showing stopping state for 5 seconds
        return; // Don't clear stopping state immediately
      } else if (response.status === 'already_finished') {
        // Workflow already finished, just refresh
        await loadWorkflowDetails();
      }
    } catch (err) {
      setError(`Failed to stop workflow: ${err.message}`);
    } finally {
      setStopping(false);
    }
  };

  const canStopWorkflow = (status) => {
    const stoppableStatuses = ['running', 'started', 'pending'];
    return stoppableStatuses.includes(status?.toLowerCase());
  };

  const getStatusBadge = (status) => {
    const statusMap = {
      'running': 'primary',
      'completed': 'success',
      'success': 'success',
      'failed': 'danger',
      'pending': 'warning',
      'cancelled': 'secondary',
      'stopped': 'secondary',
      'stopping': 'warning'
    };
    return statusMap[status?.toLowerCase()] || 'secondary';
  };

  const formatDateWithLabel = (dateString, label = '') => {
    if (!dateString) {
      // Provide context-specific messages
      if (label.toLowerCase().includes('started')) return 'Not started';
      if (label.toLowerCase().includes('completed')) return 'Not completed';
      return 'N/A';
    }
    return formatDate(dateString);
  };

  const formatDurationWithStatus = (startTime, endTime, status) => {
    if (!startTime) return 'Not started';

    // Check if workflow hasn't actually started
    if (status === 'pending' || status === 'queued') {
      return 'Not started';
    }

    const duration = calculateDuration(startTime, endTime);
    if (duration === 'Not started') return duration;

    // Add running indicator for active workflows
    if (!endTime && ['running', 'started'].includes(status?.toLowerCase())) {
      return `${duration} (running)`;
    }

    return duration;
  };

  const renderStepResults = (stepData) => {
    // Handle null/undefined stepData
    if (!stepData || typeof stepData !== 'object') {
      return <span className="text-muted">No results</span>;
    }

    // Check if this is the new detailed format
    if (stepData.total_assets !== undefined) {
      return (
        <div>
          {/* Main asset counts */}
          <div className="mb-2">
            <Badge bg="primary" className="me-2" title={`Total assets processed: ${stepData.total_assets}`}>
              📦 Assets: {stepData.total_assets}
            </Badge>
            {stepData.created_assets > 0 && (
              <Badge bg="success" className="me-1" title={`Assets created: ${stepData.created_assets}`}>
                🆕 Created: {stepData.created_assets}
              </Badge>
            )}
            {stepData.updated_assets > 0 && (
              <Badge bg="info" className="me-1" title={`Assets updated: ${stepData.updated_assets}`}>
                🔄 Updated: {stepData.updated_assets}
              </Badge>
            )}
            {stepData.failed_assets > 0 && (
              <Badge bg="danger" className="me-1" title={`Assets failed: ${stepData.failed_assets}`}>
                ❌ Failed: {stepData.failed_assets}
              </Badge>
            )}
          </div>

          {/* Main findings counts */}
          {stepData.total_findings !== undefined && stepData.total_findings > 0 && (
            <div className="mb-2">
              <Badge bg="warning" className="me-2" title={`Total findings processed: ${stepData.total_findings}`}>
                🔍 Findings: {stepData.total_findings}
              </Badge>
              {stepData.created_findings > 0 && (
                <Badge bg="success" className="me-1" title={`Findings created: ${stepData.created_findings}`}>
                  🆕 Created: {stepData.created_findings}
                </Badge>
              )}
              {stepData.updated_findings > 0 && (
                <Badge bg="info" className="me-1" title={`Findings updated: ${stepData.updated_findings}`}>
                  🔄 Updated: {stepData.updated_findings}
                </Badge>
              )}
              {stepData.failed_findings > 0 && (
                <Badge bg="danger" className="me-1" title={`Findings failed: ${stepData.failed_findings}`}>
                  ❌ Failed: {stepData.failed_findings}
                </Badge>
              )}
            </div>
          )}

          {/* Asset type breakdown */}
          {stepData.asset_types && Object.keys(stepData.asset_types).length > 0 && (
            <div className="mb-3">
              <small className="text-muted fw-bold">📦 Asset Types:</small>
              <div className="mt-1">
                {Object.entries(stepData.asset_types).map(([assetType, counts]) => (
                  <div key={assetType} className="ms-2 mb-1">
                    <Badge bg="light" text="dark" className="me-2">
                      {assetType}: {counts.total}
                    </Badge>
                    {counts.created > 0 && (
                      <Badge bg="success" className="me-1" title={`Created: ${counts.created}`}>
                        + {counts.created}
                      </Badge>
                    )}
                    {counts.updated > 0 && (
                      <Badge bg="info" className="me-1" title={`Updated: ${counts.updated}`}>
                        ↻ {counts.updated}
                      </Badge>
                    )}
                    {counts.skipped > 0 && (
                      <Badge bg="warning" className="me-1" title={`Skipped: ${counts.skipped}`}>
                        ⏭️ {counts.skipped}
                      </Badge>
                    )}
                    {counts.out_of_scope > 0 && (
                      <Badge bg="secondary" className="me-1" title={`Out of scope: ${counts.out_of_scope}`}>
                        🚫 {counts.out_of_scope}
                      </Badge>
                    )}
                    {counts.failed > 0 && (
                      <Badge bg="danger" className="me-1" title={`Failed: ${counts.failed}`}>
                        ✗ {counts.failed}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Finding type breakdown */}
          {stepData.finding_types && Object.keys(stepData.finding_types).length > 0 && (
            <div>
              <small className="text-muted fw-bold">🔍 Finding Types:</small>
              <div className="mt-1">
                {Object.entries(stepData.finding_types).map(([findingType, counts]) => (
                  <div key={findingType} className="ms-2 mb-1">
                    <Badge bg="warning" text="dark" className="me-2">
                      {findingType}: {counts.total}
                    </Badge>
                    {counts.created > 0 && (
                      <Badge bg="success" className="me-1" title={`Created: ${counts.created}`}>
                        + {counts.created}
                      </Badge>
                    )}
                    {counts.updated > 0 && (
                      <Badge bg="info" className="me-1" title={`Updated: ${counts.updated}`}>
                        ↻ {counts.updated}
                      </Badge>
                    )}
                    {counts.skipped > 0 && (
                      <Badge bg="warning" className="me-1" title={`Skipped: ${counts.skipped}`}>
                        ⏭️ {counts.skipped}
                      </Badge>
                    )}
                    {counts.out_of_scope > 0 && (
                      <Badge bg="secondary" className="me-1" title={`Out of scope: ${counts.out_of_scope}`}>
                        🚫 {counts.out_of_scope}
                      </Badge>
                    )}
                    {counts.failed > 0 && (
                      <Badge bg="danger" className="me-1" title={`Failed: ${counts.failed}`}>
                        ✗ {counts.failed}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      );
    }

    // Fallback for old simple format or other formats
    return (
      <div>
        {Object.entries(stepData).map(([key, value]) => {
          // Handle nested objects (like asset_types in new format)
          if (typeof value === 'object' && value !== null) {
            return (
              <div key={key} className="mb-1">
                <small className="text-muted fw-bold">{key}:</small>
                <div className="ms-2">
                  {Object.entries(value).map(([subKey, subValue]) => (
                    <Badge key={subKey} bg="secondary" className="me-1 mb-1">
                      {subKey}: {subValue}
                    </Badge>
                  ))}
                </div>
              </div>
            );
          }

          // Handle simple key-value pairs
          return (
            <Badge key={key} bg="secondary" className="me-1 mb-1">
              {key}: {value}
            </Badge>
          );
        })}
      </div>
    );
  };

  const highlightSearchMatches = (text, searchTerm) => {
    if (!searchTerm || !text) {
      return text;
    }

    try {
      const escapedSearch = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(${escapedSearch})`, 'gi');
      const parts = text.split(regex);
      
      return parts.map((part, index) => {
        // Check if this part matches the search term (case-insensitive)
        const testRegex = new RegExp(`^${escapedSearch}$`, 'i');
        if (testRegex.test(part)) {
          return (
            <mark key={index} style={{ backgroundColor: '#ffeb3b', padding: '0', color: '#000' }}>
              {part}
            </mark>
          );
        }
        return part;
      });
    } catch (e) {
      // If regex is invalid, just return the text
      return text;
    }
  };

  const getSearchMatches = (text, searchTerm) => {
    if (!searchTerm || !text) {
      return [];
    }

    try {
      const regex = new RegExp(searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const matches = [];
      let match;
      
      while ((match = regex.exec(text)) !== null) {
        matches.push({
          index: match.index,
          length: match[0].length
        });
      }
      
      return matches;
    } catch (e) {
      return [];
    }
  };

  const downloadPodOutput = () => {
    if (!logs?.runner_pod_output) return;
    const blob = new Blob([logs.runner_pod_output], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `workflow-${workflowId}-pod-output.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const scrollToMatch = (matches, currentIndex, containerRef, text) => {
    if (!containerRef.current || matches.length === 0 || !text) {
      return;
    }

    const container = containerRef.current;
    const match = matches[currentIndex];
    if (!match) return;

    // Calculate approximate position based on line breaks
    const textBeforeMatch = text.substring(0, match.index);
    const lines = textBeforeMatch.split('\n');
    const lineNumber = lines.length - 1;
    const lineHeight = 14; // Approximate line height in pixels (0.75rem * 1.5)
    const scrollPosition = lineNumber * lineHeight;

    container.scrollTop = Math.max(0, scrollPosition - 100); // Offset by 100px for visibility
  };

  const renderWorkflowLogs = (logs) => {
    if (!logs) {
      return <p className="text-muted">No logs available</p>;
    }

    return (
      <div>
        {/* Quick Stats Summary */}
        <div className="mb-4">
          <Card className="border summary-card">
            <Card.Body>
              <div className="d-flex justify-content-between align-items-center">
                <div className="d-flex align-items-center">
                  <span className="me-3 fs-4">
                    {logs.result === 'success' || logs.result === 'completed' ? '✅' :
                     logs.result === 'failed' ? '❌' :
                     logs.result === 'running' ? '🔄' : '⏸️'}
                  </span>
                  <div>
                    <h5 className="mb-1 fw-bold">
                      {logs.workflow_name || 'Workflow Execution'}
                    </h5>
                    <p className="mb-0 text-muted">
                      <Badge bg={getStatusBadge(logs.result)} className="me-2">
                        {logs.result || 'unknown'}
                      </Badge>
                      {logs.workflow_steps?.length > 0 && (
                        <span className="me-2">
                          📝 {logs.workflow_steps.length} step{logs.workflow_steps.length !== 1 ? 's' : ''}
                        </span>
                      )}
                      {logs.program_name && (
                        <span className="me-2">
                          🏢 {logs.program_name}
                        </span>
                      )}
                      <span className="me-2">
                        ⏱️ {formatDurationWithStatus(logs.started_at || logs.created_at, logs.completed_at || logs.updated_at, logs.result)}
                      </span>
                    </p>
                  </div>
                </div>
                <div className="text-end">
                  <div className="text-muted small">Execution ID</div>
                  <code className="small">{logs.execution_id || logs.workflow_id || 'N/A'}</code>
                </div>
              </div>
            </Card.Body>
          </Card>
        </div>

        {/* Workflow Execution Summary */}
        <div className="mb-4">
          <h6 className="fw-bold text-primary mb-3">📊 Execution Summary</h6>
          <Row>
            <Col md={4}>
              <div className="bg-light p-3 rounded">
                <div className="d-flex align-items-center mb-2">
                  <span className="me-2">🏷️</span>
                  <strong>Execution ID</strong>
                </div>
                <code className="text-break">{logs.execution_id || logs.workflow_id || 'N/A'}</code>
              </div>
            </Col>
            <Col md={4}>
              <div className="bg-light p-3 rounded">
                <div className="d-flex align-items-center mb-2">
                  <span className="me-2">📋</span>
                  <strong>Workflow Name</strong>
                </div>
                <span>{logs.workflow_name || 'N/A'}</span>
              </div>
            </Col>
            <Col md={4}>
              <div className="bg-light p-3 rounded">
                <div className="d-flex align-items-center mb-2">
                  <span className="me-2">🏢</span>
                  <strong>Program</strong>
                </div>
                <Badge bg="primary">{logs.program_name || 'Unknown'}</Badge>
              </div>
            </Col>
          </Row>
        </div>

        {/* Status and Timestamps */}
        <div className="mb-4">
          <h6 className="fw-bold text-primary mb-3">⏱️ Status & Timeline</h6>
          <Row>
            <Col md={3}>
              <div className="bg-light p-3 rounded text-center">
                <div className="mb-2">
                  <Badge bg={getStatusBadge(logs.result)} className="fs-6">
                    {logs.result || 'unknown'}
                  </Badge>
                </div>
                <small className="text-muted">Final Status</small>
              </div>
            </Col>
            <Col md={3}>
              <div className="bg-light p-3 rounded">
                <div className="d-flex align-items-center mb-2">
                  <span className="me-2">🟢</span>
                  <strong>Workflow Started</strong>
                </div>
                <div>{formatDateWithLabel(logs.started_at || logs.created_at, 'started')}</div>
              </div>
            </Col>
            <Col md={3}>
              <div className="bg-light p-3 rounded">
                <div className="d-flex align-items-center mb-2">
                  <span className="me-2">✅</span>
                  <strong>Workflow Completed</strong>
                </div>
                <div>{formatDateWithLabel(logs.completed_at, 'completed')}</div>
              </div>
            </Col>
            <Col md={3}>
              <div className="bg-light p-3 rounded">
                <div className="d-flex align-items-center mb-2">
                  <span className="me-2">⏱️</span>
                  <strong>Duration</strong>
                </div>
                <div>{formatDurationWithStatus(logs.started_at || logs.created_at, logs.completed_at || logs.updated_at, logs.result)}</div>
              </div>
            </Col>
          </Row>
        </div>

        {/* Workflow Steps Details */}
        {logs.workflow_steps && logs.workflow_steps.length > 0 && (
          <div className="mb-4">
            <h6 className="fw-bold text-primary mb-3">📝 Step Execution Details</h6>
            <div className="accordion" id="workflowStepsAccordion">
              {logs.workflow_steps.map((step, index) => {
                const stepName = Object.keys(step)[0];
                const stepData = step[stepName];
                const hasData = stepData && typeof stepData === 'object' &&
                  (stepData.total_assets > 0 || stepData.started_at || stepData.completed_at ||
                   (stepData.asset_types && Object.keys(stepData.asset_types).length > 0));

                return (
                  <div key={index} className="accordion-item">
                    <h2 className="accordion-header" id={`heading-${index}`}>
                      <button
                        className={`accordion-button theme-aware-accordion ${index === 0 ? '' : 'collapsed'}`}
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          const target = document.getElementById(`step-${index}`);
                          const button = e.currentTarget;
                          const isExpanded = button.getAttribute('aria-expanded') === 'true';

                          // Toggle the collapse state
                          if (target) {
                            if (isExpanded) {
                              target.classList.remove('show');
                              button.classList.add('collapsed');
                              button.setAttribute('aria-expanded', 'false');
                            } else {
                              target.classList.add('show');
                              button.classList.remove('collapsed');
                              button.setAttribute('aria-expanded', 'true');
                            }
                          }
                        }}
                        aria-expanded={index === 0 ? 'true' : 'false'}
                        aria-controls={`step-${index}`}
                      >
                        <div className="d-flex align-items-center w-100">
                          <Badge bg="secondary" className="me-2">
                            Step {index + 1}
                          </Badge>
                          <code className="me-3 flex-grow-1">{stepName}</code>
                          <div className="d-flex gap-1">
                            {stepData?.started_at && (
                              <small className="text-muted me-2">
                                🟢 {formatDate(stepData.started_at)}
                              </small>
                            )}
                            {stepData?.completed_at && (
                              <small className="text-muted me-2">
                                ✅ {formatDate(stepData.completed_at)}
                              </small>
                            )}
                            {stepData?.started_at && stepData?.completed_at && (
                              <small className="text-muted me-2">
                                ⏱️ {calculateDuration(stepData.started_at, stepData.completed_at)}
                              </small>
                            )}
                            {stepData?.total_assets > 0 && (
                              <Badge bg="primary" title={`Total assets: ${stepData.total_assets}`}>
                                📦 {stepData.total_assets} assets
                              </Badge>
                            )}
                            {stepData?.total_findings > 0 && (
                              <Badge bg="warning" title={`Total findings: ${stepData.total_findings}`}>
                                🔍 {stepData.total_findings} findings
                              </Badge>
                            )}
                            {stepData?.created_assets > 0 && (
                              <Badge bg="success" className="text-white" title={`Assets created: ${stepData.created_assets}`}>
                                + {stepData.created_assets}
                              </Badge>
                            )}
                            {stepData?.created_findings > 0 && (
                              <Badge bg="success" className="text-white" title={`Findings created: ${stepData.created_findings}`}>
                                + {stepData.created_findings}
                              </Badge>
                            )}
                            {stepData?.updated_assets > 0 && (
                              <Badge bg="info" title={`Assets updated: ${stepData.updated_assets}`}>
                                ↻ {stepData.updated_assets}
                              </Badge>
                            )}
                            {stepData?.updated_findings > 0 && (
                              <Badge bg="info" title={`Findings updated: ${stepData.updated_findings}`}>
                                ↻ {stepData.updated_findings}
                              </Badge>
                            )}
                            {stepData?.failed_assets > 0 && (
                              <Badge bg="danger" title={`Assets failed: ${stepData.failed_assets}`}>
                                ✗ {stepData.failed_assets}
                              </Badge>
                            )}
                            {stepData?.failed_findings > 0 && (
                              <Badge bg="danger" title={`Findings failed: ${stepData.failed_findings}`}>
                                ✗ {stepData.failed_findings}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </button>
                    </h2>
                    <div
                      id={`step-${index}`}
                      className={`accordion-collapse collapse ${index === 0 ? 'show' : ''}`}
                      aria-labelledby={`heading-${index}`}
                    >
                      <div className="accordion-body">
                        {hasData ? renderStepResults(stepData) : (
                          <p className="text-muted mb-0">No execution data available for this step.</p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Workflow Definition */}
        {logs.workflow_definition && (
          <div className="mb-4">
            <h6 className="fw-bold text-primary mb-3">📋 Workflow Definition</h6>
            <Card className="border">
              <Card.Header className="theme-aware-header">
                <div className="d-flex justify-content-between align-items-center">
                  <span>
                    <strong>{logs.workflow_definition.name || 'Workflow'}</strong>
                    {logs.workflow_definition.description && (
                      <span className="text-muted ms-2">- {logs.workflow_definition.description}</span>
                    )}
                  </span>
                  <Button
                    variant="outline-secondary"
                    size="sm"
                    onClick={() => setShowWorkflowDefinition(!showWorkflowDefinition)}
                  >
                    {showWorkflowDefinition ? '▼ Hide' : '▶ Show'}
                  </Button>
                </div>
              </Card.Header>
              {showWorkflowDefinition && (
                <Card.Body>
                  {/* Workflow Inputs */}
                  {logs.workflow_definition.inputs && Object.keys(logs.workflow_definition.inputs).length > 0 && (
                    <div className="mb-3">
                      <h6 className="fw-bold text-secondary mb-2">📥 Inputs</h6>
                      <div className="bg-light p-3 rounded">
                        {Object.entries(logs.workflow_definition.inputs).map(([inputName, inputDef]) => (
                          <div key={inputName} className="mb-2">
                            <Badge bg="primary" className="me-2">{inputName}</Badge>
                            <span className="text-muted">Type: {inputDef.type}</span>
                            {inputDef.asset_type && <span className="text-muted ms-2">Asset Type: {inputDef.asset_type}</span>}
                            {inputDef.finding_type && <span className="text-muted ms-2">Finding Type: {inputDef.finding_type}</span>}
                            {inputDef.type === 'program_protected_domains' && <span className="text-muted ms-2">(Protected domains)</span>}
                            {inputDef.type === 'program_scope_domains' && <span className="text-muted ms-2">(Scope domains)</span>}
                            {inputDef.limit && <span className="text-muted ms-2">Limit: {inputDef.limit}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Workflow Variables */}
                  {logs.workflow_definition.variables && Object.keys(logs.workflow_definition.variables).length > 0 && (
                    <div className="mb-3">
                      <h6 className="fw-bold text-secondary mb-2">🔧 Variables</h6>
                      <div className="bg-light p-3 rounded">
                        {Object.entries(logs.workflow_definition.variables).map(([varName, varValue]) => (
                          <div key={varName} className="mb-1">
                            <Badge bg="info" className="me-2">{varName}</Badge>
                            <code>{typeof varValue === 'object' ? JSON.stringify(varValue) : String(varValue)}</code>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Workflow Steps */}
                  {logs.workflow_definition.steps && logs.workflow_definition.steps.length > 0 && (
                    <div>
                      <h6 className="fw-bold text-secondary mb-2">📝 Steps</h6>
                      <div className="accordion" id="workflowDefStepsAccordion">
                        {logs.workflow_definition.steps.map((step, stepIndex) => {
                          const stepId = `def-step-${stepIndex}`;
                          const isExpanded = stepIndex === 0;
                          
                          return (
                            <div key={stepIndex} className="accordion-item">
                              <h2 className="accordion-header">
                                <button
                                  className={`accordion-button theme-aware-accordion ${isExpanded ? '' : 'collapsed'}`}
                                  type="button"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    const target = document.getElementById(stepId);
                                    const button = e.currentTarget;
                                    const currentExpanded = button.getAttribute('aria-expanded') === 'true';
                                    
                                    if (target) {
                                      if (currentExpanded) {
                                        target.classList.remove('show');
                                        button.classList.add('collapsed');
                                        button.setAttribute('aria-expanded', 'false');
                                      } else {
                                        target.classList.add('show');
                                        button.classList.remove('collapsed');
                                        button.setAttribute('aria-expanded', 'true');
                                      }
                                    }
                                  }}
                                  aria-expanded={isExpanded ? 'true' : 'false'}
                                  aria-controls={stepId}
                                >
                                  <Badge bg="secondary" className="me-2">Step {stepIndex + 1}</Badge>
                                  <code className="me-3">{step.name}</code>
                                  <Badge bg="light" text="dark">{step.tasks?.length || 0} task(s)</Badge>
                                </button>
                              </h2>
                              <div
                                id={stepId}
                                className={`accordion-collapse collapse ${isExpanded ? 'show' : ''}`}
                                aria-labelledby={`heading-${stepIndex}`}
                              >
                                <div className="accordion-body">
                                  {step.tasks && step.tasks.map((task, taskIndex) => (
                                    <Card key={taskIndex} className="mb-2 border">
                                      <Card.Body className="p-3">
                                        <div className="d-flex justify-content-between align-items-start mb-2">
                                          <div>
                                            <Badge bg="primary" className="me-2">{task.name}</Badge>
                                            {task.task_type && (
                                              <Badge bg="info" className="me-2" title="Task Type">
                                                {task.task_type}
                                              </Badge>
                                            )}
                                          </div>
                                        </div>
                                        {task.params && Object.keys(task.params).length > 0 && (
                                          <div className="mb-2">
                                            <small className="text-muted fw-bold">Parameters:</small>
                                            <div className="ms-2 mt-1">
                                              {Object.entries(task.params).map(([key, value]) => (
                                                <Badge key={key} bg="light" text="dark" className="me-1 mb-1">
                                                  {key}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                </Badge>
                                              ))}
                                            </div>
                                          </div>
                                        )}
                                        {task.input_mapping && Object.keys(task.input_mapping).length > 0 && (
                                          <div className="mb-2">
                                            <small className="text-muted fw-bold">Input Mapping:</small>
                                            <div className="ms-2 mt-1">
                                              {Object.entries(task.input_mapping).map(([key, value]) => (
                                                <div key={key} className="small">
                                                  <Badge bg="secondary" className="me-1">{key}</Badge>
                                                  <span className="text-muted">→</span>
                                                  <code className="ms-1">{value}</code>
                                                </div>
                                              ))}
                                            </div>
                                          </div>
                                        )}
                                        {task.output_mode && (
                                          <div className="mb-1">
                                            <small className="text-muted">Output Mode: </small>
                                            <Badge bg="warning" text="dark">{task.output_mode}</Badge>
                                          </div>
                                        )}
                                        {task.use_proxy && (
                                          <div className="mb-1">
                                            <small className="text-muted">Proxy: </small>
                                            <Badge bg="success">Enabled</Badge>
                                          </div>
                                        )}
                                      </Card.Body>
                                    </Card>
                                  ))}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </Card.Body>
              )}
            </Card>
          </div>
        )}

        {/* Task Execution Logs */}
        {logs.task_execution_logs && logs.task_execution_logs.length > 0 && (
          <div className="mb-4">
            <h6 className="fw-bold text-primary mb-3">⚙️ Task Execution Logs</h6>
            <Card className="border">
              <Card.Header className="theme-aware-header">
                <div className="d-flex justify-content-between align-items-center">
                  <span>
                    <strong>{logs.task_execution_logs.length} task execution(s)</strong>
                  </span>
                  <Button
                    variant="outline-secondary"
                    size="sm"
                    onClick={() => setShowTaskLogs(!showTaskLogs)}
                  >
                    {showTaskLogs ? '▼ Hide' : '▶ Show'}
                  </Button>
                </div>
              </Card.Header>
              {showTaskLogs && (
                <Card.Body className="p-0">
                  <div className="table-responsive">
                    <table className="table table-hover mb-0">
                      <thead className="theme-aware-table-header">
                        <tr>
                          <th>Step</th>
                          <th>Task</th>
                          <th>Type</th>
                          <th>Input</th>
                          <th>Output</th>
                          <th>Duration</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {logs.task_execution_logs.map((taskLog, index) => {
                          const isExpanded = expandedTaskLogs.has(index);
                          const hasDetails = taskLog.params || taskLog.input_data !== undefined || taskLog.error || taskLog.started_at || taskLog.completed_at;
                          
                          return (
                            <React.Fragment key={index}>
                              <tr>
                                <td>
                                  <Badge bg="secondary">{taskLog.step_name}</Badge>
                                </td>
                                <td>
                                  <code>{taskLog.task_name}</code>
                                </td>
                                <td>
                                  <Badge bg="info">{taskLog.task_type || 'N/A'}</Badge>
                                </td>
                                <td>
                                  <span className="text-muted">{taskLog.input_count || 0}</span>
                                </td>
                                <td>
                                  <div>
                                    <span className="text-muted">{taskLog.output_count || 0} total</span>
                                    {taskLog.output_asset_types && Object.keys(taskLog.output_asset_types).length > 0 && (
                                      <div className="mt-1">
                                        {Object.entries(taskLog.output_asset_types).slice(0, 3).map(([type, count]) => (
                                          <Badge key={type} bg="light" text="dark" className="me-1" style={{ fontSize: '0.7rem' }}>
                                            {type}: {count}
                                          </Badge>
                                        ))}
                                        {Object.keys(taskLog.output_asset_types).length > 3 && (
                                          <Badge bg="secondary" style={{ fontSize: '0.7rem' }}>
                                            +{Object.keys(taskLog.output_asset_types).length - 3} more
                                          </Badge>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                </td>
                                <td>
                                  <small className="text-muted">
                                    {taskLog.duration_seconds ? `${taskLog.duration_seconds.toFixed(2)}s` : 'N/A'}
                                  </small>
                                </td>
                                <td>
                                  <Badge bg={taskLog.status === 'success' ? 'success' : taskLog.status === 'failed' ? 'danger' : 'warning'}>
                                    {taskLog.status || 'unknown'}
                                  </Badge>
                                  {taskLog.error && (
                                    <div className="mt-1">
                                      <Badge bg="danger" style={{ fontSize: '0.7rem' }} title={taskLog.error}>
                                        ❌ Error
                                      </Badge>
                                    </div>
                                  )}
                                </td>
                                <td>
                                  {hasDetails && (
                                    <Button
                                      variant="outline-secondary"
                                      size="sm"
                                      onClick={() => {
                                        const newExpanded = new Set(expandedTaskLogs);
                                        if (isExpanded) {
                                          newExpanded.delete(index);
                                        } else {
                                          newExpanded.add(index);
                                        }
                                        setExpandedTaskLogs(newExpanded);
                                      }}
                                    >
                                      {isExpanded ? '▼ Hide' : '▶ Show'}
                                    </Button>
                                  )}
                                </td>
                              </tr>
                              {isExpanded && hasDetails && (
                                <tr>
                                  <td colSpan="8" className="bg-light">
                                    <div className="p-3">
                                      {/* Task Parameters */}
                                      {taskLog.params && Object.keys(taskLog.params).length > 0 && (
                                        <div className="mb-3">
                                          <h6 className="fw-bold text-secondary mb-2" style={{ fontSize: '0.875rem' }}>📋 Parameters</h6>
                                          <div className="ms-3">
                                            {Object.entries(taskLog.params).map(([key, value]) => (
                                              <div key={key} className="mb-1">
                                                <Badge bg="light" text="dark" className="me-2">{key}</Badge>
                                                <code className="small">
                                                  {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                                                </code>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}
                                      
                                      {/* Input Data */}
                                      {taskLog.input_data !== undefined && taskLog.input_data !== null && (
                                        <div className="mb-3">
                                          <h6 className="fw-bold text-secondary mb-2" style={{ fontSize: '0.875rem' }}>
                                            📥 Input Data ({taskLog.input_count || 0} item{taskLog.input_count !== 1 ? 's' : ''})
                                          </h6>
                                          <div className="ms-3">
                                            {Array.isArray(taskLog.input_data) ? (
                                              <div className="bg-light p-2 rounded" style={{ maxHeight: '300px', overflow: 'auto' }}>
                                                {taskLog.input_data.length > 0 ? (
                                                  <ul className="mb-0" style={{ fontSize: '0.8rem' }}>
                                                    {taskLog.input_data.slice(0, 100).map((item, idx) => (
                                                      <li key={idx} className="mb-1">
                                                        <code className="small">
                                                          {typeof item === 'object' ? JSON.stringify(item) : String(item)}
                                                        </code>
                                                      </li>
                                                    ))}
                                                    {taskLog.input_data.length > 100 && (
                                                      <li className="text-muted" style={{ fontSize: '0.75rem' }}>
                                                        ... and {taskLog.input_data.length - 100} more items
                                                      </li>
                                                    )}
                                                  </ul>
                                                ) : (
                                                  <span className="text-muted small">No input data</span>
                                                )}
                                              </div>
                                            ) : (
                                              <div className="bg-light p-2 rounded">
                                                <code className="small">
                                                  {typeof taskLog.input_data === 'object' ? JSON.stringify(taskLog.input_data, null, 2) : String(taskLog.input_data)}
                                                </code>
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                      )}
                                      
                                      {/* Timing Information */}
                                      {(taskLog.started_at || taskLog.completed_at) && (
                                        <div className="mb-3">
                                          <h6 className="fw-bold text-secondary mb-2" style={{ fontSize: '0.875rem' }}>⏱️ Timing</h6>
                                          <div className="ms-3">
                                            {taskLog.started_at && (
                                              <div className="mb-1">
                                                <Badge bg="success" className="me-2">Started</Badge>
                                                <small>{formatDate(taskLog.started_at)}</small>
                                              </div>
                                            )}
                                            {taskLog.completed_at && (
                                              <div className="mb-1">
                                                <Badge bg="info" className="me-2">Completed</Badge>
                                                <small>{formatDate(taskLog.completed_at)}</small>
                                              </div>
                                            )}
                                            {taskLog.started_at && taskLog.completed_at && (
                                              <div className="mb-1">
                                                <Badge bg="primary" className="me-2">Duration</Badge>
                                                <small>{calculateDuration(taskLog.started_at, taskLog.completed_at)}</small>
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                      )}
                                      
                                      {/* Error Details */}
                                      {taskLog.error && (
                                        <div className="mb-2">
                                          <h6 className="fw-bold text-danger mb-2" style={{ fontSize: '0.875rem' }}>❌ Error Details</h6>
                                          <Alert variant="danger" className="ms-3 mb-0 py-2">
                                            <small className="font-monospace" style={{ whiteSpace: 'pre-wrap' }}>
                                              {taskLog.error}
                                            </small>
                                          </Alert>
                                        </div>
                                      )}
                                      
                                      {/* Output Asset Types Breakdown */}
                                      {taskLog.output_asset_types && Object.keys(taskLog.output_asset_types).length > 0 && (
                                        <div>
                                          <h6 className="fw-bold text-secondary mb-2" style={{ fontSize: '0.875rem' }}>📦 Output Breakdown</h6>
                                          <div className="ms-3">
                                            {Object.entries(taskLog.output_asset_types).map(([type, count]) => (
                                              <Badge key={type} bg="light" text="dark" className="me-2 mb-1">
                                                {type}: {count}
                                              </Badge>
                                            ))}
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Card.Body>
              )}
            </Card>
          </div>
        )}

        {/* Runner Pod Output */}
        {logs.runner_pod_output && (
          <div className="mb-4">
            <h6 className="fw-bold text-primary mb-3">📟 Runner Pod Output</h6>
            <Card className="border">
              <Card.Header className="theme-aware-header">
                <div className="d-flex justify-content-between align-items-center">
                  <span>
                    <strong>Pod Logs</strong>
                    <small className="text-muted ms-2">
                      ({logs.runner_pod_output.length} characters)
                    </small>
                  </span>
                  <div className="d-flex gap-1">
                    <Button
                      variant="outline-primary"
                      size="sm"
                      onClick={downloadPodOutput}
                      title="Download pod output as text file"
                    >
                      ⬇ Download
                    </Button>
                    <Button
                      variant="outline-secondary"
                      size="sm"
                      onClick={() => setShowPodOutput(!showPodOutput)}
                    >
                      {showPodOutput ? '▼ Hide' : '▶ Show'}
                    </Button>
                  </div>
                </div>
              </Card.Header>
              {showPodOutput && (
                <Card.Body className="p-0">
                  {/* Search Box */}
                  <div className="p-3 border-bottom">
                    <InputGroup size="sm">
                      <InputGroup.Text>🔍</InputGroup.Text>
                      <Form.Control
                        type="text"
                        placeholder="Search in pod logs..."
                        value={podOutputSearch}
                        onChange={(e) => {
                          setPodOutputSearch(e.target.value);
                          setPodOutputMatchIndex(0);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && podOutputSearch) {
                            const matches = getSearchMatches(logs.runner_pod_output, podOutputSearch);
                            if (matches.length > 0) {
                              const nextIndex = (podOutputMatchIndex + 1) % matches.length;
                              setPodOutputMatchIndex(nextIndex);
                              setTimeout(() => {
                                scrollToMatch(matches, nextIndex, podOutputContainerRef, logs.runner_pod_output);
                              }, 50);
                            }
                          }
                        }}
                      />
                      {podOutputSearch && (() => {
                        const matches = getSearchMatches(logs.runner_pod_output, podOutputSearch);
                        return (
                          <>
                            <InputGroup.Text>
                              {matches.length > 0 ? (
                                <span className="text-success">
                                  {podOutputMatchIndex + 1} / {matches.length}
                                </span>
                              ) : (
                                <span className="text-danger">0 matches</span>
                              )}
                            </InputGroup.Text>
                            {matches.length > 0 && (
                              <>
                                <Button
                                  variant="outline-secondary"
                                  onClick={() => {
                                    const prevIndex = podOutputMatchIndex > 0 
                                      ? podOutputMatchIndex - 1 
                                      : matches.length - 1;
                                    setPodOutputMatchIndex(prevIndex);
                                    setTimeout(() => {
                                      scrollToMatch(matches, prevIndex, podOutputContainerRef, logs.runner_pod_output);
                                    }, 50);
                                  }}
                                  disabled={matches.length === 0}
                                >
                                  ↑ Prev
                                </Button>
                                <Button
                                  variant="outline-secondary"
                                  onClick={() => {
                                    const nextIndex = (podOutputMatchIndex + 1) % matches.length;
                                    setPodOutputMatchIndex(nextIndex);
                                    setTimeout(() => {
                                      scrollToMatch(matches, nextIndex, podOutputContainerRef, logs.runner_pod_output);
                                    }, 50);
                                  }}
                                  disabled={matches.length === 0}
                                >
                                  Next ↓
                                </Button>
                              </>
                            )}
                            <Button
                              variant="outline-secondary"
                              onClick={() => {
                                setPodOutputSearch('');
                                setPodOutputMatchIndex(0);
                              }}
                            >
                              ✕ Clear
                            </Button>
                          </>
                        );
                      })()}
                    </InputGroup>
                  </div>
                  {/* Pod Output Content */}
                  <div 
                    ref={podOutputContainerRef}
                    className="theme-aware-code-block rounded p-3" 
                    style={{ maxHeight: '600px', overflow: 'auto' }}
                  >
                    <pre className="mb-0" style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {highlightSearchMatches(logs.runner_pod_output, podOutputSearch)}
                    </pre>
                  </div>
                </Card.Body>
              )}
            </Card>
          </div>
        )}

        {/* Additional Metadata */}
        {(logs.workflow_id || logs.total_steps) && (
          <div className="mb-4">
            <h6 className="fw-bold text-primary mb-3">📋 Additional Information</h6>
            <Row>
              {logs.workflow_id && (
                <Col md={4}>
                  <div className="bg-light p-3 rounded">
                    <div className="d-flex align-items-center mb-2">
                      <span className="me-2">🔗</span>
                      <strong>Workflow ID</strong>
                    </div>
                    <code className="text-break">{logs.workflow_id}</code>
                  </div>
                </Col>
              )}
              {logs.total_steps && (
                <Col md={4}>
                  <div className="bg-light p-3 rounded">
                    <div className="d-flex align-items-center mb-2">
                      <span className="me-2">📏</span>
                      <strong>Total Steps</strong>
                    </div>
                    <Badge bg="info" className="fs-6">{logs.total_steps}</Badge>
                  </div>
                </Col>
              )}
            </Row>
          </div>
        )}

        {/* Raw Data Section */}
        {showRawData && (
          <div className="mt-4">
            <h6 className="fw-bold text-secondary mb-3">🔧 Raw JSON Data</h6>
            <Alert variant="info" className="mb-3">
              <small>
                💡 This section contains the complete raw workflow data for debugging and detailed analysis.
                Use this when you need to see all the technical details of the workflow execution.
              </small>
            </Alert>
            <Card className="border-secondary">
              <Card.Body className="p-0">
                <div className="theme-aware-code-block rounded p-3" style={{ maxHeight: '500px', overflow: 'auto' }}>
                  <pre className="mb-0" style={{ fontSize: '0.75rem' }}>
                    {JSON.stringify(logs, null, 2)}
                  </pre>
                </div>
              </Card.Body>
              <Card.Footer className="text-muted">
                                  <small>
                    📄 {JSON.stringify(logs).length.toLocaleString()} characters |
                    📊 {Object.keys(logs).length} top-level properties |
                    🟢 Started: {formatDateWithLabel(logs.started_at || logs.created_at, 'started')} |
                    ✅ Completed: {formatDateWithLabel(logs.completed_at, 'completed')}
                </small>
              </Card.Footer>
            </Card>
          </div>
        )}
      </div>
    );
  };

  const aggregateAllAssetsAndFindings = (steps) => {
    if (!steps || !Array.isArray(steps) || steps.length === 0) {
      return {
        totalAssets: 0,
        totalFindings: 0,
        createdAssets: 0,
        createdFindings: 0,
        updatedAssets: 0,
        updatedFindings: 0,
        skippedAssets: 0,
        skippedFindings: 0,
        failedAssets: 0,
        failedFindings: 0,
        assetTypes: {},
        findingTypes: {}
      };
    }

    const aggregated = {
      totalAssets: 0,
      totalFindings: 0,
      createdAssets: 0,
      createdFindings: 0,
      updatedAssets: 0,
      updatedFindings: 0,
      skippedAssets: 0,
      skippedFindings: 0,
      failedAssets: 0,
      failedFindings: 0,
      assetTypes: {},
      findingTypes: {}
    };

    steps.forEach(step => {
      Object.values(step).forEach(stepData => {
        if (stepData && typeof stepData === 'object') {
          // Aggregate asset counts
          aggregated.createdAssets += stepData.created_assets || 0;
          aggregated.updatedAssets += stepData.updated_assets || 0;
          aggregated.skippedAssets += stepData.skipped_assets || 0;
          aggregated.failedAssets += stepData.failed_assets || 0;

          // Aggregate findings counts
          aggregated.createdFindings += stepData.created_findings || 0;
          aggregated.updatedFindings += stepData.updated_findings || 0;
          aggregated.skippedFindings += stepData.skipped_findings || 0;
          aggregated.failedFindings += stepData.failed_findings || 0;

          // Aggregate asset types
          if (stepData.asset_types) {
            Object.entries(stepData.asset_types).forEach(([assetType, counts]) => {
              if (!aggregated.assetTypes[assetType]) {
                aggregated.assetTypes[assetType] = {
                  total: 0,
                  created: 0,
                  updated: 0,
                  skipped: 0,
                  failed: 0
                };
              }
              aggregated.assetTypes[assetType].total += counts.total || 0;
              aggregated.assetTypes[assetType].created += counts.created || 0;
              aggregated.assetTypes[assetType].updated += counts.updated || 0;
              aggregated.assetTypes[assetType].skipped += counts.skipped || 0;
              aggregated.assetTypes[assetType].failed += counts.failed || 0;
            });
          }

          // Aggregate finding types
          if (stepData.finding_types) {
            Object.entries(stepData.finding_types).forEach(([findingType, counts]) => {
              if (!aggregated.findingTypes[findingType]) {
                aggregated.findingTypes[findingType] = {
                  total: 0,
                  created: 0,
                  updated: 0,
                  skipped: 0,
                  failed: 0
                };
              }
              aggregated.findingTypes[findingType].total += counts.total || 0;
              aggregated.findingTypes[findingType].created += counts.created || 0;
              aggregated.findingTypes[findingType].updated += counts.updated || 0;
              aggregated.findingTypes[findingType].skipped += counts.skipped || 0;
              aggregated.findingTypes[findingType].failed += counts.failed || 0;
            });
          }
        }
      });
    });

    // Calculate totals as sum of all individual counts
    aggregated.totalAssets = aggregated.createdAssets + aggregated.updatedAssets + aggregated.skippedAssets + aggregated.failedAssets;
    aggregated.totalFindings = aggregated.createdFindings + aggregated.updatedFindings + aggregated.skippedFindings + aggregated.failedFindings;

    return aggregated;
  };

  const renderAggregatedOverview = (aggregated) => {
    if (aggregated.totalAssets === 0 && aggregated.totalFindings === 0) {
      return (
        <div className="text-center text-muted py-3">
          <p className="mb-0">No assets or findings processed yet</p>
        </div>
      );
    }

    return (
      <div>
        {/* Summary Cards */}
        <Row className="mb-4">
          <Col md={6}>
            <div className="bg-light p-3 rounded border">
              <div className="d-flex align-items-center mb-2">
                <span className="me-2 fs-4">📦</span>
                <strong>Total Assets</strong>
              </div>
              <div className="d-flex flex-wrap gap-1">
                <Badge bg="primary" className="fs-6">{aggregated.totalAssets}</Badge>
                {aggregated.createdAssets > 0 && (
                  <Badge bg="success" title={`Created: ${aggregated.createdAssets}`}>
                    + {aggregated.createdAssets}
                  </Badge>
                )}
                {aggregated.updatedAssets > 0 && (
                  <Badge bg="info" title={`Updated: ${aggregated.updatedAssets}`}>
                    ↻ {aggregated.updatedAssets}
                  </Badge>
                )}
                {aggregated.skippedAssets > 0 && (
                  <Badge bg="warning" title={`Skipped: ${aggregated.skippedAssets}`}>
                    ⏭️ {aggregated.skippedAssets}
                  </Badge>
                )}
                {aggregated.failedAssets > 0 && (
                  <Badge bg="danger" title={`Failed: ${aggregated.failedAssets}`}>
                    ✗ {aggregated.failedAssets}
                  </Badge>
                )}
              </div>
            </div>
          </Col>
          <Col md={6}>
            <div className="bg-light p-3 rounded border">
              <div className="d-flex align-items-center mb-2">
                <span className="me-2 fs-4">🔍</span>
                <strong>Total Findings</strong>
              </div>
              <div className="d-flex flex-wrap gap-1">
                <Badge bg="warning" className="fs-6">{aggregated.totalFindings}</Badge>
                {aggregated.createdFindings > 0 && (
                  <Badge bg="success" title={`Created: ${aggregated.createdFindings}`}>
                    + {aggregated.createdFindings}
                  </Badge>
                )}
                {aggregated.updatedFindings > 0 && (
                  <Badge bg="info" title={`Updated: ${aggregated.updatedFindings}`}>
                    ↻ {aggregated.updatedFindings}
                  </Badge>
                )}
                {aggregated.skippedFindings > 0 && (
                  <Badge bg="warning" title={`Skipped: ${aggregated.skippedFindings}`}>
                    ⏭️ {aggregated.skippedFindings}
                  </Badge>
                )}
                {aggregated.failedFindings > 0 && (
                  <Badge bg="danger" title={`Failed: ${aggregated.failedFindings}`}>
                    ✗ {aggregated.failedFindings}
                  </Badge>
                )}
              </div>
            </div>
          </Col>
        </Row>

        {/* Asset Types Breakdown */}
        {Object.keys(aggregated.assetTypes).length > 0 && (
          <div className="mb-4">
            <h6 className="fw-bold text-primary mb-3">📦 Asset Types Summary</h6>
            <Row>
              {Object.entries(aggregated.assetTypes).map(([assetType, counts]) => (
                <Col md={6} lg={4} key={assetType} className="mb-3">
                  <div className="bg-light p-3 rounded border">
                    <div className="d-flex align-items-center mb-2">
                      <Badge bg="light" text="dark" className="me-2">
                        {assetType}
                      </Badge>
                      <strong>{counts.total}</strong>
                    </div>
                    <div className="d-flex flex-wrap gap-1">
                      {counts.created > 0 && (
                        <Badge bg="success" title={`Created: ${counts.created}`}>
                          + {counts.created}
                        </Badge>
                      )}
                      {counts.updated > 0 && (
                        <Badge bg="info" title={`Updated: ${counts.updated}`}>
                          ↻ {counts.updated}
                        </Badge>
                      )}
                      {counts.skipped > 0 && (
                        <Badge bg="warning" title={`Skipped: ${counts.skipped}`}>
                          ⏭️ {counts.skipped}
                        </Badge>
                      )}
                      {counts.failed > 0 && (
                        <Badge bg="danger" title={`Failed: ${counts.failed}`}>
                          ✗ {counts.failed}
                        </Badge>
                      )}
                    </div>
                  </div>
                </Col>
              ))}
            </Row>
          </div>
        )}

        {/* Finding Types Breakdown */}
        {Object.keys(aggregated.findingTypes).length > 0 && (
          <div>
            <h6 className="fw-bold text-warning mb-3">🔍 Finding Types Summary</h6>
            <Row>
              {Object.entries(aggregated.findingTypes).map(([findingType, counts]) => (
                <Col md={6} lg={4} key={findingType} className="mb-3">
                  <div className="bg-light p-3 rounded border">
                    <div className="d-flex align-items-center mb-2">
                      <Badge bg="warning" text="dark" className="me-2">
                        {findingType}
                      </Badge>
                      <strong>{counts.total}</strong>
                    </div>
                    <div className="d-flex flex-wrap gap-1">
                      {counts.created > 0 && (
                        <Badge bg="success" title={`Created: ${counts.created}`}>
                          + {counts.created}
                        </Badge>
                      )}
                      {counts.updated > 0 && (
                        <Badge bg="info" title={`Updated: ${counts.updated}`}>
                          ↻ {counts.updated}
                        </Badge>
                      )}
                      {counts.skipped > 0 && (
                        <Badge bg="warning" title={`Skipped: ${counts.skipped}`}>
                          ⏭️ {counts.skipped}
                        </Badge>
                      )}
                      {counts.failed > 0 && (
                        <Badge bg="danger" title={`Failed: ${counts.failed}`}>
                          ✗ {counts.failed}
                        </Badge>
                      )}
                    </div>
                  </div>
                </Col>
              ))}
            </Row>
          </div>
        )}
      </div>
    );
  };


  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading workflow details...</p>
        </div>
      </Container>
    );
  }

  if (error) {
    return (
      <Container fluid className="p-4">
        <Alert variant="danger">
          {error}
        </Alert>
        <Button as={Link} to="/workflows/status" variant="secondary">
          ← Back to Workflow Status
        </Button>
      </Container>
    );
  }

  const currentStatus = logs?.result || workflow?.status;

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <h1>📄 Workflow Details</h1>
            <ButtonGroup>
              <Button as={Link} to="/workflows/status" variant="outline-secondary">
                ← Back to Status List
              </Button>
              {canStopWorkflow(currentStatus) && (
                <Button
                  variant="outline-danger"
                  onClick={handleStopWorkflow}
                  disabled={stopping}
                >
                  {stopping ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-1" />
                      Stopping...
                    </>
                  ) : (
                    '⏹️ Stop Workflow'
                  )}
                </Button>
              )}
            </ButtonGroup>
          </div>
        </Col>
      </Row>

      {/* Workflow Overview */}
      <Row className="mb-4">
        <Col>
          <Card>
            <Card.Header>
              <h5 className="mb-0">Workflow Overview</h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={6}>
                  <p><strong>Workflow ID:</strong> <code>{workflowId}</code></p>
                  <p><strong>Program:</strong> <Badge bg="primary">{logs?.program_name || 'Unknown'}</Badge></p>
                  <p><strong>Status:</strong> <Badge bg={getStatusBadge(currentStatus)}>{currentStatus || 'unknown'}</Badge></p>
                </Col>
                <Col md={6}>
                  <p><strong>Started:</strong> {formatDateWithLabel(logs?.started_at, 'started')}</p>
                  <p><strong>Completed:</strong> {formatDateWithLabel(logs?.completed_at, 'updated')}</p>
                  <p><strong>Duration:</strong> {formatDurationWithStatus(logs?.started_at, logs?.completed_at, currentStatus)}</p>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Aggregated Assets and Findings Overview */}
      <Row className="mb-4">
        <Col>
          <Card>
            <Card.Header>
              <h5 className="mb-0">📊 All Assets & Findings Summary</h5>
            </Card.Header>
            <Card.Body>
              {renderAggregatedOverview(aggregateAllAssetsAndFindings(logs?.workflow_steps))}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Workflow Steps
      <Row className="mb-4">
        <Col>
          <Card>
            <Card.Header>
              <h5 className="mb-0">Workflow Steps</h5>
            </Card.Header>
            <Card.Body>
              {renderWorkflowSteps(logs?.workflow_steps)}
            </Card.Body>
          </Card>
        </Col>
      </Row> */}

      {/* Execution Output */}
      {workflow?.output && (
        <Row className="mb-4">
          <Col>
            <Card>
              <Card.Header>
                <h5 className="mb-0">Execution Output</h5>
              </Card.Header>
              <Card.Body>
                <pre style={{ backgroundColor: 'var(--bs-pre-bg)', color: 'var(--bs-pre-color)', padding: '1rem', borderRadius: '0.375rem', fontSize: '0.875rem' }}>
                  {workflow.output}
                </pre>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Enhanced Workflow Logs */}
      <Row>
        <Col>
          <Card>
            <Card.Header>
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">📋 Workflow Logs & Details</h5>
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={() => setShowRawData(!showRawData)}
                >
                  {showRawData ? '👁️ Hide Raw Data' : '🔍 Show Raw Data'}
                </Button>
              </div>
            </Card.Header>
            <Card.Body>
              {renderWorkflowLogs(logs)}
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
          <div className="card border">
            <div className="card-body">
              <strong>Workflow ID:</strong> <code>{workflowId}</code><br />
              <strong>Program:</strong> {logs?.program_name || 'Unknown'}<br />
              <strong>Status:</strong> <Badge bg={getStatusBadge(currentStatus)}>{currentStatus || 'unknown'}</Badge><br />
              <strong>Started:</strong> {formatDate(logs?.created_at, 'started')}
            </div>
          </div>
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

export default WorkflowStatusDetail;