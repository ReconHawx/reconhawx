import React, { useState } from 'react';
import { Form, Button, Alert } from 'react-bootstrap';
import { useWorkflowStore } from '../../stores/workflowStore';

const StepManagementPanel = () => {
  const { steps, addStep, updateStepName, removeStep } = useWorkflowStore();
  const [editingStepId, setEditingStepId] = useState(null);
  const [editingName, setEditingName] = useState('');

  const handleStartEdit = (step) => {
    setEditingStepId(step.id);
    setEditingName(step.name);
  };

  const handleSaveEdit = () => {
    if (editingStepId && editingName.trim()) {
      updateStepName(editingStepId, editingName.trim());
    }
    setEditingStepId(null);
    setEditingName('');
  };

  const handleCancelEdit = () => {
    setEditingStepId(null);
    setEditingName('');
  };

  return (
    <div className="workflow-steps-panel" style={{
      position: 'absolute',
      right: '20px',
      top: '100px',
      borderRadius: '8px',
      padding: '15px',
      minWidth: '200px',
      maxHeight: '60vh',
      overflowY: 'auto',
      zIndex: 1000
    }}>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h6 className="mb-0">📋 Workflow Steps</h6>
        <Button
          variant="success"
          size="sm"
          onClick={addStep}
          title="Add New Step"
        >
          ➕
        </Button>
      </div>

      <div className="d-grid gap-2">
        {steps.map((step, index) => (
          <div
            key={step.id}
            className={`workflow-step-item ${index % 2 === 0 ? 'step-even' : 'step-odd'}`}
            style={{
              padding: '10px',
              borderRadius: '6px'
            }}
          >
            {editingStepId === step.id ? (
              <div className="d-flex flex-column gap-2">
                <Form.Control
                  size="sm"
                  type="text"
                  value={editingName}
                  onChange={(e) => setEditingName(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter') handleSaveEdit();
                    if (e.key === 'Escape') handleCancelEdit();
                  }}
                  autoFocus
                />
                <div className="d-flex gap-1">
                  <Button
                    variant="success"
                    size="sm"
                    onClick={handleSaveEdit}
                    style={{ fontSize: '10px' }}
                  >
                    ✓
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleCancelEdit}
                    style={{ fontSize: '10px' }}
                  >
                    ✕
                  </Button>
                </div>
              </div>
            ) : (
              <div className="d-flex justify-content-between align-items-center">
                <div>
                  <div className="fw-bold" style={{ fontSize: '12px' }}>
                    {step.name}
                  </div>
                  <small className="text-muted">
                    Step {index + 1}
                  </small>
                </div>
                <div className="d-flex gap-1">
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={() => handleStartEdit(step)}
                    style={{ fontSize: '10px', padding: '2px 6px' }}
                    title="Rename Step"
                  >
                    ✏️
                  </Button>
                  {steps.length > 1 && (
                    <Button
                      variant="outline-danger"
                      size="sm"
                      onClick={() => removeStep(step.id)}
                      style={{ fontSize: '10px', padding: '2px 6px' }}
                      title="Remove Step"
                    >
                      🗑️
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <Alert variant="info" className="mt-3 mb-0" style={{ fontSize: '11px' }}>
        <strong>Tips:</strong><br/>
        • Drag tasks into step areas<br/>
        • Tasks snap to steps automatically<br/>
        • Steps execute sequentially<br/>
        • Each step can have multiple parallel tasks
      </Alert>
    </div>
  );
};

export default StepManagementPanel;