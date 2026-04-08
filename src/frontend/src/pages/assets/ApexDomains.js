import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, InputGroup, Button, Spinner, Alert, Accordion, Modal } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { apexDomainAPI, programAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function ApexDomains() {
  usePageTitle(formatPageTitle('Apex Domains'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [apexDomains, setApexDomains] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');

  const [searchFilter, setSearchFilter] = useState('');
  const [exactMatchFilter, setExactMatchFilter] = useState('');

  // Import/Export related state
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    name: true,
    program_name: true,
    cname: true,
    ip: true,
    whois_registrar: true,
    whois_creation_date: true,
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
    updateExisting: true,  // Default to updating existing apex domains
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

  // Batch delete related state
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);


  const fetchApexDomains = useCallback(async (page = 1, programName = null, sort = null) => {
    try {
      setLoading(true);
      
      // Map to typed params
      const actualSortField = sort ? sort.replace('-', '') : sortField;
      const sortDir = sort ? (sort.startsWith('-') ? 'desc' : 'asc') : (sortDirection === 'desc' ? 'desc' : 'asc');

      const params = {
        search: searchFilter || undefined,
        exact_match: exactMatchFilter || undefined,
        program: programName || undefined,
        sort_by: actualSortField,
        sort_dir: sortDir,
        page,
        page_size: pageSize,
      };

      // Prefer typed search endpoint
      const response = await apexDomainAPI.search(params);
      
      if (response.status === 'success' && response.items) {
        
        setApexDomains(response.items);
        setTotalPages(response.pagination?.total_pages || 1);
        setTotalItems(response.pagination?.total_items || 0);
        setError(null);
      } else {
        throw new Error('Failed to fetch apex domains');
      }
    } catch (err) {
      setError('Failed to fetch apex domains: ' + err.message);
      setApexDomains([]);
    } finally {
      setLoading(false);
    }
  }, [pageSize, sortField, sortDirection, searchFilter, exactMatchFilter]);

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
    if (sortField) params.set('sort_by', sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [searchFilter, exactMatchFilter, selectedProgram, sortField, sortDirection, currentPage, pageSize]);

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

    const urlSortBy = urlParams.get('sort_by');
    if (urlSortBy && urlSortBy !== sortField) setSortField(urlSortBy);

    const urlSortDir = urlParams.get('sort_dir');
    if (urlSortDir && (urlSortDir === 'asc' || urlSortDir === 'desc') && urlSortDir !== sortDirection) {
      setSortDirection(urlSortDir);
    }

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
    fetchApexDomains(currentPage, selectedProgram);
  }, [fetchApexDomains, currentPage, selectedProgram]);

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

  // Initialize selected import program when programs are loaded or selectedProgram changes
  useEffect(() => {
    if (programs.length > 0 && selectedProgram && programs.includes(selectedProgram)) {
      setSelectedImportProgram(selectedProgram);
    }
  }, [programs, selectedProgram]);

  // Note: Search filtering is done client-side since the API doesn't support it yet

  const clearFilters = () => {
    setSearchFilter('');
    setExactMatchFilter('');
    setSortField('name');
    setSortDirection('asc');
    setCurrentPage(1);
  };

  // Export functionality
  const handleExport = () => {
    setShowExportModal(true);
  };

  const handleExportConfirm = async () => {
    try {
      setExporting(true);
      
      // Build filter for the query
      // Build typed params
      const params = {
        program: selectedProgram || undefined,
        sort_by: sortField,
        sort_dir: sortDirection,
        page: 1,
        page_size: 10000,
      };
      
      // Fetch all results
      const response = await apexDomainAPI.search(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - only apex domain names
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
            } else if (typeof value === 'object' && value !== null) {
              value = JSON.stringify(value);
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
        : `apex_domains_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting apex domains:', err);
      alert('Failed to export apex domains: ' + err.message);
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
        // Plain text - one apex domain per line
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
      // Available fields for apex domains: ['name', 'program_name', 'cname', 'ip', 'whois_data']
      
      fields.forEach(field => {
        // Auto-map common field names
        const normalizedField = field.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (normalizedField.includes('domain') || normalizedField === 'name') {
          mapping[field] = 'name';
        } else if (normalizedField.includes('program')) {
          mapping[field] = 'program_name';
        } else if (normalizedField.includes('cname')) {
          mapping[field] = 'cname';
        } else if (normalizedField.includes('ip')) {
          mapping[field] = 'ip';
        } else if (normalizedField.includes('whois')) {
          mapping[field] = 'whois_data';
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
      
      let apexDomainsToImport = [];
      
      if (importFormat === 'txt') {
        apexDomainsToImport = importPreview.map(item => ({
          name: item.name,
          program_name: selectedImportProgram || ''
        }));
      } else {
        // Apply field mapping for JSON/CSV
        apexDomainsToImport = importPreview.map(item => {
          const mapped = {
            program_name: selectedImportProgram || ''
          };
          
          Object.entries(fieldMapping).forEach(([sourceField, targetField]) => {
            if (targetField && item[sourceField] !== undefined) {
              let value = item[sourceField];
              
              // Handle specific field transformations
              if (targetField === 'ip') {
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
              } else if (targetField === 'whois_data' && typeof value === 'string') {
                try {
                  value = JSON.parse(value);
                } catch {
                  // If it's not valid JSON, keep as string
                }
              }
              
              mapped[targetField] = value;
            }
          });
          
          return mapped;
        });
      }
      
      // Filter out items without apex domain names
      apexDomainsToImport = apexDomainsToImport.filter(domain => domain.name && domain.name.trim());
      
      if (apexDomainsToImport.length === 0) {
        alert('No valid apex domains found to import');
        return;
      }
      
      // Batch import for large datasets
      const BATCH_SIZE = 100; // Adjust based on server limits
      const totalBatches = Math.ceil(apexDomainsToImport.length / BATCH_SIZE);
      
      // Initialize progress
      setImportProgress(prev => ({
        ...prev,
        current: 0,
        total: apexDomainsToImport.length,
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
        const end = Math.min(start + BATCH_SIZE, apexDomainsToImport.length);
        const batch = apexDomainsToImport.slice(start, end);
        
        // Update progress
        setImportProgress(prev => ({
          ...prev,
          current: start,
          total: apexDomainsToImport.length,
          currentBatch: i + 1,
          totalBatches: totalBatches
        }));
        
        // Small delay to ensure UI updates
        await new Promise(resolve => setTimeout(resolve, 10));
        
        try {
          const response = await apexDomainAPI.import(batch, {
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
      message += `• ${totalImported} new apex domains created\n`;
      message += `• ${totalUpdated} existing apex domains updated\n`;
      message += `• ${totalSkipped} apex domains skipped\n`;
      if (totalErrors > 0) {
        message += `• ${totalErrors} errors occurred\n`;
      }
      
      if (totalSkipped > 0 && !importOptions.updateExisting) {
        message += `\nTip: Enable "Update existing apex domains" to merge new data with existing apex domains.`;
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
      // Refresh the apex domains list with current filters
      fetchApexDomains(currentPage, selectedProgram);
      
    } catch (err) {
      console.error('Error importing apex domains:', err);
      alert('Failed to import apex domains: ' + err.message);
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

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(apexDomains.map(apexDomain => apexDomain.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (apexDomainId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(apexDomainId);
    } else {
      newSelected.delete(apexDomainId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems).filter(id => id != null && id !== undefined);
      if (selectedIds.length === 0) {
        console.error('No valid apex domains selected for deletion');
        return;
      }
      // Always delete subdomains when deleting apex domains
      await apexDomainAPI.deleteBatch(selectedIds, { deleteSubdomains: true });
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      
      // Refresh the current page with current filters
      fetchApexDomains(currentPage, selectedProgram);
    } catch (err) {
      console.error('Error deleting apex domains:', err);
      console.error('Failed to delete apex domains:', err.response?.data?.detail || err.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleApexDomainClick = (apexDomain) => {
    navigate(`/assets/apex-domain/details?id=${encodeURIComponent(apexDomain.id || '')}`);
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
          Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} apex domains
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

  // Filter apex domains based on search
  const filteredApexDomains = apexDomains.filter(domain => {
    if (!searchFilter) return true;
    const searchLower = searchFilter.toLowerCase();
    return (
      domain.name?.toLowerCase().includes(searchLower) ||
      domain.program_name?.toLowerCase().includes(searchLower) ||
      domain.cname?.toLowerCase().includes(searchLower)
    );
  });

  return (
    <Container fluid className="p-4">
      <Row className="mb-3">
        <Col>
          <h2>🌐 Apex Domains</h2>
          <p className="text-muted">
            Apex domains are the root domains stored as separate assets. This view shows apex domains with their WHOIS information and program associations.
          </p>
        </Col>
      </Row>

      <Accordion className="mb-3">
        <Accordion.Item eventKey="0">
          <Accordion.Header>🔍 Search & Filter Options</Accordion.Header>
          <Accordion.Body>
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Search Apex Domains</Form.Label>
                  <InputGroup>
                    <Form.Control
                      type="text"
                      placeholder="Search by domain name, program, or CNAME..."
                      value={searchFilter}
                      onChange={(e) => setSearchFilter(e.target.value)}
                    />
                  </InputGroup>
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Label>Exact Match</Form.Label>
                  <InputGroup>
                    <Form.Control
                      type="text"
                      placeholder="Exact domain name match..."
                      value={exactMatchFilter}
                      onChange={(e) => setExactMatchFilter(e.target.value)}
                    />
                  </InputGroup>
                  <Form.Text className="text-muted">
                    Use exact match for precise domain name searches
                  </Form.Text>
                </Form.Group>
              </Col>
              <Col md={12} className="d-flex justify-content-end">
                <Button variant="outline-secondary" onClick={clearFilters}>
                  Clear
                </Button>
              </Col>
            </Row>
          </Accordion.Body>
        </Accordion.Item>
      </Accordion>

      {/* Results */}
      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center ms-auto">
                <Badge bg="secondary" className="me-3">Total: {totalItems}</Badge>
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
                <Alert variant="danger" className="m-3">
                  {error}
                </Alert>
              ) : filteredApexDomains.length === 0 ? (
                <div className="text-center p-4">
                  <p className="text-muted">No apex domains found.</p>
                </div>
              ) : (
                <Table responsive hover className="mb-0">
                  <thead>
                    <tr>
                      <th>
                        <Form.Check
                          type="checkbox"
                          checked={selectedItems.size === apexDomains.length && apexDomains.length > 0}
                          onChange={(e) => handleSelectAll(e.target.checked)}
                        />
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('name')}
                      >
                        Domain Name {getSortIcon('name')}
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('program_name')}
                      >
                        Program {getSortIcon('program_name')}
                      </th>
                      <th>Registrar</th>
                      <th>Registration date</th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('updated_at')}
                      >
                        Last Updated {getSortIcon('updated_at')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredApexDomains.map((domain, index) => (
                      <tr 
                        key={`${domain.name}-${index}`}
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleApexDomainClick(domain)}
                        className="hover-highlight"
                      >
                        <td onClick={(e) => e.stopPropagation()}>
                          <Form.Check
                            type="checkbox"
                            checked={selectedItems.has(domain.id)}
                            onChange={(e) => handleSelectItem(domain.id, e.target.checked)}
                          />
                        </td>
                        <td>
                          <strong>{domain.name}</strong>
                        </td>
                        <td>
                          {domain.program_name ? (
                            <Badge bg="primary">{domain.program_name}</Badge>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {(domain.whois_registrar || domain.whois_data?.registrar) ? (
                            <span
                              className="text-truncate d-inline-block"
                              style={{ maxWidth: '200px' }}
                              title={domain.whois_registrar || domain.whois_data?.registrar}
                            >
                              {domain.whois_registrar || domain.whois_data?.registrar}
                            </span>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {(domain.whois_creation_date || domain.whois_data?.creation_date) ? (
                            <span>
                              {formatDate(
                                domain.whois_creation_date || domain.whois_data?.creation_date,
                                'MMM dd, yyyy'
                              )}
                            </span>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {formatDateLocal(domain.updated_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Pagination */}
      {!loading && !error && filteredApexDomains.length > 0 && (
        <Row className="mt-3">
          <Col>
            {renderPagination()}
          </Col>
        </Row>
      )}

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Apex Domains</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected apex domain(s)?</p>
          
          <Alert variant="warning">
            <i className="bi bi-exclamation-triangle"></i>
            <strong>Warning:</strong> This action cannot be undone.
          </Alert>
          
          <Alert variant="danger" className="mt-3">
            <i className="bi bi-exclamation-triangle-fill"></i>
            <strong>Critical:</strong> Deleting apex domains will also automatically remove ALL associated subdomains and their related assets:
            <ul className="mb-0 mt-2">
              <li>All subdomains under these apex domains</li>
              <li>IP addresses linked to those subdomains</li>
              <li>URLs associated with those subdomains</li>
              <li>Services running on those subdomains</li>
              <li>Certificates for those subdomains</li>
            </ul>
            <p className="mb-0 mt-2"><strong>This is a destructive operation that will permanently remove all related data!</strong></p>
          </Alert>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => {
            setShowDeleteModal(false);
          }}>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Apex Domain(s) + All Subdomains
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export Apex Domains</Modal.Title>
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
                label="Plain Text - Apex domain names only (one per line)"
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
                      label="Apex Domain Name"
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
                      label="CNAME Record"
                      checked={exportColumns.cname}
                      onChange={() => handleColumnToggle('cname')}
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
                      label="WHOIS registrar"
                      checked={exportColumns.whois_registrar}
                      onChange={() => handleColumnToggle('whois_registrar')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="WHOIS creation date"
                      checked={exportColumns.whois_creation_date}
                      onChange={() => handleColumnToggle('whois_creation_date')}
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
                  Leave empty to use default filename: apex_domains_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total apex domains to export: {totalItems} (based on current filters)
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
          <Modal.Title>Import Apex Domains</Modal.Title>
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
                  Supported formats: JSON, CSV, and Plain Text (one apex domain per line)
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
                      All imported apex domains will be assigned to this program.
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>

              <Row className="mb-3">
                <Col>
                  <h6>Import Options</h6>
                  <Form.Check
                    type="switch"
                    id="update-existing-apex-domains"
                    label="Update existing apex domains"
                    checked={importOptions.updateExisting}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, updateExisting: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block mb-2">
                    When enabled, existing apex domains will be updated with new data. When disabled, existing apex domains will be skipped.
                  </Form.Text>
                  
                  <Form.Check
                    type="switch"
                    id="merge-apex-domain-data"
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
                    id="validate-apex-domains"
                    label="Validate apex domain names"
                    checked={importOptions.validateDomains}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, validateDomains: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block">
                    When enabled, validates that apex domain names are properly formatted before import.
                  </Form.Text>
                </Col>
              </Row>

              {showFieldMapping && (
                <Row className="mb-3">
                  <Col>
                    <h6>Field Mapping</h6>
                    <p className="text-muted small">Map the columns from your file to apex domain fields:</p>
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
                            <option value="name">Apex Domain Name</option>
                            <option value="program_name">Program Name</option>
                            <option value="cname">CNAME Record</option>
                            <option value="ip">IP Addresses</option>
                            <option value="whois_data">WHOIS Data</option>
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
                              <th>Apex Domain Name</th>
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
                  `Importing batch ${importProgress.currentBatch}/${importProgress.totalBatches} (${importProgress.current}/${importProgress.total} apex domains)...` :
                  'Importing...'
                }
              </>
            ) : (
              <>
                <i className="bi bi-upload"></i> Import {importPreview.length} Apex Domains
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default ApexDomains; 