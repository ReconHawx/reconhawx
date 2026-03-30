import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { 
  Container, 
  Row, 
  Col, 
  Card, 
  Table, 
  Button, 
  Modal, 
  Form, 
  Alert, 
  Spinner, 
  Badge,
  Pagination,
  InputGroup
} from 'react-bootstrap';
import { programAPI } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { formatDate } from '../../utils/dateUtils';

function Programs() {
  const navigate = useNavigate();
  const location = useLocation();
  const { hasProgramPermission, isSuperuser } = useAuth();
  
  // State management
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  // Pagination, filtering, sorting
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [searchFilter, setSearchFilter] = useState('');
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showYwhImportModal, setShowYwhImportModal] = useState(false);
  const [selectedProgram, setSelectedProgram] = useState(null);
  
  // Form states
  const [formData, setFormData] = useState({
    name: '',
    domain_regex: [],
    out_of_scope_regex: [],
    cidr_list: [],
    safe_registrar: [],
    safe_ssl_issuer: []
  });
  const [formErrors, setFormErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  
  // Form input helpers
  const [domainRegexInput, setDomainRegexInput] = useState('');
  const [outOfScopeRegexInput, setOutOfScopeRegexInput] = useState('');
  const [cidrListInput, setCidrListInput] = useState('');
  const [safeRegistrarInput, setSafeRegistrarInput] = useState('');
  const [safeSslIssuerInput, setSafeSslIssuerInput] = useState('');
  
  // HackerOne import states
  const [importProgramHandle, setImportProgramHandle] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  
  // YesWeHack import states
  const [ywhProgramSlug, setYwhProgramSlug] = useState('');
  const [ywhJwtToken, setYwhJwtToken] = useState('');
  const [ywhImportLoading, setYwhImportLoading] = useState(false);
  
  // Intigriti import states
  const [showIntiImportModal, setShowIntiImportModal] = useState(false);
  const [intiProgramHandle, setIntiProgramHandle] = useState('');
  const [intiImportLoading, setIntiImportLoading] = useState(false);
  
  // Bugcrowd import states
  const [showBcImportModal, setShowBcImportModal] = useState(false);
  const [bcProgramCode, setBcProgramCode] = useState('');
  const [bcSessionToken, setBcSessionToken] = useState('');
  const [bcImportLoading, setBcImportLoading] = useState(false);

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
    if (sortField) params.set('sort_by', sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 25) params.set('page_size', String(pageSize));
    return params;
  }, [searchFilter, sortField, sortDirection, currentPage, pageSize]);

  // Parse query params into state (runs on URL change and initial load)
  useEffect(() => {
    isSyncingFromUrl.current = true;
    const urlParams = new URLSearchParams(location.search);

    const urlSearch = urlParams.get('search') || '';
    if (urlSearch !== searchFilter) setSearchFilter(urlSearch);
    if (urlSearch !== debouncedSearch) setDebouncedSearch(urlSearch);

    const urlSortBy = urlParams.get('sort_by') || '';
    if (urlSortBy && ['name', 'created_at', 'updated_at'].includes(urlSortBy) && urlSortBy !== sortField) {
      setSortField(urlSortBy);
    }

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

  // Reflect state changes in the URL
  useEffect(() => {
    if (isSyncingFromUrl.current) return;
    const desiredParams = buildUrlParamsFromState();
    const desired = serializeParams(desiredParams);
    const current = serializeParams(new URLSearchParams(location.search));
    if (desired !== current) {
      navigate({ pathname: location.pathname, search: desiredParams.toString() }, { replace: true });
    }
  }, [navigate, location.pathname, buildUrlParamsFromState, location.search]);

  // Debounce search to avoid excessive API calls while typing
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchFilter), 400);
    return () => clearTimeout(timer);
  }, [searchFilter]);

  const loadPrograms = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      setError(null);

      const params = {
        page,
        page_size: pageSize,
        sort_by: sortField,
        sort_dir: sortDirection
      };
      if (debouncedSearch) params.search = debouncedSearch;

      const response = await programAPI.search(params);

      if (response.items) {
        setPrograms(response.items);
      } else {
        setPrograms([]);
      }
      const pagination = response.pagination || {};
      setTotalPages(pagination.total_pages || 1);
      setTotalItems(pagination.total_items || 0);
    } catch (err) {
      console.error('Failed to load programs:', err);
      setError('Failed to load programs: ' + err.message);
      setPrograms([]);
    } finally {
      setLoading(false);
    }
  }, [pageSize, debouncedSearch, sortField, sortDirection]);

  useEffect(() => {
    loadPrograms(currentPage);
  }, [loadPrograms, currentPage]);

  // Reset to page 1 when search changes (debounced)
  const prevDebouncedSearch = useRef(debouncedSearch);
  useEffect(() => {
    if (prevDebouncedSearch.current !== debouncedSearch) {
      prevDebouncedSearch.current = debouncedSearch;
      setCurrentPage(1);
    }
  }, [debouncedSearch]);

  const resetForm = () => {
    setFormData({
      name: '',
      domain_regex: [],
      out_of_scope_regex: [],
      cidr_list: [],
      safe_registrar: [],
      safe_ssl_issuer: []
    });
    setDomainRegexInput('');
    setOutOfScopeRegexInput('');
    setCidrListInput('');
    setSafeRegistrarInput('');
    setSafeSslIssuerInput('');
    setFormErrors({});
  };

  const parseListInput = (input) => {
    if (!input.trim()) return [];
    return input.split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0);
  };

  const validateForm = () => {
    const errors = {};
    
    if (!formData.name.trim()) {
      errors.name = 'Program name is required';
    } else if (!/^[a-zA-Z0-9_-]+$/.test(formData.name)) {
      errors.name = 'Program name can only contain letters, numbers, hyphens, and underscores';
    }
    
    // Parse and validate domain regex entries
    const domainRegexList = parseListInput(domainRegexInput);
    domainRegexList.forEach((regex, index) => {
      try {
        new RegExp(regex);
      } catch (e) {
        errors.domain_regex = errors.domain_regex || [];
        errors.domain_regex.push(`Line ${index + 1}: Invalid regex pattern`);
      }
    });
    
    // Parse and validate out-of-scope regex entries
    const outOfScopeRegexList = parseListInput(outOfScopeRegexInput);
    outOfScopeRegexList.forEach((regex, index) => {
      try {
        new RegExp(regex);
      } catch (e) {
        errors.out_of_scope_regex = errors.out_of_scope_regex || [];
        errors.out_of_scope_regex.push(`Line ${index + 1}: Invalid regex pattern`);
      }
    });
    
    // Parse and validate CIDR entries
    const cidrList = parseListInput(cidrListInput);
    cidrList.forEach((cidr, index) => {
      if (!/^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/.test(cidr)) {
        errors.cidr_list = errors.cidr_list || [];
        errors.cidr_list.push(`Line ${index + 1}: Invalid CIDR format (expected x.x.x.x/xx)`);
      }
    });
    
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleCreateProgram = async () => {
    if (!validateForm()) return;
    
    try {
      setSubmitting(true);
      setError(null);
      
      const programData = {
        name: formData.name.trim(),
        domain_regex: parseListInput(domainRegexInput),
        out_of_scope_regex: parseListInput(outOfScopeRegexInput),
        cidr_list: parseListInput(cidrListInput),
        safe_registrar: parseListInput(safeRegistrarInput),
        safe_ssl_issuer: parseListInput(safeSslIssuerInput)
      };
      
      await programAPI.create(programData);
      
      setSuccess(`Program "${programData.name}" created successfully!`);
      setShowCreateModal(false);
      resetForm();
      setCurrentPage(1);
      await loadPrograms(1);
      
      // Clear success message after delay
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to create program:', err);
      setError('Failed to create program: ' + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEditProgram = async () => {
    if (!validateForm() || !selectedProgram) return;
    
    try {
      setSubmitting(true);
      setError(null);
      
      const updateData = {
        domain_regex: parseListInput(domainRegexInput),
        out_of_scope_regex: parseListInput(outOfScopeRegexInput),
        cidr_list: parseListInput(cidrListInput),
        safe_registrar: parseListInput(safeRegistrarInput),
        safe_ssl_issuer: parseListInput(safeSslIssuerInput)
      };
      
      await programAPI.update(selectedProgram.name, updateData, true); // overwrite=true
      
      setSuccess(`Program "${selectedProgram.name}" updated successfully!`);
      setShowEditModal(false);
      resetForm();
      setSelectedProgram(null);
      await loadPrograms(currentPage);
      
      // Clear success message after delay
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to update program:', err);
      setError('Failed to update program: ' + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteProgram = async () => {
    if (!selectedProgram) return;
    
    try {
      setSubmitting(true);
      setError(null);
      
      await programAPI.delete(selectedProgram.name);
      
      setSuccess(`Program "${selectedProgram.name}" deleted successfully!`);
      
      setShowDeleteModal(false);
      setSelectedProgram(null);
      await loadPrograms(currentPage);
      
      // Clear success message after delay
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to delete program:', err);
      setError('Failed to delete program: ' + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const openCreateModal = () => {
    resetForm();
    setShowCreateModal(true);
  };

  const openImportModal = () => {
    setImportProgramHandle('');
    setShowImportModal(true);
  };

  const openYwhImportModal = () => {
    setYwhProgramSlug('');
    // Try to load JWT from localStorage
    const savedJwt = localStorage.getItem('yeswehack_jwt');
    if (savedJwt) {
      setYwhJwtToken(savedJwt);
    } else {
      setYwhJwtToken('');
    }
    setShowYwhImportModal(true);
  };

  const openIntiImportModal = () => {
    setIntiProgramHandle('');
    setShowIntiImportModal(true);
  };

  const openBcImportModal = () => {
    setBcProgramCode('');
    // Try to load session token from localStorage
    const savedToken = localStorage.getItem('bugcrowd_session_token');
    if (savedToken) {
      setBcSessionToken(savedToken);
    } else {
      setBcSessionToken('');
    }
    setShowBcImportModal(true);
  };

  // openEditModal function is defined but not used in the current implementation

  const openDeleteModal = (program) => {
    setSelectedProgram(program);
    setShowDeleteModal(true);
  };

  const formatProgramListDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const closeAllModals = () => {
    setShowCreateModal(false);
    setShowEditModal(false);
    setShowDeleteModal(false);
    setShowImportModal(false);
    setShowYwhImportModal(false);
    setShowIntiImportModal(false);
    setShowBcImportModal(false);
    setSelectedProgram(null);
    setImportProgramHandle('');
    setYwhProgramSlug('');
    setIntiProgramHandle('');
    setBcProgramCode('');
    // Don't clear JWT/session tokens on close - keep for next import
    resetForm();
  };

  const handleImportProgram = async () => {
    if (!importProgramHandle.trim()) {
      setError('Please enter a program handle');
      return;
    }
    
    try {
      setImportLoading(true);
      setError(null);
      
      const result = await programAPI.importFromHackerOne(importProgramHandle.trim());
      
      setSuccess(result.message || `Program "${result.program_name}" imported successfully!`);
      setShowImportModal(false);
      setImportProgramHandle('');
      setCurrentPage(1);
      await loadPrograms(1);
      
      // Clear success message after delay
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to import program:', err);
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to import program';
      setError(errorMessage);
    } finally {
      setImportLoading(false);
    }
  };

  const handleYwhImportProgram = async () => {
    if (!ywhProgramSlug.trim()) {
      setError('Please enter a program slug');
      return;
    }
    
    if (!ywhJwtToken.trim()) {
      setError('Please enter your YesWeHack JWT token');
      return;
    }
    
    try {
      setYwhImportLoading(true);
      setError(null);
      
      const result = await programAPI.importFromYesWeHack(
        ywhProgramSlug.trim(),
        ywhJwtToken.trim()
      );
      
      // Store JWT in localStorage for future use
      localStorage.setItem('yeswehack_jwt', ywhJwtToken.trim());
      
      setSuccess(result.message || `Program "${result.program_name}" imported successfully!`);
      setShowYwhImportModal(false);
      setYwhProgramSlug('');
      // Keep JWT token in state for next import
      setCurrentPage(1);
      await loadPrograms(1);
      
      // Clear success message after delay
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to import program from YesWeHack:', err);
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to import program';
      setError(errorMessage);
    } finally {
      setYwhImportLoading(false);
    }
  };

  const handleIntiImportProgram = async () => {
    if (!intiProgramHandle.trim()) {
      setError('Please enter a program handle');
      return;
    }
    
    try {
      setIntiImportLoading(true);
      setError(null);
      
      const result = await programAPI.importFromIntigriti(intiProgramHandle.trim());
      
      setSuccess(result.message || `Program "${result.program_name}" imported successfully!`);
      setShowIntiImportModal(false);
      setIntiProgramHandle('');
      setCurrentPage(1);
      await loadPrograms(1);
      
      // Clear success message after delay
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to import program from Intigriti:', err);
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to import program';
      setError(errorMessage);
    } finally {
      setIntiImportLoading(false);
    }
  };

  const handleBcImportProgram = async () => {
    if (!bcProgramCode.trim()) {
      setError('Please enter a program code');
      return;
    }
    
    if (!bcSessionToken.trim()) {
      setError('Please enter your Bugcrowd session token');
      return;
    }
    
    try {
      setBcImportLoading(true);
      setError(null);
      
      const result = await programAPI.importFromBugcrowd(
        bcProgramCode.trim(),
        bcSessionToken.trim()
      );
      
      // Store session token in localStorage for future use
      localStorage.setItem('bugcrowd_session_token', bcSessionToken.trim());
      
      setSuccess(result.message || `Program "${result.program_name}" imported successfully!`);
      setShowBcImportModal(false);
      setBcProgramCode('');
      // Keep session token in state for next import
      setCurrentPage(1);
      await loadPrograms(1);
      
      // Clear success message after delay
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to import program from Bugcrowd:', err);
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to import program';
      setError(errorMessage);
    } finally {
      setBcImportLoading(false);
    }
  };

  // Check if user can manage a specific program
  const canManageProgram = (programName) => {
    return isSuperuser() || hasProgramPermission(programName, 'manager');
  };

  // Check if user can create programs (only superusers)
  const canCreatePrograms = () => {
    return isSuperuser();
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

  const clearFilters = () => {
    setSearchFilter('');
    setCurrentPage(1);
  };

  const renderPagination = () => {
    if (totalPages <= 1 && totalItems <= pageSize) return null;

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
          Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalItems)} of {totalItems} programs
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

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading programs...</span>
          </Spinner>
          <p className="mt-2">Loading programs...</p>
        </div>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <div>
              <h1>📁 Programs</h1>
              <p className="text-muted">
                Manage reconnaissance programs and their scope definitions
              </p>
            </div>
            {canCreatePrograms() && (
              <div className="d-flex gap-2">
                <Button 
                  variant="primary" 
                  onClick={openCreateModal}
                  disabled={submitting}
                >
                  ➕ Create Program
                </Button>
                <Button 
                  variant="success" 
                  onClick={openImportModal}
                  disabled={submitting}
                >
                  📥 Import from HackerOne
                </Button>
                <Button 
                  variant="info" 
                  onClick={openYwhImportModal}
                  disabled={submitting}
                >
                  📥 Import from YesWeHack
                </Button>
                <Button 
                  variant="warning" 
                  onClick={openIntiImportModal}
                  disabled={submitting}
                >
                  📥 Import from Intigriti
                </Button>
                <Button 
                  variant="secondary" 
                  onClick={openBcImportModal}
                  disabled={submitting}
                >
                  📥 Import from Bugcrowd
                </Button>
              </div>
            )}
          </div>
        </Col>
      </Row>

      {error && (
        <Row className="mb-3">
          <Col>
            <Alert variant="danger" dismissible onClose={() => setError(null)}>
              {error}
            </Alert>
          </Col>
        </Row>
      )}

      {success && (
        <Row className="mb-3">
          <Col>
            <Alert variant="success" dismissible onClose={() => setSuccess(null)}>
              {success}
            </Alert>
          </Col>
        </Row>
      )}

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
              <h5 className="mb-0">
                Programs ({totalItems})
              </h5>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <Button variant="link" size="sm" className="p-0" onClick={clearFilters} aria-label="Reset all filters">
                  Reset filters
                </Button>
                <InputGroup size="sm" style={{ width: '220px' }}>
                  <Form.Control
                    type="text"
                    placeholder="Search by name..."
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') setCurrentPage(1); }}
                  />
                  <Button
                    variant="outline-secondary"
                    onClick={() => setCurrentPage(1)}
                    title="Search"
                  >
                    🔍
                  </Button>
                </InputGroup>
              </div>
            </Card.Header>
            <Card.Body style={{ overflow: 'visible' }}>
              {programs.length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-muted">
                    {searchFilter ? 'No programs match your filters.' : 'No programs found.'}
                  </p>
                  {searchFilter && (
                    <Button variant="outline-secondary" size="sm" onClick={clearFilters} className="mt-2">
                      Clear filters
                    </Button>
                  )}
                  {!searchFilter && canCreatePrograms() && (
                    <Button variant="primary" onClick={openCreateModal}>
                      Create your first program
                    </Button>
                  )}
                </div>
              ) : (
                <Table responsive hover>
                  <thead>
                    <tr>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>
                        Name {getSortIcon('name')}
                      </th>
                      <th>Domain Regex</th>
                      <th>CIDR List</th>
                      <th>Safe Registrar</th>
                      <th>Safe SSL Issuer</th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('created_at')}>
                        Created {getSortIcon('created_at')}
                      </th>
                      <th style={{ cursor: 'pointer' }} onClick={() => handleSort('updated_at')}>
                        Updated {getSortIcon('updated_at')}
                      </th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {programs.map((program) => (
                      <tr key={program._id || program.name} style={{ minHeight: '60px' }}>
                        <td>
                          <strong>{program.name}</strong>
                        </td>
                        <td>
                          {program.domain_regex && program.domain_regex.length > 0 ? (
                            <div>
                              <Badge bg="info" className="me-1">
                                {program.domain_regex.length} pattern{program.domain_regex.length !== 1 ? 's' : ''}
                              </Badge>
                              <div style={{ fontSize: '0.8em', maxWidth: '200px' }}>
                                {program.domain_regex.slice(0, 2).map((regex, idx) => (
                                  <div key={idx} className="text-muted">
                                    <code>{regex}</code>
                                  </div>
                                ))}
                                {program.domain_regex.length > 2 && (
                                  <div className="text-muted">
                                    ... and {program.domain_regex.length - 2} more
                                  </div>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td>
                          {program.cidr_list && program.cidr_list.length > 0 ? (
                            <div>
                              <Badge bg="secondary" className="me-1">
                                {program.cidr_list.length} CIDR{program.cidr_list.length !== 1 ? 's' : ''}
                              </Badge>
                              <div style={{ fontSize: '0.8em', maxWidth: '150px' }}>
                                {program.cidr_list.slice(0, 2).map((cidr, idx) => (
                                  <div key={idx} className="text-muted">
                                    <code>{cidr}</code>
                                  </div>
                                ))}
                                {program.cidr_list.length > 2 && (
                                  <div className="text-muted">
                                    ... and {program.cidr_list.length - 2} more
                                  </div>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td>
                          {program.safe_registrar && program.safe_registrar.length > 0 ? (
                            <div>
                              <Badge bg="success" className="me-1">
                                {program.safe_registrar.length} registrar{program.safe_registrar.length !== 1 ? 's' : ''}
                              </Badge>
                              <div style={{ fontSize: '0.8em', maxWidth: '150px' }}>
                                {program.safe_registrar.slice(0, 2).map((registrar, idx) => (
                                  <div key={idx} className="text-muted">
                                    <code>{registrar}</code>
                                  </div>
                                ))}
                                {program.safe_registrar.length > 2 && (
                                  <div className="text-muted">
                                    ... and {program.safe_registrar.length - 2} more
                                  </div>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td>
                          {program.safe_ssl_issuer && program.safe_ssl_issuer.length > 0 ? (
                            <div>
                              <Badge bg="warning" className="me-1">
                                {program.safe_ssl_issuer.length} issuer{program.safe_ssl_issuer.length !== 1 ? 's' : ''}
                              </Badge>
                              <div style={{ fontSize: '0.8em', maxWidth: '150px' }}>
                                {program.safe_ssl_issuer.slice(0, 2).map((issuer, idx) => (
                                  <div key={idx} className="text-muted">
                                    <code>{issuer}</code>
                                  </div>
                                ))}
                                {program.safe_ssl_issuer.length > 2 && (
                                  <div className="text-muted">
                                    ... and {program.safe_ssl_issuer.length - 2} more
                                  </div>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td>
                          <small className="text-muted">
                            {formatProgramListDate(program.created_at)}
                          </small>
                        </td>
                        <td>
                          <small className="text-muted">
                            {formatProgramListDate(program.updated_at)}
                          </small>
                        </td>
                        <td style={{ minHeight: '60px', verticalAlign: 'middle' }}>
                          <div className="d-flex gap-1">
                            <Button
                              variant="outline-primary"
                              size="sm"
                              onClick={() => navigate(`/programs/${encodeURIComponent(program.name)}`)}
                              disabled={submitting}
                            >
                              👁️ View
                            </Button>
                            
                            {canManageProgram(program.name) && (
                              <>
                                <Button
                                  variant="outline-secondary"
                                  size="sm"
                                  onClick={() => navigate(`/programs/${encodeURIComponent(program.name)}`)}
                                  disabled={submitting}
                                >
                                  ✏️ Edit
                                </Button>
                                
                                {isSuperuser() && (
                                  <Button
                                    variant="outline-danger"
                                    size="sm"
                                    onClick={() => openDeleteModal(program)}
                                    disabled={submitting}
                                  >
                                    🗑️ Delete
                                  </Button>
                                )}
                              </>
                            )}
                          </div>
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

      {!loading && !error && renderPagination()}

      {/* Create Program Modal */}
      <Modal show={showCreateModal} onHide={closeAllModals} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Create New Program</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form>
            <Row>
              <Col md={12}>
                <Form.Group className="mb-3">
                  <Form.Label>Program Name</Form.Label>
                  <Form.Control
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    placeholder="Enter program name (e.g., company-name)"
                    isInvalid={!!formErrors.name}
                  />
                  <Form.Text className="text-muted">
                    Only letters, numbers, hyphens, and underscores allowed.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.name}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Domain Regex Patterns</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={6}
                    value={domainRegexInput}
                    onChange={(e) => setDomainRegexInput(e.target.value)}
                    placeholder=".*\.example\.com&#10;subdomain\.example\.org&#10;test-.*\.example\.net"
                    isInvalid={!!formErrors.domain_regex}
                  />
                  <Form.Text className="text-muted">
                    Enter one regex pattern per line. These patterns define which domains belong to this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.domain_regex && formErrors.domain_regex.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
              
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Out-of-Scope Regex Patterns</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={6}
                    value={outOfScopeRegexInput}
                    onChange={(e) => setOutOfScopeRegexInput(e.target.value)}
                    placeholder="^test-.*\.example\.com&#10;^staging-.*\.example\.com&#10;^dev-.*"
                    isInvalid={!!formErrors.out_of_scope_regex}
                  />
                  <Form.Text className="text-muted">
                    Enter one regex pattern per line. Domains matching these patterns will be excluded, even if they match in-scope patterns.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.out_of_scope_regex && formErrors.out_of_scope_regex.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>CIDR Blocks</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={6}
                    value={cidrListInput}
                    onChange={(e) => setCidrListInput(e.target.value)}
                    placeholder="192.168.1.0/24&#10;10.0.0.0/16&#10;172.16.0.0/12"
                    isInvalid={!!formErrors.cidr_list}
                  />
                  <Form.Text className="text-muted">
                    Enter one CIDR block per line. These define the IP address ranges for this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.cidr_list && formErrors.cidr_list.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
              
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Safe Registrars</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={4}
                    value={safeRegistrarInput}
                    onChange={(e) => setSafeRegistrarInput(e.target.value)}
                    placeholder="GoDaddy&#10;Namecheap&#10;Cloudflare"
                    isInvalid={!!formErrors.safe_registrar}
                  />
                  <Form.Text className="text-muted">
                    Enter one registrar per line. These registrars are considered safe/legitimate for this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.safe_registrar && formErrors.safe_registrar.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Safe SSL Issuers</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={4}
                    value={safeSslIssuerInput}
                    onChange={(e) => setSafeSslIssuerInput(e.target.value)}
                    placeholder="Let's Encrypt&#10;DigiCert&#10;Cloudflare"
                    isInvalid={!!formErrors.safe_ssl_issuer}
                  />
                  <Form.Text className="text-muted">
                    Enter one SSL issuer per line. These SSL certificate issuers are considered safe/legitimate for this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.safe_ssl_issuer && formErrors.safe_ssl_issuer.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
              <Col md={6}></Col>
            </Row>
          </Form>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeAllModals} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleCreateProgram} disabled={submitting}>
            {submitting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Creating...
              </>
            ) : (
              'Create Program'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Edit Program Modal */}
      <Modal show={showEditModal} onHide={closeAllModals} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Edit Program: {selectedProgram?.name}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form>
            <Alert variant="info">
              <strong>Note:</strong> Program name cannot be changed. Only domain regex patterns, out-of-scope patterns, and CIDR blocks can be modified.
            </Alert>
            
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Domain Regex Patterns</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={6}
                    value={domainRegexInput}
                    onChange={(e) => setDomainRegexInput(e.target.value)}
                    placeholder=".*\.example\.com&#10;subdomain\.example\.org&#10;test-.*\.example\.net"
                    isInvalid={!!formErrors.domain_regex}
                  />
                  <Form.Text className="text-muted">
                    Enter one regex pattern per line. These patterns define which domains belong to this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.domain_regex && formErrors.domain_regex.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
              
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Out-of-Scope Regex Patterns</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={6}
                    value={outOfScopeRegexInput}
                    onChange={(e) => setOutOfScopeRegexInput(e.target.value)}
                    placeholder="^test-.*\.example\.com&#10;^staging-.*\.example\.com&#10;^dev-.*"
                    isInvalid={!!formErrors.out_of_scope_regex}
                  />
                  <Form.Text className="text-muted">
                    Enter one regex pattern per line. Domains matching these patterns will be excluded, even if they match in-scope patterns.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.out_of_scope_regex && formErrors.out_of_scope_regex.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>CIDR Blocks</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={6}
                    value={cidrListInput}
                    onChange={(e) => setCidrListInput(e.target.value)}
                    placeholder="192.168.1.0/24&#10;10.0.0.0/16&#10;172.16.0.0/12"
                    isInvalid={!!formErrors.cidr_list}
                  />
                  <Form.Text className="text-muted">
                    Enter one CIDR block per line. These define the IP address ranges for this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.cidr_list && formErrors.cidr_list.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Safe Registrars</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={4}
                    value={safeRegistrarInput}
                    onChange={(e) => setSafeRegistrarInput(e.target.value)}
                    placeholder="GoDaddy&#10;Namecheap&#10;Cloudflare"
                    isInvalid={!!formErrors.safe_registrar}
                  />
                  <Form.Text className="text-muted">
                    Enter one registrar per line. These registrars are considered safe/legitimate for this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.safe_registrar && formErrors.safe_registrar.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
              
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Safe SSL Issuers</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={4}
                    value={safeSslIssuerInput}
                    onChange={(e) => setSafeSslIssuerInput(e.target.value)}
                    placeholder="Let's Encrypt&#10;DigiCert&#10;Cloudflare"
                    isInvalid={!!formErrors.safe_ssl_issuer}
                  />
                  <Form.Text className="text-muted">
                    Enter one SSL issuer per line. These SSL certificate issuers are considered safe/legitimate for this program.
                  </Form.Text>
                  <Form.Control.Feedback type="invalid">
                    {formErrors.safe_ssl_issuer && formErrors.safe_ssl_issuer.join(', ')}
                  </Form.Control.Feedback>
                </Form.Group>
              </Col>
            </Row>
          </Form>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeAllModals} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleEditProgram} disabled={submitting}>
            {submitting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Updating...
              </>
            ) : (
              'Update Program'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Delete Program Modal */}
      <Modal show={showDeleteModal} onHide={closeAllModals}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Program</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Alert variant="warning">
            <strong>⚠️ Warning:</strong> This action cannot be undone.
          </Alert>
          <p>
            Are you sure you want to delete the program <strong>"{selectedProgram?.name}"</strong>?
          </p>
          <p className="text-muted">
            This will archive all associated assets and findings, and remove the program from the system.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeAllModals} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="danger" onClick={handleDeleteProgram} disabled={submitting}>
            {submitting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Deleting...
              </>
            ) : (
              'Delete Program'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Import from HackerOne Modal */}
      <Modal show={showImportModal} onHide={closeAllModals}>
        <Modal.Header closeButton>
          <Modal.Title>📥 Import Program from HackerOne</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Alert variant="info">
            <strong>ℹ️ About HackerOne Import</strong>
            <p className="mb-0 mt-2">
              This will fetch the program's scope from HackerOne and create a new program with the name <code>H1_&lt;handle&gt;</code>.
              Only bounty-eligible URL and wildcard scopes will be imported.
            </p>
          </Alert>
          
          <Form>
            <Form.Group className="mb-3">
              <Form.Label>Program Handle</Form.Label>
              <Form.Control
                type="text"
                value={importProgramHandle}
                onChange={(e) => setImportProgramHandle(e.target.value)}
                placeholder="e.g., twitter, shopify, github"
                disabled={importLoading}
                autoFocus
              />
              <Form.Text className="text-muted">
                Enter the HackerOne program handle (the name in the program's URL, e.g., <code>hackerone.com/&lt;handle&gt;</code>)
              </Form.Text>
            </Form.Group>
          </Form>

          {error && (
            <Alert variant="danger" dismissible onClose={() => setError(null)}>
              {error}
            </Alert>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeAllModals} disabled={importLoading}>
            Cancel
          </Button>
          <Button 
            variant="success" 
            onClick={handleImportProgram} 
            disabled={importLoading || !importProgramHandle.trim()}
          >
            {importLoading ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Importing...
              </>
            ) : (
              '📥 Import Program'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Import from YesWeHack Modal */}
      <Modal show={showYwhImportModal} onHide={closeAllModals} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>📥 Import Program from YesWeHack</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Alert variant="info">
            <strong>ℹ️ About YesWeHack Import</strong>
            <p className="mb-0 mt-2">
              This will fetch the program's scope from YesWeHack and create a new program with the name <code>YWH_&lt;slug&gt;</code>.
              Web application scopes will be imported as domain regex patterns. Your JWT token will be saved in your browser for future imports.
            </p>
          </Alert>
          
          <Form>
            <Form.Group className="mb-3">
              <Form.Label>Program Slug</Form.Label>
              <Form.Control
                type="text"
                value={ywhProgramSlug}
                onChange={(e) => setYwhProgramSlug(e.target.value)}
                placeholder="e.g., swiss-post, orange"
                disabled={ywhImportLoading}
                autoFocus
              />
              <Form.Text className="text-muted">
                Enter the YesWeHack program slug (the name in the program's URL, e.g., <code>yeswehack.com/programs/&lt;slug&gt;</code>)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>JWT Token</Form.Label>
              <Form.Control
                as="textarea"
                rows={4}
                value={ywhJwtToken}
                onChange={(e) => setYwhJwtToken(e.target.value)}
                placeholder="Paste your YesWeHack JWT token here..."
                disabled={ywhImportLoading}
              />
              <Form.Text className="text-muted">
                Your YesWeHack JWT authentication token. Get it from YesWeHack (inspect network requests when logged in).
                {ywhJwtToken && <> <Badge bg="success" className="ms-2">Token saved in browser</Badge></>}
              </Form.Text>
            </Form.Group>
          </Form>

          {error && (
            <Alert variant="danger" dismissible onClose={() => setError(null)}>
              {error}
            </Alert>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeAllModals} disabled={ywhImportLoading}>
            Cancel
          </Button>
          <Button 
            variant="info" 
            onClick={handleYwhImportProgram} 
            disabled={ywhImportLoading || !ywhProgramSlug.trim() || !ywhJwtToken.trim()}
          >
            {ywhImportLoading ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Importing...
              </>
            ) : (
              '📥 Import Program'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Import from Intigriti Modal */}
      <Modal show={showIntiImportModal} onHide={closeAllModals} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>📥 Import Program from Intigriti</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Alert variant="info">
            <strong>ℹ️ About Intigriti Import</strong>
            <p className="mb-0 mt-2">
              This will fetch the program's scope from Intigriti and create a new program with the name <code>INTI_&lt;handle&gt;</code>.
              The import uses your Intigriti API token from your user profile settings.
            </p>
          </Alert>
          
          <Form>
            <Form.Group className="mb-3">
              <Form.Label>Program Handle</Form.Label>
              <Form.Control
                type="text"
                value={intiProgramHandle}
                onChange={(e) => setIntiProgramHandle(e.target.value)}
                placeholder="e.g., uzleuven, innovapost"
                disabled={intiImportLoading}
                autoFocus
              />
              <Form.Text className="text-muted">
                Enter the Intigriti program handle (e.g., "uzleuven" from the program URL)
              </Form.Text>
            </Form.Group>
          </Form>

          <Alert variant="warning" className="mb-0">
            <strong>⚙️ API Token Required</strong>
            <p className="mb-0 mt-2">
              Make sure your Intigriti API token is configured in your user profile settings before importing.
            </p>
          </Alert>

          {error && (
            <Alert variant="danger" dismissible onClose={() => setError(null)} className="mt-3">
              {error}
            </Alert>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeAllModals} disabled={intiImportLoading}>
            Cancel
          </Button>
          <Button 
            variant="warning" 
            onClick={handleIntiImportProgram} 
            disabled={intiImportLoading || !intiProgramHandle.trim()}
          >
            {intiImportLoading ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Importing...
              </>
            ) : (
              '📥 Import Program'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Import from Bugcrowd Modal */}
      <Modal show={showBcImportModal} onHide={closeAllModals} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>📥 Import Program from Bugcrowd</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Alert variant="info">
            <strong>ℹ️ About Bugcrowd Import</strong>
            <p className="mb-0 mt-2">
              This will fetch the program's scope from Bugcrowd and create a new program with the name <code>BC_&lt;program_code&gt;</code>.
              The session token will be saved in your browser for future imports.
            </p>
          </Alert>
          
          <Form>
            <Form.Group className="mb-3">
              <Form.Label>Program Code</Form.Label>
              <Form.Control
                type="text"
                value={bcProgramCode}
                onChange={(e) => setBcProgramCode(e.target.value)}
                placeholder="e.g., tesla, paypal, shopify"
                disabled={bcImportLoading}
                autoFocus
              />
              <Form.Text className="text-muted">
                Enter the Bugcrowd program code (e.g., "tesla" from https://bugcrowd.com/tesla)
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Session Token</Form.Label>
              <Form.Control
                as="textarea"
                rows={4}
                value={bcSessionToken}
                onChange={(e) => setBcSessionToken(e.target.value)}
                placeholder="Paste your _bugcrowd_session cookie value here..."
                disabled={bcImportLoading}
              />
              <Form.Text className="text-muted">
                Your Bugcrowd session token (_bugcrowd_session cookie). Get it from your browser's cookies when logged into Bugcrowd.
                {bcSessionToken && <> <Badge bg="success" className="ms-2">Token saved in browser</Badge></>}
              </Form.Text>
            </Form.Group>
          </Form>

          {error && (
            <Alert variant="danger" dismissible onClose={() => setError(null)}>
              {error}
            </Alert>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeAllModals} disabled={bcImportLoading}>
            Cancel
          </Button>
          <Button 
            variant="secondary" 
            onClick={handleBcImportProgram} 
            disabled={bcImportLoading || !bcProgramCode.trim() || !bcSessionToken.trim()}
          >
            {bcImportLoading ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Importing...
              </>
            ) : (
              '📥 Import Program'
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default Programs;