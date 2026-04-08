import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Container, Row, Col, Card, Button, Form, Alert, Spinner, Badge, Nav } from 'react-bootstrap';
import { workflowAPI, programAPI } from '../../services/api';
import JsonEditor from '../../components/JsonEditor';
import VariableInput from '../../components/VariableInput';
import VisualWorkflowBuilder from '../../components/VisualWorkflowBuilder';
import { validateVariables, processTemplate } from '../../utils/workflowTemplates';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function WorkflowRun() {
  const { workflowId } = useParams();
  const [workflows, setWorkflows] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState('');
  const [selectedProgram, setSelectedProgram] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [workflowDetails, setWorkflowDetails] = useState(null);
  const [workflowMode, setWorkflowMode] = useState('saved'); // 'saved', 'custom', or 'visual'
  const [customWorkflowJson, setCustomWorkflowJson] = useState('');
  const [customWorkflowName, setCustomWorkflowName] = useState('');
  const [workflowVariables, setWorkflowVariables] = useState({});
  const [variableValues, setVariableValues] = useState({});
  const [variableErrors, setVariableErrors] = useState({});

  // Visual builder state
  const [visualWorkflowName, setVisualWorkflowName] = useState('');
  const [visualWorkflowDescription, setVisualWorkflowDescription] = useState('');
  const [visualSteps, setVisualSteps] = useState([]);
  const [visualVariables, setVisualVariables] = useState({});
  const [visualInputs, setVisualInputs] = useState({});
  const [visualWorkflowJson, setVisualWorkflowJson] = useState('');

  usePageTitle(formatPageTitle(workflowDetails?.name, 'Run Workflow'));

  // Default template for custom workflows
  const defaultWorkflowTemplate = JSON.stringify({
    "description": "Basic domain enumeration workflow",
    "steps": [
      {
        "name": "resolve_domains",
        "type": "resolve_domain",
        "input": ["example.com"],
        "params": {}
      }
    ]
  }, null, 2);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    // Set default template when switching to custom mode
    if (workflowMode === 'custom') {
      setCustomWorkflowJson(prev => {
        // Only set default template if current value is empty
        return prev || defaultWorkflowTemplate;
      });
    }
  }, [workflowMode, defaultWorkflowTemplate]);

  // Update visual workflow JSON when visual mode data changes
  useEffect(() => {
    if (workflowMode === 'visual') {
      const workflowData = {
        workflow_name: visualWorkflowName,
        program_name: selectedProgram,
        description: visualWorkflowDescription,
        steps: visualSteps,
        variables: visualVariables,
        inputs: visualInputs,
      };
      setVisualWorkflowJson(JSON.stringify(workflowData, null, 2));
    }
  }, [visualWorkflowName, visualWorkflowDescription, visualSteps, visualVariables, visualInputs, selectedProgram, workflowMode]);

  useEffect(() => {
    if (workflowId && workflows.length > 0) {
      setSelectedWorkflow(workflowId);
      const workflow = workflows.find(w => w.id === workflowId);
      if (workflow) {
        setWorkflowDetails(workflow);
        // Don't auto-set program for global workflows
        if (workflow.program_name) {
          setSelectedProgram(workflow.program_name);
        }
        
        // Load full workflow to get variables (same logic as handleWorkflowChange)
        const loadWorkflowVariables = async () => {
          try {
            const fullWorkflow = await workflowAPI.getWorkflow(workflowId);
    
            
                    // Handle both old format (definition wrapper) and new format (separate fields)
        let variables = fullWorkflow.variables || {};
        
        // If using old format with definition wrapper
        if (fullWorkflow.definition) {
          variables = fullWorkflow.definition.variables || variables;
        }
            
            if (variables && Object.keys(variables).length > 0) {
              setWorkflowVariables(variables);
              
              // Set default values for variables
              const defaultValues = {};
              Object.entries(variables).forEach(([varName, varDef]) => {
                defaultValues[varName] = varDef.value || varDef.default || '';
              });
              setVariableValues(defaultValues);
            } else {
              setWorkflowVariables({});
              setVariableValues({});
            }
            setVariableErrors({});
          } catch (err) {
            console.error('Failed to load workflow variables (initial):', err);
            setWorkflowVariables({});
            setVariableValues({});
          }
        };
        
        loadWorkflowVariables();
      }
    }
  }, [workflowId, workflows]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [workflowsResponse, programsResponse] = await Promise.all([
        workflowAPI.getWorkflows(),
        programAPI.getAll()
      ]);
      
      setWorkflows(workflowsResponse.workflows || []);
      setPrograms(programsResponse.programs || []);
      setError(null);
    } catch (err) {
      setError('Failed to load data: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleWorkflowChange = async (e) => {
    const workflowId = e.target.value;
    setSelectedWorkflow(workflowId);
    
    if (workflowId) {
      const workflow = workflows.find(w => w.id === workflowId);
      setWorkflowDetails(workflow);
      // Don't auto-set program for global workflows
      if (workflow && workflow.program_name) {
        setSelectedProgram(workflow.program_name);
      }
      
      // Load full workflow to get variables
      try {
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
        } else {
          setWorkflowVariables({});
          setVariableValues({});
        }
        setVariableErrors({});
      } catch (err) {
        console.error('Failed to load workflow variables:', err);
        setWorkflowVariables({});
        setVariableValues({});
      }
    } else {
      setWorkflowDetails(null);
      setWorkflowVariables({});
      setVariableValues({});
      setVariableErrors({});
    }
  };

  const handleRunWorkflow = async (e) => {
    e.preventDefault();
    
    if (!selectedProgram) {
      setError('Please select a target program for workflow execution');
      return;
    }

    try {
      setRunning(true);
      setError(null);
      setSuccess(null);
      setVariableErrors({});
      
      let workflowData;
      
      if (workflowMode === 'saved') {
        if (!selectedWorkflow) {
          setError('Please select a workflow');
          return;
        }
        
        const workflow = workflows.find(w => w.id === selectedWorkflow);
        if (!workflow) {
          setError('Selected workflow not found');
          return;
        }
        
        // First, fetch the complete workflow definition from the database
        const fullWorkflow = await workflowAPI.getWorkflow(workflow.id);

        
        // Handle both old format (definition wrapper) and new format (separate fields)
        let steps = fullWorkflow.steps || [];
        let variables = fullWorkflow.variables || {};
        let inputs = fullWorkflow.inputs || {};
        let description = fullWorkflow.description || '';
        
        // If using old format with definition wrapper
        if (fullWorkflow.definition) {
          const definition = fullWorkflow.definition;
          steps = definition.steps || steps;
          variables = definition.variables || variables;
          inputs = definition.inputs || inputs;
          description = definition.description || description;
        }
        
        // Handle steps structure - steps might be wrapped in a "steps" object
        if (steps && typeof steps === 'object' && !Array.isArray(steps)) {
          if (steps.steps && Array.isArray(steps.steps)) {
            steps = steps.steps;
          }
        }
        
        // Ensure variables and inputs are properly structured
        // Variables should be an object with variable names as keys
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
        
        // Ensure inputs is properly structured
        if (inputs && typeof inputs === 'object') {
          // If inputs is an array, convert it to object format
          if (Array.isArray(inputs)) {
            const convertedInputs = {};
            inputs.forEach((inputDef, index) => {
              if (typeof inputDef === 'string') {
                convertedInputs[inputDef] = { type: 'direct', value_type: 'strings' };
              } else if (typeof inputDef === 'object') {
                convertedInputs[inputDef.name || `input_${index}`] = inputDef;
              }
            });
            inputs = convertedInputs;
          }
        }
        
        // Create the complete workflow data to send to API
        let workflowTemplate = {
          workflow_name: fullWorkflow.name,
          program_name: selectedProgram, // Use the selected program instead of saved one
          description: description,
          steps: steps,
          variables: variables,
          inputs: inputs,
          workflow_definition_id: workflow.id // Include the workflow definition ID for saved workflows
        };
        
        // If workflow has variables, validate and process them
        if (variables && Object.keys(variables).length > 0) {
          
          // Process any remaining array values that might be strings
          const processedVariableValues = { ...variableValues };
          Object.entries(variables).forEach(([varName, varDef]) => {
            if (varDef.type === 'array' && typeof processedVariableValues[varName] === 'string') {
              processedVariableValues[varName] = processedVariableValues[varName]
                .split(',')
                .map(item => item.trim())
                .filter(item => item !== '');
            }
          });
          
          
          const validation = validateVariables(workflowTemplate, processedVariableValues);
          
          if (!validation.success) {
            const errors = {};
            validation.errors.forEach(error => {
              // Extract variable name from error message
              const match = error.match(/Variable "([^"]+)"/);
              if (match) {
                errors[match[1]] = error;
              }
            });
            setVariableErrors(errors);
            setError(`Please fill in all required variables: ${validation.errors.join(', ')}`);
            return;
          }
          
          // Process template with variable values
          const processedTemplate = processTemplate(workflowTemplate, processedVariableValues);
          
          // Update variables with user-provided values
          const variablesWithValues = { ...variables };
          Object.entries(processedVariableValues).forEach(([varName, value]) => {
            if (variablesWithValues[varName]) {
              variablesWithValues[varName] = {
                ...variablesWithValues[varName],
                value: value
              };
            }
          });
          
          // Ensure inputs and variables are preserved after template processing
          workflowData = {
            workflow_name: processedTemplate.workflow_name || workflowTemplate.workflow_name,
            program_name: processedTemplate.program_name || workflowTemplate.program_name,
            description: processedTemplate.description || workflowTemplate.description,
            steps: processedTemplate.steps || workflowTemplate.steps,
            inputs: processedTemplate.inputs || inputs, // Use processed inputs with variable values resolved
            variables: variablesWithValues, // Include variables with user-provided values
            workflow_definition_id: workflowTemplate.workflow_definition_id // Always preserve workflow definition ID
          };
        } else {
          // Ensure inputs and variables are preserved even when no variables are present
          workflowData = {
            ...workflowTemplate,
            inputs: inputs,
            variables: variables,
            workflow_definition_id: workflowTemplate.workflow_definition_id // Always preserve workflow definition ID
          };
        }
      } else if (workflowMode === 'custom') {
        // Custom workflow mode
        if (!customWorkflowJson.trim() || !customWorkflowName.trim()) {
          setError('Please provide both workflow name and JSON definition');
          return;
        }
        
        try {
          const parsedWorkflow = JSON.parse(customWorkflowJson);
          workflowData = {
            workflow_name: customWorkflowName,
            program_name: selectedProgram,
            description: parsedWorkflow.description || undefined,
            steps: parsedWorkflow.steps || [],
            variables: parsedWorkflow.variables || {},
            inputs: parsedWorkflow.inputs || {}
          };
        } catch (parseError) {
          setError('Invalid JSON format: ' + parseError.message);
          return;
        }
      } else {
        // Visual workflow mode
        if (!visualWorkflowName.trim()) {
          setError('Please provide a workflow name');
          return;
        }
        
        if (visualSteps.length === 0 || visualSteps.every(step => step.tasks.length === 0)) {
          setError('Please add at least one step with tasks');
          return;
        }
        
        workflowData = {
          workflow_name: visualWorkflowName,
          program_name: selectedProgram,
          description: visualWorkflowDescription,
          steps: visualSteps,
          variables: visualVariables,
          inputs: visualInputs,
        };
      }
      

      
      // Send the complete workflow definition to the API
      const response = await workflowAPI.runWorkflow(workflowData);
      setSuccess(`Workflow "${workflowData.workflow_name}" started successfully! Workflow ID: ${response.workflow_id || 'N/A'}`);
    } catch (err) {
      setError('Failed to run workflow: ' + err.message);
    } finally {
      setRunning(false);
    }
  };

  const handleModeChange = (mode) => {
    setWorkflowMode(mode);
    setError(null);
    setSuccess(null);
    if (mode === 'custom') {
      setSelectedWorkflow('');
      setWorkflowDetails(null);
      // Set default template if switching to custom mode and no JSON exists
      if (!customWorkflowJson) {
        setCustomWorkflowJson(defaultWorkflowTemplate);
      }
    } else if (mode === 'visual') {
      setSelectedWorkflow('');
      setWorkflowDetails(null);
      // Reset visual workflow state to defaults
      setVisualWorkflowName('');
      setVisualWorkflowDescription('');
      setVisualSteps([{ name: '', tasks: [] }]);
      setVisualVariables({});
      setVisualInputs({});
    } else {
      setCustomWorkflowJson('');
      setCustomWorkflowName('');
    }
  };

  const loadSavedWorkflowToEditor = async (workflowId) => {
    if (!workflowId) return;
    
    try {
      // Fetch the complete workflow definition
      const fullWorkflow = await workflowAPI.getWorkflow(workflowId);
      
      // Handle both old format (definition wrapper) and new format (separate fields)
      let steps = fullWorkflow.steps || [];
      let description = fullWorkflow.description || '';
      
      // If using old format with definition wrapper
      if (fullWorkflow.definition) {
        const definition = fullWorkflow.definition;
        steps = definition.steps || steps;
        description = definition.description || description;
      }
      
      // Handle steps structure - steps might be wrapped in a "steps" object
      if (steps && typeof steps === 'object' && !Array.isArray(steps)) {
        if (steps.steps && Array.isArray(steps.steps)) {
          steps = steps.steps;
        }
      }
      
      // Create the workflow JSON structure expected by the custom mode
      const workflowJson = {
        description: description || fullWorkflow.name || 'Loaded workflow',
        steps: steps
      };
      
      // Load into the custom editor
      setCustomWorkflowJson(JSON.stringify(workflowJson, null, 2));
      setCustomWorkflowName(fullWorkflow.name || 'Loaded Workflow');
      setError(null);
    } catch (err) {
      setError('Failed to load workflow to editor: ' + err.message);
    }
  };

  const validateAndPreviewCustomWorkflow = () => {
    if (!customWorkflowJson.trim()) return null;
    
    try {
      const parsed = JSON.parse(customWorkflowJson);
      return parsed;
    } catch (e) {
      return null;
    }
  };

  const getWorkflowScope = (workflow) => {
    if (!workflow.program_name) {
      return { badge: '🌍 Global', variant: 'success', tooltip: 'Visible to all users' };
    }
    return { badge: workflow.program_name, variant: 'primary', tooltip: 'Program-specific workflow' };
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading workflows and programs...</p>
        </div>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <h1>▶️ Run Workflow</h1>
          <p className="text-muted">Execute a saved workflow or run a custom JSON workflow definition against a target program</p>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" dismissible onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Row>
        <Col md={8}>

          <Card>
            <Card.Header>
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">Workflow Execution</h5>
                <Nav variant="tabs" className="border-0">
                  <Nav.Item>
                    <Nav.Link 
                      active={workflowMode === 'saved'} 
                      onClick={() => handleModeChange('saved')}
                      className="py-1 px-3"
                    >
                      💾 Saved Workflows
                    </Nav.Link>
                  </Nav.Item>
                  <Nav.Item>
                    <Nav.Link 
                      active={workflowMode === 'visual'} 
                      onClick={() => handleModeChange('visual')}
                      className="py-1 px-3"
                    >
                      🎨 Visual Builder
                    </Nav.Link>
                  </Nav.Item>
                  <Nav.Item>
                    <Nav.Link 
                      active={workflowMode === 'custom'} 
                      onClick={() => handleModeChange('custom')}
                      className="py-1 px-3"
                    >
                      📝 Custom JSON
                    </Nav.Link>
                  </Nav.Item>
                </Nav>
              </div>
            </Card.Header>
            <Card.Body>
              <Form onSubmit={handleRunWorkflow}>
                {workflowMode === 'saved' ? (
                  <>
                    <Row>
                      <Col md={6}>
                        <Form.Group className="mb-3">
                          <Form.Label>Select Workflow</Form.Label>
                          <Form.Select
                            value={selectedWorkflow}
                            onChange={handleWorkflowChange}
                            required
                          >
                            <option value="">Choose a workflow...</option>
                            {workflows.map((workflow) => {
                              const scope = getWorkflowScope(workflow);
                              return (
                                <option key={workflow.id} value={workflow.id}>
                                  {workflow.name} {scope.badge}
                                  {/* Show if workflow has variables */}
                                  {(workflow.variables && Object.keys(workflow.variables).length > 0) && ' 📝'}
                                </option>
                              );
                            })}
                          </Form.Select>
                        </Form.Group>
                      </Col>
                      <Col md={6}>
                        <Form.Group className="mb-3">
                          <Form.Label>Target Program *</Form.Label>
                          <Form.Select
                            value={selectedProgram}
                            onChange={(e) => setSelectedProgram(e.target.value)}
                            required
                          >
                            <option value="">Choose a program...</option>
                            {programs.map((program) => {
                              const name = typeof program === 'string' ? program : program.name;
                              return (
                                <option key={name} value={name}>
                                  {name}
                                </option>
                              );
                            })}
                          </Form.Select>
                          <Form.Text className="text-muted">
                            Program where the workflow will be executed
                          </Form.Text>
                        </Form.Group>
                      </Col>
                    </Row>
                    
                    {Object.keys(workflowVariables).length > 0 && (
                      <div className="mt-3">
                        <VariableInput
                          variables={workflowVariables}
                          values={variableValues}
                          onVariableChange={setVariableValues}
                          errors={variableErrors}
                        />
                      </div>
                    )}
                  </>
                ) : workflowMode === 'visual' ? (
                  <>
                    {/* Program Name Selection */}
                    <Row className="mb-4">
                      <Col md={6}>
                        <Form.Group className="mb-3">
                          <Form.Label>Target Program *</Form.Label>
                          <Form.Select
                            value={selectedProgram}
                            onChange={(e) => setSelectedProgram(e.target.value)}
                            required
                          >
                            <option value="">Choose a program...</option>
                            {programs.map((program) => {
                              const name = typeof program === 'string' ? program : program.name;
                              return (
                                <option key={name} value={name}>
                                  {name}
                                </option>
                              );
                            })}
                          </Form.Select>
                          <Form.Text className="text-muted">
                            Program where the workflow will be executed
                          </Form.Text>
                        </Form.Group>
                      </Col>
                    </Row>

                    <div style={{ height: '70vh', border: '1px solid var(--bs-border-color)', borderRadius: '0.375rem', position: 'relative' }}>
                      <VisualWorkflowBuilder
                        workflowName={visualWorkflowName}
                        setWorkflowName={setVisualWorkflowName}
                        workflowDescription={visualWorkflowDescription}
                        setWorkflowDescription={setVisualWorkflowDescription}
                        steps={visualSteps}
                        setSteps={setVisualSteps}
                        variables={visualVariables}
                        setVariables={setVisualVariables}
                        inputs={visualInputs}
                        setInputs={setVisualInputs}
                        workflowJson={visualWorkflowJson}
                        setWorkflowJson={setVisualWorkflowJson}
                        showJsonPreview={false}
                        showVariableManager={false}
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <Row className="mb-3">
                      <Col md={4}>
                        <Form.Group>
                          <Form.Label>Workflow Name</Form.Label>
                          <Form.Control
                            type="text"
                            placeholder="Enter workflow name..."
                            value={customWorkflowName}
                            onChange={(e) => setCustomWorkflowName(e.target.value)}
                            required
                          />
                        </Form.Group>
                      </Col>
                      <Col md={4}>
                        <Form.Group>
                          <Form.Label>Target Program *</Form.Label>
                          <Form.Select
                            value={selectedProgram}
                            onChange={(e) => setSelectedProgram(e.target.value)}
                            required
                          >
                            <option value="">Choose a program...</option>
                            {programs.map((program) => {
                              const name = typeof program === 'string' ? program : program.name;
                              return (
                                <option key={name} value={name}>
                                  {name}
                                </option>
                              );
                            })}
                          </Form.Select>
                          <Form.Text className="text-muted">
                            Program where the workflow will be executed
                          </Form.Text>
                        </Form.Group>
                      </Col>
                      <Col md={4}>
                        <Form.Group>
                          <Form.Label>Load from Saved Workflow</Form.Label>
                          <div className="d-flex">
                            <Form.Select
                              onChange={(e) => {
                                if (e.target.value) {
                                  loadSavedWorkflowToEditor(e.target.value);
                                  e.target.value = ''; // Reset selection
                                }
                              }}
                            >
                              <option value="">-- Load template --</option>
                              {workflows.map((workflow) => {
                                const scope = getWorkflowScope(workflow);
                                return (
                                  <option key={workflow.id} value={workflow.id}>
                                    {workflow.name} {scope.badge}
                                  </option>
                                );
                              })}
                            </Form.Select>
                          </div>
                          <Form.Text className="text-muted">
                            Load a saved workflow as template
                          </Form.Text>
                        </Form.Group>
                      </Col>
                    </Row>
                    <JsonEditor
                      value={customWorkflowJson}
                      onChange={setCustomWorkflowJson}
                      height="400px"
                      className="mb-3"
                    />
                  </>
                )}

                <div className="d-flex justify-content-between align-items-center">
                  <Button
                    type="submit"
                    variant="success"
                    disabled={running || !selectedProgram || 
                             (workflowMode === 'saved' && !selectedWorkflow) || 
                             (workflowMode === 'custom' && (!customWorkflowName || !customWorkflowJson)) ||
                             (workflowMode === 'visual' && (!visualWorkflowName || visualSteps.every(step => step.tasks.length === 0)))}
                  >
                    {running ? (
                      <>
                        <Spinner animation="border" size="sm" className="me-2" />
                        Running Workflow...
                      </>
                    ) : (
                      <>▶️ Run Workflow</>
                    )}
                  </Button>
                  
                  <Button variant="outline-secondary" href="/workflows/status">
                    📊 View Status
                  </Button>
                </div>
              </Form>
            </Card.Body>
          </Card>
        </Col>

        <Col md={4}>
          {(workflowMode === 'saved' && workflowDetails) && (
            <Card>
              <Card.Header>
                <h6 className="mb-0">Workflow Details</h6>
              </Card.Header>
              <Card.Body>
                <dl className="row mb-0">
                  <dt className="col-sm-4">Name:</dt>
                  <dd className="col-sm-8">{workflowDetails.name}</dd>
                  
                  <dt className="col-sm-4">Scope:</dt>
                  <dd className="col-sm-8">
                    {(() => {
                      const scope = getWorkflowScope(workflowDetails);
                      return (
                        <Badge bg={scope.variant} title={scope.tooltip}>
                          {scope.badge}
                        </Badge>
                      );
                    })()}
                  </dd>
                  
                  <dt className="col-sm-4">Steps:</dt>
                  <dd className="col-sm-8">
                    <Badge bg="info">
                      {workflowDetails.steps ? workflowDetails.steps.length : 0} steps
                    </Badge>
                  </dd>
                  
                  <dt className="col-sm-4">Total Tasks:</dt>
                  <dd className="col-sm-8">
                    <Badge bg="success">
                      {workflowDetails.steps ? 
                        workflowDetails.steps.reduce((total, step) => 
                          total + (step.tasks ? step.tasks.length : 0), 0
                        ) : 0} tasks
                    </Badge>
                  </dd>
                  
                  <dt className="col-sm-4">Description:</dt>
                  <dd className="col-sm-8">
                    <small className="text-muted">
                      {workflowDetails.description || 'No description available'}
                    </small>
                  </dd>
                </dl>

                {workflowDetails.steps && workflowDetails.steps.length > 0 && (
                  <div className="mt-3">
                    <h6>Steps & Tasks:</h6>
                    <ul className="list-unstyled">
                      {workflowDetails.steps.map((step, stepIndex) => (
                        <li key={stepIndex} className="mb-2">
                          <div>
                            <Badge bg="primary" className="me-1">
                              Step {stepIndex + 1}
                            </Badge>
                            <small className="fw-bold">{step.name || 'Unnamed Step'}</small>
                          </div>
                          {step.tasks && step.tasks.length > 0 && (
                            <ul className="list-unstyled ms-3 mt-1">
                              {step.tasks.map((task, taskIndex) => (
                                <li key={taskIndex} className="mb-1">
                                  <Badge bg="light" text="dark" className="me-1">
                                    {task.task_type || task.type || 'unknown'}
                                  </Badge>
                                  <small>{task.name}</small>
                                  {task.input_mapping && (
                                    <div className="ms-2 mt-1">
                                      <small className="text-muted">
                                        📥 Inputs: {Object.entries(task.input_mapping).map(([key, value]) => `${key}→${value}`).join(', ')}
                                      </small>
                                    </div>
                                  )}
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {workflowDetails.inputs && Object.keys(workflowDetails.inputs).length > 0 && (
                  <div className="mt-3">
                    <h6>Workflow Inputs:</h6>
                    <ul className="list-unstyled">
                      {Object.entries(workflowDetails.inputs).map(([inputName, inputDef]) => (
                        <li key={inputName} className="mb-1">
                          <Badge bg="info" className="me-1">
                            {inputDef.type}
                          </Badge>
                          <small className="fw-bold">{inputName}</small>
                          {inputDef.type === 'direct' && inputDef.values && (
                            <div className="ms-2">
                              <small className="text-muted">
                                Values: {Array.isArray(inputDef.values) ? inputDef.values.join(', ') : inputDef.values}
                              </small>
                            </div>
                          )}
                          {inputDef.type === 'program_asset' && (
                            <div className="ms-2">
                              <small className="text-muted">
                                Asset Type: {inputDef.asset_type}
                                {inputDef.limit && ` (limit: ${inputDef.limit})`}
                                {inputDef.filter && ` (filter: ${inputDef.filter})`}
                              </small>
                            </div>
                          )}
                          {inputDef.type === 'program_protected_domains' && (
                            <div className="ms-2">
                              <small className="text-muted">Program&apos;s protected domain list</small>
                            </div>
                          )}
                          {inputDef.type === 'program_scope_domains' && (
                            <div className="ms-2">
                              <small className="text-muted">Apex domains from program&apos;s domain regex</small>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Card.Body>
            </Card>
          )}

          {workflowMode === 'visual' && (
            <Card>
              <Card.Header>
                <h6 className="mb-0">Workflow Preview</h6>
              </Card.Header>
              <Card.Body>
                <dl className="row mb-0">
                  <dt className="col-sm-4">Name:</dt>
                  <dd className="col-sm-8">{visualWorkflowName || 'Unnamed'}</dd>
                  
                  <dt className="col-sm-4">Program:</dt>
                  <dd className="col-sm-8">
                    <Badge bg="primary">{selectedProgram || 'Not selected'}</Badge>
                  </dd>
                  
                  <dt className="col-sm-4">Steps:</dt>
                  <dd className="col-sm-8">
                    <Badge bg="info">
                      {visualSteps.length} steps
                    </Badge>
                  </dd>
                  
                  <dt className="col-sm-4">Total Tasks:</dt>
                  <dd className="col-sm-8">
                    <Badge bg="success">
                      {visualSteps.reduce((total, step) => total + step.tasks.length, 0)} tasks
                    </Badge>
                  </dd>
                  
                  <dt className="col-sm-4">Description:</dt>
                  <dd className="col-sm-8">
                    <small className="text-muted">
                      {visualWorkflowDescription || 'No description provided'}
                    </small>
                  </dd>
                </dl>

                {visualSteps.length > 0 && (
                  <div className="mt-3">
                    <h6>Steps Overview:</h6>
                    <ul className="list-unstyled">
                      {visualSteps.map((step, index) => (
                        <li key={index} className="mb-1">
                          <Badge bg="primary" className="me-1">
                            Step {index + 1}
                          </Badge>
                          <small>{step.name || 'Unnamed Step'}</small>
                          <Badge bg="light" text="dark" className="ms-1">
                            {step.tasks.length} tasks
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Card.Body>
            </Card>
          )}

          {workflowMode === 'custom' && customWorkflowJson && (
            <Card>
              <Card.Header>
                <h6 className="mb-0">Workflow Preview</h6>
              </Card.Header>
              <Card.Body>
                {(() => {
                  const preview = validateAndPreviewCustomWorkflow();
                  if (!preview) {
                    return (
                      <Alert variant="warning" className="mb-0">
                        <small>⚠️ Invalid JSON format</small>
                      </Alert>
                    );
                  }
                  
                  return (
                    <>
                      <dl className="row mb-0">
                        <dt className="col-sm-4">Name:</dt>
                        <dd className="col-sm-8">{customWorkflowName || 'Unnamed'}</dd>
                        
                        <dt className="col-sm-4">Program:</dt>
                        <dd className="col-sm-8">
                          <Badge bg="primary">{selectedProgram || 'Not selected'}</Badge>
                        </dd>
                        
                        <dt className="col-sm-4">Steps:</dt>
                        <dd className="col-sm-8">
                          <Badge bg="info">
                            {preview.steps ? preview.steps.length : 0} steps
                          </Badge>
                        </dd>
                        
                        <dt className="col-sm-4">Total Tasks:</dt>
                        <dd className="col-sm-8">
                          <Badge bg="success">
                            {preview.steps ? 
                              preview.steps.reduce((total, step) => {
                                // Handle new format with tasks array
                                if (step.tasks && Array.isArray(step.tasks)) {
                                  return total + step.tasks.length;
                                }
                                // Handle legacy format where step is a task
                                if (step.type) {
                                  return total + 1;
                                }
                                return total;
                              }, 0) : 0} tasks
                          </Badge>
                        </dd>
                        
                        <dt className="col-sm-4">Description:</dt>
                        <dd className="col-sm-8">
                          <small className="text-muted">
                            {preview.description || 'No description provided'}
                          </small>
                        </dd>
                      </dl>

                      {preview.steps && preview.steps.length > 0 && (
                        <div className="mt-3">
                          <h6>Steps & Tasks:</h6>
                          <ul className="list-unstyled">
                            {preview.steps.map((step, stepIndex) => (
                              <li key={stepIndex} className="mb-2">
                                <div>
                                  <Badge bg="primary" className="me-1">
                                    Step {stepIndex + 1}
                                  </Badge>
                                  <small className="fw-bold">{step.name || `Step ${stepIndex + 1}`}</small>
                                  {step.tasks && (
                                    <Badge bg="light" text="dark" className="ms-1">
                                      {step.tasks.length} tasks
                                    </Badge>
                                  )}
                                </div>
                                {step.tasks && step.tasks.length > 0 && (
                                  <ul className="list-unstyled ms-3 mt-1">
                                    {step.tasks.map((task, taskIndex) => (
                                      <li key={taskIndex} className="mb-1">
                                <Badge bg="light" text="dark" className="me-1">
                                          {task.task_type || task.type || 'unknown'}
                                </Badge>
                                        <small>{task.name}</small>
                                      </li>
                                    ))}
                                  </ul>
                                )}
                                {/* Handle legacy format where step has direct type */}
                                {step.type && !step.tasks && (
                                  <div className="ms-3 mt-1">
                                    <Badge bg="light" text="dark" className="me-1">
                                      {step.type}
                                    </Badge>
                                    <small>Legacy step format</small>
                                  </div>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {preview.inputs && Object.keys(preview.inputs).length > 0 && (
                        <div className="mt-3">
                          <h6>Workflow Inputs:</h6>
                          <ul className="list-unstyled">
                            {Object.entries(preview.inputs).map(([inputName, inputDef]) => (
                              <li key={inputName} className="mb-1">
                                <Badge bg="info" className="me-1">
                                  {inputDef.type || 'unknown'}
                                </Badge>
                                <small className="fw-bold">{inputName}</small>
                                {inputDef.type === 'direct' && inputDef.values && (
                                  <div className="ms-2">
                                    <small className="text-muted">
                                      Values: {Array.isArray(inputDef.values) ? inputDef.values.join(', ') : inputDef.values}
                                    </small>
                                  </div>
                                )}
                                {inputDef.type === 'program_asset' && (
                                  <div className="ms-2">
                                    <small className="text-muted">
                                      Asset Type: {inputDef.asset_type}
                                      {inputDef.limit && ` (limit: ${inputDef.limit})`}
                                    </small>
                                  </div>
                                )}
                                {inputDef.type === 'program_protected_domains' && (
                                  <div className="ms-2">
                                    <small className="text-muted">Program&apos;s protected domain list</small>
                                  </div>
                                )}
                                {inputDef.type === 'program_scope_domains' && (
                                  <div className="ms-2">
                                    <small className="text-muted">Apex domains from program&apos;s domain regex</small>
                                  </div>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  );
                })()}
              </Card.Body>
            </Card>
          )}
        </Col>
      </Row>
    </Container>
  );
}

export default WorkflowRun;