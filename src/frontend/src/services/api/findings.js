import { api } from './client';

// Nuclei Findings API calls
export const nucleiAPI = {
  search: async (params) => {
    const response = await api.post('/findings/nuclei/search', params);
    return response.data;
  },
  // query: async (queryObj) => {
  //   // Try the simple GET endpoint first, fallback to POST query if needed
  //   try {
  //     const params = new URLSearchParams();
  //     if (queryObj.limit) params.append('limit', queryObj.limit);
  //     if (queryObj.skip) params.append('skip', queryObj.skip);
  //     if (queryObj.filter && Object.keys(queryObj.filter).length > 0) {
  //       // If there are filters, use the POST query endpoint
  //       const response = await api.post('/findings/nuclei/query', queryObj);
  //       return response.data;
  //     } else {
  //       // Simple listing without filters
  //       const response = await api.get(`/findings/nuclei?${params.toString()}`);
  //       return response.data;
  //     }
  //   } catch (error) {
  //     // Fallback to POST query if GET fails
  //     const response = await api.post('/findings/nuclei/query', queryObj);
  //     return response.data;
  //   }
  // },

  getById: async (findingId) => {
    const response = await api.get(`/findings/nuclei/${findingId}`);
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data;
    }
    
    throw new Error('Nuclei finding not found');
  },

  getByIdUnified: async (findingId) => {
    const response = await api.get('/findings/nuclei', { params: { id: findingId } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('Nuclei finding not found');
  },

  updateStatus: async (findingId, status, takeOwnership = false, user_id = null) => {
    const requestData = {
      status: status
    };
    
    // Add assigned_to field if taking ownership
    if (takeOwnership && user_id) {
      requestData.assigned_to = user_id;
    }
    
    const response = await api.put(`/findings/nuclei/${findingId}/status`, requestData);
    return response.data;
  },

  updateNotes: async (findingId, notes) => {
    const response = await api.put(`/findings/nuclei/${findingId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (findingId) => {
    const response = await api.delete(`/findings/nuclei/${findingId}`);
    return response.data;
  },

  deleteBatch: async (findingIds) => {
    const response = await api.delete('/findings/nuclei/batch', {
      data: findingIds
    });
    return response.data;
  },
  getDistinct: async (fieldName, filter = {}) => {
    const response = await api.post(`/findings/nuclei/distinct/${fieldName}`, { filter });
    return response.data;
  }
};

// WPScan Findings API calls
export const wpscanAPI = {
  search: async (params) => {
    const response = await api.post('/findings/wpscan/search', params);
    return response.data;
  },

  getById: async (findingId) => {
    const response = await api.get(`/findings/wpscan/${findingId}`);
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data;
    }
    
    throw new Error('WPScan finding not found');
  },

  getByIdUnified: async (findingId) => {
    const response = await api.get('/findings/wpscan', { params: { id: findingId } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('WPScan finding not found');
  },

  updateStatus: async (findingId, status, takeOwnership = false, user_id = null) => {
    const requestData = {
      status: status
    };
    
    // Add assigned_to field if taking ownership
    if (takeOwnership && user_id) {
      requestData.assigned_to = user_id;
    }
    
    const response = await api.put(`/findings/wpscan/${findingId}/status`, requestData);
    return response.data;
  },

  updateNotes: async (findingId, notes) => {
    const response = await api.put(`/findings/wpscan/${findingId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (findingId) => {
    const response = await api.delete(`/findings/wpscan/${findingId}`);
    return response.data;
  },

  deleteBatch: async (findingIds) => {
    const response = await api.delete('/findings/wpscan/batch', {
      data: findingIds
    });
    return response.data;
  },

  getDistinct: async (fieldName, filter = {}) => {
    const response = await api.post(`/findings/wpscan/distinct/${fieldName}`, filter);
    return response.data;
  },

  import: async (findings, options = {}) => {
    const response = await api.post('/findings/wpscan/import', {
      findings,
      ...options
    });
    return response.data;
  }
};

// Broken Links API calls
export const brokenLinksAPI = {
  search: async (params) => {
    const response = await api.post('/findings/broken-links/search', params);
    return response.data;
  },

  getById: async (findingId) => {
    const response = await api.get(`/findings/broken-links/${findingId}`);
    return response.data;
  },

  create: async (finding) => {
    const response = await api.post('/findings/broken-links', finding);
    return response.data;
  },

  update: async (findingId, updateData) => {
    const response = await api.put(`/findings/broken-links/${findingId}`, updateData);
    return response.data;
  },

  delete: async (findingId) => {
    const response = await api.delete(`/findings/broken-links/${findingId}`);
    return response.data;
  },

  deleteBatch: async (findingIds) => {
    const response = await api.delete('/findings/broken-links/batch', { data: findingIds });
    return response.data;
  },

  getStats: async (programName = null) => {
    const params = programName ? { program_name: programName } : {};
    const response = await api.get('/findings/broken-links/stats', { params });
    return response.data;
  }
};

// Social Media Credentials API calls
export const socialMediaCredentialsAPI = {
  list: async (platform = null) => {
    const params = platform ? { platform } : {};
    const response = await api.get('/social-media-credentials', { params });
    return response.data;
  },

  getById: async (credentialId) => {
    const response = await api.get(`/social-media-credentials/id/${credentialId}`);
    return response.data;
  },

  getByPlatform: async (platform) => {
    const response = await api.get(`/social-media-credentials/${platform}`);
    return response.data;
  },

  create: async (credential) => {
    const response = await api.post('/social-media-credentials', credential);
    return response.data;
  },

  update: async (credentialId, updateData) => {
    const response = await api.put(`/social-media-credentials/${credentialId}`, updateData);
    return response.data;
  },

  delete: async (credentialId) => {
    const response = await api.delete(`/social-media-credentials/${credentialId}`);
    return response.data;
  }
};
export const typosquatAPI = {
  search: async (params) => {
    const response = await api.post('/findings/typosquat/search', params);
    return response.data;
  },

  getById: async (findingId) => {
    const response = await api.get(`/findings/typosquat/${findingId}`);
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data.data;
    }
    
    throw new Error('Typosquat finding not found');
  },

  getByIdUnified: async (findingId) => {
    const response = await api.get('/findings/typosquat', { params: { id: findingId } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('Typosquat finding not found');
  },

  updateStatus: async (findingId, status, takeOwnership = false, user_id = null, comment = null, actionTaken = null, assigned_to = undefined) => {
    const requestData = {
      status: status
    };

    // Handle assignment - priority: explicit assigned_to > takeOwnership > no change
    if (assigned_to !== undefined) {
      // Explicit assignment (can be user ID or null for unassign)
      requestData.assigned_to = assigned_to;
    } else if (takeOwnership && user_id) {
      // Legacy takeOwnership behavior
      requestData.assigned_to = user_id;
    }

    // Add comment if provided
    if (comment && comment.trim()) {
      requestData.comment = comment.trim();
    }

    // Add action_taken if provided
    if (actionTaken && actionTaken.trim()) {
      requestData.action_taken = actionTaken.trim();
    }

    const response = await api.put(`/findings/typosquat/${findingId}/status`, requestData);
    return response.data;
  },

  updateStatusBatch: async (findingIds, status, takeOwnership = false, user_id = null, comment = null, actionTaken = null, assigned_to = undefined, forceAssignmentOverwrite = false) => {
    const requestData = {
      finding_ids: findingIds
    };

    // Only include status if it's not 'unchanged'
    if (status !== 'unchanged') {
      requestData.status = status;
    }

    // Handle assignment - priority: explicit assigned_to > takeOwnership > no change
    if (assigned_to !== undefined) {
      // Explicit assignment (can be user ID or null for unassign)
      requestData.assigned_to = assigned_to;
      requestData.force_assignment_overwrite = forceAssignmentOverwrite;
    } else if (takeOwnership && user_id) {
      // Legacy takeOwnership behavior
      requestData.assigned_to = user_id;
    }

    // Add comment if provided
    if (comment && comment.trim()) {
      requestData.comment = comment.trim();
    }

    // Add action_taken if provided
    if (actionTaken && actionTaken.trim()) {
      requestData.action_taken = actionTaken.trim();
    }

    const response = await api.put('/findings/typosquat/batch/status', requestData);
    return response.data;
  },

  updateNotes: async (findingId, notes) => {
    const response = await api.put(`/findings/typosquat/${findingId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (findingId, deleteRelated = false) => {
    const params = deleteRelated ? { delete_related: true } : {};
    const response = await api.delete(`/findings/typosquat/${findingId}`, { params });
    return response.data;
  },

  deleteBatch: async (findingIds) => {

    const response = await api.delete('/findings/typosquat/batch', {
      data: { finding_ids: findingIds }
    });
    return response.data;
  },

  calculateRiskScores: async (programName = null, findingIds = null) => {
    const requestBody = {};
    if (programName) {
      requestBody.program_name = programName;
    }
    if (findingIds && findingIds.length > 0) {
      requestBody.finding_ids = findingIds;
    }
    const response = await api.post('/findings/typosquat/calculate-risk-scores', requestBody);
    return response.data;
  },

  calculateSingleRiskScore: async (findingId) => {
    const response = await api.post(`/findings/typosquat/${findingId}/calculate-risk-score`, {});
    return response.data;
  },

  // Recalculate protected domain similarities for a program
  recalculateSimilarities: async (programName) => {
    const response = await api.post(`/findings/typosquat/recalculate-similarities/${encodeURIComponent(programName)}`);
    return response.data;
  },

  recalculateSimilaritiesForFinding: async (findingId) => {
    const response = await api.post(
      `/findings/typosquat/${encodeURIComponent(findingId)}/recalculate-similarities`
    );
    return response.data;
  },

  // Fetch PhishLabs information for a domain
  fetchPhishlabsInfo: async (typoDomain, programName) => {
    const params = new URLSearchParams({
      typo_domain: typoDomain,
      program_name: programName
    });
    const response = await api.post(`/findings/typosquat/phishlabs?${params.toString()}`, {});
    return response.data;
  },

  // Create background job for batch PhishLabs processing
  createBatchPhishlabsJob: async (findingIds) => {
    const response = await api.post('/findings/typosquat/phishlabs/batch', {
      finding_ids: findingIds
    });
    return response.data;
  },

  // Create background job for batch PhishLabs operations
  createBatchPhishlabsIncidentsJob: async (findingIds, catcode = null, comment = null, reportToGsb = false) => {
    const requestData = {
      finding_ids: findingIds,
      report_to_gsb: reportToGsb
    };
    if (catcode) {
      requestData.catcode = catcode;
    }
    if (comment) {
      requestData.comment = comment;
    }
    const response = await api.post('/findings/typosquat/phishlabs-incidents/batch', requestData);
    return response.data;
  },

  // Create PhishLabs incident for a single domain
  createPhishlabsIncident: async (typoDomain, programName, catcode, comment = null, reportToGsb = false) => {
    const params = new URLSearchParams({
      typo_domain: typoDomain,
      program_name: programName,
      catcode: catcode,
      report_to_gsb: reportToGsb
    });
    const requestBody = {};
    if (comment) {
      requestBody.comment = comment;
    }
    const response = await api.post(`/findings/typosquat/phishlabs-incidents?${params.toString()}`, requestBody);
    return response.data;
  },

  // Create PhishLabs infraction for a single domain
  createPhishlabsInfraction: async (typoDomain, programName, catcode) => {
    const params = new URLSearchParams({
      typo_domain: typoDomain,
      program_name: programName,
      catcode: catcode
    });
    const response = await api.post(`/findings/typosquat/phishlabs/create-infraction?${params.toString()}`, {});
    return response.data;
  },

  // Create background job for batch typosquat domain analysis
  createBatchTyposquatJob: async (domains, programName = null, originalDomain = null) => {
    const requestData = {
      "workflow_name": "Batch_Typosquat_Analysis",
      "program_name": programName || "default",
      "description": "Batch processing of potential Typosquat Domains",
      "steps": [
        {
          "name": "step_1",
          "tasks": [
            {
              "name": "typosquat_detection",
              "force": true,
              "params": {
                "include_subdomains": false,
                "analyze_input_as_variations": true,
              },
              "task_type": "typosquat_detection",
              "input_mapping": {
                "domains": "inputs.input_1"
              }
            }
          ]
        }
      ],
      "variables": {},
      "inputs": {
        "input_1": {
          "type": "direct",
          "values": domains,
          "value_type": "domains"
        }
      },
      "workflow_definition_id": ""
    };
    
    const response = await api.post('/workflows/run', requestData);
    return response.data;
  },

  // Get distinct values for a field
  getDistinctValues: async (fieldName, program = undefined) => {
    const body = {};
    if (program) body.program = program;
    const response = await api.post(`/findings/typosquat/distinct/${fieldName}`, body);
    return response.data;
  },

  getDistinctValuesUrl: async (fieldName, program = undefined) => {
    const body = {};
    if (program) body.program = program;
    const response = await api.post(`/findings/typosquat-url/distinct/${fieldName}`, body);
    return response.data;
  },

  // Typosquat URLs API calls - using the same pattern as other asset APIs
  searchTyposquatUrls: async (params = {}) => {
    // params: { search, exact_match, protocol, status_code, technology_text, technology, program, sort_by, sort_dir, page, page_size }
    const response = await api.post('/findings/typosquat-url/search', params);
    return response.data;
  },

  getUrlById: async (urlId) => {
    const response = await api.get(`/findings/typosquat-url/${urlId}`);
    return response.data;
  },

  deleteUrl: async (urlId) => {
    const response = await api.delete(`/findings/typosquat-url/${urlId}`);
    return response.data;
  },

  deleteBatchUrls: async (urlIds, options = {}) => {
    const response = await api.delete('/findings/typosquat-url/batch', {
      data: {
        asset_ids: urlIds,
        ...options
      }
    });
    return response.data;
  },

  updateUrlNotes: async (urlId, notes) => {
    const response = await api.put(`/findings/typosquat-url/${urlId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  // Get certificate by ID
  getCertificateById: async (certificateId) => {
    const response = await api.get(`/findings/typosquat-certificate/${certificateId}`);
    return response.data;
  },

  // Get URLs by domain
  getUrlsByDomain: async (domain) => {
    const response = await api.post('/findings/typosquat-url/search', {
      search: domain,
      page: 1,
      page_size: 1000
    });
    return response.data.items || [];
  },

  // Get related typosquat domains (domains sharing the same base domain)
  getRelatedDomains: async (findingId) => {
    const response = await api.get(`/findings/typosquat/${findingId}/related-domains`);
    return response.data;
  },

  // Get URLs for all related typosquat domains
  getRelatedUrls: async (findingId) => {
    const response = await api.get(`/findings/typosquat/${findingId}/related-urls`);
    return response.data;
  },

  // Get action logs for a specific finding
  getActionLogs: async (findingId, limit = 50, offset = 0) => {
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());
    const response = await api.get(`/findings/typosquat/${findingId}/action-logs?${params.toString()}`);
    return response.data;
  },

  // Get dashboard KPIs (days rolling window, singleDate, or dateFrom+dateTo custom range)
  getDashboardKpis: async ({
    days = 30,
    singleDate = null,
    dateFrom = null,
    dateTo = null,
    program = null,
  } = {}) => {
    const params = new URLSearchParams();
    if (dateFrom && dateTo) {
      params.append('date_from', dateFrom);
      params.append('date_to', dateTo);
    } else if (singleDate) {
      params.append('single_date', singleDate);
    } else {
      params.append('days', days.toString());
    }
    if (program) {
      params.append('program', program);
    }
    const response = await api.get(`/findings/typosquat/dashboard/kpis?${params.toString()}`);
    return response.data;
  },

  // Get all action logs for typosquat findings
  getAllActionLogs: async (params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.program) queryParams.append('program', params.program);
    if (params.action_type) queryParams.append('action_type', params.action_type);
    if (params.entity_id) queryParams.append('entity_id', params.entity_id);
    if (params.search) queryParams.append('search', params.search);
    if (params.limit) queryParams.append('limit', params.limit.toString());

    const response = await api.get(`/findings/typosquat/action-logs?${queryParams.toString()}`);
    return response.data;
  },

  aiAnalyze: async (findingId, { force = false, model = null } = {}) => {
    const params = new URLSearchParams();
    if (force) params.append('force', 'true');
    if (model) params.append('model', model);
    const response = await api.post(`/findings/typosquat/ai-analyze/${findingId}?${params.toString()}`);
    return response.data;
  },

  aiAnalyzeBatch: async (programName, { batchSize, model, reanalyzeAfterDays, applyAutoActions } = {}) => {
    const body = {
      program_name: programName,
      batch_size: batchSize || 50,
      model: model || null,
      reanalyze_after_days: reanalyzeAfterDays || null,
      apply_auto_actions: applyAutoActions || false,
    };
    const response = await api.post('/findings/typosquat/ai-analyze-batch', body);
    return response.data;
  },

  getAiAnalysis: async (findingId) => {
    const response = await api.get(`/findings/typosquat/ai-analysis/${findingId}`);
    return response.data;
  },

};
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
