import { api } from './client';

export const aiAPI = {
  getModels: async () => {
    const response = await api.get('/ai/models');
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
