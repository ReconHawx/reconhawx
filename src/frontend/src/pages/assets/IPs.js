import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, Button, Spinner, Modal, OverlayTrigger, Popover } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { ipAPI, programAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function IPs() {
  usePageTitle(formatPageTitle('IPs'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [ips, setIps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [searchFilter, setSearchFilter] = useState('');
  const [exactMatchFilter, setExactMatchFilter] = useState('');
  const [hasPtrFilter, setHasPtrFilter] = useState('');
  const [ptrTextFilter, setPtrTextFilter] = useState('');
  const [serviceProviderFilter, setServiceProviderFilter] = useState('');
  const [serviceProviders, setServiceProviders] = useState([]);
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    ip_address: true,
    program_name: true,
    ptr_record: true,
    service_provider: true,
    country: true,
    city: true,
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
    updateExisting: true,  // Default to updating existing IPs
    mergeData: true,       // Default to merging data
    validateIPs: true      // Default to validating IP addresses
  });
  const [programs, setPrograms] = useState([]);
  const [selectedImportProgram, setSelectedImportProgram] = useState('');
  const [importProgress, setImportProgress] = useState({
    current: 0,
    total: 0,
    currentBatch: 0,
    totalBatches: 0
  });

  const fetchIps = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (exactMatchFilter) params.exact_match = exactMatchFilter;
      if (selectedProgram) params.program = selectedProgram;
      if (hasPtrFilter) params.has_ptr = hasPtrFilter === 'true';
      if (ptrTextFilter) params.ptr_contains = ptrTextFilter;

      // Handle service provider filter
      if (serviceProviderFilter === '__NO_PROVIDER__') {
        // Special case: filter for IPs WITHOUT service provider
        params.has_service_provider = false;
      } else if (serviceProviderFilter) {
        // Normal case: filter by specific service provider
        params.service_provider = serviceProviderFilter;
      }

      params.sort_by = sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = page;
      params.page_size = pageSize;
      const response = await ipAPI.searchIPs(params);
      setIps(response.items || []);
      setTotalPages(response.pagination?.total_pages || 1);
      setTotalItems(response.pagination?.total_items || 0);
      setError(null);
    } catch (err) {
      setError('Failed to fetch IPs: ' + err.message);
      setIps([]);
    } finally {
      setLoading(false);
    }
  }, [
    searchFilter,
    exactMatchFilter,
    selectedProgram,
    hasPtrFilter,
    ptrTextFilter,
    serviceProviderFilter,
    sortField,
    sortDirection,
    pageSize
  ]);

  const fetchServiceProviders = async () => {
    try {
      // Fetch a larger sample via typed endpoint to get distinct service providers
      const params = { page: 1, page_size: 1000, sort_by: 'service_provider', sort_dir: 'asc' };
      const response = await ipAPI.searchIPs(params);
      if (response.items) {
        const providers = [...new Set(response.items.map(ip => ip.service_provider).filter(Boolean))].sort();
        setServiceProviders(providers);
      }
    } catch (err) {
      console.error('Error fetching service providers:', err);
    }
  };

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
    if (searchFilter) params.set('search', searchFilter);
    if (exactMatchFilter) params.set('exact_match', exactMatchFilter);
    if (selectedProgram) params.set('program', selectedProgram);
    if (hasPtrFilter) params.set('has_ptr', hasPtrFilter);
    if (ptrTextFilter) params.set('ptr_contains', ptrTextFilter);
    if (serviceProviderFilter) params.set('service_provider', serviceProviderFilter);
    if (sortField) params.set('sort_by', sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [
    searchFilter,
    exactMatchFilter,
    selectedProgram,
    hasPtrFilter,
    ptrTextFilter,
    serviceProviderFilter,
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

    const urlHasPtr = urlParams.get('has_ptr');
    const normalizedHasPtr = urlHasPtr === null ? '' : (urlHasPtr === 'true' ? 'true' : (urlHasPtr === 'false' ? 'false' : urlHasPtr));
    if (normalizedHasPtr !== hasPtrFilter) setHasPtrFilter(normalizedHasPtr);

    const urlPtrText = urlParams.get('ptr_contains') || '';
    if (urlPtrText !== ptrTextFilter) setPtrTextFilter(urlPtrText);

    const urlProvider = urlParams.get('service_provider') || '';
    if (urlProvider !== serviceProviderFilter) setServiceProviderFilter(urlProvider);

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
    fetchIps(currentPage);
  }, [fetchIps, currentPage]);

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

  // Fetch service providers on component mount
  useEffect(() => {
    fetchServiceProviders();
  }, []);

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
    setSearchFilter('');
    setExactMatchFilter('');
    setHasPtrFilter('');
    setPtrTextFilter('');
    setServiceProviderFilter('');
    setCurrentPage(1);
    // URL will be updated by sync effect
  };

  const handleIpClick = (ip) => {
    navigate(`/assets/ips/details?id=${encodeURIComponent(ip.id || '')}`);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(ips.map(ip => ip.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (ipId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(ipId);
    } else {
      newSelected.delete(ipId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems).filter(id => id != null && id !== undefined);
      if (selectedIds.length === 0) {
        alert('No valid IP addresses selected for deletion');
        return;
      }
      await ipAPI.deleteBatch(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page with current filters
      fetchIps(currentPage);
    } catch (err) {
      console.error('Error deleting IPs:', err);
      alert('Failed to delete IPs: ' + (err.response?.data?.detail || err.message));
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
      if (hasPtrFilter) params.has_ptr = hasPtrFilter === 'true';
      if (ptrTextFilter) params.ptr_contains = ptrTextFilter;

      // Handle service provider filter
      if (serviceProviderFilter === '__NO_PROVIDER__') {
        // Special case: filter for IPs WITHOUT service provider
        params.has_service_provider = false;
      } else if (serviceProviderFilter) {
        // Normal case: filter by specific service provider
        params.service_provider = serviceProviderFilter;
      }

      params.sort_by = sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = 1;
      params.page_size = 10000;
      const response = await ipAPI.searchIPs(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - only IP addresses
        exportData = rawData.map(item => item.ip_address).join('\n');
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
        : `ips_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting IPs:', err);
      alert('Failed to export IPs: ' + err.message);
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
        // Plain text - one IP per line
        parsed = text.split('\n')
          .map(line => line.trim())
          .filter(line => line)
          .map(ip => ({ ip_address: ip }));
        detectedFormat = 'txt';
        fields = ['ip_address'];
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
        if (normalizedField.includes('ip') || normalizedField === 'address') {
          mapping[field] = 'ip_address';
        } else if (normalizedField.includes('program')) {
          mapping[field] = 'program_name';
        } else if (normalizedField.includes('ptr') || normalizedField.includes('hostname')) {
          mapping[field] = 'ptr_record';
        } else if (normalizedField.includes('provider') || normalizedField.includes('isp')) {
          mapping[field] = 'service_provider';
        } else if (normalizedField.includes('country')) {
          mapping[field] = 'country';
        } else if (normalizedField.includes('city')) {
          mapping[field] = 'city';
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
      
      let ipsToImport = [];
      
      if (importFormat === 'txt') {
        ipsToImport = importPreview.map(item => ({
          ip_address: item.ip_address,
          program_name: selectedImportProgram || ''
        }));
      } else {
        // Apply field mapping for JSON/CSV
        ipsToImport = importPreview.map(item => {
          const mapped = {
            program_name: selectedImportProgram || ''
          };
          
          Object.entries(fieldMapping).forEach(([sourceField, targetField]) => {
            if (targetField && item[sourceField] !== undefined) {
              let value = item[sourceField];
              
              // Handle specific field transformations
              if (targetField === 'ptr_record' && typeof value === 'string') {
                value = value.split(/[;,]/).map(ptr => ptr.trim()).filter(ptr => ptr);
              }
              
              mapped[targetField] = value;
            }
          });
          
          return mapped;
        });
      }
      
      // Filter out items without IP addresses
      ipsToImport = ipsToImport.filter(ip => ip.ip_address && ip.ip_address.trim());
      
      if (ipsToImport.length === 0) {
        alert('No valid IP addresses found to import');
        return;
      }
      
      // Batch import for large datasets
      const BATCH_SIZE = 100; // Adjust based on server limits
      const totalBatches = Math.ceil(ipsToImport.length / BATCH_SIZE);
      
      // Initialize progress
      setImportProgress({
        current: 0,
        total: ipsToImport.length,
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
        const end = Math.min(start + BATCH_SIZE, ipsToImport.length);
        const batch = ipsToImport.slice(start, end);
        
        // Update progress
        setImportProgress({
          current: start,
          total: ipsToImport.length,
          currentBatch: i + 1,
          totalBatches: totalBatches
        });
        
        try {
          const response = await ipAPI.import(batch, {
            merge: importOptions.mergeData,
            update_existing: importOptions.updateExisting,
            validate_ips: importOptions.validateIPs
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
      message += `• ${totalImported} new IP addresses created\n`;
      message += `• ${totalUpdated} existing IP addresses updated\n`;
      message += `• ${totalSkipped} IP addresses skipped\n`;
      if (totalErrors > 0) {
        message += `• ${totalErrors} errors occurred\n`;
      }
      
      if (totalSkipped > 0 && !importOptions.updateExisting) {
        message += `\nTip: Enable "Update existing IP addresses" to merge new data with existing IPs.`;
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
      // Refresh the IPs list with current filters
      const filter = {};
      if (searchFilter) {
        filter.ip_address = { $regex: searchFilter, $options: 'i' };
      }
      if (selectedProgram) {
        filter.program_name = selectedProgram;
      }
      if (hasPtrFilter) {
        if (hasPtrFilter === 'true') {
          filter.ptr_record = { $exists: true, $nin: [null, ""] };
        } else if (hasPtrFilter === 'false') {
          filter.$or = [
            { ptr_record: { $exists: false } },
            { ptr_record: null },
            { ptr_record: "" }
          ];
        }
      }
      if (ptrTextFilter) {
        filter.ptr_record = { $regex: ptrTextFilter, $options: 'i' };
      }
      if (serviceProviderFilter) {
        filter.service_provider = serviceProviderFilter;
      }
      // Refresh the current page with current filters
      fetchIps(currentPage);
      
    } catch (err) {
      console.error('Error importing IPs:', err);
      alert('Failed to import IP addresses: ' + err.message);
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
      validateIPs: true
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
          Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} IP addresses
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
          <h1>🖥️ IP Addresses</h1>
        </Col>
      </Row>

      

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center ms-auto">
                <Badge bg="secondary" className="me-3">Total: {totalItems}</Badge>
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
                  <p className="mt-2">Loading IP addresses...</p>
                </div>
              ) : error ? (
                <div className="p-4">
                  <p className="text-danger">{error}</p>
                </div>
              ) : ips.length === 0 ? (
                <div className="p-4 text-center">
                  <p className="text-muted">No IP addresses found matching the current filters.</p>
                </div>
              ) : (
                <Table hover responsive>
                  <thead>
                    <tr>
                      <th>
                        <Form.Check
                          type="checkbox"
                          checked={selectedItems.size === ips.length && ips.length > 0}
                          onChange={(e) => handleSelectAll(e.target.checked)}
                        />
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('ip_address')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>IP Address {getSortIcon('ip_address')}</span>
                          <ColumnFilterPopover id="filter-ip" ariaLabel="Filter by IP" isActive={!!searchFilter || !!exactMatchFilter}>
                            <div>
                              <InlineTextFilter
                                label="Search"
                                placeholder="e.g., 192.168, 10.0"
                                initialValue={searchFilter}
                                onApply={(val) => setSearchFilter(val)}
                                onClear={() => setSearchFilter('')}
                              />
                              <div className="mt-3">
                                <InlineTextFilter
                                  label="Exact match"
                                  placeholder="e.g., 192.168.1.1"
                                  initialValue={exactMatchFilter}
                                  onApply={(val) => setExactMatchFilter(val)}
                                  onClear={() => setExactMatchFilter('')}
                                />
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
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('ptr_record')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>PTR Records {getSortIcon('ptr_record')}</span>
                          <ColumnFilterPopover id="filter-ptr" ariaLabel="Filter by PTR" isActive={hasPtrFilter === 'true' || hasPtrFilter === 'false' || !!ptrTextFilter}>
                            <div>
                              <Form.Group className="mb-2">
                                <Form.Label className="mb-1">Has PTR</Form.Label>
                                <Form.Select value={hasPtrFilter} onChange={(e) => setHasPtrFilter(e.target.value)}>
                                  <option value="">All</option>
                                  <option value="true">Yes</option>
                                  <option value="false">No</option>
                                </Form.Select>
                              </Form.Group>
                              <InlineTextFilter
                                label="PTR contains"
                                placeholder="hostname.example"
                                initialValue={ptrTextFilter}
                                onApply={(val) => setPtrTextFilter(val)}
                                onClear={() => setPtrTextFilter('')}
                              />
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('service_provider')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Service Provider {getSortIcon('service_provider')}</span>
                          <ColumnFilterPopover id="filter-provider" ariaLabel="Filter by provider" isActive={!!serviceProviderFilter}>
                            <div>
                              <Form.Group>
                                <Form.Label className="mb-1">Service Provider</Form.Label>
                                <Form.Select value={serviceProviderFilter} onChange={(e) => setServiceProviderFilter(e.target.value)}>
                                  <option value="">All Providers</option>
                                  <option value="__NO_PROVIDER__">No Service Provider</option>
                                  {serviceProviders.map(provider => (
                                    <option key={provider} value={provider}>{provider}</option>
                                  ))}
                                </Form.Select>
                              </Form.Group>
                              <div className="d-flex justify-content-end gap-2 mt-2">
                                <Button size="sm" variant="secondary" onClick={() => setServiceProviderFilter('')}>Clear</Button>
                                <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
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
                    {ips.map((ip) => (
                      <tr key={ip.id}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <Form.Check
                            type="checkbox"
                            checked={selectedItems.has(ip.id)}
                            onChange={(e) => handleSelectItem(ip.id, e.target.checked)}
                          />
                        </td>
                        <td 
                          onClick={() => handleIpClick(ip)} 
                          style={{ cursor: 'pointer' }}
                        >
                          <code>{ip.ip_address}</code>
                        </td>
                        <td>
                          {ip.program_name ? (
                            <Badge bg="primary">{ip.program_name}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {ip.ptr_record ? (
                            <Badge bg="secondary">
                              {ip.ptr_record.length > 50 ? ip.ptr_record.substring(0, 50) + '...' : ip.ptr_record}
                            </Badge>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td>
                          {ip.service_provider ? (
                            <Badge bg="info">{ip.service_provider}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td className="text-muted">
                          {formatDateLocal(ip.updated_at)}
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
          <Modal.Title>Delete IP Addresses</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected IP address(es)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} IP Address(es)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export IP Addresses</Modal.Title>
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
                label="Plain Text - IP addresses only (one per line)"
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
                      checked={exportColumns.ip_address}
                      onChange={() => handleColumnToggle('ip_address')}
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
                      label="PTR Records"
                      checked={exportColumns.ptr_record}
                      onChange={() => handleColumnToggle('ptr_record')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Service Provider"
                      checked={exportColumns.service_provider}
                      onChange={() => handleColumnToggle('service_provider')}
                      className="mb-2"
                    />
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="Country"
                      checked={exportColumns.country}
                      onChange={() => handleColumnToggle('country')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="City"
                      checked={exportColumns.city}
                      onChange={() => handleColumnToggle('city')}
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
                  Leave empty to use default filename: ips_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total IP addresses to export: {totalItems} (based on current filters)
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
          <Modal.Title>Import IP Addresses</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Row className="mb-4">
            <Col>
              <h6>Select File</h6>
              <Form.Control
                type="file"
                accept=".json,.csv,.txt"
                onChange={handleFileSelect}
                className="mb-3"
              />
                <Form.Text className="text-muted">
                  Supported formats: JSON, CSV, and Plain Text (one IP address per line)
                </Form.Text>
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
                      All imported IP addresses will be assigned to this program.
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>

              <Row className="mb-3">
                <Col>
                  <h6>Import Options</h6>
                  <Form.Check
                    type="switch"
                    id="update-existing-ips"
                    label="Update existing IP addresses"
                    checked={importOptions.updateExisting}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, updateExisting: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block mb-2">
                    When enabled, existing IP addresses will be updated with new data. When disabled, existing IP addresses will be skipped.
                  </Form.Text>
                  
                  <Form.Check
                    type="switch"
                    id="merge-ip-data"
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
                    id="validate-ips"
                    label="Validate IP address format"
                    checked={importOptions.validateIPs}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, validateIPs: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block">
                    When enabled, validates that IP addresses are properly formatted before import.
                  </Form.Text>
                </Col>
              </Row>
            </>
          )}

              {showFieldMapping && (
                <Row className="mb-3">
                  <Col>
                    <h6>Field Mapping</h6>
                    <p className="text-muted small">Map the columns from your file to IP address fields:</p>
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
                            <option value="ip_address">IP Address</option>
                            <option value="program_name">Program Name</option>
                            <option value="ptr_record">PTR Records</option>
                            <option value="service_provider">Service Provider</option>
                            <option value="country">Country</option>
                            <option value="city">City</option>
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
                              <th>IP Address</th>
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
                                <td>{row.ip_address}</td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  </Col>
                </Row>
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
                  `Importing batch ${importProgress.currentBatch}/${importProgress.totalBatches} (${importProgress.current}/${importProgress.total} IP addresses)...` :
                  'Importing...'
                }
              </>
            ) : (
              <>
                <i className="bi bi-upload"></i> Import {importPreview.length} IP Addresses
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default IPs;