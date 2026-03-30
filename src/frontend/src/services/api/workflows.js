import { api } from './client';

export const jobAPI = {
  getAll: async (page = 1, limit = 25, jobType = null, status = null) => {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString()
    });
    if (jobType) params.append('job_type', jobType);
    if (status) params.append('status', status);
    
    const response = await api.get(`/jobs?${params.toString()}`);
    return response.data;
  },
  
  getStatus: async (jobId) => {
    const response = await api.get(`/jobs/${jobId}/status`);
    return response.data;
  },
  
  getResults: async (jobId) => {
    const response = await api.get(`/jobs/${jobId}/results`);
    return response.data;
  },
  
  delete: async (jobId) => {
    const response = await api.delete(`/jobs/${jobId}`);
    return response.data;
  }
};

// Programs API calls
export const programAPI = {
  getAll: async () => {
    const response = await api.get('/programs');
    return response.data;
  },

  search: async (params = {}) => {
    // params: { search, exact_match, has_domains, has_ips, has_workflows, has_findings, sort_by, sort_dir, page, page_size }
    const response = await api.post('/programs/search', params);
    return response.data;
  },

  getByName: async (programName) => {
    const response = await api.get(`/programs/${encodeURIComponent(programName)}`);
    return response.data;
  },

  create: async (programData) => {
    const response = await api.post('/programs', programData);
    return response.data;
  },

  update: async (programName, programData, overwrite = false) => {
    const url = `/programs/${encodeURIComponent(programName)}${overwrite ? '?overwrite=true' : ''}`;
    const response = await api.put(url, programData);
    return response.data;
  },

  updateNotificationSettings: async (programName, notificationSettings) => {
    const url = `/programs/${encodeURIComponent(programName)}`;
    const response = await api.put(url, { notification_settings: notificationSettings });
    return response.data;
  },

  delete: async (programName) => {
    const response = await api.delete(`/programs/${encodeURIComponent(programName)}`);
    return response.data;
  },

  importFromHackerOne: async (programHandle) => {
    const response = await api.post('/programs/import/hackerone', {
      program_handle: programHandle
    });
    return response.data;
  },

  importFromYesWeHack: async (programSlug, jwtToken) => {
    const response = await api.post('/programs/import/yeswehack', {
      program_slug: programSlug,
      jwt_token: jwtToken
    });
    return response.data;
  },

  importFromIntigriti: async (programHandle) => {
    const response = await api.post('/programs/import/intigriti', {
      program_handle: programHandle
    });
    return response.data;
  },

  importFromBugcrowd: async (programCode, sessionToken) => {
    const response = await api.post('/programs/import/bugcrowd', {
      program_code: programCode,
      session_token: sessionToken
    });
    return response.data;
  }
};

// Workflow API calls - using consolidated unified API with clear path separation
export const workflowAPI = {
  // === Workflow Definitions (Templates/Saved Workflows) ===
  
  // Get all saved workflow definitions
  getWorkflows: async (programName = null) => {
    const params = programName ? `?program_name=${encodeURIComponent(programName)}` : '';
    const response = await api.get(`/workflows/definitions${params}`);
    return response.data;
  },

  // Save a new workflow definition (not run it)
  saveWorkflow: async (workflowData) => {
    const response = await api.post('/workflows/definitions', {
      name: workflowData.workflow_name,
      program_name: workflowData.program_name,
      description: workflowData.description || `Workflow: ${workflowData.workflow_name}`,
      steps: workflowData.steps,
      variables: workflowData.variables || {},
      inputs: workflowData.inputs || {}
    });
    return response.data;
  },

  // Backward compatibility alias - use saveWorkflow instead
  createWorkflow: async (workflowData) => {
    console.warn('createWorkflow is deprecated, use saveWorkflow for saving definitions or runWorkflow for execution');
    const response = await api.post('/workflows/definitions', {
      name: workflowData.workflow_name,
      program_name: workflowData.program_name,
      description: workflowData.description || `Workflow: ${workflowData.workflow_name}`,
      steps: workflowData.steps,
      variables: workflowData.variables || {},
      inputs: workflowData.inputs || {}
    });
    return response.data;
  },

  // Update an existing workflow definition
  updateWorkflow: async (workflowId, workflowData) => {
    const response = await api.put(`/workflows/definitions/${workflowId}`, {
      name: workflowData.workflow_name,
      program_name: workflowData.program_name,
      description: workflowData.description || `Workflow: ${workflowData.workflow_name}`,
      steps: workflowData.steps,
      variables: workflowData.variables || {},
      inputs: workflowData.inputs || {}
    });
    return response.data;
  },

  // Delete a workflow definition
  deleteWorkflow: async (workflowId) => {
    const response = await api.delete(`/workflows/definitions/${workflowId}`);
    return response.data;
  },

  // Get workflow definition by ID
  getWorkflow: async (workflowId) => {
    const response = await api.get(`/workflows/definitions/${workflowId}`);
    return response.data;
  },

  // === Workflow Executions (Runtime Operations) ===
  
  // Execute/run a workflow with complete definition
  runWorkflow: async (workflowData) => {
    // Send the complete workflow definition for execution
    const response = await api.post('/workflows/run', {
      workflow_name: workflowData.workflow_name,
      program_name: workflowData.program_name,
      description: workflowData.description,
      steps: workflowData.steps,
      variables: workflowData.variables || {},
      inputs: workflowData.inputs || {},
      workflow_definition_id: workflowData.workflow_definition_id // Include workflow definition ID for saved workflows
    });
    return response.data;
  },

  // Get workflow execution status list (paginated)
  getWorkflowStatus: async (page = 1, limit = 25, programName = null, sortField = null, sortOrder = 'desc') => {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString()
    });
    if (programName) {
      params.append('program_name', programName);
    }
    if (sortField) {
      params.append('sort_field', sortField);
      params.append('sort_order', sortOrder);
    }
    const response = await api.get(`/workflows/executions?${params}`);
    return response.data;
  },

  // Get detailed status for a specific workflow execution
  getWorkflowStatusDetail: async (workflowId) => {
    const response = await api.get(`/workflows/executions/${workflowId}`);
    return response.data;
  },

  // Get workflow execution logs
  getWorkflowLogs: async (workflowId) => {
    const response = await api.get(`/workflows/executions/${workflowId}/logs`);
    return response.data;
  },

  // Get workflow execution tasks
  getWorkflowTasks: async (workflowId) => {
    const response = await api.get(`/workflows/executions/${workflowId}/tasks`);
    return response.data;
  },

  // Delete a workflow execution
  deleteWorkflowExecution: async (workflowId) => {
    const response = await api.delete(`/workflows/executions/${workflowId}`);
    return response.data;
  },

  // Stop a running workflow execution
  stopWorkflow: async (workflowId) => {
    const response = await api.post(`/workflows/executions/${workflowId}/stop`);
    return response.data;
  },

  // === Legacy Endpoints (for backward compatibility) ===
  
  // Legacy: Get all workflow logs (use getWorkflowStatus instead)
  getAllWorkflowLogs: async () => {
    console.warn('getAllWorkflowLogs is deprecated, use getWorkflowStatus for paginated results');
    const response = await api.get('/workflows/logs');
    return response.data;
  },

  // Legacy: Query workflow logs (use getWorkflowStatus instead)
  queryWorkflowLogs: async (queryFilter) => {
    console.warn('queryWorkflowLogs is deprecated, use getWorkflowStatus for better performance');
    const response = await api.post('/workflows/logs/query', queryFilter);
    return response.data;
  }
};

// Queue API calls
export const queueAPI = {
  getStatus: async () => {
    const response = await api.get('/queue/status');
    return response.data;
  },

  getJobs: async () => {
    const response = await api.get('/queue/jobs');
    return response.data;
  },

  clearQueue: async () => {
    const response = await api.delete('/queue/clear');
    return response.data;
  }
};

export const scheduledJobsAPI = {
  // Get all scheduled jobs
  getAll: async (limit = 25, skip = 0, status = null, jobType = null) => {
    const params = new URLSearchParams();
    params.append('limit', limit);
    params.append('skip', skip);
    if (status) params.append('status', status);
    if (jobType) params.append('job_type', jobType);
    
    const response = await api.get(`/scheduled-jobs?${params.toString()}`);
    return response.data;
  },

  // Get a specific scheduled job
  getById: async (scheduleId) => {
    const response = await api.get(`/scheduled-jobs/${scheduleId}`);
    return response.data;
  },

  // Create a new scheduled job
  create: async (jobData) => {
    const response = await api.post('/scheduled-jobs', jobData);
    return response.data;
  },

  // Update a scheduled job
  update: async (scheduleId, jobData) => {
    const response = await api.put(`/scheduled-jobs/${scheduleId}`, jobData);
    return response.data;
  },

  // Delete a scheduled job
  delete: async (scheduleId) => {
    const response = await api.delete(`/scheduled-jobs/${scheduleId}`);
    return response.data;
  },

  // Enable a scheduled job
  enable: async (scheduleId) => {
    const response = await api.post(`/scheduled-jobs/${scheduleId}/enable`);
    return response.data;
  },

  // Disable a scheduled job
  disable: async (scheduleId) => {
    const response = await api.post(`/scheduled-jobs/${scheduleId}/disable`);
    return response.data;
  },

  // Run a scheduled job immediately
  runNow: async (scheduleId) => {
    const response = await api.post(`/scheduled-jobs/${scheduleId}/run-now`);
    return response.data;
  },

  // Get execution history for a scheduled job
  getExecutionHistory: async (scheduleId, limit = 25, skip = 0) => {
    const params = new URLSearchParams();
    params.append('limit', limit);
    params.append('skip', skip);
    
    const response = await api.get(`/scheduled-jobs/${scheduleId}/executions?${params.toString()}`);
    return response.data;
  },

  // Get available job types
  getJobTypes: async () => {
    const response = await api.get('/scheduled-jobs/types');
    return response.data;
  }
}; // scheduledJobsAPI
