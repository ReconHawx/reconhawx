/**
 * Modal wrapper for VisualWorkflowBuilder used when editing workflow_trigger
 * actions in event handlers. Loads workflow parameters, allows visual editing,
 * and saves back to the action's parameters.
 */

import React, { useEffect, useState } from 'react';
import { Modal, Button } from 'react-bootstrap';
import VisualWorkflowBuilder from './VisualWorkflowBuilder';
import { useWorkflowStore } from '../stores/workflowStore';
import { getDefaultEventHandlerInputs } from '../utils/eventHandlerWorkflowDefaults';

function mergeParametersWithEventHandlerDefaults(parameters, eventType) {
  const p = parameters ? { ...parameters } : {};
  let inputs = p.inputs || {};
  if (p.definition) {
    inputs = p.definition.inputs || inputs;
  }
  if (Object.keys(inputs).length === 0) {
    inputs = getDefaultEventHandlerInputs(eventType);
  }
  const merged = { ...p, inputs };
  if (p.definition) {
    merged.definition = { ...p.definition, inputs };
  }
  return merged;
}

function EmbeddedWorkflowBuilderModal({ show, onHide, initialParameters, onSave, eventType = '' }) {
  const { convertWorkflowToNodes, getWorkflowPayload } = useWorkflowStore();
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');

  // Load workflow into store when modal opens
  useEffect(() => {
    if (show) {
      const merged = mergeParametersWithEventHandlerDefaults(initialParameters, eventType);
      convertWorkflowToNodes(merged);
      setWorkflowName(merged.workflow_name || merged.name || '');
      setWorkflowDescription(merged.description || '');
    }
  }, [show, initialParameters, eventType, convertWorkflowToNodes]);

  const handleSave = () => {
    // Sync name/description to store before generating payload
    useWorkflowStore.setState({
      workflowName,
      workflowDescription,
    });
    const payload = getWorkflowPayload();
    onSave(payload);
    onHide();
  };

  if (!show) return null;

  return (
    <Modal show={show} onHide={onHide} size="xl" scrollable backdrop="static" className="embedded-workflow-modal">
      <Modal.Header closeButton>
        <Modal.Title>Build Workflow</Modal.Title>
      </Modal.Header>
      <Modal.Body className="p-0" style={{ minHeight: '60vh' }}>
        <VisualWorkflowBuilder
          workflowName={workflowName}
          setWorkflowName={setWorkflowName}
          workflowDescription={workflowDescription}
          setWorkflowDescription={setWorkflowDescription}
          eventHandlerMode
          eventHandlerEventType={eventType}
        />
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>
          Cancel
        </Button>
        <Button variant="primary" onClick={handleSave}>
          Save Workflow
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

export default EmbeddedWorkflowBuilderModal;
