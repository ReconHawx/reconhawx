import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, Button, Spinner, Modal, OverlayTrigger, Popover } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { serviceAPI, programAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function Services() {
  usePageTitle(formatPageTitle('Services'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  
  const [pageSize, setPageSize] = useState(25);

  const [ipFilter, setIpFilter] = useState('');
  const [portFilter, setPortFilter] = useState('');
  const [uncommonPortsOnly, setUncommonPortsOnly] = useState(false);
  const [distinctPorts, setDistinctPorts] = useState([]);
  const [protocolFilter, setProtocolFilter] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');
  const [serviceTextFilter, setServiceTextFilter] = useState('');
  const [distinctServiceNames, setDistinctServiceNames] = useState([]);
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    ip: true,
    port: true,
    service: true,
    protocol: true,
    banner: true,
    product: true,
    version: true,
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
    updateExisting: true,  // Default to updating existing services
    mergeData: true,       // Default to merging data
    validateServices: true // Default to validating service data
  });
  const [programs, setPrograms] = useState([]);
  const [selectedImportProgram, setSelectedImportProgram] = useState('');
  const [importProgress, setImportProgress] = useState({
    current: 0,
    total: 0,
    currentBatch: 0,
    totalBatches: 0
  });

  const fetchServices = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = {};
      if (ipFilter && ipFilter.trim()) {
        params.search_ip = ipFilter.trim();
      }
      if (portFilter && portFilter.trim()) {
        const portNum = parseInt(portFilter.trim(), 10);
        if (!Number.isNaN(portNum) && portNum >= 0 && portNum <= 65535) {
          params.port = portNum;
        }
      }
      if (selectedProgram) params.program = selectedProgram;
      if (protocolFilter) params.protocol = protocolFilter;
      if (serviceTextFilter) params.service_text = serviceTextFilter;
      else if (serviceFilter) params.service_name = serviceFilter;
      if (uncommonPortsOnly) params.exclude_common_ports = true;
      // Map common field name variations to correct service field names
      const mappedSortField = sortField === 'ip_address' ? 'ip' : sortField === 'service' ? 'service_name' : sortField;
      params.sort_by = mappedSortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = page;
      params.page_size = pageSize;
      const response = await serviceAPI.searchServices(params);
      setServices(response.items || []);
      setTotalPages(response.pagination?.total_pages || 1);
      setTotalItems(response.pagination?.total_items || 0);
      setError(null);
    } catch (err) {
      setError('Failed to fetch services: ' + err.message);
      setServices([]);
    } finally {
      setLoading(false);
    }
  }, [
    ipFilter,
    portFilter,
    selectedProgram,
    protocolFilter,
    serviceTextFilter,
    serviceFilter,
    uncommonPortsOnly,
    sortField,
    sortDirection,
    pageSize
  ]);

  const fetchDistinctServiceNames = useCallback(async () => {
    try {
      const sample = await serviceAPI.searchServices({ program: selectedProgram || undefined, page: 1, page_size: 1000, sort_by: 'service_name', sort_dir: 'asc' });
      if (sample.items) {
        const serviceNames = [...new Set(sample.items.map(s => s.service_name).filter(Boolean))].sort();
        setDistinctServiceNames(serviceNames);
      }
    } catch (err) {
      console.error('Error fetching service names:', err);
    }
  }, [selectedProgram]);

  const fetchDistinctPorts = useCallback(async () => {
    try {
      const ports = await serviceAPI.getDistinctValues('port', selectedProgram || undefined);
      if (ports && Array.isArray(ports)) {
        setDistinctPorts(ports.map(String).sort((a, b) => parseInt(a, 10) - parseInt(b, 10)));
      } else {
        setDistinctPorts([]);
      }
    } catch (err) {
      console.error('Error fetching distinct ports:', err);
      setDistinctPorts([]);
    }
  }, [selectedProgram]);

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
    if (ipFilter) params.set('ip', ipFilter);
    if (portFilter) params.set('port', portFilter);
    if (uncommonPortsOnly) params.set('uncommon_ports', '1');
    if (selectedProgram) params.set('program', selectedProgram);
    if (protocolFilter) params.set('protocol', protocolFilter);
    if (serviceTextFilter) params.set('service_text', serviceTextFilter);
    if (serviceFilter) params.set('service_name', serviceFilter);
    if (sortField) params.set('sort_by', sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [
    ipFilter,
    portFilter,
    uncommonPortsOnly,
    selectedProgram,
    protocolFilter,
    serviceTextFilter,
    serviceFilter,
    sortField,
    sortDirection,
    currentPage,
    pageSize
  ]);

  // Parse query params into state (runs on URL change and initial load)
  useEffect(() => {
    isSyncingFromUrl.current = true;
    const urlParams = new URLSearchParams(location.search);

    const urlIp = urlParams.get('ip') || '';
    if (urlIp !== ipFilter) setIpFilter(urlIp);

    const urlPort = urlParams.get('port') || '';
    if (urlPort !== portFilter) setPortFilter(urlPort);

    const urlProgram = urlParams.get('program') || '';
    if (urlProgram && urlProgram !== selectedProgram) setSelectedProgram(urlProgram);

    const urlProtocol = urlParams.get('protocol') || '';
    if (urlProtocol !== protocolFilter) setProtocolFilter(urlProtocol);

    const urlServiceText = urlParams.get('service_text') || '';
    if (urlServiceText !== serviceTextFilter) setServiceTextFilter(urlServiceText);

    const urlServiceName = urlParams.get('service_name') || '';
    if (urlServiceName !== serviceFilter) setServiceFilter(urlServiceName);

    const urlUncommonPorts = urlParams.get('uncommon_ports');
    if (urlUncommonPorts === '1' && !uncommonPortsOnly) setUncommonPortsOnly(true);
    else if (urlUncommonPorts !== '1' && uncommonPortsOnly) setUncommonPortsOnly(false);

    const urlSortBy = urlParams.get('sort_by');
    if (urlSortBy && urlSortBy !== sortField) {
      // Map common field name variations to correct service field names
      const mappedSortBy = urlSortBy === 'ip_address' ? 'ip' : urlSortBy === 'service_name' ? 'service' : urlSortBy;
      setSortField(mappedSortBy);
    }

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
    fetchServices(currentPage);
  }, [fetchServices, currentPage]);

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

  // Fetch distinct service names and ports on mount and when program changes
  useEffect(() => {
    fetchDistinctServiceNames();
    fetchDistinctPorts();
  }, [fetchDistinctServiceNames, fetchDistinctPorts]);

  // Fetch programs on component mount
  useEffect(() => {
    fetchPrograms();
  }, []);

  // Initialize selected import program when programs are loaded or selectedProgram changes
  useEffect(() => {
    if (programs.length > 0 && selectedProgram && programs.includes(selectedProgram)) {
      setSelectedImportProgram(selectedProgram);
    }
  }, [programs, selectedProgram]);

  const clearFilters = () => {
    setIpFilter('');
    setPortFilter('');
    setUncommonPortsOnly(false);
    setProtocolFilter('');
    setServiceFilter('');
    setServiceTextFilter('');
    setPageSize(25);
    setCurrentPage(1);
    // URL will be updated by sync effect
  };

  const handleServiceClick = (service) => {
    navigate(`/assets/services/details?id=${encodeURIComponent(service.id || '')}`);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(services.map(service => service.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (serviceId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(serviceId);
    } else {
      newSelected.delete(serviceId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems);
      await serviceAPI.deleteBatch(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page with current filters
      fetchServices(currentPage);
    } catch (err) {
      console.error('Error deleting services:', err);
      alert('Failed to delete services: ' + (err.response?.data?.detail || err.message));
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

      // Fetch all results
      const params = {};
      if (ipFilter && ipFilter.trim()) params.search_ip = ipFilter.trim();
      if (portFilter && portFilter.trim()) {
        const portNum = parseInt(portFilter.trim(), 10);
        if (!Number.isNaN(portNum) && portNum >= 0 && portNum <= 65535) {
          params.port = portNum;
        }
      }
      if (selectedProgram) params.program = selectedProgram;
      if (protocolFilter) params.protocol = protocolFilter;
      if (serviceTextFilter) params.service_text = serviceTextFilter;
      else if (serviceFilter) params.service_name = serviceFilter;
      if (uncommonPortsOnly) params.exclude_common_ports = true;
      // Map common field name variations to correct service field names
      const mappedSortField = sortField === 'ip_address' ? 'ip' : sortField === 'service' ? 'service_name' : sortField;
      params.sort_by = mappedSortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = 1;
      params.page_size = 10000;
      const response = await serviceAPI.searchServices(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - IP:Port combinations
        exportData = rawData.map(item => `${item.ip?.split('/')[0] || item.ip}:${item.port}`).join('\n');
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
        : `services_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting services:', err);
      alert('Failed to export services: ' + err.message);
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
        // Plain text - one IP:Port per line
        parsed = text.split('\n')
          .map(line => line.trim())
          .filter(line => line)
          .map(line => {
            const parts = line.split(':');
            if (parts.length >= 2) {
              return { 
                ip: parts[0].trim(), 
                port: parseInt(parts[1].trim()) || parts[1].trim()
              };
            } else {
              return { service_line: line }; // Handle non-standard formats
            }
          });
        detectedFormat = 'txt';
        fields = ['ip', 'port'];
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
        if (normalizedField.includes('ip') || normalizedField.includes('address')) {
          mapping[field] = 'ip';
        } else if (normalizedField.includes('port')) {
          mapping[field] = 'port';
        } else if (normalizedField.includes('program')) {
          mapping[field] = 'program_name';
        } else if (normalizedField.includes('service') || normalizedField.includes('name')) {
          mapping[field] = 'service';
        } else if (normalizedField.includes('protocol')) {
          mapping[field] = 'protocol';
        } else if (normalizedField.includes('banner')) {
          mapping[field] = 'banner';
        } else if (normalizedField.includes('product')) {
          mapping[field] = 'product';
        } else if (normalizedField.includes('version')) {
          mapping[field] = 'version';
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
      
      let servicesToImport = [];
      
      if (importFormat === 'txt') {
        servicesToImport = importPreview.map(item => ({
          ip: item.ip,
          port: item.port,
          program_name: selectedImportProgram || ''
        }));
      } else {
        // Apply field mapping for JSON/CSV
        servicesToImport = importPreview.map(item => {
          const mapped = {
            program_name: selectedImportProgram || ''
          };
          
          Object.entries(fieldMapping).forEach(([sourceField, targetField]) => {
            if (targetField && item[sourceField] !== undefined) {
              let value = item[sourceField];
              
              // Handle specific field transformations
              if (targetField === 'port' && typeof value === 'string') {
                value = parseInt(value) || value;
              }
              
              mapped[targetField] = value;
            }
          });
          
          return mapped;
        });
      }
      
      // Filter out items without IP and port
      servicesToImport = servicesToImport.filter(service => 
        service.ip && service.ip.trim() && service.port
      );
      
      if (servicesToImport.length === 0) {
        alert('No valid services found to import. Each service needs at least an IP address and port.');
        return;
      }
      
      // Batch import for large datasets
      const BATCH_SIZE = 100; // Adjust based on server limits
      const totalBatches = Math.ceil(servicesToImport.length / BATCH_SIZE);
      
      // Initialize progress
      setImportProgress({
        current: 0,
        total: servicesToImport.length,
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
        const end = Math.min(start + BATCH_SIZE, servicesToImport.length);
        const batch = servicesToImport.slice(start, end);
        
        // Update progress
        setImportProgress({
          current: start,
          total: servicesToImport.length,
          currentBatch: i + 1,
          totalBatches: totalBatches
        });
        
        try {
          const response = await serviceAPI.import(batch, {
            merge: importOptions.mergeData,
            update_existing: importOptions.updateExisting,
            validate_services: importOptions.validateServices
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
      message += `• ${totalImported} new services created\n`;
      message += `• ${totalUpdated} existing services updated\n`;
      message += `• ${totalSkipped} services skipped\n`;
      if (totalErrors > 0) {
        message += `• ${totalErrors} errors occurred\n`;
      }
      
      if (totalSkipped > 0 && !importOptions.updateExisting) {
        message += `\nTip: Enable "Update existing services" to merge new data with existing services.`;
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
      // Refresh the services list with current filters
      fetchServices(currentPage);
      
    } catch (err) {
      console.error('Error importing services:', err);
      alert('Failed to import services: ' + err.message);
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
      validateServices: true
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
          Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} services
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

  // Local text filter (apply on Enter/Apply button)
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
          <h1>⚙️ Services</h1>
        </Col>
      </Row>

      

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center ms-auto">
                <Badge bg="secondary" className="me-3">Total: {totalItems}</Badge>
                <Form.Check
                  type="switch"
                  id="uncommon-ports-only"
                  label="Uncommon ports only"
                  checked={uncommonPortsOnly}
                  onChange={(e) => { setUncommonPortsOnly(e.target.checked); setCurrentPage(1); }}
                  className="me-3"
                  title="Hide common ports (80, 443, 21, etc.); show 8080, 8443, etc."
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
                  <p className="mt-2">Loading services...</p>
                </div>
              ) : error ? (
                <div className="p-4">
                  <p className="text-danger">{error}</p>
                </div>
              ) : services.length === 0 ? (
                <div className="p-4 text-center">
                  <p className="text-muted">No services found matching the current filters.</p>
                </div>
              ) : (
                <Table hover responsive>
                  <thead>
                    <tr>
                      <th>
                        <Form.Check
                          type="checkbox"
                          checked={selectedItems.size === services.length && services.length > 0}
                          onChange={(e) => handleSelectAll(e.target.checked)}
                        />
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('ip')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>IP {getSortIcon('ip')}</span>
                          <ColumnFilterPopover id="filter-ip" ariaLabel="Filter by IP" isActive={!!ipFilter}>
                            <div>
                              <InlineTextFilter
                                label="Search IP"
                                placeholder="e.g., 192.168.1.1"
                                initialValue={ipFilter}
                                onApply={(val) => setIpFilter(val)}
                                onClear={() => setIpFilter('')}
                              />
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('port')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Port {getSortIcon('port')}</span>
                          <ColumnFilterPopover id="filter-port" ariaLabel="Filter by port" isActive={!!portFilter}>
                            <div>
                              <InlineTextFilter
                                label="Port (search)"
                                placeholder="e.g., 80 or 8080"
                                initialValue={portFilter}
                                onApply={(val) => setPortFilter(val)}
                                onClear={() => setPortFilter('')}
                              />
                              <div className="mt-3">
                                <Form.Group>
                                  <Form.Label className="mb-1">Port (exact)</Form.Label>
                                  <Form.Select value={portFilter} onChange={(e) => setPortFilter(e.target.value)}>
                                    <option value="">All Ports</option>
                                    {distinctPorts.map(port => (
                                      <option key={port} value={port}>{port}</option>
                                    ))}
                                  </Form.Select>
                                </Form.Group>
                                <div className="d-flex justify-content-end gap-2 mt-2">
                                  <Button size="sm" variant="secondary" onClick={() => setPortFilter('')}>Clear</Button>
                                  <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                </div>
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('service')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Service {getSortIcon('service')}</span>
                          <ColumnFilterPopover id="filter-service" ariaLabel="Filter by service" isActive={!!serviceTextFilter || !!serviceFilter}>
                            <div>
                              <InlineTextFilter
                                label="Service (text)"
                                placeholder="Search services by name..."
                                initialValue={serviceTextFilter}
                                onApply={(val) => setServiceTextFilter(val)}
                                onClear={() => setServiceTextFilter('')}
                              />
                              <div className="mt-3">
                                <Form.Group>
                                  <Form.Label className="mb-1">Service (exact)</Form.Label>
                                  <Form.Select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)}>
                                    <option value="">All Services</option>
                                    {distinctServiceNames.map(serviceName => (
                                      <option key={serviceName} value={serviceName}>{serviceName}</option>
                                    ))}
                                  </Form.Select>
                                </Form.Group>
                                <div className="d-flex justify-content-end gap-2 mt-2">
                                  <Button size="sm" variant="secondary" onClick={() => setServiceFilter('')}>Clear</Button>
                                  <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                </div>
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('protocol')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Protocol {getSortIcon('protocol')}</span>
                          <ColumnFilterPopover id="filter-protocol" ariaLabel="Filter by protocol" isActive={!!protocolFilter}>
                            <div>
                              <Form.Group>
                                <Form.Label className="mb-1">Protocol</Form.Label>
                                <Form.Select value={protocolFilter} onChange={(e) => setProtocolFilter(e.target.value)}>
                                  <option value="">All</option>
                                  <option value="tcp">TCP</option>
                                  <option value="udp">UDP</option>
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
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('banner')}
                      >
                        Banner {getSortIcon('banner')}
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('program_name')}
                      >
                        Program {getSortIcon('program_name')}
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
                    {services.map((service) => (
                      <tr key={service.id}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <Form.Check
                            type="checkbox"
                            checked={selectedItems.has(service.id)}
                            onChange={(e) => handleSelectItem(service.id, e.target.checked)}
                          />
                        </td>
                        <td 
                          onClick={() => handleServiceClick(service)} 
                          style={{ cursor: 'pointer' }}
                        >
                          <code>{service.ip?.split('/')[0]}</code>
                        </td>
                        <td 
                          onClick={() => handleServiceClick(service)} 
                          style={{ cursor: 'pointer' }}
                        >
                          <code>{service.port}</code>
                        </td>
                        <td>
                          {service.service_name ? (
                            <Badge bg="success">{service.service_name}</Badge>
                          ) : (
                            <span className="text-muted">Unknown</span>
                          )}
                        </td>
                        <td>
                          {service.protocol ? (
                            <Badge bg="info">{service.protocol.toUpperCase()}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {service.banner ? (
                            <span title={service.banner} style={{ maxWidth: '200px', display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {service.banner}
                            </span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {service.program_name ? (
                            <Badge bg="primary">{service.program_name}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td className="text-muted">
                          {formatDateLocal(service.updated_at)}
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
          <Modal.Title>Delete Services</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected service(s)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Service(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export Services</Modal.Title>
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
                label="Plain Text - IP:Port combinations only (one per line)"
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
                      label="IP Address"
                      checked={exportColumns.ip}
                      onChange={() => handleColumnToggle('ip')}
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
                      label="Service"
                      checked={exportColumns.service}
                      onChange={() => handleColumnToggle('service')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Protocol"
                      checked={exportColumns.protocol}
                      onChange={() => handleColumnToggle('protocol')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Banner"
                      checked={exportColumns.banner}
                      onChange={() => handleColumnToggle('banner')}
                      className="mb-2"
                    />
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="Product"
                      checked={exportColumns.product}
                      onChange={() => handleColumnToggle('product')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Version"
                      checked={exportColumns.version}
                      onChange={() => handleColumnToggle('version')}
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
                  Leave empty to use default filename: services_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total services to export: {totalItems} (based on current filters)
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
          <Modal.Title>Import Services</Modal.Title>
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
                  Supported formats: JSON, CSV, and Plain Text (IP:Port per line)
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
                      All imported services will be assigned to this program.
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>

              <Row className="mb-3">
                <Col>
                  <h6>Import Options</h6>
                  <Form.Check
                    type="switch"
                    id="update-existing-services"
                    label="Update existing services"
                    checked={importOptions.updateExisting}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, updateExisting: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block mb-2">
                    When enabled, existing services will be updated with new data. When disabled, existing services will be skipped.
                  </Form.Text>
                  
                  <Form.Check
                    type="switch"
                    id="merge-service-data"
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
                    id="validate-services"
                    label="Validate service data"
                    checked={importOptions.validateServices}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, validateServices: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block">
                    When enabled, validates that IP addresses and ports are properly formatted before import.
                  </Form.Text>
                </Col>
              </Row>

              {showFieldMapping && (
                <Row className="mb-3">
                  <Col>
                    <h6>Field Mapping</h6>
                    <p className="text-muted small">Map the columns from your file to service fields:</p>
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
                            <option value="ip">IP Address</option>
                            <option value="port">Port</option>
                            <option value="program_name">Program Name</option>
                            <option value="service">Service Name</option>
                            <option value="protocol">Protocol</option>
                            <option value="banner">Banner</option>
                            <option value="product">Product</option>
                            <option value="version">Version</option>
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
                              <>
                                <th>IP Address</th>
                                <th>Port</th>
                              </>
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
                                <>
                                  <td>{row.ip}</td>
                                  <td>{row.port}</td>
                                </>
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
                  `Importing batch ${importProgress.currentBatch}/${importProgress.totalBatches} (${importProgress.current}/${importProgress.total} services)...` :
                  'Importing...'
                }
              </>
            ) : (
              <>
                <i className="bi bi-upload"></i> Import {importPreview.length} Services
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default Services;