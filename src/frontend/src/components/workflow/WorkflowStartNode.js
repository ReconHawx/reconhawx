import React from 'react';
import { Handle, Position } from 'reactflow';
import { useTheme } from '../../contexts/ThemeContext';

const WorkflowStartNode = ({ data, selected }) => {
  const { isDark } = useTheme();

  return (
    <div
      style={{
        padding: '15px 20px',
        borderRadius: '8px',
        background: isDark
          ? 'linear-gradient(145deg, #142820 0%, #121c2f 100%)'
          : 'linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%)',
        border: `2px solid ${selected ? (isDark ? '#00f2ff' : '#0d6efd') : isDark ? 'rgba(0, 200, 120, 0.55)' : '#4caf50'}`,
        minWidth: '250px',
        fontSize: '14px',
        boxShadow: selected
          ? (isDark ? '0 4px 20px rgba(0, 242, 255, 0.15)' : '0 4px 12px rgba(0,0,0,0.15)')
          : (isDark ? '0 2px 12px rgba(0,0,0,0.35)' : '0 2px 8px rgba(0,0,0,0.1)'),
      }}
    >
      <div className="d-flex align-items-center mb-2">
        <span className="me-2" style={{fontSize: '20px'}}>🚀</span>
        <strong style={{ color: isDark ? '#f0fbff' : 'inherit' }}>Workflow Start</strong>
      </div>
      <div style={{ fontSize: '12px', color: isDark ? '#9db4c4' : '#555', marginBottom: '10px' }}>
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