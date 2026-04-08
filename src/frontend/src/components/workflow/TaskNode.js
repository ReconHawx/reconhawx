import React, { useMemo } from 'react';
import { Handle, Position } from 'reactflow';
import { Form, Button, Badge } from 'react-bootstrap';
import { useWorkflowStore } from '../../stores/workflowStore';
import { TASK_TYPES, TASK_CATEGORIES, getDataTypeColor } from './constants';
import {
  WORKFLOW_STEP_BACKGROUND_PATTERNS,
  workflowNodeShadowIdle,
  workflowNodeShadowSelected,
} from '../../utils/workflowNodeTheme';

const TaskNode = ({ data, selected, id }) => {
  const { openTaskConfigModal, deleteNode, steps, getStepForPosition, updateNodeData } = useWorkflowStore();
  const taskType = TASK_TYPES[data.taskType];
  const category = taskType?.category || 'Other';
  const categoryInfo = TASK_CATEGORIES[category] || { color: 'var(--bs-text-muted)', icon: '⚙️' };
  
  const currentNode = useWorkflowStore(state => state.nodes.find(n => n.id === id));
  const currentStep = currentNode ? getStepForPosition(currentNode.position.y) : null;
  const stepIndex = currentStep ? steps.findIndex(s => s.id === currentStep.id) : -1;
  
  const stepBackground = useMemo(() => {
    if (stepIndex < 0) {
      return 'linear-gradient(145deg, var(--bs-card-bg) 0%, var(--bs-pre-bg) 100%)';
    }
    const palette = WORKFLOW_STEP_BACKGROUND_PATTERNS;
    return palette[stepIndex % palette.length];
  }, [stepIndex]);

  const borderColor = selected ? 'var(--bs-primary)' : categoryInfo.color;

  const nodeShadow = selected ? workflowNodeShadowSelected : workflowNodeShadowIdle;

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
        color: 'var(--bs-body-color)',
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
              style={{ backgroundColor: categoryInfo.color, color: 'var(--rh-on-cyan)' }}
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
            color: 'var(--bs-text-muted)',
            marginBottom: '10px',
            minHeight: '30px',
          }}
        >
          {taskType?.description}
        </div>

        <div style={{ fontSize: '11px', color: 'var(--bs-text-muted)' }}>
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
          <small style={{ fontSize: '11px', color: 'var(--bs-text-muted)' }}>
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