import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, Button, Spinner, Modal, OverlayTrigger, Popover } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { certificateAPI, programAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function Certificates() {
  usePageTitle(formatPageTitle('Certificates'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [certificates, setCertificates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [searchFilter, setSearchFilter] = useState('');
  const [exactMatchFilter, setExactMatchFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [tlsVersionFilter, setTlsVersionFilter] = useState('');
  const [issuerOrgFilter, setIssuerOrgFilter] = useState('');
  const [cipherFilter, setCipherFilter] = useState('');
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    subject_dn: true,
    issuer_dn: true,
    subject_alternative_names: true,
    not_valid_before: true,
    valid_until: true,
    tls_version: true,
    cipher: true,
    issuer_organization: true,
    serial_number: true,
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
    updateExisting: true,       // Default to updating existing certificates
    mergeData: true,           // Default to merging data
    validateCertificates: true // Default to validating certificate data
  });
  const [programs, setPrograms] = useState([]);
  const [selectedImportProgram, setSelectedImportProgram] = useState('');
  const [issuerOrganizations, setIssuerOrganizations] = useState([]);
  const [importProgress, setImportProgress] = useState({
    current: 0,
    total: 0,
    currentBatch: 0,
    totalBatches: 0
  });

  const fetchCertificates = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (exactMatchFilter) params.exact_match = exactMatchFilter;
      if (selectedProgram) params.program = selectedProgram;
      if (statusFilter) {
        if (statusFilter === 'expired') params.status = 'expired';
        else if (statusFilter === 'valid') params.status = 'valid';
        else if (statusFilter === 'expiring_soon') params.status = 'expiring_soon';
      }
      if (tlsVersionFilter) params.tls_version = tlsVersionFilter;
      if (issuerOrgFilter) params.issuer_organization = issuerOrgFilter;
      if (cipherFilter) params.cipher = cipherFilter;
      params.sort_by = sortField === 'subject_alternative_names' ? 'san_count' : sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = page;
      params.page_size = pageSize;
      const response = await certificateAPI.searchCertificates(params);
      setCertificates(response.items || []);
      setTotalPages(response.pagination?.total_pages || 1);
      setTotalItems(response.pagination?.total_items || 0);
      setError(null);
    } catch (err) {
      setError('Failed to fetch certificates: ' + err.message);
      setCertificates([]);
    } finally {
      setLoading(false);
    }
  }, [
    searchFilter,
    exactMatchFilter,
    selectedProgram,
    statusFilter,
    tlsVersionFilter,
    issuerOrgFilter,
    cipherFilter,
    sortField,
    sortDirection,
    pageSize
  ]);

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

  // Column filter popover utilities
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
    if (selectedProgram) params.set('program', selectedProgram);
    if (statusFilter) params.set('status', statusFilter);
    if (tlsVersionFilter) params.set('tls_version', tlsVersionFilter);
    if (issuerOrgFilter) params.set('issuer_organization', issuerOrgFilter);
    if (cipherFilter) params.set('cipher', cipherFilter);
    if (sortField) params.set('sort_by', sortField === 'subject_alternative_names' ? 'san_count' : sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [
    searchFilter,
    selectedProgram,
    statusFilter,
    tlsVersionFilter,
    issuerOrgFilter,
    cipherFilter,
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

    const urlProgram = urlParams.get('program') || '';
    if (urlProgram && urlProgram !== selectedProgram) setSelectedProgram(urlProgram);

    const urlStatus = urlParams.get('status') || '';
    if (urlStatus !== statusFilter) setStatusFilter(urlStatus);

    const urlTlsVersion = urlParams.get('tls_version') || '';
    if (urlTlsVersion !== tlsVersionFilter) setTlsVersionFilter(urlTlsVersion);

    const urlIssuerOrg = urlParams.get('issuer_organization') || '';
    if (urlIssuerOrg !== issuerOrgFilter) setIssuerOrgFilter(urlIssuerOrg);

    const urlCipher = urlParams.get('cipher') || '';
    if (urlCipher !== cipherFilter) setCipherFilter(urlCipher);

    const urlSortBy = urlParams.get('sort_by');
    if (urlSortBy) {
      const mapped = urlSortBy === 'san_count' ? 'subject_alternative_names' : urlSortBy;
      if (mapped !== sortField) setSortField(mapped);
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
    fetchCertificates(currentPage);
  }, [fetchCertificates, currentPage]);

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

  // Fetch distinct dropdown values when program changes
  useEffect(() => {
    const fetchDistincts = async () => {
      try {
        const issuerResp = await certificateAPI.getDistinctValues('issuer_organization', selectedProgram || undefined);
        if (Array.isArray(issuerResp)) setIssuerOrganizations(issuerResp.filter(Boolean).sort());
      } catch (e) {
        // Fail silently to keep UI responsive
        setIssuerOrganizations([]);
      }
    };
    fetchDistincts();
  }, [selectedProgram]);

  // Initialize selected import program when programs are loaded or selectedProgram changes
  useEffect(() => {
    if (programs.length > 0 && selectedProgram && programs.includes(selectedProgram)) {
      setSelectedImportProgram(selectedProgram);
    }
  }, [programs, selectedProgram]);

  const clearFilters = () => {
    setSearchFilter('');
    setExactMatchFilter('');
    setStatusFilter('');
    setTlsVersionFilter('');
    setIssuerOrgFilter('');
    setCipherFilter('');
    setCurrentPage(1);
    // URL will be updated by sync effect
  };

  const handleCertificateClick = (certificate) => {
    navigate(`/assets/certificates/details?id=${encodeURIComponent(certificate.id || '')}`);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(certificates.map(cert => cert.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (certId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(certId);
    } else {
      newSelected.delete(certId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems);
      await certificateAPI.deleteBatch(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page with current filters
      fetchCertificates(currentPage);
    } catch (err) {
      console.error('Error deleting certificates:', err);
      alert('Failed to delete certificates: ' + (err.response?.data?.detail || err.message));
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
      
      // Fetch all results via typed endpoint
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (selectedProgram) params.program = selectedProgram;
      if (statusFilter) {
        if (statusFilter === 'expired') params.status = 'expired';
        else if (statusFilter === 'valid') params.status = 'valid';
        else if (statusFilter === 'expiring_soon') params.status = 'expiring_soon';
      }
      if (tlsVersionFilter) params.tls_version = tlsVersionFilter;
      if (issuerOrgFilter) params.issuer_organization = issuerOrgFilter;
      if (cipherFilter) params.cipher = cipherFilter;
      params.sort_by = sortField === 'subject_alternative_names' ? 'san_count' : sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = 1;
      params.page_size = 10000;
      const response = await certificateAPI.searchCertificates(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - only subject DN
        exportData = rawData.map(item => item.subject_dn).join('\n');
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
        : `certificates_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting certificates:', err);
      alert('Failed to export certificates: ' + err.message);
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
        // Plain text - one subject DN per line
        parsed = text.split('\n')
          .map(line => line.trim())
          .filter(line => line)
          .map(subjectDn => ({ subject_dn: subjectDn }));
        detectedFormat = 'txt';
        fields = ['subject_dn'];
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
        if (normalizedField.includes('subject') && normalizedField.includes('dn')) {
          mapping[field] = 'subject_dn';
        } else if (normalizedField.includes('issuer') && normalizedField.includes('dn')) {
          mapping[field] = 'issuer_dn';
        } else if (normalizedField.includes('subject') && normalizedField.includes('an')) {
          mapping[field] = 'subject_alternative_names';
        } else if (normalizedField.includes('program')) {
          mapping[field] = 'program_name';
        } else if (normalizedField.includes('serial')) {
          mapping[field] = 'serial_number';
        } else if (normalizedField.includes('notvalidbefore') || normalizedField.includes('valid_before')) {
          mapping[field] = 'not_valid_before';
        } else if (normalizedField.includes('notvalidafter') || normalizedField.includes('valid_after')) {
          mapping[field] = 'valid_until';
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
      
      let certificatesToImport = [];
      
      if (importFormat === 'txt') {
        certificatesToImport = importPreview.map(item => ({
          subject_dn: item.subject_dn,
          program_name: selectedImportProgram || ''
        }));
      } else {
        // Apply field mapping for JSON/CSV
        certificatesToImport = importPreview.map(item => {
          const mapped = {
            program_name: selectedImportProgram || ''
          };
          
          Object.entries(fieldMapping).forEach(([sourceField, targetField]) => {
            if (targetField && item[sourceField] !== undefined) {
              let value = item[sourceField];
              
              // Handle specific field transformations
              if ((targetField === 'not_valid_before' || targetField === 'valid_until') && typeof value === 'string') {
                // Try to parse as date
                try {
                  const parsedDate = new Date(value);
                  if (!isNaN(parsedDate.getTime())) {
                    value = parsedDate.toISOString();
                  }
                } catch (e) {
                  // Keep original value if parsing fails
                }
              }
              
              mapped[targetField] = value;
            }
          });
          
          return mapped;
        });
      }
      
      // Filter out items without subject_dn
      certificatesToImport = certificatesToImport.filter(cert => 
        cert.subject_dn && cert.subject_dn.trim()
      );
      
      if (certificatesToImport.length === 0) {
        alert('No valid certificates found to import. Each certificate needs at least a subject DN.');
        return;
      }
      
      // Batch import for large datasets
      const BATCH_SIZE = 100; // Adjust based on server limits
      const totalBatches = Math.ceil(certificatesToImport.length / BATCH_SIZE);
      
      // Initialize progress
      setImportProgress({
        current: 0,
        total: certificatesToImport.length,
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
        const end = Math.min(start + BATCH_SIZE, certificatesToImport.length);
        const batch = certificatesToImport.slice(start, end);
        
        // Update progress
        setImportProgress({
          current: start,
          total: certificatesToImport.length,
          currentBatch: i + 1,
          totalBatches: totalBatches
        });
        
        try {
          const response = await certificateAPI.import(batch, {
            merge: importOptions.mergeData,
            update_existing: importOptions.updateExisting,
            validate_certificates: importOptions.validateCertificates
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
      message += `• ${totalImported} new certificates created\n`;
      message += `• ${totalUpdated} existing certificates updated\n`;
      message += `• ${totalSkipped} certificates skipped\n`;
      if (totalErrors > 0) {
        message += `• ${totalErrors} errors occurred\n`;
      }
      
      if (totalSkipped > 0 && !importOptions.updateExisting) {
        message += `\nTip: Enable "Update existing certificates" to merge new data with existing certificates.`;
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
      // Refresh the certificates list with current filters
      const filter = {};
      if (searchFilter) {
        filter.$or = [
          { subject_dn: { $regex: searchFilter, $options: 'i' } },
          { issuer_dn: { $regex: searchFilter, $options: 'i' } },
          { subject_alternative_names: { $regex: searchFilter, $options: 'i' } }
        ];
      }
      if (selectedProgram) {
        filter.program_name = selectedProgram;
      }
      if (statusFilter === 'expired') {
        filter.valid_until = { $lt: new Date().toISOString() };
      } else if (statusFilter === 'valid') {
        filter.valid_until = { $gte: new Date().toISOString() };
      } else if (statusFilter === 'expiring_soon') {
        const thirtyDaysFromNow = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
        filter.$and = [
          { valid_until: { $gte: new Date().toISOString() } },
          { valid_until: { $lt: thirtyDaysFromNow } }
        ];
      }
      const sort = { [sortField]: sortDirection === 'asc' ? 1 : -1 };
      fetchCertificates(currentPage, filter, sort);
      
    } catch (err) {
      console.error('Error importing certificates:', err);
      alert('Failed to import certificates: ' + err.message);
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
      validateCertificates: true
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

  const formatCertDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      return formatDate(dateString, 'MMM dd, yyyy');
    } catch (e) {
      return dateString;
    }
  };

  const isExpired = (expiryDate) => {
    if (!expiryDate) return false;
    return new Date(expiryDate) < new Date();
  };

  const isExpiringSoon = (expiryDate) => {
    if (!expiryDate) return false;
    const expiry = new Date(expiryDate);
    const now = new Date();
    const thirtyDaysFromNow = new Date(now.getTime() + (30 * 24 * 60 * 60 * 1000));
    return expiry < thirtyDaysFromNow && expiry > now;
  };

  const getCertificateStatusBadge = (cert) => {
    if (isExpired(cert.valid_until)) {
      return <Badge bg="danger">Expired</Badge>;
    } else if (isExpiringSoon(cert.valid_until)) {
      return <Badge bg="warning">Expires Soon</Badge>;
    } else {
      return <Badge bg="success">Valid</Badge>;
    }
  };

  const truncateText = (text, maxLength = 50) => {
    if (!text) return '-';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
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
          Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} certificates
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

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <h1>🔐 Certificates</h1>
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
                  <p className="mt-2">Loading certificates...</p>
                </div>
              ) : error ? (
                <div className="p-4">
                  <p className="text-danger">{error}</p>
                </div>
              ) : certificates.length === 0 ? (
                <div className="p-4 text-center">
                  <p className="text-muted">No certificates found matching the current filters.</p>
                </div>
              ) : (
                <Table hover responsive>
                  <thead>
                    <tr>
                      <th>
                        <Form.Check
                          type="checkbox"
                          checked={selectedItems.size === certificates.length && certificates.length > 0}
                          onChange={(e) => handleSelectAll(e.target.checked)}
                        />
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('subject_dn')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Subject DN {getSortIcon('subject_dn')}</span>
                          <ColumnFilterPopover id="filter-subject" ariaLabel="Filter by subject" isActive={!!searchFilter}>
                            <InlineTextFilter
                              label="Search"
                              placeholder="Subject DN, Issuer, or SAN"
                              initialValue={searchFilter}
                              onApply={(val) => setSearchFilter(val)}
                              onClear={() => setSearchFilter('')}
                            />
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('valid_until')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Status {getSortIcon('valid_until')}</span>
                          <ColumnFilterPopover id="filter-status" ariaLabel="Filter by status" isActive={!!statusFilter}>
                            <div>
                              <Form.Group>
                                <Form.Label className="mb-1">Status</Form.Label>
                                <Form.Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                                  <option value="">All</option>
                                  <option value="valid">Valid</option>
                                  <option value="expiring_soon">Expiring Soon</option>
                                  <option value="expired">Expired</option>
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
                      {/* <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('tls_version')}
                      >
                        TLS Version {getSortIcon('tls_version')}
                      </th> */}
                      {/* <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('cipher')}
                      >
                        Cipher {getSortIcon('cipher')}
                      </th> */}
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('issuer_organization')}>
                        <div className="d-flex align-items-center gap-2">
                          <span>Issuer Organization {getSortIcon('issuer_organization')}</span>
                          <ColumnFilterPopover id="filter-issuer" ariaLabel="Filter by issuer" isActive={!!issuerOrgFilter}>
                            <div>
                              <Form.Group>
                                <Form.Label className="mb-1">Issuer Organization</Form.Label>
                                <Form.Select value={issuerOrgFilter} onChange={(e) => setIssuerOrgFilter(e.target.value)}>
                                  <option value="">All</option>
                                  {issuerOrganizations.map(org => (
                                    <option key={org} value={org}>{org}</option>
                                  ))}
                                </Form.Select>
                              </Form.Group>
                              <div className="d-flex justify-content-end gap-2 mt-2">
                                <Button size="sm" variant="secondary" onClick={() => setIssuerOrgFilter('')}>Clear</Button>
                                <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                              </div>
                            </div>
                          </ColumnFilterPopover>
                        </div>
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('valid_until')}
                      >
                        Valid Until {getSortIcon('valid_until')}
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('program_name')}
                      >
                        Program {getSortIcon('program_name')}
                      </th>
                      <th 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('subject_alternative_names')}
                      >
                        SAN Count {getSortIcon('subject_alternative_names')}
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
                    {certificates.map((cert) => (
                      <tr key={cert.id}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <Form.Check
                            type="checkbox"
                            checked={selectedItems.has(cert.id)}
                            onChange={(e) => handleSelectItem(cert.id, e.target.checked)}
                          />
                        </td>
                        <td 
                          onClick={() => handleCertificateClick(cert)} 
                          style={{ cursor: 'pointer' }}
                        >
                          <span title={cert.subject_dn} className="text-break">
                            {truncateText(cert.subject_dn, 60)}
                          </span>
                        </td>
                        <td>
                          {getCertificateStatusBadge(cert)}
                        </td>
                        {/* <td>
                          {cert.tls_version ? (
                            <Badge bg="primary">{cert.tls_version}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {cert.cipher ? (
                            <Badge bg="primary">{cert.cipher}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td> */}
                        <td>
                          {cert.issuer_organization ? (
                            <Badge bg="primary">{cert.issuer_organization}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          <span className={isExpired(cert.valid_until) ? 'text-danger' : 
                                         isExpiringSoon(cert.valid_until) ? 'text-warning' : ''}>
                            {formatCertDate(cert.valid_until)}
                          </span>
                        </td>
                        <td>
                          {cert.program_name ? (
                            <Badge bg="primary">{cert.program_name}</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          <Badge bg="info">
                            {cert.subject_alternative_names ? cert.subject_alternative_names.length : 0}
                          </Badge>
                        </td>
                        <td className="text-muted">
                          {formatDateLocal(cert.updated_at)}
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
          <Modal.Title>Delete Certificates</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected certificate(s)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Certificate(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export Certificates</Modal.Title>
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
                label="Plain Text - Subject DN only (one per line)"
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
                      label="Subject DN"
                      checked={exportColumns.subject_dn}
                      onChange={() => handleColumnToggle('subject_dn')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Issuer DN"
                      checked={exportColumns.issuer_dn}
                      onChange={() => handleColumnToggle('issuer_dn')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Subject Alternative Names"
                      checked={exportColumns.subject_alternative_names}
                      onChange={() => handleColumnToggle('subject_alternative_names')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Valid From"
                      checked={exportColumns.not_valid_before}
                      onChange={() => handleColumnToggle('not_valid_before')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Valid Until"
                      checked={exportColumns.valid_until}
                      onChange={() => handleColumnToggle('valid_until')}
                      className="mb-2"
                    />
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="Serial Number"
                      checked={exportColumns.serial_number}
                      onChange={() => handleColumnToggle('serial_number')}
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
                  Leave empty to use default filename: certificates_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total certificates to export: {totalItems} (based on current filters)
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
          <Modal.Title>Import Certificates</Modal.Title>
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
                  Supported formats: JSON, CSV, and Plain Text (one subject DN per line)
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
                      All imported certificates will be assigned to this program.
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>

              <Row className="mb-3">
                <Col>
                  <h6>Import Options</h6>
                  <Form.Check
                    type="switch"
                    id="update-existing-certificates"
                    label="Update existing certificates"
                    checked={importOptions.updateExisting}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, updateExisting: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block mb-2">
                    When enabled, existing certificates will be updated with new data. When disabled, existing certificates will be skipped.
                  </Form.Text>
                  
                  <Form.Check
                    type="switch"
                    id="merge-certificate-data"
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
                    id="validate-certificates"
                    label="Validate certificate data"
                    checked={importOptions.validateCertificates}
                    onChange={(e) => setImportOptions(prev => ({ ...prev, validateCertificates: e.target.checked }))}
                    className="mb-2"
                  />
                  <Form.Text className="text-muted d-block">
                    When enabled, validates that certificate data is properly formatted before import.
                  </Form.Text>
                </Col>
              </Row>

              {showFieldMapping && (
                <Row className="mb-3">
                  <Col>
                    <h6>Field Mapping</h6>
                    <p className="text-muted small">Map the columns from your file to certificate fields:</p>
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
                            <option value="subject_dn">Subject DN</option>
                            <option value="issuer_dn">Issuer DN</option>
                            <option value="subject_alternative_names">Subject Alternative Names</option>
                            <option value="program_name">Program Name</option>
                            <option value="serial_number">Serial Number</option>
                            <option value="not_valid_before">Not Valid Before</option>
                            <option value="valid_until">Not Valid After</option>
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
                              <th>Subject DN</th>
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
                                <td>{row.subject_dn}</td>
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
                  `Importing batch ${importProgress.currentBatch}/${importProgress.totalBatches} (${importProgress.current}/${importProgress.total} certificates)...` :
                  'Importing...'
                }
              </>
            ) : (
              <>
                <i className="bi bi-upload"></i> Import {importPreview.length} Certificates
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default Certificates;