import React, { useState, useEffect } from 'react';
import { 
  Container, 
  Row, 
  Col, 
  Card, 
  Button, 
  Alert, 
  Spinner, 
  Form,
  Table,
  Badge,
  Modal,
  Tabs,
  Tab
} from 'react-bootstrap';
import { adminAPI } from '../../services/api';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

// Add Font Awesome CSS if not already loaded
const loadFontAwesome = () => {
  if (!document.querySelector('link[href*="fontawesome"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css';
    document.head.appendChild(link);
  }
};

function SystemSettings() {
  usePageTitle(formatPageTitle('System Settings'));
  const [reconTasks, setReconTasks] = useState([]);
  const [awsCredentials, setAwsCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // Modal states
  const [showEditModal, setShowEditModal] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);

  // AWS Credentials modal states
  const [showAwsEditModal, setShowAwsEditModal] = useState(false);
  const [showAwsCreateModal, setShowAwsCreateModal] = useState(false);
  const [selectedAwsCredential, setSelectedAwsCredential] = useState(null);

  // Form states
  const [editForm, setEditForm] = useState({
    last_execution_threshold: 24,
    timeout: 300,
    max_retries: 3,
    chunk_size: 10
  });

  const [createForm, setCreateForm] = useState({
    recon_task: '',
    last_execution_threshold: 24,
    timeout: 300,
    max_retries: 3,
    chunk_size: 10
  });

  // AWS Credentials form states
  const [awsEditForm, setAwsEditForm] = useState({
    name: '',
    access_key: '',
    secret_access_key: '',
    default_region: 'us-east-1',
    is_active: true
  });

  const [awsCreateForm, setAwsCreateForm] = useState({
    name: '',
    access_key: '',
    secret_access_key: '',
    default_region: 'us-east-1',
    is_active: true
  });

  // AI Settings state
  const [aiSettingsLoading, setAiSettingsLoading] = useState(false);
  const [aiSettingsSaving, setAiSettingsSaving] = useState(false);
  const [aiEditForm, setAiEditForm] = useState({});

  const [activeTab, setActiveTab] = useState('recon');

  const [ctMonitorRuntime, setCtMonitorRuntime] = useState({
    domain_refresh_interval: '',
    stats_interval: '',
    ct_poll_interval: '',
    ct_batch_size: '',
    ct_max_entries_per_poll: '',
    ct_start_offset: ''
  });
  const [ctMonitorRuntimeLoading, setCtMonitorRuntimeLoading] = useState(false);
  const [ctMonitorRuntimeSaving, setCtMonitorRuntimeSaving] = useState(false);

  const FEATURE_LABELS = {
    typosquat: 'Typosquat Analysis',
    nuclei: 'Nuclei Analysis'
  };
  const FIELD_LABELS = {
    default_prompt: 'Default System Prompt',
    rules_and_mapping_instructions: 'Rules and Mapping Instructions',
    response_format_suffix: 'Response Format (JSON Schema)',
    user_content_prefix: 'User Message Prefix (use {RESPONSE_FORMAT_SUFFIX} as placeholder)'
  };

  const FIELD_HELP = {
    default_prompt: 'First part of the system message. Combined with Rules and Mapping Instructions to form the full system prompt sent to Ollama as messages[0].content. Defines the analyst role and threat-level guidelines.',
    rules_and_mapping_instructions: 'Appended to the Default System Prompt to form the complete system message. Contains decision rules, evidence constraints, and threat_level mapping. Sent as the second half of messages[0].content.',
    response_format_suffix: 'Injected into the user message where {RESPONSE_FORMAT_SUFFIX} appears in the prefix. Specifies the exact JSON schema the model must return (threat_level, confidence, summary, etc.). Ensures parseable output.',
    user_content_prefix: 'Text that appears before the finding data in the user message. Use {RESPONSE_FORMAT_SUFFIX} as a placeholder; it is replaced with the JSON schema at runtime. The finding\'s enrichment data (DNS, WHOIS, HTTP probes, screenshot text) is always appended automatically by the code—no placeholder needed. Full user message = prefix + context.'
  };

  useEffect(() => {
    loadReconTasks();
    loadAwsCredentials();
    loadAiSettings();
    loadCtMonitorRuntime();
  }, []);

  // Load Font Awesome CSS
  useEffect(() => {
    loadFontAwesome();
  }, []);

  const loadReconTasks = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await adminAPI.listReconTaskParameters();
      setReconTasks(response.tasks || []);
    } catch (err) {
      setError('Failed to load recon task parameters: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const loadAwsCredentials = async () => {
    try {
      setError('');
      const response = await adminAPI.listAwsCredentials();
      setAwsCredentials(response.credentials || []);
    } catch (err) {
      setError('Failed to load AWS credentials: ' + (err.response?.data?.detail || err.message));
    }
  };

  const loadCtMonitorRuntime = async () => {
    try {
      setCtMonitorRuntimeLoading(true);
      setError('');
      const response = await adminAPI.getCtMonitorRuntimeSettings();
      const s = response.settings || {};
      setCtMonitorRuntime({
        domain_refresh_interval: String(s.domain_refresh_interval ?? ''),
        stats_interval: String(s.stats_interval ?? ''),
        ct_poll_interval: String(s.ct_poll_interval ?? ''),
        ct_batch_size: String(s.ct_batch_size ?? ''),
        ct_max_entries_per_poll: String(s.ct_max_entries_per_poll ?? ''),
        ct_start_offset: String(s.ct_start_offset ?? '')
      });
    } catch (err) {
      setError('Failed to load CT monitor runtime settings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setCtMonitorRuntimeLoading(false);
    }
  };

  const handleSaveCtMonitorRuntime = async () => {
    try {
      setCtMonitorRuntimeSaving(true);
      setError('');
      const payload = {
        domain_refresh_interval: parseInt(ctMonitorRuntime.domain_refresh_interval, 10),
        stats_interval: parseInt(ctMonitorRuntime.stats_interval, 10),
        ct_poll_interval: parseInt(ctMonitorRuntime.ct_poll_interval, 10),
        ct_batch_size: parseInt(ctMonitorRuntime.ct_batch_size, 10),
        ct_max_entries_per_poll: parseInt(ctMonitorRuntime.ct_max_entries_per_poll, 10),
        ct_start_offset: parseInt(ctMonitorRuntime.ct_start_offset, 10)
      };
      for (const [k, v] of Object.entries(payload)) {
        if (Number.isNaN(v)) {
          setError(`Invalid number for ${k}`);
          return;
        }
      }
      await adminAPI.updateCtMonitorRuntimeSettings(payload);
      setSuccess('CT monitor runtime settings saved; ct-monitor pod will reload on next tick or immediately if reachable.');
      loadCtMonitorRuntime();
    } catch (err) {
      setError('Failed to save CT monitor runtime: ' + (err.response?.data?.detail || err.message));
    } finally {
      setCtMonitorRuntimeSaving(false);
    }
  };

  const loadAiSettings = async () => {
    try {
      setAiSettingsLoading(true);
      setError('');
      const response = await adminAPI.getAiSettings();
      const settings = response.settings || {};
      setAiEditForm(JSON.parse(JSON.stringify(settings)));
    } catch (err) {
      setError('Failed to load AI settings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setAiSettingsLoading(false);
    }
  };

  const handleSaveAiSettings = async () => {
    try {
      setAiSettingsSaving(true);
      setError('');
      const payload = { typosquat: aiEditForm.typosquat || {} };
      await adminAPI.updateAiSettings(payload);
      setSuccess('AI settings saved successfully');
      loadAiSettings();
    } catch (err) {
      setError('Failed to save AI settings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setAiSettingsSaving(false);
    }
  };

  const handleResetAiSettings = async (feature) => {
    try {
      setAiSettingsSaving(true);
      setError('');
      const response = await adminAPI.getAiSettingsDefaults();
      const defaults = response.settings || {};
      setAiEditForm(prev => {
        const next = { ...prev };
        next[feature] = { ...(defaults[feature] || {}) };
        return next;
      });
      setSuccess(`Reset ${FEATURE_LABELS[feature] || feature} to defaults`);

      const payload = { [feature]: defaults[feature] || {} };
      await adminAPI.updateAiSettings(payload);
      loadAiSettings();
    } catch (err) {
      setError('Failed to reset AI settings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setAiSettingsSaving(false);
    }
  };

  const handleAiFieldChange = (feature, field, value) => {
    setAiEditForm(prev => {
      const next = { ...prev };
      next[feature] = { ...(next[feature] || {}), [field]: value };
      return next;
    });
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    
    if (!createForm.recon_task.trim()) {
      setError('Recon task name is required');
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      
      const parameters = {
        last_execution_threshold: createForm.last_execution_threshold,
        timeout: createForm.timeout,
        max_retries: createForm.max_retries,
        chunk_size: createForm.chunk_size
      };
      
      await adminAPI.createReconTaskParameters(createForm.recon_task, parameters);
      setSuccess('Recon task parameters created successfully');
      setShowCreateModal(false);
      setCreateForm({
        recon_task: '',
        last_execution_threshold: 24,
        timeout: 300,
        max_retries: 3
      });
      loadReconTasks();
    } catch (err) {
      setError('Failed to create recon task parameters: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditTask = async (e) => {
    e.preventDefault();
    
    if (!selectedTask) return;
    
    try {
      setActionLoading(true);
      setError('');
      
      const parameters = {
        last_execution_threshold: editForm.last_execution_threshold,
        timeout: editForm.timeout,
        max_retries: editForm.max_retries,
        chunk_size: editForm.chunk_size
      };
      
      await adminAPI.updateReconTaskParameters(selectedTask.recon_task, parameters);
      setSuccess('Recon task parameters updated successfully');
      setShowEditModal(false);
      setSelectedTask(null);
      loadReconTasks();
    } catch (err) {
      setError('Failed to update recon task parameters: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteTask = async (task) => {
    if (!window.confirm(`Are you sure you want to delete parameters for "${task.recon_task}"? This action cannot be undone.`)) {
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      
      await adminAPI.deleteReconTaskParameters(task.recon_task);
      setSuccess('Recon task parameters deleted successfully');
      loadReconTasks();
    } catch (err) {
      setError('Failed to delete recon task parameters: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const openEditModal = (task) => {
    setSelectedTask(task);
    setEditForm({
      last_execution_threshold: task.parameters.last_execution_threshold || 24,
      timeout: task.parameters.timeout || 300,
      max_retries: task.parameters.max_retries || 3,
      chunk_size: task.parameters.chunk_size || 10
    });
    setShowEditModal(true);
  };

  const openCreateModal = () => {
    setCreateForm({
      recon_task: '',
      last_execution_threshold: 24,
      timeout: 300,
      max_retries: 3,
      chunk_size: 10
    });
    setShowCreateModal(true);
  };

  // AWS Credentials Handlers
  const handleCreateAwsCredential = async (e) => {
    e.preventDefault();

    if (!awsCreateForm.name.trim()) {
      setError('Credential name is required');
      return;
    }

    try {
      setActionLoading(true);
      setError('');

      await adminAPI.createAwsCredential(awsCreateForm);
      setSuccess('AWS credential created successfully');
      setShowAwsCreateModal(false);
      setAwsCreateForm({
        name: '',
        access_key: '',
        secret_access_key: '',
        default_region: 'us-east-1',
        is_active: true
      });
      loadAwsCredentials();
    } catch (err) {
      setError('Failed to create AWS credential: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditAwsCredential = async (e) => {
    e.preventDefault();

    if (!selectedAwsCredential) return;

    try {
      setActionLoading(true);
      setError('');

      await adminAPI.updateAwsCredential(selectedAwsCredential.id, awsEditForm);
      setSuccess('AWS credential updated successfully');
      setShowAwsEditModal(false);
      setSelectedAwsCredential(null);
      loadAwsCredentials();
    } catch (err) {
      setError('Failed to update AWS credential: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteAwsCredential = async (credential) => {
    if (!window.confirm(`Are you sure you want to delete AWS credential "${credential.name}"? This action cannot be undone.`)) {
      return;
    }

    try {
      setActionLoading(true);
      setError('');

      await adminAPI.deleteAwsCredential(credential.id);
      setSuccess('AWS credential deleted successfully');
      loadAwsCredentials();
    } catch (err) {
      setError('Failed to delete AWS credential: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const openAwsEditModal = (credential) => {
    setSelectedAwsCredential(credential);
    setAwsEditForm({
      name: credential.name,
      access_key: credential.access_key,
      secret_access_key: credential.secret_access_key,
      default_region: credential.default_region,
      is_active: credential.is_active
    });
    setShowAwsEditModal(true);
  };

  const openAwsCreateModal = () => {
    setAwsCreateForm({
      name: '',
      access_key: '',
      secret_access_key: '',
      default_region: 'us-east-1',
      is_active: true
    });
    setShowAwsCreateModal(true);
  };

  const maskAccessKey = (accessKey) => {
    if (!accessKey || accessKey.length < 8) return accessKey;
    const last4 = accessKey.slice(-4);
    return `${accessKey.slice(0, 4)}...${last4}`;
  };

  const formatDateLocal = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const getTaskBadge = (taskName) => {
    const variants = {
      'resolve_domain': 'primary',
      'port_scan': 'info',
      'nuclei_scan': 'warning',
      'screenshot_website': 'success',
      'crawl_website': 'secondary'
    };
    
    return <Badge bg={variants[taskName] || 'secondary'}>{taskName}</Badge>;
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <Row className="justify-content-center">
          <Col>
            <div className="text-center mt-5">
              <Spinner animation="border" role="status">
                <span className="visually-hidden">Loading...</span>
              </Spinner>
              <p className="mt-2">Loading system settings...</p>
            </div>
          </Col>
        </Row>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <h2 className="mb-1">System Settings</h2>
          <p className="text-muted mb-0">Global recon, cloud, and AI defaults</p>
        </Col>
      </Row>

      {error && (
        <Row className="mb-3">
          <Col>
            <Alert variant="danger" dismissible onClose={() => setError('')}>
              {error}
            </Alert>
          </Col>
        </Row>
      )}

      {success && (
        <Row className="mb-3">
          <Col>
            <Alert variant="success" dismissible onClose={() => setSuccess('')}>
              {success}
            </Alert>
          </Col>
        </Row>
      )}

      <Row>
        <Col>
          <Tabs activeKey={activeTab} onSelect={(k) => setActiveTab(k)} className="mb-3">
            <Tab eventKey="recon" title="Recon task parameters">
              <Card className="mb-4">
                <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                  <h5 className="mb-0">Recon task parameters</h5>
                  <Button variant="primary" size="sm" onClick={openCreateModal}>
                    <i className="fas fa-plus me-2"></i>
                    Add parameters
                  </Button>
                </Card.Header>
                <Card.Body>
                  {reconTasks.length === 0 ? (
                    <div className="text-center py-4">
                      <p className="text-muted">No recon task parameters configured yet.</p>
                      <Button variant="outline-primary" onClick={openCreateModal}>
                        Add first task parameters
                      </Button>
                    </div>
                  ) : (
                    <Table responsive striped hover>
                      <thead>
                        <tr>
                          <th>Task Name</th>
                          <th>Last Execution Threshold (hours)</th>
                          <th>Timeout (seconds)</th>
                          <th>Max Retries</th>
                          <th>Chunk Size</th>
                          <th>Last Updated</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reconTasks.map((task) => (
                          <tr key={task.id}>
                            <td>{getTaskBadge(task.recon_task)}</td>
                            <td>
                              <Badge bg="info">
                                {task.parameters.last_execution_threshold || 'Not set'}
                              </Badge>
                            </td>
                            <td>
                              <Badge bg="secondary">
                                {task.parameters.timeout || 'Not set'}
                              </Badge>
                            </td>
                            <td>
                              <Badge bg="warning">
                                {task.parameters.max_retries || 'Not set'}
                              </Badge>
                            </td>
                            <td>
                              <Badge bg="success">
                                {task.parameters.chunk_size || 'Not set'}
                              </Badge>
                            </td>
                            <td>{formatDateLocal(task.updated_at)}</td>
                            <td>
                              <div className="btn-group" role="group">
                                <Button
                                  variant="outline-primary"
                                  size="sm"
                                  onClick={() => openEditModal(task)}
                                  disabled={actionLoading}
                                  title="Edit Parameters"
                                >
                                  ✏️
                                </Button>
                                <Button
                                  variant="outline-danger"
                                  size="sm"
                                  onClick={() => handleDeleteTask(task)}
                                  disabled={actionLoading}
                                  title="Delete Parameters"
                                >
                                  🗑️
                                </Button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  )}
                </Card.Body>
              </Card>
            </Tab>

            <Tab eventKey="aws" title="AWS credentials">
              <Card className="mb-4">
                <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                  <h5 className="mb-0">AWS credentials</h5>
                  <Button variant="primary" size="sm" onClick={openAwsCreateModal}>
                    <i className="fas fa-plus me-2"></i>
                    Add credential
                  </Button>
                </Card.Header>
                <Card.Body>
                  {awsCredentials.length === 0 ? (
                    <div className="text-center py-4">
                      <p className="text-muted">No AWS credentials configured yet.</p>
                      <Button variant="outline-primary" onClick={openAwsCreateModal}>
                        Add first credential
                      </Button>
                    </div>
                  ) : (
                    <Table responsive striped hover>
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Access Key</th>
                          <th>Default Region</th>
                          <th>Status</th>
                          <th>Last Updated</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {awsCredentials.map((credential) => (
                          <tr key={credential.id}>
                            <td>
                              <strong>{credential.name}</strong>
                            </td>
                            <td>
                              <code className="text-muted">{maskAccessKey(credential.access_key)}</code>
                            </td>
                            <td>
                              <Badge bg="secondary">{credential.default_region}</Badge>
                            </td>
                            <td>
                              {credential.is_active ? (
                                <Badge bg="success">Active</Badge>
                              ) : (
                                <Badge bg="danger">Inactive</Badge>
                              )}
                            </td>
                            <td>{formatDateLocal(credential.updated_at)}</td>
                            <td>
                              <div className="btn-group" role="group">
                                <Button
                                  variant="outline-primary"
                                  size="sm"
                                  onClick={() => openAwsEditModal(credential)}
                                  disabled={actionLoading}
                                  title="Edit Credential"
                                >
                                  ✏️
                                </Button>
                                <Button
                                  variant="outline-danger"
                                  size="sm"
                                  onClick={() => handleDeleteAwsCredential(credential)}
                                  disabled={actionLoading}
                                  title="Delete Credential"
                                >
                                  🗑️
                                </Button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  )}
                </Card.Body>
              </Card>
            </Tab>

            <Tab eventKey="ctmonitor" title="CT monitor">
              <Card className="mb-4">
                <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                  <h5 className="mb-0">CT monitor runtime</h5>
                  <div>
                    <Button
                      variant="outline-secondary"
                      size="sm"
                      className="me-2"
                      onClick={loadCtMonitorRuntime}
                      disabled={ctMonitorRuntimeLoading}
                    >
                      {ctMonitorRuntimeLoading ? <Spinner animation="border" size="sm" /> : 'Refresh'}
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleSaveCtMonitorRuntime}
                      disabled={ctMonitorRuntimeSaving || ctMonitorRuntimeLoading}
                    >
                      {ctMonitorRuntimeSaving ? (
                        <>
                          <Spinner animation="border" size="sm" className="me-2" />
                          Saving...
                        </>
                      ) : (
                        'Save all'
                      )}
                    </Button>
                  </div>
                </Card.Header>
                <Card.Body>
                  <p className="text-muted small">
                    Global intervals and CT log polling behavior for the ct-monitor service (stored in the database).
                    Per-program TLD filter and similarity are configured on each program&apos;s Typosquat tab.
                  </p>
                  {ctMonitorRuntimeLoading ? (
                    <div className="text-center py-4">
                      <Spinner animation="border" />
                    </div>
                  ) : (
                    <>
                      <Form.Group className="mb-3">
                        <Form.Label>Domain refresh interval (seconds)</Form.Label>
                        <Form.Control
                          type="number"
                          min={1}
                          value={ctMonitorRuntime.domain_refresh_interval}
                          onChange={(e) =>
                            setCtMonitorRuntime({ ...ctMonitorRuntime, domain_refresh_interval: e.target.value })
                          }
                        />
                        <Form.Text className="text-muted">How often ct-monitor reloads program config from the API.</Form.Text>
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <Form.Label>Stats log interval (seconds)</Form.Label>
                        <Form.Control
                          type="number"
                          min={1}
                          value={ctMonitorRuntime.stats_interval}
                          onChange={(e) =>
                            setCtMonitorRuntime({ ...ctMonitorRuntime, stats_interval: e.target.value })
                          }
                        />
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <Form.Label>CT poll interval (seconds)</Form.Label>
                        <Form.Control
                          type="number"
                          min={1}
                          value={ctMonitorRuntime.ct_poll_interval}
                          onChange={(e) =>
                            setCtMonitorRuntime({ ...ctMonitorRuntime, ct_poll_interval: e.target.value })
                          }
                        />
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <Form.Label>CT batch size</Form.Label>
                        <Form.Control
                          type="number"
                          min={1}
                          value={ctMonitorRuntime.ct_batch_size}
                          onChange={(e) =>
                            setCtMonitorRuntime({ ...ctMonitorRuntime, ct_batch_size: e.target.value })
                          }
                        />
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <Form.Label>Max entries per poll</Form.Label>
                        <Form.Control
                          type="number"
                          min={1}
                          value={ctMonitorRuntime.ct_max_entries_per_poll}
                          onChange={(e) =>
                            setCtMonitorRuntime({ ...ctMonitorRuntime, ct_max_entries_per_poll: e.target.value })
                          }
                        />
                      </Form.Group>
                      <Form.Group className="mb-0">
                        <Form.Label>CT start offset</Form.Label>
                        <Form.Control
                          type="number"
                          min={0}
                          value={ctMonitorRuntime.ct_start_offset}
                          onChange={(e) =>
                            setCtMonitorRuntime({ ...ctMonitorRuntime, ct_start_offset: e.target.value })
                          }
                        />
                        <Form.Text className="text-muted">
                          Entries behind log head on startup (0 in production). Changing this restarts CT ingestion.
                        </Form.Text>
                      </Form.Group>
                    </>
                  )}
                </Card.Body>
              </Card>
            </Tab>

            <Tab eventKey="ai" title="AI settings">
              <Card className="mb-4">
                <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                  <h5 className="mb-0">AI settings</h5>
                  <div>
                    <Button
                      variant="outline-secondary"
                      size="sm"
                      className="me-2"
                      onClick={loadAiSettings}
                      disabled={aiSettingsLoading}
                    >
                      {aiSettingsLoading ? <Spinner animation="border" size="sm" /> : 'Refresh'}
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleSaveAiSettings}
                      disabled={aiSettingsSaving}
                    >
                      {aiSettingsSaving ? (
                        <>
                          <Spinner animation="border" size="sm" className="me-2" />
                          Saving...
                        </>
                      ) : (
                        'Save all'
                      )}
                    </Button>
                  </div>
                </Card.Header>
                <Card.Body>
                  <Alert variant="info" className="mb-4">
                    <strong>How the Ollama message is built:</strong> The API sends a 2-message array. <strong>System</strong> = Default Prompt + Rules and Mapping. <strong>User</strong> = User Message Prefix (with {'{RESPONSE_FORMAT_SUFFIX}'} replaced) + the finding&apos;s enrichment data (DNS, WHOIS, HTTP probes, screenshot text), which is appended automatically.
                  </Alert>
                  {aiSettingsLoading ? (
                    <div className="text-center py-4">
                      <Spinner animation="border" />
                      <p className="mt-2 text-muted">Loading AI settings...</p>
                    </div>
                  ) : Object.keys(aiEditForm).length > 0 ? (
                    <Tabs defaultActiveKey={Object.keys(aiEditForm)[0]} className="mb-0">
                      {Object.entries(aiEditForm).map(([featureKey, featureData]) => (
                        <Tab
                          eventKey={featureKey}
                          title={FEATURE_LABELS[featureKey] || featureKey}
                          key={featureKey}
                        >
                          {['default_prompt', 'rules_and_mapping_instructions', 'response_format_suffix', 'user_content_prefix'].map((fieldKey) => (
                            <Form.Group className="mb-4" key={fieldKey}>
                              <Form.Label>{FIELD_LABELS[fieldKey] || fieldKey}</Form.Label>
                              <Form.Control
                                as="textarea"
                                rows={fieldKey === 'default_prompt' || fieldKey === 'rules_and_mapping_instructions' ? 8 : 6}
                                value={featureData?.[fieldKey] ?? ''}
                                onChange={(e) => handleAiFieldChange(featureKey, fieldKey, e.target.value)}
                                className="font-monospace"
                                style={{ fontSize: '0.9rem' }}
                              />
                              <Form.Text className="text-muted">
                                {FIELD_HELP[fieldKey]}
                              </Form.Text>
                            </Form.Group>
                          ))}
                          <Button
                            variant="outline-warning"
                            size="sm"
                            onClick={() => handleResetAiSettings(featureKey)}
                            disabled={aiSettingsSaving}
                          >
                            Reset to defaults
                          </Button>
                        </Tab>
                      ))}
                    </Tabs>
                  ) : (
                    <p className="text-muted text-center py-4 mb-0">No AI features configured. Settings will use in-code defaults.</p>
                  )}
                </Card.Body>
              </Card>
            </Tab>
          </Tabs>
        </Col>
      </Row>

      {/* Create Modal */}
      <Modal show={showCreateModal} onHide={() => setShowCreateModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Add Recon Task Parameters</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleCreateTask}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Recon Task Name</Form.Label>
              <Form.Control
                type="text"
                value={createForm.recon_task}
                onChange={(e) => setCreateForm({...createForm, recon_task: e.target.value})}
                placeholder="e.g., resolve_domain"
                required
              />
              <Form.Text className="text-muted">
                Enter the name of the recon task (e.g., resolve_domain, port_scan, nuclei_scan)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Last Execution Threshold (hours)</Form.Label>
              <Form.Control
                type="number"
                min="1"
                value={createForm.last_execution_threshold}
                onChange={(e) => setCreateForm({...createForm, last_execution_threshold: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Minimum hours to wait before re-executing this task on the same target
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Timeout (seconds)</Form.Label>
              <Form.Control
                type="number"
                min="1"
                value={createForm.timeout}
                onChange={(e) => setCreateForm({...createForm, timeout: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Maximum time to wait for task completion
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Max Retries</Form.Label>
              <Form.Control
                type="number"
                min="0"
                value={createForm.max_retries}
                onChange={(e) => setCreateForm({...createForm, max_retries: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Maximum number of retry attempts for failed tasks
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Chunk Size</Form.Label>
              <Form.Control
                type="number"
                min="1"
                value={createForm.chunk_size}
                onChange={(e) => setCreateForm({...createForm, chunk_size: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Number of items to process in each chunk (affects parallelization)
              </Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Creating...
                </>
              ) : (
                'Create Parameters'
              )}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal show={showEditModal} onHide={() => setShowEditModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Edit Recon Task Parameters</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleEditTask}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Recon Task</Form.Label>
              <Form.Control
                type="text"
                value={selectedTask?.recon_task || ''}
                disabled
                className="bg-light"
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Last Execution Threshold (hours)</Form.Label>
              <Form.Control
                type="number"
                min="1"
                value={editForm.last_execution_threshold}
                onChange={(e) => setEditForm({...editForm, last_execution_threshold: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Minimum hours to wait before re-executing this task on the same target
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Timeout (seconds)</Form.Label>
              <Form.Control
                type="number"
                min="1"
                value={editForm.timeout}
                onChange={(e) => setEditForm({...editForm, timeout: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Maximum time to wait for task completion
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Max Retries</Form.Label>
              <Form.Control
                type="number"
                min="0"
                value={editForm.max_retries}
                onChange={(e) => setEditForm({...editForm, max_retries: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Maximum number of retry attempts for failed tasks
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Chunk Size</Form.Label>
              <Form.Control
                type="number"
                min="1"
                value={editForm.chunk_size}
                onChange={(e) => setEditForm({...editForm, chunk_size: parseInt(e.target.value)})}
                required
              />
              <Form.Text className="text-muted">
                Number of items to process in each chunk (affects parallelization)
              </Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Updating...
                </>
              ) : (
                'Update Parameters'
              )}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* AWS Create Modal */}
      <Modal show={showAwsCreateModal} onHide={() => setShowAwsCreateModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Add AWS Credential</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleCreateAwsCredential}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Name</Form.Label>
              <Form.Control
                type="text"
                value={awsCreateForm.name}
                onChange={(e) => setAwsCreateForm({...awsCreateForm, name: e.target.value})}
                placeholder="e.g., Production AWS Account"
                required
              />
              <Form.Text className="text-muted">
                A descriptive name for this credential set
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Access Key ID</Form.Label>
              <Form.Control
                type="text"
                value={awsCreateForm.access_key}
                onChange={(e) => setAwsCreateForm({...awsCreateForm, access_key: e.target.value})}
                placeholder="AKIA..."
                required
              />
              <Form.Text className="text-muted">
                Your AWS access key ID (starts with AKIA)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Secret Access Key</Form.Label>
              <Form.Control
                type="password"
                value={awsCreateForm.secret_access_key}
                onChange={(e) => setAwsCreateForm({...awsCreateForm, secret_access_key: e.target.value})}
                placeholder="Enter secret access key"
                required
              />
              <Form.Text className="text-muted">
                Your AWS secret access key (kept secure)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Default Region</Form.Label>
              <Form.Control
                type="text"
                value={awsCreateForm.default_region}
                onChange={(e) => setAwsCreateForm({...awsCreateForm, default_region: e.target.value})}
                placeholder="us-east-1"
                required
              />
              <Form.Text className="text-muted">
                Default AWS region (e.g., us-east-1, eu-west-1)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Active"
                checked={awsCreateForm.is_active}
                onChange={(e) => setAwsCreateForm({...awsCreateForm, is_active: e.target.checked})}
              />
              <Form.Text className="text-muted">
                Whether this credential set is active
              </Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowAwsCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Creating...
                </>
              ) : (
                'Create Credential'
              )}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* AWS Edit Modal */}
      <Modal show={showAwsEditModal} onHide={() => setShowAwsEditModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Edit AWS Credential</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleEditAwsCredential}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Name</Form.Label>
              <Form.Control
                type="text"
                value={awsEditForm.name}
                onChange={(e) => setAwsEditForm({...awsEditForm, name: e.target.value})}
                placeholder="e.g., Production AWS Account"
                required
              />
              <Form.Text className="text-muted">
                A descriptive name for this credential set
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Access Key ID</Form.Label>
              <Form.Control
                type="text"
                value={awsEditForm.access_key}
                onChange={(e) => setAwsEditForm({...awsEditForm, access_key: e.target.value})}
                placeholder="AKIA..."
                required
              />
              <Form.Text className="text-muted">
                Your AWS access key ID (starts with AKIA)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Secret Access Key</Form.Label>
              <Form.Control
                type="password"
                value={awsEditForm.secret_access_key}
                onChange={(e) => setAwsEditForm({...awsEditForm, secret_access_key: e.target.value})}
                placeholder="Enter secret access key"
                required
              />
              <Form.Text className="text-muted">
                Your AWS secret access key (kept secure)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Default Region</Form.Label>
              <Form.Control
                type="text"
                value={awsEditForm.default_region}
                onChange={(e) => setAwsEditForm({...awsEditForm, default_region: e.target.value})}
                placeholder="us-east-1"
                required
              />
              <Form.Text className="text-muted">
                Default AWS region (e.g., us-east-1, eu-west-1)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Active"
                checked={awsEditForm.is_active}
                onChange={(e) => setAwsEditForm({...awsEditForm, is_active: e.target.checked})}
              />
              <Form.Text className="text-muted">
                Whether this credential set is active
              </Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowAwsEditModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Updating...
                </>
              ) : (
                'Update Credential'
              )}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </Container>
  );
}

export default SystemSettings; 