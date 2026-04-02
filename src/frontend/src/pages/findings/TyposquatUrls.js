import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, Button, Spinner, Modal, OverlayTrigger, Popover } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { typosquatAPI } from '../../services/api';
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

function TyposquatUrls() {
  usePageTitle(formatPageTitle('Typosquat URLs'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [typosquatUrls, setTyposquatUrls] = useState([]);
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
    typosquat_type: true,
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

  const fetchTyposquatUrls = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (exactMatchFilter) params.exact_match = exactMatchFilter;
      if (protocolFilter) params.protocol = protocolFilter;
      if (selectedProgram) params.program = selectedProgram;
      if (statusFilter) params.status_code = parseInt(statusFilter);
      if (showOnlyRootUrls) params.only_root = true;
      if (techTextFilter) params.technology_text = techTextFilter;
      if (techDropdownFilter) params.technology = techDropdownFilter;
      if (portFilter) params.port = parseInt(portFilter);
      if (showOnlyUnusualPorts) params.unusual_ports = true;
      params.sort_by = sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = page;
      params.page_size = pageSize;
      
      // Use typosquat-specific API endpoint
      const response = await typosquatAPI.searchTyposquatUrls(params);
      
      setTyposquatUrls(response.items || []);
      setTotalPages(response.pagination?.total_pages || 1);
      setTotalItems(response.pagination?.total_items || 0);
      setError(null);
    } catch (err) {
      setError('Failed to fetch typosquat URLs: ' + err.message);
      setTyposquatUrls([]);
    } finally {
      setLoading(false);
    }
  }, [pageSize, searchFilter, exactMatchFilter, protocolFilter, selectedProgram, statusFilter, showOnlyRootUrls, techTextFilter, techDropdownFilter, portFilter, showOnlyUnusualPorts, sortField, sortDirection]);

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
      const technologies = await typosquatAPI.getDistinctValuesUrl('technologies', selectedProgram || undefined);
      if (technologies && Array.isArray(technologies)) {
        setTechnologies(technologies.sort());
      }
    } catch (err) {
      console.error('Error fetching technologies:', err);
      setTechnologies([]);
    }
  }, [selectedProgram]);

  const fetchPorts = useCallback(async () => {
    try {
      const ports = await typosquatAPI.getDistinctValuesUrl('port', selectedProgram || undefined);
      if (ports && Array.isArray(ports)) {
        setPorts(ports.sort((a, b) => parseInt(a) - parseInt(b)));
      }
    } catch (err) {
      console.error('Error fetching ports:', err);
      setPorts([]);
    }
  }, [selectedProgram]);

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
    fetchTyposquatUrls(currentPage);
  }, [currentPage, fetchTyposquatUrls]);

  // Fetch technologies and ports on component mount and when selected program changes
  useEffect(() => {
    fetchTechnologies();
    fetchPorts();
  }, [selectedProgram, fetchTechnologies, fetchPorts]);

  // Load Font Awesome CSS on component mount
  useEffect(() => {
    loadFontAwesome();
  }, []);

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
  };

  const handleUrlClick = (url) => {
    navigate(`/findings/typosquat-urls/details?id=${encodeURIComponent(url.id || '')}`);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(typosquatUrls.map(url => url.id)));
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
      await typosquatAPI.deleteBatchUrls(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      fetchTyposquatUrls(currentPage);
    } catch (err) {
      console.error('Error deleting typosquat URLs:', err);
      alert('Failed to delete typosquat URLs: ' + (err.response?.data?.detail || err.message));
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
      
      const params = {};
      if (searchFilter) params.search = searchFilter;
      if (protocolFilter) params.protocol = protocolFilter;
      if (selectedProgram) params.program = selectedProgram;
      if (statusFilter) params.status_code = parseInt(statusFilter);
      if (showOnlyRootUrls) params.only_root = true;
      if (techTextFilter) params.technology_text = techTextFilter;
      if (techDropdownFilter) params.technology = techDropdownFilter;
      if (portFilter) params.port = parseInt(portFilter);
      if (showOnlyUnusualPorts) params.unusual_ports = true;
      params.sort_by = sortField;
      params.sort_dir = sortDirection === 'asc' ? 'asc' : 'desc';
      params.page = 1;
      params.page_size = 10000;
      
      const response = await typosquatAPI.searchTyposquatUrls(params);
      const rawData = response.items || [];
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        exportData = rawData.map(item => item.url).join('\n');
        fileExtension = 'txt';
        mimeType = 'text/plain';
      } else if (exportFormat === 'csv') {
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
      
      const dataUri = `data:${mimeType};charset=utf-8,${encodeURIComponent(exportData)}`;
      const exportFileDefaultName = customFilename.trim() 
        ? `${customFilename.trim()}.${fileExtension}` 
        : `typosquat_urls_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting typosquat URLs:', err);
      alert('Failed to export typosquat URLs: ' + err.message);
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

  const truncateUrl = (url, maxLength = 60) => {
    if (url.length <= maxLength) return url;
    return url.substring(0, maxLength) + '...';
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

  // Local text filter buffer
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
          <h1>🔤 Typosquat URLs</h1>
          <p className="text-muted">Browse and manage typosquat URLs discovered during reconnaissance</p>
        </Col>
      </Row>

      

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">Typosquat URLs</h5>
              <div className="d-flex align-items-center">
                <Badge bg="secondary" className="me-3">Total: {totalItems}</Badge>
                <Form.Check
                  type="switch"
                  id="root-path-only-typosquat"
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
                  <p className="mt-2">Loading typosquat URLs...</p>
                </div>
              ) : error ? (
                <div className="p-4">
                  <p className="text-danger">{error}</p>
                </div>
              ) : typosquatUrls.length === 0 ? (
                <div className="p-4 text-center">
                  <p className="text-muted">No typosquat URLs found matching the current filters.</p>
                </div>
              ) : (
                <Table hover responsive>
                  <thead>
                    <tr>
                      <th>
                        <Form.Check
                          type="checkbox"
                          checked={selectedItems.size === typosquatUrls.length && typosquatUrls.length > 0}
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
                        onClick={() => handleSort('chain_status_code')}
                      >
                        Chain Status {getSortIcon('chain_status_code')}
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
                    {typosquatUrls.map((url) => (
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
                          {url.chain_status_codes && Array.isArray(url.chain_status_codes) && url.chain_status_codes.length > 0 ? (
                            <div>
                              {url.chain_status_codes.map((statusCode, idx) => (
                                <Badge 
                                  key={idx} 
                                  bg={statusCode < 300 ? 'success' : statusCode < 400 ? 'warning' : 'danger'}
                                  className="me-1 mb-1"
                                >
                                  {statusCode}
                                </Badge>
                              ))}
                            </div>
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
          </Card>

          {/* Pagination */}
          {totalPages > 1 && !loading && !error && (
            <div className="mt-4">
              <div className="text-center mb-3">
                <div className="text-muted">
                  Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} typosquat URLs
                  (Page {currentPage} of {totalPages})
                </div>
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

                {/* Show pagination numbers */}
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (currentPage <= 3) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }

                  return (
                    <Pagination.Item
                      key={pageNum}
                      active={pageNum === currentPage}
                      onClick={() => setCurrentPage(pageNum)}
                    >
                      {pageNum}
                    </Pagination.Item>
                  );
                })}

                <Pagination.Next onClick={() => setCurrentPage(currentPage + 1)} disabled={currentPage === totalPages} />
                <Pagination.Last onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} />
              </Pagination>
              </div>
            </div>
          )}


        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Typosquat URLs</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected typosquat URL(s)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Typosquat URL(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export Typosquat URLs</Modal.Title>
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
                      label="Typosquat Type"
                      checked={exportColumns.typosquat_type}
                      onChange={() => handleColumnToggle('typosquat_type')}
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
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="Content Type"
                      checked={exportColumns.content_type}
                      onChange={() => handleColumnToggle('content_type')}
                      className="mb-2"
                    />
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
                  Leave empty to use default filename: typosquat_urls_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total typosquat URLs to export: {totalItems} (based on current filters)
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
    </Container>
  );
}

export default TyposquatUrls;
