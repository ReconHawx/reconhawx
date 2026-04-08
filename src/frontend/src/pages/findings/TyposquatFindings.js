import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Container, 
  Card, 
  Table, 
  Badge, 
  Form, 
  Row, 
  Col, 
  Button,
  Pagination,
  Alert,
  Spinner,
  Accordion,
  Modal,
  OverlayTrigger,
  Popover
} from 'react-bootstrap';
import { useNavigate, useSearchParams, useLocation, Link } from 'react-router-dom';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { useAuth } from '../../contexts/AuthContext';
import api, { jobAPI, userManagementAPI } from '../../services/api';
import { formatDate } from '../../utils/dateUtils';
import { initializeUserCache } from '../../utils/userUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

/** Keep in sync with API `AI_ANALYSIS_BATCH_MAX_FINDINGS` in typosquat_findings.py (temporary cap). */
const AI_ANALYSIS_BATCH_MAX_FINDINGS = 10;

function TyposquatFindings() {
  usePageTitle(formatPageTitle('Typosquat Findings'));
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();

  // Get allowed status transitions for batch operations
  const getAllowedBatchStatusOptions = (selectedFindings) => {
    // Always include "unchanged" as the first option
    const baseOptions = [{ value: 'unchanged', label: 'Keep Current Status' }];

    if (!selectedFindings || selectedFindings.length === 0) {
      return [
        ...baseOptions,
        { value: 'new', label: 'New' },
        { value: 'inprogress', label: 'In Progress' },
        { value: 'dismissed', label: 'Dismissed' },
        { value: 'resolved', label: 'Resolved' }
      ];
    }

    // Check if any selected findings have 'new' status
    const hasNewStatus = selectedFindings.some(f => f.status === 'new');

    // If any finding has 'new' status, only allow 'new' and 'inprogress'
    if (hasNewStatus) {
      return [
        ...baseOptions,
        { value: 'new', label: 'New' },
        { value: 'inprogress', label: 'In Progress' }
      ];
    }

    // Otherwise, allow all statuses
    return [
      ...baseOptions,
      { value: 'new', label: 'New' },
      { value: 'inprogress', label: 'In Progress' },
      { value: 'dismissed', label: 'Dismissed' },
      { value: 'resolved', label: 'Resolved' }
    ];
  };

  // Validate batch status transition
  const validateBatchStatusTransition = (selectedFindings, newStatus, assignedTo, comment) => {
    // Skip validation if status is unchanged
    if (newStatus === 'unchanged') {
      return null; // No validation error
    }

    // Rule 1: Check if any findings with 'new' status are trying to transition to invalid states
    const newFindings = selectedFindings.filter(f => f.status === 'new');
    if (newFindings.length > 0 && newStatus !== 'new' && newStatus !== 'inprogress') {
      return `${newFindings.length} selected finding(s) have 'New' status and can only be changed to 'In Progress'`;
    }

    // Rule 2: 'inprogress' status requires an assigned user (unless keeping current assignment)
    if (newStatus === 'inprogress' && !assignedTo && assignedTo !== 'unchanged') {
      return "'In Progress' status requires an assigned user";
    }

    // Rule 3: Check if any findings with 'inprogress' status require comments
    const inProgressFindings = selectedFindings.filter(f => f.status === 'inprogress');
    if (inProgressFindings.length > 0 && (newStatus === 'dismissed' || newStatus === 'resolved') && !comment) {
      return `${inProgressFindings.length} selected finding(s) have 'In Progress' status and require a comment when changing to '${newStatus}'`;
    }

    return null; // No validation error
  };
  const { selectedProgram, programs } = useProgramFilter();
  const { user, isAdmin } = useAuth();
  
  // Initialize user cache with current user
  React.useEffect(() => {
    initializeUserCache(user);
  }, [user]);

  // Debug: Log programs from context
  // State management
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  
  // Typo domain input (debounced into filters.typo_domain)
  const [typoDomainInput, setTypoDomainInput] = useState(searchParams.get('typo_domain') || '');

  // Filter state
  const [filters, setFilters] = useState({
    typo_domain: searchParams.get('typo_domain') || '',
    status: searchParams.get('status') ? searchParams.get('status').split(',') : ['new', 'inprogress'], // Multi-select array, default to new and inprogress
    country: searchParams.get('country') || '',
    registrar: searchParams.get('registrar') || '',
    ip_address: searchParams.get('ip_address') || '',
    has_ip: searchParams.get('has_ip') === 'true',
    hide_no_registrar: searchParams.get('hide_no_registrar') === 'true', // Default to false
    is_wildcard: searchParams.get('is_wildcard') || '',
    is_parked: searchParams.get('is_parked') || '',
    has_phishlabs: searchParams.get('has_phishlabs') || '',
    phishlabs_incident_status: searchParams.get('phishlabs_incident_status') ? searchParams.get('phishlabs_incident_status').split(',') : [], // Multi-select array for PhishLabs incident status
    source: searchParams.get('source') || '',
    assigned_to_username: searchParams.get('assigned_to_username') || '',
    apex_domain: searchParams.get('apex_domain') || '',
    apex_only: searchParams.get('apex_only') === 'true',
    similarity_protected_domain: searchParams.get('similarity_protected_domain') || '',
    min_similarity_percent: searchParams.get('min_similarity_percent') || '',
    auto_resolve: searchParams.get('auto_resolve') || '',
    created_at_from: searchParams.get('created_at_from') || '',
    created_at_to: searchParams.get('created_at_to') || '',
    updated_at_from: searchParams.get('updated_at_from') || '',
    updated_at_to: searchParams.get('updated_at_to') || '',
    last_closure_at_from: searchParams.get('last_closure_at_from') || '',
    last_closure_at_to: searchParams.get('last_closure_at_to') || ''
  });
  
  // Sort state
  const [sortField, setSortField] = useState(searchParams.get('sort') || 'updated_at');
  const [sortDirection, setSortDirection] = useState(searchParams.get('dir') || 'desc');

  // Batch delete state
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteRelated, setDeleteRelated] = useState(false);
  
  // Batch status update state
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [batchStatus, setBatchStatus] = useState('unchanged');
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [statusComment, setStatusComment] = useState('');
  const [actionTaken, setActionTaken] = useState('');

  // User assignment state
  const [availableUsers, setAvailableUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [batchSelectedAssignedTo, setBatchSelectedAssignedTo] = useState('unchanged');
  const [hasExplicitAssignment, setHasExplicitAssignment] = useState(false);
  const [forceAssignmentOverwrite, setForceAssignmentOverwrite] = useState(false);

  // Batch PhishLabs incident creation state
  const [showPhishlabsModal, setShowPhishlabsModal] = useState(false);
  const [phishlabsAction, setPhishlabsAction] = useState(''); // 'fetch' or 'create'
  const [selectedCatcode, setSelectedCatcode] = useState('');
  const [phishlabsComment, setPhishlabsComment] = useState('Typosquat related to our brand. Please monitor in case of new evidences, please proceed to takedown. Regards');
  const [creatingPhishlabs, setCreatingPhishlabs] = useState(false);
  const [batchReportToGsb, setBatchReportToGsb] = useState(false);
  
  // Export state
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exportColumns, setExportColumns] = useState({
    typo_domain: true,
    status: true,
    assigned_to: true,
    risk_score: true,
    registrar: true,
    country: true,
    ip_address: true,
    is_wildcard: true,
    creation_date: true,
    program_name: true,
    updated_at: true,
    has_phishlabs: true,
    threatstream_id: true,
    threatstream_threat_score: true,
    source: true
  });
  const [exporting, setExporting] = useState(false);
  const [customFilename, setCustomFilename] = useState('');

  // Similarity calculation state
  const [calculatingSimilarity, setCalculatingSimilarity] = useState(false);
  const [similarityMessage, setSimilarityMessage] = useState({ text: '', type: '' });
  const [showSimilarityProgramModal, setShowSimilarityProgramModal] = useState(false);
  const [similarityModalProgram, setSimilarityModalProgram] = useState('');

  // PhishLabs fetch state
  const [phishMessage, setPhishMessage] = useState({ text: '', type: '' });

  // Typosquat batch job state
  const [showTyposquatBatchModal, setShowTyposquatBatchModal] = useState(false);
  const [typosquatBatchLoading, setTyposquatBatchLoading] = useState(false);
  const [typosquatBatchMessage, setTyposquatBatchMessage] = useState({ text: '', type: '' });
  const [batchDomains, setBatchDomains] = useState('');
  const [batchProgramName, setBatchProgramName] = useState('');
  const [batchOriginalDomain, setBatchOriginalDomain] = useState('');
  const [uploadedFile, setUploadedFile] = useState(null);

  // Batch AI analysis (selected rows → K8s job)
  const [showAiAnalysisBatchModal, setShowAiAnalysisBatchModal] = useState(false);
  const [aiBatchLoading, setAiBatchLoading] = useState(false);
  const [batchAiForce, setBatchAiForce] = useState(false);
  const [batchAiModel, setBatchAiModel] = useState('');
  const [aiModels, setAiModels] = useState([]);
  const [aiDefaultModel, setAiDefaultModel] = useState('');
  const [aiModelsLoading, setAiModelsLoading] = useState(false);
  const [aiAnalysisBatchMessage, setAiAnalysisBatchMessage] = useState({ text: '', type: '' });
  
  // Fallback programs state if context doesn't have them
  const [localPrograms, setLocalPrograms] = useState([]);
  const [localProgramsLoading, setLocalProgramsLoading] = useState(false);

  // Distinct values for filters
  const [distinctValues, setDistinctValues] = useState({
    countries: [],
    registrars: [],
    httpStatusCodes: [],
    sources: [],
    assignedToUsernames: [],
    apexDomains: []
  });

  // URL <-> State sync helpers
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

    Object.entries(filters).forEach(([key, value]) => {
      if ((key === 'status' || key === 'phishlabs_incident_status') && Array.isArray(value) && value.length > 0) {
        // Handle array filters - join with commas
        params.set(key, value.join(','));
      } else if (typeof value === 'boolean') {
        // Normal boolean filters - add when true
        if (value) params.set(key, 'true');
      } else if (value) {
        params.set(key, value);
      }
    });

    if (sortField) params.set('sort', sortField);
    if (sortDirection) params.set('dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 100) params.set('page_size', String(pageSize));
    return params;
  }, [filters, sortField, sortDirection, currentPage, pageSize]);

  // Parse URL -> state on location change
  useEffect(() => {
    isSyncingFromUrl.current = true;
    const urlParams = new URLSearchParams(location.search);

    const newFilters = { ...filters };
    const boolKeys = ['has_ip', 'hide_no_registrar', 'apex_only'];
    const arrayKeys = ['status', 'phishlabs_incident_status'];
    Object.keys(newFilters).forEach((k) => {
      const v = urlParams.get(k);
      if (arrayKeys.includes(k)) {
        // Handle array filters
        if (v === null || v === '') {
          if (k === 'status') {
            newFilters[k] = ['new', 'inprogress']; // Default to new and inprogress
          } else if (k === 'phishlabs_incident_status') {
            newFilters[k] = []; // Default to empty (no filter)
          } else {
            newFilters[k] = [];
          }
        } else {
          newFilters[k] = v.split(',');
        }
      } else if (v === null) {
        // Special defaults for certain filters
        if (k === 'hide_no_registrar' || k === 'apex_only') {
          newFilters[k] = false; // Default to false for this filter
        } else if (boolKeys.includes(k)) {
          newFilters[k] = false;
        } else {
          newFilters[k] = '';
        }
      } else {
        if (boolKeys.includes(k)) newFilters[k] = v === 'true'; else newFilters[k] = v;
      }
    });
    setFilters(newFilters);
    setTypoDomainInput(urlParams.get('typo_domain') || '');

    const urlSort = urlParams.get('sort') || 'updated_at';
    if (urlSort !== sortField) setSortField(urlSort);

    const urlDir = urlParams.get('dir') || 'desc';
    if (urlDir !== sortDirection) setSortDirection(urlDir);

    const urlPage = parseInt(urlParams.get('page') || '1', 10);
    if (!Number.isNaN(urlPage) && urlPage > 0 && urlPage !== currentPage) setCurrentPage(urlPage);

    const urlPageSize = parseInt(urlParams.get('page_size') || '100', 10);
    if (!Number.isNaN(urlPageSize) && urlPageSize > 0 && urlPageSize !== pageSize) setPageSize(urlPageSize);

    setTimeout(() => { isSyncingFromUrl.current = false; }, 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  // State -> URL
  useEffect(() => {
    if (isSyncingFromUrl.current) return;
    const desiredParams = buildUrlParamsFromState();
    const desired = serializeParams(desiredParams);
    const current = serializeParams(new URLSearchParams(location.search));
    if (desired !== current) {
      setSearchParams(desiredParams);
    }
  }, [filters, sortField, sortDirection, currentPage, pageSize, setSearchParams, location.search, buildUrlParamsFromState]);

  // Build API filter object
  const buildTypedParams = useCallback(() => {
    const dayStartUtc = (ymd) => (ymd ? `${ymd}T00:00:00.000Z` : undefined);
    const dayEndUtc = (ymd) => (ymd ? `${ymd}T23:59:59.999Z` : undefined);
    const params = {
      search: filters.typo_domain || undefined,
      status: (filters.status && filters.status.length > 0) ? filters.status : undefined,
      registrar_contains: filters.registrar || undefined,
      country: filters.country || undefined,
      ip_contains: filters.ip_address || undefined,
      has_ip: filters.has_ip || undefined,
      is_wildcard: filters.is_wildcard ? (filters.is_wildcard === 'true') : undefined,
      is_parked: filters.is_parked ? (filters.is_parked === 'true') : undefined,
      // http_status: filters.http_status ? parseInt(filters.http_status) : undefined,
      has_phishlabs: filters.has_phishlabs ? (filters.has_phishlabs === 'with') : undefined,
      has_whois_registrar: filters.hide_no_registrar ? true : undefined,
      phishlabs_incident_status: (filters.phishlabs_incident_status && filters.phishlabs_incident_status.length > 0) ? filters.phishlabs_incident_status : undefined,
      source: filters.source === 'no_source' ? 'no_source' : (filters.source || undefined),
      assigned_to_username: filters.assigned_to_username === 'unassigned' ? 'unassigned' : (filters.assigned_to_username || undefined),
      apex_domain: filters.apex_domain || undefined,
      apex_only: filters.apex_only || undefined,
      similarity_protected_domain: filters.similarity_protected_domain || undefined,
      min_similarity_percent: filters.min_similarity_percent ? parseFloat(filters.min_similarity_percent) : undefined,
      auto_resolve: filters.auto_resolve ? (filters.auto_resolve === 'true') : undefined,
      created_at_from: dayStartUtc(filters.created_at_from),
      created_at_to: dayEndUtc(filters.created_at_to),
      updated_at_from: dayStartUtc(filters.updated_at_from),
      updated_at_to: dayEndUtc(filters.updated_at_to),
      last_closure_at_from: dayStartUtc(filters.last_closure_at_from),
      last_closure_at_to: dayEndUtc(filters.last_closure_at_to),
      program: selectedProgram || undefined,
      sort_by: sortField,
      sort_dir: sortDirection,
      page: currentPage,
      page_size: pageSize,
    };
    return params;
  }, [filters, selectedProgram, sortField, sortDirection, currentPage, pageSize]);

  // Fetch findings
  const fetchFindings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await api.findings.typosquat.search(buildTypedParams());
      
      if (response.status === 'success') {
        const findings = response.items || [];
        setFindings(findings);
        setTotalCount(response.pagination?.total_items || 0);
      } else {
        throw new Error(response.message || 'Failed to fetch typosquat findings');
      }
    } catch (err) {
      console.error('Error fetching typosquat findings:', err);
      setError(err.message || 'Failed to load typosquat findings');
      setFindings([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [buildTypedParams]);

  // Fetch distinct values for filters
  const fetchDistinctValues = useCallback(async () => {
    try {
      // Build filter to apply to distinct values
      const programForDistinct = selectedProgram || undefined;
      
      // Only fetch distinct values for fields that have dropdowns
      const [
        countriesResponse,
        registrarsResponse,
        sourcesResponse,
        assignedToUsernamesResponse,
        apexDomainsResponse
      ] = await Promise.all([
        api.findings.typosquat.getDistinctValues('geoip_country', programForDistinct),
        api.findings.typosquat.getDistinctValues('whois_registrar', programForDistinct),
        api.findings.typosquat.getDistinctValues('source', programForDistinct),
        api.findings.typosquat.getDistinctValues('assigned_to_username', programForDistinct),
        api.findings.typosquat.getDistinctValues('typosquat_apex_domain', programForDistinct)
      ]);
      
      let countries = [];
      let registrars = [];
      let sources = [];
      let assignedToUsernames = [];
      let apexDomains = [];

      // Process countries - API returns direct array
      if (Array.isArray(countriesResponse)) {
        countries = countriesResponse.filter(Boolean).sort();
      }

      // Process registrars - API returns direct array
      if (Array.isArray(registrarsResponse)) {
        registrars = registrarsResponse.filter(Boolean).sort();
      }

      // Process sources - API returns direct array
      if (Array.isArray(sourcesResponse)) {
        sources = sourcesResponse.filter(Boolean).sort();
      }

      // Process assigned_to_username - API returns direct array
      if (Array.isArray(assignedToUsernamesResponse)) {
        assignedToUsernames = assignedToUsernamesResponse.filter(Boolean).sort();
      }

      // Process apex domains - API returns direct array
      if (Array.isArray(apexDomainsResponse)) {
        apexDomains = apexDomainsResponse.filter(Boolean).sort();
      }

      setDistinctValues({
        countries,
        registrars,
        sources,
        assignedToUsernames,
        apexDomains
      });
    } catch (err) {
      console.error('Error fetching distinct values:', err);
      // Fallback to empty arrays if all distinct calls fail
      setDistinctValues({
        countries: [],
        registrars: [],
        httpStatusCodes: [],
        sources: [],
        assignedToUsernames: [],
        apexDomains: []
      });
    }
  }, [selectedProgram]);

  // Fetch programs locally if context doesn't have them
  const fetchLocalPrograms = useCallback(async () => {
    if (programs.length === 0) {
      try {
        setLocalProgramsLoading(true);
        const response = await api.programs.getAll();
        if (response.status === 'success' && response.programs_with_permissions) {
          setLocalPrograms(response.programs_with_permissions);
        } else if (response.status === 'success' && response.programs) {
          // Fallback: convert array of names to objects
          setLocalPrograms(response.programs.map(name => ({ name })));
        } else {
          setLocalPrograms([]);
        }
      } catch (err) {
        console.error('Error fetching programs locally:', err);
        setLocalPrograms([]);
      } finally {
        setLocalProgramsLoading(false);
      }
    }
  }, [programs.length]);

  // Fetch all users by getting a large sample of findings to extract user mappings
  const fetchAllUsers = useCallback(async () => {
    try {
      setUsersLoading(true);

      // Fetch users who have access to this program from the new endpoint
      const response = await userManagementAPI.getUsersForAssignment(selectedProgram);

      if (response && Array.isArray(response)) {
        setAvailableUsers(response);
      } else {
        setAvailableUsers([]);
      }
    } catch (err) {
      console.error('Error fetching users:', err);
      setAvailableUsers([]);
    } finally {
      setUsersLoading(false);
    }
  }, [selectedProgram]);

  // Initial data fetch and refetch when dependencies change
  useEffect(() => {
    fetchFindings();
    fetchDistinctValues();
    fetchLocalPrograms();
    fetchAllUsers();
  }, [fetchFindings, fetchDistinctValues, fetchLocalPrograms, fetchAllUsers]);

  // Debounce typo_domain so search runs after user stops typing
  const TYPO_DOMAIN_DEBOUNCE_MS = 400;
  useEffect(() => {
    const t = setTimeout(() => {
      setFilters(prev => {
        if (prev.typo_domain === typoDomainInput) return prev;
        return { ...prev, typo_domain: typoDomainInput };
      });
      setCurrentPage(1);
    }, TYPO_DOMAIN_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [typoDomainInput]);

  // Handle filter changes
  const handleFilterChange = (key, value) => {
    if (key === 'typo_domain') setTypoDomainInput(value);
    setFilters(prev => ({
      ...prev,
      [key]: value
    }));
    setCurrentPage(1); // Reset to first page when filtering
  };

  const STATUS_FILTER_OPTIONS = [
    { value: 'new', label: 'New' },
    { value: 'inprogress', label: 'In Progress' },
    { value: 'resolved', label: 'Resolved' },
    { value: 'dismissed', label: 'Dismissed' },
  ];
  const PHISHLABS_INCIDENT_FILTER_OPTIONS = [
    { value: 'no_incident', label: 'No Incident' },
    { value: 'monitoring', label: 'Monitoring' },
    { value: 'other', label: 'Other' },
  ];

  const renderStatusFilterChecks = (idPrefix) => (
    <div className="d-flex flex-wrap gap-3">
      {STATUS_FILTER_OPTIONS.map(({ value, label }) => (
        <Form.Check
          key={value}
          type="checkbox"
          id={`${idPrefix}-status-${value}`}
          label={label}
          checked={(filters.status || []).includes(value)}
          onChange={(e) => {
            const cur = filters.status || [];
            if (e.target.checked) {
              handleFilterChange('status', [...cur, value]);
            } else {
              handleFilterChange('status', cur.filter((s) => s !== value));
            }
          }}
        />
      ))}
    </div>
  );

  const renderPhishlabsIncidentFilterChecks = (idPrefix) => (
    <div className="d-flex flex-wrap gap-3">
      {PHISHLABS_INCIDENT_FILTER_OPTIONS.map(({ value, label }) => (
        <Form.Check
          key={value}
          type="checkbox"
          id={`${idPrefix}-phishlabs-${value}`}
          label={label}
          checked={(filters.phishlabs_incident_status || []).includes(value)}
          onChange={(e) => {
            const cur = filters.phishlabs_incident_status || [];
            if (e.target.checked) {
              handleFilterChange('phishlabs_incident_status', [...cur, value]);
            } else {
              handleFilterChange('phishlabs_incident_status', cur.filter((s) => s !== value));
            }
          }}
        />
      ))}
    </div>
  );

  // Handle sorting
  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
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
    React.useEffect(() => { setLocalValue(initialValue || ''); }, [initialValue]);
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


  // Get status badge variant
  const getStatusBadgeVariant = (status) => {
    switch (status) {
      case 'new': return 'info';
      case 'inprogress': return 'warning';
      case 'dismissed': return 'danger';
      case 'resolved': return 'success';
      default: return 'info';
    }
  };

  // Get PhishLabs badge variant based on incident status
  const getPhishlabsBadgeVariant = (status) => {
    return status === 'Monitoring' ? 'success' : 'danger';
  };

  // Format status text
  const formatStatus = (status) => {
    switch (status) {
      case 'new': return 'New';
      case 'inprogress': return 'In Progress';
      case 'dismissed': return 'Dismissed';
      case 'resolved': return 'Resolved';
      default: return 'New';
    }
  };

  // Format action taken value for display
  const formatActionTaken = (actionTaken) => {
    switch (actionTaken) {
      case 'takedown_requested': return 'Takedown requested';
      case 'reported_google_safe_browsing': return 'Reported to Google Safe Browsing';
      case 'blocked_firewall': return 'Blocked on firewall';
      case 'monitoring': return 'Monitoring';
      case 'other': return 'Other';
      default: return actionTaken;
    }
  };

  const getAiThreatBadge = (analysis) => {
    if (!analysis) return null;
    const level = analysis.threat_level;
    const variants = { high: 'danger', medium: 'warning', low: 'secondary', benign: 'success' };
    const labels = { high: 'High', medium: 'Medium', low: 'Low', benign: 'Benign' };
    return { variant: variants[level] || 'secondary', label: labels[level] || level };
  };

  const [analyzingIds, setAnalyzingIds] = useState(new Set());

  const handleAiAnalyze = async (findingId) => {
    setAnalyzingIds(prev => new Set(prev).add(findingId));
    try {
      await api.findings.typosquat.aiAnalyze(findingId, { force: true });
      setTimeout(() => fetchFindings(), 5000);
    } catch (err) {
      console.error('AI analysis request failed:', err);
    } finally {
      setTimeout(() => {
        setAnalyzingIds(prev => {
          const next = new Set(prev);
          next.delete(findingId);
          return next;
        });
      }, 5000);
    }
  };

  // Handle finding click
  const handleFindingClick = (finding) => {
    navigate(`/findings/typosquat/details?id=${finding.id}`);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      const allIds = findings.map(finding => finding.id);
      setSelectedItems(new Set(allIds));
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
      
      if (deleteRelated) {
        // When delete_related is enabled, use individual delete calls for each finding
        // This allows each finding to trigger deletion of its related domains
        for (const findingId of selectedIds) {
          try {
            await api.findings.typosquat.delete(findingId, true);
          } catch (err) {
            console.error(`Error deleting finding ${findingId}:`, err);
          }
        }
        
        // Handle errors silently - user will see the refresh
      } else {
        // Standard batch delete for selected findings only
        await api.findings.typosquat.deleteBatch(selectedIds);
      }
      
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      setDeleteRelated(false); // Reset the checkbox
      // Refresh the current page
      fetchFindings();
    } catch (err) {
      console.error('Error deleting typosquat findings:', err);
      alert('Failed to delete typosquat findings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
    }
  };

  const runSimilarityRecalculation = async (programName) => {
    if (!programName) {
      setSimilarityMessage({
        text: 'Please select a program',
        type: 'warning'
      });
      return;
    }

    try {
      setCalculatingSimilarity(true);
      setSimilarityMessage({ text: '', type: '' });

      const response = await api.findings.typosquat.recalculateSimilarities(programName);

      if (response.status === 'success' || response.status === 'warning') {
        const message = response.message ||
          `Similarity calculated: ${response.updated || 0} updated, ${response.failed || 0} failed`;
        setSimilarityMessage({
          text: message,
          type: response.status === 'warning' ? 'warning' : 'success'
        });

        fetchFindings();

        setTimeout(() => {
          setSimilarityMessage({ text: '', type: '' });
        }, 5000);
      } else {
        setSimilarityMessage({
          text: response.error || response.message || 'Failed to calculate similarities',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error calculating similarities:', err);
      setSimilarityMessage({
        text: err.response?.data?.detail || err.message || 'Error calculating similarities. Please try again.',
        type: 'danger'
      });
    } finally {
      setCalculatingSimilarity(false);
    }
  };

  const openSimilarityRecalculation = () => {
    if (calculatingSimilarity) return;
    if (selectedProgram) {
      runSimilarityRecalculation(selectedProgram);
      return;
    }
    const programList = programs.length > 0 ? programs : localPrograms;
    const names = programList
      .map((p) => (typeof p === 'string' ? p : p?.name))
      .filter(Boolean);
    if (names.length === 0) {
      setSimilarityMessage({
        text: 'Select a program in the global header filter, or wait for programs to load.',
        type: 'warning'
      });
      return;
    }
    setSimilarityModalProgram((prev) => (names.includes(prev) ? prev : names[0]));
    setShowSimilarityProgramModal(true);
  };

  const handleConfirmSimilarityProgramModal = () => {
    setShowSimilarityProgramModal(false);
    runSimilarityRecalculation(similarityModalProgram);
  };

  const handleBatchStatusUpdate = async () => {
    if (selectedItems.size === 0) return;

    try {
      setUpdatingStatus(true);
      const selectedIds = Array.from(selectedItems);

      // Get selected findings data for validation
      const selectedFindings = findings.filter(f => selectedIds.includes(f.id));

      // Validate batch status transition
      const validationError = validateBatchStatusTransition(
        selectedFindings,
        batchStatus,
        hasExplicitAssignment ? batchSelectedAssignedTo : undefined,
        statusComment
      );

      if (validationError) {
        alert(validationError);
        setUpdatingStatus(false);
        return;
      }

      // Handle assignment using dropdown selection only
      let assignedTo;

      if (hasExplicitAssignment) {
        if (batchSelectedAssignedTo === 'unchanged') {
          // User chose to keep current assignments
          assignedTo = undefined;
        } else {
          // User explicitly chose from dropdown - empty string means "Unassigned"
          assignedTo = batchSelectedAssignedTo || null; // Empty string becomes null for unassign
        }
      } else {
        // No assignment change requested
        assignedTo = undefined;
      }

      const response = await api.findings.typosquat.updateStatusBatch(
        selectedIds,
        batchStatus,
        false, // No longer using takeOwnership
        null, // No longer using legacy user_id
        statusComment,
        actionTaken,
        assignedTo,
        forceAssignmentOverwrite
      );

      if (response.status === 'success') {
        setShowStatusModal(false);
        setSelectedItems(new Set());
        setBatchStatus('unchanged'); // Reset status
        setBatchSelectedAssignedTo('unchanged'); // Reset assignment
        setHasExplicitAssignment(false); // Reset assignment flag
        setForceAssignmentOverwrite(false); // Reset assignment overwrite flag
        setStatusComment(''); // Reset comment
        setActionTaken(''); // Reset action taken
        // Refresh the current page
        fetchFindings();
      }
    } catch (err) {
      console.error('Error updating status for typosquat findings:', err);
      alert('Failed to update status for typosquat findings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleBatchPhishlabsOpen = () => {
    if (selectedItems.size === 0) return;
    setPhishlabsAction('fetch');
    setShowPhishlabsModal(true);
  };

  const handleConfirmPhishlabsAction = async () => {
    if (phishlabsAction === 'fetch') {
      await handleExecuteBatchPhishlabsFetch();
    } else if (phishlabsAction === 'create') {
      await handleExecuteBatchPhishlabsIncidents();
    } else if (phishlabsAction === 'takedown') {
      await handleExecuteBatchPhishlabsTakedown();
    }
  };

  const handleExecuteBatchPhishlabsTakedown = async () => {
    try {
      setCreatingPhishlabs(true);
      setPhishMessage({ text: '', type: '' });

      const selectedIds = Array.from(selectedItems);
      const response = await api.findings.typosquat.startPhishlabsTakedownBatch(selectedIds);

      const msgType =
        response.status === 'success'
          ? 'success'
          : response.status === 'partial_success'
            ? 'warning'
            : 'danger';

      setPhishMessage({
        text:
          response.message ||
          `PhishLabs takedown: ${response.success_count ?? 0} succeeded, ${response.error_count ?? 0} failed`,
        type: msgType
      });

      fetchFindings();
    } catch (err) {
      console.error('Error starting PhishLabs takedown batch:', err);
      setPhishMessage({
        text: err.response?.data?.detail || err.message || 'Error requesting PhishLabs takedown',
        type: 'danger'
      });
    } finally {
      setCreatingPhishlabs(false);
      setShowPhishlabsModal(false);
    }
  };

  const handleExecuteBatchPhishlabsFetch = async () => {
    try {
      setCreatingPhishlabs(true);
      setPhishMessage({ text: '', type: '' });

      const selectedIds = Array.from(selectedItems);
      const response = await api.findings.typosquat.createBatchPhishlabsJob(selectedIds);

      if (response.status === 'success') {
        const jobId = response.job_id;

        setPhishMessage({
          text: `PhishLabs batch job started (ID: ${jobId}). Processing ${response.total_findings} findings...`,
          type: 'info'
        });

        // Start polling for job status
        pollJobStatus(jobId);
      } else {
        setPhishMessage({
          text: response.message || 'Failed to start PhishLabs batch job',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error starting PhishLabs batch job:', err);
      setPhishMessage({
        text: err.response?.data?.detail || err.message || 'Error starting PhishLabs batch job',
        type: 'danger'
      });
    } finally {
      setCreatingPhishlabs(false);
      setShowPhishlabsModal(false);
    }
  };

  const handleExecuteBatchPhishlabsIncidents = async () => {
    if (!selectedCatcode) {
      alert('Please select a category code');
      return;
    }

    try {
      setCreatingPhishlabs(true);
      setPhishMessage({ text: '', type: '' });

      const selectedIds = Array.from(selectedItems);
      const response = await api.findings.typosquat.createBatchPhishlabsIncidentsJob(selectedIds, selectedCatcode, phishlabsComment, batchReportToGsb);

      if (response.status === 'success') {
        const jobId = response.job_id;

        setPhishMessage({
          text: `PhishLabs incidents batch job started (ID: ${jobId}). Creating incidents for ${response.total_findings} findings...`,
          type: 'info'
        });

        // Start polling for job status
        pollJobStatus(jobId);
      } else {
        setPhishMessage({
          text: response.message || 'Failed to start PhishLabs incidents batch job',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error starting PhishLabs incidents batch job:', err);
      setPhishMessage({
        text: err.response?.data?.detail || err.message || 'Error starting PhishLabs incidents batch job',
        type: 'danger'
      });
    } finally {
      setCreatingPhishlabs(false);
      setShowPhishlabsModal(false);
      setSelectedCatcode('');
      setPhishlabsComment('');
      setBatchReportToGsb(false);
    }
  };

  const handleBatchTyposquatAnalysis = async () => {
    if (!batchDomains.trim() && !uploadedFile) {
      setTyposquatBatchMessage({
        text: 'Please enter domains or upload a file to analyze',
        type: 'warning'
      });
      return;
    }

    try {
      setTyposquatBatchLoading(true);
      setTyposquatBatchMessage({ text: '', type: '' });

      let domainsToAnalyze = [];

      // Helper function to normalize domains by replacing [.] with .
      const normalizeDomain = (domain) => {
        return domain.replace(/\[.\]/g, '.');
      };

      // Parse domains from text input
      if (batchDomains.trim()) {
        domainsToAnalyze = batchDomains
          .split(/[\n,]/)
          .map(domain => normalizeDomain(domain.trim()))
          .filter(domain => domain.length > 0);
      }

      // Parse domains from uploaded file
      if (uploadedFile) {
        try {
          const text = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (event) => resolve(event.target.result);
            reader.onerror = () => reject(new Error('Failed to read file'));
            reader.readAsText(uploadedFile);
          });

          const fileDomains = text
            .split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0 && !line.startsWith('#'))
            .map(domain => normalizeDomain(domain));

          domainsToAnalyze = [...domainsToAnalyze, ...fileDomains];
        } catch (e) {
          setTyposquatBatchMessage({
            text: `Error reading uploaded file: ${e.message}`,
            type: 'danger'
          });
          setTyposquatBatchLoading(false);
          return;
        }
      }

      if (domainsToAnalyze.length === 0) {
        setTyposquatBatchMessage({
          text: 'No valid domains found in input',
          type: 'warning'
        });
        setTyposquatBatchLoading(false);
        return;
      }
      
      const response = await api.findings.typosquat.createBatchTyposquatJob(
        domainsToAnalyze, 
        batchProgramName || selectedProgram,
        batchOriginalDomain || null
      );
      
      if (response.status === 'started') {
        const workflowId = response.workflow_id;
        
        setTyposquatBatchMessage({
          text: (
            <span>
              Typosquat workflow started (ID: {workflowId}). Analyzing {domainsToAnalyze.length} domains...{' '}
              <a href={`/workflows/status/${workflowId}`} target="_blank" rel="noopener noreferrer">
                View workflow status
              </a>
            </span>
          ),
          type: 'success'
        });
        
        // Close modal
        setShowTyposquatBatchModal(false);
        setBatchDomains('');
        setBatchProgramName('');
        setBatchOriginalDomain('');
        setUploadedFile(null); // Clear uploaded file
      } else {
        setTyposquatBatchMessage({
          text: response.message || 'Failed to start typosquat workflow',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error starting typosquat batch job:', err);
      setTyposquatBatchMessage({
        text: err.response?.data?.detail || err.message || 'Error starting typosquat batch job',
        type: 'danger'
      });
    } finally {
      setTyposquatBatchLoading(false);
    }
  };

  const pollJobStatus = async (jobId) => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await jobAPI.getStatus(jobId);
        const statusResponse = response.job; // Extract job data from response
        
        if (statusResponse.status === 'completed') {
          clearInterval(pollInterval);
          
          // Parse results if it's a JSON string
          let results = statusResponse.results;
          if (typeof results === 'string') {
            try {
              results = JSON.parse(results);
            } catch (e) {
              console.error('Error parsing job results:', e);
              results = {};
            }
          }
          
          setPhishMessage({
            text: `PhishLabs batch job completed: ${results?.success_count || 0} successful, ${results?.error_count || 0} errors`,
            type: 'success'
          });
          
          // Refresh the findings list
          fetchFindings();
          
          // Clear message after 10 seconds
          setTimeout(() => {
            setPhishMessage({ text: '', type: '' });
          }, 10000);
          
        } else if (statusResponse.status === 'failed') {
          clearInterval(pollInterval);
          setPhishMessage({
            text: `PhishLabs batch job failed: ${statusResponse.message}`,
            type: 'danger'
          });
          
        } else {
          // Still running, update progress message
          setPhishMessage({
            text: `PhishLabs batch job running... ${statusResponse.progress}% complete`,
            type: 'info'
          });
        }
      } catch (err) {
        console.error('Error polling job status:', err);
        clearInterval(pollInterval);
        setPhishMessage({
          text: 'Error checking job status',
          type: 'danger'
        });
      }
    }, 5000); // Poll every 5 seconds
  };

  const pollAiAnalysisBatchJobStatus = (jobId) => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await jobAPI.getStatus(jobId);
        const statusResponse = response.job;

        if (statusResponse.status === 'completed') {
          clearInterval(pollInterval);
          let results = statusResponse.results;
          if (typeof results === 'string') {
            try {
              results = JSON.parse(results);
            } catch (e) {
              console.error('Error parsing AI batch job results:', e);
              results = {};
            }
          }
          setAiAnalysisBatchMessage({
            text: `AI analysis batch completed: ${results?.success_count ?? 0} successful, ${results?.error_count ?? 0} errors`,
            type: 'success',
          });
          fetchFindings();
          setTimeout(() => setAiAnalysisBatchMessage({ text: '', type: '' }), 10000);
        } else if (statusResponse.status === 'failed') {
          clearInterval(pollInterval);
          setAiAnalysisBatchMessage({
            text: `AI analysis batch failed: ${statusResponse.message}`,
            type: 'danger',
          });
        } else {
          setAiAnalysisBatchMessage({
            text: `AI analysis batch running... ${statusResponse.progress}% complete`,
            type: 'info',
          });
        }
      } catch (err) {
        console.error('Error polling AI batch job status:', err);
        clearInterval(pollInterval);
        setAiAnalysisBatchMessage({
          text: 'Error checking AI batch job status',
          type: 'danger',
        });
      }
    }, 5000);
  };

  const fetchAiModelsForBatch = useCallback(async () => {
    setAiModelsLoading(true);
    try {
      const data = await api.ai.getModels();
      const models = data.models || [];
      setAiModels(models);
      const rawDef = data.default_model;
      const def =
        rawDef != null && String(rawDef).trim() !== '' ? String(rawDef).trim() : '';
      setAiDefaultModel(def);
      const names = new Set(models.map((m) => m.name).filter(Boolean));
      setBatchAiModel(def && names.has(def) ? def : '');
    } catch (err) {
      setAiModels([]);
      setAiDefaultModel('');
      setBatchAiModel('');
    } finally {
      setAiModelsLoading(false);
    }
  }, []);

  const handleOpenAiAnalysisBatchModal = () => {
    if (!isAdmin() || selectedItems.size === 0) return;
    setBatchAiForce(false);
    setShowAiAnalysisBatchModal(true);
    fetchAiModelsForBatch();
  };

  const handleExecuteAiAnalysisBatch = async () => {
    if (!isAdmin() || selectedItems.size === 0) return;
    if (selectedItems.size > AI_ANALYSIS_BATCH_MAX_FINDINGS) return;
    setAiBatchLoading(true);
    setAiAnalysisBatchMessage({ text: '', type: '' });
    try {
      const findingIds = Array.from(selectedItems);
      const modelParam = batchAiModel || null;
      const result = await api.findings.typosquat.aiAnalysisBatchForFindingIds({
        finding_ids: findingIds,
        force: batchAiForce,
        model: modelParam,
      });
      const jobId = result?.job_id;
      const n = result?.finding_ids?.length ?? findingIds.length;
      setShowAiAnalysisBatchModal(false);
      setBatchAiForce(false);
      setBatchAiModel('');
      setAiAnalysisBatchMessage({
        text: (
          <span>
            AI analysis batch started for {n} finding(s). Job ID: {jobId}.{' '}
            <Link to="/workflows/status?tab=jobs">View jobs</Link>
          </span>
        ),
        type: 'info',
      });
      if (jobId) {
        pollAiAnalysisBatchJobStatus(jobId);
      }
    } catch (err) {
      setAiAnalysisBatchMessage({
        text: err.response?.data?.detail || err.message || 'Failed to start AI analysis batch',
        type: 'danger',
      });
    } finally {
      setAiBatchLoading(false);
    }
  };

  const handleExport = () => {
    setShowExportModal(true);
  };

  const handleExportConfirm = async () => {
    try {
      setExporting(true);
      
      const exportParams = { ...buildTypedParams(), page: 1, page_size: 10000 };
      const response = await api.findings.typosquat.search(exportParams);
      
      if (response.status === 'success') {
        const rawData = response.items || [];
        
        let exportData;
        let fileExtension;
        let mimeType;
        
        if (exportFormat === 'txt') {
          // Plain text export - only typo domains
          exportData = rawData.map(item => item.typo_domain).join('\n');
          fileExtension = 'txt';
          mimeType = 'text/plain';
        } else if (exportFormat === 'csv') {
          // CSV export with selected columns
          const selectedCols = Object.keys(exportColumns).filter(col => exportColumns[col]);
          const headers = selectedCols.join(',');
          const rows = rawData.map(item => {
            return selectedCols.map(col => {
              let value;
              // Handle nested properties
              if (col === 'risk_score') {
                value = item.risk_score;
              } else if (col === 'registrar') {
                value = item.whois_registrar;
              } else if (col === 'country') {
                value = item.geoip_country;
              } else if (col === 'ip_address') {
                value = Array.isArray(item.dns_a_records) ? item.dns_a_records[0] : undefined;
              } else if (col === 'is_wildcard') {
                value = item.is_wildcard;
              } else if (col === 'creation_date') {
                value = item.whois_creation_date;
              } else if (col === 'has_phishlabs') {
                value = (item.phishlabs_data && item.phishlabs_data.incident_id) ? 'Yes' : 'No';
              } else if (col === 'threatstream_id') {
                try {
                  const threatstreamData = item.threatstream_data || null;
                  value = threatstreamData?.id || '';
                } catch (e) {
                  value = '';
                }
              } else if (col === 'threatstream_threat_score') {
                try {
                  const threatstreamData = item.threatstream_data || null;
                  value = threatstreamData?.threatscore || '';
                } catch (e) {
                  value = '';
                }
              } else {
                value = item[col];
              }
              
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
                if (col === 'registrar') {
                  filtered[col] = item.whois_registrar;
                } else if (col === 'country') {
                  filtered[col] = item.geoip_country;
                } else if (col === 'ip_address') {
                  filtered[col] = Array.isArray(item.dns_a_records) ? item.dns_a_records[0] : undefined;
                // } else if (col === 'http_status') {
                //   filtered[col] = item.http_status_code;
                } else if (col === 'is_wildcard') {
                  filtered[col] = item.is_wildcard;
                } else if (col === 'creation_date') {
                  filtered[col] = item.whois_creation_date;
                } else if (col === 'has_phishlabs') {
                  filtered[col] = (item.phishlabs_data && item.phishlabs_data.incident_id) ? 'Yes' : 'No';
                } else if (col === 'threatstream_id') {
                  try {
                    const threatstreamData = item.threatstream_data || null;
                    filtered[col] = threatstreamData?.id || null;
                  } catch (e) {
                    filtered[col] = null;
                  }
                } else if (col === 'threatstream_threat_score') {
                  try {
                    const threatstreamData = item.threatstream_data || null;
                    filtered[col] = threatstreamData?.threatscore || null;
                  } catch (e) {
                    filtered[col] = null;
                  }
                } else {
                  filtered[col] = item[col];
                }
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
          : `typosquat_findings_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
        
        const linkElement = document.createElement('a');
        linkElement.setAttribute('href', dataUri);
        linkElement.setAttribute('download', exportFileDefaultName);
        linkElement.click();
        
        setShowExportModal(false);
      } else {
        throw new Error(response.message || 'Failed to export typosquat findings');
      }
      
    } catch (err) {
      console.error('Error exporting typosquat findings:', err);
      alert('Failed to export typosquat findings: ' + err.message);
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

  // Handle file upload
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (file) {
      if (file.type === 'text/plain' || file.name.endsWith('.txt')) {
        setUploadedFile(file);
      } else {
        setTyposquatBatchMessage({
          text: 'Please upload a .txt file only',
          type: 'warning'
        });
        event.target.value = ''; // Clear the input
      }
    }
  };

  // Clear uploaded file
  const clearUploadedFile = () => {
    setUploadedFile(null);
    // Clear the file input
    const fileInput = document.getElementById('domain-file-upload');
    if (fileInput) {
      fileInput.value = '';
    }
  };

  // Handle opening the typosquat batch modal
  const handleOpenTyposquatBatchModal = () => {
    // Preselect the program from global filter if available
    if (selectedProgram && !batchProgramName) {
      setBatchProgramName(selectedProgram);
    }
    setShowTyposquatBatchModal(true);
  };

  // Use context programs or fallback to local programs
  const availablePrograms = programs.length > 0 ? programs : localPrograms;
  const programsLoading = localProgramsLoading;
  
  // Debug: Log which programs are being used

  // Calculate pagination
  const totalPages = Math.ceil(totalCount / pageSize);
  const startItem = (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalCount);

  return (
    <Container fluid className="p-4">
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h1>🔤 Typosquat Findings</h1>
        <div className="d-flex align-items-center">
          <Badge bg="primary" className="fs-6 me-3">
            {totalCount} total
          </Badge>
          <Button
            variant="outline-success"
            size="sm"
            onClick={handleExport}
            className="me-2"
          >
            <i className="bi bi-download"></i> Export
          </Button>
          <Button
            variant="outline-secondary"
            size="sm"
            onClick={openSimilarityRecalculation}
            disabled={calculatingSimilarity}
            className="me-2"
            title={
              selectedProgram
                ? 'Calculate similarity scores with protected domains for all typosquat domains in the program selected in the global filter'
                : 'Calculate similarities for all typosquat domains in a program (choose program if none is selected in the global filter)'
            }
          >
            {calculatingSimilarity ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Calculating...
              </>
            ) : (
              <>
                <i className="bi bi-shield-check"></i> Calculate Similarities
              </>
            )}
          </Button>
          {selectedItems.size > 0 && (
            <Button
              variant="outline-info"
              size="sm"
              onClick={handleBatchPhishlabsOpen}
              disabled={creatingPhishlabs}
              className="me-2"
            >
              {creatingPhishlabs ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Working...
                </>
              ) : (
                <>
                  <i className="bi bi-shield-lock"></i> PhishLabs actions ({selectedItems.size})
                </>
              )}
            </Button>
          )}
          {selectedItems.size > 0 && isAdmin() && (
            <Button
              variant="outline-primary"
              size="sm"
              onClick={handleOpenAiAnalysisBatchModal}
              disabled={aiBatchLoading}
              className="me-2"
              title={
                selectedItems.size > AI_ANALYSIS_BATCH_MAX_FINDINGS
                  ? `Select at most ${AI_ANALYSIS_BATCH_MAX_FINDINGS} findings for one batch`
                  : undefined
              }
            >
              <i className="bi bi-robot" aria-hidden /> AI analysis ({selectedItems.size}
              {selectedItems.size > AI_ANALYSIS_BATCH_MAX_FINDINGS ? ` — max ${AI_ANALYSIS_BATCH_MAX_FINDINGS}` : ''})
            </Button>
          )}
          {selectedItems.size > 0 && (
            <Button
              variant="outline-warning"
              size="sm"
              onClick={() => setShowStatusModal(true)}
              disabled={updatingStatus}
              className="me-2"
            >
              {updatingStatus ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Updating...
                </>
              ) : (
                <>
                  <i className="bi bi-tag"></i> Update Status ({selectedItems.size})
                </>
              )}
            </Button>
          )}
          <Button
            variant="outline-success"
            size="sm"
            onClick={handleOpenTyposquatBatchModal}
            className="me-2"
          >
            <i className="bi bi-search"></i> Analyze Domains
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
      </div>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      {similarityMessage.text && (
        <Alert variant={similarityMessage.type} className="mb-4">
          {similarityMessage.text}
        </Alert>
      )}

      {phishMessage.text && (
        <Alert variant={phishMessage.type} className="mb-4">
          {phishMessage.text}
        </Alert>
      )}

      {typosquatBatchMessage.text && (
        <Alert variant={typosquatBatchMessage.type} className="mb-4">
          {typosquatBatchMessage.text}
        </Alert>
      )}

      {aiAnalysisBatchMessage.text && (
        <Alert variant={aiAnalysisBatchMessage.type} className="mb-4">
          {aiAnalysisBatchMessage.text}
        </Alert>
      )}

      {/* Filters (kept for advanced filters below); core column filters moved to header popovers */}
      <Row className="mb-4">
        <Col>
          <Accordion>
            <Accordion.Item eventKey="0">
              <Accordion.Header>
                <span className="d-flex align-items-center gap-2">
                  <i className="bi bi-search" aria-hidden />
                  Search &amp; Filter Options
                </span>
              </Accordion.Header>
              <Accordion.Body className="pt-3">
                <h6 className="text-secondary text-uppercase small fw-semibold mb-0">Search &amp; assignment</h6>
                <Row className="g-3 mt-2">
                  <Col md={4}>
                    <Form.Group className="mb-0">
                      <Form.Label>Typo Domain</Form.Label>
                      <Form.Control
                        type="text"
                        placeholder="Search typo domain..."
                        value={typoDomainInput}
                        onChange={(e) => setTypoDomainInput(e.target.value)}
                      />
                    </Form.Group>
                  </Col>
                  <Col md={4}>
                    <Form.Group className="mb-0">
                      <Form.Label>Apex Domain</Form.Label>
                      <Form.Select
                        value={filters.apex_domain}
                        onChange={(e) => handleFilterChange('apex_domain', e.target.value)}
                      >
                        <option value="">All Apex Domains</option>
                        {distinctValues.apexDomains.map(apexDomain => (
                          <option key={apexDomain} value={apexDomain}>{apexDomain}</option>
                        ))}
                      </Form.Select>
                      <Form.Check
                        type="checkbox"
                        label="Apex domains only (hide subdomains)"
                        checked={filters.apex_only}
                        onChange={(e) => handleFilterChange('apex_only', e.target.checked)}
                        className="mt-2"
                      />
                    </Form.Group>
                  </Col>
                  <Col md={4}>
                    <Form.Group className="mb-0">
                      <Form.Label>Assigned To</Form.Label>
                      <Form.Select
                        value={filters.assigned_to_username}
                        onChange={(e) => handleFilterChange('assigned_to_username', e.target.value)}
                      >
                        <option value="">All Users</option>
                        <option value="unassigned">Unassigned</option>
                        {distinctValues.assignedToUsernames.map(username => (
                          <option key={username} value={username}>{username}</option>
                        ))}
                      </Form.Select>
                    </Form.Group>
                  </Col>
                </Row>

                <hr className="my-3" />
                <h6 className="text-secondary text-uppercase small fw-semibold mb-0">Date range</h6>
                <Row className="g-3 mt-2">
                  <Col md={4}>
                    <Form.Group className="mb-0">
                      <Form.Label>Created at</Form.Label>
                      <div className="d-flex flex-wrap align-items-center gap-2">
                        <Form.Control
                          type="date"
                          value={filters.created_at_from}
                          onChange={(e) => handleFilterChange('created_at_from', e.target.value)}
                          aria-label="Created from"
                        />
                        <span className="text-muted small">to</span>
                        <Form.Control
                          type="date"
                          value={filters.created_at_to}
                          onChange={(e) => handleFilterChange('created_at_to', e.target.value)}
                          aria-label="Created to"
                        />
                      </div>
                    </Form.Group>
                  </Col>
                  <Col md={4}>
                    <Form.Group className="mb-0">
                      <Form.Label>Updated at</Form.Label>
                      <div className="d-flex flex-wrap align-items-center gap-2">
                        <Form.Control
                          type="date"
                          value={filters.updated_at_from}
                          onChange={(e) => handleFilterChange('updated_at_from', e.target.value)}
                          aria-label="Updated from"
                        />
                        <span className="text-muted small">to</span>
                        <Form.Control
                          type="date"
                          value={filters.updated_at_to}
                          onChange={(e) => handleFilterChange('updated_at_to', e.target.value)}
                          aria-label="Updated to"
                        />
                      </div>
                    </Form.Group>
                  </Col>
                  <Col md={4}>
                    <Form.Group className="mb-0">
                      <Form.Label>Last closure (resolved / dismissed)</Form.Label>
                      <div className="d-flex flex-wrap align-items-center gap-2">
                        <Form.Control
                          type="date"
                          value={filters.last_closure_at_from}
                          onChange={(e) => handleFilterChange('last_closure_at_from', e.target.value)}
                          aria-label="Last closure from"
                        />
                        <span className="text-muted small">to</span>
                        <Form.Control
                          type="date"
                          value={filters.last_closure_at_to}
                          onChange={(e) => handleFilterChange('last_closure_at_to', e.target.value)}
                          aria-label="Last closure to"
                        />
                      </div>
                      <Form.Text className="text-muted">UTC day range on last resolve/dismiss time.</Form.Text>
                    </Form.Group>
                  </Col>
                </Row>

                <hr className="my-3" />
                <h6 className="text-secondary text-uppercase small fw-semibold mb-0">Network &amp; source</h6>
                <Row className="g-3 mt-2">
                  <Col md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>IP Address</Form.Label>
                      <Form.Control
                        type="text"
                        placeholder="Filter by IP..."
                        value={filters.ip_address}
                        onChange={(e) => handleFilterChange('ip_address', e.target.value)}
                      />
                      <Form.Check
                        type="checkbox"
                        label="Has IP Address"
                        checked={filters.has_ip}
                        onChange={(e) => handleFilterChange('has_ip', e.target.checked)}
                        className="mt-2"
                      />
                    </Form.Group>
                  </Col>
                  <Col md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Source</Form.Label>
                      <Form.Select
                        value={filters.source}
                        onChange={(e) => handleFilterChange('source', e.target.value)}
                      >
                        <option value="">All Sources</option>
                        <option value="no_source">No Source</option>
                        {distinctValues.sources.map(source => (
                          <option key={source} value={source}>{source}</option>
                        ))}
                      </Form.Select>
                    </Form.Group>
                  </Col>
                </Row>

                <hr className="my-3" />
                <h6 className="text-secondary text-uppercase small fw-semibold mb-0">Status &amp; PhishLabs</h6>
                <Row className="g-3 mt-2">
                  <Col md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Status</Form.Label>
                      {renderStatusFilterChecks('accordion')}
                    </Form.Group>
                  </Col>
                  <Col md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>PhishLabs incident</Form.Label>
                      {renderPhishlabsIncidentFilterChecks('accordion')}
                    </Form.Group>
                  </Col>
                </Row>

                <hr className="my-3" />
                <h6 className="text-secondary text-uppercase small fw-semibold mb-0">Domain attributes</h6>
                <Row className="g-3 mt-2">
                  <Col lg={3} md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Country</Form.Label>
                      <Form.Select
                        value={filters.country}
                        onChange={(e) => handleFilterChange('country', e.target.value)}
                      >
                        <option value="">All Countries</option>
                        {distinctValues.countries.map(country => (
                          <option key={country} value={country}>{country}</option>
                        ))}
                      </Form.Select>
                    </Form.Group>
                  </Col>
                  <Col lg={3} md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Registrar</Form.Label>
                      <Form.Select
                        value={filters.registrar}
                        onChange={(e) => handleFilterChange('registrar', e.target.value)}
                      >
                        <option value="">All Registrars</option>
                        {distinctValues.registrars.map(registrar => (
                          <option key={registrar} value={registrar}>{registrar}</option>
                        ))}
                      </Form.Select>
                      <Form.Check
                        type="checkbox"
                        label="Hide Without Registrar"
                        checked={filters.hide_no_registrar}
                        onChange={(e) => handleFilterChange('hide_no_registrar', e.target.checked)}
                        className="mt-2"
                      />
                    </Form.Group>
                  </Col>
                  <Col lg={3} md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Wildcard Status</Form.Label>
                      <Form.Select
                        value={filters.is_wildcard}
                        onChange={(e) => handleFilterChange('is_wildcard', e.target.value)}
                      >
                        <option value="">All Domains</option>
                        <option value="true">Wildcard Domains</option>
                        <option value="false">Normal Domains</option>
                      </Form.Select>
                    </Form.Group>
                  </Col>
                  <Col lg={3} md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Parked Domain Status</Form.Label>
                      <Form.Select
                        value={filters.is_parked}
                        onChange={(e) => handleFilterChange('is_parked', e.target.value)}
                      >
                        <option value="">All Domains</option>
                        <option value="true">Parked Domains</option>
                        <option value="false">Non-Parked Domains</option>
                      </Form.Select>
                    </Form.Group>
                  </Col>
                </Row>

                <hr className="my-3" />
                <h6 className="text-secondary text-uppercase small fw-semibold mb-0">Similarity &amp; auto-resolve</h6>
                <Row className="g-3 mt-2">
                  <Col lg={4} md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Protected Domain Similarity</Form.Label>
                      <Form.Select
                        value={filters.similarity_protected_domain}
                        onChange={(e) => handleFilterChange('similarity_protected_domain', e.target.value)}
                        disabled={!selectedProgram}
                      >
                        <option value="">All Protected Domains</option>
                        {(() => {
                          const currentProgram = availablePrograms.find(p => p.name === selectedProgram);
                          const protectedDomains = currentProgram?.protected_domains || [];
                          return protectedDomains.map(domain => (
                            <option key={domain} value={domain}>{domain}</option>
                          ));
                        })()}
                      </Form.Select>
                      {!selectedProgram && (
                        <Form.Text className="text-muted">Select a program first</Form.Text>
                      )}
                    </Form.Group>
                  </Col>
                  <Col lg={4} md={6}>
                    <Form.Group className="mb-0">
                      <Form.Label>Min Similarity %</Form.Label>
                      <Form.Control
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        placeholder="e.g. 60"
                        value={filters.min_similarity_percent}
                        onChange={(e) => {
                          // Only allow numeric values
                          const value = e.target.value.replace(/[^0-9]/g, '');
                          if (value === '' || (parseInt(value) >= 0 && parseInt(value) <= 100)) {
                            handleFilterChange('min_similarity_percent', value);
                          }
                        }}
                      />
                      <Form.Text className="text-muted">0-100</Form.Text>
                    </Form.Group>
                  </Col>
                  <Col lg={4} md={12}>
                    <Form.Group className="mb-0">
                      <Form.Label>Would Auto-Resolve</Form.Label>
                      <Form.Select
                        value={filters.auto_resolve}
                        onChange={(e) => handleFilterChange('auto_resolve', e.target.value)}
                      >
                        <option value="">All</option>
                        <option value="true">Yes</option>
                        <option value="false">No</option>
                      </Form.Select>
                    </Form.Group>
                  </Col>
                </Row>
                <Row className="g-3 mt-3">
                <Col md={12} className="d-flex justify-content-end">
                    <Button variant="outline-secondary" onClick={() => {
                      setTypoDomainInput('');
                      setFilters({
                        typo_domain: '',
                        status: ['new', 'inprogress'], // Reset to default (new and inprogress)
                        country: '',
                        registrar: '',
                        min_risk_score: '',
                        max_risk_score: '',
                        ip_address: '',
                        has_ip: false,
                        hide_no_registrar: false, // Reset to default (false)
                        is_wildcard: '',
                        is_parked: '',
                        has_phishlabs: '',
                        phishlabs_incident_status: [], // Reset to empty (no filter)
                        source: '',
                        assigned_to_username: '',
                        apex_domain: '',
                        apex_only: false,
                        similarity_protected_domain: '',
                        min_similarity_percent: '',
                        auto_resolve: '',
                        created_at_from: '',
                        created_at_to: '',
                        updated_at_from: '',
                        updated_at_to: '',
                        last_closure_at_from: '',
                        last_closure_at_to: ''
                      });
                    }}>
                      Clear
                    </Button>
                  </Col>
                </Row>
              </Accordion.Body>
            </Accordion.Item>
          </Accordion>
        </Col>
      </Row>

      {/* Results */}
      <Card>
        <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
          {totalCount > 0 && (
            <small className="text-muted">
              Showing {startItem}-{endItem} of {totalCount} findings
            </small>
          )}
          <div className="d-flex align-items-center ms-auto">
            <Button variant="link" size="sm" className="me-2 p-0" onClick={() => {
              setTypoDomainInput('');
              setFilters({
                typo_domain: '',
                status: ['new', 'inprogress'],
                country: '',
                registrar: '',
                ip_address: '',
                has_ip: false,
                hide_no_registrar: false,
                is_wildcard: '',
                is_parked: '',
                has_phishlabs: '',
                phishlabs_incident_status: [],
                source: '',
                assigned_to_username: '',
                apex_domain: '',
                apex_only: false,
                similarity_protected_domain: '',
                min_similarity_percent: '',
                auto_resolve: '',
                created_at_from: '',
                created_at_to: '',
                updated_at_from: '',
                updated_at_to: '',
                last_closure_at_from: '',
                last_closure_at_to: ''
              });
              setCurrentPage(1);
            }}>Reset filters</Button>
          </div>
        </Card.Header>
        <Card.Body className="p-0">
          {loading ? (
            <div className="text-center p-4">
              <Spinner animation="border" role="status">
                <span className="visually-hidden">Loading...</span>
              </Spinner>
            </div>
          ) : findings.length === 0 ? (
            <div className="text-center p-4">
              <p className="text-muted mb-0">No typosquat findings found matching your criteria.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <Table hover className="mb-0">
                <thead className="table-light">
                  <tr>
                    <th>
                      <Form.Check
                        type="checkbox"
                        checked={selectedItems.size === findings.length && findings.length > 0}
                        onChange={(e) => handleSelectAll(e.target.checked)}
                      />
                    </th>
                    <th style={{cursor: 'pointer'}} onClick={() => handleSort('typo_domain')}>
                      <div className="d-flex align-items-center gap-2">
                        <span>Typo Domain {getSortIcon('typo_domain')}</span>
                        <ColumnFilterPopover id="filter-typo-domain" ariaLabel="Filter by typo domain" isActive={!!filters.typo_domain}>
                          <InlineTextFilter
                            label="Typo domain"
                            placeholder="Search typo domain..."
                            initialValue={filters.typo_domain}
                            onApply={(val) => handleFilterChange('typo_domain', val)}
                            onClear={() => handleFilterChange('typo_domain', '')}
                          />
                        </ColumnFilterPopover>
                      </div>
                    </th>
                    <th style={{cursor: 'pointer'}} onClick={() => handleSort('status')}>
                      <div className="d-flex align-items-center gap-2">
                        <span>Status {getSortIcon('status')}</span>
                        <ColumnFilterPopover id="filter-status" ariaLabel="Filter by status" isActive={(filters.status||[]).length>0}>
                          <div>
                            <Form.Label className="mb-1">Status</Form.Label>
                            {renderStatusFilterChecks('col-filter')}
                            <div className="d-flex justify-content-end gap-2 mt-2">
                              <Button size="sm" variant="secondary" onClick={() => handleFilterChange('status', [])}>Clear</Button>
                            </div>
                          </div>
                        </ColumnFilterPopover>
                      </div>
                    </th>
                    <th style={{cursor: 'pointer'}} onClick={() => handleSort('assigned_to')}>
                      <div className="d-flex align-items-center gap-2">
                        <span>Assigned To {getSortIcon('assigned_to')}</span>
                        <ColumnFilterPopover id="filter-assigned" ariaLabel="Filter by assignee" isActive={!!filters.assigned_to_username}>
                          <div>
                            <Form.Label className="mb-1">Assigned To</Form.Label>
                            <Form.Select value={filters.assigned_to_username} onChange={(e) => handleFilterChange('assigned_to_username', e.target.value)}>
                              <option value="">All Users</option>
                              <option value="unassigned">Unassigned</option>
                            </Form.Select>
                            <div className="d-flex justify-content-end gap-2 mt-2">
                              <Button size="sm" variant="secondary" onClick={() => handleFilterChange('assigned_to_username', '')}>Clear</Button>
                              <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                            </div>
                          </div>
                        </ColumnFilterPopover>
                      </div>
                    </th>
                    <th>Registrar</th>
                    <th>Country</th>
                    <th>IP Address</th>
                    <th>Wildcard</th>
                    <th 
                      style={{cursor: 'pointer'}} 
                      onClick={() => handleSort('is_parked')}
                    >
                      <div className="d-flex align-items-center gap-2">
                        <span>Parked Domain {getSortIcon('is_parked')}</span>
                        <ColumnFilterPopover id="filter-parked" ariaLabel="Filter by parked domain" isActive={!!filters.is_parked}>
                          <div>
                            <Form.Label className="mb-1">Parked Domain Status</Form.Label>
                            <Form.Select value={filters.is_parked} onChange={(e) => handleFilterChange('is_parked', e.target.value)}>
                              <option value="">All Domains</option>
                              <option value="true">Parked Domains</option>
                              <option value="false">Non-Parked Domains</option>
                            </Form.Select>
                            <div className="d-flex justify-content-end gap-2 mt-2">
                              <Button size="sm" variant="secondary" onClick={() => handleFilterChange('is_parked', '')}>Clear</Button>
                              <Button size="sm" variant="primary" onClick={() => {}}>Apply</Button>
                            </div>
                          </div>
                        </ColumnFilterPopover>
                      </div>
                    </th>
                    <th>Auto-Resolve</th>
                    {isAdmin() && (
                      <th
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('ai_analysis_threat_level')}
                      >
                        AI Analysis {getSortIcon('ai_analysis_threat_level')}
                      </th>
                    )}
                    <th 
                      style={{cursor: 'pointer'}} 
                                      onClick={() => handleSort('whois_creation_date')}
              >
                Registered {getSortIcon('whois_creation_date')}
                    </th>
                                        <th
                      style={{cursor: 'pointer'}}
                      onClick={() => handleSort('phishlabs_incident_id')}
              >
                PhishLabs Incident {getSortIcon('phishlabs_incident_id')}
                    </th>

                    <th
                      style={{cursor: 'pointer'}}
                      onClick={() => handleSort('source')}
                    >
                      Source {getSortIcon('source')}
                    </th>
                    <th>Actions Taken</th>
                    <th
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleSort('updated_at')}
                      >
                        Last Updated {getSortIcon('updated_at')}
                      </th>
                    <th style={{ cursor: 'pointer' }} onClick={() => handleSort('last_closure_at')}>
                      Last closure {getSortIcon('last_closure_at')}
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
                        <td 
                          style={{cursor: 'pointer'}}
                          onClick={() => handleFindingClick(finding)}
                        >
                          <strong>{finding.typo_domain}</strong>
                        </td>
                        <td>
                          <Badge bg={getStatusBadgeVariant(finding.status)}>
                            {formatStatus(finding.status)}
                          </Badge>
                        </td>
                        <td>
                          {finding.assigned_to_username ? (
                            <span className="text-primary">{finding.assigned_to_username}</span>
                          ) : (
                            <span className="text-muted">Unassigned</span>
                          )}
                        </td>
                        <td>
                                                      {finding.whois_registrar ? (
                            <span>{finding.whois_registrar}</span>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                                                      {finding.geoip_country ? (
                            <Badge bg="info">{finding.geoip_country}</Badge>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                                                <td>
                          {Array.isArray(finding.dns_a_records) ? finding.dns_a_records[0] : <span className="text-muted">N/A</span>}
                        </td>
                        <td>
                          {finding.is_wildcard ? (
                            <div>
                              <Badge bg="warning">
                                <i className="bi bi-asterisk"></i> Wildcard
                              </Badge>
                              {finding.wildcard_types && finding.wildcard_types.length > 0 && (
                                <div>
                                  <small className="text-muted">
                                    {finding.wildcard_types.join(', ')}
                                  </small>
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted">
                              <i className="bi bi-check-circle"></i> Normal
                            </span>
                          )}
                        </td>
                        <td>
                          {finding.is_parked === true ? (
                            <div>
                              <Badge bg="warning">
                                🅿️ Yes
                              </Badge>
                              {finding.parked_confidence !== null && finding.parked_confidence !== undefined && (
                                <div>
                                  <small className="text-muted">
                                    {finding.parked_confidence}% confidence
                                  </small>
                                </div>
                              )}
                            </div>
                          ) : finding.is_parked === false ? (
                            <Badge bg="success">No</Badge>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {finding.auto_resolve ? (
                            <Badge bg="info">Would auto-resolve</Badge>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        {isAdmin() && (
                          <td>
                            {finding.ai_analysis ? (() => {
                              const badge = getAiThreatBadge(finding.ai_analysis);
                              return (
                                <OverlayTrigger
                                  trigger={['hover', 'focus']}
                                  placement="left"
                                  overlay={
                                    <Popover style={{ maxWidth: '350px' }}>
                                      <Popover.Header>AI Analysis</Popover.Header>
                                      <Popover.Body>
                                        <div><strong>Threat:</strong> {finding.ai_analysis.threat_level} ({finding.ai_analysis.confidence}% confidence)</div>
                                        <div className="mt-1"><strong>Summary:</strong> {finding.ai_analysis.summary}</div>
                                        <div className="mt-1"><strong>Action:</strong> {formatActionTaken(finding.ai_analysis.recommended_action)}</div>
                                        {finding.ai_analysis.indicators?.length > 0 && (
                                          <div className="mt-1"><strong>Indicators:</strong> {finding.ai_analysis.indicators.join(', ')}</div>
                                        )}
                                        <div className="mt-1 text-muted" style={{fontSize: '0.75em'}}>Model: {finding.ai_analysis.model}</div>
                                      </Popover.Body>
                                    </Popover>
                                  }
                                >
                                  <Badge bg={badge.variant} style={{ cursor: 'pointer' }}>
                                    {badge.label} ({finding.ai_analysis.confidence}%)
                                  </Badge>
                                </OverlayTrigger>
                              );
                            })() : (
                              <Button
                                variant="outline-secondary"
                                size="sm"
                                disabled={analyzingIds.has(finding.id)}
                                onClick={() => handleAiAnalyze(finding.id)}
                                title="Run AI Analysis"
                              >
                                {analyzingIds.has(finding.id) ? (
                                  <Spinner animation="border" size="sm" />
                                ) : (
                                  <i className="bi bi-robot"></i>
                                )}
                              </Button>
                            )}
                          </td>
                        )}
                        <td>
                          {finding.whois_creation_date ? (
                            new Date(
                              finding.whois_creation_date
                            ).toLocaleDateString()
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                                                <td>
                          {(() => {
                            // Parse phishlabs_data if it's a string
                            let phishlabsData = finding.phishlabs_data;
                            if (typeof phishlabsData === 'string') {
                              try {
                                phishlabsData = JSON.parse(phishlabsData);
                              } catch (e) {
                                phishlabsData = null;
                              }
                            }

                            // Check if PhishLabs data was never fetched
                            if (!phishlabsData && !finding.phishlabs_incident_id) {
                              return <span className="text-muted">N/A</span>;
                            }

                            // Check if there's an incident ID
                            const incidentId = phishlabsData?.incident_id || finding.phishlabs_incident_id;
                            if (incidentId) {
                              return (
                                <Badge bg={getPhishlabsBadgeVariant(phishlabsData?.incident_status)}>
                                  <i className="bi bi-exclamation-triangle"></i> {incidentId}
                                </Badge>
                              );
                            }

                            // Check if it was fetched but no incident (has no_incident flag or empty response)
                            if (phishlabsData?.no_incident || phishlabsData) {
                              return <span className="text-muted">None</span>;
                            }

                            // Fallback to N/A
                            return <span className="text-muted">N/A</span>;
                          })()}
                        </td>
                        <td>
                          {finding.source ? (
                            <Badge bg="secondary">
                              {finding.source}
                            </Badge>
                          ) : (
                            <span className="text-muted">N/A</span>
                          )}
                        </td>
                        <td>
                          {finding.action_taken && finding.action_taken.length > 0 ? (
                            <div>
                              {finding.action_taken.slice(0, 2).map((action, index) => (
                                <Badge key={index} bg="success" className="me-1 mb-1 small">
                                  {formatActionTaken(action)}
                                </Badge>
                              ))}
                              {finding.action_taken.length > 2 && (
                                <Badge bg="secondary" className="small">
                                  +{finding.action_taken.length - 2} more
                                </Badge>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td className="text-muted">
                          {formatDate(finding.updated_at, 'MMM dd, yyyy HH:mm:ss')}
                        </td>
                        <td className="text-muted">
                          {finding.last_closure_at
                            ? formatDate(finding.last_closure_at, 'MMM dd, yyyy HH:mm:ss')
                            : '—'}
                        </td>
                        {/* <td>
                          <div className="d-flex gap-1">
                            <Button
                              variant="outline-primary"
                              size="sm"
                              onClick={() => navigate(`/findings/typosquat/details?id=${finding.id}`)}
                              title="View Details"
                            >
                              <i className="bi bi-eye"></i>
                            </Button>
                            <Button
                              variant="outline-info"
                              size="sm"
                              onClick={() => navigate(`/findings/typosquat-urls?domain=${finding.typo_domain}`)}
                              title="View URLs"
                            >
                              <i className="bi bi-link-45deg"></i>
                            </Button>
                          </div>
                        </td> */}
                      </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </Card.Body>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4">
          <div className="text-center mb-3">
            <div className="text-muted">
              Showing {startItem}-{endItem} of {totalCount} findings
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
            <Pagination.First 
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(1)}
            />
            <Pagination.Prev 
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
            />
            
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
            
            <Pagination.Next 
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
            />
            <Pagination.Last 
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(totalPages)}
            />
          </Pagination>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => {
        setShowDeleteModal(false);
        setDeleteRelated(false);
      }}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Typosquat Findings</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected typosquat finding(s)?</p>
          
          <Form.Group className="mb-3">
            <Form.Check
              type="checkbox"
              id="delete-related-checkbox"
              label="Also delete all findings with the same base domain"
              checked={deleteRelated}
              onChange={(e) => setDeleteRelated(e.target.checked)}
            />
            <Form.Text className="text-muted">
              If checked, this will delete all findings that share the same base domain. 
              For example, deleting 'web1.domain.com' will also delete 'mail.domain.com', 'domain.com', etc.
            </Form.Text>
          </Form.Group>
          
          <p className="text-danger">
            <i className="bi bi-exclamation-triangle"></i>
            This action cannot be undone.
            {deleteRelated && (
              <><br />
              <strong>Warning:</strong> Enabling "delete related" may delete many more findings than selected.
              </>
            )}
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => {
            setShowDeleteModal(false);
            setDeleteRelated(false);
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Finding(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Batch Status Update Modal */}
      <Modal show={showStatusModal} onHide={() => {
        setShowStatusModal(false);
        setBatchStatus('unchanged');
        setBatchSelectedAssignedTo('unchanged');
        setHasExplicitAssignment(false);
        setForceAssignmentOverwrite(false);
        setStatusComment('');
        setActionTaken('');
      }}>
        <Modal.Header closeButton>
          <Modal.Title>Update Status for Selected Findings</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Update the status for {selectedItems.size} selected finding(s)</p>

          <Form.Group className="mb-3">
            <Form.Label>New Status *</Form.Label>
            <Form.Select
              value={batchStatus}
              onChange={(e) => setBatchStatus(e.target.value)}
            >
              {getAllowedBatchStatusOptions(findings.filter(f => selectedItems.has(f.id))).map((statusOption) => (
                <option key={statusOption.value} value={statusOption.value}>
                  {statusOption.label}
                </option>
              ))}
            </Form.Select>
          </Form.Group>

          <Form.Group className="mb-3">
            <Form.Label>
              Assign To
              {batchStatus === 'inprogress' && <span className="text-danger">*</span>}
            </Form.Label>
            <Form.Select
              value={batchSelectedAssignedTo}
              onChange={(e) => {
                setBatchSelectedAssignedTo(e.target.value);
                setHasExplicitAssignment(true); // User made an explicit choice
              }}
              disabled={usersLoading}
              className={batchStatus === 'inprogress' && !batchSelectedAssignedTo && batchSelectedAssignedTo !== 'unchanged' ? 'is-invalid' : ''}
            >
              <option value="unchanged">Keep Current Assignment</option>
              <option value="">Unassigned</option>
              {availableUsers.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username}
                </option>
              ))}
            </Form.Select>
            {usersLoading && (
              <Form.Text className="text-muted">
                <Spinner animation="border" size="sm" className="me-1" />
                Loading users...
              </Form.Text>
            )}
            <Form.Text className="text-muted">
              Select "Keep Current Assignment" to preserve existing assignments, choose a user to assign findings to, or select "Unassigned" to remove assignments.
            </Form.Text>
            {batchStatus === 'inprogress' && !batchSelectedAssignedTo && batchSelectedAssignedTo !== 'unchanged' && (
              <Form.Text className="text-danger">
                An assigned user is required for 'In Progress' status
              </Form.Text>
            )}

            {/* Force assignment overwrite checkbox */}
            {hasExplicitAssignment && batchSelectedAssignedTo && batchSelectedAssignedTo !== 'unchanged' && (
              <Form.Group className="mt-2">
                <Form.Check
                  type="checkbox"
                  id="force-assignment-overwrite"
                  label="Force overwrite existing assignments"
                  checked={forceAssignmentOverwrite}
                  onChange={(e) => setForceAssignmentOverwrite(e.target.checked)}
                />
                <Form.Text className="text-muted">
                  When checked, findings that are already assigned to someone else will be reassigned to the selected user.
                  When unchecked, only unassigned findings will be assigned to the selected user.
                </Form.Text>
              </Form.Group>
            )}
          </Form.Group>

          <Form.Group className="mb-3">
            <Form.Label>
              Comment
              {(() => {
                const selectedFindings = findings.filter(f => selectedItems.has(f.id));
                const hasInProgress = selectedFindings.some(f => f.status === 'inprogress');
                return hasInProgress && (batchStatus === 'dismissed' || batchStatus === 'resolved') && (
                  <span className="text-danger">* (Required for findings changing from In Progress)</span>
                );
              })()}
              {!(() => {
                const selectedFindings = findings.filter(f => selectedItems.has(f.id));
                const hasInProgress = selectedFindings.some(f => f.status === 'inprogress');
                return hasInProgress && (batchStatus === 'dismissed' || batchStatus === 'resolved');
              })() && (
                <span className="text-muted">(Optional)</span>
              )}
            </Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              placeholder="Enter a comment about this status change..."
              value={statusComment}
              onChange={(e) => setStatusComment(e.target.value)}
              className={(() => {
                const selectedFindings = findings.filter(f => selectedItems.has(f.id));
                const hasInProgress = selectedFindings.some(f => f.status === 'inprogress');
                return hasInProgress && (batchStatus === 'dismissed' || batchStatus === 'resolved') && !statusComment ? 'is-invalid' : '';
              })()}
            />
            {(() => {
              const selectedFindings = findings.filter(f => selectedItems.has(f.id));
              const hasInProgress = selectedFindings.some(f => f.status === 'inprogress');
              const inProgressCount = selectedFindings.filter(f => f.status === 'inprogress').length;
              return hasInProgress && (batchStatus === 'dismissed' || batchStatus === 'resolved') && !statusComment && (
                <Form.Text className="text-danger">
                  A comment is required because {inProgressCount} selected finding(s) have 'In Progress' status
                </Form.Text>
              );
            })()}
          </Form.Group>

          {batchStatus === 'resolved' && (
            <Form.Group className="mb-3">
              <Form.Label>Action Taken</Form.Label>
              <Form.Select
                value={actionTaken}
                onChange={(e) => setActionTaken(e.target.value)}
              >
                <option value="">Select an action...</option>
                <option value="takedown_requested">Takedown requested</option>
                <option value="reported_google_safe_browsing">Reported to Google Safe Browsing</option>
                <option value="blocked_firewall">Blocked on firewall</option>
                <option value="monitoring">Monitoring</option>
                <option value="other">Other</option>
              </Form.Select>
            </Form.Group>
          )}

        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => {
            setShowStatusModal(false);
            setBatchStatus('unchanged');
            setBatchSelectedAssignedTo('unchanged');
            setHasExplicitAssignment(false);
            setForceAssignmentOverwrite(false);
            setStatusComment('');
            setActionTaken('');
          }}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleBatchStatusUpdate}
            disabled={updatingStatus}
          >
            {updatingStatus ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Updating...
              </>
            ) : (
              <>
                <i className="bi bi-tag"></i> Update Status
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export Typosquat Findings</Modal.Title>
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
                label="Plain Text - Typo domains only (one per line)"
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
                      label="Typo Domain"
                      checked={exportColumns.typo_domain}
                      onChange={() => handleColumnToggle('typo_domain')}
                      className="mb-2"
                    />

                    <Form.Check
                      type="checkbox"
                      label="Status"
                      checked={exportColumns.status}
                      onChange={() => handleColumnToggle('status')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Assigned To"
                      checked={exportColumns.assigned_to}
                      onChange={() => handleColumnToggle('assigned_to')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Registrar"
                      checked={exportColumns.registrar}
                      onChange={() => handleColumnToggle('registrar')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Country"
                      checked={exportColumns.country}
                      onChange={() => handleColumnToggle('country')}
                      className="mb-2"
                    />
                  </Col>
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
                      label="Is Wildcard"
                      checked={exportColumns.is_wildcard}
                      onChange={() => handleColumnToggle('is_wildcard')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Creation Date"
                      checked={exportColumns.creation_date}
                      onChange={() => handleColumnToggle('creation_date')}
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
                      label="Has PhishLabs Incident"
                      checked={exportColumns.has_phishlabs}
                      onChange={() => handleColumnToggle('has_phishlabs')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Threatstream ID"
                      checked={exportColumns.threatstream_id}
                      onChange={() => handleColumnToggle('threatstream_id')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Threatstream Threat Score"
                      checked={exportColumns.threatstream_threat_score}
                      onChange={() => handleColumnToggle('threatstream_threat_score')}
                      className="mb-2"
                    />
                    <Form.Check
                      type="checkbox"
                      label="Source"
                      checked={exportColumns.source}
                      onChange={() => handleColumnToggle('source')}
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
                  Leave empty to use default filename: typosquat_findings_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <small className="text-muted">
                Total findings to export: {totalCount} (based on current filters)
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

      <Modal show={showSimilarityProgramModal} onHide={() => setShowSimilarityProgramModal(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Calculate similarities</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p className="text-muted small mb-3">
            No program is selected in the global filter. Choose which program&apos;s typosquat findings should be
            recalculated against its protected domains.
          </p>
          <Form.Group>
            <Form.Label>Program</Form.Label>
            <Form.Select
              value={similarityModalProgram}
              onChange={(e) => setSimilarityModalProgram(e.target.value)}
              disabled={programsLoading}
            >
              {programsLoading ? (
                <option value="">Loading programs...</option>
              ) : (
                availablePrograms.map((program) => {
                  const programName = typeof program === 'string' ? program : program?.name || '';
                  return (
                    <option key={programName} value={programName}>
                      {programName}
                    </option>
                  );
                })
              )}
            </Form.Select>
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowSimilarityProgramModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleConfirmSimilarityProgramModal}
            disabled={programsLoading || !similarityModalProgram}
          >
            Run for program
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Typosquat Batch Modal */}
      <Modal show={showTyposquatBatchModal} onHide={() => setShowTyposquatBatchModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Analyze Domains for Typosquatting</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form onSubmit={(e) => {
            e.preventDefault();
            handleBatchTyposquatAnalysis();
          }}>
            <Row className="mb-3">
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Domains to Analyze (one per line or comma-separated)</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={5}
                    placeholder="example.com, sub.example.org, www[.]test[.]co[.]uk"
                    value={batchDomains}
                    onChange={(e) => setBatchDomains(e.target.value)}
                  />
                  <Form.Text className="text-muted">
                    Enter one or more domain names to analyze for typosquatting.
                    You can use either regular format (sub1.sub2.domain.com) or secured format (sub1[.]sub2[.]domain[.]com).
                    Both formats can be mixed in the same request.
                  </Form.Text>
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Upload File (Optional)</Form.Label>
                  <Form.Control
                    type="file"
                    id="domain-file-upload"
                    accept=".txt"
                    onChange={handleFileUpload}
                  />
                  {uploadedFile && (
                    <div className="mt-2">
                      <Badge bg="info" className="me-2">
                        Selected File: {uploadedFile.name}
                      </Badge>
                      <Button variant="outline-danger" size="sm" onClick={clearUploadedFile}>
                        <i className="bi bi-x-circle"></i> Clear File
                      </Button>
                    </div>
                  )}
                  <Form.Text className="text-muted">
                    If you have a text file containing domains, you can upload it here.
                    The file should contain one domain per line. You can use either regular format
                    (sub1.sub2.domain.com) or secured format (sub1[.]sub2[.]domain[.]com).
                  </Form.Text>
                </Form.Group>
              </Col>
            </Row>
            <Form.Group className="mb-3">
              <Form.Label>Program Name (Optional)</Form.Label>
              <Form.Select
                value={batchProgramName}
                onChange={(e) => setBatchProgramName(e.target.value)}
                disabled={programsLoading}
              >
                <option value="">Select a Program</option>
                {programsLoading ? (
                  <option value="">Loading programs...</option>
                ) : availablePrograms.length === 0 ? (
                  <option value="">No programs found. Please add one in the Programs page.</option>
                ) : (
                  availablePrograms.map(program => {
                    const programName = typeof program === 'string' ? program : program?.name || '';
                    return (
                      <option key={programName} value={programName}>
                        {programName}
                      </option>
                    );
                  })
                )}
              </Form.Select>
              <Form.Text className="text-muted">
                If you have a specific program name for these domains, enter it here.
                Otherwise, it will use the default program name.
              </Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Original Domain (Optional)</Form.Label>
              <Form.Control
                type="text"
                placeholder="example.com"
                value={batchOriginalDomain}
                onChange={(e) => setBatchOriginalDomain(e.target.value)}
              />
            </Form.Group>
            <Button 
              variant="primary" 
              type="submit"
              disabled={typosquatBatchLoading}
            >
              {typosquatBatchLoading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Analyzing...
                </>
              ) : (
                <>
                  <i className="bi bi-search"></i> Start Typosquat Analysis
                </>
              )}
            </Button>
          </Form>
          {typosquatBatchMessage.text && (
            <Alert variant={typosquatBatchMessage.type} className="mt-3">
              {typosquatBatchMessage.text}
            </Alert>
          )}
        </Modal.Body>
      </Modal>

      {/* Batch AI analysis (selected findings) */}
      <Modal
        show={showAiAnalysisBatchModal && isAdmin()}
        onHide={() => {
          if (!aiBatchLoading) setShowAiAnalysisBatchModal(false);
        }}
      >
        <Modal.Header closeButton>
          <Modal.Title>AI analysis ({selectedItems.size} selected)</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p className="text-muted small mb-3">
            Runs a background job (same path as single-finding analysis). Unreachable or unauthorized IDs are skipped on the server; only findings you can access are analyzed.
          </p>
          {selectedItems.size > AI_ANALYSIS_BATCH_MAX_FINDINGS && (
            <Alert variant="warning" className="mb-3 py-2">
              At most {AI_ANALYSIS_BATCH_MAX_FINDINGS} findings per batch for now. You have {selectedItems.size} selected—deselect some or split into multiple jobs.
            </Alert>
          )}
          <Form.Check
            type="checkbox"
            id="batch-ai-force"
            label="Force re-analyze (even if already analyzed)"
            checked={batchAiForce}
            onChange={(e) => setBatchAiForce(e.target.checked)}
            disabled={aiBatchLoading}
            className="mb-3"
          />
          <Form.Group className="mb-3">
            <Form.Label>Ollama model</Form.Label>
            {aiModelsLoading ? (
              <div className="text-muted small">
                <Spinner animation="border" size="sm" className="me-2" />
                Loading models…
              </div>
            ) : aiModels.length > 0 ? (
              <Form.Select
                size="sm"
                style={{ width: 'auto', minWidth: '160px' }}
                value={batchAiModel}
                onChange={(e) => setBatchAiModel(e.target.value)}
                disabled={aiBatchLoading}
              >
                {!aiDefaultModel && <option value="" />}
                {aiModels.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name}{m.parameter_size ? ` (${m.parameter_size})` : ''}
                  </option>
                ))}
              </Form.Select>
            ) : (
              <p className="text-muted small mb-0">
                Could not load models from Ollama. The server default model will be used.
              </p>
            )}
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowAiAnalysisBatchModal(false)} disabled={aiBatchLoading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleExecuteAiAnalysisBatch}
            disabled={aiBatchLoading || selectedItems.size > AI_ANALYSIS_BATCH_MAX_FINDINGS}
          >
            {aiBatchLoading ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Starting…
              </>
            ) : (
              <>Start AI analysis</>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* PhishLabs Action Modal */}
      <Modal show={showPhishlabsModal} onHide={() => {
        setShowPhishlabsModal(false);
        setBatchReportToGsb(false);
      }}>
        <Modal.Header closeButton>
          <Modal.Title>
            {phishlabsAction === 'fetch' && 'Fetch PhishLabs Data'}
            {phishlabsAction === 'create' && 'Create PhishLabs Incidents'}
            {phishlabsAction === 'takedown' && 'Start PhishLabs Takedown'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3">
            <Form.Label>Action</Form.Label>
            <div className="d-flex flex-column gap-1">
              <Form.Check
                type="radio"
                id="phishlabs-modal-fetch"
                name="phishlabsModalAction"
                label="Fetch PhishLabs data (background job)"
                checked={phishlabsAction === 'fetch'}
                onChange={() => setPhishlabsAction('fetch')}
              />
              <Form.Check
                type="radio"
                id="phishlabs-modal-create"
                name="phishlabsModalAction"
                label="Create PhishLabs incident (background job)"
                checked={phishlabsAction === 'create'}
                onChange={() => {
                  setPhishlabsAction('create');
                  setPhishlabsComment('Typosquat related to our brand. Please monitor in case of new evidences, please proceed to takedown. Regards');
                  setBatchReportToGsb(true);
                }}
              />
              <Form.Check
                type="radio"
                id="phishlabs-modal-takedown"
                name="phishlabsModalAction"
                label="Start takedown (immediate API — requires incident ID per finding)"
                checked={phishlabsAction === 'takedown'}
                onChange={() => setPhishlabsAction('takedown')}
              />
            </div>
          </Form.Group>
          <p className="text-muted small mb-3">
            {phishlabsAction === 'fetch' &&
              `Fetch existing PhishLabs incident data for ${selectedItems.size} selected finding(s).`}
            {phishlabsAction === 'create' &&
              `Create PhishLabs incidents for ${selectedItems.size} selected finding(s).`}
            {phishlabsAction === 'takedown' &&
              `Request takedown (apply action) in PhishLabs for ${selectedItems.size} finding(s). Rows without a stored PhishLabs incident ID will fail.`}
          </p>

          {phishlabsAction === 'create' && (
            <>
              <Form.Group className="mb-3">
                <Form.Label>Category Code *</Form.Label>
                <Form.Select
                  value={selectedCatcode}
                  onChange={(e) => setSelectedCatcode(e.target.value)}
                  required
                >
                  <option value="">Select a category...</option>
                  <option value="1204">Parked Domain</option>
                  <option value="1201">Domain without content</option>
                  <option value="1205">Content unrelated to your organization</option>
                  <option value="1210">This domain resolves to a monetized link page</option>
                  <option value="1224">Content Unavailable - Site Login Required</option>
                  <option value="1221">Phishing</option>
                </Form.Select>
                <Form.Text className="text-muted">
                  Select the appropriate category for these typosquat findings
                </Form.Text>
              </Form.Group>

              <Form.Group className="mb-3">
                <Form.Label>Comment</Form.Label>
                <Form.Control
                  as="textarea"
                  rows={3}
                  placeholder="Enter a comment for this PhishLabs incident..."
                  value={phishlabsComment}
                  onChange={(e) => setPhishlabsComment(e.target.value)}
                />
                <Form.Text className="text-muted">
                  This comment will be included with the PhishLabs incident creation
                </Form.Text>
              </Form.Group>

              <Form.Group className="mb-3">
                <Form.Check
                  type="checkbox"
                  id="report-to-gsb-batch"
                  label="Also report domains to Google Safe Browsing"
                  checked={batchReportToGsb}
                  onChange={(e) => setBatchReportToGsb(e.target.checked)}
                />
                <Form.Text className="text-muted">
                  If checked, all selected domains will also be reported to Google Safe Browsing before creating PhishLabs incidents
                </Form.Text>
              </Form.Group>

              <Alert variant="info">
                <i className="bi bi-info-circle me-2"></i>
                <strong>Note:</strong> The selected category will be applied to all selected findings. The domain will be used as the URL for each finding.
              </Alert>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => {
            setShowPhishlabsModal(false);
            setPhishlabsComment('');
            setBatchReportToGsb(false);
          }}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleConfirmPhishlabsAction}
            disabled={creatingPhishlabs || (phishlabsAction === 'create' && !selectedCatcode)}
          >
            {creatingPhishlabs ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Processing...
              </>
            ) : (
              <>
                <i
                  className={`bi me-2 ${
                    phishlabsAction === 'fetch'
                      ? 'bi-cloud-download'
                      : phishlabsAction === 'takedown'
                        ? 'bi-shield-fill-check'
                        : 'bi-plus-circle'
                  }`}
                ></i>
                {phishlabsAction === 'fetch' && 'Fetch Data'}
                {phishlabsAction === 'create' && 'Create Incidents'}
                {phishlabsAction === 'takedown' && 'Start Takedown'}
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

    </Container>
  );
}

export default TyposquatFindings;