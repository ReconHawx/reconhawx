import { api } from './client';

export const aiAPI = {
  /**
   * @param {{ baseUrl?: string }} [opts] If baseUrl is set, list models from that Ollama base URL (admin).
   */
  getModels: async (opts = {}) => {
    const params = {};
    if (opts.baseUrl != null && String(opts.baseUrl).trim() !== '') {
      params.base_url = String(opts.baseUrl).trim();
    }
    const response = await api.get('/ai/models', { params });
    return response.data;
  },

  getDefaultPrompts: async () => {
    const response = await api.get('/ai/prompts/defaults');
    return response.data;
  },

  getHealth: async () => {
    const response = await api.get('/ai/health');
    return response.data;
  },
};
