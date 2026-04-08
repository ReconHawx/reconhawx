import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ReactFlowProvider,
  Panel
} from 'reactflow';
import 'reactflow/dist/style.css';
import './VisualWorkflowBuilder.css';
import {
  Form, Button, Alert, Modal, Badge, Tabs, Tab
} from 'react-bootstrap';
import { useWorkflowStore } from '../stores/workflowStore';
import FlowCanvas from './workflow/FlowCanvas';
import WorkflowBuilderMetadataBar from './workflow/WorkflowBuilderMetadataBar';
import TaskLibrarySidebar from './workflow/TaskLibrarySidebar';
import TaskParameterSelector from './workflow/TaskParameterSelector';
import InputMappingSection from './workflow/InputMappingSection';
import InputConfigSidebar from './workflow/InputConfigSidebar';
import VariablesConfigSidebar from './workflow/VariablesConfigSidebar';
import { TASK_TYPES } from './workflow/constants';
import { getEventHandlerDirectInputDefaults } from '../utils/eventHandlerWorkflowDefaults';







function VisualWorkflowBuilder({
  workflowName,
  setWorkflowName,
  workflowDescription,
  setWorkflowDescription,
  eventHandlerMode = false,
  eventHandlerEventType = '',
  showMetadataBar = true,
}) {
    const {
        nodes,
        steps,
        clearWorkflow,
        isTaskModalOpen,
        closeTaskConfigModal,
        isInputConfigModalOpen, // New modal state
        closeInputConfigModal, // New modal action
        openInputConfigModal,
        selectedNodeId,
        updateNodeData,
        inputs, // Global inputs from the store
        setInputs, // Action to set inputs in the store
        variables, // Global variables from the store
        setVariables, // Action to set variables in the store
        addNode, // Get addNode action from the store
        deleteNode, // Get deleteNode action from the store
    } = useWorkflowStore();
  // UI state
  const [draggedTaskType, setDraggedTaskType] = useState(null);

  // Task configuration state
  const [taskConfig, setTaskConfig] = useState({});
  const [currentTaskParams, setCurrentTaskParams] = useState({});
  const [pendingTaskParams, setPendingTaskParams] = useState(null);
  // --- NEW: State for the global input configuration modal ---
  const [currentInputs, setCurrentInputs] = useState({});
  const [editingInput, setEditingInput] = useState(null); // To edit a specific input

  // --- State for the variables configuration panel (same UX as inputs panel) ---
  const [showVariablesPanel, setShowVariablesPanel] = useState(false);
  const [currentVariables, setCurrentVariables] = useState({});
  const [editingVariable, setEditingVariable] = useState(null);
  const [showVariableNotification, setShowVariableNotification] = useState(false);
  const [extractedVariableNames, setExtractedVariableNames] = useState([]);

  // Nuclei templates state for task configuration modal
  const [selectedTreeTemplates, setSelectedTreeTemplates] = useState(new Set());
  const [selectedCustomTemplates, setSelectedCustomTemplates] = useState([]);
  
  // Wordlist selection state
  const [selectedWordlist, setSelectedWordlist] = useState(null);
  const [wordlistInputType, setWordlistInputType] = useState('database');
  const [customWordlistUrl, setCustomWordlistUrl] = useState('');

  // Output mode selection state for fuzz_website
  const [outputMode, setOutputMode] = useState(null);

  // Proxy selection state for tasks that support proxying (fuzz_website, nuclei_scan)
  const [useProxy, setUseProxy] = useState(false);

  const selectedNode = useMemo(() => nodes.find(n => n.id === selectedNodeId), [nodes, selectedNodeId]);


  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  // Load on component mount
  useEffect(() => {
    // On unmount, clear the workflow from the store
    return () => {
      clearWorkflow();
    };
  }, [clearWorkflow]);


  // Pre-fill task config only when modal opens or selected node ID changes.
  // Do NOT depend on selectedNode identity: store updates (e.g. React Flow pan/zoom) replace nodes and would re-run this,
  // overwriting in-progress wordlist selection for dns_bruteforce/fuzz_website.
  useEffect(() => {
    if (!isTaskModalOpen || !selectedNodeId) return;

    const node = useWorkflowStore.getState().nodes.find((n) => n.id === selectedNodeId);
    if (!node) return;

    setTaskConfig(node.data);
    setCurrentTaskParams(node.data.params || {});

    if (node.data.taskType === 'nuclei_scan') {
      const officialTemplates = node.data.params?.template?.official || [];
      const customTemplates = node.data.params?.template?.custom || [];
      setSelectedTreeTemplates(new Set(officialTemplates));
      setSelectedCustomTemplates(customTemplates);
    }

    if (node.data.taskType === 'fuzz_website') {
      const wordlistParam = node.data.params?.wordlist || '/workspace/files/webcontent_test.txt';
      if (wordlistParam.startsWith('http')) {
        setWordlistInputType('url');
        setCustomWordlistUrl(wordlistParam);
        setSelectedWordlist(null);
      } else {
        setWordlistInputType('database');
        setCustomWordlistUrl('');
        setSelectedWordlist({ id: wordlistParam });
      }
      setOutputMode(node.data.output_mode || '');
    }

    if (node.data.taskType === 'dns_bruteforce') {
      const wordlistParam = node.data.params?.wordlist || '/workspace/files/subdomains.txt';
      if (wordlistParam.startsWith('http')) {
        setWordlistInputType('url');
        setCustomWordlistUrl(wordlistParam);
        setSelectedWordlist(null);
      } else {
        setWordlistInputType('database');
        setCustomWordlistUrl('');
        setSelectedWordlist({ id: wordlistParam });
      }
      setOutputMode(node.data.output_mode || '');
    }

    if (node.data.taskType === 'fuzz_website' || node.data.taskType === 'nuclei_scan' || node.data.taskType === 'crawl_website') {
      setUseProxy(node.data.use_proxy || false);
    }
  }, [selectedNodeId, isTaskModalOpen]);

  // Open input config modal and populate with current global inputs
  useEffect(() => {
    if (isInputConfigModalOpen) {
      setCurrentInputs(JSON.parse(JSON.stringify(inputs))); // Deep copy
    }
  }, [isInputConfigModalOpen, inputs]);

  // Load inputs and variables from the store when they change
  useEffect(() => {
    // This ensures the VisualWorkflowBuilder stays in sync with the store
    // when workflows are loaded from the API
    
    // Extract variables from inputs if they exist but variables are empty
    if (Object.keys(inputs).length > 0 && Object.keys(variables).length === 0) {
      const extractedVariables = extractVariablesFromInputs(inputs);
      if (Object.keys(extractedVariables).length > 0) {
        setVariables(extractedVariables);
      }
    }
  }, [inputs, variables, setVariables]);

  // Open variables config panel and populate with current global variables
  useEffect(() => {
    if (showVariablesPanel) {
      setCurrentVariables(JSON.parse(JSON.stringify(variables))); // Deep copy
    }
  }, [showVariablesPanel, variables]);







  

  const saveTaskConfiguration = () => {
    if (!selectedNode) return;
    // Use pendingTaskParams if available (most recent), otherwise fall back to currentTaskParams or taskConfig.params
    let updatedParams = { ...(pendingTaskParams || currentTaskParams || taskConfig.params || {}) };
    if (selectedNode.data.taskType === 'nuclei_scan') {
      const allOfficialTemplates = Array.from(selectedTreeTemplates);
      
      updatedParams.template = {
        official: allOfficialTemplates,
        custom: selectedCustomTemplates
      };
    }

    // Update wordlist config if it's a fuzz_website task
    if (selectedNode.data.taskType === 'fuzz_website') {
      if (wordlistInputType === 'url') {
        updatedParams.wordlist = customWordlistUrl;
      } else if (selectedWordlist) {
        updatedParams.wordlist = selectedWordlist.id; // Pass the wordlist ID instead of filename
      } else {
        updatedParams.wordlist = '/workspace/files/webcontent_test.txt'; // Default
      }
    }

    // Update wordlist config if it's a dns_bruteforce task
    if (selectedNode.data.taskType === 'dns_bruteforce') {
      if (wordlistInputType === 'url') {
        updatedParams.wordlist = customWordlistUrl;
      } else if (selectedWordlist) {
        updatedParams.wordlist = selectedWordlist.id; // Pass the wordlist ID instead of filename
      } else {
        updatedParams.wordlist = '/workspace/files/subdomains.txt'; // Default
      }
    }

    const dataToUpdate = {
        params: updatedParams,
        hasConfiguration: Object.keys(updatedParams).length > 0 || selectedNode.data.force,
        nucleiTemplateCount: selectedNode.data.taskType === 'nuclei_scan'
          ? (selectedTreeTemplates.size + selectedCustomTemplates.length)
          : 0,
    };

    // Add output_mode at task level (not in params) if it's a fuzz_website or dns_bruteforce task
    // Save even if empty string (which represents default "Assets" mode)
    if (selectedNode.data.taskType === 'fuzz_website' || selectedNode.data.taskType === 'dns_bruteforce') {
      dataToUpdate.output_mode = outputMode || '';
    }

    // Add use_proxy at task level (not in params) for tasks that support it
    if (selectedNode.data.taskType === 'fuzz_website' || selectedNode.data.taskType === 'nuclei_scan') {
      dataToUpdate.use_proxy = useProxy;
    }

    updateNodeData(selectedNode.id, dataToUpdate);
    setPendingTaskParams(null); // Clear pending parameters after saving
    closeTaskConfigModal();
  };

  // --- NEW: Functions to manage global inputs ---
  const handleSaveInputs = () => {
    // 1. Clean up inputs before saving
    const cleanedInputs = {};
    Object.entries(currentInputs).forEach(([name, config]) => {
      const cleanedConfig = { ...config };

      if (config.type === 'direct') {
        // Remove program asset and finding specific fields
        delete cleanedConfig.asset_type;
        delete cleanedConfig.finding_type;
        delete cleanedConfig.filter;
        delete cleanedConfig.filter_type;
        delete cleanedConfig.limit;
      } else if (config.type === 'program_asset') {
        // Remove direct input and finding specific fields
        delete cleanedConfig.value_type;
        delete cleanedConfig.values;
        delete cleanedConfig.finding_type;
      } else if (config.type === 'program_finding') {
        // Remove direct input and asset specific fields
        delete cleanedConfig.value_type;
        delete cleanedConfig.values;
        delete cleanedConfig.asset_type;
      } else if (config.type === 'program_protected_domains') {
        delete cleanedConfig.value_type;
        delete cleanedConfig.values;
        delete cleanedConfig.asset_type;
        delete cleanedConfig.finding_type;
        delete cleanedConfig.filter;
        delete cleanedConfig.filter_type;
        delete cleanedConfig.limit;
      } else if (config.type === 'program_scope_domains') {
        delete cleanedConfig.value_type;
        delete cleanedConfig.values;
        delete cleanedConfig.asset_type;
        delete cleanedConfig.finding_type;
        delete cleanedConfig.filter;
        delete cleanedConfig.filter_type;
        delete cleanedConfig.limit;
      }

      cleanedInputs[name] = cleanedConfig;
    });

    // 2. Extract variables from cleaned inputs
    const extractedVariables = extractVariablesFromInputs(cleanedInputs);

    // 3. Show notification if new variables were extracted
    const newVariableNames = Object.keys(extractedVariables).filter(name => !variables[name]);
    if (newVariableNames.length > 0) {
      setExtractedVariableNames(newVariableNames);
      setShowVariableNotification(true);
      // Auto-hide notification after 5 seconds
      setTimeout(() => setShowVariableNotification(false), 5000);
    }

    // 4. Merge extracted variables with existing variables
    const updatedVariables = { ...variables, ...extractedVariables };

    // 5. Get current edges to preserve connections
    const currentEdges = useWorkflowStore.getState().edges;

    // 6. Clear all existing input nodes ('inputNode' and the old 'workflowStartNode')
    const nodesToRemove = nodes.filter(
        (node) => node.type === 'inputNode' || node.type === 'workflowStartNode'
    );
    const nodeIdMapping = {};

    // Map old node IDs to new input names for connection preservation
    nodesToRemove.forEach((oldNode) => {
      if (oldNode.data && oldNode.data.name) {
        // For named input nodes, map to the new input name
        nodeIdMapping[oldNode.id] = `input-${oldNode.data.name}`;
      } else if (oldNode.id === 'start' || oldNode.id === 'source') {
        // For start/source nodes, try to find a default input or use the first available
        const firstInputName = Object.keys(cleanedInputs)[0];
        if (firstInputName) {
          nodeIdMapping[oldNode.id] = `input-${firstInputName}`;
        }
      }
    });

    // Remove old input nodes (including empty source when replacing with configured inputs)
    nodesToRemove.forEach((node) => deleteNode(node.id, true));

    // 7. Create new input nodes from `cleanedInputs`
    if (Object.keys(cleanedInputs).length > 0) {
      const firstStepY = steps.length > 0 ? steps[0].yPosition : 200;
      Object.entries(cleanedInputs).forEach(([name, config], index) => {
        const newNode = {
          id: `input-${name}`,
          type: 'inputNode',
          position: { x: 20 + index * 280, y: firstStepY - 150 }, // Place above the first step
          data: {
            name: name,
            ...config,
          },
          deletable: true,
        };
        addNode(newNode);
      });
    } else {
        // 8. If there are no inputs, add back an empty source node
        const sourceNode = {
            id: 'source',
            type: 'inputNode',
            position: { x: 20, y: 20 },
            data: {
                name: 'source',
                isEmpty: true,
            },
            deletable: false,
        };
        addNode(sourceNode);
    }

    // 9. Update edges to use new node IDs
    const updatedEdges = currentEdges.map(edge => {
      const newEdge = { ...edge };
      if (nodeIdMapping[edge.source]) {
        newEdge.source = nodeIdMapping[edge.source];
      }
      if (nodeIdMapping[edge.target]) {
        newEdge.target = nodeIdMapping[edge.target];
      }
      return newEdge;
    });

    // Update the edges in the store
    useWorkflowStore.setState({ edges: updatedEdges });

    // 10. Update both inputs and variables in the store
    setInputs(cleanedInputs);
    setVariables(updatedVariables);

    closeInputConfigModal();
  };

  const handleAddInput = () => {
    const newId = `new_input_${Date.now()}`;
    setEditingInput({
      id: newId,
      name: `input_${Object.keys(currentInputs).length + 1}`,
      type: eventHandlerMode ? 'direct' : 'program_asset',
      ...(eventHandlerMode
        ? getEventHandlerDirectInputDefaults(eventHandlerEventType)
        : { asset_type: 'subdomain', filter: '', filter_type: '', limit: 100 }),
    });
  };

  const handleUpdateInput = (id, field, value, additionalUpdates = {}) => {
    if (editingInput && editingInput.id === id) {
      const updatedInput = { ...editingInput, [field]: value, ...additionalUpdates };

      // Clean up fields when input type changes
      if (field === 'type') {
        if (value === 'direct') {
          // Remove program asset and finding specific fields
          delete updatedInput.asset_type;
          delete updatedInput.finding_type;
          delete updatedInput.filter;
          delete updatedInput.filter_type;
          delete updatedInput.limit;
          // Set default value_type for direct inputs
          updatedInput.value_type = 'domains';
          updatedInput.values = [];
        } else if (value === 'program_asset') {
          // Remove direct input and finding specific fields
          delete updatedInput.value_type;
          delete updatedInput.values;
          delete updatedInput.finding_type;
          // Set default asset_type for program assets
          updatedInput.asset_type = 'subdomain'; // Changed to subdomain to show filter_type options
          updatedInput.filter = '';
          updatedInput.filter_type = '';
          updatedInput.limit = 100;
        } else if (value === 'program_finding') {
          // Remove direct input and asset specific fields
          delete updatedInput.value_type;
          delete updatedInput.values;
          delete updatedInput.asset_type;
          // Set default finding_type for program findings
          updatedInput.finding_type = 'typosquat_url';
          updatedInput.filter = '';
          updatedInput.filter_type = '';
          updatedInput.limit = 100;
        } else if (value === 'program_protected_domains') {
          delete updatedInput.value_type;
          delete updatedInput.values;
          delete updatedInput.asset_type;
          delete updatedInput.finding_type;
          delete updatedInput.filter;
          delete updatedInput.filter_type;
          delete updatedInput.limit;
        } else if (value === 'program_scope_domains') {
          delete updatedInput.value_type;
          delete updatedInput.values;
          delete updatedInput.asset_type;
          delete updatedInput.finding_type;
          delete updatedInput.filter;
          delete updatedInput.filter_type;
          delete updatedInput.limit;
        }
      }

      // Clean up filter_type when asset_type changes to something other than subdomain, ip, or url
      if (field === 'asset_type' && value !== 'subdomain' && value !== 'ip' && value !== 'url') {
        delete updatedInput.filter_type;
      }

      setEditingInput(updatedInput);
    }
  };
  
  const handleSaveEditingInput = () => {
    if (!editingInput) return;
    const { id, name, type, ...rest } = editingInput;
    
    // Clean up unused fields based on input type
    const cleanedConfig = { type, ...rest };
    
    if (type === 'direct') {
      // For direct inputs, remove asset_type, finding_type and program-related fields
      delete cleanedConfig.asset_type;
      delete cleanedConfig.finding_type;
      delete cleanedConfig.filter;
      delete cleanedConfig.filter_type;
      delete cleanedConfig.limit;
    } else if (type === 'program_asset') {
      // For program assets, remove value_type, values, and finding_type
      delete cleanedConfig.value_type;
      delete cleanedConfig.values;
      delete cleanedConfig.finding_type;
    } else if (type === 'program_finding') {
      // For program findings, remove value_type, values, and asset_type
      delete cleanedConfig.value_type;
      delete cleanedConfig.values;
      delete cleanedConfig.asset_type;
    } else if (type === 'program_protected_domains') {
      delete cleanedConfig.value_type;
      delete cleanedConfig.values;
      delete cleanedConfig.asset_type;
      delete cleanedConfig.finding_type;
      delete cleanedConfig.filter;
      delete cleanedConfig.filter_type;
      delete cleanedConfig.limit;
    } else if (type === 'program_scope_domains') {
      delete cleanedConfig.value_type;
      delete cleanedConfig.values;
      delete cleanedConfig.asset_type;
      delete cleanedConfig.finding_type;
      delete cleanedConfig.filter;
      delete cleanedConfig.filter_type;
      delete cleanedConfig.limit;
    }
    
    // Check for name uniqueness
    if (Object.keys(currentInputs).some(key => key === name && key !== id)) {
        alert('Input name must be unique.');
        return;
    }
    
    const newInputs = { ...currentInputs };
    if (id !== name && newInputs[id]) {
        delete newInputs[id]; // handle name change
    }
    newInputs[name] = cleanedConfig;
    
    setCurrentInputs(newInputs);
    setEditingInput(null);
  };
  
  const handleRemoveInput = (inputName) => {
    const newInputs = { ...currentInputs };
    delete newInputs[inputName];
    setCurrentInputs(newInputs);
  };

  // Special handler for ProgramAssetSelector to handle combined asset type + filter type updates
  const handleAssetTypeAndFilterChange = (assetType, filterType) => {
    if (editingInput) {
      // Auto-convert to program_finding if typosquat_url or external_link is selected
      if (assetType === 'typosquat_url' || assetType === 'external_link') {
        // Switch to program_finding type and set finding_type
        const updatedInput = {
          ...editingInput,
          type: 'program_finding',
          finding_type: assetType,
          filter_type: filterType,
        };
        // Remove asset-specific fields
        delete updatedInput.asset_type;
        setEditingInput(updatedInput);
      } else {
        handleUpdateInput(editingInput.id, 'asset_type', assetType, { filter_type: filterType });
      }
    }
  };

  // Special handler for ProgramAssetSelector to handle combined finding type + filter type updates
  const handleFindingTypeAndFilterChange = (findingType, filterType) => {
    if (editingInput) {
      handleUpdateInput(editingInput.id, 'finding_type', findingType, { filter_type: filterType });
    }
  };

  // --- NEW: Functions to manage variables ---
  
  // Function to extract variables from input values
  const extractVariablesFromInputs = (inputs) => {
    const extractedVariables = {};
    const variableRegex = /\{\{([^}]+)\}\}/g;
    
    Object.entries(inputs).forEach(([inputName, inputConfig]) => {
      // Only process direct inputs that have values
      if (inputConfig.type === 'direct' && inputConfig.values && Array.isArray(inputConfig.values)) {
        inputConfig.values.forEach(value => {
          if (typeof value === 'string') {
            let match;
            while ((match = variableRegex.exec(value)) !== null) {
              const variableName = match[1].trim();
              if (!extractedVariables[variableName]) {
                extractedVariables[variableName] = {
                  value: '',
                  description: `Variable used in input: ${inputName}`
                };
              }
            }
          }
        });
      }
    });
    
    return extractedVariables;
  };

  const handleSaveVariables = () => {
    setVariables(currentVariables);
    setShowVariablesPanel(false);
  };

  const handleAddVariable = () => {
    const newId = `new_variable_${Date.now()}`;
    setEditingVariable({
      id: newId,
      name: `variable_${Object.keys(currentVariables).length + 1}`,
      value: '',
      description: ''
    });
  };

  const handleUpdateVariable = (id, field, value) => {
    if (editingVariable && editingVariable.id === id) {
      setEditingVariable(prev => ({ ...prev, [field]: value }));
    }
  };

  const handleSaveEditingVariable = () => {
    if (!editingVariable) return;
    const { id, name, ...rest } = editingVariable;
    
    // Check for name uniqueness
    if (Object.keys(currentVariables).some(key => key === name && key !== id)) {
      alert('Variable name must be unique.');
      return;
    }
    
    const newVariables = { ...currentVariables };
    if (id !== name && newVariables[id]) {
      delete newVariables[id]; // handle name change
    }
    newVariables[name] = rest;
    
    setCurrentVariables(newVariables);
    setEditingVariable(null);
  };

  const handleRemoveVariable = (variableName) => {
    const newVariables = { ...currentVariables };
    delete newVariables[variableName];
    setCurrentVariables(newVariables);
  };



  return (
    <ReactFlowProvider>
      <div className="workflow-builder-layout-root d-flex flex-column" style={{ height: '100%', minHeight: 0 }}>
        {showMetadataBar && (
          <WorkflowBuilderMetadataBar
            workflowName={workflowName}
            setWorkflowName={setWorkflowName}
            workflowDescription={workflowDescription}
            setWorkflowDescription={setWorkflowDescription}
          />
        )}

        {eventHandlerMode && (
          <Alert variant="info" className="workflow-builder-inline-alert mb-0">
            <small>
              <strong>Event handler workflow:</strong> This workflow receives data from the event. Configure inputs with template variables like {'{domain_list_array}'} for batched event data.
            </small>
          </Alert>
        )}

        {/* Variable Extraction Notification */}
        {showVariableNotification && (
          <Alert 
            variant="info" 
            dismissible 
            onClose={() => setShowVariableNotification(false)}
            style={{
              position: 'fixed',
              top: '20px',
              right: '20px',
              zIndex: 9999,
              maxWidth: '400px'
            }}
          >
            <strong>Variables Detected!</strong><br/>
            The following variables were automatically extracted from your inputs:<br/>
            {extractedVariableNames.map(name => (
              <Badge key={name} bg="primary" className="me-1">
                {name}
              </Badge>
            ))}<br/>
            <small>Open the Configure Variables panel to set their values.</small>
          </Alert>
        )}

        <div
          className="workflow-builder-workspace"
          style={{ flexGrow: 1, position: 'relative', display: 'flex', minHeight: 0 }}
        >
          <TaskLibrarySidebar setDraggedTaskType={setDraggedTaskType} />

          {/* Main Canvas Area — elevated tile beside the library (not stacked under it) */}
          <div className="workflow-canvas-shell" style={{ flex: 1, position: 'relative', minHeight: 0, overflow: 'hidden' }}>
            {/* Action Panel */}
            <Panel position="top-left" className="workflow-action-panel">
              <div className="d-flex gap-2 flex-wrap">
                <Button 
                  variant="outline-success" 
                  size="sm"
                  onClick={isInputConfigModalOpen ? closeInputConfigModal : openInputConfigModal}
                >
                  🚀 Configure Inputs
                </Button>
                <Button 
                  variant="outline-info" 
                  size="sm"
                  onClick={showVariablesPanel ? () => setShowVariablesPanel(false) : () => setShowVariablesPanel(true)}
                >
                  🔧 Configure Variables
                </Button>
                <Button 
                  variant="outline-danger" 
                  size="sm"
                  onClick={clearWorkflow}
                >
                  🗑️ Clear All
                </Button>
              </div>
            </Panel>

            {/* React Flow Canvas — flex child fills shell; pan/zoom for tall graphs */}
            <div className="workflow-canvas-flow-host">
              <FlowCanvas
                onDragOver={onDragOver}
                draggedTaskType={draggedTaskType}
                setDraggedTaskType={setDraggedTaskType}
              />
            </div>

            {/* Input Configuration Sidebar - slides in from right */}
            <InputConfigSidebar
              isOpen={isInputConfigModalOpen}
              onClose={closeInputConfigModal}
              currentInputs={currentInputs}
              setCurrentInputs={setCurrentInputs}
              editingInput={editingInput}
              setEditingInput={setEditingInput}
              handleAddInput={handleAddInput}
              handleUpdateInput={handleUpdateInput}
              handleSaveEditingInput={handleSaveEditingInput}
              handleRemoveInput={handleRemoveInput}
              handleAssetTypeAndFilterChange={handleAssetTypeAndFilterChange}
              handleFindingTypeAndFilterChange={handleFindingTypeAndFilterChange}
              handleSaveInputs={handleSaveInputs}
              eventHandlerMode={eventHandlerMode}
            />

            {/* Variables Configuration Sidebar - slides in from right, same pattern as Inputs */}
            <VariablesConfigSidebar
              isOpen={showVariablesPanel}
              onClose={() => setShowVariablesPanel(false)}
              currentVariables={currentVariables}
              editingVariable={editingVariable}
              setEditingVariable={setEditingVariable}
              handleAddVariable={handleAddVariable}
              handleUpdateVariable={handleUpdateVariable}
              handleSaveEditingVariable={handleSaveEditingVariable}
              handleRemoveVariable={handleRemoveVariable}
              handleSaveVariables={handleSaveVariables}
            />
          </div>
        </div>

      {/* Task Configuration Modal */}
      <Modal 
          show={isTaskModalOpen}
          onHide={closeTaskConfigModal}
        dialogClassName="modal-xl"
      >
        <Modal.Header closeButton>
          <Modal.Title>
            Configure {selectedNode && TASK_TYPES[selectedNode.data.taskType]?.name}
            {selectedNode && selectedNode.data.taskType === 'typosquat_detection' && 
             taskConfig.params?.analyze_input_as_variations && (
              <div className="mt-2">
                <small className="text-muted">
                  🔍 Input Domain Analysis Mode
                </small>
              </div>
            )}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          {selectedNode && (
            <Tabs defaultActiveKey="params" className="mb-3">
              <Tab eventKey="params" title="Parameters">
                {/* Input mapping - map connections to task input types */}
                {selectedNode && (
                  <InputMappingSection
                    selectedNode={selectedNode}
                    updateNodeData={updateNodeData}
                  />
                )}
                {/* Task-specific parameter configuration */}
                {selectedNode && (
                  <TaskParameterSelector
                    taskType={selectedNode.data.taskType}
                    taskParams={taskConfig.params || {}}
                    onParameterChange={(newParams) => {
                      // Store the current parameters separately
                      setCurrentTaskParams(newParams);
                      setPendingTaskParams(newParams);

                      // If taskConfig is empty, initialize it with selectedNode.data first
                      const baseConfig = Object.keys(taskConfig).length > 0 ? taskConfig : (selectedNode?.data || {});

                      setTaskConfig({
                        ...baseConfig,
                        params: newParams
                      });
                    }}
                    // Nuclei template props
                    selectedOfficialTemplates={selectedTreeTemplates}
                    selectedCustomTemplates={selectedCustomTemplates}
                    onOfficialTemplatesChange={setSelectedTreeTemplates}
                    onCustomTemplatesChange={setSelectedCustomTemplates}
                    // Wordlist props
                    selectedWordlist={selectedWordlist}
                    customWordlistUrl={customWordlistUrl}
                    wordlistInputType={wordlistInputType}
                    onWordlistChange={setSelectedWordlist}
                    onCustomUrlChange={setCustomWordlistUrl}
                    onInputTypeChange={setWordlistInputType}
                    // Output mode props
                    outputMode={outputMode}
                    onOutputModeChange={(newValue) => {
                      setOutputMode(newValue);
                    }}
                    // Node update callback
                    selectedNode={selectedNode}
                    updateNodeData={updateNodeData}
                  />
                )}

                {/* Special info alert for typosquat input analysis mode */}
                {selectedNode && selectedNode.data.taskType === 'typosquat_detection' &&
                 taskConfig.params?.analyze_input_as_variations && (
                  <Alert variant="info" className="mb-4">
                    <strong>🔍 Input Domain Analysis Mode Enabled</strong><br/>
                    <small>
                      In this mode, input domains are treated as potential typosquat domains and analyzed directly.
                      No variations are generated - the task will analyze each input domain as if it were a typosquat variation.
                      <br/><br/>
                      <strong>Use cases:</strong> Analyzing suspicious domains, validating potential typosquats,
                      or investigating specific domains of interest.
                    </small>
                  </Alert>
                )}
              </Tab>

              <Tab eventKey="options" title="Options">
                <Alert variant="info">
                  <small>
                    <strong>Note:</strong> The "Force execution" option has been moved to the task node itself for easier access.
                    You can now toggle it directly on the workflow canvas.
                  </small>
                </Alert>

                {/* Proxy Option - Show for tasks that support proxying */}
                {selectedNode && (selectedNode.data.taskType === 'fuzz_website' || selectedNode.data.taskType === 'nuclei_scan') && (
                  <Form.Group className="mb-3">
                    <Form.Check
                      type="checkbox"
                      id="useProxyCheckbox"
                      label="🔒 Use AWS API Gateway Proxy (FireProx)"
                      checked={useProxy}
                      onChange={(e) => setUseProxy(e.target.checked)}
                    />
                    <Form.Text className="text-muted">
                      Route {selectedNode.data.taskType === 'fuzz_website' ? 'fuzzing' : 'scanning'} requests through AWS API Gateway proxies to mask reconnaissance traffic
                    </Form.Text>
                  </Form.Group>
                )}
              </Tab>
            </Tabs>
          )}
        </Modal.Body>
        <Modal.Footer>
            <Button variant="secondary" onClick={closeTaskConfigModal}>
            Cancel
          </Button>
          <Button variant="primary" onClick={saveTaskConfiguration}>
            Save Configuration
          </Button>
        </Modal.Footer>
      </Modal>

      </div>
    </ReactFlowProvider>
  );
}

export default VisualWorkflowBuilder; 