import React from 'react';
import { Form } from 'react-bootstrap';
import { useWorkflowStore } from '../../stores/workflowStore';
import { TASK_TYPES } from './constants';

function InputMappingSection({ selectedNode, updateNodeData }) {
  const { nodes, edges } = useWorkflowStore();
  const taskType = selectedNode?.data?.taskType;
  const taskConfig = TASK_TYPES[taskType];
  const inputTypes = taskConfig?.inputs || [];

  const incomingEdges = edges.filter(edge => edge.target === selectedNode?.id);
  const inputMapping = selectedNode?.data?.inputMapping || {};

  if (incomingEdges.length === 0 || inputTypes.length === 0) {
    return null;
  }

  const getMappingKey = (edge) => {
    return edge.sourceHandle && edge.sourceHandle !== 'output'
      ? `${edge.source}::${edge.sourceHandle}`
      : edge.source;
  };

  const getSourceNodeLabel = (edge) => {
    const sourceNode = nodes.find(n => n.id === edge.source);
    const base = (sid) => {
      if (!sourceNode) return sid;
      if (sourceNode.type === 'inputNode') {
        return sourceNode.data?.isEmpty ? 'Workflow Start' : `Input: ${sourceNode.data?.name || sid}`;
      }
      if (sourceNode.type === 'taskNode') {
        const tt = TASK_TYPES[sourceNode.data?.taskType];
        return tt?.name || sourceNode.data?.taskType || sid;
      }
      return sid;
    };
    const label = base(edge.source);
    if (edge.sourceHandle && edge.sourceHandle !== 'output') {
      return `${label} (${edge.sourceHandle})`;
    }
    return label;
  };

  const handleMappingChange = (mappingKey, targetInputType) => {
    const newMapping = { ...inputMapping };
    if (targetInputType) {
      newMapping[mappingKey] = targetInputType;
    } else {
      delete newMapping[mappingKey];
    }
    updateNodeData(selectedNode.id, { inputMapping: newMapping });
  };

  return (
    <div className="mb-4">
      <h6 className="mb-3">Input Mapping</h6>
      <p className="text-muted small mb-3">
        Map each connection to the input type this task expects.
      </p>
      {incomingEdges.map((edge) => {
        const mappingKey = getMappingKey(edge);
        return (
        <Form.Group key={edge.id} className="mb-2">
          <Form.Label className="small mb-1">{getSourceNodeLabel(edge)}</Form.Label>
          <Form.Select
            size="sm"
            value={inputMapping[mappingKey] || inputMapping[edge.source] || ''}
            onChange={(e) => handleMappingChange(mappingKey, e.target.value || null)}
          >
            <option value="">Select input type...</option>
            {inputTypes.map((inputType) => (
              <option key={inputType} value={inputType}>
                {inputType}
              </option>
            ))}
          </Form.Select>
        </Form.Group>
        );
      })}
    </div>
  );
}

export default InputMappingSection;
