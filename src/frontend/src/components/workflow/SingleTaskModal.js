import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  Form,
  Row,
  Col,
  Button,
  Alert,
  Spinner
} from 'react-bootstrap';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { workflowAPI, programAPI } from '../../services/api';
import { TASK_TYPES } from './constants';
import ProgramAssetSelector from './ProgramAssetSelector';
import TaskParameterSelector from './TaskParameterSelector';

function SingleTaskModal({ show, onHide, onSuccess }) {
  const { selectedProgram, programs } = useProgramFilter();

  // Form state
  const [selectedProgramName, setSelectedProgramName] = useState('');
  const [selectedTask, setSelectedTask] = useState('');
  const [inputSourceType, setInputSourceType] = useState('direct'); // 'direct', 'program_asset', or 'program_protected_domains'
  const [inputType, setInputType] = useState('domains');
  const [inputValues, setInputValues] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Program asset configuration
  const [assetType, setAssetType] = useState('');
  const [assetFilter, setAssetFilter] = useState('');
  const [assetFilterType, setAssetFilterType] = useState('');
  const [assetLimit, setAssetLimit] = useState(100);
  const [minSimilarityPercent, setMinSimilarityPercent] = useState('');

  // Nuclei templates state
  const [selectedTreeTemplates, setSelectedTreeTemplates] = useState(new Set());
  const [selectedCustomTemplates, setSelectedCustomTemplates] = useState([]);

  // Wordlist state
  const [selectedWordlist, setSelectedWordlist] = useState(null);
  const [customWordlistUrl, setCustomWordlistUrl] = useState('');
  const [wordlistInputType, setWordlistInputType] = useState('database');

  // Output mode state for fuzz_website
  const [outputMode, setOutputMode] = useState('');

  // Proxy state for fuzz_website
  const [useProxy, setUseProxy] = useState(false);

  // Task parameters state
  const [taskParams, setTaskParams] = useState({});

  // Force execution state
  const [forceExecution, setForceExecution] = useState(false);

  // Available programs state
  const [availablePrograms, setAvailablePrograms] = useState([]);
  const [programsLoading, setProgramsLoading] = useState(false);

  // Available tasks
  const availableTasks = Object.keys(TASK_TYPES);

  // Input type options
  const inputTypeOptions = [
    { value: 'domains', label: 'Domains' },
    { value: 'urls', label: 'URLs' },
    { value: 'ips', label: 'IP Addresses' },
    { value: 'cidrs', label: 'CIDR blocks' }
  ];

  // Helper to extract program name from string or object
  const getProgramName = (program) => {
    return typeof program === 'string' ? program : program?.name || '';
  };

  const loadPrograms = useCallback(async () => {
    if (programs.length > 0) {
      // Use programs from context if available - extract names if objects
      const programNames = programs.map(getProgramName).filter(Boolean);
      setAvailablePrograms(programNames);
      return;
    }

    try {
      setProgramsLoading(true);
      const response = await programAPI.getAll();
      if (response.status === 'success' && response.programs) {
        // Handle both array of strings and array of objects
        const programNames = response.programs.map(getProgramName).filter(Boolean);
        setAvailablePrograms(programNames);
        setSelectedProgramName(programNames[0] || '');
      }
    } catch (err) {
      console.error('Error loading programs:', err);
      setAvailablePrograms([]);
    } finally {
      setProgramsLoading(false);
    }
  }, [programs]);



  useEffect(() => {
    if (show) {
      loadPrograms();
      // Set default program from context
      if (selectedProgram && programs.length > 0) {
        setSelectedProgramName(selectedProgram);
      }
    }
  }, [show, selectedProgram, programs, loadPrograms]);



  const handleTaskChange = (taskType) => {
    setSelectedTask(taskType);

    // Reset nuclei template selections if switching away from nuclei_scan
    if (taskType !== 'nuclei_scan') {
      setSelectedTreeTemplates(new Set());
      setSelectedCustomTemplates([]);
    }

    // Reset wordlist selections and output mode if switching away from fuzz_website
    if (taskType !== 'fuzz_website') {
      setSelectedWordlist(null);
      setCustomWordlistUrl('');
      setWordlistInputType('database');
      setOutputMode('');
    }

    // Reset proxy if switching to a task that doesn't support it
    if (taskType !== 'fuzz_website' && taskType !== 'nuclei_scan' && taskType !== 'crawl_website') {
      setUseProxy(false);
    }

    // Reset task parameters
    setTaskParams({});

    // Auto-set input type based on task's primary input
    const taskConfig = TASK_TYPES[taskType];
    if (taskConfig && taskConfig.inputs && taskConfig.inputs.length > 0) {
      const primaryInput = taskConfig.inputs[0];
      // Map task input types to our input type options
      if (primaryInput === 'domains') {
        setInputType('domains');
      } else if (primaryInput === 'urls') {
        setInputType('urls');
      } else if (primaryInput === 'ips') {
        setInputType('ips');
      } else if (primaryInput === 'cidrs') {
        setInputType('cidrs');
      }
    }
  };

  const constructWorkflowData = () => {
    // Start with the task parameters from the state
    let finalTaskParams = { ...taskParams };
    
    // Remove empty/null/undefined timeout to use system default
    if (finalTaskParams.timeout === undefined || finalTaskParams.timeout === null || finalTaskParams.timeout === '') {
      delete finalTaskParams.timeout;
    }

    // Add nuclei template configuration if nuclei_scan is selected
    if (selectedTask === 'nuclei_scan') {
      const allOfficialTemplates = Array.from(selectedTreeTemplates);

      finalTaskParams.template = {
        official: allOfficialTemplates,
        custom: selectedCustomTemplates
      };
    }

    // Add wordlist configuration if fuzz_website is selected
    if (selectedTask === 'fuzz_website') {
      if (wordlistInputType === 'url') {
        finalTaskParams.wordlist = customWordlistUrl;
      } else if (selectedWordlist) {
        finalTaskParams.wordlist = selectedWordlist.id; // Pass the wordlist ID instead of filename
      } else {
        finalTaskParams.wordlist = '/workspace/files/webcontent_test.txt'; // Default
      }
    }

    // Build inputs based on source type
    let inputsConfig;
    if (inputSourceType === 'direct') {
      // Parse input values (one per line, trim whitespace)
      const values = inputValues
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);

      if (values.length === 0) {
        throw new Error('Please enter at least one input value');
      }

      inputsConfig = {
        "type": "direct",
        "values": values,
        "value_type": inputType
      };
    } else if (inputSourceType === 'program_protected_domains') {
      inputsConfig = {
        "type": "program_protected_domains"
      };
    } else if (inputSourceType === 'program_scope_domains') {
      inputsConfig = {
        "type": "program_scope_domains"
      };
    } else if (inputSourceType === 'program_asset') {
      if (!assetType) {
        throw new Error('Please select an asset type');
      }

      // Auto-convert to program_finding if typosquat_url, typosquat_domain, typosquat_apex_domain, or external_link is selected
      if (assetType === 'typosquat_url' || assetType === 'external_link' || 
          assetType === 'typosquat_domain' || assetType === 'typosquat_apex_domain') {
        inputsConfig = {
          "type": "program_finding",
          "finding_type": assetType,
          "limit": assetLimit
        };
      } else {
        inputsConfig = {
          "type": "program_asset",
          "asset_type": assetType,
          "limit": assetLimit
        };
      }

      if (assetFilter.trim()) {
        inputsConfig.filter = assetFilter.trim();
      }

      if (assetFilterType) {
        inputsConfig.filter_type = assetFilterType;
      }

      if ((assetType === 'typosquat_domain' || assetType === 'typosquat_apex_domain') && minSimilarityPercent !== '') {
        const pct = Number(minSimilarityPercent);
        if (!Number.isNaN(pct) && pct >= 0 && pct <= 100) {
          inputsConfig.min_similarity_percent = pct;
        }
      }
    }

    // Build task definition - input_mapping key: for direct use inputType; for program_protected_domains/program_scope_domains use 'domains'; for program_asset use assetType
    const inputMappingKey = inputSourceType === 'direct' ? inputType :
      inputSourceType === 'program_protected_domains' || inputSourceType === 'program_scope_domains' ? 'domains' : assetType;
    const taskDefinition = {
      "name": selectedTask,
      "force": forceExecution,
      "params": finalTaskParams,
      "task_type": selectedTask,
      "input_mapping": {
        [inputMappingKey]: "inputs.input_1"
      }
    };

    // Add output_mode at task level for fuzz_website and dns_bruteforce
    if ((selectedTask === 'fuzz_website' || selectedTask === 'dns_bruteforce') && outputMode) {
      taskDefinition.output_mode = outputMode;
    }

    // Add use_proxy at task level if enabled (for tasks that support it)
    if (useProxy) {
      taskDefinition.use_proxy = true;
    }

    const workflowData = {
      "workflow_name": `Single Task Run - ${selectedTask}`,
      "program_name": selectedProgramName,
      "description": `Single Task Run - ${selectedTask}`,
      "steps": [
        {
          "name": "step_1",
          "tasks": [taskDefinition]
        }
      ],
      "variables": {},
      "inputs": {
        "input_1": inputsConfig
      }
    };

    return workflowData;
  };

  const handleRunTask = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);

      // Validate form
      if (!selectedProgramName) {
        throw new Error('Please select a program');
      }
      if (!selectedTask) {
        throw new Error('Please select a task');
      }

      // Validate inputs based on source type
      if (inputSourceType === 'direct') {
        if (!inputValues.trim()) {
          throw new Error('Please enter input values');
        }
      } else if (inputSourceType === 'program_asset') {
        if (!assetType) {
          throw new Error('Please select an asset type');
        }
      }
      // program_protected_domains needs no additional validation

      // Construct workflow data
      const workflowData = constructWorkflowData();

      // Run the workflow
      const response = await workflowAPI.runWorkflow(workflowData);

      if (response.status === 'success' || response.workflow_id) {
        setSuccess(`Single task workflow started successfully! Workflow ID: ${response.workflow_id || response.data?.workflow_id || 'N/A'}`);

        // Call success callback if provided
        if (onSuccess) {
          onSuccess(response);
        }

        // Close modal after a short delay
        setTimeout(() => {
          handleClose();
        }, 2000);
      } else {
        throw new Error(response.message || 'Failed to run workflow');
      }
    } catch (err) {
      console.error('Error running single task:', err);
      setError(err.message || 'Failed to run single task');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    // Reset form state
    setSelectedProgramName('');
    setSelectedTask('');
    setInputSourceType('direct');
    setInputType('domains');
    setInputValues('');
    setError(null);
    setSuccess(null);

    // Reset nuclei template state
    setSelectedTreeTemplates(new Set());
    setSelectedCustomTemplates([]);

    // Reset wordlist state
    setSelectedWordlist(null);
    setCustomWordlistUrl('');
    setWordlistInputType('database');

    // Reset output mode
    setOutputMode('');

    // Reset proxy state
    setUseProxy(false);

    // Reset program asset state
    setAssetType('');
    setAssetFilter('');
    setAssetFilterType('');
    setAssetLimit(100);
    setMinSimilarityPercent('');

    // Reset task parameters
    setTaskParams({});

    // Reset force execution
    setForceExecution(false);

    onHide();
  };

  const getTaskDescription = (taskType) => {
    const task = TASK_TYPES[taskType];
    return task ? task.description : '';
  };

  const getTaskCategory = (taskType) => {
    const task = TASK_TYPES[taskType];
    return task ? task.category : '';
  };

  return (
    <Modal show={show} onHide={handleClose} size="lg">
      <Modal.Header closeButton>
        <Modal.Title>🔧 Run Single Task</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <Form>
          {error && (
            <Alert variant="danger" className="mb-3">
              {error}
            </Alert>
          )}

          {success && (
            <Alert variant="success" className="mb-3">
              {success}
            </Alert>
          )}

          <Row className="mb-3">
            <Col md={6}>
              <Form.Group>
                <Form.Label>Target Program *</Form.Label>
                <Form.Select
                  value={selectedProgramName}
                  onChange={(e) => setSelectedProgramName(e.target.value)}
                  disabled={programsLoading}
                  required
                >
                  <option value="">
                    {programsLoading ? 'Loading programs...' : 'Choose a program...'}
                  </option>
                  {availablePrograms.map((program) => (
                    <option key={program} value={program}>
                      {program}
                    </option>
                  ))}
                </Form.Select>
                <Form.Text className="text-muted">
                  Program where the task will be executed
                </Form.Text>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group>
                <Form.Label>Task Type *</Form.Label>
                <Form.Select
                  value={selectedTask}
                  onChange={(e) => handleTaskChange(e.target.value)}
                  required
                >
                  <option value="">Choose a task...</option>
                  {availableTasks.map((taskType) => {
                    const task = TASK_TYPES[taskType];
                    return (
                      <option key={taskType} value={taskType}>
                        {task.name} ({task.category})
                      </option>
                    );
                  })}
                </Form.Select>
                {selectedTask && (
                  <Form.Text className="text-muted">
                    {getTaskDescription(selectedTask)}
                  </Form.Text>
                )}
              </Form.Group>
            </Col>
          </Row>

          <Row className="mb-3">
            <Col md={6}>
              <Form.Group>
                <Form.Label>Input Source *</Form.Label>
                <Form.Select
                  value={inputSourceType}
                  onChange={(e) => setInputSourceType(e.target.value)}
                  required
                >
                  <option value="direct">Direct Input</option>
                  <option value="program_asset">Program Assets / Findings</option>
                  <option value="program_protected_domains">Program Protected Domains</option>
                  <option value="program_scope_domains">Program Scope Domains</option>
                </Form.Select>
                <Form.Text className="text-muted">
                  Direct values, program assets/findings, protected domains, or scope domains from domain regex
                </Form.Text>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group>
                <Form.Check
                  type="checkbox"
                  id="forceExecution"
                  label="Force Execution"
                  checked={forceExecution}
                  onChange={(e) => setForceExecution(e.target.checked)}
                />
                <Form.Text className="text-muted">
                  Force task execution even if it has already been run
                </Form.Text>
              </Form.Group>
            </Col>
          </Row>

          {inputSourceType === 'direct' && (
            <>
              <Row className="mb-3">
                <Col md={6}>
                  <Form.Group>
                    <Form.Label>Input Type *</Form.Label>
                    <Form.Select
                      value={inputType}
                      onChange={(e) => setInputType(e.target.value)}
                      required
                    >
                      {inputTypeOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Form.Select>
                    <Form.Text className="text-muted">
                      Type of input data for the task
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>

              <Row className="mb-3">
                <Col>
                  <Form.Group>
                    <Form.Label>Input Values *</Form.Label>
                    <Form.Control
                      as="textarea"
                      rows={6}
                      placeholder={`Enter ${inputType} (one per line):${inputType === 'domains' ? '\nexample.com\nsubdomain.example.com' : inputType === 'urls' ? '\nhttps://example.com\nhttp://test.com' : inputType === 'cidrs' ? '\n192.168.0.0/24\n10.0.0.0/16' : '\n192.168.1.1\n10.0.0.1'}`}
                      value={inputValues}
                      onChange={(e) => setInputValues(e.target.value)}
                      required
                    />
                    <Form.Text className="text-muted">
                      Enter one {inputType.slice(0, -1)} per line. The task will process each input.
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>
            </>
          )}

          {inputSourceType === 'program_protected_domains' && (
            <Alert variant="info" className="mb-3">
              This will use the program&apos;s protected domain list (apex domains) as input. No additional configuration needed.
            </Alert>
          )}

          {inputSourceType === 'program_scope_domains' && (
            <Alert variant="info" className="mb-3">
              This will use apex domains extracted from the program&apos;s domain regex (in-scope patterns) as input. No additional configuration needed.
            </Alert>
          )}

          {inputSourceType === 'program_asset' && (
            <Row className="mb-4">
              <Col>
                <ProgramAssetSelector
                  assetType={assetType}
                  filter={assetFilter}
                  filterType={assetFilterType}
                  limit={assetLimit}
                  minSimilarityPercent={minSimilarityPercent}
                  onMinSimilarityPercentChange={(v) => setMinSimilarityPercent(v)}
                  onAssetTypeChange={(newAssetType) => {
                    if (newAssetType !== 'typosquat_domain' && newAssetType !== 'typosquat_apex_domain' &&
                        !String(newAssetType).startsWith('typosquat_domain') && !String(newAssetType).startsWith('typosquat_apex_domain')) {
                      setMinSimilarityPercent('');
                    }
                    setAssetType(newAssetType);
                  }}
                  onFilterChange={setAssetFilter}
                  onFilterTypeChange={setAssetFilterType}
                  onLimitChange={setAssetLimit}
                  onAssetAndFilterChange={(type, filter) => {
                    if (type !== 'typosquat_domain' && type !== 'typosquat_apex_domain') {
                      setMinSimilarityPercent('');
                    }
                    setAssetType(type);
                    setAssetFilterType(filter);
                  }}
                />
              </Col>
            </Row>
          )}

          {/* Task Parameters - Show for all tasks that have parameters */}
          {selectedTask && TASK_TYPES[selectedTask]?.params && Object.keys(TASK_TYPES[selectedTask].params).length > 0 && (
            <Row className="mb-4">
              <Col>
                <TaskParameterSelector
                  taskType={selectedTask}
                  taskParams={taskParams}
                  onParameterChange={setTaskParams}
                  // Nuclei template props
                  selectedOfficialTemplates={selectedTreeTemplates}
                  selectedCustomTemplates={selectedCustomTemplates}
                  onOfficialTemplatesChange={setSelectedTreeTemplates}
                  onCustomTemplatesChange={setSelectedCustomTemplates}
                  // Wordlist props
                  selectedWordlist={selectedWordlist}
                  customWordlistUrl={customWordlistUrl}
                  wordlistInputType={wordlistInputType}
                  onWordlistChange={setSelectedWordlist}
                  onCustomUrlChange={setCustomWordlistUrl}
                  onInputTypeChange={setWordlistInputType}
                  // Output mode props
                  outputMode={outputMode}
                  onOutputModeChange={setOutputMode}
                />
              </Col>
            </Row>
          )}

          {/* Proxy Option - Show for tasks that support proxying */}
          {(selectedTask === 'fuzz_website' || selectedTask === 'nuclei_scan' || selectedTask === 'crawl_website') && (
            <Row className="mb-3">
              <Col>
                <Form.Group>
                  <Form.Check
                    type="checkbox"
                    id="useProxy"
                    label="Use AWS API Gateway Proxy (FireProx)"
                    checked={useProxy}
                    onChange={(e) => setUseProxy(e.target.checked)}
                  />
                  <Form.Text className="text-muted">
                    Route {selectedTask === 'fuzz_website' ? 'fuzzing' : selectedTask === 'nuclei_scan' ? 'scanning' : 'crawling'} requests through AWS API Gateway proxies to mask reconnaissance traffic
                  </Form.Text>
                </Form.Group>
              </Col>
            </Row>
          )}

          {selectedTask && (
            <Alert variant="info">
              <strong>Task Details:</strong>
              <br />
              <strong>Name:</strong> {TASK_TYPES[selectedTask].name}
              <br />
              <strong>Category:</strong> {getTaskCategory(selectedTask)}
              <br />
              <strong>Description:</strong> {getTaskDescription(selectedTask)}
              <br />
              <strong>Expected Inputs:</strong> {TASK_TYPES[selectedTask].inputs.join(', ')}
              <br />
              <strong>Expected Outputs:</strong> {TASK_TYPES[selectedTask].outputs.join(', ')}
            </Alert>
          )}
        </Form>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={handleClose}>
          Cancel
        </Button>
                  <Button
            variant="success"
            onClick={handleRunTask}
            disabled={loading || !selectedProgramName || !selectedTask ||
              (inputSourceType === 'direct' && !inputValues.trim()) ||
              (inputSourceType === 'program_asset' && !assetType)}
          >
          {loading ? (
            <>
              <Spinner animation="border" size="sm" className="me-2" />
              Running...
            </>
          ) : (
            <>
              ▶️ Run Task
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

export default SingleTaskModal;
