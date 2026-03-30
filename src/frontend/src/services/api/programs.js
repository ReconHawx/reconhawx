import { api } from './client';

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

  getEventHandlerConfig: async (programName) => {
    const response = await api.get(`/programs/${encodeURIComponent(programName)}/event-handler-configs`);
    return response.data;
  },

  getEventHandlerGlobalTemplate: async (programName) => {
    const response = await api.get(`/programs/${encodeURIComponent(programName)}/event-handler-configs/global-template`);
    return response.data;
  },

  updateEventHandlerConfig: async (programName, handlers, eventHandlerAddonMode) => {
    const body = { handlers };
    if (eventHandlerAddonMode !== undefined && eventHandlerAddonMode !== null) {
      body.event_handler_addon_mode = Boolean(eventHandlerAddonMode);
    }
    const response = await api.put(
      `/programs/${encodeURIComponent(programName)}/event-handler-configs`,
      body
    );
    return response.data;
  },

  deleteEventHandlerConfig: async (programName) => {
    const response = await api.delete(`/programs/${encodeURIComponent(programName)}/event-handler-configs`);
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
