import { api } from './client';

export const commonStatsAPI = {
  /** Single round-trip for Dashboard first paint (requires API /dashboard/summary). */
  getDashboardSummary: async ({
    programName = null,
    latestLimit = 10,
    days = 30,
    startDate = null,
    endDate = null,
  } = {}) => {
    const params = new URLSearchParams();
    params.append('latest_limit', String(latestLimit));
    params.append('days', String(days));
    if (programName) params.append('program_name', programName);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const response = await api.get(`/dashboard/summary?${params.toString()}`);
    return response.data;
  },

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
  getLatestAssetsAndFindings: async (programName = null, limit = 5, daysAgo = null) => {
    const params = new URLSearchParams();
    if (programName) params.append('program_name', programName);
    params.append('limit', limit.toString());
    if (daysAgo != null && daysAgo !== '') {
      params.append('days_ago', String(daysAgo));
    }

    // Get assets and findings separately since they're now in different endpoints
    params.append('types', 'subdomains,urls');
    const assetsParams = new URLSearchParams(params);
    const findingsParams = new URLSearchParams(params);
    findingsParams.delete('types');
    findingsParams.append('types', 'nuclei,typosquat,wpscan');

    const [assetsResponse, findingsResponse] = await Promise.allSettled([
      api.get(`/assets/common/latest?${assetsParams.toString()}`),
      api.get(`/findings/common/latest?${findingsParams.toString()}`),
    ]);

    return {
      status: 'success',
      data: {
        latest_assets: assetsResponse.status === 'fulfilled' ? assetsResponse.value.data.data.latest_assets : {},
        latest_findings: findingsResponse.status === 'fulfilled' ? findingsResponse.value.data.data : {}
      }
    };
  },

  getAssetTrends: async ({ days = 30, programName = null, startDate = null, endDate = null } = {}) => {
    const params = new URLSearchParams();
    params.append('days', String(days));
    if (programName) params.append('program_name', programName);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const response = await api.get(`/assets/common/trends?${params.toString()}`);
    return response.data;
  },

  getFindingsTrends: async ({ days = 30, programName = null, startDate = null, endDate = null } = {}) => {
    const params = new URLSearchParams();
    params.append('days', String(days));
    if (programName) params.append('program_name', programName);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const response = await api.get(`/findings/common/trends?${params.toString()}`);
    return response.data;
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
