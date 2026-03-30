import React, { useMemo } from 'react';
import { Handle, Position } from 'reactflow';
import { Form, Button, Badge } from 'react-bootstrap';
import { useWorkflowStore } from '../../stores/workflowStore';
import { useTheme } from '../../contexts/ThemeContext';
import { TASK_TYPES, TASK_CATEGORIES, getDataTypeColor } from './constants';

const LIGHT_STEP_FILLS = [
  '#e3f2fd', '#f3e5f5', '#e8f5e8', '#fff3e0', '#fce4ec',
  '#e0f2f1', '#f1f8e9', '#fff8e1', '#e8eaf6', '#fafafa',
];

const DARK_STEP_FILLS = [
  'linear-gradient(145deg, #121c2f 0%, #151d30 100%)',
  'linear-gradient(145deg, #15182a 0%, #1a1530 100%)',
  'linear-gradient(145deg, #142028 0%, #121c2f 100%)',
  'linear-gradient(145deg, #1a1528 0%, #151d30 100%)',
  'linear-gradient(145deg, #0f1828 0%, #142030 100%)',
  'linear-gradient(145deg, #151d30 0%, #16162a 100%)',
  'linear-gradient(145deg, #121c2f 0%, #181828 100%)',
  'linear-gradient(145deg, #152028 0%, #15182a 100%)',
  'linear-gradient(145deg, #141e30 0%, #122018 100%)',
];

const TaskNode = ({ data, selected, id }) => {
  const { isDark } = useTheme();
  const { openTaskConfigModal, deleteNode, steps, getStepForPosition, updateNodeData } = useWorkflowStore();
  const taskType = TASK_TYPES[data.taskType];
  const category = taskType?.category || 'Other';
  const categoryInfo = TASK_CATEGORIES[category] || { color: '#666', icon: '⚙️' };
  
  const currentNode = useWorkflowStore(state => state.nodes.find(n => n.id === id));
  const currentStep = currentNode ? getStepForPosition(currentNode.position.y) : null;
  const stepIndex = currentStep ? steps.findIndex(s => s.id === currentStep.id) : -1;
  
  const stepBackground = useMemo(() => {
    if (stepIndex < 0) {
      return isDark
        ? 'linear-gradient(145deg, #121c2f 0%, #0d1422 100%)'
        : '#ffffff';
    }
    const palette = isDark ? DARK_STEP_FILLS : LIGHT_STEP_FILLS;
    return palette[stepIndex % palette.length];
  }, [stepIndex, isDark]);

  const borderColor = selected
    ? (isDark ? '#00f2ff' : '#1976d2')
    : categoryInfo.color;

  const nodeShadow = selected
    ? (isDark
        ? '0 4px 20px rgba(0, 242, 255, 0.18)'
        : '0 4px 12px rgba(0,0,0,0.15)')
    : (isDark ? '0 2px 12px rgba(0,0,0,0.35)' : '0 2px 8px rgba(0,0,0,0.1)');

  const handleForceChange = (e) => {
    e.stopPropagation();
    updateNodeData(id, {
      ...data,
      force: e.target.checked
    });
  };

  return (
    <div
      style={{
        padding: '20px',
        borderRadius: '8px',
        background: stepBackground,
        border: `2px solid ${borderColor}`,
        boxShadow: nodeShadow,
        minWidth: '280px',
        fontSize: '14px',
        position: 'relative',
        margin: '10px',
        color: isDark ? '#f0fbff' : '#212529',
      }}
    >
      {/* Invisible input handle - edges connect to node edge, no visual misalignment */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        className="workflow-node-handle-invisible"
      />

      <div>
        <div className="d-flex align-items-center mb-2">
          <span className="me-2" style={{ fontSize: '18px' }}>
            {taskType?.icon || '⚙️'}
          </span>
          <div className="flex-grow-1">
            <div className="fw-bold">{taskType?.name || data.taskType}</div>
            <Badge 
              bg="light" 
              text="dark"
              style={{ backgroundColor: categoryInfo.color, color: 'white' }}
            >
              {category}
            </Badge>
            {currentStep && (
              <Badge bg="info" className="ms-1" style={{ fontSize: '10px' }}>
                {currentStep.name}
              </Badge>
            )}
          </div>
          <div className="d-flex gap-1">
            <Button
              variant="outline-primary"
              size="sm"
              onClick={() => openTaskConfigModal(id)}
              style={{ fontSize: '12px' }}
              title="Configure Task"
            >
              ⚙️
            </Button>
            <Button
              variant="outline-danger"
              size="sm"
              onClick={() => deleteNode(id)}
              style={{ fontSize: '12px' }}
              title="Delete Task"
            >
              🗑️
            </Button>
          </div>
        </div>

        <div
          style={{
            fontSize: '12px',
            color: isDark ? '#9db4c4' : '#666',
            marginBottom: '10px',
            minHeight: '30px',
          }}
        >
          {taskType?.description}
        </div>

        <div style={{ fontSize: '11px', color: isDark ? '#8eadbf' : '#888' }}>
          {data.hasConfiguration && (
            <Badge bg="success" className="me-1">Configured</Badge>
          )}
          {data.nucleiTemplateCount > 0 && (
            <Badge bg="info" className="me-1">{data.nucleiTemplateCount} templates</Badge>
          )}
          {data.use_proxy && (
            <Badge bg="warning" text="dark" className="me-1">🔒 Proxy</Badge>
          )}
        </div>

        <div className="mt-2 d-flex align-items-center">
          <Form.Check
            type="checkbox"
            id={`force-${id}`}
            checked={data.force || false}
            onChange={handleForceChange}
            style={{ fontSize: '11px' }}
            className="me-2"
          />
          <small style={{ fontSize: '11px', color: isDark ? '#9db4c4' : '#666' }}>
            Force execution (ignore cache)
          </small>
        </div>
      </div>

      {/* Multiple output handles - one per output type for connecting to downstream tasks */}
      {taskType?.outputs?.map((outputType, index) => {
        const handleColor = getDataTypeColor(outputType);
        const topPosition = 20 + (index * 28);
        return (
          <Handle
            key={`output-${outputType}`}
            type="source"
            position={Position.Right}
            id={outputType}
            className="workflow-node-handle-invisible workflow-node-handle-colored"
            style={{
              top: `${topPosition}px`,
              right: 0,
              transform: 'translate(100%, -50%)',
              '--handle-color': handleColor,
            }}
          />
        );
      })}
      {/* Fallback: single output handle for tasks with no outputs defined */}
      {(!taskType?.outputs || taskType.outputs.length === 0) && (
        <Handle
          type="source"
          position={Position.Right}
          id="output"
          className="workflow-node-handle-invisible"
        />
      )}
    </div>
  );
};

export default TaskNode;