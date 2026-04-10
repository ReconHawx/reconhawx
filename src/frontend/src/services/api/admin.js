import { api } from './client';

export const authAPI = {
  login: async (username, password) => {
    const response = await api.post('/auth/login', {
      username,
      password
    });
    return response.data;
  },

  logout: async (refreshToken) => {
    const response = await api.post('/auth/logout', {
      refresh_token: refreshToken
    });
    return response.data;
  },

  refreshToken: async (refreshToken) => {
    const response = await api.post('/auth/refresh', {
      refresh_token: refreshToken
    });
    return response.data;
  },

  logoutAllDevices: async () => {
    const response = await api.post('/auth/logout-all');
    return response.data;
  },

  getCurrentUser: async () => {
    const response = await api.get('/auth/user');
    return response.data;
  },

  changeOwnPassword: async (currentPassword, newPassword) => {
    const response = await api.post('/auth/me/password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  // API Token Management
  getApiTokens: async () => {
    const response = await api.get('/auth/api-tokens');
    return response.data;
  },

  createApiToken: async (tokenData) => {
    const response = await api.post('/auth/api-tokens', tokenData);
    return response.data;
  },

  revokeApiToken: async (tokenId) => {
    const response = await api.delete(`/auth/api-tokens/${tokenId}`);
    return response.data;
  }
};

// User Management API calls (superuser only)
export const userManagementAPI = {
  getUsers: async (page = 1, limit = 25, search = '') => {
    const params = new URLSearchParams({ page: page.toString(), limit: limit.toString() });
    if (search) {
      params.append('search', search);
    }
    const response = await api.get(`/auth/users?${params}`);
    return response.data;
  },

  createUser: async (userData) => {
    const response = await api.post('/auth/users', userData);
    return response.data;
  },

  getUser: async (userId) => {
    const response = await api.get(`/auth/users/${userId}`);
    return response.data;
  },

  updateUser: async (userId, userData) => {
    const response = await api.put(`/auth/users/${userId}`, userData);
    return response.data;
  },

  deleteUser: async (userId) => {
    const response = await api.delete(`/auth/users/${userId}`);
    return response.data;
  },

  changePassword: async (userId, newPassword, forcePasswordChange = false) => {
    const response = await api.put(`/auth/users/${userId}/password`, {
      new_password: newPassword,
      force_password_change: Boolean(forcePasswordChange),
    });
    return response.data;
  },

  getUsersForAssignment: async (program = null) => {
    const params = new URLSearchParams();
    if (program) {
      params.append('program', program);
    }
    const response = await api.get(`/auth/users/assignment?${params}`);
    return response.data;
  }
};

// External Links API calls
export const externalLinksAPI = {
  getExternalLinks: async (programName = '', linkSearch = '', linkNegative = false, rootSite = '', page = null, pageSize = null) => {
    const params = new URLSearchParams();
    if (programName) params.append('program_name', programName);
    if (linkSearch) params.append('link_search', linkSearch);
    if (linkNegative) params.append('link_negative', 'true');
    if (rootSite) params.append('root_site', rootSite);
    if (page !== null) params.append('page', page.toString());
    if (pageSize !== null) params.append('page_size', pageSize.toString());
    
    const response = await api.get(`/findings/external-links/?${params.toString()}`);
    return response.data;
  }
};

// Admin API calls
export const adminAPI = {
  // Recon Task Parameters
  listReconTaskParameters: async () => {
    const response = await api.get('/admin/recon-tasks/parameters');
    return response.data;
  },

  getReconTaskParameters: async (reconTask) => {
    const response = await api.get(`/admin/recon-tasks/${reconTask}/parameters`);
    return response.data;
  },

  createReconTaskParameters: async (reconTask, parameters) => {
    const response = await api.post(`/admin/recon-tasks/${reconTask}/parameters`, {
      parameters: parameters
    });
    return response.data;
  },

  updateReconTaskParameters: async (reconTask, parameters) => {
    const response = await api.put(`/admin/recon-tasks/${reconTask}/parameters`, {
      parameters: parameters
    });
    return response.data;
  },

  deleteReconTaskParameters: async (reconTask) => {
    const response = await api.delete(`/admin/recon-tasks/${reconTask}/parameters`);
    return response.data;
  },

  // Last Execution Threshold
  getLastExecutionThreshold: async (reconTask) => {
    const response = await api.get(`/admin/recon-tasks/${reconTask}/last-execution-threshold`);
    return response.data;
  },

  setLastExecutionThreshold: async (reconTask, threshold) => {
    const response = await api.put(`/admin/recon-tasks/${reconTask}/last-execution-threshold`, {
      last_execution_threshold: threshold
    });
    return response.data;
  },

  // Chunk Size
  getChunkSize: async (reconTask) => {
    const response = await api.get(`/admin/recon-tasks/${reconTask}/chunk-size`);
    return response.data;
  },

  setChunkSize: async (reconTask, chunkSize) => {
    const response = await api.put(`/admin/recon-tasks/${reconTask}/chunk-size`, {
      chunk_size: chunkSize
    });
    return response.data;
  },

  // AWS Credentials
  listAwsCredentials: async () => {
    const response = await api.get('/admin/aws-credentials');
    return response.data;
  },

  getAwsCredential: async (credentialId) => {
    const response = await api.get(`/admin/aws-credentials/${credentialId}`);
    return response.data;
  },

  createAwsCredential: async (data) => {
    const response = await api.post('/admin/aws-credentials', data);
    return response.data;
  },

  updateAwsCredential: async (credentialId, data) => {
    const response = await api.put(`/admin/aws-credentials/${credentialId}`, data);
    return response.data;
  },

  deleteAwsCredential: async (credentialId) => {
    const response = await api.delete(`/admin/aws-credentials/${credentialId}`);
    return response.data;
  },

  // Event Queue Statistics (NATS JetStream)
  getEventStats: async () => {
    const response = await api.get('/admin/events/stats');
    return response.data;
  },

  getEventPending: async (limit = 50, options = {}) => {
    const { search, max_scan } = options;
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (search != null && String(search).trim() !== '') {
      params.set('search', String(search).trim());
      if (max_scan != null && max_scan !== '') {
        params.set('max_scan', String(max_scan));
      }
    }
    const response = await api.get(`/admin/events/pending?${params.toString()}`);
    return response.data;
  },

  purgeEventsStream: async (confirm = 'PURGE_EVENTS') => {
    const response = await api.post('/admin/events/purge', { confirm });
    return response.data;
  },

  deleteEventMessages: async (sequences) => {
    const response = await api.post('/admin/events/messages/delete', { sequences });
    return response.data;
  },

  getEventBatches: async () => {
    const response = await api.get('/admin/events/batches');
    return response.data;
  },

  flushEventBatches: async () => {
    const response = await api.post('/admin/events/batches/flush');
    return response.data;
  },

  clearEventBatches: async () => {
    const response = await api.post('/admin/events/batches/clear');
    return response.data;
  },

  getEventHandlerStatus: async () => {
    const response = await api.get('/admin/event-handler/status');
    return response.data;
  },

  pauseEventHandler: async () => {
    const response = await api.post('/admin/event-handler/pause');
    return response.data;
  },

  resumeEventHandler: async () => {
    const response = await api.post('/admin/event-handler/resume');
    return response.data;
  },

  // Event Handler Config (superuser)
  getEventHandlerConfig: async () => {
    const response = await api.get('/admin/event-handler-configs');
    return response.data;
  },

  updateEventHandlerConfig: async (handlers) => {
    const response = await api.put('/admin/event-handler-configs', { handlers });
    return response.data;
  },

  getEventHandlerConfigDefaults: async () => {
    const response = await api.get('/admin/event-handler-configs/defaults');
    return response.data;
  },

  getEventHandlerSystemConfig: async () => {
    const response = await api.get('/admin/event-handler-configs/system');
    return response.data;
  },

  // CT Monitor Control
  getCtMonitorStatus: async () => {
    const response = await api.get('/admin/ct-monitor/status');
    return response.data;
  },

  startCtMonitor: async () => {
    const response = await api.post('/admin/ct-monitor/start');
    return response.data;
  },

  stopCtMonitor: async () => {
    const response = await api.post('/admin/ct-monitor/stop');
    return response.data;
  },

  getCtMonitorRuntimeSettings: async () => {
    const response = await api.get('/admin/ct-monitor/runtime-settings');
    return response.data;
  },

  updateCtMonitorRuntimeSettings: async (payload) => {
    const response = await api.put('/admin/ct-monitor/runtime-settings', payload);
    return response.data;
  },

  getWorkflowKubernetesSettings: async () => {
    const response = await api.get('/admin/workflow-kubernetes-settings');
    return response.data;
  },

  updateWorkflowKubernetesSettings: async (payload) => {
    const response = await api.put('/admin/workflow-kubernetes-settings', payload);
    return response.data;
  },

  deleteWorkflowKubernetesSettings: async () => {
    const response = await api.delete('/admin/workflow-kubernetes-settings');
    return response.data;
  },

  // AI Settings
  getAiSettings: async () => {
    const response = await api.get('/admin/ai-settings');
    return response.data;
  },

  getAiSettingsDefaults: async () => {
    const response = await api.get('/admin/ai-settings/defaults');
    return response.data;
  },

  updateAiSettings: async (payload) => {
    const response = await api.put('/admin/ai-settings', payload);
    return response.data;
  },

  // System Status
  getSystemStatus: async () => {
    const response = await api.get('/admin/system-status');
    return response.data;
  },

  // Database backup / restore (superuser)
  getDatabaseBackupStatus: async () => {
    const response = await api.get('/admin/database/status');
    return response.data;
  },

  downloadDatabaseBackup: async (format = 'custom') => {
    const response = await api.get('/admin/database/backup', {
      params: { format },
      responseType: 'blob'
    });
    let filename = format === 'plain' ? 'reconhawx-backup.sql' : 'reconhawx-backup.dump';
    const cd = response.headers['content-disposition'];
    if (cd) {
      const m = /filename="([^"]+)"/.exec(cd);
      if (m) filename = m[1];
    }
    return { blob: response.data, filename };
  },

  getMaintenanceSettings: async () => {
    const response = await api.get('/admin/database/maintenance/settings');
    return response.data;
  },

  putMaintenanceSettings: async (payload) => {
    const response = await api.put('/admin/database/maintenance/settings', payload);
    return response.data;
  },

  kueueHoldClusterQueues: async () => {
    const response = await api.post('/admin/database/maintenance/kueue/hold');
    return response.data;
  },

  kueueClearStopPolicy: async () => {
    const response = await api.post('/admin/database/maintenance/kueue/clear-stop-policy');
    return response.data;
  },

  kueueDrainStatus: async () => {
    const response = await api.get('/admin/database/maintenance/kueue/drain-status');
    return response.data;
  },

  kueueFlushBatchJobs: async () => {
    const response = await api.post('/admin/database/maintenance/kueue/flush-batch-jobs');
    return response.data;
  },

  stageDatabaseRestore: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/admin/database/maintenance/restore/stage', formData);
    return response.data;
  },

  createDatabaseRestoreJob: async (stagingId, confirm = 'RESTORE_DATABASE') => {
    const response = await api.post('/admin/database/maintenance/restore/job', {
      staging_id: stagingId,
      confirm
    });
    return response.data;
  },

  getDatabaseRestoreJobStatus: async (jobName) => {
    const response = await api.get(
      `/admin/database/maintenance/restore/job/${encodeURIComponent(jobName)}`
    );
    return response.data;
  }
};

// Nuclei Templates API calls
export const nucleiTemplatesAPI = {
  list: async (skip = 0, limit = 100, activeOnly = true, tags = null, severity = null, search = null) => {
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: limit.toString(),
      active_only: activeOnly.toString()
    });
    
    if (tags) params.append('tags', tags);
    if (severity) params.append('severity', severity);
    if (search) params.append('search', search);
    
    const url = `/nuclei-templates/?${params}`;
    const response = await api.get(url);
    return response.data;
  },

  getById: async (templateId) => {
    const response = await api.get(`/nuclei-templates/${templateId}`);
    return response.data;
  },

  getByName: async (templateName) => {
    const response = await api.get(`/nuclei-templates/name/${encodeURIComponent(templateName)}`);
    return response.data;
  },

  create: async (templateData) => {
    const response = await api.post('/nuclei-templates/', templateData);
    return response.data;
  },

  update: async (templateId, updateData) => {
    const response = await api.put(`/nuclei-templates/${templateId}`, updateData);
    return response.data;
  },

  delete: async (templateId, hardDelete = false) => {
    const params = hardDelete ? '?hard_delete=true' : '';
    const response = await api.delete(`/nuclei-templates/${templateId}${params}`);
    return response.data;
  },

  checkExists: async (templateId) => {
    const response = await api.get(`/nuclei-templates/check/${templateId}/exists`);
    return response.data;
  },

  // Official templates endpoints
  getOfficialStructure: async () => {
    const response = await api.get('/nuclei-templates/official/structure');
    return response.data;
  },

  getOfficialCategories: async () => {
    const response = await api.get('/nuclei-templates/official/categories');
    return response.data;
  },

  getOfficialTemplatesByCategory: async (categoryName) => {
    const response = await api.get(`/nuclei-templates/official/category/${encodeURIComponent(categoryName)}`);
    return response.data;
  },

  updateOfficialTemplates: async () => {
    const response = await api.post('/nuclei-templates/official/update');
    return response.data;
  },

  setupOfficialTemplates: async () => {
    const response = await api.post('/nuclei-templates/official/setup');
    return response.data;
  },

  getOfficialTemplatesStatus: async () => {
    const response = await api.get('/nuclei-templates/official/status');
    return response.data;
  },

  // New enhanced browsing endpoints
  getOfficialTemplatesByFolder: async (folderPath) => {
    const response = await api.get(`/nuclei-templates/official/folder/${encodeURIComponent(folderPath)}`);
    return response.data;
  },

  searchOfficialTemplates: async (query, limit = 50) => {
    const params = new URLSearchParams({
      query: query,
      limit: limit.toString()
    });
    const response = await api.get(`/nuclei-templates/official/search?${params}`);
    return response.data;
  },

  getOfficialTemplatesTree: async () => {
    const response = await api.get('/nuclei-templates/official/tree');
    return response.data;
  },

  // Get raw content of official template by path
  getOfficialTemplateContent: async (templatePath) => {
    const response = await api.get(`/nuclei-templates/official/${encodeURIComponent(templatePath)}`, {
      responseType: 'text'
    });
    return response.data;
  }
};

// Wordlists API calls
export const wordlistsAPI = {
  list: async (skip = 0, limit = 100, activeOnly = true, programName = null, tags = null, search = null) => {
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: limit.toString(),
      active_only: activeOnly.toString()
    });
    
    if (programName) params.append('program_name', programName);
    if (tags) params.append('tags', tags);
    if (search) params.append('search', search);
    
    const url = `/wordlists/?${params}`;
    const response = await api.get(url);
    return response.data;
  },

  getById: async (wordlistId) => {
    const response = await api.get(`/wordlists/${wordlistId}`);
    return response.data;
  },

  upload: async (formData) => {
    const response = await api.post('/wordlists/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  update: async (wordlistId, updateData) => {
    const response = await api.put(`/wordlists/${wordlistId}`, updateData);
    return response.data;
  },

  delete: async (wordlistId) => {
    const response = await api.delete(`/wordlists/${wordlistId}`);
    return response.data;
  },

  download: async (wordlistId) => {
    const response = await api.get(`/wordlists/${wordlistId}/download`, {
      responseType: 'blob'
    });
    return response.data;
  },

  createDynamic: async (data) => {
    const response = await api.post('/wordlists/dynamic', data);
    return response.data;
  }
};

// Scheduled Jobs API calls
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

// CT Monitor API calls
export const ctMonitorAPI = {
  getStatus: async () => {
    const response = await api.get('/admin/ct-monitor/status');
    return response.data;
  },

  start: async () => {
    const response = await api.post('/admin/ct-monitor/start');
    return response.data;
  },

  stop: async () => {
    const response = await api.post('/admin/ct-monitor/stop');
    return response.data;
  }
};
