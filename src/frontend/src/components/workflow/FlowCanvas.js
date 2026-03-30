import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { ReactFlow, Controls, MiniMap, Background, useReactFlow, useUpdateNodeInternals } from 'reactflow';
import { useWorkflowStore } from '../../stores/workflowStore';
import { useTheme } from '../../contexts/ThemeContext';
import { TASK_TYPES } from './constants';
import StepBackground from './StepBackground';
import StepManagementPanel from './StepManagementPanel';
import InputNode from './InputNode';
import TaskNode from './TaskNode';
import WorkflowStartNode from './WorkflowStartNode';

const nodeTypes = {
  taskNode: TaskNode,
  inputNode: InputNode,
  workflowStartNode: WorkflowStartNode,
};

// Utility function to extract default parameters for a task type
const getDefaultParams = (taskType) => {
  const taskConfig = TASK_TYPES[taskType];
  if (!taskConfig || !taskConfig.params) {
    return {};
  }

  const defaultParams = {};
  Object.entries(taskConfig.params).forEach(([paramName, paramConfig]) => {
    if (paramConfig.default !== undefined) {
      defaultParams[paramName] = paramConfig.default;
    }
  });

  return defaultParams;
};

function FlowCanvas({ onDragOver, draggedTaskType, setDraggedTaskType }) {
  const {
    nodes, 
    edges, 
    onNodesChange, 
    onEdgesChange, 
    onConnect, 
    addNode,
    steps,
    getStepForPosition,
  } = useWorkflowStore();
  const { screenToFlowPosition } = useReactFlow();
  const { isDark } = useTheme();

  const calculateCanvasHeight = useMemo(() => {
    if (steps.length === 0) return 800;
    
    const lastStep = steps[steps.length - 1];
    const bottomOfLastStep = lastStep.yPosition + lastStep.height;
    const requiredHeight = bottomOfLastStep + 330;
    
    return Math.max(800, requiredHeight);
  }, [steps]);

  const calculateCanvasWidth = useMemo(() => {
    const sidebarWidth = 400;
    const padding = 40;
    const availableWidth = window.innerWidth - sidebarWidth - padding;
    
    return Math.max(400, availableWidth);
  }, []);

  const [canvasWidth, setCanvasWidth] = useState(calculateCanvasWidth);
  const updateNodeInternals = useUpdateNodeInternals();

  // Force React Flow to recalculate handle positions - fixes edge-handle misalignment
  useEffect(() => {
    const timer = setTimeout(() => {
      nodes.forEach((n) => updateNodeInternals(n.id));
    }, 50);
    return () => clearTimeout(timer);
  }, [nodes, updateNodeInternals]);

  useEffect(() => {
    const handleResize = () => {
      const sidebarWidth = 400;
      const padding = 40;
      const availableWidth = window.innerWidth - sidebarWidth - padding;
      const newWidth = Math.max(400, availableWidth);
      setCanvasWidth(newWidth);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleDrop = useCallback(
    (event) => {
      event.preventDefault();

      if (!draggedTaskType) return;

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const targetStep = getStepForPosition(position.y);
      let adjustedPosition = position;
      
      if (targetStep) {
        adjustedPosition = {
          ...position,
          y: targetStep.yPosition + 80
        };
      } else {
        const firstStep = steps[0];
        if (firstStep) {
          adjustedPosition = {
            ...position,
            y: firstStep.yPosition + 80
          };
        }
      }

      const newNodeId = `${draggedTaskType}-${Date.now()}`;
      const defaultParams = getDefaultParams(draggedTaskType);
      const hasDefaultParams = Object.keys(defaultParams).length > 0;
      
      const newNode = {
        id: newNodeId,
        type: 'taskNode',
        position: adjustedPosition,
        data: {
          taskType: draggedTaskType,
          params: defaultParams,
          force: false,
          hasConfiguration: hasDefaultParams,
          nucleiTemplateCount: 0,
        }
      };

      addNode(newNode);
      setDraggedTaskType(null);
    },
    [draggedTaskType, addNode, setDraggedTaskType, screenToFlowPosition, getStepForPosition, steps]
  );

  return (
    <div style={{ position: 'relative', width: '100%', height: `${calculateCanvasHeight}px` }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={handleDrop}
        onDragOver={onDragOver}
        nodeTypes={nodeTypes}
        snapToGrid={true}
        snapGrid={[25, 50]}
        proOptions={{ hideAttribution: true }}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        minZoom={0.8}
        maxZoom={2}
        nodesDraggable={true}
        nodesConnectable={true}
        elementsSelectable={true}
        selectNodesOnDrag={false}
        panOnDrag={true}
        zoomOnScroll={true}
        zoomActivationKeyCode="Control"
        zoomOnPinch={true}
        panOnScroll={true}
        panOnScrollMode="free"
        preventScrolling={true}
        connectionRadius={12}
        connectionLineStyle={{
          stroke: isDark ? 'rgba(0, 242, 255, 0.75)' : '#1976d2',
          strokeWidth: 2,
          strokeDasharray: '5,5',
        }}
      >
        <Controls />
        <MiniMap />
        <Background
          variant="dots"
          gap={25}
          size={1}
          color={isDark ? 'rgba(0, 242, 255, 0.14)' : '#c5cfdd'}
        />
      </ReactFlow>
      <StepBackground steps={steps} canvasWidth={canvasWidth} />
      <StepManagementPanel />
    </div>
  );
}

export default FlowCanvas;