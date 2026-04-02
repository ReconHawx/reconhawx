import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, Button, Spinner, Modal, OverlayTrigger, Popover } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { urlAPI, programAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

// Add Font Awesome CSS if not already loaded
const loadFontAwesome = () => {
  if (!document.querySelector('link[href*="fontawesome"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css';
    document.head.appendChild(link);
  }
};

function URLs() {
  usePageTitle(formatPageTitle('URLs'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [urls, setUrls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  const [searchFilter, setSearchFilter] = useState('');
  const [exactMatchFilter, setExactMatchFilter] = useState('');
  const [protocolFilter, setProtocolFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showOnlyRootUrls, setShowOnlyRootUrls] = useState(true);
  const [techTextFilter, setTechTextFilter] = useState('');
  const [techDropdownFilter, setTechDropdownFilter] = useState('');
  const [technologies, setTechnologies] = useState([]);
  const [portFilter, setPortFilter] = useState('');
  const [showOnlyUnusualPorts, setShowOnlyUnusualPorts] = useState(false);
  const [ports, setPorts] = useState([]);
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    url: true,
    http_status_code: true,
    title: true,
    content_length: true,
    content_type: true,
    technologies: true,
    port: true,
    program_name: true,
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
    updateExisting: true,  // Default to updating existing URLs
    mergeData: true,       // Default to merging data
    validateURLs: true     // Default to validating URLs
  });
  const [importProgress, setImportProgress] = useState({
    current: 0,
    total: 0,
    currentBatch: 0,
    totalBatches: 0
  });
  const [programs, setPrograms] = useState([]);
  const [selectedImportProgram, setSelectedImportProgram] = useState('');

  const fetchUrls = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (exactMatchFilter) params.exact_match = exactMatchFilter;
      if (protocolFilter) params.protocol = protocolFilter;
      if (showOnlyRootUrls) params.only_root = true;
      if (selectedProgram) params.program = selectedProgram;
      if (statusFilter) params.status_code = parseInt(statusFilter);
      if (techTextFilter) params.technology_text = techTextFilter;
      if (techDropdownFilter) params.technology = techDropdownFilter;
      if (portFilter) params.port = parseInt(portFilter);
      if (showOnlyUnusualPorts) params.unusual_ports = true;
      params.sort_by = sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = page;
      params.page_size = pageSize;
      const response = await urlAPI.searchURLs(params);
      setUrls(response.items || []);
      setTotalPages(response.pagination?.total_pages || 1);
      setTotalItems(response.pagination?.total_items || 0);
      setError(null);
      

    } catch (err) {
      setError('Failed to fetch URLs: ' + err.message);
      setUrls([]);
    } finally {
      setLoading(false);
    }
  }, [pageSize, searchFilter, exactMatchFilter, protocolFilter, showOnlyRootUrls, selectedProgram, statusFilter, techTextFilter, techDropdownFilter, portFilter, showOnlyUnusualPorts, sortField, sortDirection]);

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

  const fetchTechnologies = useCallback(async () => {
    try {
      // Use new efficient distinct values endpoint
      const technologies = await urlAPI.getDistinctValues('technologies', selectedProgram || undefined);
      if (technologies && Array.isArray(technologies)) {
        setTechnologies(technologies.sort());
      }
    } catch (err) {
      console.error('Error fetching technologies:', err);
      // Fallback to empty array if API call fails
      setTechnologies([]);
    }
  }, [selectedProgram]);

  const fetchPorts = useCallback(async () => {
    try {
      // Use new efficient distinct values endpoint
      const ports = await urlAPI.getDistinctValues('port', selectedProgram || undefined);
      if (ports && Array.isArray(ports)) {
        setPorts(ports.sort((a, b) => parseInt(a) - parseInt(b)));
      }
    } catch (err) {
      console.error('Error fetching ports:', err);
      // Fallback to empty array if API call fails
      setPorts([]);
    }
  }, [selectedProgram]);

  const fetchPrograms = useCallback(async () => {
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
  }, []);

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
    if (protocolFilter) params.set('protocol', protocolFilter);
    if (statusFilter) params.set('status_code', statusFilter);
    if (showOnlyRootUrls) params.set('only_root', 'true');
    if (techTextFilter) params.set('technology_text', techTextFilter);
    if (techDropdownFilter) params.set('technology', techDropdownFilter);
    if (portFilter) params.set('port', portFilter);
    if (showOnlyUnusualPorts) params.set('unusual_ports', 'true');
    if (sortField) params.set('sort_by', sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [
    searchFilter,
    exactMatchFilter,
    selectedProgram,
    protocolFilter,
    statusFilter,
    showOnlyRootUrls,
    techTextFilter,
    techDropdownFilter,
    portFilter,
    showOnlyUnusualPorts,
    sortField,
    sortDirection,
    currentPage,
    pageSize
  ]);

  // Parse query params into state (runs on URL change and initial load)
  useEffect(() => {
    isSyncingFromUrl.current = true;
    const urlParams = new URLSearchParams(location.search);

    const urlSearch = urlParams.get('search') || '';
    if (urlSearch !== searchFilter) setSearchFilter(urlSearch);

    const urlExactMatch = urlParams.get('exact_match') || '';
    if (urlExactMatch !== exactMatchFilter) setExactMatchFilter(urlExactMatch);

    const urlProgram = urlParams.get('program') || '';
    if (urlProgram && urlProgram !== selectedProgram) setSelectedProgram(urlProgram);

    const urlProtocol = urlParams.get('protocol') || '';
    if (urlProtocol !== protocolFilter) setProtocolFilter(urlProtocol);

    const urlStatus = urlParams.get('status_code') || '';
    if (urlStatus !== statusFilter) setStatusFilter(urlStatus);

    const urlOnlyRoot = urlParams.get('only_root');
    const normalizedOnlyRoot = urlOnlyRoot === 'true';
    if (urlOnlyRoot !== null && normalizedOnlyRoot !== showOnlyRootUrls) setShowOnlyRootUrls(normalizedOnlyRoot);

    const urlTechText = urlParams.get('technology_text') || '';
    if (urlTechText !== techTextFilter) setTechTextFilter(urlTechText);

    const urlTech = urlParams.get('technology') || '';
    if (urlTech !== techDropdownFilter) setTechDropdownFilter(urlTech);

    const urlPort = urlParams.get('port') || '';
    if (urlPort !== portFilter) setPortFilter(urlPort);

    const urlUnusualPorts = urlParams.get('unusual_ports');
    const normalizedUnusualPorts = urlUnusualPorts === 'true';
    if (urlUnusualPorts !== null && normalizedUnusualPorts !== showOnlyUnusualPorts) setShowOnlyUnusualPorts(normalizedUnusualPorts);

    const urlSortBy = urlParams.get('sort_by');
    if (urlSortBy && urlSortBy !== sortField) setSortField(urlSortBy);

    const urlSortDir = urlParams.get('sort_dir');
    if (urlSortDir && (urlSortDir === 'asc' || urlSortDir === 'desc') && urlSortDir !== sortDirection) setSortDirection(urlSortDir);

    const urlPage = parseInt(urlParams.get('page') || '1', 10);
    if (!Number.isNaN(urlPage) && urlPage > 0 && urlPage !== currentPage) setCurrentPage(urlPage);

    const urlPageSize = parseInt(urlParams.get('page_size') || '25', 10);
    if (!Number.isNaN(urlPageSize) && urlPageSize > 0 && urlPageSize !== pageSize) setPageSize(urlPageSize);

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
  }, [navigate, location.pathname, location.search, buildUrlParamsFromState]);

  useEffect(() => {

    fetchUrls(currentPage);
  }, [currentPage, fetchUrls]);

  // Fetch technologies and ports on component mount and when selected program changes
  useEffect(() => {
    fetchTechnologies();
    fetchPorts();
  }, [selectedProgram, fetchTechnologies, fetchPorts]);

  // Load Font Awesome CSS on component mount
  useEffect(() => {
    loadFontAwesome();
  }, []);

  // Fetch programs on component mount
  useEffect(() => {
    fetchPrograms();
  }, [fetchPrograms]);

  // Initialize selected import program when programs are loaded or selectedProgram changes
  useEffect(() => {
    if (programs.length > 0 && selectedProgram && programs.includes(selectedProgram)) {
      setSelectedImportProgram(selectedProgram);
    }
  }, [programs, selectedProgram]);

  const clearFilters = () => {
    setSearchFilter('');
    setExactMatchFilter('');
    setProtocolFilter('');
    setStatusFilter('');
    setShowOnlyRootUrls(true);
    setTechTextFilter('');
    setTechDropdownFilter('');
    setPortFilter('');
    setShowOnlyUnusualPorts(false);
    setPageSize(25);
    setCurrentPage(1);
    // URL will be updated by sync effect
  };

  const handleUrlClick = (url) => {
    navigate(`/assets/urls/details?id=${encodeURIComponent(url.id || '')}`);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(urls.map(url => url.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (urlId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(urlId);
    } else {
      newSelected.delete(urlId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems);
      await urlAPI.deleteBatch(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page with current filters
      const filter = buildExportFilter();
      
      const sort = { [sortField]: sortDirection === 'asc' ? 1 : -1 };
      fetchUrls(currentPage, filter, sort);
    } catch (err) {
      console.error('Error deleting URLs:', err);
      alert('Failed to delete URLs: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
    }
  };

  const buildExportFilter = () => {
    const filter = {};
    
    // Simple URL search pattern - let backend handle the optimization
    if (searchFilter) {
      filter.url = { $regex: searchFilter, $options: 'i' };
    }
    
    // Protocol filter
    if (protocolFilter) {
      filter.scheme = protocolFilter;
    }
    
    // Root URLs filter - simplified to work better with backend
    if (showOnlyRootUrls) {
      // Use a simple path filter instead of complex regex
      filter.path = '/';
    }
    
    // Add other filters
    if (selectedProgram) {
      filter.program_name = selectedProgram;
    }
    if (statusFilter) {
      filter.http_status_code = parseInt(statusFilter);
    }
    if (techTextFilter) {
      filter.technologies = { $regex: techTextFilter, $options: 'i' };
    }
    if (techDropdownFilter) {
      filter.technologies = techDropdownFilter;
    }
    if (portFilter) {
      filter.port = parseInt(portFilter);
    }
    if (showOnlyUnusualPorts) {
      filter.unusual_ports = true;
    }
    return filter;
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
      if (protocolFilter) params.protocol = protocolFilter;
      if (showOnlyRootUrls) params.only_root = true;
      if (selectedProgram) params.program = selectedProgram;
      if (statusFilter) params.status_code = parseInt(statusFilter);
      if (techTextFilter) params.technology_text = techTextFilter;
      if (techDropdownFilter) params.technology = techDropdownFilter;
      if (portFilter) params.port = parseInt(portFilter);
      if (showOnlyUnusualPorts) params.unusual_ports = true;
      params.sort_by = sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = 1;
      params.page_size = 10000;
      const response = await urlAPI.searchURLs(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - only URLs
        exportData = rawData.map(item => item.url).join('\n');
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
        : `urls_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting URLs:', err);
      alert('Failed to export URLs: ' + err.message);
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
          parsed = lines.slice(1).map(line => {
            const values = parseCSVLine(line);
            const obj = {};
            fields.forEach((field, index) => {
              obj[field] = values[index] || '';
            });
            return obj;
          });
          detectedFormat = 'csv';
        }
      } else {
        // Plain text - one URL per line
        parsed = text.split('\n')
          .map(line => line.trim())
          .filter(line => line)
          .map(url => ({ url: url }));
        detectedFormat = 'txt';
        fields = ['url'];
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
      
      fields.forEach(field => {
        // Auto-map common field names
        const normalizedField = field.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (normalizedField.includes('url') || normalizedField.includes('link')) {
          mapping[field] = 'url';
        } else if (normalizedField.includes('program')) {
          mapping[field] = 'program_name';
        } else if (normalizedField.includes('status') || normalizedField.includes('code')) {
          mapping[field] = 'http_status_code';
        } else if (normalizedField.includes('title')) {
          mapping[field] = 'title';
        } else if (normalizedField.includes('length') || normalizedField.includes('size')) {
          mapping[field] = 'content_length';
        } else if (normalizedField.includes('type') || normalizedField.includes('contenttype')) {
          mapping[field] = 'content_type';
        } else if (normalizedField.includes('tech') || normalizedField.includes('technology')) {
          mapping[field] = 'technologies';
        } else if (normalizedField.includes('port')) {
          mapping[field] = 'port';
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
      
      let urlsToImport = [];
      
      if (importFormat === 'txt') {
        urlsToImport = importPreview.map(item => ({
          url: item.url,
          program_name: selectedImportProgram || ''
        }));
      } else {
        // Apply field mapping for JSON/CSV
        urlsToImport = importPreview.map(item => {
          const mapped = {
            program_name: selectedImportProgram || ''
          };
          
          Object.entries(fieldMapping).forEach(([sourceField, targetField]) => {
            if (targetField && item[sourceField] !== undefined) {
              let value = item[sourceField];
              
              // Handle specific field transformations
              if (targetField === 'technologies' && typeof value === 'string') {
                value = value.split(/[;,]/).map(tech => tech.trim()).filter(tech => tech);
              } else if (targetField === 'http_status_code' && typeof value === 'string') {
                value = parseInt(value) || 0;
              } else if (targetField === 'content_length' && typeof value === 'string') {
                value = parseInt(value) || 0;
              } else if (targetField === 'port' && typeof value === 'string') {
                value = parseInt(value) || 0;
              }
              
              mapped[targetField] = value;
            }
          });
          
          return mapped;
        });
      }
      
      // Filter out items without URLs
      urlsToImport = urlsToImport.filter(url => url.url && url.url.trim());
      
      if (urlsToImport.length === 0) {
        alert('No valid URLs found to import');
        return;
      }
      
      // Batch import for large datasets
      const BATCH_SIZE = 100; // Adjust based on server limits
      const totalBatches = Math.ceil(urlsToImport.length / BATCH_SIZE);
      
      // Initialize progress
      setImportProgress({
        current: 0,
        total: urlsToImport.length,
        currentBatch: 0,
        totalBatches: totalBatches
      });
      
      let totalImported = 0;
      let totalUpdated = 0;
      let totalSkipped = 0;
      let totalErrors = 0;
      let allErrors = [];
      
      for (let i = 0; i < totalBatches; i++) {
        const start = i * BATCH_SIZE;
        const end = Math.min(start + BATCH_SIZE, urlsToImport.length);
        const batch = urlsToImport.slice(start, end);
        
        // Update progress
        setImportProgress({
          current: start,
          total: urlsToImport.length,
          currentBatch: i + 1,
          totalBatches: totalBatches
        });
        
        try {
          const response = await urlAPI.import(batch, {
            merge: importOptions.mergeData,
            update_existing: importOptions.updateExisting,
            validate_urls: importOptions.validateURLs
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
      message += `• ${totalImported} new URLs created\n`;
      message += `• ${totalUpdated} existing URLs updated\n`;
      message += `• ${totalSkipped} URLs skipped\n`;
      if (totalErrors > 0) {
        message += `• ${totalErrors} errors occurred\n`;
      }
      
      if (totalSkipped > 0 && !importOptions.updateExisting) {
        message += `\nTip: Enable "Update existing URLs" to merge new data with existing URLs.`;
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
      // Refresh the URLs list with current filters
      const filter = buildExportFilter();
      
      const sort = { [sortField]: sortDirection === 'asc' ? 1 : -1 };
      fetchUrls(currentPage, filter, sort);
      
    } catch (err) {
      console.error('Error importing URLs:', err);
      alert('Failed to import URLs: ' + err.message);
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
      validateURLs: true
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



  const truncateUrl = (url, maxLength = 60) => {
    if (url.length <= maxLength) return url;
    return url.substring(0, maxLength) + '...';
  };

  const getProtocolFromUrl = (url) => {
    try {
      return new URL(url).protocol.replace(':', '');
    } catch (e) {
      return 'unknown';
    }
  };

  const renderPagination = () => {
    if (totalPages <= 1) return null;

    const pages = [];
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage < maxVisiblePages - 1) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
      pages.push(
        <Pagination.Item
          key={i}
          active={i === currentPage}
          onClick={() => setCurrentPage(i)}
        >
          {i}
        </Pagination.Item>
      );
    }

    return (
      <>
        <div className="text-center text-muted mb-2">
          Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} URLs
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
            <Pagination.First onClick={() => setCurrentPage(1)} disabled={currentPage === 1} />
            <Pagination.Prev onClick={() => setCurrentPage(currentPage - 1)} disabled={currentPage === 1} />
            {startPage > 1 && <Pagination.Ellipsis disabled />}
            {pages}
            {endPage < totalPages && <Pagination.Ellipsis disabled />}
            <Pagination.Next onClick={() => setCurrentPage(currentPage + 1)} disabled={currentPage === totalPages} />
            <Pagination.Last onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} />
          </Pagination>
        </div>
      </>
    );
  };

  // Column filter popover trigger
  const ColumnFilterPopover = ({ id, isActive, ariaLabel, placement = 'bottom', children }) => {
    const buttonVariant = isActive ? 'primary' : 'outline-secondary';
    const overlay = (
      <Popover id={id} style={{ minWidth: 280, maxWidth: 380 }} onClick={(e) => e.stopPropagation()}>
        <Popover.Body onClick={(e) => e.stopPropagation()}>
          {children}
        </Popover.Body>
      </Popover>
    );
    return (
      <OverlayTrigger trigger="click" rootClose placement={placement} overlay={overlay}>
        <Button size="sm" variant={buttonVariant} aria-label={ariaLabel} onClick={(e) => e.stopPropagation()}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style={{ marginRight: 4 }}>
            <path d="M1.5 1.5a.5.5 0 0 0 0 1h13a.5.5 0 0 0 .4-.8L10 9.2V13a.5.5 0 0 1-.276.447l-2 1A.5.5 0 0 1 7 14V9.2L1.1 1.7a.5.5 0 0 0-.4-.2z" />
          </svg>
          {/* <span style={{ fontSize: '0.8rem' }}>Filter</span> */}
        </Button>
      </OverlayTrigger>
    );
  };

  // Local text filter component to avoid per-keystroke URL sync
  const InlineTextFilter = ({ label, placeholder, initialValue, onApply, onClear }) => {
    const [localValue, setLocalValue] = useState(initialValue || '');
    useEffect(() => { setLocalValue(initialValue || ''); }, [initialValue]);
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
          <h1>🔗 URLs</h1>
          <p className="text-muted">Browse and manage URLs discovered during reconnaissance</p>
        </Col>
      </Row>

      

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">URLs</h5>
              <div className="d-flex align-items-center">
                <Badge bg="secondary" className="me-3">Total: {totalItems}</Badge>
                <Form.Check
                  type="switch"
                  id="root-path-only"
                  label="Root Path Only"
                  checked={showOnlyRootUrls}
                  onChange={(e) => { setShowOnlyRootUrls(e.target.checked); setCurrentPage(1); }}
                  className="me-3"
                  title="Show only URLs with root path (/); hide URLs with paths like /about, /login, etc."
                />
                <Button variant="link" size="sm" className="me-2 p-0" onClick={clearFilters} aria-label="Reset all filters">Reset filters</Button>
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
                  <p className="mt-2">Loading URLs...</p>
                </div>
              ) : error ? (
                <div className="p-4">
                  <p className="text-danger">{error}</p>
                </div>
              ) : urls.length === 0 ? (
                <div className="p-4 text-center">
                  <p className="text-muted">No URLs found matching the current filters.</p>
                </div>
              ) : (
                <Table hover responsive>
                  <thead>
                    <tr>
                      <th>
                        <Form.Check
                          type="checkbox"
                          checked={selectedItems.size === urls.length && urls.length > 0}
                          onChange={(e) => handleSelectAll(e.target.checked)}
                        />
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('url')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>URL {getSortIcon('url')}</span>
                          <ColumnFilterPopover id="filter-url" ariaLabel="Filter by URL" isActive={!!searchFilter || !!exactMatchFilter}>
                            <div>
                              <InlineTextFilter
                                label="Search"
                                placeholder="e.g., admin, login, api"
                                initialValue={searchFilter}
                                onApply={(val) => setSearchFilter(val)}
                                onClear={() => setSearchFilter('')}
                              />
                              <div className="mt-3">
                                <InlineTextFilter
                                  label="Exact match"
                                  placeholder="https://example.com/admin"
                                  initialValue={exactMatchFilter}
                                  onApply={(val) => setExactMatchFilter(val)}
                                  onClear={() => setExactMatchFilter('')}
                                />
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('url')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Protocol {getSortIcon('url')}</span>
                          <ColumnFilterPopover id="filter-protocol" ariaLabel="Filter by protocol" isActive={!!protocolFilter}>
                            <div>
                              <Form.Group>
                                <Form.Label className="mb-1">Protocol</Form.Label>
                                <Form.Select value={protocolFilter} onChange={(e) => setProtocolFilter(e.target.value)}>
                                  <option value="">All</option>
                                  <option value="https">HTTPS</option>
                                  <option value="http">HTTP</option>
                                </Form.Select>
                              </Form.Group>
                              <div className="d-flex justify-content-end gap-2 mt-2">
                                <Button size="sm" variant="secondary" onClick={() => setProtocolFilter('')}>Clear</Button>
                                <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('port')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Port {getSortIcon('port')}</span>
                          <ColumnFilterPopover id="filter-port" ariaLabel="Filter by port" isActive={!!portFilter || showOnlyUnusualPorts}>
                            <div>
                              <Form.Group className="mb-2">
                                <Form.Label className="mb-1">Port</Form.Label>
                                <Form.Select value={portFilter} onChange={(e) => setPortFilter(e.target.value)}>
                                  <option value="">All Ports</option>
                                  {ports.map(port => (
                                    <option key={port} value={port}>{port}</option>
                                  ))}
                                </Form.Select>
                              </Form.Group>
                              <Form.Check
                                type="switch"
                                id="unusual-ports"
                                label="Only unusual ports (not 80/443)"
                                checked={showOnlyUnusualPorts}
                                onChange={(e) => setShowOnlyUnusualPorts(e.target.checked)}
                              />
                              <div className="d-flex justify-content-end gap-2 mt-2">
                                <Button size="sm" variant="secondary" onClick={() => { setPortFilter(''); setShowOnlyUnusualPorts(false); }}>Clear</Button>
                                <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('http_status_code')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Status {getSortIcon('http_status_code')}</span>
                          <ColumnFilterPopover id="filter-status" ariaLabel="Filter by status" isActive={!!statusFilter}>
                            <div>
                              <Form.Group>
                                <Form.Label className="mb-1">Status Code</Form.Label>
                                <Form.Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                                  <option value="">All</option>
                                  <option value="200">200</option>
                                  <option value="301">301</option>
                                  <option value="302">302</option>
                                  <option value="403">403</option>
                                  <option value="404">404</option>
                                  <option value="500">500</option>
                                </Form.Select>
                              </Form.Group>
                              <div className="d-flex justify-content-end gap-2 mt-2">
                                <Button size="sm" variant="secondary" onClick={() => setStatusFilter('')}>Clear</Button>
                                <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('program_name')}
                      >
                        Program {getSortIcon('program_name')}
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('technologies')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Technologies {getSortIcon('technologies')}</span>
                          <ColumnFilterPopover id="filter-technologies" ariaLabel="Filter by technologies" isActive={!!techTextFilter || !!techDropdownFilter}>
                            <div>
                              <InlineTextFilter
                                label="Technology (Text)"
                                placeholder="Search technologies..."
                                initialValue={techTextFilter}
                                onApply={(val) => setTechTextFilter(val)}
                                onClear={() => setTechTextFilter('')}
                              />
                              <div className="mt-3">
                                <Form.Group>
                                  <Form.Label className="mb-1">Technology (Dropdown)</Form.Label>
                                  <Form.Select value={techDropdownFilter} onChange={(e) => setTechDropdownFilter(e.target.value)}>
                                    <option value="">All Technologies</option>
                                    {technologies.map(tech => (
                                      <option key={tech} value={tech}>{tech}</option>
                                    ))}
                                  </Form.Select>
                                </Form.Group>
                                <div className="d-flex justify-content-end gap-2 mt-2">
                                  <Button size="sm" variant="secondary" onClick={() => setTechDropdownFilter('')}>Clear</Button>
                                  <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                </div>
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('updated_at')}
                      >
                        Last Updated {getSortIcon('updated_at')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {urls.map((url) => (
                      <tr key={url.id}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <Form.Check
                            type="checkbox"
                            checked={selectedItems.has(url.id)}
                            onChange={(e) => handleSelectItem(url.id, e.target.checked)}
                          />
                        </td>
                        <td 
                          onClick={() => handleUrlClick(url)} 
                          style={{ cursor: 'pointer' }}
                        >
                          <code title={url.url} className="text-break">
                            {truncateUrl(url.url)}
                          </code>
                        </td>
                        <td>
                          <Badge bg={getProtocolFromUrl(url.url) === 'https' ? 'success' : 'warning'}>
                            {getProtocolFromUrl(url.url)}
                          </Badge>
                        </td>
                        <td>
                          {url.port ? (
                            <Badge bg={url.port === 80 || url.port === 443 ? 'secondary' : 'warning'}>
                              {url.port}
                            </Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {url.http_status_code ? (
                            <Badge bg={url.http_status_code < 300 ? 'success' : url.http_status_code < 400 ? 'warning' : 'danger'}>
                              {url.http_status_code}
                            </Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {url.program_name ? (
                            <Badge bg="primary">{url.program_name}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {url.technologies && url.technologies.length > 0 ? (
                            <div>
                              {url.technologies.slice(0, 2).map((tech, idx) => (
                                <Badge key={idx} bg="info" className="me-1 mb-1">
                                  {tech}
                                </Badge>
                              ))}
                              {url.technologies.length > 2 && (
                                <Badge bg="secondary">+{url.technologies.length - 2} more</Badge>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td className="text-muted">
                          {formatDate(url.updated_at, 'MMM dd, yyyy HH:mm:ss')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card.Body>
            {!loading && !error && renderPagination() && (
              <Card.Footer>
                {renderPagination()}
              </Card.Footer>
            )}
          </Card>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete URLs</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected URL(s)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} URL(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export URLs</Modal.Title>
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
                label="Plain Text - URLs only (one per line)"
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
                      label="URL"
                      checked={exportColumns.url}
                      onChange={() => handleColumnToggle('url')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Status Code"
                      checked={exportColumns.http_status_code}
                      onChange={() => handleColumnToggle('http_status_code')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Title"
                      checked={exportColumns.title}
                      onChange={() => handleColumnToggle('title')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Content Length"
                      checked={exportColumns.content_length}
                      onChange={() => handleColumnToggle('content_length')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Content Type"
                      checked={exportColumns.content_type}
                      onChange={() => handleColumnToggle('content_type')}
                      className="mb-2"
                    />
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="Technologies"
                      checked={exportColumns.technologies}
                      onChange={() => handleColumnToggle('technologies')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Port"
                      checked={exportColumns.port}
                      onChange={() => handleColumnToggle('port')}
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
                  Leave empty to use default filename: urls_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total URLs to export: {totalItems} (based on current filters)
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
          <Modal.Title>Import URLs</Modal.Title>
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
                  Supported formats: JSON, CSV, and Plain Text (one URL per line)
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
                      All imported URLs will be assigned to this program.
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>

              <Row className="mb-3">
                <Col>
                  <h6>Import Options</h6>
                  <Form.Check
                    type="switch"
                    id="update-existing-urls"
                    label="Update existing URLs"
                    checked={importOptions.updateExisting}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, updateExisting: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block mb-2">
                    When enabled, existing URLs will be updated with new data. When disabled, existing URLs will be skipped.
                  </Form.Text>
                  
                  <Form.Check
                    type="switch"
                    id="merge-url-data"
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
                    id="validate-urls"
                    label="Validate URL format"
                    checked={importOptions.validateURLs}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, validateURLs: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block">
                    When enabled, validates that URLs are properly formatted before import.
                  </Form.Text>
                </Col>
              </Row>

              {showFieldMapping && (
                <Row className="mb-3">
                  <Col>
                    <h6>Field Mapping</h6>
                    <p className="text-muted small">Map the columns from your file to URL fields:</p>
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
                            <option value="url">URL</option>
                            <option value="program_name">Program Name</option>
                            <option value="http_status_code">Status Code</option>
                            <option value="title">Title</option>
                            <option value="content_length">Content Length</option>
                            <option value="content_type">Content Type</option>
                            <option value="technologies">Technologies</option>
                            <option value="port">Port</option>
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
                              <th>URL</th>
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
                                <td>{row.url}</td>
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
                  `Importing batch ${importProgress.currentBatch}/${importProgress.totalBatches} (${importProgress.current}/${importProgress.total} URLs)...` :
                  'Importing...'
                }
              </>
            ) : (
              <>
                <i className="bi bi-upload"></i> Import {importPreview.length} URLs
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default URLs;