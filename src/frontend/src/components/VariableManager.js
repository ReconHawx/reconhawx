import React, { useState, useEffect } from 'react';
import { Form, Card, Row, Col, Button, Alert, Badge, Table, Modal } from 'react-bootstrap';
import { extractVariables, generateVariableDefinitions } from '../utils/workflowTemplates';

const VariableManager = ({ 
  workflowJson, 
  variables, 
  onVariablesChange, 
  showDetectedVariables = true 
}) => {
  const [localVariables, setLocalVariables] = useState(variables || {});
  const [detectedVariables, setDetectedVariables] = useState([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingVariable, setEditingVariable] = useState(null);
  const [newVariable, setNewVariable] = useState({
    name: '',
    type: 'string',
    description: '',
    required: true,
    default: ''
  });

  useEffect(() => {
    setLocalVariables(variables || {});
  }, [variables]);

  useEffect(() => {
    // Extract variables from workflow JSON
    if (workflowJson) {
      try {
        const parsed = JSON.parse(workflowJson);
        const detected = extractVariables(parsed);
        setDetectedVariables(detected);
      } catch (e) {
        setDetectedVariables([]);
      }
    }
  }, [workflowJson]);

  const handleAddVariable = () => {
    if (!newVariable.name.trim()) return;
    
    const updatedVariables = {
      ...localVariables,
      [newVariable.name]: {
        type: newVariable.type,
        description: newVariable.description,
        required: newVariable.required,
        default: newVariable.default
      }
    };
    
    setLocalVariables(updatedVariables);
    onVariablesChange(updatedVariables);
    setShowAddModal(false);
    setNewVariable({
      name: '',
      type: 'string',
      description: '',
      required: true,
      default: ''
    });
  };

  const handleEditVariable = (varName) => {
    setEditingVariable(varName);
    setNewVariable({
      name: varName,
      ...localVariables[varName]
    });
    setShowAddModal(true);
  };

  const handleUpdateVariable = () => {
    if (!newVariable.name.trim()) return;
    
    const updatedVariables = { ...localVariables };
    
    // If name changed, remove old entry
    if (editingVariable && editingVariable !== newVariable.name) {
      delete updatedVariables[editingVariable];
    }
    
    updatedVariables[newVariable.name] = {
      type: newVariable.type,
      description: newVariable.description,
      required: newVariable.required,
      default: newVariable.default
    };
    
    setLocalVariables(updatedVariables);
    onVariablesChange(updatedVariables);
    setShowAddModal(false);
    setEditingVariable(null);
    setNewVariable({
      name: '',
      type: 'string',
      description: '',
      required: true,
      default: ''
    });
  };

  const handleDeleteVariable = (varName) => {
    const updatedVariables = { ...localVariables };
    delete updatedVariables[varName];
    setLocalVariables(updatedVariables);
    onVariablesChange(updatedVariables);
  };

  const handleAutoGenerateVariables = () => {
    if (!workflowJson) return;
    
    try {
      const parsed = JSON.parse(workflowJson);
      const generated = generateVariableDefinitions(parsed, localVariables);
      setLocalVariables(generated);
      onVariablesChange(generated);
    } catch (e) {
      console.error('Error auto-generating variables:', e);
    }
  };

  const getTypeColor = (type) => {
    const colors = {
      string: 'primary',
      array: 'info',
      number: 'warning',
      boolean: 'success'
    };
    return colors[type] || 'secondary';
  };

  const renderDefaultValue = (varDef) => {
    if (varDef.type === 'array') {
      return Array.isArray(varDef.default) ? varDef.default.join(', ') : varDef.default;
    }
    return String(varDef.default);
  };

  return (
    <Card>
      <Card.Header>
        <div className="d-flex justify-content-between align-items-center">
          <h6 className="mb-0">
            🔧 Variable Definitions
            <Badge bg="secondary" className="ms-2">
              {Object.keys(localVariables).length} defined
            </Badge>
          </h6>
          <div>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={handleAutoGenerateVariables}
              className="me-2"
            >
              🔍 Auto-detect
            </Button>
            <Button
              variant="outline-primary"
              size="sm"
              onClick={() => setShowAddModal(true)}
            >
              ➕ Add Variable
            </Button>
          </div>
        </div>
      </Card.Header>
      <Card.Body>
        {showDetectedVariables && detectedVariables.length > 0 && (
          <Alert variant="info" className="mb-3">
            <strong>Detected Variables:</strong>{' '}
            {detectedVariables.map(varName => (
              <Badge key={varName} bg="info" className="me-1">
                {varName}
              </Badge>
            ))}
            <br />
            <small>
              These variables were found in your workflow JSON. 
              Click "Auto-detect" to generate definitions for them.
            </small>
          </Alert>
        )}

        {Object.keys(localVariables).length === 0 ? (
          <div className="text-center text-muted py-4">
            <p>No variables defined yet.</p>
            <p>
              <small>
                Use variables in your workflow JSON with the syntax: <code>{"{{variable_name}}"}</code>
              </small>
            </p>
          </div>
        ) : (
          <Table responsive>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Description</th>
                <th>Required</th>
                <th>Default</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(localVariables).map(([varName, varDef]) => (
                <tr key={varName}>
                  <td>
                    <code>{varName}</code>
                  </td>
                  <td>
                    <Badge bg={getTypeColor(varDef.type)}>
                      {varDef.type}
                    </Badge>
                  </td>
                  <td>{varDef.description || <span className="text-muted">No description</span>}</td>
                  <td>
                    <Badge bg={varDef.required ? 'danger' : 'secondary'}>
                      {varDef.required ? 'Required' : 'Optional'}
                    </Badge>
                  </td>
                  <td>
                    <code>{renderDefaultValue(varDef)}</code>
                  </td>
                  <td>
                    <Button
                      variant="outline-primary"
                      size="sm"
                      onClick={() => handleEditVariable(varName)}
                      className="me-1"
                    >
                      ✏️
                    </Button>
                    <Button
                      variant="outline-danger"
                      size="sm"
                      onClick={() => handleDeleteVariable(varName)}
                    >
                      🗑️
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card.Body>

      {/* Add/Edit Variable Modal */}
      <Modal show={showAddModal} onHide={() => setShowAddModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>
            {editingVariable ? 'Edit Variable' : 'Add Variable'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form>
            <Form.Group className="mb-3">
              <Form.Label>Variable Name</Form.Label>
              <Form.Control
                type="text"
                value={newVariable.name}
                onChange={(e) => setNewVariable({...newVariable, name: e.target.value})}
                placeholder="Enter variable name"
              />
              <Form.Text className="text-muted">
                Use in workflow JSON as: <code>{`{{${newVariable.name || 'variable_name'}}}`}</code>
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Type</Form.Label>
              <Form.Select
                value={newVariable.type}
                onChange={(e) => setNewVariable({...newVariable, type: e.target.value})}
              >
                <option value="string">String</option>
                <option value="array">Array</option>
                <option value="number">Number</option>
                <option value="boolean">Boolean</option>
              </Form.Select>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Description</Form.Label>
              <Form.Control
                type="text"
                value={newVariable.description}
                onChange={(e) => setNewVariable({...newVariable, description: e.target.value})}
                placeholder="Describe what this variable is for"
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Required"
                checked={newVariable.required}
                onChange={(e) => setNewVariable({...newVariable, required: e.target.checked})}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Default Value</Form.Label>
              {newVariable.type === 'array' ? (
                <Form.Control
                  type="text"
                  value={newVariable.default}
                  onChange={(e) => setNewVariable({...newVariable, default: e.target.value})}
                  placeholder="Enter comma-separated values"
                />
              ) : newVariable.type === 'boolean' ? (
                <Form.Select
                  value={newVariable.default}
                  onChange={(e) => setNewVariable({...newVariable, default: e.target.value === 'true'})}
                >
                  <option value="false">False</option>
                  <option value="true">True</option>
                </Form.Select>
              ) : (
                <Form.Control
                  type={newVariable.type === 'number' ? 'number' : 'text'}
                  value={newVariable.default}
                  onChange={(e) => setNewVariable({...newVariable, default: e.target.value})}
                  placeholder={`Enter default ${newVariable.type} value`}
                />
              )}
            </Form.Group>
          </Form>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowAddModal(false)}>
            Cancel
          </Button>
          <Button 
            variant="primary" 
            onClick={editingVariable ? handleUpdateVariable : handleAddVariable}
          >
            {editingVariable ? 'Update' : 'Add'} Variable
          </Button>
        </Modal.Footer>
      </Modal>
    </Card>
  );
};

export default VariableManager; 