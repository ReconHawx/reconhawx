import { api } from './client';

export const commonStatsAPI = {
  // Get aggregated asset stats across all accessible programs
  getAggregatedAssetStats: async () => {
    const response = await api.get('/assets/common/stats');
    return response.data;
  },

  // Get asset stats for a specific program
  getProgramAssetStats: async (programName) => {
    const response = await api.get(`/assets/common/stats/${encodeURIComponent(programName)}`);
    return response.data;
  },

  // Get aggregated findings stats across all accessible programs
  getAggregatedFindingsStats: async () => {
    const response = await api.get('/findings/common/stats');
    return response.data;
  },

  // Get findings stats for a specific program
  getProgramFindingsStats: async (programName) => {
    const response = await api.get(`/findings/common/stats/${encodeURIComponent(programName)}`);
    return response.data;
  },

  // Get latest assets and findings for dashboard
  getLatestAssetsAndFindings: async (programName = null, limit = 5) => {
    const params = new URLSearchParams();
    if (programName) params.append('program_name', programName);
    params.append('limit', limit.toString());
    
    // Get assets and findings separately since they're now in different endpoints
    const [assetsResponse, findingsResponse] = await Promise.allSettled([
      api.get(`/assets/common/latest?${params.toString()}`),
      api.get(`/findings/common/latest?${params.toString()}`)
    ]);
    
    return {
      status: 'success',
      data: {
        latest_assets: assetsResponse.status === 'fulfilled' ? assetsResponse.value.data.data.latest_assets : {},
        latest_findings: findingsResponse.status === 'fulfilled' ? findingsResponse.value.data.data : {}
      }
    };
  },

  // Get only latest assets for dashboard
  getLatestAssets: async (programName = null, limit = 5) => {
    const params = new URLSearchParams();
    if (programName) params.append('program_name', programName);
    params.append('limit', limit.toString());
    
    const response = await api.get(`/assets/common/latest?${params.toString()}`);
    return response.data;
  },

  // Get only latest findings for dashboard
  getLatestFindings: async (programName = null, limit = 5) => {
    const params = new URLSearchParams();
    if (programName) params.append('program_name', programName);
    params.append('limit', limit.toString());
    
    const response = await api.get(`/findings/common/latest?${params.toString()}`);
    return response.data;
  }
};
