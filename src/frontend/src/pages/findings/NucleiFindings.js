import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Row, Col, Form, Button, Modal, Spinner, Pagination, Badge, OverlayTrigger, Popover } from 'react-bootstrap';
import api from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';

const NucleiFindings = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({});
  const [severityDistribution, setSeverityDistribution] = useState({});
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [searchTerm, setSearchTerm] = useState('');
  const [nameExact, setNameExact] = useState('');
  const [nameOptions, setNameOptions] = useState([]);
  const [severityFilter, setSeverityFilter] = useState('');
  const [templateFilter, setTemplateFilter] = useState('');
  const [templateExact, setTemplateExact] = useState('');
  const [extractedResultsContains, setExtractedResultsContains] = useState('');
  const [extractedResultsExact, setExtractedResultsExact] = useState('');
  const [extractedResultsOptions, setExtractedResultsOptions] = useState([]);
  const [templateIdOptions, setTemplateIdOptions] = useState([]);
  const [tagsInclude, setTagsInclude] = useState([]);
  const [tagsExclude, setTagsExclude] = useState([]);
  const [tagsOptions, setTagsOptions] = useState([]);
  const { selectedProgram } = useProgramFilter();
  const [sortField, setSortField] = useState('created_at');
  const [sortDirection, setSortDirection] = useState('desc');
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
    if (searchTerm) params.set('search', searchTerm);
    if (nameExact) params.set('exact_match', nameExact);
    if (severityFilter) params.set('severity', severityFilter);
    if (templateFilter) params.set('template_contains', templateFilter);
    if (templateExact) params.set('template_exact', templateExact);
    if (extractedResultsContains) params.set('extracted_results_contains', extractedResultsContains);
    if (extractedResultsExact) params.set('extracted_results_exact', extractedResultsExact);
    if (tagsInclude.length > 0) params.set('tags_include', tagsInclude.join(','));
    if (tagsExclude.length > 0) params.set('tags_exclude', tagsExclude.join(','));
    if (selectedProgram) params.set('program', selectedProgram);
    if (sortField) params.set('sort_by', sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [searchTerm, nameExact, severityFilter, templateFilter, templateExact, extractedResultsContains, extractedResultsExact, tagsInclude, tagsExclude, selectedProgram, sortField, sortDirection, currentPage, pageSize]);

  // Parse query params into state - only run when location.search changes
  useEffect(() => {
    isSyncingFromUrl.current = true;
    const urlParams = new URLSearchParams(location.search);

    const urlSearch = urlParams.get('search') || '';
    setSearchTerm(urlSearch);

    const urlExactMatch = urlParams.get('exact_match') || '';
    setNameExact(urlExactMatch);

    const urlSeverity = urlParams.get('severity') || '';
    setSeverityFilter(urlSeverity);

    const urlTemplate = urlParams.get('template_contains') || '';
    setTemplateFilter(urlTemplate);

    const urlTemplateExact = urlParams.get('template_exact') || '';
    setTemplateExact(urlTemplateExact);

    const urlExtractedResultsContains = urlParams.get('extracted_results_contains') || '';
    setExtractedResultsContains(urlExtractedResultsContains);

    const urlExtractedResultsExact = urlParams.get('extracted_results_exact') || '';
    setExtractedResultsExact(urlExtractedResultsExact);

    const urlTagsInclude = urlParams.get('tags_include') || '';
    setTagsInclude(urlTagsInclude ? urlTagsInclude.split(',') : []);

    const urlTagsExclude = urlParams.get('tags_exclude') || '';
    setTagsExclude(urlTagsExclude ? urlTagsExclude.split(',') : []);

    // Program filter is read-only here; global context controls value

    const urlSortBy = urlParams.get('sort_by');
    if (urlSortBy) setSortField(urlSortBy);

    const urlSortDir = urlParams.get('sort_dir');
    if (urlSortDir && (urlSortDir === 'asc' || urlSortDir === 'desc')) setSortDirection(urlSortDir);

    const urlPage = parseInt(urlParams.get('page') || '1', 10);
    if (!Number.isNaN(urlPage) && urlPage > 0) setCurrentPage(urlPage);

    const urlPageSize = parseInt(urlParams.get('page_size') || '25', 10);
    if (!Number.isNaN(urlPageSize) && urlPageSize > 0) setPageSize(urlPageSize);

    setTimeout(() => { isSyncingFromUrl.current = false; }, 0);
  }, [location.search]); // Only depend on location.search

  // Reflect state changes in the URL - run when filter state changes
  useEffect(() => {
    if (isSyncingFromUrl.current) return;
    
    const desiredParams = buildUrlParamsFromState();
    const desired = serializeParams(desiredParams);
    const current = serializeParams(new URLSearchParams(location.search));
    
    if (desired !== current) {
      navigate({ pathname: location.pathname, search: desiredParams.toString() }, { replace: true });
    }
  }, [navigate, location.pathname, location.search, buildUrlParamsFromState]);
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    name: true,
    severity: true,
    template_id: true,
    hostname: true,
    url: true,
    matcher_name: true,
    description: true,
    program_name: true,
    created_at: true
  });
  const [exporting, setExporting] = useState(false);
  const [customFilename, setCustomFilename] = useState('');

  const severityColors = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: 'secondary',
    info: 'primary',
    unknown: 'dark'
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

  // Column filter popover
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

  const loadFindings = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      setError(null);

      // Build typed request
      const params = {
        search: searchTerm || undefined,
        exact_match: nameExact || undefined,
        severity: severityFilter || undefined,
        template_contains: templateFilter || undefined,
        template_exact: templateExact || undefined,
        extracted_results_contains: extractedResultsContains || undefined,
        extracted_results_exact: extractedResultsExact || undefined,
        tags_include: tagsInclude.length > 0 ? tagsInclude : undefined,
        tags_exclude: tagsExclude.length > 0 ? tagsExclude : undefined,
        program: selectedProgram || undefined,
        sort_by: sortField,
        sort_dir: sortDirection,
        page,
        page_size: pageSize,
      };

      const response = await api.findings.nuclei.search(params);
      setFindings(response.items || []);
      setPagination(response.pagination || {});
      setSeverityDistribution(response.severity_distribution || {});
      setCurrentPage(page);
    } catch (err) {
      console.error('Error loading nuclei findings:', err);
      setError('Failed to load nuclei findings');
    } finally {
      setLoading(false);
    }
  }, [searchTerm, nameExact, severityFilter, templateFilter, templateExact, extractedResultsContains, extractedResultsExact, tagsInclude, tagsExclude, selectedProgram, sortField, sortDirection, pageSize]);

  useEffect(() => {
    loadFindings(currentPage);
  }, [loadFindings, currentPage]);

  // Load distinct values for name dropdown
  const loadNameOptions = useCallback(async () => {
    try {
      const response = await api.findings.nuclei.getDistinct('name', {
        program_name: selectedProgram || undefined
      });
      setNameOptions(response || []);
    } catch (err) {
      console.error('Error loading name options:', err);
      setNameOptions([]);
    }
  }, [selectedProgram]);

  // Load distinct values for extracted_results dropdown
  const loadExtractedResultsOptions = useCallback(async () => {
    try {
      const response = await api.findings.nuclei.getDistinct('extracted_results', {
        program_name: selectedProgram || undefined
      });
      setExtractedResultsOptions(response || []);
    } catch (err) {
      console.error('Error loading extracted results options:', err);
      setExtractedResultsOptions([]);
    }
  }, [selectedProgram]);

  // Load distinct values for template_id dropdown
  const loadTemplateIdOptions = useCallback(async () => {
    try {
      const response = await api.findings.nuclei.getDistinct('template_id', {
        program_name: selectedProgram || undefined
      });
      setTemplateIdOptions(response || []);
    } catch (err) {
      console.error('Error loading template id options:', err);
      setTemplateIdOptions([]);
    }
  }, [selectedProgram]);

  // Load distinct values for tags dropdown
  const loadTagsOptions = useCallback(async () => {
    try {
      const response = await api.findings.nuclei.getDistinct('tags', {
        program_name: selectedProgram || undefined
      });
      setTagsOptions(response || []);
    } catch (err) {
      console.error('Error loading tags options:', err);
      setTagsOptions([]);
    }
  }, [selectedProgram]);

  // Load options on mount and when program changes
  useEffect(() => {
    loadNameOptions();
    loadExtractedResultsOptions();
    loadTemplateIdOptions();
    loadTagsOptions();
  }, [loadNameOptions, loadExtractedResultsOptions, loadTemplateIdOptions, loadTagsOptions]);

  const clearFilters = () => {
    setSearchTerm('');
    setNameExact('');
    setSeverityFilter('');
    setTemplateFilter('');
    setTemplateExact('');
    setExtractedResultsContains('');
    setExtractedResultsExact('');
    setTagsInclude([]);
    setTagsExclude([]);
    setCurrentPage(1); // Reset to first page when clearing filters
  };

  const handleNameExactChange = (e) => {
    setNameExact(e.target.value);
    setCurrentPage(1); // Reset to first page when filter changes
  };

  const handleTagsIncludeChange = (tag) => {
    const newTags = tagsInclude.includes(tag)
      ? tagsInclude.filter(t => t !== tag)
      : [...tagsInclude, tag];
    setTagsInclude(newTags);
    setCurrentPage(1); // Reset to first page when filter changes
  };

  const handleTagsExcludeChange = (tag) => {
    const newTags = tagsExclude.includes(tag)
      ? tagsExclude.filter(t => t !== tag)
      : [...tagsExclude, tag];
    setTagsExclude(newTags);
    setCurrentPage(1); // Reset to first page when filter changes
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(findings.map(finding => finding.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (findingId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(findingId);
    } else {
      newSelected.delete(findingId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems);
      await api.findings.nuclei.deleteBatch(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page
      loadFindings(currentPage);
    } catch (err) {
      console.error('Error deleting nuclei findings:', err);
      alert('Failed to delete nuclei findings: ' + (err.response?.data?.detail || err.message));
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
      
      const params = {
        search: searchTerm || undefined,
        exact_match: nameExact || undefined,
        severity: severityFilter || undefined,
        template_contains: templateFilter || undefined,
        template_exact: templateExact || undefined,
        extracted_results_contains: extractedResultsContains || undefined,
        extracted_results_exact: extractedResultsExact || undefined,
        program: selectedProgram || undefined,
        sort_by: sortField,
        sort_dir: sortDirection,
        page: 1,
        page_size: 10000,
      };

      const response = await api.findings.nuclei.search(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - only URLs
        exportData = rawData.map(item => item.url || item.hostname || item.name).filter(Boolean).join('\n');
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
        : `nuclei_findings_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting nuclei findings:', err);
      alert('Failed to export nuclei findings: ' + err.message);
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

  const formatNucleiListDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const truncateText = (text, maxLength = 50) => {
    if (!text) return 'N/A';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
  };

  if (loading && findings.length === 0) {
    return (
      <div className="container-fluid mt-4">
        <div className="text-center">
          <div className="spinner-border" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
          <p className="mt-2">Loading nuclei findings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container-fluid mt-4">
      <div className="row mb-4">
        <div className="col">
          <h2>Nuclei Findings</h2>
          <p className="text-muted">Security vulnerabilities discovered by Nuclei scanner</p>
        </div>
      </div>

      {/* Header filters moved to column popovers; accordion removed */}

      {error && (
        <div className="alert alert-danger" role="alert">
          {error}
        </div>
      )}

      {/* Results */}
      <div className="row">
        <div className="col">
          <div className="card">
            <div className="card-header d-flex justify-content-between align-items-center">
              <h5 className="mb-0">
                Findings {pagination.total_items ? `(${pagination.total_items} total)` : ''}
                {Object.keys(severityDistribution).length > 0 && (
                  <div className="d-flex align-items-center mt-2">
                    {Object.entries(severityColors).map(([severity, color]) => {
                      const count = severityDistribution[severity] || 0;
                      if (count === 0) return null;
                      return (
                        <span key={severity} className={`badge bg-${color} me-2`}>
                          {severity}: {count}
                        </span>
                      );
                    })}
                  </div>
                )}
              </h5>
              <div className="d-flex align-items-center">
                <Button variant="link" size="sm" className="me-2 p-0" onClick={clearFilters} aria-label="Reset all filters">Reset filters</Button>
                <Button
                  variant="outline-primary"
                  size="sm"
                  onClick={handleExport}
                  className="me-2"
                >
                  <i className="bi bi-download"></i> Export
                </Button>
                {selectedItems.size > 0 && (
                  <Button
                    variant="outline-danger"
                    size="sm"
                    className="me-2"
                    onClick={() => setShowDeleteModal(true)}
                  >
                    <i className="bi bi-trash"></i> Delete Selected ({selectedItems.size})
                  </Button>
                )}
                {loading && (
                  <div className="spinner-border spinner-border-sm" role="status">
                    <span className="visually-hidden">Loading...</span>
                  </div>
                )}
              </div>
            </div>
            <div className="card-body p-0">
              {findings.length === 0 ? (
                <div className="text-center p-4">
                  <p className="text-muted mb-0">No nuclei findings found</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="table table-hover mb-0">
                    <thead className="table-light">
                      <tr>
                        <th>
                          <Form.Check
                            type="checkbox"
                            checked={selectedItems.size === findings.length && findings.length > 0}
                            onChange={(e) => handleSelectAll(e.target.checked)}
                          />
                        </th>
                        <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Name {getSortIcon('name')}</span>
                            <ColumnFilterPopover id="filter-name" ariaLabel="Filter by name" isActive={!!searchTerm || !!nameExact}>
                              <div>
                                <InlineTextFilter
                                  label="Search"
                                  placeholder="Search by name..."
                                  initialValue={searchTerm}
                                  onApply={(val) => setSearchTerm(val)}
                                  onClear={() => setSearchTerm('')}
                                />
                                <div className="mt-3">
                                  <Form.Group>
                                    <Form.Label className="mb-1">Name (exact)</Form.Label>
                                    <Form.Select value={nameExact} onChange={handleNameExactChange}>
                                      <option value="">All Names</option>
                                      {nameOptions.map((option) => (
                                        <option key={option} value={option}>{option}</option>
                                      ))}
                                    </Form.Select>
                                  </Form.Group>
                                  <div className="d-flex justify-content-end gap-2 mt-2">
                                    <Button size="sm" variant="secondary" onClick={() => setNameExact('')}>Clear</Button>
                                    <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                  </div>
                                </div>
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th style={{ cursor: 'pointer' }} onClick={() => handleSort('severity')}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Severity {getSortIcon('severity')}</span>
                            <ColumnFilterPopover id="filter-severity" ariaLabel="Filter by severity" isActive={!!severityFilter}>
                              <div>
                                <Form.Group>
                                  <Form.Label className="mb-1">Severity</Form.Label>
                                  <Form.Select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                                    <option value="">All Severities</option>
                                    <option value="critical">Critical</option>
                                    <option value="high">High</option>
                                    <option value="medium">Medium</option>
                                    <option value="low">Low</option>
                                    <option value="info">Info</option>
                                  </Form.Select>
                                </Form.Group>
                                <div className="d-flex justify-content-end gap-2 mt-2">
                                  <Button size="sm" variant="secondary" onClick={() => setSeverityFilter('')}>Clear</Button>
                                  <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                </div>
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th 
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleSort('tags')}
                        >
                          Tags {getSortIcon('tags')}
                        </th>
                        <th style={{ cursor: 'pointer' }} onClick={() => handleSort('template_id')}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Template ID {getSortIcon('template_id')}</span>
                            <ColumnFilterPopover id="filter-template" ariaLabel="Filter by template id" isActive={!!templateFilter || !!templateExact}>
                              <div>
                                <InlineTextFilter
                                  label="Template contains"
                                  placeholder="Template ID..."
                                  initialValue={templateFilter}
                                  onApply={(val) => setTemplateFilter(val)}
                                  onClear={() => setTemplateFilter('')}
                                />
                                <div className="mt-3">
                                  <Form.Group>
                                    <Form.Label className="mb-1">Template (exact)</Form.Label>
                                    <Form.Select value={templateExact} onChange={(e) => setTemplateExact(e.target.value)}>
                                      <option value="">All Templates</option>
                                      {templateIdOptions.map((option) => (
                                        <option key={option} value={option}>{option}</option>
                                      ))}
                                    </Form.Select>
                                  </Form.Group>
                                  <div className="d-flex justify-content-end gap-2 mt-2">
                                    <Button size="sm" variant="secondary" onClick={() => setTemplateExact('')}>Clear</Button>
                                    <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                  </div>
                                </div>
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th style={{ cursor: 'pointer' }} onClick={() => handleSort('extracted_results')}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Extracted Results {getSortIcon('extracted_results')}</span>
                            <ColumnFilterPopover id="filter-extracted" ariaLabel="Filter by extracted results" isActive={!!extractedResultsContains || !!extractedResultsExact}>
                              <div>
                                <InlineTextFilter
                                  label="Contains"
                                  placeholder="Search in extracted results..."
                                  initialValue={extractedResultsContains}
                                  onApply={(val) => setExtractedResultsContains(val)}
                                  onClear={() => setExtractedResultsContains('')}
                                />
                                <div className="mt-3">
                                  <Form.Group>
                                    <Form.Label className="mb-1">Exact</Form.Label>
                                    <Form.Select value={extractedResultsExact} onChange={(e) => setExtractedResultsExact(e.target.value)}>
                                      <option value="">All Results</option>
                                      {extractedResultsOptions.map((option) => (
                                        <option key={option} value={option}>{option}</option>
                                      ))}
                                    </Form.Select>
                                  </Form.Group>
                                  <div className="d-flex justify-content-end gap-2 mt-2">
                                    <Button size="sm" variant="secondary" onClick={() => setExtractedResultsExact('')}>Clear</Button>
                                    <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                  </div>
                                </div>
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th style={{ cursor: 'pointer' }} onClick={() => handleSort('hostname')}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Hostname {getSortIcon('hostname')}</span>
                            <ColumnFilterPopover id="filter-tags" ariaLabel="Filter by tags" isActive={tagsInclude.length>0 || tagsExclude.length>0}>
                              <div>
                                <Form.Label className="fw-bold small">Tags include</Form.Label>
                                <div className="border rounded p-2 mb-2" style={{ maxHeight: 150, overflowY: 'auto' }}>
                                  <Row>
                                    {tagsOptions.length === 0 ? (
                                      <Col><span className="text-muted">No tags available</span></Col>
                                    ) : (
                                      tagsOptions.map((tag) => (
                                        <Col key={tag} xs={6} className="mb-1">
                                          <Form.Check
                                            type="checkbox"
                                            label={tag}
                                            checked={tagsInclude.includes(tag)}
                                            onChange={() => handleTagsIncludeChange(tag)}
                                          />
                                        </Col>
                                      ))
                                    )}
                                  </Row>
                                </div>
                                <Form.Label className="fw-bold small">Tags exclude</Form.Label>
                                <div className="border rounded p-2" style={{ maxHeight: 150, overflowY: 'auto' }}>
                                  <Row>
                                    {tagsOptions.length === 0 ? (
                                      <Col><span className="text-muted">No tags available</span></Col>
                                    ) : (
                                      tagsOptions.map((tag) => (
                                        <Col key={tag} xs={6} className="mb-1">
                                          <Form.Check
                                            type="checkbox"
                                            label={tag}
                                            checked={tagsExclude.includes(tag)}
                                            onChange={() => handleTagsExcludeChange(tag)}
                                          />
                                        </Col>
                                      ))
                                    )}
                                  </Row>
                                </div>
                                <div className="d-flex justify-content-end gap-2 mt-2">
                                  <Button size="sm" variant="secondary" onClick={() => { setTagsInclude([]); setTagsExclude([]); }}>Clear</Button>
                                  <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                                </div>
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th 
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleSort('url')}
                        >
                          URL {getSortIcon('url')}
                        </th>
                        <th 
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleSort('program_name')}
                        >
                          Program {getSortIcon('program_name')}
                        </th>
                        <th 
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleSort('created_at')}
                        >
                          Created {getSortIcon('created_at')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {findings.map((finding) => (
                        <tr key={finding.id}>
                          <td onClick={(e) => e.stopPropagation()}>
                            <Form.Check
                              type="checkbox"
                              checked={selectedItems.has(finding.id)}
                              onChange={(e) => handleSelectItem(finding.id, e.target.checked)}
                            />
                          </td>
                          <td>
                            <Link 
                              to={`/findings/nuclei/details?id=${finding.id}`}
                              className="text-decoration-none"
                            >
                              <div className="fw-medium text-primary">{truncateText(finding.name, 40)}</div>
                            </Link>
                            {finding.matcher_name && (
                              <small className="text-muted">{truncateText(finding.matcher_name, 30)}</small>
                            )}
                          </td>
                          <td>
                            <span className={`badge bg-${severityColors[finding.severity] || 'secondary'}`}>
                              {finding.severity}
                            </span>
                          </td>
                          <td>
                            {finding.tags && finding.tags.length > 0 ? (
                              <div>
                                {finding.tags.slice(0, 2).map((ip, idx) => (
                                  <Badge key={idx} bg="secondary" className="me-1">
                                    {ip}
                                  </Badge>
                                ))}
                                {finding.tags.length > 2 && (
                                  <Badge bg="secondary">
                                    +{finding.tags.length - 2} more
                                  </Badge>
                                )}
                              </div>
                            ) : (
                              <span className="text-muted">-</span>
                            )}
                          </td>
                          <td>
                            <code className="small">{truncateText(finding.template_id, 20)}</code>
                          </td>
                          <td>
                            {(() => {
                              if (!finding.extracted_results) return 'N/A';
                              if (Array.isArray(finding.extracted_results)) {
                                if (finding.extracted_results.length === 0) return 'N/A';
                                return truncateText(finding.extracted_results.join(', '), 50);
                              }
                              return truncateText(String(finding.extracted_results), 50);
                            })()}
                          </td>
                          <td>{truncateText(finding.hostname, 25)}</td>
                          <td>
                            {finding.url && (
                              <a href={finding.url} target="_blank" rel="noopener noreferrer" className="text-decoration-none">
                                {truncateText(finding.url, 30)}
                                <i className="bi bi-box-arrow-up-right ms-1 small"></i>
                              </a>
                            )}
                          </td>
                          <td>
                            <span className="badge bg-secondary">{finding.program_name}</span>
                          </td>
                          <td className="small text-muted">
                            {formatNucleiListDate(finding.created_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Pagination */}
      {pagination.total_pages > 1 && (
        <div className="row mt-4 mb-4">
          <div className="col">
            <div className="text-center mb-3">
              <div className="text-muted">
                Showing page {pagination.current_page} of {pagination.total_pages}
                {pagination.total_items && ` (${pagination.total_items} total findings)`}
              </div>
            </div>
            <div className="d-flex justify-content-center align-items-center gap-3">
              <Form.Select
                size="sm"
                value={pageSize}
                onChange={(e) => setPageSize(parseInt(e.target.value))}
                style={{ width: 'auto' }}
              >
                <option value={10}>10 per page</option>
                <option value={25}>25 per page</option>
                <option value={50}>50 per page</option>
                <option value={100}>100 per page</option>
              </Form.Select>
              <Pagination className="mb-0">
                <li className={`page-item ${!pagination.has_previous ? 'disabled' : ''}`}>
                  <button
                    className="page-link"
                    onClick={() => loadFindings(currentPage - 1)}
                    disabled={!pagination.has_previous}
                  >
                    Previous
                  </button>
                </li>
                
                {/* Page numbers */}
                {Array.from({ length: Math.min(5, pagination.total_pages) }, (_, i) => {
                  const startPage = Math.max(1, currentPage - 2);
                  const pageNumber = startPage + i;
                  
                  if (pageNumber <= pagination.total_pages) {
                    return (
                      <li key={pageNumber} className={`page-item ${currentPage === pageNumber ? 'active' : ''}`}>
                        <button
                          className="page-link"
                          onClick={() => loadFindings(pageNumber)}
                        >
                          {pageNumber}
                        </button>
                      </li>
                    );
                  }
                  return null;
                })}
                
                <li className={`page-item ${!pagination.has_next ? 'disabled' : ''}`}>
                  <button
                    className="page-link"
                    onClick={() => loadFindings(currentPage + 1)}
                    disabled={!pagination.has_next}
                  >
                    Next
                  </button>
                </li>
              </Pagination>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Nuclei Findings</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected nuclei finding(s)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Finding(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export Nuclei Findings</Modal.Title>
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
                label="Plain Text - URLs/Hostnames only (one per line)"
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
                      label="Name"
                      checked={exportColumns.name}
                      onChange={() => handleColumnToggle('name')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Severity"
                      checked={exportColumns.severity}
                      onChange={() => handleColumnToggle('severity')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Template ID"
                      checked={exportColumns.template_id}
                      onChange={() => handleColumnToggle('template_id')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Hostname"
                      checked={exportColumns.hostname}
                      onChange={() => handleColumnToggle('hostname')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="URL"
                      checked={exportColumns.url}
                      onChange={() => handleColumnToggle('url')}
                      className="mb-2"
                    />
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="Matcher Name"
                      checked={exportColumns.matcher_name}
                      onChange={() => handleColumnToggle('matcher_name')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Description"
                      checked={exportColumns.description}
                      onChange={() => handleColumnToggle('description')}
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
                  Leave empty to use default filename: nuclei_findings_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total findings to export: {pagination.total_items || 0} (based on current filters)
                {Object.keys(severityDistribution).length > 0 && (
                  <div className="mt-1">
                    {Object.entries(severityDistribution).map(([severity, count]) => (
                      <span key={severity} className={`badge bg-${severityColors[severity] || 'secondary'} me-1`}>
                        {severity}: {count}
                      </span>
                    ))}
                  </div>
                )}
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
    </div>
  );
};

export default NucleiFindings;