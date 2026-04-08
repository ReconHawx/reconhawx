import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, Button, Spinner, Modal, OverlayTrigger, Popover } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { domainAPI, programAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function Subdomains() {
  usePageTitle(formatPageTitle('Subdomains'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [searchFilter, setSearchFilter] = useState('');
  const [exactMatchFilter, setExactMatchFilter] = useState('');
  const [wildcardFilter, setWildcardFilter] = useState('');
  const [hasIpsFilter, setHasIpsFilter] = useState('');
  const [hasCnameFilter, setHasCnameFilter] = useState('');
  const [cnameFilter, setCnameFilter] = useState('');
  const [apexDomainFilter, setApexDomainFilter] = useState('');
  const [availableApexDomains, setAvailableApexDomains] = useState([]);
  const [loadingApexDomains, setLoadingApexDomains] = useState(false);
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    name: true,
    program_name: true,
    is_wildcard: true,
    ip: true,
    cname_record: true,
    updated_at: true,
    created_at: true
  });
  const [exporting, setExporting] = useState(false);
  const [customFilename, setCustomFilename] = useState('');
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importFormat, setImportFormat] = useState('auto');
  const [importing, setImporting] = useState(false);
  const [importPreview, setImportPreview] = useState([]);
  const [fieldMapping, setFieldMapping] = useState({});
  const [showFieldMapping, setShowFieldMapping] = useState(false);
  const [availableFields, setAvailableFields] = useState([]);
  const [previewData, setPreviewData] = useState([]);
  const [importOptions, setImportOptions] = useState({
    updateExisting: true,  // Default to updating existing domains
    mergeData: true,       // Default to merging data
    validateDomains: true  // Default to validating domain names
  });
  const [programs, setPrograms] = useState([]);
  const [selectedImportProgram, setSelectedImportProgram] = useState('');
  const [importProgress, setImportProgress] = useState({
    current: 0,
    total: 0,
    currentBatch: 0,
    totalBatches: 0
  });

  // --- URL <-> State sync helpers ---
  const isSyncingFromUrl = useRef(false);
  const serializeParams = (params) => {
    const entries = [];
    for (const [key, value] of params.entries()) {
      if (value !== undefined && value !== null && String(value).length > 0) {
        entries.push([key, String(value)]);
      }
    }
    entries.sort((a, b) => a[0].localeCompare(b[0]));
    return entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
  };

  const buildUrlParamsFromState = useCallback(() => {
    const params = new URLSearchParams();
    if (searchFilter) params.set('search', searchFilter);
    if (exactMatchFilter) params.set('exact_match', exactMatchFilter);
    if (selectedProgram) params.set('program', selectedProgram);
    if (wildcardFilter) params.set('wildcard', wildcardFilter);
    if (hasIpsFilter) params.set('has_ips', hasIpsFilter);
    if (hasCnameFilter) params.set('has_cname', hasCnameFilter);
    if (cnameFilter) params.set('cname_contains', cnameFilter);
    if (apexDomainFilter) params.set('apex_domain', apexDomainFilter);
    const apiSortBy = sortField === 'ip' ? 'ip_count' : sortField;
    if (apiSortBy) params.set('sort_by', apiSortBy);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [searchFilter, exactMatchFilter, selectedProgram, wildcardFilter, hasIpsFilter, hasCnameFilter, cnameFilter, apexDomainFilter, sortField, sortDirection, currentPage, pageSize]);

  // Parse query params into state (runs on URL change and initial load)
  useEffect(() => {
    isSyncingFromUrl.current = true;
    const urlParams = new URLSearchParams(location.search);

    const urlSearch = urlParams.get('search') || '';
    if (urlSearch !== searchFilter) setSearchFilter(urlSearch);

    const urlExactMatch = urlParams.get('exact_match') || '';
    if (urlExactMatch !== exactMatchFilter) setExactMatchFilter(urlExactMatch);

    const urlProgram = urlParams.get('program') || '';
    if (urlProgram && urlProgram !== selectedProgram) {
      setSelectedProgram(urlProgram);
    }

    const urlWildcard = urlParams.get('wildcard');
    const normalizedWildcard = urlWildcard === null ? '' : (urlWildcard === 'true' ? 'true' : (urlWildcard === 'false' ? 'false' : urlWildcard));
    if (normalizedWildcard !== wildcardFilter) setWildcardFilter(normalizedWildcard);

    const urlHasIps = urlParams.get('has_ips');
    const normalizedHasIps = urlHasIps === null ? '' : (urlHasIps === 'true' ? 'true' : (urlHasIps === 'false' ? 'false' : urlHasIps));
    if (normalizedHasIps !== hasIpsFilter) setHasIpsFilter(normalizedHasIps);

    const urlHasCname = urlParams.get('has_cname');
    const normalizedHasCname = urlHasCname === null ? '' : (urlHasCname === 'true' ? 'true' : (urlHasCname === 'false' ? 'false' : urlHasCname));
    if (normalizedHasCname !== hasCnameFilter) setHasCnameFilter(normalizedHasCname);

    const urlCnameContains = urlParams.get('cname_contains') || '';
    if (urlCnameContains !== cnameFilter) setCnameFilter(urlCnameContains);

    const urlApex = urlParams.get('apex_domain') || '';
    if (urlApex !== apexDomainFilter) setApexDomainFilter(urlApex);

    const urlSortBy = urlParams.get('sort_by');
    if (urlSortBy) {
      const mappedField = urlSortBy === 'ip_count' ? 'ip' : urlSortBy;
      if (mappedField !== sortField) setSortField(mappedField);
    }

    const urlSortDir = urlParams.get('sort_dir');
    if (urlSortDir && (urlSortDir === 'asc' || urlSortDir === 'desc') && urlSortDir !== sortDirection) {
      setSortDirection(urlSortDir);
    }

    const urlPage = parseInt(urlParams.get('page') || '1', 10);
    if (!Number.isNaN(urlPage) && urlPage > 0 && urlPage !== currentPage) setCurrentPage(urlPage);

    const urlPageSize = parseInt(urlParams.get('page_size') || '25', 10);
    if (!Number.isNaN(urlPageSize) && urlPageSize > 0 && urlPageSize !== pageSize) setPageSize(urlPageSize);

    // allow state to settle before enabling write-back
    setTimeout(() => { isSyncingFromUrl.current = false; }, 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  // Reflect state changes in the URL (skip while applying URL params)
  useEffect(() => {
    if (isSyncingFromUrl.current) return;
    const desiredParams = buildUrlParamsFromState();
    const desired = serializeParams(desiredParams);
    const current = serializeParams(new URLSearchParams(location.search));
    if (desired !== current) {
      navigate({ pathname: location.pathname, search: desiredParams.toString() }, { replace: true });
    }
  }, [navigate, location.pathname, buildUrlParamsFromState, location.search]);

  const fetchDomains = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      // Build typed params for new endpoint
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (exactMatchFilter) params.exact_match = exactMatchFilter;
      if (selectedProgram) params.program = selectedProgram; // backend infers via auth; still allowed to pass
      if (wildcardFilter) params.wildcard = wildcardFilter === 'true';
      if (hasIpsFilter) params.has_ips = hasIpsFilter === 'true';
      if (hasCnameFilter) params.has_cname = hasCnameFilter === 'true';
      if (cnameFilter) params.cname_contains = cnameFilter;
      if (apexDomainFilter) params.apex_domain = apexDomainFilter;
      params.sort_by = sortField === 'ip' ? 'ip_count' : sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = page;
      params.page_size = pageSize;

      const response = await domainAPI.searchSubdomains(params);
      setDomains(response.items || []);
      setTotalPages(response.pagination?.total_pages || 1);
      setTotalItems(response.pagination?.total_items || 0);
      setError(null);
    } catch (err) {
      setError('Failed to fetch domains: ' + err.message);
      setDomains([]);
    } finally {
      setLoading(false);
    }
  }, [pageSize, searchFilter, exactMatchFilter, selectedProgram, wildcardFilter, hasIpsFilter, hasCnameFilter, cnameFilter, apexDomainFilter, sortField, sortDirection]);

  const fetchApexDomains = useCallback(async () => {
    try {
      setLoadingApexDomains(true);
      
      // Use the domain API's getDistinctValues to get distinct apex_domain values from subdomains
      // This ensures we only show apex domains that actually exist in the subdomains data
      const apexDomainNames = await domainAPI.getDistinctValues('apex_domain', selectedProgram || undefined);
      
      if (apexDomainNames && Array.isArray(apexDomainNames)) {
        // Filter out empty/null values and sort alphabetically
        const filteredNames = apexDomainNames
          .filter(name => name && name.trim())
          .sort();
        setAvailableApexDomains(filteredNames);
      } else {
        setAvailableApexDomains([]);
      }
    } catch (err) {
      console.error('Error fetching apex domains:', err);
      setAvailableApexDomains([]);
    } finally {
      setLoadingApexDomains(false);
    }
  }, [selectedProgram]);

  const buildCurrentFilter = useCallback(() => {
    const filter = {};
    if (searchFilter) {
      filter.name = { $regex: searchFilter, $options: 'i' };
    }
    if (selectedProgram) {
      filter.program_name = selectedProgram;
    }
    if (wildcardFilter) {
      filter.is_wildcard = wildcardFilter === 'true';
    }
    if (hasIpsFilter) {
      if (hasIpsFilter === 'true') {
        // Check if IPs exist
        filter.ip = { $exists: true };
      } else if (hasIpsFilter === 'false') {
        // Check if IPs don't exist
        filter.ip = { $exists: false };
      }
    }
    if (hasCnameFilter) {
      if (hasCnameFilter === 'true') {
        // Check if CNAME record exists
        filter.cname_record = { $exists: true };
      } else if (hasCnameFilter === 'false') {
        // Check if CNAME record doesn't exist
        filter.cname_record = { $exists: false };
      }
    }
    if (cnameFilter) {
      filter.cname_record = { $regex: cnameFilter, $options: 'i' };
    }
    if (apexDomainFilter) {
      filter.apex_domain = apexDomainFilter;
    }
    return filter;
  }, [searchFilter, selectedProgram, wildcardFilter, hasIpsFilter, hasCnameFilter, cnameFilter, apexDomainFilter]);

  const handleSort = (field) => {
    const newDirection = sortField === field && sortDirection === 'asc' ? 'desc' : 'asc';
    setSortField(field);
    setSortDirection(newDirection);
    setCurrentPage(1);
  };

  const getSortIcon = (field) => {
    if (sortField !== field) {
      return <span className="text-muted">↕</span>;
    }
    return sortDirection === 'asc' ? <span>↑</span> : <span>↓</span>;
  };

  // Removed localStorage persistence; URL query params are the source of truth

  useEffect(() => {
    fetchDomains(currentPage);
  }, [fetchDomains, currentPage]);

  const fetchPrograms = async () => {
    try {
      const response = await programAPI.getAll();
      if (response.status === 'success' && response.programs) {
        setPrograms(response.programs);
      } else if (Array.isArray(response)) {
        setPrograms(response);
      }
    } catch (err) {
      console.error('Error fetching programs:', err);
      setPrograms([]);
    }
  };

  // Fetch programs on component mount
  useEffect(() => {
    fetchPrograms();
  }, []);

  // Fetch apex domains when program changes
  useEffect(() => {
    fetchApexDomains();
  }, [fetchApexDomains]);

  // Handle URL parameters for apex domain filtering
  useEffect(() => {
    const urlParams = new URLSearchParams(location.search);
    const apexDomainParam = urlParams.get('apex_domain');
    if (apexDomainParam) {
      setApexDomainFilter(apexDomainParam);
    }
  }, [location.search]);

  // Initialize selected import program when programs are loaded or selectedProgram changes
  useEffect(() => {
    if (programs.length > 0 && selectedProgram && programs.includes(selectedProgram)) {
      setSelectedImportProgram(selectedProgram);
    }
  }, [programs, selectedProgram]);

  // Search is handled automatically by the useEffect that watches filter changes

  const clearFilters = () => {
    setSearchFilter('');
    setExactMatchFilter('');
    setWildcardFilter('');
    setHasIpsFilter('');
    setHasCnameFilter('');
    setCnameFilter('');
    setApexDomainFilter('');
    setCurrentPage(1);
  };

  const handleDomainClick = (domain) => {
    const id = domain && domain.id;
    navigate(`/assets/subdomains/details?id=${encodeURIComponent(id || '')}`);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(domains.map(domain => domain.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (domainId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(domainId);
    } else {
      newSelected.delete(domainId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems);
      await domainAPI.deleteBatch(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page with current filters
      fetchDomains(currentPage);
    } catch (err) {
      console.error('Error deleting domains:', err);
      alert('Failed to delete domains: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
    }
  };



  const handleExport = () => {
    setShowExportModal(true);
  };

  const handleExportConfirm = async () => {
    try {
      setExporting(true);
      
      // Fetch all results via typed endpoint with large page size
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (selectedProgram) params.program = selectedProgram;
      if (wildcardFilter) params.wildcard = wildcardFilter === 'true';
      if (hasIpsFilter) params.has_ips = hasIpsFilter === 'true';
      if (hasCnameFilter) params.has_cname = hasCnameFilter === 'true';
      if (cnameFilter) params.cname_contains = cnameFilter;
      if (apexDomainFilter) params.apex_domain = apexDomainFilter;
      params.sort_by = sortField === 'ip' ? 'ip_count' : sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = 1;
      params.page_size = 10000;
      const response = await domainAPI.searchSubdomains(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - only domain names
        exportData = rawData.map(item => item.name).join('\n');
        fileExtension = 'txt';
        mimeType = 'text/plain';
      } else if (exportFormat === 'csv') {
        // CSV export with selected columns
        const selectedCols = Object.keys(exportColumns).filter(col => exportColumns[col]);
        const headers = selectedCols.join(',');
        const rows = rawData.map(item => {
          return selectedCols.map(col => {
            let value = item[col];
            if (Array.isArray(value)) {
              value = value.join('; ');
            }
            if (value && typeof value === 'string' && value.includes(',')) {
              value = `"${value.replace(/"/g, '""')}"`;
            }
            return value || '';
          }).join(',');
        });
        exportData = [headers, ...rows].join('\n');
        fileExtension = 'csv';
        mimeType = 'text/csv';
      } else {
        // JSON export with selected columns
        const selectedCols = Object.keys(exportColumns).filter(col => exportColumns[col]);
        if (selectedCols.length === Object.keys(exportColumns).length) {
          exportData = JSON.stringify(rawData, null, 2);
        } else {
          const filteredData = rawData.map(item => {
            const filtered = {};
            selectedCols.forEach(col => {
              filtered[col] = item[col];
            });
            return filtered;
          });
          exportData = JSON.stringify(filteredData, null, 2);
        }
        fileExtension = 'json';
        mimeType = 'application/json';
      }
      
      // Create and download the file
      const dataUri = `data:${mimeType};charset=utf-8,${encodeURIComponent(exportData)}`;
      const exportFileDefaultName = customFilename.trim() 
        ? `${customFilename.trim()}.${fileExtension}` 
        : `domains_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting domains:', err);
      alert('Failed to export domains: ' + err.message);
    } finally {
      setExporting(false);
    }
  };

  const handleSelectAllColumns = (checked) => {
    const newSelection = {};
    Object.keys(exportColumns).forEach(col => {
      newSelection[col] = checked;
    });
    setExportColumns(newSelection);
  };

  const handleColumnToggle = (column) => {
    setExportColumns(prev => ({
      ...prev,
      [column]: !prev[column]
    }));
  };

  // Import functionality
  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (file) {
      setImportFile(file);
      parseFilePreview(file);
    }
  };

  const parseFilePreview = async (file) => {
    const text = await file.text();
    let parsed = [];
    let detectedFormat = 'txt';
    let fields = [];

    try {
      if (file.name.endsWith('.json') || importFormat === 'json') {
        const jsonData = JSON.parse(text);
        parsed = Array.isArray(jsonData) ? jsonData : [jsonData];
        detectedFormat = 'json';
        if (parsed.length > 0) {
          fields = Object.keys(parsed[0]);
        }
      } else if (file.name.endsWith('.csv') || importFormat === 'csv') {
        const lines = text.split('\n').filter(line => line.trim());
        if (lines.length > 0) {
          // Parse CSV properly respecting quoted fields
          const parseCSVLine = (line) => {
            const result = [];
            let current = '';
            let inQuotes = false;
            
            for (let i = 0; i < line.length; i++) {
              const char = line[i];
              
              if (char === '"') {
                if (inQuotes && line[i + 1] === '"') {
                  // Escaped quote
                  current += '"';
                  i++; // Skip next quote
                } else {
                  // Toggle quote state
                  inQuotes = !inQuotes;
                }
              } else if (char === ',' && !inQuotes) {
                // Field separator
                result.push(current.trim());
                current = '';
              } else {
                current += char;
              }
            }
            
            // Add the last field
            result.push(current.trim());
            return result;
          };
          
          fields = parseCSVLine(lines[0]);
          parsed = lines.slice(1).map((line, lineIndex) => {
            const values = parseCSVLine(line);
            const obj = {};
            fields.forEach((field, index) => {
              obj[field] = values[index] || '';
            });
            
            
            // Smart handling: if we have extra values that look like IPs, merge them
            if (values.length > fields.length) {
              const extraValues = values.slice(fields.length);
              const ipPattern = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;
              const extraIPs = extraValues.filter(val => ipPattern.test(val.trim()));
              
              if (extraIPs.length > 0) {
                // Find the IP field and merge the extra IPs
                const ipFieldNames = ['ip', 'ips', 'ip_address', 'ip_addresses', 'address', 'addresses'];
                const ipField = fields.find(field => 
                  ipFieldNames.some(name => field.toLowerCase().includes(name))
                );
                
                if (ipField && obj[ipField]) {
                  // Merge with existing IP value
                  const currentIPs = obj[ipField].split(/[;,]/).map(ip => ip.trim()).filter(ip => ip);
                  const allIPs = [...currentIPs, ...extraIPs];
                  obj[ipField] = allIPs.join(', ');
                } else if (ipField) {
                  // Set IP field to the extra IPs
                  obj[ipField] = extraIPs.join(', ');
                }
              }
            }
            
            return obj;
          });
          detectedFormat = 'csv';
        }
      } else {
        // Plain text - one domain per line
        parsed = text.split('\n')
          .map(line => line.trim())
          .filter(line => line)
          .map(domain => ({ name: domain }));
        detectedFormat = 'txt';
        fields = ['name'];
      }
    } catch (error) {
      console.error('Error parsing file:', error);
      alert('Error parsing file: ' + error.message);
      return;
    }

    setPreviewData(parsed.slice(0, 10)); // Show first 10 rows for preview
    setImportPreview(parsed);
    setAvailableFields(fields);
    setImportFormat(detectedFormat);

    // Initialize field mapping for CSV/JSON
    if (detectedFormat !== 'txt') {
      const mapping = {};
      // Available fields for domains: ['name', 'program_name', 'is_wildcard', 'ip', 'cname_record']
      
      fields.forEach(field => {
        // Auto-map common field names
        const normalizedField = field.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (normalizedField.includes('domain') || normalizedField === 'name') {
          mapping[field] = 'name';
        } else if (normalizedField.includes('program')) {
          mapping[field] = 'program_name';
        } else if (normalizedField.includes('wildcard')) {
          mapping[field] = 'is_wildcard';
        } else if (normalizedField.includes('ip')) {
          mapping[field] = 'ip';
        } else if (normalizedField.includes('cname')) {
          mapping[field] = 'cname_record';
        } else {
          mapping[field] = ''; // No mapping
        }
      });
      
      setFieldMapping(mapping);
      setShowFieldMapping(true);
    } else {
      setShowFieldMapping(false);
    }
  };

  const handleFieldMappingChange = (sourceField, targetField) => {
    setFieldMapping(prev => ({
      ...prev,
      [sourceField]: targetField
    }));
  };

  const handleImportConfirm = async () => {
    if (!importPreview.length) {
      alert('No data to import');
      return;
    }

    try {
      setImporting(true);
      
      let domainsToImport = [];
      
      if (importFormat === 'txt') {
        domainsToImport = importPreview.map(item => ({
          name: item.name,
          program_name: selectedImportProgram || ''
        }));
      } else {
        // Apply field mapping for JSON/CSV
        domainsToImport = importPreview.map(item => {
          const mapped = {
            program_name: selectedImportProgram || ''
          };
          
          Object.entries(fieldMapping).forEach(([sourceField, targetField]) => {
            if (targetField && item[sourceField] !== undefined) {
              let value = item[sourceField];
              
              // Handle specific field transformations
              if (targetField === 'is_wildcard' && typeof value === 'string') {
                value = value.toLowerCase() === 'true' || value === '1';
              } else if (targetField === 'ip') {
                if (typeof value === 'string') {
                  // Split comma/semicolon separated IP addresses
                  value = value.split(/[;,]/).map(ip => ip.trim()).filter(ip => ip);
                } else if (Array.isArray(value)) {
                  // Already an array, just filter out empty values
                  value = value.filter(ip => ip && ip.trim());
                } else if (value) {
                  // Single IP value, convert to array
                  value = [String(value).trim()].filter(ip => ip);
                } else {
                  // No value, set to empty array
                  value = [];
                }
              }
              
              mapped[targetField] = value;
            }
          });
          
          return mapped;
        });
      }
      
      // Filter out items without domain names
      domainsToImport = domainsToImport.filter(domain => domain.name && domain.name.trim());
      
      if (domainsToImport.length === 0) {
        alert('No valid domains found to import');
        return;
      }
      
      // Batch import for large datasets
      const BATCH_SIZE = 100; // Adjust based on server limits
      const totalBatches = Math.ceil(domainsToImport.length / BATCH_SIZE);
      
      // Initialize progress
      setImportProgress(prev => ({
        ...prev,
        current: 0,
        total: domainsToImport.length,
        currentBatch: 0,
        totalBatches: totalBatches
      }));
      
      let totalImported = 0;
      let totalUpdated = 0;
      let totalSkipped = 0;
      let totalErrors = 0;
      let allErrors = [];
      
      for (let i = 0; i < totalBatches; i++) {
        const start = i * BATCH_SIZE;
        const end = Math.min(start + BATCH_SIZE, domainsToImport.length);
        const batch = domainsToImport.slice(start, end);
        
        // Update progress
        setImportProgress(prev => ({
          ...prev,
          current: start,
          total: domainsToImport.length,
          currentBatch: i + 1,
          totalBatches: totalBatches
        }));
        
        // Small delay to ensure UI updates
        await new Promise(resolve => setTimeout(resolve, 10));
        
        try {
          const response = await domainAPI.import(batch, {
            merge: importOptions.mergeData,
            update_existing: importOptions.updateExisting,
            validate_domains: importOptions.validateDomains
          });
          
          if (response.status === 'success' || response.status === 'partial_success') {
            const { imported_count, updated_count, skipped_count, error_count, errors } = response.data || {};
            totalImported += imported_count || 0;
            totalUpdated += updated_count || 0;
            totalSkipped += skipped_count || 0;
            totalErrors += error_count || 0;
            
            if (errors && errors.length > 0) {
              allErrors.push(...errors);
            }
          } else {
            // If batch fails completely, count as errors
            totalErrors += batch.length;
            allErrors.push(`Batch ${i + 1} failed: ${response.message || 'Unknown error'}`);
          }
        } catch (err) {
          // If batch request fails, count as errors
          totalErrors += batch.length;
          allErrors.push(`Batch ${i + 1} request failed: ${err.message}`);
        }
        
        // Small delay between batches to avoid overwhelming the server
        if (i < totalBatches - 1) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
      }
      
      // Show final results
      let message = `Import completed (${totalBatches} batches):\n`;
      message += `• ${totalImported} new domains created\n`;
      message += `• ${totalUpdated} existing domains updated\n`;
      message += `• ${totalSkipped} domains skipped\n`;
      if (totalErrors > 0) {
        message += `• ${totalErrors} errors occurred\n`;
      }
      
      if (totalSkipped > 0 && !importOptions.updateExisting) {
        message += `\nTip: Enable "Update existing domains" to merge new data with existing domains.`;
      }
      
      if (allErrors.length > 0) {
        message += `\n\nFirst few errors:\n${allErrors.slice(0, 5).join('\n')}`;
        if (allErrors.length > 5) {
          message += `\n...and ${allErrors.length - 5} more errors`;
        }
      }
      
      alert(message);
      setShowImportModal(false);
      setImportFile(null);
      setImportPreview([]);
      setFieldMapping({});
      // Refresh the domains list with current filters
      const filter = buildCurrentFilter();
      const sort = { [sortField]: sortDirection === 'asc' ? 1 : -1 };
      fetchDomains(currentPage, filter, sort);
      
    } catch (err) {
      console.error('Error importing domains:', err);
      alert('Failed to import domains: ' + err.message);
    } finally {
      setImporting(false);
    }
  };

  const resetImportModal = () => {
    setShowImportModal(false);
    setImportFile(null);
    setImportFormat('auto');
    setImportPreview([]);
    setFieldMapping({});
    setShowFieldMapping(false);
    setAvailableFields([]);
    setPreviewData([]);
    // Reset import options to defaults
    setImportOptions({
      updateExisting: true,
      mergeData: true,
      validateDomains: true
    });
    // Reset progress
    setImportProgress({
      current: 0,
      total: 0,
      currentBatch: 0,
      totalBatches: 0
    });
    // Reset selected import program to current program filter
    if (selectedProgram && programs.includes(selectedProgram)) {
      setSelectedImportProgram(selectedProgram);
    } else {
      setSelectedImportProgram('');
    }
  };

  const formatDateLocal = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString, 'MMM dd, yyyy HH:mm:ss');
  };

  const renderPagination = () => {
    if (totalPages <= 1) return null;

    const items = [];
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);

    if (endPage - startPage + 1 < maxVisible) {
      startPage = Math.max(1, endPage - maxVisible + 1);
    }

    for (let page = startPage; page <= endPage; page++) {
      items.push(
        <Pagination.Item
          key={page}
          active={page === currentPage}
          onClick={() => setCurrentPage(page)}
        >
          {page}
        </Pagination.Item>
      );
    }

    return (
      <>
        <div className="text-center text-muted mb-2">
          Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} subdomains
          (Page {currentPage} of {totalPages})
        </div>
        <div className="d-flex justify-content-center align-items-center gap-3">
          <Form.Select
            size="sm"
            value={pageSize}
            onChange={(e) => {
              setPageSize(parseInt(e.target.value));
              setCurrentPage(1);
            }}
            style={{ width: 'auto' }}
          >
            <option value={10}>10 per page</option>
            <option value={25}>25 per page</option>
            <option value={50}>50 per page</option>
            <option value={100}>100 per page</option>
          </Form.Select>
          <Pagination className="mb-0">
            <Pagination.First
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
            />
            <Pagination.Prev 
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
            />
            {startPage > 1 && <Pagination.Ellipsis disabled />}
            {items}
            {endPage < totalPages && <Pagination.Ellipsis disabled />}
            <Pagination.Next 
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
            />
            <Pagination.Last
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages}
            />
          </Pagination>
        </div>
      </>
    );
  };

  // Inline reusable popover trigger for column filters
  const ColumnFilterPopover = ({ id, isActive, ariaLabel, placement = 'bottom', buttonClassName = '', children }) => {
    const buttonVariant = isActive ? 'primary' : 'outline-secondary';

    const overlay = (
      <Popover id={id} style={{ minWidth: 280, maxWidth: 360 }} onClick={(e) => e.stopPropagation()}>
        <Popover.Body onClick={(e) => e.stopPropagation()}>
          {children}
        </Popover.Body>
      </Popover>
    );

    return (
      <OverlayTrigger trigger="click" rootClose placement={placement} overlay={overlay}>
        <Button size="sm" variant={buttonVariant} aria-label={ariaLabel} className={buttonClassName} onClick={(e) => e.stopPropagation()}>
          {/* Inline SVG fallback to avoid external icon dependency */}
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="currentColor"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
            style={{ marginRight: 4 }}
          >
            <path d="M1.5 1.5a.5.5 0 0 0 0 1h13a.5.5 0 0 0 .4-.8L10 9.2V13a.5.5 0 0 1-.276.447l-2 1A.5.5 0 0 1 7 14V9.2L1.1 1.7a.5.5 0 0 0-.4-.2z" />
          </svg>
          {/* <span style={{ fontSize: '0.8rem' }}>Filter</span> */}
        </Button>
      </OverlayTrigger>
    );
  };

  // Local text filter with Apply/Clear that doesn't update global state per keystroke
  const InlineTextFilter = ({
    label,
    placeholder,
    initialValue,
    onApply,
    onClear,
  }) => {
    const [localValue, setLocalValue] = useState(initialValue || '');
    useEffect(() => {
      setLocalValue(initialValue || '');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialValue]);

    const applyNow = () => onApply(localValue);

    return (
      <div>
        <Form.Group>
          <Form.Label className="mb-1">{label}</Form.Label>
          <Form.Control
            type="text"
            placeholder={placeholder}
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') applyNow(); }}
          />
        </Form.Group>
        <div className="d-flex justify-content-end gap-2 mt-3">
          <Button size="sm" variant="secondary" onClick={() => { setLocalValue(''); onClear?.(); }}>Clear</Button>
          <Button size="sm" variant="primary" onClick={applyNow}>Apply</Button>
        </div>
      </div>
    );
  };

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <h1>🌐 Subdomains</h1>
        </Col>
      </Row>

      <Card>
        <Card.Header className="d-flex justify-content-between align-items-center">
          <div className="d-flex align-items-center ms-auto">
            <Badge bg="secondary" className="me-3">Total: {totalItems}</Badge>
            <Button variant="link" size="sm" className="me-2 p-0" onClick={clearFilters} aria-label="Reset all filters">
              Reset filters
            </Button>
            <Button
              variant="outline-primary"
              size="sm"
              onClick={handleExport}
              className="me-2"
            >
              <i className="bi bi-download"></i> Export
            </Button>
            <Button
              variant="outline-success"
              size="sm"
              onClick={() => setShowImportModal(true)}
              className="me-2"
            >
              <i className="bi bi-upload"></i> Import
            </Button>
            {selectedItems.size > 0 && (
              <Button
                variant="outline-danger"
                size="sm"
                onClick={() => setShowDeleteModal(true)}
              >
                <i className="bi bi-trash"></i> Delete Selected ({selectedItems.size})
              </Button>
            )}
          </div>
        </Card.Header>
        <Card.Body className="p-0">
          {loading ? (
            <div className="text-center p-4">
              <Spinner animation="border" role="status">
                <span className="visually-hidden">Loading...</span>
              </Spinner>
            </div>
          ) : error ? (
            <div className="text-center p-4 text-danger">
              {error}
            </div>
          ) : domains.length === 0 ? (
            <div className="text-center p-4 text-muted">
              No domains found. This might be because the Data API is not running or no data exists.
            </div>
          ) : (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>
                    <Form.Check
                      type="checkbox"
                      checked={selectedItems.size === domains.length && domains.length > 0}
                      onChange={(e) => handleSelectAll(e.target.checked)}
                    />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>
                    <div className="d-flex align-items-center gap-2">
                      <span>Subdomain {getSortIcon('name')}</span>
                      <ColumnFilterPopover
                        id="filter-subdomain"
                        ariaLabel="Filter by subdomain"
                        isActive={!!searchFilter || !!exactMatchFilter}
                      >
                        <div>
                          <InlineTextFilter
                            label="Search"
                            placeholder="Search domains..."
                            initialValue={searchFilter}
                            onApply={(val) => setSearchFilter(val)}
                            onClear={() => setSearchFilter('')}
                          />
                          <div className="mt-3">
                            <InlineTextFilter
                              label="Exact match"
                              placeholder="Exact domain name..."
                              initialValue={exactMatchFilter}
                              onApply={(val) => setExactMatchFilter(val)}
                              onClear={() => setExactMatchFilter('')}
                            />
                          </div>
                        </div>
                      </ColumnFilterPopover>
                    </div>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('apex_domain')}>
                    <div className="d-flex align-items-center gap-2">
                      <span>Apex Domain {getSortIcon('apex_domain')}</span>
                      <ColumnFilterPopover
                        id="filter-apex"
                        ariaLabel="Filter by apex domain"
                        isActive={!!apexDomainFilter}
                      >
                        <div>
                          <Form.Group className="mb-2">
                            <Form.Label className="mb-1">Apex Domain</Form.Label>
                            <Form.Select
                              value={apexDomainFilter}
                              onChange={(e) => setApexDomainFilter(e.target.value)}
                              disabled={loadingApexDomains}
                            >
                              <option value="">All apex domains</option>
                              {availableApexDomains.map((apexDomain) => (
                                <option key={apexDomain} value={apexDomain}>{apexDomain}</option>
                              ))}
                            </Form.Select>
                            {loadingApexDomains && (
                              <Form.Text className="text-muted">Loading apex domains...</Form.Text>
                            )}
                          </Form.Group>
                          <div className="d-flex justify-content-end gap-2 mt-2">
                            <Button size="sm" variant="secondary" onClick={() => setApexDomainFilter('')}>Clear</Button>
                            <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                          </div>
                        </div>
                      </ColumnFilterPopover>
                    </div>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('program_name')}>
                    Program {getSortIcon('program_name')}
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('is_wildcard')}>
                    <div className="d-flex align-items-center gap-2">
                      <span>Type {getSortIcon('is_wildcard')}</span>
                      <ColumnFilterPopover
                        id="filter-type"
                        ariaLabel="Filter by type"
                        isActive={wildcardFilter === 'true' || wildcardFilter === 'false'}
                      >
                        <div>
                          <Form.Group>
                            <Form.Label className="mb-1">Wildcard</Form.Label>
                            <Form.Select value={wildcardFilter} onChange={(e) => setWildcardFilter(e.target.value)}>
                              <option value="">All</option>
                              <option value="true">Wildcard</option>
                              <option value="false">Regular</option>
                            </Form.Select>
                          </Form.Group>
                          <div className="d-flex justify-content-end gap-2 mt-2">
                            <Button size="sm" variant="secondary" onClick={() => setWildcardFilter('')}>Clear</Button>
                            <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                          </div>
                        </div>
                      </ColumnFilterPopover>
                    </div>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('ip')}>
                    <div className="d-flex align-items-center gap-2">
                      <span>IP Addresses {getSortIcon('ip')}</span>
                      <ColumnFilterPopover
                        id="filter-ip"
                        ariaLabel="Filter by IP presence"
                        isActive={hasIpsFilter === 'true' || hasIpsFilter === 'false'}
                      >
                        <div>
                          <Form.Group>
                            <Form.Label className="mb-1">Has IPs</Form.Label>
                            <Form.Select value={hasIpsFilter} onChange={(e) => setHasIpsFilter(e.target.value)}>
                              <option value="">All</option>
                              <option value="true">Yes</option>
                              <option value="false">No</option>
                            </Form.Select>
                          </Form.Group>
                          <div className="d-flex justify-content-end gap-2 mt-2">
                            <Button size="sm" variant="secondary" onClick={() => setHasIpsFilter('')}>Clear</Button>
                            <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                          </div>
                        </div>
                      </ColumnFilterPopover>
                    </div>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('cname_record')}>
                    <div className="d-flex align-items-center gap-2">
                      <span>CNAME {getSortIcon('cname_record')}</span>
                      <ColumnFilterPopover
                        id="filter-cname"
                        ariaLabel="Filter by CNAME"
                        isActive={hasCnameFilter === 'true' || hasCnameFilter === 'false' || !!cnameFilter}
                      >
                        <div>
                          <Form.Group className="mb-2">
                            <Form.Label className="mb-1">Has CNAME</Form.Label>
                            <Form.Select value={hasCnameFilter} onChange={(e) => setHasCnameFilter(e.target.value)}>
                              <option value="">All</option>
                              <option value="true">Yes</option>
                              <option value="false">No</option>
                            </Form.Select>
                          </Form.Group>
                          <InlineTextFilter
                            label="CNAME contains"
                            placeholder="e.g. cloudfront.net"
                            initialValue={cnameFilter}
                            onApply={(val) => setCnameFilter(val)}
                            onClear={() => setCnameFilter('')}
                          />
                        </div>
                      </ColumnFilterPopover>
                    </div>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('updated_at')}>
                    Last Updated {getSortIcon('updated_at')}
                  </th>
                </tr>
              </thead>
              <tbody>
                                    {domains.map((domain, index) => (
                      <tr key={domain.id || index}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <Form.Check
                            type="checkbox"
                            checked={selectedItems.has(domain.id)}
                            onChange={(e) => handleSelectItem(domain.id, e.target.checked)}
                          />
                    </td>
                    <td>
                      <strong 
                        style={{ cursor: 'pointer', color: 'var(--bs-link-color)' }}
                        onClick={() => handleDomainClick(domain)}
                      >
                        {domain.name || 'N/A'}
                      </strong>
                    </td>
                    <td>
                      {domain.apex_domain ? (
                        <Badge bg="info">{domain.apex_domain}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td>
                      {domain.program_name ? (
                        <Badge bg="primary">{domain.program_name}</Badge>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td>
                      {domain.is_wildcard ? (
                        <Badge bg="warning" text="dark">
                          Wildcard
                        </Badge>
                      ) : (
                        <Badge bg="success">
                          Regular
                        </Badge>
                      )}
                    </td>
                    <td>
                      {domain.ip && domain.ip.length > 0 ? (
                        <div>
                          {domain.ip.slice(0, 2).map((ip, idx) => (
                            <Badge key={idx} bg="secondary" className="me-1">
                              {ip}
                            </Badge>
                          ))}
                          {domain.ip.length > 2 && (
                            <Badge bg="secondary">
                              +{domain.ip.length - 2} more
                            </Badge>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td>
                      {domain.cname_record ? (
                        <div className="text-truncate" style={{ maxWidth: '200px' }}>
                          <small className="text-muted">{domain.cname_record}</small>
                        </div>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                                            <td className="text-muted">
                          {formatDateLocal(domain.updated_at)}
                        </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>

      {!loading && !error && renderPagination()}

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Domains</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected domain(s)?</p>
          <p className="text-danger">
            <i className="bi bi-exclamation-triangle"></i>
            This action cannot be undone.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
            Cancel
          </Button>
          <Button 
            variant="danger" 
            onClick={handleBatchDelete}
            disabled={deleting}
          >
            {deleting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Deleting...
              </>
            ) : (
              <>
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Domain(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export Domains</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Row className="mb-4">
            <Col>
              <h6>Export Format</h6>
              <Form.Check
                type="radio"
                name="exportFormat"
                id="format-json"
                label="JSON - Full data with selected columns"
                checked={exportFormat === 'json'}
                onChange={() => setExportFormat('json')}
                className="mb-2"
              />
              <Form.Check
                type="radio"
                name="exportFormat"
                id="format-csv"
                label="CSV - Spreadsheet format with selected columns"
                checked={exportFormat === 'csv'}
                onChange={() => setExportFormat('csv')}
                className="mb-2"
              />
              <Form.Check
                type="radio"
                name="exportFormat"
                id="format-txt"
                label="Plain Text - Domain names only (one per line)"
                checked={exportFormat === 'txt'}
                onChange={() => setExportFormat('txt')}
              />
            </Col>
          </Row>
          
          {exportFormat !== 'txt' && (
            <Row>
              <Col>
                <h6>Select Columns to Export</h6>
                <div className="mb-3">
                  <Form.Check
                    type="checkbox"
                    label="Select All"
                    checked={Object.values(exportColumns).every(Boolean)}
                    onChange={(e) => handleSelectAllColumns(e.target.checked)}
                    className="fw-bold mb-2"
                  />
                </div>
                <Row>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="Domain Name"
                      checked={exportColumns.name}
                      onChange={() => handleColumnToggle('name')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Program Name"
                      checked={exportColumns.program_name}
                      onChange={() => handleColumnToggle('program_name')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Is Wildcard"
                      checked={exportColumns.is_wildcard}
                      onChange={() => handleColumnToggle('is_wildcard')}
                      className="mb-2"
                    />
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="IP Addresses"
                      checked={exportColumns.ip}
                      onChange={() => handleColumnToggle('ip')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="CNAME Record"
                      checked={exportColumns.cname_record}
                      onChange={() => handleColumnToggle('cname_record')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Updated Date"
                      checked={exportColumns.updated_at}
                      onChange={() => handleColumnToggle('updated_at')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Created Date"
                      checked={exportColumns.created_at}
                      onChange={() => handleColumnToggle('created_at')}
                      className="mb-2"
                    />
                  </Col>
                </Row>
              </Col>
            </Row>
          )}
          
          <Row className="mt-3">
            <Col>
              <h6>File Name (Optional)</h6>
              <Form.Group className="mb-3">
                <Form.Control
                  type="text"
                  placeholder="Enter custom filename (without extension)"
                  value={customFilename}
                  onChange={(e) => setCustomFilename(e.target.value)}
                />
                <Form.Text className="text-muted">
                  Leave empty to use default filename: domains_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total domains to export: {totalItems} (based on current filters)
              </small>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowExportModal(false)}>
            Cancel
          </Button>
          <Button 
            variant="primary" 
            onClick={handleExportConfirm}
            disabled={exporting || (exportFormat !== 'txt' && !Object.values(exportColumns).some(Boolean))}
          >
            {exporting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Exporting...
              </>
            ) : (
              <>
                <i className="bi bi-download"></i> Export {exportFormat.toUpperCase()}
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Import Modal */}
      <Modal show={showImportModal} onHide={resetImportModal} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Import Domains</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Row className="mb-4">
            <Col>
              <h6>Select File</h6>
              <Form.Group className="mb-3">
                <Form.Control
                  type="file"
                  accept=".json,.csv,.txt"
                  onChange={handleFileSelect}
                />
                <Form.Text className="text-muted">
                  Supported formats: JSON, CSV, and Plain Text (one domain per line)
                </Form.Text>
              </Form.Group>
            </Col>
          </Row>

          {importFile && (
            <>
              <Row className="mb-3">
                <Col>
                  <h6>Program Selection</h6>
                  <Form.Group className="mb-3">
                    <Form.Label>Select Program for Import</Form.Label>
                    <Form.Select
                      value={selectedImportProgram}
                      onChange={(e) => setSelectedImportProgram(e.target.value)}
                      required
                    >
                      <option value="">-- Select a program --</option>
                      {programs.map(program => {
                        const name = typeof program === 'string' ? program : program.name;
                        return <option key={name} value={name}>{name}</option>;
                      })}
                    </Form.Select>
                    <Form.Text className="text-muted">
                      All imported domains will be assigned to this program.
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>

              <Row className="mb-3">
                <Col>
                  <h6>Import Options</h6>
                  <Form.Check
                    type="switch"
                    id="update-existing-domains"
                    label="Update existing domains"
                    checked={importOptions.updateExisting}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, updateExisting: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block mb-2">
                    When enabled, existing domains will be updated with new data. When disabled, existing domains will be skipped.
                  </Form.Text>
                  
                  <Form.Check
                    type="switch"
                    id="merge-domain-data"
                    label="Merge data (preserve existing fields)"
                    checked={importOptions.mergeData}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, mergeData: e.target.checked }))}
                    className="mb-2"
                    disabled={!importOptions.updateExisting}
                  />
                  <Form.Text className="text-muted d-block mb-2">
                    When enabled, preserves existing data and only updates fields provided in import. When disabled, replaces all data.
                  </Form.Text>
                  
                  <Form.Check
                    type="switch"
                    id="validate-domains"
                    label="Validate domain names"
                    checked={importOptions.validateDomains}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, validateDomains: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block">
                    When enabled, validates that domain names are properly formatted before import.
                  </Form.Text>
                </Col>
              </Row>

              {showFieldMapping && (
                <Row className="mb-3">
                  <Col>
                    <h6>Field Mapping</h6>
                    <p className="text-muted small">Map the columns from your file to domain fields:</p>
                    {availableFields.map(field => (
                      <Row key={field} className="mb-2 align-items-center">
                        <Col md={4}>
                          <strong>{field}</strong>
                        </Col>
                        <Col md={8}>
                          <Form.Select
                            value={fieldMapping[field] || ''}
                            onChange={(e) => handleFieldMappingChange(field, e.target.value)}
                          >
                            <option value="">-- Skip this field --</option>
                            <option value="name">Domain Name</option>
                            <option value="program_name">Program Name</option>
                            <option value="is_wildcard">Is Wildcard</option>
                            <option value="ip">IP Addresses</option>
                            <option value="cname_record">CNAME Record</option>
                          </Form.Select>
                        </Col>
                      </Row>
                    ))}
                  </Col>
                </Row>
              )}

              {previewData.length > 0 && (
                <Row className="mb-3">
                  <Col>
                    <h6>Preview ({previewData.length} of {importPreview.length} total rows)</h6>
                    <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                      <Table striped bordered size="sm">
                        <thead>
                          <tr>
                            {showFieldMapping ? (
                              availableFields.map(field => (
                                <th key={field}>{field}</th>
                              ))
                            ) : (
                              <th>Domain Name</th>
                            )}
                          </tr>
                        </thead>
                        <tbody>
                          {previewData.map((row, index) => (
                            <tr key={index}>
                              {showFieldMapping ? (
                                availableFields.map(field => (
                                  <td key={field}>{row[field]}</td>
                                ))
                              ) : (
                                <td>{row.name}</td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  </Col>
                </Row>
              )}
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={resetImportModal}>
            Cancel
          </Button>
          <Button 
            variant="primary" 
            onClick={handleImportConfirm}
            disabled={importing || !importFile || importPreview.length === 0 || !selectedImportProgram}
          >
            {importing ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                {importProgress.total > 0 ? 
                  `Importing batch ${importProgress.currentBatch}/${importProgress.totalBatches} (${importProgress.current}/${importProgress.total} domains)...` :
                  'Importing...'
                }
              </>
            ) : (
              <>
                <i className="bi bi-upload"></i> Import {importPreview.length} Domains
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default Subdomains;