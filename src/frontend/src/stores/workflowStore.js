import { create } from 'zustand';
import {
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  Position,
} from 'reactflow';
import { TASK_TYPES } from '../components/workflow/constants';

const useWorkflowStore = create((set, get) => ({
  nodes: [
    {
      id: 'source',
      type: 'inputNode',
      position: { x: 20, y: 20 },
      data: {
        name: 'source',
        isEmpty: true,
      },
      deletable: false,
    },
  ],
  edges: [],
  workflowName: '',
  programName: '',
  workflowDescription: '',
  variables: {},
  steps: [
    {
      id: 'step-1',
      name: 'Step 1',
      yPosition: 200,
      height: 300
    }
  ],
  inputs: {},
  isTaskModalOpen: false,
  isInputConfigModalOpen: false,
  selectedNodeId: null,

  // --- Actions ---

  setInputs: (inputs) => {
    set({ inputs });
    // Update the source node's data to reflect the new inputs for rendering handles
    set((state) => ({
      nodes: state.nodes.map((node) => {
        if (node.id === 'source') {
          return { ...node, data: { ...node.data, inputs } };
        }
        return node;
      }),
    }));
  },

  setVariables: (variables) => {
    set({ variables });
  },

  // Modal actions
  openTaskConfigModal: (nodeId) => set({ isTaskModalOpen: true, selectedNodeId: nodeId }),
  closeTaskConfigModal: () => set({ isTaskModalOpen: false, selectedNodeId: null }),
  openInputConfigModal: () => set({ isInputConfigModalOpen: true }),
  closeInputConfigModal: () => set({ isInputConfigModalOpen: false }),

  // React Flow state changes
  onNodesChange: (changes) => {
    set({
      nodes: applyNodeChanges(changes, get().nodes),
    });
  },
  onEdgesChange: (changes) => {
    set({
      edges: applyEdgeChanges(changes, get().edges),
    });
  },
  onConnect: (connection) => {
    const newEdge = { 
      ...connection, 
      sourceHandle: connection.sourceHandle ?? 'output',
      targetHandle: connection.targetHandle ?? 'input',
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      type: 'default', 
      style: { strokeWidth: 2 }
    };
    const state = get();
    const newEdges = addEdge(newEdge, state.edges);

    // Auto-populate inputMapping for target node with default (first input type)
    let newNodes = state.nodes;
    const targetNode = state.nodes.find(n => n.id === connection.target);
    if (targetNode?.type === 'taskNode' && targetNode.data) {
      const taskInputs = TASK_TYPES[targetNode.data.taskType]?.inputs || [];
      const existingMapping = targetNode.data.inputMapping || {};
      const mappingKey = connection.sourceHandle && connection.sourceHandle !== 'output'
        ? `${connection.source}::${connection.sourceHandle}`
        : connection.source;
      if (!existingMapping[mappingKey] && taskInputs.length > 0) {
        const usedTypes = new Set(Object.values(existingMapping));
        const firstUnused = taskInputs.find(t => !usedTypes.has(t)) || taskInputs[0];
        newNodes = state.nodes.map(n =>
          n.id === connection.target
            ? { ...n, data: { ...n.data, inputMapping: { ...existingMapping, [mappingKey]: firstUnused } } }
            : n
        );
      }
    }
    set({ edges: newEdges, nodes: newNodes });
  },

  // Node and edge manipulation
  addNode: (newNode) => {
    set((state) => ({ nodes: [...state.nodes, newNode] }));
  },
  deleteNode: (nodeId, force = false) => {
    if (nodeId === 'source' && !force) return; // Prevent deleting the source node (unless replacing with inputs)
    set((state) => ({
      nodes: state.nodes.filter((node) => node.id !== nodeId),
      edges: state.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
    }));
  },
  updateNodeData: (nodeId, data) => {
    set({
      nodes: get().nodes.map((node) => {
        if (node.id === nodeId) {
          return { ...node, data: { ...node.data, ...data } };
        }
        return node;
      }),
    });
  },
  
  // NEW: Step management actions
  addStep: () => set((state) => {
    const newStepNumber = state.steps.length + 1;
    const lastStep = state.steps[state.steps.length - 1];
    const newStep = {
      id: `step-${newStepNumber}`,
      name: `Step ${newStepNumber}`,
      yPosition: lastStep.yPosition + lastStep.height + 80, // 80px gap between steps
      height: 300
    };
    
    return {
      steps: [...state.steps, newStep]
    };
  }),
  
  updateStepName: (stepId, newName) => set((state) => ({
    steps: state.steps.map(step =>
      step.id === stepId ? { ...step, name: newName } : step
    )
  })),
  
  removeStep: (stepId) => set((state) => {
    if (state.steps.length <= 1) return state; // Don't allow removing the last step
    
    const stepToRemove = state.steps.find(s => s.id === stepId);
    if (!stepToRemove) return state;
    
    // Remove nodes that are in this step
    const nodesInStep = state.nodes.filter(node => {
      if (node.id === 'source') return false;
      return node.position.y >= stepToRemove.yPosition && 
             node.position.y < stepToRemove.yPosition + stepToRemove.height;
    });
    
    const nodeIdsToRemove = nodesInStep.map(n => n.id);
    const newNodes = state.nodes.filter(n => !nodeIdsToRemove.includes(n.id));
    const newEdges = state.edges.filter(e => 
      !nodeIdsToRemove.includes(e.source) && !nodeIdsToRemove.includes(e.target)
    );
    
    // Remove the step and adjust positions of subsequent steps
    const newSteps = state.steps
      .filter(s => s.id !== stepId)
      .map((step, index) => {
        if (step.yPosition > stepToRemove.yPosition) {
          return {
            ...step,
            yPosition: step.yPosition - (stepToRemove.height + 80)
          };
        }
        return step;
      });
    
    return {
      steps: newSteps,
      nodes: newNodes,
      edges: newEdges
    };
  }),
  
  getStepForPosition: (y) => {
    const state = get();
    return state.steps.find(step => 
      y >= step.yPosition && y < step.yPosition + step.height
    );
  },
  
  // Modified clearWorkflow to reset steps
  clearWorkflow: () => set({
    nodes: [{
      id: 'source',
      type: 'inputNode',
      position: { x: 20, y: 20 },
      data: {
        name: 'source',
        isEmpty: true,
      },
      deletable: false,
    }],
    edges: [],
    steps: [
      {
        id: 'step-1',
        name: 'Step 1',
        yPosition: 200,
        height: 300
      }
    ],
    inputs: {},
    workflowName: '',
    workflowDescription: '',
    programName: '',
    variables: {},
    selectedNodeId: null,
    isTaskModalOpen: false,
    isInputConfigModalOpen: false,
  }),

  // --- CONVERSION LOGIC ---

  convertWorkflowToNodes: (workflowDef) => {
    if (!workflowDef) {
        get().clearWorkflow();
        return;
    }



    // Handle both old format (inputs/variables in definition) and new format (separate fields)
    let steps = workflowDef.steps || [];
    let inputs = workflowDef.inputs || {};
    let variables = workflowDef.variables || {};
    let workflow_name = workflowDef.workflow_name || workflowDef.name || '';
    let description = workflowDef.description || '';
    let program_name = workflowDef.program_name ?? null;

    // If using old format where everything is in definition
    if (workflowDef.definition) {
      const definition = workflowDef.definition;
      steps = definition.steps || steps;
      inputs = definition.inputs || inputs;
      variables = definition.variables || variables;
    }



    // Convert workflow steps to visual step structure
    const visualSteps = steps.map((step, index) => ({
      id: `step-${index + 1}`,
      name: step.name || `Step ${index + 1}`,
      yPosition: 200 + (index * 380), // 300 height + 80 gap, starting at 200
      height: 300
    }));

    // If no steps exist, create a default one
    const finalVisualSteps = visualSteps.length > 0 ? visualSteps : [{
      id: 'step-1',
      name: 'Step 1',
      yPosition: 200,
      height: 300
    }];

    const newNodes = [];
    if (Object.keys(inputs).length > 0) {
      const firstStepY = finalVisualSteps.length > 0 ? finalVisualSteps[0].yPosition : 200;
      Object.entries(inputs).forEach(([name, config], index) => {
        newNodes.push({
          id: `input-${name}`,
          type: 'inputNode',
          position: { x: 20 + index * 280, y: firstStepY - 150 },
          data: { name, ...config },
          deletable: true,
        });
      });
    } else {
      newNodes.push({
        id: 'source',
        type: 'inputNode',
        position: { x: 20, y: 20 },
        data: {
          name: 'source',
          isEmpty: true,
        },
        deletable: false,
      });
    }

    const newEdges = [];
    const taskNodeIdMap = new Map();
    let edgeId = 0;

    // Update global state with visual steps
    
    set({
      workflowName: workflow_name,
      workflowDescription: description,
      programName: program_name,
      variables,
      inputs,
      steps: finalVisualSteps, // Use visual steps instead of original steps
    });

    steps.forEach((step, stepIndex) => {
        // Use the visual step positioning
        const visualStep = finalVisualSteps[stepIndex];
        const stepY = visualStep ? visualStep.yPosition + 80 : 100 + (stepIndex * 380) + 80;

        step.tasks.forEach((task, taskIndex) => {
            const taskId = `${step.name}_${task.name}`;
            const nodeInputMapping = {};
            if (task.input_mapping) {
                Object.entries(task.input_mapping).forEach(([targetHandle, sourcePath]) => {
                    const sourcePaths = Array.isArray(sourcePath) ? sourcePath : [sourcePath];
                    sourcePaths.forEach((path) => {
                        const pathParts = path.split('.');
                        let sourceNodeId;
                        let mappingKey;
                        if (pathParts[0] === 'inputs') {
                            sourceNodeId = `input-${pathParts[1]}`;
                            mappingKey = sourceNodeId;
                        } else if (pathParts[0] === 'steps') {
                            const sourceStepName = pathParts[1];
                            const sourceTaskName = pathParts[2];
                            sourceNodeId = taskNodeIdMap.get(`${sourceStepName}.${sourceTaskName}`);
                            const outputType = pathParts[4] || 'output';
                            mappingKey = sourceNodeId ? `${sourceNodeId}::${outputType}` : null;
                        }
                        if (mappingKey) {
                            nodeInputMapping[mappingKey] = targetHandle;
                        }
                    });
                });
            }
            const taskNode = {
                id: taskId,
                type: 'taskNode',
                position: { x: 400 + (taskIndex * 350), y: stepY },
                data: {
                    taskType: task.task_type,
                    taskName: task.name,
                    params: task.params || {},
                    force: task.force || false,
                    hasConfiguration: Object.keys(task.params || {}).length > 0 || task.force || false,
                    nucleiTemplateCount: task.task_type === 'nuclei_scan' && task.params?.template
                        ? (task.params.template.official?.length || 0) + (task.params.template.custom?.length || 0)
                        : 0,
                    inputMapping: nodeInputMapping,
                    // Load output_mode if it exists (for fuzz_website tasks)
                    ...(task.output_mode !== undefined && { output_mode: task.output_mode }),
                    // Load use_proxy if it exists (for tasks that support proxying)
                    ...(task.use_proxy !== undefined && { use_proxy: task.use_proxy }),
                }
            };
            newNodes.push(taskNode);
            taskNodeIdMap.set(`${step.name}.${task.name}`, taskId);
        });
    });
    
    // Create edges after all nodes have been created
    steps.forEach((step) => {
        step.tasks.forEach((task) => {
            const targetNodeId = taskNodeIdMap.get(`${step.name}.${task.name}`);
            if (!task.input_mapping) return;

            Object.entries(task.input_mapping).forEach(([targetHandle, sourcePath]) => {
                const sourcePaths = Array.isArray(sourcePath) ? sourcePath : [sourcePath];
                sourcePaths.forEach((path) => {
                    const pathParts = path.split('.');
                    let sourceNodeId;
                    let sourceHandle;

                    if (pathParts[0] === 'inputs') {
                        sourceNodeId = `input-${pathParts[1]}`;
                        sourceHandle = 'output';
                    } else if (pathParts[0] === 'steps') {
                        const sourceStepName = pathParts[1];
                        const sourceTaskName = pathParts[2];
                        sourceNodeId = taskNodeIdMap.get(`${sourceStepName}.${sourceTaskName}`);
                        sourceHandle = pathParts[4];
                    }

                    if (sourceNodeId && targetNodeId) {
                        newEdges.push({
                            id: `edge-${edgeId++}`,
                            source: sourceNodeId,
                            target: targetNodeId,
                            sourceHandle: sourceHandle ?? 'output',
                            targetHandle: 'input',
                            sourcePosition: Position.Right,
                            targetPosition: Position.Left,
                            type: 'default',
                            style: { strokeWidth: 2 }
                        });
                    }
                });
            });
        });
    });


    set({ nodes: newNodes, edges: newEdges });
  },

  getWorkflowPayload: () => {
    const { nodes, edges, inputs, workflowName, programName, workflowDescription, variables, steps } = get();
    
    // Step 1: Group task nodes by their visual step position
    const taskNodes = nodes.filter(node => node.type === 'taskNode');
    const stepGroups = {};

    // Initialize step groups based on visual steps
    steps.forEach((step, index) => {
      stepGroups[index] = [];
    });

    // Assign task nodes to step groups based on their Y position
    taskNodes.forEach(node => {
      const nodeY = node.position.y;
      let assignedStepIndex = 0;
      
      // Find which visual step this node belongs to
      for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        if (nodeY >= step.yPosition && nodeY < step.yPosition + step.height) {
          assignedStepIndex = i;
          break;
        } else if (nodeY >= step.yPosition + step.height && i === steps.length - 1) {
          // If past the last step, assign to the last step
          assignedStepIndex = i;
        } else if (nodeY < step.yPosition && i === 0) {
          // If before the first step, assign to the first step
          assignedStepIndex = i;
        }
      }
      
      stepGroups[assignedStepIndex].push(node);
    });

    // Step 2: Build the steps array
    const workflowSteps = Object.keys(stepGroups)
      .sort((a, b) => parseInt(a) - parseInt(b))
      .map((stepIndex) => {
        const stepNodes = stepGroups[stepIndex];
        const visualStep = steps[parseInt(stepIndex)];
        const stepName = visualStep ? visualStep.name.toLowerCase().replace(/\s+/g, '_') : `step_${parseInt(stepIndex) + 1}`;
        const stepTaskNames = new Set();

        const tasks = stepNodes.map(node => {
          // Ensure unique task name within the step
          let taskName = node.data.taskType;
          let counter = 1;
          while (stepTaskNames.has(taskName)) {
            taskName = `${node.data.taskType}_${counter++}`;
          }
          stepTaskNames.add(taskName);

          // Build input mapping from edges
          const inputMapping = {};
          const incomingEdges = edges.filter(edge => edge.target === node.id);
          const nodeInputMapping = node.data.inputMapping || {};

          incomingEdges.forEach((edge, index) => {
            const sourceNode = nodes.find(n => n.id === edge.source);
            if (!sourceNode) return;

            // Get target input type: from node's inputMapping (use composite key for multi-output sources)
            const mappingKey = edge.sourceHandle && edge.sourceHandle !== 'output'
              ? `${edge.source}::${edge.sourceHandle}`
              : edge.source;
            let targetHandle = nodeInputMapping[mappingKey] ?? nodeInputMapping[edge.source];
            if (!targetHandle && edge.targetHandle && edge.targetHandle !== 'input') {
              targetHandle = edge.targetHandle; // Legacy: targetHandle was the type
            }
            if (!targetHandle) {
              // Fallback: assign by connection order to task's input types
              const taskInputs = TASK_TYPES[node.data.taskType]?.inputs || [];
              targetHandle = taskInputs[index] || taskInputs[0];
            }
            if (!targetHandle) return;

            let sourcePath = '';
            if (sourceNode.id === 'source') {
              sourcePath = `inputs.${sourceNode.data?.name || 'source'}`;
            } else if (sourceNode.type === 'inputNode') {
              sourcePath = `inputs.${sourceNode.data.name}`;
            } else {
              // Find which step the source node belongs to
              const sourceNodeY = sourceNode.position.y;
              let sourceStepIndex = 0;
              
              for (let i = 0; i < steps.length; i++) {
                const step = steps[i];
                if (sourceNodeY >= step.yPosition && sourceNodeY < step.yPosition + step.height) {
                  sourceStepIndex = i;
                  break;
                }
              }
              
              const sourceVisualStep = steps[sourceStepIndex];
              const sourceStepName = sourceVisualStep ? sourceVisualStep.name.toLowerCase().replace(/\s+/g, '_') : `step_${sourceStepIndex + 1}`;
              const sourceTaskName = sourceNode.data.taskName || sourceNode.data.taskType;

              sourcePath = `steps.${sourceStepName}.${sourceTaskName}.outputs.${edge.sourceHandle || 'output'}`;
            }
            // Accumulate multiple sources per target handle (support multiple task outputs as input)
            if (!inputMapping[targetHandle]) inputMapping[targetHandle] = [];
            inputMapping[targetHandle].push(sourcePath);
          });

          // Normalize: single-element arrays become strings for backward compatibility
          Object.keys(inputMapping).forEach((k) => {
            const val = inputMapping[k];
            if (Array.isArray(val) && val.length === 1) inputMapping[k] = val[0];
          });

          const taskDef = {
            name: taskName,
            task_type: node.data.taskType,
            params: node.data.params || {},
            force: node.data.force || false,
            input_mapping: inputMapping,
          };

          // Add output_mode if it exists (for fuzz_website tasks)
          if (node.data.output_mode !== undefined) {
            taskDef.output_mode = node.data.output_mode;
          }

          // Add use_proxy if it exists (for tasks that support proxying)
          if (node.data.use_proxy !== undefined) {
            taskDef.use_proxy = node.data.use_proxy;
          }

          return taskDef;
        });

        return { name: stepName, tasks };
      })
      .filter(step => step.tasks.length > 0); // Only include steps that have tasks
      
    // Construct the final workflow object
    return {
        workflow_name: workflowName ? workflowName.toLowerCase().replace(/\s+/g, '_') : '',
        program_name: programName,
        description: workflowDescription,
        inputs: inputs,
        steps: workflowSteps,
        variables: variables,
    };
  },
}));

export { useWorkflowStore };