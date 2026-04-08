/* eslint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Container, Row, Col, Card, Form, Button, Alert, Spinner
} from 'react-bootstrap';
import { workflowAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { useAuth } from '../../contexts/AuthContext';
import VisualWorkflowBuilder from '../../components/VisualWorkflowBuilder';
import { useWorkflowStore } from '../../stores/workflowStore';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function WorkflowCreate() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const isEdit = Boolean(workflowId);
  
  // Use program filter context
  const { selectedProgram, programs, loading: programsLoading } = useProgramFilter();
  
  // Use auth context to check superuser status
  const { isSuperuser } = useAuth();
  
  // Workflow data
  const [workflowName, setWorkflowName] = useState('');
  const [programName, setProgramName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [steps, setSteps] = useState([]);
  const [isGlobalWorkflow, setIsGlobalWorkflow] = useState(false);
  
  // UI state
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  const {
    convertWorkflowToNodes, 
    clearWorkflow,
    getWorkflowPayload,
  } = useWorkflowStore();

  usePageTitle(
    isEdit ? formatPageTitle(workflowName || undefined, 'Edit Workflow') : formatPageTitle('Create Workflow')
  );

  useEffect(() => {
    if (isEdit) {
      loadWorkflow();
    } else {
      initializeNewWorkflow();
    }
  }, [workflowId, isEdit]);
  
  // Pre-select the currently selected program from navigation
  useEffect(() => {
    if (selectedProgram && !isEdit) {
      setProgramName(selectedProgram);
      setIsGlobalWorkflow(false);
    }
  }, [selectedProgram, isEdit]);


  const initializeNewWorkflow = () => {
    setWorkflowName('');
    setProgramName('');
    setWorkflowDescription('');
    setSteps([]);
    setIsGlobalWorkflow(false);
    clearWorkflow();
  };

  const loadWorkflow = async () => {
    try {
      setLoading(true);
      const workflow = await workflowAPI.getWorkflow(workflowId);
      

      
      // Handle both old format (definition wrapper) and new format (separate fields)
      let steps = workflow.steps || [];
      let inputs = workflow.inputs || {};
      let variables = workflow.variables || {};
      let description = workflow.description || '';
      
      // If using old format with definition wrapper
      if (workflow.definition) {
        const definition = workflow.definition;
        steps = definition.steps || steps;
        inputs = definition.inputs || inputs;
        variables = definition.variables || variables;
        description = definition.description || description;
      }
      
      setWorkflowName(workflow.name || '');
      setProgramName(workflow.program_name || '');
      setWorkflowDescription(description);
      setSteps(steps);
      
      // Check if this is a global workflow
      const isGlobal = !workflow.program_name;
      setIsGlobalWorkflow(isGlobal);
      
      // If non-superuser is trying to edit a global workflow, show error
      if (isGlobal && !isSuperuser) {
        setError('Only superusers can edit global workflows');
        return;
      }
      
      // Directly load the fetched definition into the store
      convertWorkflowToNodes({
        workflow_name: workflow.name || '',
        description: description,
        steps: steps,
        variables: variables,
        inputs: inputs,
      });

      setError(null);
    } catch (err) {
      setError('Failed to load workflow: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const generateAndSyncPayload = useCallback(() => {
    // Sync local state (name, description) to the store right before generation
    useWorkflowStore.setState({ 
      workflowName: workflowName, 
      workflowDescription: workflowDescription,
      programName: isGlobalWorkflow ? null : programName,
    });
    
    // Generate the full payload from the store's state
    return getWorkflowPayload();
  }, [workflowName, workflowDescription, programName, isGlobalWorkflow, getWorkflowPayload]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const payload = generateAndSyncPayload();
      
      const validationError = validateFormWithSteps(payload.steps);
      if (validationError) {
        setError(validationError);
        setSaving(false);
        return;
      }

      if (isEdit) {
        await workflowAPI.updateWorkflow(workflowId, payload);
        setSuccess('Workflow updated successfully!');
      } else {
        await workflowAPI.saveWorkflow(payload);
        setSuccess('Workflow created successfully!');
      }
      
      setTimeout(() => {
        navigate('/workflows/list');
      }, 1500);

    } catch (err) {
      setError(`Failed to save workflow: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };


  const validateFormWithSteps = (stepsToValidate) => {
    if (!workflowName.trim()) {
      return 'Workflow name is required';
    }
    if (!isGlobalWorkflow && !programName.trim()) {
      return 'Program name is required for program-specific workflows';
    }
    if (!stepsToValidate || stepsToValidate.length === 0) {
      // Allow saving with no steps if inputs are defined for starting a workflow
      return null;
    }
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      if (!step.name.trim()) {
        return `Step ${i + 1} must have a valid name.`;
      }
      if (!step.tasks || step.tasks.length === 0) {
        return `Step ${i + 1} must have at least one task.`;
      }
      for (let j = 0; j < step.tasks.length; j++) {
        const task = step.tasks[j];
        if (!task.name.trim() || !task.task_type.trim()) {
          return `Task ${j + 1} in step ${i + 1} must have a unique name and a valid type.`;
        }
      }
    }
    return null;
  };

  const handleGlobalToggle = (checked) => {
    // Only allow superusers to enable global workflows
    if (checked && !isSuperuser) {
      return;
    }
    
    setIsGlobalWorkflow(checked);
    if (checked) {
      setProgramName(''); // Clear program when making global
    } else if (selectedProgram) {
      setProgramName(selectedProgram); // Restore selected program
    }
  };

  if (loading && isEdit) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading workflow...</p>
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
              <h1>{isEdit ? '✏️ Edit Workflow' : '🆕 Create New Workflow'}</h1>
              <p className="text-muted">
                {isEdit ? 'Modify an existing workflow' : 'Create a new workflow using the visual builder'}
              </p>
            </div>
            <Button variant="outline-secondary" onClick={() => navigate('/workflows/list')}>
              ← Back to Workflows
            </Button>
          </div>
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

      {/* Builder Card */}
      <Card>
        <Card.Header>
          <Row>
            <Col md={6}>
              <Form.Group className="mb-2">
                <Form.Check
                  type="switch"
                  id="global-workflow-switch"
                  label="🌍 Global Workflow (visible to everyone)"
                  checked={isGlobalWorkflow}
                  onChange={(e) => handleGlobalToggle(e.target.checked)}
                  disabled={!isSuperuser}
                />
                <Form.Text className="text-muted">
                  {!isSuperuser 
                    ? 'Only superusers can create global workflows' 
                    : isGlobalWorkflow 
                      ? 'This workflow will be visible to all users' 
                      : 'This workflow will only be visible to users with program access'}
                </Form.Text>
              </Form.Group>
              
              {!isGlobalWorkflow && (
                <Form.Group>
                  <Form.Label className="mb-0"><small>Program Name *</small></Form.Label>
                  <Form.Control
                    as="select"
                    size="sm"
                    value={programName}
                    onChange={(e) => setProgramName(e.target.value)}
                    disabled={programsLoading}
                  >
                    <option value="">Select a program</option>
                    {programs.map(program => {
                      const name = typeof program === 'string' ? program : program.name;
                      return (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      );
                    })}
                  </Form.Control>
                  {programsLoading && <Form.Text className="text-muted">Loading programs...</Form.Text>}
                </Form.Group>
              )}
            </Col>
            <Col md={6}>
              <div className="d-flex justify-content-end align-items-end h-100">
                <Button variant="outline-secondary" size="sm" className="me-2" onClick={() => navigate('/workflows/list')}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={saving}
                  onClick={handleSubmit}
                >
                  {saving ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-2" />
                      {isEdit ? 'Updating...' : 'Creating...'}
                    </>
                  ) : (
                    <>{isEdit ? '💾 Update Workflow' : '✨ Create Workflow'}</>
                  )}
                </Button>
              </div>
            </Col>
          </Row>
        </Card.Header>
        <Card.Body className="p-2">
            <div style={{ height: 'calc(100vh - 300px)', border: '1px solid var(--bs-border-color)', borderRadius: '0.375rem' }}>
              <VisualWorkflowBuilder
                workflowName={workflowName}
                setWorkflowName={setWorkflowName}
                workflowDescription={workflowDescription}
                setWorkflowDescription={setWorkflowDescription}
              />
            </div>
        </Card.Body>
      </Card>
    </Container>
  );
}

export default WorkflowCreate;