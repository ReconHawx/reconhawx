import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Container, Row, Col, Card, Button, Badge, Table, Alert, Modal, Tabs, Tab, Form } from 'react-bootstrap';
import { useParams, useNavigate } from 'react-router-dom';
import { scheduledJobsAPI, workflowAPI, programAPI } from '../../services/api';
import { formatDate, formatRelativeTime } from '../../utils/dateUtils';
import VariableInput from '../../components/VariableInput';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

const ScheduledJobDetail = () => {
  const { jobId } = useParams();
  const navigate = useNavigate();

  const [job, setJob] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState({});
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [isEditing, setIsEditing] = useState(false);
  const [editFormData, setEditFormData] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState(null);

  // Workflow variables state
  const [workflowVariables, setWorkflowVariables] = useState({});
  const [variableValues, setVariableValues] = useState({});
  const [variableErrors, setVariableErrors] = useState({});

  /** Resolved workflow definition name for overview Job Configuration (workflow jobs only). */
  const [overviewWorkflowName, setOverviewWorkflowName] = useState(null);
  const [overviewWorkflowNameLoading, setOverviewWorkflowNameLoading] = useState(false);

  usePageTitle(formatPageTitle(job?.name, 'Scheduled Job'));

  const loadJobDetails = useCallback(async () => {
    try {
      setLoading(true);
      const response = await scheduledJobsAPI.getById(jobId);
      setJob(response);
      setError(null);
    } catch (err) {
      console.error('Error loading job details:', err);
      setError('Failed to load job details');
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  const loadExecutionHistory = useCallback(async () => {
    try {
      const response = await scheduledJobsAPI.getExecutionHistory(jobId, 50, 0);
      setExecutions(response || []);
    } catch (err) {
      console.error('Error loading execution history:', err);
    }
  }, [jobId]);

  // Calculate execution statistics from execution history
  const getExecutionStats = () => {
    if (!executions || executions.length === 0) {
      return { total: 0, successful: 0, failed: 0 };
    }
    
    const total = executions.length;
    const successful = executions.filter(exec => exec.status === 'completed').length;
    const failed = executions.filter(exec => exec.status === 'failed').length;
    
    return { total, successful, failed };
  };

  const loadProgramsForEdit = useCallback(async () => {
    try {
      const res = await programAPI.getAll();
      const withPerms = res.programs_with_permissions;
      const nameList = res.programs;
      if (Array.isArray(withPerms) && withPerms.length > 0) {
        setPrograms(withPerms);
      } else if (Array.isArray(nameList) && nameList.length > 0) {
        setPrograms(nameList.map((name) => ({ name, permission_level: 'analyst' })));
      } else {
        setPrograms([]);
      }
    } catch (err) {
      console.error('Error loading programs for edit:', err);
    }
  }, []);

  const loadWorkflowsForEdit = useCallback(async () => {
    try {
      const res = await workflowAPI.getWorkflows();
      const list = res?.workflows ?? res?.items ?? [];
      setWorkflows(Array.isArray(list) ? list : []);
    } catch (err) {
      console.error('Error loading workflows for edit:', err);
      setWorkflows([]);
    }
  }, []);

  const loadEditData = async () => {
    await loadProgramsForEdit();
    await loadWorkflowsForEdit();
  };

  useEffect(() => {
    loadJobDetails();
    loadExecutionHistory();
    if (isEditing) {
      loadEditData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadEditData is mount/edit-guarded here
  }, [jobId, isEditing, loadJobDetails, loadExecutionHistory]);

  useEffect(() => {
    if (!job || job.job_type !== 'workflow') {
      setOverviewWorkflowName(null);
      setOverviewWorkflowNameLoading(false);
      return;
    }
    const wid = job.job_data?.workflow_id;
    if (!wid) {
      setOverviewWorkflowName(null);
      setOverviewWorkflowNameLoading(false);
      return;
    }
    let cancelled = false;
    setOverviewWorkflowName(null);
    setOverviewWorkflowNameLoading(true);
    workflowAPI
      .getWorkflow(wid)
      .then((wf) => {
        if (!cancelled) {
          const n = wf?.name && String(wf.name).trim();
          setOverviewWorkflowName(n || null);
        }
      })
      .catch(() => {
        if (!cancelled) setOverviewWorkflowName(null);
      })
      .finally(() => {
        if (!cancelled) setOverviewWorkflowNameLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- granular job fields sufficient; full job object changes often
  }, [job?.schedule_id, job?.job_type, job?.job_data?.workflow_id]);

  /** Workflow definitions from API plus the job's current workflow_id if missing from the list. */
  const workflowSelectOptions = useMemo(() => {
    const list = Array.isArray(workflows) ? workflows.map((w) => ({ ...w })) : [];
    const currentId = editFormData?.job_data?.workflow_id;
    if (currentId && !list.some((w) => w && w.id === currentId)) {
      list.push({
        id: currentId,
        name: `Current workflow (${String(currentId).slice(0, 8)}…)`,
        program_name: null,
        variables: {},
      });
    }
    return list.sort((a, b) =>
      (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }),
    );
  }, [workflows, editFormData?.job_data?.workflow_id]);

  /** Programs from API plus any names already selected on the job so checkboxes always render. */
  const workflowProgramOptions = useMemo(() => {
    const byName = new Map();
    for (const p of programs) {
      if (p && p.name) byName.set(p.name, p);
    }
    const selected = editFormData?.workflow_program_names || [];
    for (const n of selected) {
      const name = typeof n === 'string' ? n.trim() : '';
      if (name && !byName.has(name)) {
        byName.set(name, { name });
      }
    }
    return Array.from(byName.values()).sort((a, b) =>
      (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }),
    );
  }, [programs, editFormData?.workflow_program_names]);

  const handleToggleStatus = async () => {
    try {
      setActionLoading(prev => ({ ...prev, toggle: true }));
      if (job.schedule?.enabled) {
        await scheduledJobsAPI.disable(job.schedule_id);
      } else {
        await scheduledJobsAPI.enable(job.schedule_id);
      }
      await loadJobDetails();
    } catch (err) {
      console.error('Error toggling job status:', err);
      setError('Failed to update job status');
    } finally {
      setActionLoading(prev => ({ ...prev, toggle: false }));
    }
  };

  const handleRunNow = async () => {
    try {
      setActionLoading(prev => ({ ...prev, runNow: true }));
      await scheduledJobsAPI.runNow(job.schedule_id);
      await loadJobDetails();
      await loadExecutionHistory();
    } catch (err) {
      console.error('Error running job:', err);
      setError('Failed to run job');
    } finally {
      setActionLoading(prev => ({ ...prev, runNow: false }));
    }
  };

  const handleDelete = async () => {
    try {
      setActionLoading(prev => ({ ...prev, delete: true }));
      await scheduledJobsAPI.delete(job.schedule_id);
      navigate('/scheduled-jobs');
    } catch (err) {
      console.error('Error deleting job:', err);
      setError('Failed to delete job');
    } finally {
      setActionLoading(prev => ({ ...prev, delete: false }));
    }
  };

  const handleEdit = async () => {
    // Deep clone the schedule data to avoid modifying the original
    const scheduleData = JSON.parse(JSON.stringify(job.schedule));

    // Ensure cron_schedule is properly structured for editing
    if (scheduleData.schedule_type === 'cron' && scheduleData.cron_schedule) {
      // Make sure all cron fields are present with actual values or empty strings
      scheduleData.cron_schedule = {
        minute: scheduleData.cron_schedule.minute || '',
        hour: scheduleData.cron_schedule.hour || '',
        day_of_month: scheduleData.cron_schedule.day_of_month || '',
        month: scheduleData.cron_schedule.month || '',
        day_of_week: scheduleData.cron_schedule.day_of_week || ''
      };
    }

    const formData = {
      job_type: job.job_type,
      name: job.name,
      description: job.description || '',
      program_name: job.program_name || '',
      workflow_program_names: (
        job.program_names && job.program_names.length > 0
          ? [...job.program_names]
          : job.program_name
            ? [job.program_name]
            : []
      )
        .map((n) => (typeof n === 'string' ? n.trim() : n))
        .filter(Boolean),
      schedule: scheduleData,
      job_data: { ...job.job_data },
      tags: job.tags || []
    };

    setEditFormData(formData);
    setIsEditing(true);
    setEditError(null);

    // If this is a workflow job, load workflow variables
    if (job.job_type === 'workflow' && job.job_data.workflow_id) {
      try {
        const fullWorkflow = await workflowAPI.getWorkflow(job.job_data.workflow_id);

        // Handle both old format (definition wrapper) and new format (separate fields)
        let variables = fullWorkflow.variables || {};

        // If using old format with definition wrapper
        if (fullWorkflow.definition) {
          variables = fullWorkflow.definition.variables || variables;
        }

        // Ensure variables are properly structured
        if (variables && typeof variables === 'object') {
          // If variables is an array, convert it to object format
          if (Array.isArray(variables)) {
            const convertedVariables = {};
            variables.forEach((varDef, index) => {
              if (typeof varDef === 'string') {
                convertedVariables[varDef] = { value: '', description: `Variable ${index + 1}` };
              } else if (varDef && typeof varDef === 'object') {
                convertedVariables[varDef.name || `var_${index}`] = varDef;
              }
            });
            variables = convertedVariables;
          }
        }

        if (variables && Object.keys(variables).length > 0) {
          setWorkflowVariables(variables);

          // Set current values from job data
          const currentValues = job.job_data.workflow_variables || {};
          setVariableValues(currentValues);
        }
      } catch (err) {
        console.error('Failed to load workflow variables for editing:', err);
      }
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditFormData(null);
    setEditError(null);
    setWorkflowVariables({});
    setVariableValues({});
    setVariableErrors({});
  };

  const handleSaveEdit = async () => {
    try {
      setEditLoading(true);
      setEditError(null);

      // Validate workflow variables if this is a workflow job
      if (editFormData.job_type === 'workflow' && Object.keys(workflowVariables).length > 0) {
        const missingVariables = [];
        Object.entries(workflowVariables).forEach(([varName, varDef]) => {
          if (varDef.required && (!variableValues[varName] || variableValues[varName] === '')) {
            missingVariables.push(varName);
          }
        });

        if (missingVariables.length > 0) {
          setEditError(`Please fill in all required workflow variables: ${missingVariables.join(', ')}`);
          return;
        }
      }

      if (
        editFormData.job_type === 'workflow' &&
        (!editFormData.workflow_program_names ||
          editFormData.workflow_program_names.length === 0)
      ) {
        setEditError('Select at least one program for this workflow schedule');
        return;
      }

      if (
        editFormData.job_type === 'gather_api_findings' &&
        (editFormData.job_data.api_vendor || 'threatstream') === 'threatstream'
      ) {
        const q = (editFormData.job_data.custom_query || '').trim();
        if (!q) {
          setEditError(
            'ThreatStream gather jobs require a non-empty ThreatStream intelligence query (custom_query).'
          );
          return;
        }
      }

      const updatePayload = {
        name: editFormData.name,
        description: editFormData.description,
        schedule: editFormData.schedule,
        tags: editFormData.tags,
        job_data: editFormData.job_data,
        enabled: editFormData.schedule?.enabled,
      };
      if (
        editFormData.job_type === 'workflow' &&
        editFormData.workflow_program_names &&
        editFormData.workflow_program_names.length > 0
      ) {
        updatePayload.program_names = editFormData.workflow_program_names;
      }

      await scheduledJobsAPI.update(jobId, updatePayload);
      await loadJobDetails();
      setIsEditing(false);
      setEditFormData(null);
      setWorkflowVariables({});
      setVariableValues({});
      setVariableErrors({});
    } catch (err) {
      console.error('Error updating job:', err);
      setEditError('Failed to update job: ' + err.message);
    } finally {
      setEditLoading(false);
    }
  };

  const handleEditInputChange = (field, value) => {
    if (field.includes('.')) {
      const parts = field.split('.');
      if (parts.length === 2) {
        // Handle one level of nesting: schedule.schedule_type
        const [parent, child] = parts;
        setEditFormData(prev => ({
          ...prev,
          [parent]: {
            ...prev[parent],
            [child]: value
          }
        }));
      } else if (parts.length === 3) {
        // Handle two levels of nesting: schedule.cron_schedule.minute
        const [parent, child, grandchild] = parts;
        setEditFormData(prev => ({
          ...prev,
          [parent]: {
            ...prev[parent],
            [child]: {
              ...prev[parent]?.[child],
              [grandchild]: value
            }
          }
        }));
      }
    } else {
      setEditFormData(prev => ({
        ...prev,
        [field]: value
      }));
    }
  };

  const handleWorkflowChange = async (workflowId) => {
    handleEditInputChange('job_data.workflow_id', workflowId);

    if (workflowId) {
      try {
        // Load workflow details to get variables
        const fullWorkflow = await workflowAPI.getWorkflow(workflowId);

        // Handle both old format (definition wrapper) and new format (separate fields)
        let variables = fullWorkflow.variables || {};

        // If using old format with definition wrapper
        if (fullWorkflow.definition) {
          variables = fullWorkflow.definition.variables || variables;
        }

        // Ensure variables are properly structured
        if (variables && typeof variables === 'object') {
          // If variables is an array, convert it to object format
          if (Array.isArray(variables)) {
            const convertedVariables = {};
            variables.forEach((varDef, index) => {
              if (typeof varDef === 'string') {
                convertedVariables[varDef] = { value: '', description: `Variable ${index + 1}` };
              } else if (varDef && typeof varDef === 'object') {
                convertedVariables[varDef.name || `var_${index}`] = varDef;
              }
            });
            variables = convertedVariables;
          }
        }

        if (variables && Object.keys(variables).length > 0) {
          setWorkflowVariables(variables);

          // Set current values for variables from existing job data
          const currentValues = editFormData.job_data.workflow_variables || {};
          const newValues = {};
          Object.entries(variables).forEach(([varName, varDef]) => {
            newValues[varName] = currentValues[varName] || varDef.value || varDef.default || '';
          });
          setVariableValues(newValues);

          // Update job_data with workflow variables
          handleEditInputChange('job_data.workflow_variables', newValues);
        } else {
          setWorkflowVariables({});
          setVariableValues({});
          handleEditInputChange('job_data.workflow_variables', {});
        }
        setVariableErrors({});
      } catch (err) {
        console.error('Failed to load workflow variables:', err);
        setWorkflowVariables({});
        setVariableValues({});
        handleEditInputChange('job_data.workflow_variables', {});
      }
    } else {
      setWorkflowVariables({});
      setVariableValues({});
      handleEditInputChange('job_data.workflow_variables', {});
    }
  };

  const handleVariableChange = (newValues) => {
    setVariableValues(newValues);
    handleEditInputChange('job_data.workflow_variables', newValues);
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
      'gather_api_findings': 'Gather API Findings',
      'sync_recordedfuture_data': 'Sync RecordedFuture Data',
      'workflow': 'Workflow'
    };
    return labels[jobType] || jobType;
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

  const formatDuration = (seconds) => {
    if (!seconds) return '-';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  const renderJobDataDisplay = (job) => {
    if (!job.job_data || Object.keys(job.job_data).length === 0) {
      return (
        <div className="text-muted">
          <em>No job configuration data</em>
        </div>
      );
    }

    const jobData = job.job_data;

    switch (job.job_type) {
      case 'dummy_batch':
        return (
          <div className="bg-light p-3 rounded">
            <Table size="sm" className="mb-0">
              <tbody>
                <tr>
                  <td><strong>Items Count:</strong></td>
                  <td>{jobData.items?.length || 0} items</td>
                </tr>
                <tr>
                  <td style={{ verticalAlign: 'top' }}><strong>Items:</strong></td>
                  <td>
                    {jobData.items?.length > 0 ? (
                      <div className="text-break">
                        {jobData.items.slice(0, 5).map((item, index) => (
                          <span key={index} className="d-block">
                            <code className="small">{item}</code>
                          </span>
                        ))}
                        {jobData.items.length > 5 && (
                          <span className="text-muted small">
                            ... and {jobData.items.length - 5} more
                          </span>
                        )}
                      </div>
                    ) : (
                      <em className="text-muted">No items</em>
                    )}
                  </td>
                </tr>
              </tbody>
            </Table>
          </div>
        );

      case 'typosquat_batch':
        return (
          <div className="bg-light p-3 rounded">
            <Table size="sm" className="mb-0">
              <tbody>
                <tr>
                  <td><strong>Domains Count:</strong></td>
                  <td>{jobData.domains?.length || 0} domains</td>
                </tr>
                <tr>
                  <td style={{ verticalAlign: 'top' }}><strong>Domains:</strong></td>
                  <td>
                    {jobData.domains?.length > 0 ? (
                      <div className="text-break">
                        {jobData.domains.slice(0, 10).map((domain, index) => (
                          <span key={index} className="d-block">
                            <code className="small">{domain}</code>
                          </span>
                        ))}
                        {jobData.domains.length > 10 && (
                          <span className="text-muted small">
                            ... and {jobData.domains.length - 10} more
                          </span>
                        )}
                      </div>
                    ) : (
                      <em className="text-muted">No domains</em>
                    )}
                  </td>
                </tr>
              </tbody>
            </Table>
          </div>
        );

      case 'phishlabs_batch':
      case 'ai_analysis_batch':
        return (
          <div className="bg-light p-3 rounded">
            <Table size="sm" className="mb-0">
              <tbody>
                <tr>
                  <td><strong>Finding IDs Count:</strong></td>
                  <td>{jobData.finding_ids?.length || 0} findings</td>
                </tr>
                {jobData.force && (
                  <tr>
                    <td><strong>Force Re-analyze:</strong></td>
                    <td><Badge bg="warning">Yes</Badge></td>
                  </tr>
                )}
                <tr>
                  <td style={{ verticalAlign: 'top' }}><strong>Finding IDs:</strong></td>
                  <td>
                    {jobData.finding_ids?.length > 0 ? (
                      <div className="text-break">
                        {jobData.finding_ids.slice(0, 10).map((id, index) => (
                          <span key={index} className="d-block">
                            <code className="small">{id}</code>
                          </span>
                        ))}
                        {jobData.finding_ids.length > 10 && (
                          <span className="text-muted small">
                            ... and {jobData.finding_ids.length - 10} more
                          </span>
                        )}
                      </div>
                    ) : (
                      <em className="text-muted">No finding IDs</em>
                    )}
                  </td>
                </tr>
              </tbody>
            </Table>
          </div>
        );

      case 'gather_api_findings':
        return (
          <div className="bg-light p-3 rounded">
            <Table size="sm" className="mb-0">
              <tbody>
                <tr>
                  <td><strong>API Vendor:</strong></td>
                  <td>
                    <Badge bg={jobData.api_vendor === 'threatstream' ? 'primary' : 'info'}>
                      {jobData.api_vendor === 'threatstream' ? 'ThreatStream' :
                       jobData.api_vendor === 'recordedfuture' ? 'RecordedFuture' :
                       jobData.api_vendor || 'ThreatStream'}
                    </Badge>
                  </td>
                </tr>
                <tr>
                  <td><strong>Date Range:</strong></td>
                  <td>
                    {jobData.date_range_hours === 0 ? (
                      <span>
                        <Badge bg="warning" className="me-2">No Limit</Badge>
                        All findings (no date filtering)
                      </span>
                    ) : (
                      `${jobData.date_range_hours || 24} hours`
                    )}
                  </td>
                </tr>
                {jobData.custom_query && (
                  <tr>
                    <td style={{ verticalAlign: 'top' }}><strong>Custom Query:</strong></td>
                    <td>
                      <pre className="bg-white p-2 rounded border small mb-0" style={{ fontSize: '0.8rem', maxHeight: '200px', overflow: 'auto' }}>
                        {jobData.custom_query}
                      </pre>
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        );

      case 'sync_recordedfuture_data':
        return (
          <div className="bg-light p-3 rounded">
            <Table size="sm" className="mb-0">
              <tbody>
                <tr>
                  <td><strong>Batch Size:</strong></td>
                  <td>{jobData.sync_options?.batch_size || 50} findings per batch</td>
                </tr>
                <tr>
                  <td><strong>Max Age:</strong></td>
                  <td>{jobData.sync_options?.max_age_days || 30} days</td>
                </tr>
                <tr>
                  <td><strong>Include Screenshots:</strong></td>
                  <td>
                    <Badge bg={jobData.sync_options?.include_screenshots !== false ? 'success' : 'secondary'}>
                      {jobData.sync_options?.include_screenshots !== false ? 'Yes' : 'No'}
                    </Badge>
                  </td>
                </tr>
              </tbody>
            </Table>
          </div>
        );

      case 'workflow':
        return (
          <div className="bg-light p-3 rounded">
            <Table size="sm" className="mb-0">
              <tbody>
                <tr>
                  <td><strong>Workflow:</strong></td>
                  <td>
                    {!jobData.workflow_id ? (
                      <span className="text-muted">—</span>
                    ) : (
                      <>
                        {overviewWorkflowNameLoading && (
                          <span className="text-muted">Loading…</span>
                        )}
                        {!overviewWorkflowNameLoading && overviewWorkflowName && (
                          <span>{overviewWorkflowName}</span>
                        )}
                        {!overviewWorkflowNameLoading && !overviewWorkflowName && (
                          <span className="text-muted">Not available</span>
                        )}
                        {' '}
                        <code className="small">({jobData.workflow_id})</code>
                      </>
                    )}
                  </td>
                </tr>
                {jobData.workflow_variables && Object.keys(jobData.workflow_variables).length > 0 && (
                  <tr>
                    <td style={{ verticalAlign: 'top' }}><strong>Variables:</strong></td>
                    <td>
                      <Table size="sm" className="mb-0 border">
                        <thead className="table-secondary">
                          <tr>
                            <th className="small">Variable</th>
                            <th className="small">Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(jobData.workflow_variables).map(([key, value], index) => (
                            <tr key={index}>
                              <td className="small"><code>{key}</code></td>
                              <td className="small text-break">
                                <code style={{ backgroundColor: 'rgba(0,123,255,0.1)', padding: '2px 4px', borderRadius: '3px' }}>
                                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                </code>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        );

      default:
        // Fallback for unknown job types - show raw JSON
        return (
          <div className="bg-light p-3 rounded">
            <div className="mb-2">
              <Badge bg="secondary">Raw Configuration</Badge>
            </div>
            <pre className="bg-white p-2 rounded border small mb-0" style={{ fontSize: '0.8rem', maxHeight: '300px', overflow: 'auto' }}>
              {JSON.stringify(jobData, null, 2)}
            </pre>
          </div>
        );
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

  if (!job) {
    return (
      <Container fluid>
        <Alert variant="danger">
          Job not found
        </Alert>
      </Container>
    );
  }

  return (
    <Container fluid>
      <Row className="mb-3">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <div>
              <h2>⏰ {job.name}</h2>
              {job.description && (
                <p className="text-muted mb-0">{job.description}</p>
              )}
            </div>
            <div className="d-flex gap-2">
              {!isEditing ? (
                <>
                  <Button 
                    variant="outline-secondary" 
                    onClick={() => navigate('/scheduled-jobs')}
                  >
                    ← Back to Jobs
                  </Button>
                  <Button 
                    variant="outline-primary"
                    onClick={handleEdit}
                  >
                    ✏️ Edit
                  </Button>
                </>
              ) : (
                <>
                  <Button 
                    variant="outline-secondary" 
                    onClick={handleCancelEdit}
                  >
                    ✕ Cancel
                  </Button>
                  <Button 
                    variant="success"
                    onClick={handleSaveEdit}
                    disabled={editLoading}
                  >
                    {editLoading ? 'Saving...' : '💾 Save Changes'}
                  </Button>
                </>
              )}
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

      {editError && (
        <Row className="mb-3">
          <Col>
            <Alert variant="danger" onClose={() => setEditError(null)} dismissible>
              {editError}
            </Alert>
          </Col>
        </Row>
      )}

      <Row>
        <Col lg={8}>
          <Tabs activeKey={activeTab} onSelect={(k) => setActiveTab(k)} className="mb-3">
            <Tab eventKey="overview" title="Overview">
              <Card>
                <Card.Body>
                  <Row>
                    <Col md={6}>
                      <h6>Job Information</h6>
                      <Table borderless size="sm">
                        <tbody>
                          <tr>
                            <td><strong>Job Type:</strong></td>
                            <td>{getJobTypeLabel(job.job_type)}</td>
                          </tr>
                          <tr>
                            <td><strong>Programs:</strong></td>
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
                              ) && <span className="text-muted">N/A</span>}
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Status:</strong></td>
                            <td>
                              <div className="d-flex align-items-center gap-2">
                                {getStatusBadge(job.status)}
                                {job.schedule?.enabled ? (
                                  <Badge bg="success">Enabled</Badge>
                                ) : (
                                  <Badge bg="secondary">Disabled</Badge>
                                )}
                              </div>
                            </td>
                          </tr>
                          <tr>
                            <td><strong>Schedule:</strong></td>
                            <td>{getScheduleDescription(job.schedule, job.last_run, job.status)}</td>
                          </tr>
                          <tr>
                            <td><strong>Next Run:</strong></td>
                            <td>
                              {job.next_run ? (
                                formatDate(job.next_run)
                              ) : (
                                <span className="text-muted">-</span>
                              )}
                            </td>
                          </tr>
                        </tbody>
                      </Table>
                    </Col>
                    <Col md={6}>
                      <h6>Execution Statistics</h6>
                      <Table borderless size="sm">
                        <tbody>
                          <tr>
                            <td><strong>Total Executions:</strong></td>
                            <td>{getExecutionStats().total}</td>
                          </tr>
                          <tr>
                            <td><strong>Successful:</strong></td>
                            <td className="text-success">{getExecutionStats().successful}</td>
                          </tr>
                          <tr>
                            <td><strong>Failed:</strong></td>
                            <td className="text-danger">{getExecutionStats().failed}</td>
                          </tr>
                          <tr>
                            <td><strong>Last Run:</strong></td>
                            <td>
                              {job.last_run ? (
                                formatRelativeTime(job.last_run)
                              ) : (
                                <span className="text-muted">Never</span>
                              )}
                            </td>
                          </tr>
                        </tbody>
                      </Table>
                    </Col>
                  </Row>

                  {/* Job Configuration Section */}
                  {job.job_data && Object.keys(job.job_data).length > 0 && (
                    <>
                      <hr />
                      <h6>Job Configuration</h6>
                      {renderJobDataDisplay(job)}
                    </>
                  )}
                </Card.Body>
              </Card>
            </Tab>

            <Tab eventKey="executions" title="Execution History">
              <Card>
                <Card.Body>
                  {executions.length === 0 ? (
                    <div className="text-center py-4">
                      <p className="text-muted">No execution history found</p>
                    </div>
                  ) : (
                    <Table responsive>
                      <thead>
                        <tr>
                          <th>Execution ID</th>
                          <th>Job ID</th>
                          <th>Status</th>
                          <th>Started</th>
                          <th>Completed</th>
                          <th>Duration</th>
                          <th>Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {executions.map((execution) => (
                          <tr key={execution.execution_id}>
                            <td>
                              <code className="small">{execution.execution_id.slice(0, 8)}...</code>
                            </td>
                            <td>
                              <code className="small">{execution.job_id}</code>
                            </td>
                            <td>{getStatusBadge(execution.status)}</td>
                            <td>
                              <small>{formatDate(execution.started_at)}</small>
                            </td>
                            <td>
                              {execution.completed_at ? (
                                <small>{formatDate(execution.completed_at)}</small>
                              ) : (
                                <span className="text-muted">-</span>
                              )}
                            </td>
                            <td>
                              <small>{formatDuration(execution.duration_seconds)}</small>
                            </td>
                            <td>
                              {execution.error_message ? (
                                <small className="text-danger">{execution.error_message}</small>
                              ) : (
                                <span className="text-muted">-</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  )}
                </Card.Body>
              </Card>
            </Tab>
          </Tabs>

          {/* Edit Form */}
          {isEditing && editFormData && (
            <Card className="mt-3">
              <Card.Header>
                <h5>✏️ Edit Scheduled Job</h5>
              </Card.Header>
              <Card.Body>
                <Form>
                  <Row>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>Job Name</Form.Label>
                        <Form.Control
                          type="text"
                          value={editFormData.name}
                          onChange={(e) => handleEditInputChange('name', e.target.value)}
                          placeholder="Enter job name"
                        />
                      </Form.Group>
                    </Col>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>Job Type</Form.Label>
                        <Form.Control
                          plaintext
                          readOnly
                          className="border rounded px-3 py-2 bg-light"
                          value={getJobTypeLabel(editFormData.job_type)}
                        />
                        <Form.Text className="text-muted">Job type cannot be changed after creation.</Form.Text>
                      </Form.Group>
                    </Col>
                  </Row>

                  <Form.Group className="mb-3">
                    <Form.Label>Description</Form.Label>
                    <Form.Control
                      as="textarea"
                      rows={2}
                      value={editFormData.description}
                      onChange={(e) => handleEditInputChange('description', e.target.value)}
                      placeholder="Enter job description"
                    />
                  </Form.Group>

                  {/* Job Type Specific Fields */}
                  {editFormData.job_type === 'dummy_batch' && (
                    <Form.Group className="mb-3">
                      <Form.Label>Items (one per line)</Form.Label>
                      <Form.Control
                        as="textarea"
                        rows={3}
                        value={editFormData.job_data.items?.join('\n') || ''}
                        onChange={(e) => handleEditInputChange('job_data.items', e.target.value.split('\n').filter(item => item.trim()))}
                        placeholder="test1&#10;test2&#10;test3"
                      />
                    </Form.Group>
                  )}

                  {editFormData.job_type === 'typosquat_batch' && (
                    <>
                      <Form.Group className="mb-3">
                        <Form.Label>Domains (one per line)</Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={3}
                          value={editFormData.job_data.domains?.join('\n') || ''}
                          onChange={(e) => handleEditInputChange('job_data.domains', e.target.value.split('\n').filter(domain => domain.trim()))}
                          placeholder="example.com&#10;test.com"
                        />
                      </Form.Group>
                    </>
                  )}

                  {(editFormData.job_type === 'phishlabs_batch' || editFormData.job_type === 'ai_analysis_batch') && (
                    <>
                      <Form.Group className="mb-3">
                        <Form.Label>Finding IDs (one per line)</Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={3}
                          value={editFormData.job_data.finding_ids?.join('\n') || ''}
                          onChange={(e) => handleEditInputChange('job_data.finding_ids', e.target.value.split('\n').filter(id => id.trim()))}
                          placeholder="finding1&#10;finding2&#10;finding3"
                        />
                      </Form.Group>
                      {editFormData.job_type === 'ai_analysis_batch' && (
                        <Form.Group className="mb-3">
                          <Form.Check
                            type="checkbox"
                            label="Force re-analyze (even if already analyzed)"
                            checked={editFormData.job_data.force || false}
                            onChange={(e) => handleEditInputChange('job_data.force', e.target.checked)}
                          />
                        </Form.Group>
                      )}
                    </>
                  )}

                  {editFormData.job_type === 'gather_api_findings' && (
                    <>
                      <Form.Group className="mb-3">
                        <Form.Label>API Vendor</Form.Label>
                        <Form.Select
                          value={editFormData.job_data.api_vendor || 'threatstream'}
                          onChange={(e) => handleEditInputChange('job_data.api_vendor', e.target.value)}
                        >
                          <option value="threatstream">ThreatStream</option>
                          <option value="recordedfuture">RecordedFuture</option>
                        </Form.Select>
                        <Form.Text className="text-muted">
                          Select which vendor API to use for gathering findings. Will use the program selected above.
                        </Form.Text>
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <Form.Label>Date Range (hours)</Form.Label>
                        <Form.Control
                          type="number"
                          min="0"
                          max="8760"
                          value={editFormData.job_data.date_range_hours ?? 24}
                          onChange={(e) => handleEditInputChange('job_data.date_range_hours', parseInt(e.target.value))}
                        />
                        <Form.Text className="text-muted">
                          Fetch findings updated within the last N hours (0-8760 hours). <strong>Set to 0 for no date filtering (all findings).</strong> Works with both ThreatStream and RecordedFuture APIs.
                        </Form.Text>
                      </Form.Group>
                      {(editFormData.job_data.api_vendor || 'threatstream') === 'threatstream' && (
                        <Form.Group className="mb-3">
                          <Form.Label>ThreatStream query (required)</Form.Label>
                          <Form.Control
                            as="textarea"
                            rows={3}
                            required
                            value={editFormData.job_data.custom_query || ''}
                            onChange={(e) => handleEditInputChange('job_data.custom_query', e.target.value)}
                            placeholder="(feed_name = &quot;Feed Name&quot; and (itype = mal_domain or itype = phish_domain) and (value contains myorganization or value contains mycompany))"
                          />
                          <Form.Text className="text-muted">
                            ThreatStream intelligence <code>q=</code> filter. Must not be empty. Examples:{' '}
                            <code>(feed_name = "Feed Name" and itype = mal_domain and (value contains myorganization))</code>
                          </Form.Text>
                        </Form.Group>
                      )}
                    </>
                  )}

                  {editFormData.job_type === 'sync_recordedfuture_data' && (
                    <>
                      <Form.Group className="mb-3">
                        <Form.Label>Batch Size</Form.Label>
                        <Form.Control
                          type="number"
                          min="10"
                          max="200"
                          value={editFormData.job_data.sync_options?.batch_size || 50}
                          onChange={(e) => {
                            const newSyncOptions = {
                              ...editFormData.job_data.sync_options,
                              batch_size: parseInt(e.target.value)
                            };
                            handleEditInputChange('job_data.sync_options', newSyncOptions);
                          }}
                        />
                        <Form.Text className="text-muted">
                          Number of findings to process in each batch (10-200)
                        </Form.Text>
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <Form.Label>Max Age (days)</Form.Label>
                        <Form.Control
                          type="number"
                          min="0"
                          max="365"
                          value={editFormData.job_data.sync_options?.max_age_days || 30}
                          onChange={(e) => {
                            const newSyncOptions = {
                              ...editFormData.job_data.sync_options,
                              max_age_days: parseInt(e.target.value)
                            };
                            handleEditInputChange('job_data.sync_options', newSyncOptions);
                          }}
                        />
                        <Form.Text className="text-muted">
                          Only sync findings that haven't been updated in this many days (0 for all)
                        </Form.Text>
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <Form.Check
                          type="checkbox"
                          id="include_screenshots_edit"
                          label="Include Screenshots"
                          checked={editFormData.job_data.sync_options?.include_screenshots !== false}
                          onChange={(e) => {
                            const newSyncOptions = {
                              ...editFormData.job_data.sync_options,
                              include_screenshots: e.target.checked
                            };
                            handleEditInputChange('job_data.sync_options', newSyncOptions);
                          }}
                        />
                        <Form.Text className="text-muted">
                          Whether to process screenshot data during sync
                        </Form.Text>
                      </Form.Group>
                    </>
                  )}

                  {editFormData.job_type === 'workflow' && (
                    <>
                      <Form.Group className="mb-3">
                        <Form.Label>Select Workflow</Form.Label>
                        <Form.Select
                          value={editFormData.job_data.workflow_id || ''}
                          onChange={(e) => {
                            const workflowId = e.target.value;
                            handleWorkflowChange(workflowId);

                            if (workflowId) {
                              const selectedWorkflow = workflowSelectOptions.find((w) => w.id === workflowId);
                              if (
                                selectedWorkflow &&
                                selectedWorkflow.program_name &&
                                (editFormData.workflow_program_names || []).length === 0
                              ) {
                                handleEditInputChange('workflow_program_names', [
                                  selectedWorkflow.program_name,
                                ]);
                                handleEditInputChange('program_name', selectedWorkflow.program_name);
                              }
                            }
                          }}
                        >
                          <option value="">Choose a workflow...</option>
                          {workflowSelectOptions.map((workflow) => (
                            <option key={workflow.id} value={workflow.id}>
                              {workflow.name} {workflow.program_name && `(${workflow.program_name})`}
                              {(workflow.variables && Object.keys(workflow.variables).length > 0) && ' 📝'}
                            </option>
                          ))}
                        </Form.Select>
                        <Form.Text className="text-muted">
                          Select a saved workflow to schedule
                        </Form.Text>
                      </Form.Group>

                      <Form.Group className="mb-3">
                        <Form.Label>Programs *</Form.Label>
                        <div
                          className="border rounded p-2 bg-light"
                          style={{ maxHeight: '200px', overflowY: 'auto' }}
                        >
                          {workflowProgramOptions.length === 0 && (
                            <span className="text-muted small">No programs to show.</span>
                          )}
                          {workflowProgramOptions.map((p) => (
                            <Form.Check
                              key={p.name}
                              type="checkbox"
                              id={`edit-workflow-program-${p.name}`}
                              label={p.name}
                              checked={(editFormData.workflow_program_names || []).includes(p.name)}
                              onChange={(e) => {
                                const current = editFormData.workflow_program_names || [];
                                const next = e.target.checked
                                  ? (current.includes(p.name) ? current : [...current, p.name])
                                  : current.filter((n) => n !== p.name);
                                handleEditInputChange('workflow_program_names', next);
                                handleEditInputChange('program_name', next.length > 0 ? next[0] : '');
                              }}
                              className="mb-1"
                            />
                          ))}
                        </div>
                        <Form.Text className="text-muted">
                          One workflow run is started per program on each schedule tick
                        </Form.Text>
                      </Form.Group>

                      {/* Workflow Variables Section */}
                      {Object.keys(workflowVariables).length > 0 && (
                        <div className="mt-3">
                          <h6>Workflow Variables</h6>
                          <Alert variant="info" className="mb-3">
                            This workflow contains variables that need to be configured. These values will be used for all scheduled executions.
                          </Alert>
                          <VariableInput
                            variables={workflowVariables}
                            values={variableValues}
                            onVariableChange={handleVariableChange}
                            errors={variableErrors}
                          />
                        </div>
                      )}
                    </>
                  )}

                  {/* Schedule Configuration */}
                  <hr />
                  <h6>Schedule Configuration</h6>
                  
                  <Row>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>Schedule Type</Form.Label>
                        <Form.Select
                          value={editFormData.schedule.schedule_type}
                          onChange={(e) => handleEditInputChange('schedule.schedule_type', e.target.value)}
                        >
                          <option value="once">Once</option>
                          <option value="recurring">Recurring</option>
                          <option value="cron">Cron</option>
                        </Form.Select>
                      </Form.Group>
                    </Col>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>Enabled</Form.Label>
                        <Form.Check
                          type="switch"
                          checked={editFormData.schedule.enabled}
                          onChange={(e) => handleEditInputChange('schedule.enabled', e.target.checked)}
                          label={editFormData.schedule.enabled ? 'Enabled' : 'Disabled'}
                        />
                      </Form.Group>
                    </Col>
                  </Row>

                  {editFormData.schedule.schedule_type === 'once' && (
                    <Form.Group className="mb-3">
                      <Form.Label>Run At (Local Time)</Form.Label>
                      <Form.Control
                        type="datetime-local"
                        value={(() => {
                          if (editFormData.schedule.start_time) {
                            const date = new Date(editFormData.schedule.start_time);
                            const year = date.getFullYear();
                            const month = String(date.getMonth() + 1).padStart(2, '0');
                            const day = String(date.getDate()).padStart(2, '0');
                            const hours = String(date.getHours()).padStart(2, '0');
                            const minutes = String(date.getMinutes()).padStart(2, '0');
                            return `${year}-${month}-${day}T${hours}:${minutes}`;
                          }
                          return '';
                        })()}
                        onChange={(e) => {
                          if (e.target.value) {
                            const localDate = new Date(e.target.value);
                            handleEditInputChange('schedule.start_time', localDate.toISOString());
                          }
                        }}
                      />
                    </Form.Group>
                  )}

                  {editFormData.schedule.schedule_type === 'recurring' && (
                    <Row>
                      <Col md={4}>
                        <Form.Group className="mb-3">
                          <Form.Label>Interval (Minutes)</Form.Label>
                          <Form.Control
                            type="number"
                            value={editFormData.schedule.recurring_schedule?.interval_minutes || ''}
                            onChange={(e) => handleEditInputChange('schedule.recurring_schedule.interval_minutes', parseInt(e.target.value) || null)}
                            placeholder="30"
                          />
                        </Form.Group>
                      </Col>
                      <Col md={4}>
                        <Form.Group className="mb-3">
                          <Form.Label>Interval (Hours)</Form.Label>
                          <Form.Control
                            type="number"
                            value={editFormData.schedule.recurring_schedule?.interval_hours || ''}
                            onChange={(e) => handleEditInputChange('schedule.recurring_schedule.interval_hours', parseInt(e.target.value) || null)}
                            placeholder="2"
                          />
                        </Form.Group>
                      </Col>
                      <Col md={4}>
                        <Form.Group className="mb-3">
                          <Form.Label>Max Executions</Form.Label>
                          <Form.Control
                            type="number"
                            value={editFormData.schedule.recurring_schedule?.max_executions || ''}
                            onChange={(e) => handleEditInputChange('schedule.recurring_schedule.max_executions', parseInt(e.target.value) || null)}
                            placeholder="10"
                          />
                        </Form.Group>
                      </Col>
                    </Row>
                  )}

                  {editFormData.schedule.schedule_type === 'cron' && (
                    <Row>
                      <Col md={2}>
                        <Form.Group className="mb-3">
                          <Form.Label>Minute</Form.Label>
                          <Form.Control
                            type="text"
                            value={editFormData.schedule.cron_schedule?.minute || ''}
                            onChange={(e) => handleEditInputChange('schedule.cron_schedule.minute', e.target.value)}
                            placeholder="0"
                          />
                        </Form.Group>
                      </Col>
                      <Col md={2}>
                        <Form.Group className="mb-3">
                          <Form.Label>Hour</Form.Label>
                          <Form.Control
                            type="text"
                            value={editFormData.schedule.cron_schedule?.hour || ''}
                            onChange={(e) => handleEditInputChange('schedule.cron_schedule.hour', e.target.value)}
                            placeholder="23"
                          />
                        </Form.Group>
                      </Col>
                      <Col md={2}>
                        <Form.Group className="mb-3">
                          <Form.Label>Day of Month</Form.Label>
                          <Form.Control
                            type="text"
                            value={editFormData.schedule.cron_schedule?.day_of_month || ''}
                            onChange={(e) => handleEditInputChange('schedule.cron_schedule.day_of_month', e.target.value)}
                            placeholder="*"
                          />
                        </Form.Group>
                      </Col>
                      <Col md={2}>
                        <Form.Group className="mb-3">
                          <Form.Label>Month</Form.Label>
                          <Form.Control
                            type="text"
                            value={editFormData.schedule.cron_schedule?.month || ''}
                            onChange={(e) => handleEditInputChange('schedule.cron_schedule.month', e.target.value)}
                            placeholder="*"
                          />
                        </Form.Group>
                      </Col>
                      <Col md={2}>
                        <Form.Group className="mb-3">
                          <Form.Label>Day of Week</Form.Label>
                          <Form.Control
                            type="text"
                            value={editFormData.schedule.cron_schedule?.day_of_week || ''}
                            onChange={(e) => handleEditInputChange('schedule.cron_schedule.day_of_week', e.target.value)}
                            placeholder="6"
                          />
                        </Form.Group>
                      </Col>
                    </Row>
                  )}
                </Form>
              </Card.Body>
            </Card>
          )}
        </Col>

        <Col lg={4}>
          <Card>
            <Card.Header>
              <h5>Actions</h5>
            </Card.Header>
            <Card.Body>
              <div className="d-grid gap-2">
                <Button 
                  variant="primary"
                  onClick={handleRunNow}
                  disabled={actionLoading.runNow}
                >
                  {actionLoading.runNow ? 'Running...' : '▶️ Run Now'}
                </Button>
                
                                 <Button 
                   variant={job.schedule?.enabled ? 'warning' : 'success'}
                   onClick={handleToggleStatus}
                   disabled={actionLoading.toggle}
                 >
                   {actionLoading.toggle ? 'Updating...' : (job.schedule?.enabled ? '⏸️ Disable' : '▶️ Enable')}
                 </Button>
                

                
                <hr />
                
                <Button 
                  variant="outline-danger"
                  onClick={() => setShowDeleteModal(true)}
                  disabled={actionLoading.delete}
                >
                  🗑️ Delete Job
                </Button>
              </div>
            </Card.Body>
          </Card>

          <Card className="mt-3">
            <Card.Header>
              <h5>Quick Stats</h5>
            </Card.Header>
            <Card.Body>
              <div className="text-center">
                <div className="mb-3">
                  <h3 className="text-primary mb-0">{getExecutionStats().total}</h3>
                  <small className="text-muted">Total Executions</small>
                </div>
                <div className="row text-center">
                  <div className="col-6">
                    <h5 className="text-success mb-0">{getExecutionStats().successful}</h5>
                    <small className="text-muted">Success</small>
                  </div>
                  <div className="col-6">
                    <h5 className="text-danger mb-0">{getExecutionStats().failed}</h5>
                    <small className="text-muted">Failed</small>
                  </div>
                </div>
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Scheduled Job</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          Are you sure you want to delete the scheduled job "{job.name}"? 
          This action cannot be undone and will also delete all execution history.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
            Cancel
          </Button>
          <Button 
            variant="danger" 
            onClick={handleDelete}
            disabled={actionLoading.delete}
          >
            {actionLoading.delete ? 'Deleting...' : 'Delete'}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default ScheduledJobDetail; 