import React from 'react';
import { Form, Button, Spinner } from 'react-bootstrap';
import WorkflowBuilderMetadataBar from './WorkflowBuilderMetadataBar';

/**
 * Create/edit page only: global workflow + program + actions, plus name/description.
 * Single surface with inset dividers — not stacked floating panels above the canvas.
 */
function WorkflowBuilderEditorChrome({
  isSuperuser,
  isGlobalWorkflow,
  onGlobalToggle,
  programName,
  onProgramChange,
  programs,
  programsLoading,
  isEdit,
  saving,
  onCancel,
  onSave,
  workflowName,
  setWorkflowName,
  workflowDescription,
  setWorkflowDescription,
}) {
  return (
    <div className="workflow-builder-editor-chrome">
      <div className="workflow-builder-editor-chrome-toolbar">
        <div className="workflow-builder-editor-chrome-toolbar-main">
          <Form.Group className="mb-2 mb-md-0">
            <Form.Check
              type="switch"
              id="global-workflow-switch"
              label="🌍 Global Workflow (visible to everyone)"
              checked={isGlobalWorkflow}
              onChange={(e) => onGlobalToggle(e.target.checked)}
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
            <Form.Group className="mb-0" style={{ minWidth: '220px' }}>
              <Form.Label className="mb-0">
                <small>Program Name *</small>
              </Form.Label>
              <Form.Control
                as="select"
                size="sm"
                value={programName}
                onChange={(e) => onProgramChange(e.target.value)}
                disabled={programsLoading}
              >
                <option value="">Select a program</option>
                {programs.map((program) => {
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
        </div>
        <div className="workflow-builder-editor-chrome-toolbar-actions d-flex gap-2 align-items-end flex-shrink-0">
          <Button variant="outline-secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" variant="primary" disabled={saving} onClick={onSave}>
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
      </div>

      <WorkflowBuilderMetadataBar
        embedInChrome
        workflowName={workflowName}
        setWorkflowName={setWorkflowName}
        workflowDescription={workflowDescription}
        setWorkflowDescription={setWorkflowDescription}
      />
    </div>
  );
}

export default WorkflowBuilderEditorChrome;
