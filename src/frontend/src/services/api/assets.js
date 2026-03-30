import { api } from './client';

export const assetAPI = {
  delete: async (assetType, assetId) => {
    const response = await api.delete(`/assets/${assetType}/${assetId}`);
    return response.data;
  },

  deleteBatch: async (assetType, assetIds, options = {}) => {
    const response = await api.delete(`/assets/${assetType}/batch`, {
      data: {
        asset_ids: assetIds,
        ...options
      }
    });
    return response.data;
  }
};

// Domain API calls
export const domainAPI = {
  // New typed subdomain search API (preferred)
  searchSubdomains: async (params = {}) => {
    // params: { search, apex_domain, wildcard, has_ips, ip, has_cname, cname_contains, sort_by, sort_dir, page, page_size }
    const response = await api.post('/assets/subdomain/search', params);
    return response.data;
  },

  getById: async (id) => {
    const response = await api.get('/assets/subdomain', { params: { id } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('Domain not found');
  },

  getByName: async (domainName) => {
    // Use the new domain by name endpoint for better performance
    const response = await api.get(`/assets/subdomain/name/${encodeURIComponent(domainName)}`);
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data.data;
    }
    
    throw new Error('Domain not found');
  },

  updateNotes: async (domainId, notes) => {
    const response = await api.put(`/assets/subdomain/${domainId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (domainId) => {
    const response = await api.delete(`/assets/subdomain/${domainId}`);
    return response.data;
  },

  deleteBatch: async (domainIds, options = {}) => {
    const response = await api.delete('/assets/subdomain/batch', {
      data: {
        asset_ids: domainIds,
        ...options
      }
    });
    return response.data;
  },

  import: async (domains, options = {}) => {
    const response = await api.post('/assets/subdomain/import', {
      domains,
      ...options
    });
    return response.data;
  },

  // Get distinct values for a field
  getDistinctValues: async (fieldName, program = undefined) => {
    const body = {};
    if (program) body.program = program;
    const response = await api.post(`/assets/subdomain/distinct/${fieldName}`, body);
    return response.data;
  },

  // Get subdomains that resolve to a specific IP address
  getSubdomainsByIP: async (ipAddress, page = 1, pageSize = 25) => {
    const response = await api.post('/assets/subdomain/search', {
      ip: ipAddress,
      page: page,
      page_size: pageSize,
      sort_by: 'name',
      sort_dir: 'asc'
    });
    return response.data;
  }
};

// Apex Domain API calls
export const apexDomainAPI = {
  // Search apex domains with typed parameters
  search: async (params = {}) => {
    // params: { search, program, sort_by, sort_dir, page, page_size }
    const response = await api.post('/assets/apex-domain/search', params);
    return response.data;
  },

  // Get apex domain by ID
  getById: async (id) => {
    const response = await api.get('/assets/apex-domain', { params: { id } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('Apex domain not found');
  },

  // Import apex domains
  import: async (apexDomains, options = {}) => {
    const response = await api.post('/assets/apex-domain/import', {
      apex_domains: apexDomains,
      merge: options.merge !== false,
      update_existing: options.update_existing !== false,
      validate_domains: options.validate_domains !== false
    });
    return response.data;
  },

  // Delete individual apex domain
  delete: async (apexDomainId) => {
    const response = await api.delete(`/assets/apex-domain/${apexDomainId}`);
    return response.data;
  },

  // Delete multiple apex domains in batch
  deleteBatch: async (apexDomainIds, options = {}) => {
    const response = await api.delete('/assets/apex-domain/batch', {
      data: {
        asset_ids: apexDomainIds,
        delete_subdomains: options.deleteSubdomains || false
      }
    });
    return response.data;
  },

  // Update notes for an apex domain
  updateNotes: async (apexDomainId, notes) => {
    const response = await api.put(`/assets/apex-domain/${apexDomainId}/notes`, {
      notes: notes
    });
    return response.data;
  }
};

// IP API calls
export const ipAPI = {
  // New typed IPs search API (preferred)
  searchIPs: async (params = {}) => {
    // params: { search, program, has_ptr, ptr_contains, service_provider, sort_by, sort_dir, page, page_size }
    const response = await api.post('/assets/ip/search', params);
    return response.data;
  },

  getByAddress: async (ipAddress) => {
    // Use the new IP by address endpoint for better performance
    const response = await api.get(`/assets/ip/address/${encodeURIComponent(ipAddress)}`);
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data.data;
    }
    
    throw new Error('IP not found');
  },

  getById: async (id) => {
    const response = await api.get('/assets/ip', { params: { id } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('IP not found');
  },

  updateNotes: async (ipId, notes) => {
    const response = await api.put(`/assets/ip/${ipId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (ipId) => {
    const response = await api.delete(`/assets/ip/${ipId}`);
    return response.data;
  },

  deleteBatch: async (ipIds, options = {}) => {
    const response = await api.delete('/assets/ip/batch', {
      data: {
        asset_ids: ipIds,
        ...options
      }
    });
    return response.data;
  },

  import: async (ips, options = {}) => {
    const response = await api.post('/assets/ip/import', {
      ips,
      ...options
    });
    return response.data;
  }
};

// URL API calls
export const urlAPI = {
  // New typed URL search API (preferred)
  searchURLs: async (params = {}) => {
    // params: { search, protocol, status_code, only_root, technology_text, technology, program, sort_by, sort_dir, page, page_size }
    const response = await api.post('/assets/url/search', params);
    return response.data;
  },

  getByUrl: async (url) => {
    // Use the new URL by URL string endpoint for better performance
    const response = await api.post('/assets/url/by-url', {
      url: url
    });
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data.data;
    }
    
    throw new Error('URL not found');
  },

  getById: async (id) => {
    const response = await api.get('/assets/url', { params: { id } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('URL not found');
  },

  updateNotes: async (urlId, notes) => {
    const response = await api.put(`/assets/url/${urlId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (urlId) => {
    const response = await api.delete(`/assets/url/${urlId}`);
    return response.data;
  },

  deleteBatch: async (urlIds, options = {}) => {
    const response = await api.delete('/assets/url/batch', {
      data: {
        asset_ids: urlIds,
        ...options
      }
    });
    return response.data;
  },

  // Get related URLs for sitemap (same scheme/host/port but different paths)
  getRelatedUrls: async (scheme, host, port, currentUrl) => {

    
    const response = await api.post('/assets/url/search', {
      port: port,
      hostname: host,
      sort_by: 'url',
      scheme: scheme,
      sort_dir: 'asc',
      page: 1,
      page_size: 25
    });
    
    if (response.data.status === 'success' && response.data.items) {
      // Filter out the current URL and return others
      return response.data.items.filter(url => url.url !== currentUrl);
    }
    
    return [];
  },

  // Get distinct values for a field
  getDistinctValues: async (fieldName, program = undefined) => {
    const body = {};
    if (program) body.program = program;
    const response = await api.post(`/assets/url/distinct/${fieldName}`, body);
    return response.data;
  },

  import: async (urls, options = {}) => {
    const response = await api.post('/assets/url/import', {
      urls,
      ...options
    });
    return response.data;
  },

  // Get technologies summary with counts and URLs (paginated)
  getTechnologiesSummary: async (program = null, page = 1, page_size = 25, search = undefined, sort_by = undefined, sort_order = undefined) => {
    const params = {
      page,
      page_size
    };
    if (program) {
      params.program = program;
    }
    if (search) {
      params.search = search;
    }
    if (sort_by) {
      params.sort_by = sort_by;
    }
    if (sort_order) {
      params.sort_order = sort_order;
    }
    const response = await api.get('/assets/url/technologies/summary', { params });
    return response.data;
  }
};

// Service API calls
export const serviceAPI = {
  // New typed services search API (preferred)
  searchServices: async (params = {}) => {
    // params: { search_ip, port, protocol, service_name, service_text, program, sort_by, sort_dir, page, page_size }
    const response = await api.post('/assets/service/search', params);
    return response.data;
  },

  getByIpPort: async (ip, port) => {
    // Use the existing service by IP:port endpoint
    const response = await api.get(`/assets/service/${encodeURIComponent(ip)}/${encodeURIComponent(port)}`);
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data.data;
    }
    
    throw new Error('Service not found');
  },

  getById: async (id) => {
    const response = await api.get('/assets/service', { params: { id } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('Service not found');
  },

  updateNotes: async (serviceId, notes) => {
    const response = await api.put(`/assets/service/${serviceId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (serviceId) => {
    const response = await api.delete(`/assets/service/${serviceId}`);
    return response.data;
  },

  deleteBatch: async (serviceIds, options = {}) => {
    const response = await api.delete('/assets/service/batch', {
      data: {
        asset_ids: serviceIds,
        ...options
      }
    });
    return response.data;
  },

  import: async (services, options = {}) => {
    const response = await api.post('/assets/service/import', {
      services,
      ...options
    });
    return response.data;
  },

  // Get distinct values for a field (e.g. port, service_name)
  getDistinctValues: async (fieldName, program = undefined) => {
    const body = {};
    if (program) body.program = program;
    const response = await api.post(`/assets/service/distinct/${fieldName}`, body);
    return response.data;
  }
};


// Screenshot API calls
export const screenshotAPI = {
  // New typed screenshots search API (preferred)
  searchScreenshots: async (params = {}) => {
    // params: { search_url, url_equals, program, sort_by, sort_dir, page, page_size }
    const response = await api.post('/assets/screenshot/search', params);
    return response.data;
  },

  getById: async (fileId) => {
    const response = await api.get(`/assets/screenshot/${fileId}`);
    return response.data;
  },

  delete: async (screenshotId) => {
    const response = await api.delete(`/assets/screenshot/${screenshotId}`);
    return response.data;
  },

  deleteBatch: async (screenshotIds, options = {}) => {
    const response = await api.delete('/assets/screenshot/batch', {
      data: screenshotIds  // Send screenshot_ids as direct list, not wrapped in asset_ids object
    });
    return response.data;
  }
};

// Typosquat Screenshot API calls - using the same pattern as other asset APIs
export const typosquatScreenshotAPI = {
  // Search typosquat screenshots with typed parameters
  searchTyposquatScreenshots: async (params = {}) => {
    // params: { search_url, url_equals, typosquat_type, program, sort_by, sort_dir, page, page_size }
    const response = await api.post('/findings/typosquat-screenshot/search', params);
    return response.data;
  },

  getById: async (fileId) => {
    const response = await api.get(`/findings/typosquat-screenshot/${fileId}`);
    return response.data;
  },

  delete: async (screenshotId) => {
    const response = await api.delete(`/findings/typosquat-screenshot/${screenshotId}`);
    return response.data;
  },

  deleteBatch: async (screenshotIds, options = {}) => {
    const response = await api.delete('/findings/typosquat-screenshot/batch', {
      data: {
        asset_ids: screenshotIds,
        ...options
      }
    });
    return response.data;
  }
};

// Technology API calls
export const technologyAPI = {

  getById: async (technologyName) => {
    const response = await api.get(`/assets/technologies/${encodeURIComponent(technologyName)}`);
    return response.data;
  },

  delete: async (technologyId) => {
    const response = await api.delete(`/assets/technology/${technologyId}`);
    return response.data;
  },

  deleteBatch: async (technologyIds, options = {}) => {
    const response = await api.delete('/assets/technology/batch', {
      data: {
        asset_ids: technologyIds,
        ...options
      }
    });
    return response.data;
  }
};

// Certificate API calls
export const certificateAPI = {
  // New typed certificates search API (preferred)
  searchCertificates: async (params = {}) => {
    // params: { search, program, status, expiring_within_days, sort_by, sort_dir, page, page_size }
    const response = await api.post('/assets/certificate/search', params);
    return response.data;
  },

  // Get distinct values for a certificate field
  getDistinctValues: async (fieldName, program = undefined) => {
    const body = {};
    if (program) body.program = program;
    const response = await api.post(`/assets/certificate/distinct/${fieldName}`, body);
    return response.data;
  },

  getBySubjectDN: async (subjectDN) => {
    // Use the new certificate by subject DN endpoint
    const response = await api.post('/assets/certificate/by-subject-dn', {
      subject_dn: subjectDN
    });
    
    if (response.data.status === 'success' && response.data.data) {
      return response.data.data;
    }
    
    throw new Error('Certificate not found');
  },

  getById: async (id) => {
    const response = await api.get('/assets/certificate', { params: { id } });
    if (response.data && response.data.data) return response.data.data;
    throw new Error('Certificate not found');
  },

  updateNotes: async (certificateId, notes) => {
    const response = await api.put(`/assets/certificate/${certificateId}/notes`, {
      notes: notes
    });
    return response.data;
  },

  delete: async (certificateId) => {
    const response = await api.delete(`/assets/certificate/${certificateId}`);
    return response.data;
  },

  deleteBatch: async (certificateIds, options = {}) => {
    const response = await api.delete('/assets/certificate/batch', {
      data: {
        asset_ids: certificateIds,
        ...options
      }
    });
    return response.data;
  },

  import: async (certificates, options = {}) => {
    const response = await api.post('/assets/certificate/import', {
      certificates,
      ...options
    });
    return response.data;
  }
};
