import React from 'react';
import { Form, Button, Badge, Card, ListGroup, Alert } from 'react-bootstrap';
import './VariablesConfigSidebar.css';

function VariablesConfigSidebar({
  isOpen,
  onClose,
  currentVariables,
  editingVariable,
  setEditingVariable,
  handleAddVariable,
  handleUpdateVariable,
  handleSaveEditingVariable,
  handleRemoveVariable,
  handleSaveVariables,
}) {
  return (
    <>
      <div
        className={`variables-config-sidebar-overlay ${isOpen ? 'open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div className={`variables-config-sidebar ${isOpen ? 'open' : ''}`}>
        <div className="variables-config-sidebar-header">
          <h6 className="mb-0">Configure Variables</h6>
          <Button variant="link" size="sm" className="p-0 text-muted" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </div>
        <div className="variables-config-sidebar-body">
          <Alert variant="info" className="small py-2">
            Use Jinja2 in parameters and inputs (e.g. {'{{domain}}'}). Variables are auto-extracted from input values, or add them here.
          </Alert>

          {editingVariable ? (
            <Card className="mb-3">
              <Card.Header className="py-2">
                <small>{editingVariable.id.startsWith('new_') ? 'Add Variable' : `Edit: ${editingVariable.name}`}</small>
              </Card.Header>
              <Card.Body className="py-2">
                <Form.Group className="mb-2">
                  <Form.Label className="small">Name (unique)</Form.Label>
                  <Form.Control
                    size="sm"
                    type="text"
                    value={editingVariable.name}
                    onChange={(e) => handleUpdateVariable(editingVariable.id, 'name', e.target.value.replace(/\s/g, '_'))}
                    placeholder="e.g., domain"
                  />
                </Form.Group>
                <Form.Group className="mb-2">
                  <Form.Label className="small">Value</Form.Label>
                  <Form.Control
                    size="sm"
                    type="text"
                    value={editingVariable.value}
                    onChange={(e) => handleUpdateVariable(editingVariable.id, 'value', e.target.value)}
                    placeholder="e.g., example.com"
                  />
                </Form.Group>
                <Form.Group className="mb-2">
                  <Form.Label className="small">Description (optional)</Form.Label>
                  <Form.Control
                    size="sm"
                    type="text"
                    value={editingVariable.description || ''}
                    onChange={(e) => handleUpdateVariable(editingVariable.id, 'description', e.target.value)}
                    placeholder="Brief description"
                  />
                </Form.Group>
                <div className="d-flex justify-content-end gap-1 mt-2">
                  <Button variant="secondary" size="sm" onClick={() => setEditingVariable(null)}>Cancel</Button>
                  <Button variant="primary" size="sm" onClick={handleSaveEditingVariable}>Save</Button>
                </div>
              </Card.Body>
            </Card>
          ) : (
            <Button variant="success" size="sm" className="mb-3 w-100" onClick={handleAddVariable}>
              + Add Variable
            </Button>
          )}

          <ListGroup variant="flush">
            {Object.entries(currentVariables).map(([name, config]) => (
              <ListGroup.Item key={name} className="py-2 px-2">
                <div className="d-flex justify-content-between align-items-center">
                  <div className="small">
                    <strong>{name}</strong>
                    <Badge bg="info" className="ms-1">Variable</Badge>
                    {config.description && (
                      <div className="text-muted" style={{ fontSize: '11px' }}>{config.description}</div>
                    )}
                    <code className="d-block mt-1" style={{ fontSize: '11px' }}>{config.value || '(empty)'}</code>
                  </div>
                  <div>
                    <Button variant="outline-primary" size="sm" className="py-0 px-1 me-1" onClick={() => setEditingVariable({ id: name, name, ...config })} title="Edit">✏️</Button>
                    <Button variant="outline-danger" size="sm" className="py-0 px-1" onClick={() => handleRemoveVariable(name)} title="Remove">🗑️</Button>
                  </div>
                </div>
              </ListGroup.Item>
            ))}
          </ListGroup>

          {Object.keys(currentVariables).length === 0 && !editingVariable && (
            <Alert variant="warning" className="small py-2 mt-2">
              No variables defined. Use {'{{name}}'} in task parameters or input values.
            </Alert>
          )}
        </div>
        <div className="variables-config-sidebar-footer">
          <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
          <Button variant="primary" size="sm" onClick={handleSaveVariables}>Apply</Button>
        </div>
      </div>
    </>
  );
}

export default VariablesConfigSidebar;
