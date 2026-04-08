import React from 'react';
import { Form } from 'react-bootstrap';

/**
 * Workflow name + description.
 * - Default: full-width strip for modal / event-handler builder (flat divider, not floating).
 * - embedInChrome: fields only; parent `WorkflowBuilderEditorChrome` supplies surface + dividers.
 */
function WorkflowBuilderMetadataBar({
  workflowName,
  setWorkflowName,
  workflowDescription,
  setWorkflowDescription,
  embedInChrome = false,
}) {
  const fields = (
    <div className="workflow-builder-metadata-fields">
      <div className="workflow-builder-metadata-field">
        <Form.Group className="mb-0">
          <Form.Label className="mb-1">
            <small><strong>Workflow Name</strong></small>
          </Form.Label>
          <Form.Control
            size="sm"
            type="text"
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            placeholder="Enter workflow name"
            style={{ fontSize: '14px' }}
          />
        </Form.Group>
      </div>
      <div className="workflow-builder-metadata-field">
        <Form.Group className="mb-0">
          <Form.Label className="mb-1">
            <small><strong>Description</strong></small>
          </Form.Label>
          <Form.Control
            size="sm"
            as="textarea"
            rows={1}
            value={workflowDescription}
            onChange={(e) => setWorkflowDescription(e.target.value)}
            placeholder="Enter workflow description"
            style={{ fontSize: '14px', resize: 'vertical' }}
          />
        </Form.Group>
      </div>
    </div>
  );

  if (embedInChrome) {
    return fields;
  }

  return (
    <div className="workflow-info-section workflow-builder-metadata-bar">
      {fields}
    </div>
  );
}

export default WorkflowBuilderMetadataBar;
