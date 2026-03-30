import React, { useState, useEffect, useCallback } from 'react';
import { Container, Row, Col, Card, Button, Form, Alert } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';
import { scheduledJobsAPI, workflowAPI, programAPI } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { formatLocalDateTime } from '../../utils/dateUtils';
import VariableInput from '../../components/VariableInput';

// Helper function to get user-friendly timezone name
const getUserFriendlyTimezone = () => {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  
  // Map common timezone IDs to user-friendly names
  const timezoneMap = {
    'America/New_York': 'America/New_York',
    'America/Chicago': 'America/Chicago', 
    'America/Denver': 'America/Denver',
    'America/Los_Angeles': 'America/Los_Angeles',
    'Europe/London': 'Europe/London',
    'Europe/Paris': 'Europe/Paris',
    'Europe/Berlin': 'Europe/Berlin',
    'Asia/Tokyo': 'Asia/Tokyo',
    'Asia/Shanghai': 'Asia/Shanghai',
    'UTC': 'UTC'
  };
  
  // If it's a known timezone, use it; otherwise use the detected one
  const result = timezoneMap[timezone] || timezone;
  return result;
};

const ScheduledJobCreate = () => {
  // Debug timezone detection
  const initialTimezone = getUserFriendlyTimezone();

  
  const [formData, setFormData] = useState({
    job_type: 'dummy_batch',
    name: '',
    description: '',
    program_name: '',
    schedule: {
      schedule_type: 'once',
      run_at: (() => {
        const now = new Date();
        const future = new Date(now.getTime() + 60000); // 1 minute from now
        return formatLocalDateTime(future);
      })(),
      interval_minutes: 30,
      minute: '0',
      hour: '0',
      day_of_month: '*',
      month: '*',
      day_of_week: '*',
      timezone: initialTimezone // Use the helper function
    },
    job_data: {
      items: ['test1', 'test2', 'test3']
    },
    tags: []
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [jobTypes, setJobTypes] = useState([
    { value: 'dummy_batch', label: 'Dummy Batch Job', description: 'A test job that processes a list of items' },
    { value: 'typosquat_batch', label: 'Typosquat Batch Job', description: 'Analyze domains for typosquatting characteristics' },
    { value: 'phishlabs_batch', label: 'PhishLabs Batch Job', description: 'Enrich typosquat findings with PhishLabs data' },
    { value: 'ai_analysis_batch', label: 'AI Analysis Batch Job', description: 'Run AI threat analysis on typosquat findings' },
    { value: 'gather_api_findings', label: 'Gather API Findings', description: 'Gather typosquat findings from vendor APIs (ThreatStream, RecordedFuture)' },
    { value: 'sync_recordedfuture_data', label: 'Sync RecordedFuture Data', description: 'Synchronize RecordedFuture data for existing findings' },
    { value: 'workflow', label: 'Workflow Job', description: 'Execute a predefined workflow' }
  ]);
  
  const [workflows, setWorkflows] = useState([]);
  const [programs, setPrograms] = useState([]);
  
  // Workflow variables state
  const [workflowVariables, setWorkflowVariables] = useState({});
  const [variableValues, setVariableValues] = useState({});
  const [variableErrors, setVariableErrors] = useState({});
  
  const navigate = useNavigate();
  const { isSuperuser, isAdmin, user } = useAuth();

  const hasAnyManagerPermission = useCallback(() => {
    if (isSuperuser && isSuperuser()) return true;
    if (isAdmin && isAdmin()) return true;
    if (!user || !user.program_permissions) return false;
    const programPermissions = user.program_permissions || {};
    if (typeof programPermissions === 'object' && !Array.isArray(programPermissions)) {
      return Object.values(programPermissions).includes('manager');
    }
    return false;
  }, [isSuperuser, isAdmin, user]);

  const loadJobTypes = useCallback(async () => {
    try {
      const response = await scheduledJobsAPI.getJobTypes();
      const supportedTypes = response.supported_job_types || {};
      
      if (Object.keys(supportedTypes).length > 0) {
        const jobTypesList = Object.entries(supportedTypes).map(([value, info]) => ({
          value,
          label: info.name,
          description: info.description
        }));
        setJobTypes(jobTypesList);
      }
    } catch (err) {
      console.error('Error loading job types:', err);
      // Keep the default job types if API fails
    }
  }, []);

  const loadWorkflows = useCallback(async () => {
    try {
      const data = await workflowAPI.getWorkflows();
      setWorkflows(data.workflows || []);
    } catch (err) {
      console.error('Error loading workflows:', err);
      setWorkflows([]);
    }
  }, []);

  const loadPrograms = useCallback(async () => {
    try {
      const data = await programAPI.getAll();
      const programObjects = data.programs_with_permissions || [];
      setPrograms(programObjects);
    } catch (err) {
      console.error('Error loading programs:', err);
      setPrograms([]);
    }
  }, []);

  useEffect(() => {
    // Redirect simple users (no manager permission) away from this page
    if (!hasAnyManagerPermission()) {
      navigate('/scheduled-jobs');
      return;
    }
    loadJobTypes();
    loadWorkflows();
    loadPrograms();
  }, [hasAnyManagerPermission, loadJobTypes, loadWorkflows, loadPrograms, navigate]);

  const handleInputChange = (field, value) => {
    if (field.includes('.')) {
      const [parent, child] = field.split('.');
      setFormData(prev => ({
        ...prev,
        [parent]: {
          ...prev[parent],
          [child]: value
        }
      }));
    } else {
      setFormData(prev => ({
        ...prev,
        [field]: value
      }));
    }
  };

  const handleWorkflowChange = async (workflowId) => {
    handleInputChange('job_data.workflow_id', workflowId);
    
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
          
          // Set default values for variables
          const defaultValues = {};
          Object.entries(variables).forEach(([varName, varDef]) => {
            defaultValues[varName] = varDef.value || varDef.default || '';
          });
          setVariableValues(defaultValues);
          
          // Update job_data with workflow variables
          handleInputChange('job_data.workflow_variables', defaultValues);
        } else {
          setWorkflowVariables({});
          setVariableValues({});
          handleInputChange('job_data.workflow_variables', {});
        }
        setVariableErrors({});
      } catch (err) {
        console.error('Failed to load workflow variables:', err);
        setWorkflowVariables({});
        setVariableValues({});
        handleInputChange('job_data.workflow_variables', {});
      }
    } else {
      setWorkflowVariables({});
      setVariableValues({});
      handleInputChange('job_data.workflow_variables', {});
    }
  };

  const handleScheduleTypeChange = (scheduleType) => {
    setFormData(prev => ({
      ...prev,
      schedule: {
        ...prev.schedule,
        schedule_type: scheduleType
      }
    }));
  };

  const handleVariableChange = (newValues) => {
    setVariableValues(newValues);
    handleInputChange('job_data.workflow_variables', newValues);
  };

  const handleJobTypeChange = (jobType) => {
    setFormData(prev => ({
      ...prev,
      job_type: jobType,
      job_data: getDefaultJobData(jobType)
    }));
    
    // Clear workflow variables when changing job type
    if (jobType !== 'workflow') {
      setWorkflowVariables({});
      setVariableValues({});
      setVariableErrors({});
    }
  };

  const getDefaultJobData = (jobType) => {
    switch (jobType) {
      case 'dummy_batch':
        return { items: ['test1', 'test2', 'test3'] };
      case 'typosquat_batch':
        return {
          domains: ['example.com']
        };
      case 'phishlabs_batch':
        return {
          finding_ids: ['finding1', 'finding2']
        };
      case 'ai_analysis_batch':
        return {
          finding_ids: ['finding1', 'finding2'],
          model: null,
          force: false
        };
      case 'gather_api_findings':
        return {
          api_vendor: 'threatstream',
          date_range_hours: 24,
          custom_query: ''
        };
      case 'sync_recordedfuture_data':
        return {
          program_name: 'example_program',
          sync_options: {
            batch_size: 50,
            max_age_days: 30,
            include_screenshots: true
          }
        };
      case 'workflow':
        return {
          workflow_id: '',
          workflow_variables: {}
        };

      default:
        return {};
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      setError('Job name is required');
      return;
    }

    if (!formData.program_name) {
      setError('Program is required');
      return;
    }

    // Validate that the scheduled time is in the future
    if (formData.schedule.schedule_type === 'once' && formData.schedule.run_at) {
      const selectedTime = new Date(formData.schedule.run_at);
      const now = new Date();
      
      if (selectedTime <= now) {
        setError('Scheduled time must be in the future');
        return;
      }
    }

    // Validate workflow variables if this is a workflow job
    if (formData.job_type === 'workflow' && Object.keys(workflowVariables).length > 0) {
      const missingVariables = [];
      Object.entries(workflowVariables).forEach(([varName, varDef]) => {
        if (varDef.required && (!variableValues[varName] || variableValues[varName] === '')) {
          missingVariables.push(varName);
        }
      });
      
      if (missingVariables.length > 0) {
        setError(`Please fill in all required workflow variables: ${missingVariables.join(', ')}`);
        return;
      }
    }

    if (
      formData.job_type === 'gather_api_findings' &&
      (formData.job_data.api_vendor || 'threatstream') === 'threatstream'
    ) {
      const q = (formData.job_data.custom_query || '').trim();
      if (!q) {
        setError(
          'ThreatStream gather jobs require a non-empty ThreatStream intelligence query (custom_query).'
        );
        return;
      }
    }

    try {
      setLoading(true);
      setError(null);
      
      // Convert local datetime to UTC for the API
      let scheduleData = { ...formData.schedule };
      
      // Ensure timezone is always set for all schedule types
      if (!scheduleData.timezone) {
        scheduleData.timezone = getUserFriendlyTimezone();
      }
      
      if (scheduleData.schedule_type === 'once' && scheduleData.run_at) {
        // Convert local datetime to UTC
        // The datetime-local input gives us a string like "2025-08-06T12:12"
        // JavaScript automatically converts local time to UTC when creating a Date object
        const localDate = new Date(scheduleData.run_at);
        scheduleData.start_time = localDate.toISOString();
        delete scheduleData.run_at; // Remove the local time field
      } else if (scheduleData.schedule_type === 'recurring') {
        // For recurring jobs, we need to structure the data properly
        scheduleData.recurring_schedule = {
          interval_minutes: scheduleData.interval_minutes || null,
          interval_hours: null,
          interval_days: null,
          max_executions: null,
          end_date: null
        };
        delete scheduleData.interval_minutes; // Remove the flat field
      } else if (scheduleData.schedule_type === 'cron') {
        // For cron jobs, we need to structure the data properly
        scheduleData.cron_schedule = {
          minute: scheduleData.minute || '0',
          hour: scheduleData.hour || '0',
          day_of_month: scheduleData.day_of_month || '*',
          month: scheduleData.month || '*',
          day_of_week: scheduleData.day_of_week || '*'
        };
        // Remove the flat fields
        delete scheduleData.minute;
        delete scheduleData.hour;
        delete scheduleData.day_of_month;
        delete scheduleData.month;
        delete scheduleData.day_of_week;
      }
      
      const jobPayload = {
        job_type: formData.job_type,
        name: formData.name,
        description: formData.description,
        schedule: scheduleData,
        job_data: formData.job_data,
        tags: formData.tags
      };

      // All job types use program_name
      jobPayload.program_name = formData.program_name;

      // For gather_api_findings, also include program_name in job_data for the job runner
      if (formData.job_type === 'gather_api_findings') {
        jobPayload.job_data.program_name = formData.program_name;
      }

      const response = await scheduledJobsAPI.create(jobPayload);
      setSuccess(true);
      
      // Redirect to the job detail page after a short delay
      setTimeout(() => {
        navigate(`/scheduled-jobs/${response.schedule_id}`);
      }, 1500);
      
    } catch (err) {
      console.error('Error creating scheduled job:', err);
      setError(err.response?.data?.detail || 'Failed to create scheduled job');
    } finally {
      setLoading(false);
    }
  };

  const renderScheduleForm = () => {
    const { schedule_type } = formData.schedule;
    
    return (
      <div>
        <Form.Group className="mb-3">
          <Form.Label>Schedule Type</Form.Label>
          <Form.Select
            value={schedule_type}
            onChange={(e) => handleScheduleTypeChange(e.target.value)}
          >
            <option value="once">One-time</option>
            <option value="recurring">Recurring</option>
            <option value="cron">Cron Expression</option>
          </Form.Select>
        </Form.Group>

        {schedule_type === 'once' && (
          <>
            <Form.Group className="mb-3">
              <Form.Label>Run At (Local Time)</Form.Label>
              <Form.Control
                type="datetime-local"
                value={formData.schedule.run_at}
                min={formatLocalDateTime(new Date(Date.now() + 60000))} // Minimum 1 minute from now in local time
                onChange={(e) => handleInputChange('schedule.run_at', e.target.value)}
              />
              <Form.Text className="text-muted">
                Enter the time in your local timezone ({formData.schedule.timezone}). The system will automatically convert it to UTC for scheduling.
              </Form.Text>
            </Form.Group>
          </>
        )}

        {schedule_type === 'recurring' && (
          <>
            <Form.Group className="mb-3">
              <Form.Label>Interval (minutes)</Form.Label>
              <Form.Control
                type="number"
                min="1"
                value={formData.schedule.interval_minutes}
                onChange={(e) => handleInputChange('schedule.interval_minutes', parseInt(e.target.value))}
              />
              <Form.Text className="text-muted">
                The job will run at regular intervals starting from now in the selected timezone ({formData.schedule.timezone}).
              </Form.Text>
            </Form.Group>
          </>
        )}

        {schedule_type === 'cron' && (
          <>
            <Row>
              <Col md={2}>
                <Form.Group className="mb-3">
                  <Form.Label>Minute</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="0"
                    value={formData.schedule.minute}
                    onChange={(e) => handleInputChange('schedule.minute', e.target.value)}
                  />
                </Form.Group>
              </Col>
              <Col md={2}>
                <Form.Group className="mb-3">
                  <Form.Label>Hour</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="0"
                    value={formData.schedule.hour}
                    onChange={(e) => handleInputChange('schedule.hour', e.target.value)}
                  />
                </Form.Group>
              </Col>
              <Col md={2}>
                <Form.Group className="mb-3">
                  <Form.Label>Day of Month</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="*"
                    value={formData.schedule.day_of_month}
                    onChange={(e) => handleInputChange('schedule.day_of_month', e.target.value)}
                  />
                </Form.Group>
              </Col>
              <Col md={2}>
                <Form.Group className="mb-3">
                  <Form.Label>Month</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="*"
                    value={formData.schedule.month}
                    onChange={(e) => handleInputChange('schedule.month', e.target.value)}
                  />
                </Form.Group>
              </Col>
              <Col md={2}>
                <Form.Group className="mb-3">
                  <Form.Label>Day of Week</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="*"
                    value={formData.schedule.day_of_week}
                    onChange={(e) => handleInputChange('schedule.day_of_week', e.target.value)}
                  />
                </Form.Group>
              </Col>
            </Row>
          </>
        )}
      </div>
    );
  };

  const renderJobDataForm = () => {
    const { job_type } = formData;
    
    switch (job_type) {
      case 'dummy_batch':
        return (
          <Form.Group className="mb-3">
            <Form.Label>Items (one per line)</Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              value={formData.job_data.items.join('\n')}
              onChange={(e) => handleInputChange('job_data.items', e.target.value.split('\n').filter(item => item.trim()))}
              placeholder="test1&#10;test2&#10;test3"
            />
          </Form.Group>
        );
        
      case 'typosquat_batch':
        return (
          <>
            <Form.Group className="mb-3">
              <Form.Label>Domains (one per line)</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                value={formData.job_data.domains.join('\n')}
                onChange={(e) => handleInputChange('job_data.domains', e.target.value.split('\n').filter(domain => domain.trim()))}
                placeholder="example.com&#10;test.com"
              />
            </Form.Group>
          </>
        );
        
      case 'phishlabs_batch':
        return (
          <Form.Group className="mb-3">
            <Form.Label>Finding IDs (one per line)</Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              value={formData.job_data.finding_ids.join('\n')}
              onChange={(e) => handleInputChange('job_data.finding_ids', e.target.value.split('\n').filter(id => id.trim()))}
              placeholder="finding1&#10;finding2&#10;finding3"
            />
          </Form.Group>
        );

      case 'ai_analysis_batch':
        return (
          <>
            <Form.Group className="mb-3">
              <Form.Label>Finding IDs (one per line)</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                value={(formData.job_data.finding_ids || []).join('\n')}
                onChange={(e) => handleInputChange('job_data.finding_ids', e.target.value.split('\n').filter(id => id.trim()))}
                placeholder="finding1&#10;finding2&#10;finding3"
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Force re-analyze (even if already analyzed)"
                checked={formData.job_data.force || false}
                onChange={(e) => handleInputChange('job_data.force', e.target.checked)}
              />
            </Form.Group>
          </>
        );

      case 'gather_api_findings':
        return (
          <>
            <Form.Group className="mb-3">
              <Form.Label>API Vendor</Form.Label>
              <Form.Select
                value={formData.job_data.api_vendor || 'threatstream'}
                onChange={(e) => handleInputChange('job_data.api_vendor', e.target.value)}
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
                value={formData.job_data.date_range_hours ?? 24}
                onChange={(e) => handleInputChange('job_data.date_range_hours', parseInt(e.target.value))}
              />
              <Form.Text className="text-muted">
                Fetch findings created within the last N hours (0-8760 hours). <strong>Set to 0 for no date filtering (all findings).</strong> Works with both ThreatStream and RecordedFuture APIs.
              </Form.Text>
            </Form.Group>
            {formData.job_data.api_vendor === 'threatstream' && (
              <Form.Group className="mb-3">
                <Form.Label>ThreatStream query (required)</Form.Label>
                <Form.Control
                  as="textarea"
                  rows={3}
                  required
                  value={formData.job_data.custom_query || ''}
                  onChange={(e) => handleInputChange('job_data.custom_query', e.target.value)}
                  placeholder='(feed_name = "FeedName" and itype = mal_domain and (value contains Value1 or value contains Value2))'
                />
                <Form.Text className="text-muted">
                  ThreatStream intelligence <code>q=</code> filter passed through to the API. Must not be empty.
                  Examples:{' '}
                  <code>(feed_name = "FeedName" and itype = mal_domain and (value contains Value1))</code>
                  {' · '}
                  <code>(feed_name = "FeedName" and (itype = mal_domain or itype = phish_domain) and value contains Value2)</code>
                </Form.Text>
              </Form.Group>
            )}
          </>
        );

      case 'sync_recordedfuture_data':
        return (
          <>
            <Form.Group className="mb-3">
              <Form.Label>Program Name</Form.Label>
              <Form.Select
                value={formData.job_data.program_name || ''}
                onChange={(e) => handleInputChange('job_data.program_name', e.target.value)}
                required
              >
                <option value="">Choose a program...</option>
                {programs.map((program) => (
                  <option key={program.name} value={program.name}>
                    {program.name}
                  </option>
                ))}
              </Form.Select>
              <Form.Text className="text-muted">
                Select the program to sync RecordedFuture data for
              </Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Batch Size</Form.Label>
              <Form.Control
                type="number"
                min="10"
                max="200"
                value={formData.job_data.sync_options?.batch_size || 50}
                onChange={(e) => {
                  const newSyncOptions = {
                    ...formData.job_data.sync_options,
                    batch_size: parseInt(e.target.value)
                  };
                  handleInputChange('job_data.sync_options', newSyncOptions);
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
                value={formData.job_data.sync_options?.max_age_days || 30}
                onChange={(e) => {
                  const newSyncOptions = {
                    ...formData.job_data.sync_options,
                    max_age_days: parseInt(e.target.value)
                  };
                  handleInputChange('job_data.sync_options', newSyncOptions);
                }}
              />
              <Form.Text className="text-muted">
                Only sync findings that haven't been updated in this many days (0 for all)
              </Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                id="include_screenshots"
                label="Include Screenshots"
                checked={formData.job_data.sync_options?.include_screenshots !== false}
                onChange={(e) => {
                  const newSyncOptions = {
                    ...formData.job_data.sync_options,
                    include_screenshots: e.target.checked
                  };
                  handleInputChange('job_data.sync_options', newSyncOptions);
                }}
              />
              <Form.Text className="text-muted">
                Whether to process screenshot data during sync
              </Form.Text>
            </Form.Group>
          </>
        );

      case 'workflow':
        return (
          <>
            <Form.Group className="mb-3">
              <Form.Label>Select Workflow</Form.Label>
              <Form.Select
                value={formData.job_data.workflow_id}
                onChange={(e) => {
                  const workflowId = e.target.value;
                  handleWorkflowChange(workflowId);
                  
                  // Auto-fill program if workflow is selected
                  if (workflowId) {
                    const selectedWorkflow = workflows.find(w => w.id === workflowId);
                    if (selectedWorkflow && selectedWorkflow.program_name) {
                      handleInputChange('program_name', selectedWorkflow.program_name);
                    }
                  }
                }}
              >
                <option value="">Choose a workflow...</option>
                {workflows.map((workflow) => (
                  <option key={workflow.id} value={workflow.id}>
                    {workflow.name} {workflow.program_name && `(${workflow.program_name})`}
                    {/* Show if workflow has variables */}
                    {(workflow.variables && Object.keys(workflow.variables).length > 0) && ' 📝'}
                  </option>
                ))}
              </Form.Select>
              <Form.Text className="text-muted">
                Select a saved workflow to schedule
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
        );
        
      default:
        return null;
    }
  };

  return (
    <Container fluid>
      <Row className="mb-3">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <h2>⏰ Create Scheduled Job</h2>
            <Button variant="outline-secondary" onClick={() => navigate('/scheduled-jobs')}>
              ← Back to Jobs
            </Button>
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

      {success && (
        <Row className="mb-3">
          <Col>
            <Alert variant="success">
              Scheduled job created successfully! Redirecting to job details...
            </Alert>
          </Col>
        </Row>
      )}

      <Form onSubmit={handleSubmit}>
        <Row>
          <Col lg={8}>
            <Card className="mb-3">
              <Card.Header>
                <h5>Job Configuration</h5>
                <small className="text-muted">
                  Job will run in timezone: <strong>{formData.schedule.timezone}</strong>
                </small>
              </Card.Header>
              <Card.Body>
                <Row>
                  <Col md={4}>
                    <Form.Group className="mb-3">
                      <Form.Label>Job Type</Form.Label>
                      <Form.Select
                        value={formData.job_type}
                        onChange={(e) => handleJobTypeChange(e.target.value)}
                      >
                        {jobTypes.map(type => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </Form.Select>
                    </Form.Group>
                  </Col>
                  <Col md={4}>
                    <Form.Group className="mb-3">
                      <Form.Label>Job Name *</Form.Label>
                      <Form.Control
                        type="text"
                        value={formData.name}
                        onChange={(e) => handleInputChange('name', e.target.value)}
                        placeholder="Enter job name"
                        required
                      />
                    </Form.Group>
                  </Col>
                  <Col md={4}>
                    <Form.Group className="mb-3">
                      <Form.Label>Program *</Form.Label>
                      <Form.Select
                        value={formData.program_name}
                        onChange={(e) => handleInputChange('program_name', e.target.value)}
                        required
                      >
                        <option value="">Choose a program...</option>
                        {programs.map((program) => (
                          <option key={program.name} value={program.name}>
                            {program.name}
                          </option>
                        ))}
                      </Form.Select>
                    </Form.Group>
                  </Col>
                </Row>
                
                <Form.Group className="mb-3">
                  <Form.Label>Description</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={2}
                    value={formData.description}
                    onChange={(e) => handleInputChange('description', e.target.value)}
                    placeholder="Enter job description"
                  />
                </Form.Group>
              </Card.Body>
            </Card>

            <Card className="mb-3">
              <Card.Header>
                <h5>Schedule Configuration</h5>
                <small className="text-muted">
                  Current timezone: <strong>{formData.schedule.timezone}</strong>
                </small>
              </Card.Header>
              <Card.Body>
                <Form.Group className="mb-3">
                  <Form.Label>Timezone</Form.Label>
                  <Form.Select
                    value={formData.schedule.timezone}
                    onChange={(e) => handleInputChange('schedule.timezone', e.target.value)}
                  >
                    <option value="America/New_York">Eastern Time (ET)</option>
                    <option value="America/Chicago">Central Time (CT)</option>
                    <option value="America/Denver">Mountain Time (MT)</option>
                    <option value="America/Los_Angeles">Pacific Time (PT)</option>
                    <option value="Europe/London">London (GMT/BST)</option>
                    <option value="Europe/Paris">Paris (CET/CEST)</option>
                    <option value="Europe/Berlin">Berlin (CET/CEST)</option>
                    <option value="Asia/Tokyo">Tokyo (JST)</option>
                    <option value="Asia/Shanghai">Shanghai (CST)</option>
                    <option value="UTC">UTC</option>
                  </Form.Select>
                  <Form.Text className="text-muted">
                    Select the timezone for your schedule. All times will be interpreted in this timezone.
                  </Form.Text>
                </Form.Group>
                {renderScheduleForm()}
              </Card.Body>
            </Card>

            <Card className="mb-3">
              <Card.Header>
                <h5>Job Data</h5>
                <small className="text-muted">
                  Schedule timezone: <strong>{formData.schedule.timezone}</strong>
                </small>
              </Card.Header>
              <Card.Body>
                {renderJobDataForm()}
              </Card.Body>
            </Card>
          </Col>

          <Col lg={4}>
            <Card>
              <Card.Header>
                <h5>Actions</h5>
                <small className="text-muted">
                  Final timezone: <strong>{formData.schedule.timezone}</strong>
                </small>
              </Card.Header>
              <Card.Body>
                <div className="d-grid gap-2">
                  <Button 
                    type="submit" 
                    variant="primary" 
                    disabled={loading}
                  >
                    {loading ? 'Creating...' : 'Create Scheduled Job'}
                  </Button>
                  <Button 
                    variant="outline-secondary" 
                    onClick={() => navigate('/scheduled-jobs')}
                    disabled={loading}
                  >
                    Cancel
                  </Button>
                </div>
                
                <div className="mt-3">
                  <small className="text-muted">
                    <strong>Timezone Summary:</strong>
                    <br />
                    • Job will run in: <strong>{formData.schedule.timezone}</strong>
                    <br />
                    • Schedule type: <strong>{formData.schedule.schedule_type}</strong>
                    {formData.schedule.schedule_type === 'cron' && (
                      <>
                        <br />
                        • Cron expression: <code>{formData.schedule.minute || '0'} {formData.schedule.hour || '0'} {formData.schedule.day_of_month || '*'} {formData.schedule.month || '*'} {formData.schedule.day_of_week || '*'}</code>
                        <br />
                        • Will run at: <strong>{formData.schedule.hour || '0'}:{formData.schedule.minute || '0'} on {formData.schedule.day_of_week === '6' ? 'Saturday' : formData.schedule.day_of_week === '0' ? 'Sunday' : `day ${formData.schedule.day_of_week}`} in {formData.schedule.timezone}</strong>
                      </>
                    )}
                    {formData.schedule.schedule_type === 'once' && (
                      <>
                        <br />
                        • Will run at: <strong>{formData.schedule.run_at} in {formData.schedule.timezone}</strong>
                      </>
                    )}
                    {formData.schedule.schedule_type === 'recurring' && (
                      <>
                        <br />
                        • Will run every: <strong>{formData.schedule.interval_minutes} minutes in {formData.schedule.timezone}</strong>
                      </>
                    )}
                  </small>
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Form>
    </Container>
  );
};

export default ScheduledJobCreate;