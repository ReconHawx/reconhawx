import React from 'react';
import { Handle, Position } from 'reactflow';
import {
  workflowNodeShadowIdle,
  workflowNodeShadowSelected,
} from '../../utils/workflowNodeTheme';

const WorkflowStartNode = ({ selected }) => {
  return (
    <div
      style={{
        padding: '15px 20px',
        borderRadius: '8px',
        background:
          'linear-gradient(135deg, rgba(var(--bs-success-rgb), 0.12) 0%, rgba(var(--bs-success-rgb), 0.2) 100%)',
        border: `2px solid ${
          selected
            ? 'var(--bs-primary)'
            : 'rgba(var(--bs-success-rgb), 0.65)'
        }`,
        minWidth: '250px',
        fontSize: '14px',
        boxShadow: selected ? workflowNodeShadowSelected : workflowNodeShadowIdle,
        color: 'var(--bs-body-color)',
      }}
    >
      <div className="d-flex align-items-center mb-2">
        <span className="me-2" style={{ fontSize: '20px' }}>
          🚀
        </span>
        <strong>Workflow Start</strong>
      </div>
      <div
        style={{
          fontSize: '12px',
          color: 'var(--bs-text-muted)',
          marginBottom: '10px',
        }}
      >
        <small>Configure inputs to start your workflow</small>
      </div>

      {/* Invisible output handle - edges connect to node edge, no visual misalignment */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        className="workflow-node-handle-invisible"
      />
    </div>
  );
};

export default WorkflowStartNode;
