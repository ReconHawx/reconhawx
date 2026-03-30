import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  Container,
  Card,
  Badge,
  Row,
  Col,
  Button,
  Alert,
  Spinner,
  Table,
  Form,
  Collapse,
  Modal
} from 'react-bootstrap';
import api, { userManagementAPI } from '../../services/api';
import NotesSection from '../../components/NotesSection';
import RelatedScreenshotsViewer from '../../components/RelatedScreenshotsViewer';
import { formatDate, formatLocalDate } from '../../utils/dateUtils';
import { useAuth } from '../../contexts/AuthContext';
import { formatAssignedTo, initializeUserCache, preloadUsers } from '../../utils/userUtils';

const WHOIS_FLAT_KEYS = [
  'whois_registrar',
  'whois_creation_date',
  'whois_expiration_date',
  'whois_registrant_name',
  'whois_registrant_country',
  'whois_admin_email',
];

/**
 * Normalize WHOIS for display: legacy `info.whois` (string/object) or top-level `whois_*` API fields.
 */
function getTyposquatWhoisForDisplay(finding) {
  if (!finding) return null;

  const raw = finding.info?.whois;

  if (raw != null) {
    if (typeof raw === 'string' && raw.trim()) {
      return { kind: 'string', value: raw };
    }
    if (
      typeof raw === 'object' &&
      !Array.isArray(raw) &&
      Object.keys(raw).length > 0
    ) {
      return { kind: 'object', value: raw };
    }
  }

  const hasFlat = WHOIS_FLAT_KEYS.some((k) => {
    const v = finding[k];
    return v != null && String(v).trim() !== '';
  });
  if (!hasFlat) return null;

  return {
    kind: 'object',
    value: {
      domain_name: finding.typo_domain || undefined,
      registrar: finding.whois_registrar,
      creation_date: finding.whois_creation_date,
      expiration_date: finding.whois_expiration_date,
      registrant_name: finding.whois_registrant_name,
      registrant_org: finding.whois_registrant_org,
      registrant_country: finding.whois_registrant_country,
      admin_email: finding.whois_admin_email,
    },
  };
}

function TyposquatFindingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAdmin } = useAuth();
  
  // Initialize user cache with current user
  React.useEffect(() => {
    initializeUserCache(user);
  }, [user]);
  
  // State management
  const [finding, setFinding] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('');
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState({ text: '', type: '' });
  const [statusComment, setStatusComment] = useState('');
  const [actionTaken, setActionTaken] = useState('');
  const [expandedSections, setExpandedSections] = useState({
    whois: true,
    dns: true,
    ssl: false,
    http: false,
    threatstream: true,
    recordedfuture: true,
    parked: false,
    similarities: true,
    aiAnalysis: true,
    json: false
  });
  const [similaritiesShowAll, setSimilaritiesShowAll] = useState(false);
  const [relatedDomainsShowAll, setRelatedDomainsShowAll] = useState(false);
  const [relatedUrlsShowAll, setRelatedUrlsShowAll] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteRelated, setDeleteRelated] = useState(false);

  // PhishLabs fetch state
  const [phishMessage, setPhishMessage] = useState({ text: '', type: '' });

  const [recalculatingSimilarities, setRecalculatingSimilarities] = useState(false);
  const [similarityRecalcMessage, setSimilarityRecalcMessage] = useState({ text: '', type: '' });

  // AI analysis state
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiMessage, setAiMessage] = useState({ text: '', type: '' });
  const [aiModels, setAiModels] = useState([]);
  const [aiDefaultModel, setAiDefaultModel] = useState('');
  const [aiSelectedModel, setAiSelectedModel] = useState('');

  // User assignment state
  const [availableUsers, setAvailableUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [selectedAssignedTo, setSelectedAssignedTo] = useState('');

  // PhishLabs incident creation state
  const [showPhishlabsModal, setShowPhishlabsModal] = useState(false);
  const [phishlabsAction, setPhishlabsAction] = useState(''); // 'fetch' or 'create'
  const [selectedCatcode, setSelectedCatcode] = useState('');
  const [phishlabsComment, setPhishlabsComment] = useState('Typosquat related to our brand. Please monitor in case of new evidences, please proceed to takedown. Regards');
  const [creatingPhishlabs, setCreatingPhishlabs] = useState(false);
  const [reportToGsb, setReportToGsb] = useState(false);

  // Job status polling state
  const [pollingJobId, setPollingJobId] = useState(null);
  const [pollingInterval, setPollingInterval] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [jobPollingProgress, setJobPollingProgress] = useState('');

  // Typosquat URLs state
  const [typosquatUrls, setTyposquatUrls] = useState([]);
  const [urlsLoading, setUrlsLoading] = useState(false);

  // Related domains state
  const [relatedDomains, setRelatedDomains] = useState([]);
  const [relatedDomainsLoading, setRelatedDomainsLoading] = useState(false);

  // Action logs state
  const [actionLogs, setActionLogs] = useState([]);
  const [actionLogsLoading, setActionLogsLoading] = useState(false);

  // Fetch finding details
  useEffect(() => {
    const fetchFinding = async () => {
      try {
        setLoading(true);
        setError(null);
        
        // Check for query parameter first, then URL parameter
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');

        if (idParam) {
          // Use unified endpoint for query parameters
          const data = await api.findings.typosquat.getByIdUnified(idParam);
          setFinding(data);
          setStatus(data?.status || 'new');

          // Preload user data for assigned_to field
          if (data?.assigned_to) {
            preloadUsers([data.assigned_to]).catch(err => {
              console.warn('Failed to preload user data:', err);
            });
          }
        } else if (id) {
          // Use regular endpoint for URL parameters
          const data = await api.findings.typosquat.getById(id);
          setFinding(data);
          setStatus(data?.status || 'new');

          // Preload user data for assigned_to field
          if (data?.assigned_to) {
            preloadUsers([data.assigned_to]).catch(err => {
              console.warn('Failed to preload user data:', err);
            });
          }
        }
      } catch (err) {
        console.error('Error fetching typosquat finding:', err);
        setError(err.message || 'Failed to load typosquat finding');
      } finally {
        setLoading(false);
      }
    };

    // Load if we have either a URL parameter or query parameter
    if (id || new URLSearchParams(location.search).get('id')) {
      fetchFinding();
    }
  }, [id, location.search]);

  // Fetch typosquat URLs for all related domains
  useEffect(() => {
    const fetchTyposquatUrls = async () => {
      if (!finding?.typo_domain) return;
      
      try {
        setUrlsLoading(true);
        
        // Get the correct ID from query params or URL params
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        const findingId = idParam || id;
        
        if (findingId) {
          const response = await api.findings.typosquat.getRelatedUrls(findingId);
          setTyposquatUrls(response.items || []);
        } else {
          setTyposquatUrls([]);
        }
      } catch (err) {
        console.error('Error fetching related typosquat URLs:', err);
        setTyposquatUrls([]);
      } finally {
        setUrlsLoading(false);
      }
    };

    fetchTyposquatUrls();
  }, [finding?.typo_domain, id, location.search]);

  // Fetch related domains (same apex domain)
  useEffect(() => {
    const fetchRelatedDomains = async () => {
      if (!finding?.typo_domain) return;
      
      try {
        setRelatedDomainsLoading(true);
        
        // Get the correct ID from query params or URL params
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        const findingId = idParam || id;
        
        if (findingId) {
          const response = await api.findings.typosquat.getRelatedDomains(findingId);
          setRelatedDomains(response.items || []);
        } else {
          setRelatedDomains([]);
        }
      } catch (err) {
        console.error('Error fetching related domains:', err);
        setRelatedDomains([]);
      } finally {
        setRelatedDomainsLoading(false);
      }
    };

    fetchRelatedDomains();
  }, [finding?.typo_domain, id, location.search]);

  // Fetch action logs
  useEffect(() => {
    const fetchActionLogs = async () => {
      if (!finding?.id && !finding?._id) return;

      try {
        setActionLogsLoading(true);

        // Get the correct ID from query params or URL params
        const params = new URLSearchParams(location.search);
        const idParam = params.get('id');
        const findingId = idParam || id;

        if (findingId) {
          const response = await api.findings.typosquat.getActionLogs(findingId);
          setActionLogs(response.items || []);
        } else {
          setActionLogs([]);
        }
      } catch (err) {
        console.error('Error fetching action logs:', err);
        setActionLogs([]);
      } finally {
        setActionLogsLoading(false);
      }
    };

    fetchActionLogs();
  }, [finding?.id, finding?._id, id, location.search]);

  const refreshFindingAfterSimilarityRecalc = async () => {
    const params = new URLSearchParams(location.search);
    const idParam = params.get('id');
    try {
      if (idParam) {
        const data = await api.findings.typosquat.getByIdUnified(idParam);
        setFinding(data);
        setStatus(data?.status || 'new');
      } else if (id) {
        const data = await api.findings.typosquat.getById(id);
        setFinding(data);
        setStatus(data?.status || 'new');
      }
    } catch (err) {
      console.error('Error refreshing finding after similarity recalc:', err);
    }
  };

  const handleRecalculateFindingSimilarities = async () => {
    const params = new URLSearchParams(location.search);
    const idParam = params.get('id');
    const findingId = idParam || id;
    if (!findingId) return;

    try {
      setRecalculatingSimilarities(true);
      setSimilarityRecalcMessage({ text: '', type: '' });

      const response = await api.findings.typosquat.recalculateSimilaritiesForFinding(findingId);

      if (response.status === 'success' || response.status === 'warning') {
        setSimilarityRecalcMessage({
          text:
            response.message ||
            `Updated: ${response.updated ?? 0}, failed: ${response.failed ?? 0}`,
          type: response.status === 'warning' ? 'warning' : 'success'
        });
        await refreshFindingAfterSimilarityRecalc();
        setTimeout(() => setSimilarityRecalcMessage({ text: '', type: '' }), 6000);
      } else {
        setSimilarityRecalcMessage({
          text: response.error || response.message || 'Recalculation failed',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error recalculating similarities:', err);
      setSimilarityRecalcMessage({
        text: err.response?.data?.detail || err.message || 'Error recalculating similarities',
        type: 'danger'
      });
    } finally {
      setRecalculatingSimilarities(false);
    }
  };

  // Fetch available users by getting assigned users from findings
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        setUsersLoading(true);

        // Fetch users who have access to this program from the new endpoint
        const response = await userManagementAPI.getUsersForAssignment(finding?.program_name);

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
    };

    // Only fetch users if we have the finding and program name
    if (finding?.program_name) {
      fetchUsers();
    }
  }, [finding?.program_name]);

  // Update selectedAssignedTo when finding changes
  useEffect(() => {
    if (finding?.assigned_to) {
      setSelectedAssignedTo(finding.assigned_to);
    } else {
      setSelectedAssignedTo('');
    }
  }, [finding?.assigned_to]);

  // Handle automatic unassign when changing from inprogress to new
  useEffect(() => {
    if (finding?.status === 'inprogress' && status === 'new') {
      setSelectedAssignedTo(''); // Auto-unassign
    }
  }, [status, finding?.status]);

  // Cleanup polling interval on component unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);

  // Fetch available AI models (admin only, re-run when user loads)
  useEffect(() => {
    if (!isAdmin()) return;
    const fetchModels = async () => {
      try {
        const data = await api.ai.getModels();
        setAiModels(data.models || []);
        setAiDefaultModel(data.default_model || '');
      } catch (err) {
        // Ollama may be unreachable; not critical
      }
    };
    fetchModels();
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  // Toggle expanded sections
  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };


  // Get status badge variant
  const getStatusBadgeVariant = (status) => {
    switch (status) {
      case 'inprogress': return 'warning';
      case 'dismissed': return 'secondary';
      case 'resolved': return 'success';
      default: return 'info';
    }
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

  // Format fuzzer names
  const formatFuzzerName = (fuzzer) => {
    const fuzzerMap = {
      'insertion': 'Character Insertion',
      'repetition': 'Character Repetition',
      'omission': 'Character Omission',
      'replacement': 'Character Replacement',
      'transposition': 'Character Transposition',
      'subdomain': 'Subdomain Fuzzing',
      'tld': 'TLD Fuzzing',
      'homograph': 'Homograph Attack',
      'keyboard': 'Keyboard Layout',
      'addition': 'Character Addition',
      'bitsquatting': 'Bitsquatting',
      'hyphenation': 'Hyphenation',
      'vowel_swap': 'Vowel Swapping',
      'double_replacement': 'Double Replacement'
    };
    
    return fuzzerMap[fuzzer] || fuzzer.charAt(0).toUpperCase() + fuzzer.slice(1);
  };

  // Extract apex domain from a subdomain
  const getApexDomain = (domain) => {
    if (!domain) return null;
    
    // Remove protocol if present
    const cleanDomain = domain.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    
    // Split by dots and take the last two parts (handles most common TLDs)
    const parts = cleanDomain.split('.');
    if (parts.length >= 2) {
      return parts.slice(-2).join('.');
    }
    
    return cleanDomain;
  };

  // Format action type for display
  const formatActionType = (actionType) => {
    switch (actionType) {
      case 'status_change': return 'Status Changed';
      case 'assignment_change': return 'Assignment Changed';
      case 'phishlabs_incident_created': return 'PhishLabs Incident Created';
      case 'phishlabs_batch_job_initiated': return 'PhishLabs Batch Job Initiated';
      case 'google_safe_browsing_reported': return 'Reported to Google Safe Browsing';
      default: return actionType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
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

  // AI threat level badge styling
  const getAiThreatBadgeVariant = (level) => {
    switch (level) {
      case 'high': return 'danger';
      case 'medium': return 'warning';
      case 'low': return 'secondary';
      case 'benign': return 'success';
      default: return 'secondary';
    }
  };

  const handleAiAnalyze = async (force = false) => {
    setAiAnalyzing(true);
    setAiMessage({ text: '', type: '' });
    try {
      const findingId = finding.id;
      const modelParam = aiSelectedModel || null;
      const result = await api.findings.typosquat.aiAnalyze(findingId, { force, model: modelParam });
      const jobId = result?.job_id;
      setAiMessage({
        text: jobId
          ? 'AI analysis job started. Results will appear when the job completes (may take a few minutes).'
          : 'AI analysis started. Results will appear shortly...',
        type: 'info',
      });
      const pollInterval = setInterval(async () => {
        try {
          const params = new URLSearchParams(window.location.search);
          const idParam = params.get('id') || id;
          const updated = idParam
            ? await api.findings.typosquat.getByIdUnified(idParam)
            : await api.findings.typosquat.getById(id);
          if (updated?.ai_analysis) {
            setFinding(updated);
            setAiMessage({ text: 'AI analysis complete.', type: 'success' });
            clearInterval(pollInterval);
            setAiAnalyzing(false);
          }
        } catch (err) {
          // keep polling
        }
      }, 3000);
      setTimeout(() => {
        clearInterval(pollInterval);
        setAiAnalyzing(false);
      }, 300000);
    } catch (err) {
      setAiMessage({ text: `AI analysis request failed: ${err.message}`, type: 'danger' });
      setAiAnalyzing(false);
    }
  };

  // Copy JSON to clipboard
  const copyJsonToClipboard = () => {
    if (finding) {
      navigator.clipboard.writeText(JSON.stringify(finding, null, 2));
    }
  };

  // Copy domain to clipboard
  const handleCopyDomain = async () => {
    if (finding?.typo_domain) {
      try {
        await navigator.clipboard.writeText(finding.typo_domain);
        // You could add a toast notification here if desired
      } catch (err) {
        console.error('Failed to copy domain:', err);
      }
    }
  };

  // Copy defanged domain to clipboard
  const handleCopyDefanged = async () => {
    if (finding?.typo_domain) {
      try {
        const defanged = finding.typo_domain.replace(/\./g, '[.]');
        await navigator.clipboard.writeText(defanged);
      } catch (err) {
        console.error('Failed to copy defanged domain:', err);
      }
    }
  };

  // Get allowed status transitions based on current status
  const getAllowedStatusOptions = (currentStatus) => {
    const allStatuses = [
      { value: 'new', label: 'New' },
      { value: 'inprogress', label: 'In Progress' },
      { value: 'dismissed', label: 'Dismissed' },
      { value: 'resolved', label: 'Resolved' }
    ];

    // Rule: From 'new' status, only 'inprogress' is allowed (besides staying 'new')
    if (currentStatus === 'new') {
      return allStatuses.filter(s => s.value === 'new' || s.value === 'inprogress');
    }

    // For other statuses, all transitions are allowed
    return allStatuses;
  };

  // Validate status transition
  const validateStatusTransition = (oldStatus, newStatus, assignedTo, comment) => {
    // Rule 1: From 'new' status, only 'inprogress' is allowed
    if (oldStatus === 'new' && newStatus !== 'new' && newStatus !== 'inprogress') {
      return `From 'New' status, you can only change to 'In Progress'`;
    }

    // Rule 2: 'inprogress' status requires an assigned user
    if (newStatus === 'inprogress' && !assignedTo) {
      return "'In Progress' status requires an assigned user";
    }

    // Rule 3: Transitions from 'inprogress' to 'dismissed' or 'resolved' require a comment
    if (oldStatus === 'inprogress' && (newStatus === 'dismissed' || newStatus === 'resolved') && !comment) {
      return `Transition from 'In Progress' to '${newStatus}' requires a comment`;
    }

    return null; // No validation error
  };

  // Handle status update
  const handleStatusUpdate = async (newStatus, takeOwnership = false, explicitAssignedTo = undefined) => {
    try {
      setStatusLoading(true);
      setStatusMessage({ text: '', type: '' });

      // Perform client-side validation
      const oldStatus = finding.status;
      const finalAssignedTo = explicitAssignedTo !== undefined ? explicitAssignedTo : selectedAssignedTo;
      const validationError = validateStatusTransition(oldStatus, newStatus, finalAssignedTo, statusComment);

      if (validationError) {
        setStatusMessage({
          text: validationError,
          type: 'danger'
        });
        setStatusLoading(false);
        return;
      }

      // Get the correct ID from query params or URL params
      const params = new URLSearchParams(location.search);
      const idParam = params.get('id');
      const findingId = idParam || id;

      // Use explicit assignment if provided, otherwise use selectedAssignedTo from dropdown
      let assignedTo;
      if (explicitAssignedTo !== undefined) {
        assignedTo = explicitAssignedTo;
      } else {
        // Convert empty string (Unassigned) to null, keep non-empty values as-is
        assignedTo = selectedAssignedTo === '' ? null : selectedAssignedTo;
      }

      const response = await api.findings.typosquat.updateStatus(
        findingId,
        newStatus,
        takeOwnership,
        user?.id,
        statusComment,
        actionTaken,
        assignedTo
      );

      if (response.status === 'success') {
        // Update local state
        setFinding(prev => {
          const newAssignedTo = response.data?.assigned_to !== undefined ? response.data.assigned_to : prev.assigned_to;
          return {
            ...prev,
            status: newStatus,
            assigned_to: newAssignedTo,
            assigned_to_username: newAssignedTo ? response.data?.assigned_to_username || prev.assigned_to_username : null
          };
        });
        setStatus(newStatus);
        setSelectedAssignedTo(response.data?.assigned_to || ''); // Update selected assignment
        setStatusComment(''); // Clear comment after successful update
        setActionTaken(''); // Clear action taken after successful update
        setStatusMessage({
          text: response.message || 'Status updated successfully',
          type: 'success'
        });

        // Refresh action logs to show the new status change
        try {
          const logsResponse = await api.findings.typosquat.getActionLogs(findingId);
          setActionLogs(logsResponse.items || []);
        } catch (err) {
          console.error('Error refreshing action logs:', err);
        }

        // Clear success message after 3 seconds
        setTimeout(() => {
          setStatusMessage({ text: '', type: '' });
        }, 3000);
      } else {
        setStatusMessage({
          text: response.message || 'Failed to update status',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error updating status:', err);
      setStatusMessage({
        text: err.message || 'Error updating status. Please try again.',
        type: 'danger'
      });
    } finally {
      setStatusLoading(false);
    }
  };

  // Handle notes update (for NotesSection component)
  const handleNotesUpdate = (newNotes) => {
    // Update the finding object with new notes
    setFinding(prev => ({ ...prev, notes: newNotes }));
  };

  // Handle delete finding
  const handleDelete = async () => {
    try {
      setDeleting(true);
      // Get the correct ID from query params or URL params
      const params = new URLSearchParams(location.search);
      const idParam = params.get('id');
      const findingId = idParam || id;
      
      await api.findings.typosquat.delete(findingId, deleteRelated);
      setShowDeleteModal(false);
      setDeleteRelated(false); // Reset the checkbox
      navigate('/findings/typosquat');
    } catch (err) {
      console.error('Error deleting typosquat finding:', err);
      alert('Failed to delete typosquat finding: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
    }
  };

  // Handle start investigation (take ownership)
  const handleStartInvestigation = () => {
    handleStatusUpdate('inprogress', true, user?.id);
  };

  // Handle status form submission
  const handleStatusSubmit = (e) => {
    e.preventDefault();
    handleStatusUpdate(status, false);
  };

  // Handle PhishLabs info fetch
  const handleFetchPhishlabs = () => {
    setPhishlabsAction('fetch');
    setShowPhishlabsModal(true);
  };

  // Handle PhishLabs incident creation
  const handleCreatePhishlabsIncident = () => {
    setPhishlabsAction('create');
    // Set default comment for incident creation
    setPhishlabsComment('Typosquat related to our brand. Please monitor in case of new evidences, please proceed to takedown. Regards');
    // Set Google Safe Browsing to checked by default
    setReportToGsb(true);
    setShowPhishlabsModal(true);
  };

  const handleConfirmPhishlabsAction = async () => {
    if (phishlabsAction === 'fetch') {
      await handleExecutePhishlabsFetch();
    } else if (phishlabsAction === 'create') {
      await handleExecutePhishlabsIncident();
    }
  };

  const handleExecutePhishlabsFetch = async () => {
    try {
      setCreatingPhishlabs(true);
      setPhishMessage({ text: '', type: '' });
      const response = await api.findings.typosquat.fetchPhishlabsInfo(
        finding.typo_domain,
        finding.program_name
      );

      if (response.status === 'success') {
        const jobId = response.job_id;
        setPhishMessage({
          text: `${response.message || 'PhishLabs fetch job created successfully'} (Job ID: ${jobId})`,
          type: 'info'
        });

        // Note: Don't refresh finding immediately since processing is async
        // The job uses improved logic that tries multiple URL formats
        // Users should check job status or refresh page later to see results
        setTimeout(() => setPhishMessage({ text: '', type: '' }), 10000);
      } else {
        setPhishMessage({
          text: response.message || 'Failed to create PhishLabs fetch job',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error creating PhishLabs fetch job:', err);
      setPhishMessage({
        text: err.response?.data?.detail || err.message || 'Error creating PhishLabs fetch job.',
        type: 'danger'
      });
    } finally {
      setCreatingPhishlabs(false);
      setShowPhishlabsModal(false);
    }
  };

  const handleExecutePhishlabsIncident = async () => {
    if (!selectedCatcode) {
      alert('Please select a category code');
      return;
    }

    try {
      setCreatingPhishlabs(true);
      setPhishMessage({ text: '', type: '' });
      const response = await api.findings.typosquat.createPhishlabsIncident(
        finding.typo_domain,
        finding.program_name,
        selectedCatcode,
        phishlabsComment,
        reportToGsb
      );

      if (response.status === 'success') {
        const jobId = response.job_id;

        setPhishMessage({
          text: `PhishLabs incident job started (ID: ${jobId}). Processing domain ${response.typo_domain}...`,
          type: 'info'
        });

        // Start polling for job status instead of static timeout
        try {
          await startJobPolling(jobId);
        } catch (pollingErr) {
          console.error('Error starting job polling:', pollingErr);
          setPhishMessage({
            text: `Job created but failed to start status polling: ${pollingErr.message}`,
            type: 'warning'
          });
        }
      } else {
        setPhishMessage({
          text: response.message || 'Failed to create PhishLabs incident job',
          type: 'danger'
        });
      }
    } catch (err) {
      console.error('Error creating PhishLabs incident:', err);
      setPhishMessage({
        text: err.response?.data?.detail || err.message || 'Error creating PhishLabs incident job.',
        type: 'danger'
      });
    } finally {
      // Only reset state if we're not polling a job
      if (!pollingJobId) {
        setCreatingPhishlabs(false);
        setShowPhishlabsModal(false);
        setSelectedCatcode('');
        setPhishlabsComment('');
        setReportToGsb(false);
      } else {
        // Keep the modal open but change the state to indicate polling
        setCreatingPhishlabs(false);
      }
    }
  };

  // Job Status Polling Functions
  const startJobPolling = async (jobId) => {
    setPollingJobId(jobId);
    setJobStatus(null);
    setJobPollingProgress('Starting job...');

    // Clear any existing polling interval
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }

    // Set maximum polling time (10 minutes)
    const maxPollingTime = 10 * 60 * 1000; // 10 minutes in milliseconds
    const startTime = Date.now();

    // Start polling every 2 seconds
    const interval = setInterval(async () => {
      try {
        // Check if maximum polling time has been exceeded
        if (Date.now() - startTime > maxPollingTime) {
          clearInterval(interval);
          setPollingInterval(null);
          setJobPollingProgress('Job polling timeout reached');
          setPhishMessage({
            text: 'Job polling timeout reached (10 minutes). The job may still be running. Please refresh the page later to check results.',
            type: 'warning'
          });
          setPollingJobId(null);
          setJobStatus(null);
          setJobPollingProgress('');
          return;
        }

        const response = await api.jobs.getStatus(jobId);

        if (response.status === 'success' && response.job) {
          const job = response.job;
          setJobStatus(job);

          // Update progress message based on job status
          switch (job.status) {
            case 'pending':
              setJobPollingProgress('Job queued, waiting to start...');
              break;
            case 'running':
              setJobPollingProgress(`Processing... (${job.progress || 0}%)`);
              break;
            case 'completed':
              setJobPollingProgress('Job completed successfully!');
              clearInterval(interval);
              setPollingInterval(null);
              await handleJobCompletion(job);
              break;
            case 'failed':
              setJobPollingProgress(`Job failed: ${job.message || 'Unknown error'}`);
              clearInterval(interval);
              setPollingInterval(null);
              setPhishMessage({
                text: `PhishLabs incident creation failed: ${job.message || 'Unknown error'}`,
                type: 'danger'
              });
              break;
            default:
              setJobPollingProgress(`Status: ${job.status}`);
          }
        }
      } catch (err) {
        console.error('Error polling job status:', err);
        setJobPollingProgress('Error checking job status');
        clearInterval(interval);
        setPollingInterval(null);

        // Show user-friendly error message
        const errorMessage = err.response?.data?.detail || err.message || 'Unknown error occurred';
        setPhishMessage({
          text: `Error checking job status: ${errorMessage}. You may need to refresh the page to see results.`,
          type: 'danger'
        });

        // Reset polling state on error
        setPollingJobId(null);
        setJobStatus(null);
        setJobPollingProgress('');
      }
    }, 2000); // Poll every 2 seconds

    setPollingInterval(interval);
  };

  const handleJobCompletion = async (job) => {
    try {
      // Refresh finding data to show the new PhishLabs incident
      const params = new URLSearchParams(location.search);
      const idParam = params.get('id');

      let updatedFinding;
      if (idParam) {
        updatedFinding = await api.findings.typosquat.getByIdUnified(idParam);
      } else if (id) {
        updatedFinding = await api.findings.typosquat.getById(id);
      }

      if (updatedFinding) {
        setFinding(updatedFinding);

        // Show success message with incident details
        const incidentId = updatedFinding.phishlabs_data?.incident_id ||
                          updatedFinding.phishlabs_incident_id ||
                          'Unknown';

        setPhishMessage({
          text: `PhishLabs incident created successfully! Incident ID: ${incidentId}`,
          type: 'success'
        });

        // Clear the success message after 10 seconds
        setTimeout(() => setPhishMessage({ text: '', type: '' }), 10000);
      }
    } catch (err) {
      console.error('Error refreshing finding data:', err);
      setPhishMessage({
        text: 'Incident created but failed to refresh data. Please refresh the page manually.',
        type: 'warning'
      });
    } finally {
      // Reset polling state and modal state
      setPollingJobId(null);
      setJobStatus(null);
      setJobPollingProgress('');
      setShowPhishlabsModal(false);
      setSelectedCatcode('');
      setPhishlabsComment('');
      setReportToGsb(false);
    }
  };

  const stopJobPolling = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
    setPollingJobId(null);
    setJobStatus(null);
    setJobPollingProgress('');
  };

  // -----------------------------------------------------------------------
  // Derived data & normalisers (must come *before* any early returns so that
  // React Hooks are called unconditionally in every render).
  const dnsRecords = React.useMemo(() => {
    // Use new schema fields first, fallback to info object
    const records = {};
    if (Array.isArray(finding?.dns_a_records) && finding.dns_a_records.length) {
      records.A = finding.dns_a_records;
    } else if (Array.isArray(finding?.info?.dns_a) && finding.info.dns_a.length) {
      records.A = finding.info.dns_a;
    }
    if (Array.isArray(finding?.dns_mx_records) && finding.dns_mx_records.length) {
      records.MX = finding.dns_mx_records;
    } else if (Array.isArray(finding?.info?.dns_mx) && finding.info.dns_mx.length) {
      records.MX = finding.info.dns_mx;
    }
    return Object.keys(records).length ? records : null;
  }, [finding]);

  // // Use new schema fields with fallback to info object
  // const sslCertificate = {
  //   has_ssl: finding?.ssl_has_ssl,
  //   issuer: finding?.ssl_issuer,
  //   subject: finding?.ssl_subject,
  //   valid_from: finding?.ssl_valid_from,
  //   valid_to: finding?.ssl_valid_to,
  //   self_signed: finding?.ssl_self_signed
  // } || finding?.info?.ssl_cert || finding?.info?.ssl || null;
  
  // const httpInfo = {
  //   status_code: finding?.http_status_code,
  //   title: finding?.http_title,
  //   server: finding?.http_server,
  //   redirects: finding?.http_redirects
  // } || finding?.info?.http || null;
  
  const country = finding?.geoip_country || finding?.info?.country || finding?.info?.geoip?.country || null;
  const ipAddress = finding?.dns_a_records?.[0] || finding?.info?.ip || (Array.isArray(finding?.info?.dns_a) ? finding.info.dns_a[0] : null);

  // -----------------------------------------------------------------------
  // PhishLabs data
  // -----------------------------------------------------------------------
  // Use new schema fields with fallback to info object
  const phishlabsIncident = finding?.phishlabs_data ? {
    Infraction: {
      IncidentID: finding.phishlabs_data.incident_id,
      Url: finding.phishlabs_data.url,
      Domain: finding?.typo_domain,
      Catcode: finding.phishlabs_data.category_code,
      Catname: finding.phishlabs_data.category_name,
      Status: finding.phishlabs_data.status,
      Comment: finding.phishlabs_data.comment,
      Product: finding.phishlabs_data.product,
      Createdate: finding.phishlabs_data.create_date,
      Assignee: finding.phishlabs_data.assignee,
      Lastcomment: finding.phishlabs_data.last_comment,
      Groupcatname: finding.phishlabs_data.group_category_name,
      Actiondescr: finding.phishlabs_data.action_description,
      Statusdescr: finding.phishlabs_data.status_description,
      Mitigationstart: finding.phishlabs_data.mitigation_start,
      Dateresolved: finding.phishlabs_data.date_resolved,
      Severityname: finding.phishlabs_data.severity_name,
      Mxrecord: finding.phishlabs_data.mx_record,
      Ticketstatus: finding.phishlabs_data.ticket_status,
      Resolutionstatus: finding.phishlabs_data.resolution_status,
      Incidentstatus: finding.phishlabs_data.incident_status
    }
  } : (finding?.phishlabs_incident || null);
  
  const phishlabsCreateIncident = finding?.phishlabs_createincident || null;
  const phishlabsIncidentId = finding?.phishlabs_data?.incident_id || finding?.phishlabs_incident_id || null;

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading typosquat finding...</p>
        </div>
      </Container>
    );
  }

  if (error) {
    return (
      <Container fluid className="p-4">
        <Alert variant="danger">
          <Alert.Heading>Error Loading Finding</Alert.Heading>
          <p>{error}</p>
          <Button variant="outline-danger" onClick={() => navigate(-1)}>
            Go Back
          </Button>
        </Alert>
      </Container>
    );
  }

  if (!finding) {
    return (
      <Container fluid className="p-4">
        <Alert variant="warning">
          <Alert.Heading>Finding Not Found</Alert.Heading>
          <p>The requested typosquat finding could not be found.</p>
          <Button variant="outline-warning" onClick={() => navigate(-1)}>
            Go Back
          </Button>
        </Alert>
      </Container>
    );
  }

  const whoisDisplay = getTyposquatWhoisForDisplay(finding);

  return (
    <Container fluid className="p-4">
      {/* Header */}
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h1 className="d-inline">Typosquat Finding Details</h1>
        </div>
        <div className="d-flex align-items-center">
                <Button
                  variant="outline-info"
                  onClick={handleFetchPhishlabs}
                  disabled={creatingPhishlabs}
                  className="me-2"
                >
                  {creatingPhishlabs ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-2" />
                      Fetching...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-cloud-download"></i> Fetch PhishLabs Incident
                    </>
                  )}
                </Button>
                <Button
                  variant="outline-success"
                  onClick={handleCreatePhishlabsIncident}
                  disabled={creatingPhishlabs}
                  className="me-2"
                >
                  {creatingPhishlabs ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-2" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-plus-circle"></i> Create Phishlabs Incident
                    </>
                  )}
                </Button>
          <Button 
            variant="outline-danger" 
            onClick={() => setShowDeleteModal(true)}
            className="me-2"
          >
            <i className="bi bi-trash"></i> Delete
          </Button>
          <Button variant="outline-primary" onClick={() => navigate('/findings/typosquat')} className="me-3">
            ← Back to Typosquat Domains
          </Button>
        </div>
      </div>

      {/* Basic Information */}
      <Card className="mb-4">
        <Card.Header>
          <h6 className="mb-0">Basic Information</h6>
        </Card.Header>
        <Card.Body>
          <Row>
            <Col md={6}>
              <Table borderless size="sm">
                <tbody>
                  <tr>
                    <td><strong>Typo Domain:</strong></td>
                    <td>
                      <div className="d-flex align-items-center">
                        <strong className="me-2">{finding.typo_domain}</strong>
                        {finding.typo_domain && (
                          <div>
                            <Button
                              variant="outline-secondary"
                              size="sm"
                              onClick={handleCopyDomain}
                              className="me-1"
                              title="Copy to clipboard"
                            >
                              📋
                            </Button>
                            <Button
                              variant="outline-secondary"
                              size="sm"
                              onClick={handleCopyDefanged}
                              title="Copy to clipboard (defanged)"
                            >
                              🛡️
                            </Button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Status:</strong></td>
                    <td>
                      <Badge bg={getStatusBadgeVariant(finding.status)} id="current-status-badge">
                        {formatStatus(finding.status)}
                      </Badge>
                      {finding.auto_resolve && (
                        <Badge bg="info" className="ms-2">Would auto-resolve</Badge>
                      )}
                      {finding.assigned_to && (
                        <div>
                          <small className="text-muted">Assigned to: <span id="assigned-user">{finding.assigned_to_username || formatAssignedTo(finding.assigned_to)}</span></small>
                        </div>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td>{finding.created_at ? formatDate(finding.created_at) : <span className="text-muted">N/A</span>}</td>
                  </tr>
                  <tr>
                    <td><strong>Updated:</strong></td>
                    <td>{finding.updated_at ? formatDate(finding.updated_at) : <span className="text-muted">N/A</span>}</td>
                  </tr>
                </tbody>
              </Table>
            </Col>
            <Col md={6}>
              <Table borderless size="sm">
                <tbody>
                  <tr>
                    <td><strong>GeoIP Country:</strong></td>
                    <td>
                      {country ? (
                        <Badge bg="info">{country}</Badge>
                      ) : (
                        <span className="text-muted">N/A</span>
                      )}
                    </td>
                  </tr>
                  {/* <tr>
                    <td><strong>Registered:</strong></td>
                    <td>
                      {finding.info?.registered ? (
                        <Badge bg="warning">Yes</Badge>
                      ) : (
                        <Badge bg="success">No</Badge>
                      )}
                    </td>
                  </tr> */}
                  <tr>
                    <td><strong>IP Address:</strong></td>
                    <td>{ipAddress || <span className="text-muted">N/A</span>}</td>
                  </tr>
                  <tr>
                    <td><strong>Program:</strong></td>
                    <td>{finding.program_name || <span className="text-muted">N/A</span>}</td>
                  </tr>
                  <tr>
                    <td><strong>Source:</strong></td>
                    <td>
                      {finding.source ? (
                        <Badge bg="secondary">{finding.source}</Badge>
                      ) : (
                        <span className="text-muted">N/A</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Actions Taken:</strong></td>
                    <td>
                      {finding.action_taken && finding.action_taken.length > 0 ? (
                        <div>
                          {finding.action_taken.map((action, index) => (
                            <Badge key={index} bg="success" className="me-1 mb-1">
                              {formatActionTaken(action)}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted">None</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Parked Domain:</strong></td>
                    <td>
                      {finding.is_parked === true ? (
                        <Badge bg="warning">Yes - Parked</Badge>
                      ) : finding.is_parked === false ? (
                        <Badge bg="success">No</Badge>
                      ) : (
                        <span className="text-muted">Not Detected</span>
                      )}
                    </td>
                  </tr>
                </tbody>
              </Table>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {/* Investigation Status */}
      <Card className="mb-4">
        <Card.Header>
          <h6 className="mb-0">Investigation Status</h6>
        </Card.Header>
        <Card.Body>
          <Form onSubmit={handleStatusSubmit}>
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Change Status *</Form.Label>
                  <Form.Select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    disabled={statusLoading}
                  >
                    {getAllowedStatusOptions(finding?.status).map((statusOption) => (
                      <option key={statusOption.value} value={statusOption.value}>
                        {statusOption.label}
                      </option>
                    ))}
                  </Form.Select>
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>
                    Assign To
                    {status === 'inprogress' && <span className="text-danger">*</span>}
                  </Form.Label>
                  <Form.Select
                    value={selectedAssignedTo}
                    onChange={(e) => setSelectedAssignedTo(e.target.value)}
                    disabled={statusLoading || usersLoading}
                    className={status === 'inprogress' && !selectedAssignedTo ? 'is-invalid' : ''}
                  >
                    <option value="">Unassigned</option>
                    {availableUsers.map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.username} ({user.email})
                      </option>
                    ))}
                  </Form.Select>
                  {usersLoading && (
                    <Form.Text className="text-muted">
                      <Spinner animation="border" size="sm" className="me-1" />
                      Loading users...
                    </Form.Text>
                  )}
                  {status === 'inprogress' && !selectedAssignedTo && (
                    <Form.Text className="text-danger">
                      An assigned user is required for 'In Progress' status
                    </Form.Text>
                  )}
                  {finding?.status === 'inprogress' && status === 'new' && (
                    <Form.Text className="text-info">
                      User will be automatically unassigned when changing to 'New' status
                    </Form.Text>
                  )}
                </Form.Group>
              </Col>
            </Row>

            <Row>
              <Col md={12}>
                <Form.Group className="mb-3">
                  <Form.Label>
                    Comment
                    {finding?.status === 'inprogress' && (status === 'dismissed' || status === 'resolved') && (
                      <span className="text-danger">* (Required for this status change)</span>
                    )}
                    {!(finding?.status === 'inprogress' && (status === 'dismissed' || status === 'resolved')) && (
                      <span className="text-muted">(Optional)</span>
                    )}
                  </Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    placeholder="Enter a comment about this status change..."
                    value={statusComment}
                    onChange={(e) => setStatusComment(e.target.value)}
                    disabled={statusLoading}
                    className={
                      finding?.status === 'inprogress' &&
                      (status === 'dismissed' || status === 'resolved') &&
                      !statusComment ? 'is-invalid' : ''
                    }
                  />
                  {finding?.status === 'inprogress' && (status === 'dismissed' || status === 'resolved') && !statusComment && (
                    <Form.Text className="text-danger">
                      A comment is required when changing from 'In Progress' to '{status === 'dismissed' ? 'Dismissed' : 'Resolved'}'
                    </Form.Text>
                  )}
                </Form.Group>
              </Col>
            </Row>

            {status === 'resolved' && (
              <Row>
                <Col md={6}>
                  <Form.Group className="mb-3">
                    <Form.Label>Action Taken (Optional)</Form.Label>
                    <Form.Select
                      value={actionTaken}
                      onChange={(e) => setActionTaken(e.target.value)}
                      disabled={statusLoading}
                    >
                      <option value="">Select an action...</option>
                      <option value="takedown_requested">Takedown requested</option>
                      <option value="reported_google_safe_browsing">Reported to Google Safe Browsing</option>
                      <option value="blocked_firewall">Blocked on firewall</option>
                      <option value="monitoring">Monitoring</option>
                      <option value="other">Other</option>
                    </Form.Select>
                  </Form.Group>
                </Col>
              </Row>
            )}

            <Row>
              <Col>
                <div className="d-flex gap-2">
                  {/* Show Start Investigation button only if status is 'new' AND finding is unassigned */}
                  {finding.status === 'new' && !finding.assigned_to && (
                    <Button
                      variant="warning"
                      onClick={handleStartInvestigation}
                      disabled={statusLoading}
                    >
                      {statusLoading ? (
                        <Spinner animation="border" size="sm" />
                      ) : (
                        <>👤 Start Investigation</>
                      )}
                    </Button>
                  )}
                  <Button
                    variant="primary"
                    type="submit"
                    disabled={statusLoading}
                  >
                    {statusLoading ? (
                      <Spinner animation="border" size="sm" />
                    ) : (
                      <>💾 Update Status</>
                    )}
                  </Button>
                </div>
              </Col>
            </Row>

          </Form>
          
          {/* Status Messages */}
          {statusMessage.text && (
            <Alert variant={statusMessage.type} className="mt-3 mb-0">
              {statusMessage.text}
            </Alert>
          )}
        </Card.Body>
      </Card>

      {/* History Section */}
      <Card className="mb-4">
        <Card.Header>
          <h6 className="mb-0">📋 History</h6>
        </Card.Header>
        <Card.Body>
          {actionLogsLoading ? (
            <div className="text-center">
              <Spinner animation="border" size="sm" />
              <span className="ms-2">Loading history...</span>
            </div>
          ) : actionLogs.length > 0 ? (
            <div className="timeline">
              {actionLogs.map((log, index) => {
                // The API already returns parsed objects, no need to parse again
                const oldValue = log.old_value;
                const newValue = log.new_value;
                const metadata = log.metadata;
                const isLatest = index === 0; // First item is the most recent

                return (
                  <div key={log.id} className={`${isLatest ? 'mb-3 pb-2' : 'mb-2 pb-1'} ${isLatest ? 'border-bottom border-2' : 'border-bottom'} ${!isLatest ? 'opacity-60' : ''}`}>
                    <div className="d-flex justify-content-between align-items-center mb-1">
                      <span className={`${isLatest ? 'fw-bold h6 mb-0' : 'fw-normal small'} text-body`}>
                        {formatActionType(log.action_type)}
                        {isLatest && <Badge bg="primary" className="ms-2 small">Latest</Badge>}
                      </span>
                      <small className={`${isLatest ? 'text-body' : 'text-muted'} ${!isLatest ? 'small' : ''}`}>
                        {formatDate(log.created_at)} by {log.user?.username || 'Unknown User'}
                      </small>
                    </div>

                    {log.action_type === 'status_change' && (
                      <div>
                        {/* Status Change Details */}
                        {oldValue?.status && newValue?.status ? (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className="d-flex align-items-center">
                              <Badge
                                bg={getStatusBadgeVariant(oldValue.status)}
                                className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                              >
                                {formatStatus(oldValue.status)}
                              </Badge>
                              <div className="mx-2 d-flex align-items-center">
                                <span className={`${isLatest ? 'text-primary fs-5' : 'text-muted'}`}>→</span>
                              </div>
                              <Badge
                                bg={getStatusBadgeVariant(newValue.status)}
                                className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                              >
                                {formatStatus(newValue.status)}
                              </Badge>
                            </div>
                          </div>
                        ) : newValue?.status ? (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <small className="text-muted me-2">Status set to</small>
                            <Badge
                              bg={getStatusBadgeVariant(newValue.status)}
                              className={isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}
                            >
                              {formatStatus(newValue.status)}
                            </Badge>
                          </div>
                        ) : oldValue?.status ? (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <small className="text-muted me-2">Previous status:</small>
                            <Badge
                              bg={getStatusBadgeVariant(oldValue.status)}
                              className={isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}
                            >
                              {formatStatus(oldValue.status)}
                            </Badge>
                          </div>
                        ) : null}

                        {/* Comment */}
                        {metadata?.comment && (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className={`${isLatest ? 'bg-primary-subtle border-start border-primary border-3 p-2' : 'bg-body-tertiary p-1'} rounded`}>
                              <i className={`bi bi-chat-text ${isLatest ? 'text-primary' : 'text-muted'} me-1`}></i>
                              <small className="text-muted me-1">Comment:</small>
                              <span className={`${isLatest ? 'fw-medium' : ''} ${!isLatest ? 'small' : ''}`}>{metadata.comment}</span>
                            </div>
                          </div>
                        )}

                        {/* Action Taken */}
                        {metadata?.action_taken && (
                          <div className={!isLatest ? 'small' : ''}>
                            <i className={`bi bi-check-circle text-success me-1 ${!isLatest ? 'small' : ''}`}></i>
                            <small className="text-muted me-2">Action taken:</small>
                            <Badge
                              bg="success"
                              className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                            >
                              {formatActionTaken(metadata.action_taken)}
                            </Badge>
                          </div>
                        )}
                      </div>
                    )}

                    {log.action_type === 'assignment_change' && (
                      <div>
                        {/* Assignment Change Details */}
                        {oldValue?.assigned_to !== undefined && newValue?.assigned_to !== undefined ? (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className="d-flex align-items-center">
                              {oldValue.assigned_to ? (
                                <Badge
                                  bg="secondary"
                                  className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                                >
                                  {oldValue.assigned_to_username || oldValue.assigned_to}
                                </Badge>
                              ) : (
                                <Badge
                                  bg="light"
                                  text="dark"
                                  className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                                >
                                  Unassigned
                                </Badge>
                              )}
                              <div className="mx-2 d-flex align-items-center">
                                <span className={`${isLatest ? 'text-primary fs-5' : 'text-muted'}`}>→</span>
                              </div>
                              {newValue.assigned_to ? (
                                <Badge
                                  bg="info"
                                  className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                                >
                                  {newValue.assigned_to_username || newValue.assigned_to}
                                </Badge>
                              ) : (
                                <Badge
                                  bg="light"
                                  text="dark"
                                  className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                                >
                                  Unassigned
                                </Badge>
                              )}
                            </div>
                          </div>
                        ) : newValue?.assigned_to !== undefined ? (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <small className="text-muted me-2">Assigned to</small>
                            {newValue.assigned_to ? (
                              <Badge
                                bg="info"
                                className={isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}
                              >
                                {newValue.assigned_to_username || newValue.assigned_to}
                              </Badge>
                            ) : (
                              <Badge
                                bg="light"
                                text="dark"
                                className={isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}
                              >
                                Unassigned
                              </Badge>
                            )}
                          </div>
                        ) : oldValue?.assigned_to !== undefined ? (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <small className="text-muted me-2">Previously assigned to</small>
                            {oldValue.assigned_to ? (
                              <Badge
                                bg="secondary"
                                className={isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}
                              >
                                {oldValue.assigned_to_username || oldValue.assigned_to}
                              </Badge>
                            ) : (
                              <Badge
                                bg="light"
                                text="dark"
                                className={isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}
                              >
                                Unassigned
                              </Badge>
                            )}
                          </div>
                        ) : null}

                        {/* Comment for assignment change */}
                        {metadata?.comment && (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className={`${isLatest ? 'bg-info-subtle border-start border-info border-3 p-2' : 'bg-body-tertiary p-1'} rounded`}>
                              <i className={`bi bi-chat-text ${isLatest ? 'text-info' : 'text-muted'} me-1`}></i>
                              <small className="text-muted me-1">Comment:</small>
                              <span className={`${isLatest ? 'fw-medium' : ''} ${!isLatest ? 'small' : ''}`}>{metadata.comment}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {log.action_type === 'phishlabs_incident_created' && (
                      <div>
                        {/* PhishLabs Incident Details */}
                        {newValue?.phishlabs_incident_id && (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className="d-flex align-items-center">
                              <i className={`bi bi-shield-check text-success me-2 ${!isLatest ? 'small' : ''}`}></i>
                              <small className="text-muted me-2">Incident ID:</small>
                              <Badge
                                bg="success"
                                className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                              >
                                {newValue.phishlabs_incident_id}
                              </Badge>
                              <small className="text-muted ms-3 me-2">Category:</small>
                              <Badge
                                bg="success"
                                className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                              >
                                {metadata.catcode}
                              </Badge>
                            </div>
                          </div>
                        )}

                        {/* Comment for PhishLabs incident */}
                        {metadata?.comment && (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className={`${isLatest ? 'bg-success-subtle border-start border-success border-3 p-2' : 'bg-body-tertiary p-1'} rounded`}>
                              <i className={`bi bi-chat-text ${isLatest ? 'text-success' : 'text-muted'} me-1`}></i>
                              <small className="text-muted me-1">Comment:</small>
                              <span className={`${isLatest ? 'fw-medium' : ''} ${!isLatest ? 'small' : ''}`}>{metadata.comment}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {log.action_type === 'google_safe_browsing_reported' && (
                      <div>
                        {/* Google Safe Browsing Report Details */}
                        {newValue?.gsb_reference_id && (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className="d-flex align-items-center">
                              <i className={`bi bi-shield-fill-check text-info me-2 ${!isLatest ? 'small' : ''}`}></i>
                              <small className="text-muted me-2">GSB Reference ID:</small>
                              <Badge
                                bg="info"
                                className={`${isLatest ? 'px-3 py-1' : 'px-2 py-1 small'}`}
                              >
                                {newValue.gsb_reference_id}
                              </Badge>
                            </div>
                          </div>
                        )}

                        {/* Comment for GSB report */}
                        {metadata?.comment && (
                          <div className={`mb-2 ${!isLatest ? 'small' : ''}`}>
                            <div className={`${isLatest ? 'bg-info-subtle border-start border-info border-3 p-2' : 'bg-body-tertiary p-1'} rounded`}>
                              <i className={`bi bi-chat-text ${isLatest ? 'text-info' : 'text-muted'} me-1`}></i>
                              <small className="text-muted me-1">Comment:</small>
                              <span className={`${isLatest ? 'fw-medium' : ''} ${!isLatest ? 'small' : ''}`}>{metadata.comment}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <Alert variant="info" className="py-2 mb-0">
              <i className="fas fa-info-circle me-2"></i>
              No history records found for this finding.
            </Alert>
          )}
        </Card.Body>
      </Card>

      {/* Parked Domain Detection Details */}
      {finding.is_parked === true && finding.parked_detection_reasons && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">
              🅿️ Parked Domain Detection
              {finding.parked_confidence !== null && finding.parked_confidence !== undefined && (
                <Badge bg={finding.parked_confidence >= 80 ? 'danger' : finding.parked_confidence >= 60 ? 'warning' : 'info'} className="ms-2">
                  {finding.parked_confidence}% confidence
                </Badge>
              )}
            </h6>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => toggleSection('parked')}
            >
              {expandedSections.parked ? 'Hide' : 'Show'}
            </Button>
          </Card.Header>
          <Collapse in={expandedSections.parked}>
            <Card.Body>
              {finding.parked_detection_timestamp && (
                <div className="mb-3">
                  <small className="text-muted">
                    Detected on: {formatDate(finding.parked_detection_timestamp)}
                  </small>
                </div>
              )}
              {finding.parked_confidence !== null && finding.parked_confidence !== undefined && (
                <div className="mb-3">
                  <strong>Confidence Score:</strong> {finding.parked_confidence}%
                  <small className="text-muted ms-2">
                    (Based on DNS/HTTP indicators and similarity to protected domains)
                  </small>
                </div>
              )}
              
              <Row>
                {finding.parked_detection_reasons.nameserver_matches && finding.parked_detection_reasons.nameserver_matches.length > 0 && (
                  <Col md={6} className="mb-3">
                    <h6>Nameserver Matches</h6>
                    <div>
                      {finding.parked_detection_reasons.nameserver_matches.map((ns, index) => (
                        <Badge key={index} bg="warning" className="me-1 mb-1">
                          {ns}
                        </Badge>
                      ))}
                    </div>
                    <small className="text-muted">Parking service nameservers detected</small>
                  </Col>
                )}
                
                {finding.parked_detection_reasons.mx_matches && finding.parked_detection_reasons.mx_matches.length > 0 && (
                  <Col md={6} className="mb-3">
                    <h6>MX Server Matches</h6>
                    <div>
                      {finding.parked_detection_reasons.mx_matches.map((mx, index) => (
                        <Badge key={index} bg="warning" className="me-1 mb-1">
                          {mx}
                        </Badge>
                      ))}
                    </div>
                    <small className="text-muted">Parking service MX servers detected</small>
                  </Col>
                )}
                
                {finding.parked_detection_reasons.title_keywords && finding.parked_detection_reasons.title_keywords.length > 0 && (
                  <Col md={6} className="mb-3">
                    <h6>Title Keywords</h6>
                    <div>
                      {finding.parked_detection_reasons.title_keywords.map((keyword, index) => (
                        <Badge key={index} bg="info" className="me-1 mb-1">
                          {keyword}
                        </Badge>
                      ))}
                    </div>
                    <small className="text-muted">Parking-related keywords found in page title</small>
                  </Col>
                )}
                
                {finding.parked_detection_reasons.body_keywords && finding.parked_detection_reasons.body_keywords.length > 0 && (
                  <Col md={6} className="mb-3">
                    <h6>Body Keywords</h6>
                    <div>
                      {finding.parked_detection_reasons.body_keywords.map((keyword, index) => (
                        <Badge key={index} bg="info" className="me-1 mb-1">
                          {keyword}
                        </Badge>
                      ))}
                    </div>
                    <small className="text-muted">Parking-related keywords found in page content</small>
                  </Col>
                )}
                
                {finding.parked_detection_reasons.indicators && finding.parked_detection_reasons.indicators.length > 0 && (
                  <Col md={12} className="mb-3">
                    <h6>Other Indicators</h6>
                    <div>
                      {finding.parked_detection_reasons.indicators.map((indicator, index) => (
                        <Badge key={index} bg="secondary" className="me-1 mb-1">
                          {indicator.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </Badge>
                      ))}
                    </div>
                  </Col>
                )}
                {finding.parked_detection_reasons.a_matches && finding.parked_detection_reasons.a_matches.length > 0 && (
                  <Col md={12} className="mb-3">
                    <h6>A Record Matches (Parking IP Ranges)</h6>
                    <div>
                      {finding.parked_detection_reasons.a_matches.map((match, index) => (
                        <Badge key={index} bg="danger" className="me-1 mb-1">
                          {match}
                        </Badge>
                      ))}
                    </div>
                    <small className="text-muted">
                      A-record IPs matching known parking service networks (per parking_services.json)
                    </small>
                  </Col>
                )}
                
                {finding.parked_detection_reasons.similarity_match && (
                  <Col md={12} className="mb-3">
                    <h6>Protected Domain Similarity</h6>
                    <div>
                      <Badge bg="primary" className="me-2">
                        {finding.parked_detection_reasons.similarity_match.protected_domain}
                      </Badge>
                      <Badge bg="info">
                        {finding.parked_detection_reasons.similarity_match.similarity_percent}% similar
                      </Badge>
                    </div>
                    <small className="text-muted">
                      Similarity to protected domain based on Levenshtein distance calculation
                    </small>
                  </Col>
                )}
              </Row>
            </Card.Body>
          </Collapse>
        </Card>
      )}

      {/* DNS Records */}
      {dnsRecords && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">DNS Records</h6>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => toggleSection('dns')}
            >
              {expandedSections.dns ? 'Hide' : 'Show'}
            </Button>
          </Card.Header>
          <Collapse in={expandedSections.dns}>
            <Card.Body>
              <Table borderless size="sm">
                <tbody>
                  {Object.entries(dnsRecords)
                    .filter(([, records]) => records && records.length > 0)
                    .map(([recordType, records]) => (
                      <tr key={recordType}>
                        <td><strong>{recordType} Records:</strong></td>
                        <td>
                          {records.map((record, index) => (
                            <Badge key={index} bg="secondary" className="me-1">
                              {record}
                            </Badge>
                          ))}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </Table>
            </Card.Body>
          </Collapse>
        </Card>
      )}

      {/* WHOIS Information */}
      {whoisDisplay && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">WHOIS Information</h6>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => toggleSection('whois')}
            >
              {expandedSections.whois ? 'Hide' : 'Show'}
            </Button>
          </Card.Header>
          <Collapse in={expandedSections.whois}>
            <Card.Body>
              {whoisDisplay.kind === 'string' ? (
                <pre className="bg-body-secondary p-2 rounded small text-body">
                  {whoisDisplay.value}
                </pre>
              ) : (
                <Row>
                  <Col md={6}>
                    <Table borderless size="sm">
                      <tbody>
                        {whoisDisplay.value.domain_name && (
                          <tr>
                            <td><strong>Domain Name:</strong></td>
                            <td>{whoisDisplay.value.domain_name}</td>
                          </tr>
                        )}
                        {whoisDisplay.value.registrar && (
                          <tr>
                            <td><strong>Registrar:</strong></td>
                            <td>{whoisDisplay.value.registrar}</td>
                          </tr>
                        )}
                        {whoisDisplay.value.creation_date && (
                          <tr>
                            <td><strong>Creation Date:</strong></td>
                            <td>{formatDate(whoisDisplay.value.creation_date, 'MMM dd, yyyy')}</td>
                          </tr>
                        )}
                        {whoisDisplay.value.expiration_date && (
                          <tr>
                            <td><strong>Expiration Date:</strong></td>
                            <td>{formatDate(whoisDisplay.value.expiration_date, 'MMM dd, yyyy')}</td>
                          </tr>
                        )}
                      </tbody>
                    </Table>
                  </Col>
                  <Col md={6}>
                    <Table borderless size="sm">
                      <tbody>
                        {whoisDisplay.value.registrant_name && (
                          <tr>
                            <td><strong>Registrant Name:</strong></td>
                            <td>{whoisDisplay.value.registrant_name}</td>
                          </tr>
                        )}
                        {whoisDisplay.value.registrant_org && (
                          <tr>
                            <td><strong>Registrant Org:</strong></td>
                            <td>{whoisDisplay.value.registrant_org}</td>
                          </tr>
                        )}
                        {whoisDisplay.value.registrant_country && (
                          <tr>
                            <td><strong>Registrant Country:</strong></td>
                            <td>{whoisDisplay.value.registrant_country}</td>
                          </tr>
                        )}
                        {whoisDisplay.value.admin_email && (
                          <tr>
                            <td><strong>Admin Email:</strong></td>
                            <td>{whoisDisplay.value.admin_email}</td>
                          </tr>
                        )}
                      </tbody>
                    </Table>
                  </Col>
                </Row>
              )}
            </Card.Body>
          </Collapse>
        </Card>
      )}

      {/* Protected Domain Similarities */}
      {finding && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h6 className="mb-0">
              🛡️ Protected Domain Similarities
              {(finding.protected_domain_similarities?.length > 0) && (
                <Badge bg="info" className="ms-2">
                  {finding.protected_domain_similarities.length} protected domain
                  {finding.protected_domain_similarities.length !== 1 ? 's' : ''}
                </Badge>
              )}
            </h6>
            <div className="d-flex gap-2 align-items-center">
              <Button
                variant="outline-primary"
                size="sm"
                disabled={recalculatingSimilarities}
                onClick={handleRecalculateFindingSimilarities}
                title="Recompute similarity scores for this domain against the program's current protected domains"
              >
                {recalculatingSimilarities ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-1" />
                    Recalculating…
                  </>
                ) : (
                  <>
                    <i className="bi bi-arrow-clockwise me-1"></i>
                    Recalculate
                  </>
                )}
              </Button>
              <Button
                variant="outline-secondary"
                size="sm"
                onClick={() => toggleSection('similarities')}
              >
                {expandedSections.similarities ? 'Hide' : 'Show'}
              </Button>
            </div>
          </Card.Header>
          <Collapse in={expandedSections.similarities}>
            <Card.Body>
              {similarityRecalcMessage.text && (
                <Alert variant={similarityRecalcMessage.type} className="mb-3">
                  {similarityRecalcMessage.text}
                </Alert>
              )}
              <p className="text-muted mb-3">
                Similarity scores between this typosquat domain (<code>{finding.typo_domain}</code>) and the
                program&apos;s protected domains.
              </p>
              {(!finding.protected_domain_similarities ||
                finding.protected_domain_similarities.length === 0) && (
                <p className="text-muted mb-0">No similarity scores stored yet. Use Recalculate to compute them.</p>
              )}
              {finding.protected_domain_similarities && finding.protected_domain_similarities.length > 0 && (
                <>
                  {(() => {
                    const sortedSimilarities = [...finding.protected_domain_similarities]
                      .sort((a, b) => (b.similarity_percent || 0) - (a.similarity_percent || 0));
                    const displaySimilarities = similaritiesShowAll
                      ? sortedSimilarities
                      : sortedSimilarities.slice(0, 3);
                    const hasMore = sortedSimilarities.length > 3;
                    return (
                      <>
                        <Table striped bordered hover size="sm">
                          <thead>
                            <tr>
                              <th>Protected Domain</th>
                              <th>Similarity</th>
                              <th>Calculated At</th>
                            </tr>
                          </thead>
                          <tbody>
                            {displaySimilarities.map((similarity, index) => (
                              <tr key={index}>
                                <td>
                                  <code>{similarity.protected_domain}</code>
                                </td>
                                <td>
                                  <Badge
                                    bg={
                                      similarity.similarity_percent >= 80
                                        ? 'danger'
                                        : similarity.similarity_percent >= 60
                                          ? 'warning'
                                          : similarity.similarity_percent >= 40
                                            ? 'info'
                                            : 'secondary'
                                    }
                                  >
                                    {similarity.similarity_percent?.toFixed(1) || 0}%
                                  </Badge>
                                </td>
                                <td>
                                  <small className="text-muted">
                                    {similarity.calculated_at ? formatDate(similarity.calculated_at) : 'N/A'}
                                  </small>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </Table>
                        {hasMore && (
                          <Button
                            variant="outline-primary"
                            size="sm"
                            className="mt-2"
                            onClick={() => setSimilaritiesShowAll(!similaritiesShowAll)}
                          >
                            {similaritiesShowAll ? 'Show less' : `Show all ${sortedSimilarities.length} domains`}
                          </Button>
                        )}
                      </>
                    );
                  })()}
                  {finding.protected_domain_similarities.some((s) => s.similarity_percent >= 60) && (
                    <Alert variant="warning" className="mt-3 mb-0">
                      <i className="bi bi-exclamation-triangle me-2"></i>
                      High similarity detected with one or more protected domains. This domain may be attempting to
                      impersonate your brand.
                    </Alert>
                  )}
                </>
              )}
            </Card.Body>
          </Collapse>
        </Card>
      )}

      {/* AI Analysis - visible to admin/superuser only */}
      {isAdmin() && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">
              AI Threat Analysis
              {finding.ai_analysis && (
                <Badge
                  bg={getAiThreatBadgeVariant(finding.ai_analysis.threat_level)}
                  className="ms-2"
                >
                  {finding.ai_analysis.threat_level?.toUpperCase()} ({finding.ai_analysis.confidence}%)
                </Badge>
              )}
            </h6>
            <div className="d-flex gap-2 align-items-center">
              {aiModels.length > 0 && (
                <Form.Select
                  size="sm"
                  style={{ width: 'auto', minWidth: '160px' }}
                  value={aiSelectedModel}
                  onChange={(e) => setAiSelectedModel(e.target.value)}
                  disabled={aiAnalyzing}
                >
                  <option value="">{aiDefaultModel} (default)</option>
                  {aiModels
                    .filter(m => m.name !== aiDefaultModel)
                    .map(m => (
                      <option key={m.name} value={m.name}>
                        {m.name}{m.parameter_size ? ` (${m.parameter_size})` : ''}
                      </option>
                    ))}
                </Form.Select>
              )}
              <Button
                variant={finding.ai_analysis ? 'outline-secondary' : 'outline-primary'}
                size="sm"
                disabled={aiAnalyzing}
                onClick={() => handleAiAnalyze(!!finding.ai_analysis)}
              >
                {aiAnalyzing ? (
                  <><Spinner animation="border" size="sm" className="me-1" /> Analyzing...</>
                ) : finding.ai_analysis ? (
                  'Re-analyze'
                ) : (
                  'Run AI Analysis'
                )}
              </Button>
              {finding.ai_analysis && (
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={() => toggleSection('aiAnalysis')}
                >
                  {expandedSections.aiAnalysis ? 'Hide' : 'Show'}
                </Button>
              )}
            </div>
          </Card.Header>
          {aiMessage.text && (
            <Alert variant={aiMessage.type} className="mb-0 rounded-0 border-start-0 border-end-0">
              {aiMessage.text}
            </Alert>
          )}
          {finding.ai_analysis && (
            <Collapse in={expandedSections.aiAnalysis}>
              <Card.Body>
                <Row>
                  <Col md={6}>
                    <Table borderless size="sm">
                      <tbody>
                        <tr>
                          <td style={{width: '40%'}}><strong>Threat Level:</strong></td>
                          <td>
                            <Badge bg={getAiThreatBadgeVariant(finding.ai_analysis.threat_level)}>
                              {finding.ai_analysis.threat_level?.toUpperCase()}
                            </Badge>
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Confidence:</strong></td>
                          <td>{finding.ai_analysis.confidence}%</td>
                        </tr>
                        <tr>
                          <td><strong>Recommended Action:</strong></td>
                          <td>
                            <Badge bg="info">
                              {formatActionTaken(finding.ai_analysis.recommended_action)}
                            </Badge>
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Model:</strong></td>
                          <td><code>{finding.ai_analysis.model}</code></td>
                        </tr>
                        <tr>
                          <td><strong>Analyzed At:</strong></td>
                          <td>
                            <small className="text-muted">
                              {finding.ai_analyzed_at ? formatDate(finding.ai_analyzed_at) : finding.ai_analysis.analyzed_at ? formatDate(finding.ai_analysis.analyzed_at) : 'N/A'}
                            </small>
                          </td>
                        </tr>
                      </tbody>
                    </Table>
                  </Col>
                  <Col md={6}>
                    {finding.ai_analysis.indicators && finding.ai_analysis.indicators.length > 0 && (
                      <div className="mb-3">
                        <strong>Threat Indicators:</strong>
                        <div className="mt-1">
                          {finding.ai_analysis.indicators.map((indicator, i) => (
                            <Badge key={i} bg="outline-dark" className="me-1 mb-1 border text-dark">
                              {indicator}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </Col>
                </Row>
                <div className="mt-2">
                  <strong>Summary:</strong>
                  <p className="mt-1 mb-2">{finding.ai_analysis.summary}</p>
                </div>
                <div>
                  <strong>Reasoning:</strong>
                  <p className="mt-1 mb-0 text-muted" style={{whiteSpace: 'pre-wrap'}}>
                    {finding.ai_analysis.reasoning}
                  </p>
                </div>
              </Card.Body>
            </Collapse>
          )}
          {!finding.ai_analysis && !aiAnalyzing && (
            <Card.Body>
              <p className="text-muted mb-0">
                No AI analysis available yet. Click "Run AI Analysis" to analyze this finding using the configured LLM.
              </p>
            </Card.Body>
          )}
        </Card>
      )}

      {/* Threatstream Data */}
      {finding.threatstream_data && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">🔍 Threatstream Intelligence</h6>
            <div className="d-flex align-items-center">
              {finding.threatstream_data.threatscore && (
                <Badge
                  bg={
                    finding.threatstream_data.threatscore >= 80 ? 'danger' :
                    finding.threatstream_data.threatscore >= 60 ? 'warning' :
                    finding.threatstream_data.threatscore >= 40 ? 'info' :
                    'secondary'
                  }
                  className="me-2"
                >
                  Threat Score: {finding.threatstream_data.threatscore}
                </Badge>
              )}
              <Button
                variant="outline-secondary"
                size="sm"
                onClick={() => toggleSection('threatstream')}
              >
                {expandedSections.threatstream ? 'Hide' : 'Show'}
              </Button>
            </div>
          </Card.Header>
          <Collapse in={expandedSections.threatstream}>
            <Card.Body>
              <Row className="mb-4">
                <Col md={6}>
                  <Table borderless size="sm">
                    <tbody>
                      {finding.threatstream_data.id && (
                        <tr>
                          <td><strong>Threatstream ID:</strong></td>
                          <td>
                            <code className="small">{finding.threatstream_data.id}</code>
                          </td>
                        </tr>
                      )}
                      {finding.threatstream_data.source && (
                        <tr>
                          <td><strong>Source:</strong></td>
                          <td>
                            <Badge bg="info">{finding.threatstream_data.source}</Badge>
                          </td>
                        </tr>
                      )}
                      {finding.threatstream_data.threat_type && (
                        <tr>
                          <td><strong>Threat Type:</strong></td>
                          <td>
                            <Badge bg="warning">{finding.threatstream_data.threat_type}</Badge>
                          </td>
                        </tr>
                      )}
                      {finding.threatstream_data.confidence && (
                        <tr>
                          <td><strong>Confidence:</strong></td>
                          <td>
                            <Badge bg={
                              finding.threatstream_data.confidence >= 80 ? 'success' :
                              finding.threatstream_data.confidence >= 60 ? 'info' :
                              finding.threatstream_data.confidence >= 40 ? 'warning' :
                              'secondary'
                            }>
                              {finding.threatstream_data.confidence}%
                            </Badge>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </Col>
                <Col md={6}>
                  <Table borderless size="sm">
                    <tbody>
                      {finding.threatstream_data.org && (
                        <tr>
                          <td><strong>Organization:</strong></td>
                          <td>{finding.threatstream_data.org}</td>
                        </tr>
                      )}
                      {finding.threatstream_data.created_ts && (
                        <tr>
                          <td><strong>Created:</strong></td>
                          <td>{formatDate(finding.threatstream_data.created_ts)}</td>
                        </tr>
                      )}
                      {finding.threatstream_data.modified_ts && (
                        <tr>
                          <td><strong>Last Modified:</strong></td>
                          <td>{formatDate(finding.threatstream_data.modified_ts)}</td>
                        </tr>
                      )}
                      {finding.threatstream_data.expiration_ts && (
                        <tr>
                          <td><strong>Expires:</strong></td>
                          <td>{formatDate(finding.threatstream_data.expiration_ts)}</td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </Col>
              </Row>

              {/* Description */}
              {finding.threatstream_data.description && (
                <div className="mb-4">
                  <h6>Description</h6>
                  <div className="bg-body-tertiary p-3 rounded border">
                    <p className="mb-0">{finding.threatstream_data.description}</p>
                  </div>
                </div>
              )}

              {/* Tags */}
              {finding.threatstream_data.tags && finding.threatstream_data.tags.length > 0 && (
                <div className="mb-4">
                  <h6>Tags</h6>
                  <div>
                    {finding.threatstream_data.tags.map((tag, index) => (
                      <Badge key={index} bg="secondary" className="me-1 mb-1">
                        {typeof tag === 'string' ? tag : tag.name || tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Locations */}
              {finding.threatstream_data.locations && finding.threatstream_data.locations.length > 0 && (
                <div className="mb-4">
                  <h6>Associated Locations</h6>
                  <div>
                    {finding.threatstream_data.locations.map((location, index) => (
                      <Badge key={index} bg="info" className="me-1 mb-1">
                        {location.name || location.value || location}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Additional Threatstream Data */}
              <div>
                <h6>Additional Intelligence Data</h6>
                <Table size="sm" borderless>
                  <tbody>
                    {finding.threatstream_data.itype && (
                      <tr>
                        <td><strong>Intelligence Type:</strong></td>
                        <td><code className="small">{finding.threatstream_data.itype}</code></td>
                      </tr>
                    )}
                    {finding.threatstream_data.feed_id && (
                      <tr>
                        <td><strong>Feed ID:</strong></td>
                        <td><code className="small">{finding.threatstream_data.feed_id}</code></td>
                      </tr>
                    )}
                    {finding.threatstream_data.retina_confidence && (
                      <tr>
                        <td><strong>Retina Confidence:</strong></td>
                        <td>
                          <Badge bg={
                            finding.threatstream_data.retina_confidence >= 0 ? 'success' : 'secondary'
                          }>
                            {finding.threatstream_data.retina_confidence}
                          </Badge>
                        </td>
                      </tr>
                    )}
                    {finding.threatstream_data.source_reported_confidence && (
                      <tr>
                        <td><strong>Source Reported Confidence:</strong></td>
                        <td>
                          <Badge bg={
                            finding.threatstream_data.source_reported_confidence >= 80 ? 'success' :
                            finding.threatstream_data.source_reported_confidence >= 60 ? 'info' :
                            finding.threatstream_data.source_reported_confidence >= 40 ? 'warning' :
                            'secondary'
                          }>
                            {finding.threatstream_data.source_reported_confidence}%
                          </Badge>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </Table>
              </div>
            </Card.Body>
          </Collapse>
        </Card>
      )}

      {/* RecordedFuture Data */}
      {finding.recordedfuture_data && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">🔮 RecordedFuture Intelligence</h6>
            <div className="d-flex align-items-center">
              {finding.recordedfuture_data.risk_score && (
                <Badge
                  bg={
                    finding.recordedfuture_data.risk_score >= 80 ? 'danger' :
                    finding.recordedfuture_data.risk_score >= 60 ? 'warning' :
                    finding.recordedfuture_data.risk_score >= 40 ? 'info' :
                    'secondary'
                  }
                  className="me-2"
                >
                  Risk Score: {finding.recordedfuture_data.risk_score}
                </Badge>
              )}
              <Button
                variant="outline-secondary"
                size="sm"
                onClick={() => toggleSection('recordedfuture')}
              >
                {expandedSections.recordedfuture ? 'Hide' : 'Show'}
              </Button>
            </div>
          </Card.Header>
          <Collapse in={expandedSections.recordedfuture}>
            <Card.Body>
              <Row className="mb-4">
                <Col md={6}>
                  <Table borderless size="sm">
                    <tbody>
                      {finding.recordedfuture_data.alert_id && (
                        <tr>
                          <td><strong>Alert ID:</strong></td>
                          <td>
                            <code className="small">{finding.recordedfuture_data.alert_id}</code>
                          </td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.status && (
                        <tr>
                          <td><strong>Status:</strong></td>
                          <td>
                            <Badge bg="info">{finding.recordedfuture_data.status}</Badge>
                          </td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.category && (
                        <tr>
                          <td><strong>Category:</strong></td>
                          <td>
                            <Badge bg="warning">{finding.recordedfuture_data.category}</Badge>
                          </td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.priority && (
                        <tr>
                          <td><strong>Priority:</strong></td>
                          <td>
                            <Badge bg={
                              finding.recordedfuture_data.priority === 'High' ? 'danger' :
                              finding.recordedfuture_data.priority === 'Moderate' ? 'warning' :
                              finding.recordedfuture_data.priority === 'Low' ? 'info' :
                              'secondary'
                            }>
                              {finding.recordedfuture_data.priority}
                            </Badge>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </Col>
                <Col md={6}>
                  <Table borderless size="sm">
                    <tbody>
                      {finding.recordedfuture_data.owner_name && (
                        <tr>
                          <td><strong>Owner:</strong></td>
                          <td>{finding.recordedfuture_data.owner_name}</td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.organisation_name && (
                        <tr>
                          <td><strong>Organization:</strong></td>
                          <td>{finding.recordedfuture_data.organisation_name}</td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.created && (
                        <tr>
                          <td><strong>Created:</strong></td>
                          <td>{formatDate(finding.recordedfuture_data.created)}</td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.updated && (
                        <tr>
                          <td><strong>Last Updated:</strong></td>
                          <td>{formatDate(finding.recordedfuture_data.updated)}</td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </Col>
              </Row>

              {/* Title and Entity Information */}
              {(finding.recordedfuture_data.raw_alert?.title || finding.recordedfuture_data.entity_id) && (
                <div className="mb-4">
                  {finding.recordedfuture_data.raw_alert?.title && (
                    <div className="mb-3">
                      <h6>Alert Title</h6>
                      <div className="bg-body-tertiary p-3 rounded border">
                        <p className="mb-0">{finding.recordedfuture_data.raw_alert.title}</p>
                      </div>
                    </div>
                  )}
                  {finding.recordedfuture_data.entity_id && (
                    <div className="mb-3">
                      <h6>Entity</h6>
                      <div className="bg-body-tertiary p-3 rounded border">
                        <p className="mb-0">
                          <strong>ID:</strong> {finding.recordedfuture_data.entity_id}
                          {finding.recordedfuture_data.entity_criticality && (
                            <>
                              <br />
                              <strong>Criticality:</strong> <Badge bg={
                                finding.recordedfuture_data.entity_criticality === 'High' ? 'danger' :
                                finding.recordedfuture_data.entity_criticality === 'Medium' ? 'warning' :
                                finding.recordedfuture_data.entity_criticality === 'Low' ? 'info' :
                                'secondary'
                              }>{finding.recordedfuture_data.entity_criticality}</Badge>
                            </>
                          )}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Additional Alert Data */}
              {(finding.recordedfuture_data.assignee_name || finding.recordedfuture_data.targets || finding.recordedfuture_data.raw_details?.panel_evidence_summary?.explanation) && (
                <div className="mb-4">
                  <h6>Additional Alert Information</h6>
                  <Table size="sm" borderless>
                    <tbody>
                      {finding.recordedfuture_data.assignee_name && (
                        <tr>
                          <td><strong>Assignee:</strong></td>
                          <td>{finding.recordedfuture_data.assignee_name}</td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.targets && finding.recordedfuture_data.targets.length > 0 && (
                        <tr>
                          <td><strong>Targets:</strong></td>
                          <td>
                            {finding.recordedfuture_data.targets.map((target, index) => (
                              <Badge key={index} bg="secondary" className="me-1">
                                {target}
                              </Badge>
                            ))}
                          </td>
                        </tr>
                      )}
                      {finding.recordedfuture_data.raw_details?.panel_evidence_summary?.explanation && (
                        <tr>
                          <td><strong>Explanation:</strong></td>
                          <td>{finding.recordedfuture_data.raw_details.panel_evidence_summary.explanation}</td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </div>
              )}

              {/* DNS Evidence */}
              {finding.recordedfuture_data.raw_details?.panel_evidence_dns?.ip_list && finding.recordedfuture_data.raw_details.panel_evidence_dns.ip_list.length > 0 && (
                <div className="mb-4">
                  <h6>DNS Evidence</h6>
                  <Table size="sm" borderless>
                    <tbody>
                      <tr>
                        <td><strong>IP Addresses:</strong></td>
                        <td>
                          {finding.recordedfuture_data.raw_details.panel_evidence_dns.ip_list.map((ip, index) => (
                            <div key={index} className="mb-1">
                              <Badge bg="info" className="me-2">
                                {ip.entity.replace('ip:', '')}
                              </Badge>
                              <small className="text-muted">
                                {ip.record_type} record
                                {ip.risk_score > 0 && ` - Risk: ${ip.risk_score}`}
                              </small>
                            </div>
                          ))}
                        </td>
                      </tr>
                    </tbody>
                  </Table>
                </div>
              )}

              {/* WHOIS Evidence */}
              {finding.recordedfuture_data.raw_details?.panel_evidence_whois?.body && finding.recordedfuture_data.raw_details.panel_evidence_whois.body.length > 0 && (
                <div>
                  <h6>WHOIS Evidence</h6>
                  <Table size="sm" borderless>
                    <tbody>
                      {finding.recordedfuture_data.raw_details.panel_evidence_whois.body
                        .filter(item => item.attribute === 'attr:whois' && item.value)
                        .map((item, index) => (
                        <React.Fragment key={index}>
                          {item.value.registrarName && (
                            <tr>
                              <td><strong>Registrar:</strong></td>
                              <td>{item.value.registrarName}</td>
                            </tr>
                          )}
                          {item.value.createdDate && (
                            <tr>
                              <td><strong>Created Date:</strong></td>
                              <td>{formatDate(item.value.createdDate, 'MMM dd, yyyy')}</td>
                            </tr>
                          )}
                          {item.value.expiresDate && (
                            <tr>
                              <td><strong>Expires Date:</strong></td>
                              <td>{formatDate(item.value.expiresDate, 'MMM dd, yyyy')}</td>
                            </tr>
                          )}
                          {item.value.status && (
                            <tr>
                              <td><strong>Status:</strong></td>
                              <td><Badge bg="secondary">{item.value.status}</Badge></td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </Table>
                </div>
              )}
            </Card.Body>
          </Collapse>
        </Card>
      )}

      {phishMessage.text && (
        <Alert variant={phishMessage.type} className="mb-4">
          {phishMessage.text}
        </Alert>
      )}

      {/* PhishLabs Information */}
      {(phishlabsIncident || phishlabsCreateIncident) && (
        <Card className="mb-4">
          <Card.Header>
            <div className="d-flex justify-content-between align-items-center">
              <h6 className="mb-0">PhishLabs Incident</h6>
              {/* <div className="d-flex align-items-center">
                <Button
                  variant="outline-info"
                  onClick={handleFetchPhishlabs}
                  disabled={creatingPhishlabs}
                  className="me-2"
                >
                  {creatingPhishlabs ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-2" />
                      Fetching...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-cloud-download"></i> Fetch PhishLabs Incident
                    </>
                  )}
                </Button>
                <Button
                  variant="outline-success"
                  onClick={handleCreatePhishlabsIncident}
                  disabled={creatingPhishlabs}
                  className="me-2"
                >
                  {creatingPhishlabs ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-2" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-plus-circle"></i> Create Phishlabs Incident
                    </>
                  )}
                </Button>
              </div> */}
            </div>
          </Card.Header>
          <Card.Body>
            <Row className="mb-3">
              {phishlabsIncidentId && (
                <Col md={6} className="mb-2">
                  <strong>Incident ID:</strong> {phishlabsIncidentId}
                </Col>
              )}
              {(finding.phishlabs_data?.last_updated || finding.phishlabs_last_updated) && (
                <Col md={6} className="mb-2">
                  <strong>Last Updated:</strong> {formatLocalDate(finding.phishlabs_data?.last_updated || finding.phishlabs_last_updated)}
                </Col>
              )}

            </Row>

            {/* CreateIncident Summary */}
{/*             {phishlabsCreateIncident && (
              <div className="mb-4">
                <h6>Create Incident Response</h6>
                <Table size="sm" borderless>
                  <tbody>
                    <tr>
                      <td><strong>Request ID:</strong></td>
                      <td>{phishlabsCreateIncident.RequestId || 'N/A'}</td>
                    </tr>
                    <tr>
                      <td><strong>Error Message:</strong></td>
                      <td>{phishlabsCreateIncident.ErrorMessage || 'None'}</td>
                    </tr>
                  </tbody>
                </Table>
              </div>
            )} 
*/}

            {/* Infraction Details */}
            {phishlabsIncident?.Infraction && (
              <div className="mb-4">
                <h6>Infraction Details</h6>
                <Table size="sm" borderless>
                  <tbody>
                    <tr>
                      <td><strong>Status:</strong></td>
                      <td>{phishlabsIncident.Infraction.Status}</td>
                    </tr>
                    <tr>
                      <td><strong>Category:</strong></td>
                      <td>{phishlabsIncident.Infraction.Catname}</td>
                    </tr>
                    <tr>
                      <td><strong>Severity:</strong></td>
                      <td>{phishlabsIncident.Infraction.Severityname}</td>
                    </tr>
                    <tr>
                      <td><strong>Created:</strong></td>
                      <td>{formatLocalDate(phishlabsIncident.Infraction.Createdate)}</td>
                    </tr>
                    {phishlabsIncident.Infraction.Lastcomment && (
                      <tr>
                        <td><strong>Last Comment:</strong></td>
                        <td>{phishlabsIncident.Infraction.Lastcomment}</td>
                      </tr>
                    )}
                  </tbody>
                </Table>
              </div>
            )}

            {/* Enrichment Data */}
            {phishlabsIncident?.EnrichmentData && (
              <div>
                <h6>Enrichment Data</h6>
                <Table size="sm" borderless>
                  <tbody>
                    <tr>
                      <td><strong>IP Address:</strong></td>
                      <td>{phishlabsIncident.EnrichmentData.IpAddress}</td>
                    </tr>
                    <tr>
                      <td><strong>Country:</strong></td>
                      <td>{phishlabsIncident.EnrichmentData.Country}</td>
                    </tr>
                    <tr>
                      <td><strong>Registrar:</strong></td>
                      <td>{phishlabsIncident.EnrichmentData.RegistrarName}</td>
                    </tr>
                    {phishlabsIncident.EnrichmentData.RegistrationDate && (
                      <tr>
                        <td><strong>Registration Date:</strong></td>
                        <td>{formatDate(phishlabsIncident.EnrichmentData.RegistrationDate, 'MMM dd, yyyy')}</td>
                      </tr>
                    )}
                    {phishlabsIncident.EnrichmentData.ExpiryDate && (
                      <tr>
                        <td><strong>Expiry Date:</strong></td>
                        <td>{formatDate(phishlabsIncident.EnrichmentData.ExpiryDate, 'MMM dd, yyyy')}</td>
                      </tr>
                    )}
                  </tbody>
                </Table>
              </div>
            )}
          </Card.Body>
        </Card>
      )}

      {/* Notes Section */}
      <NotesSection
        assetType="typosquat finding"
        assetId={finding._id}
        currentNotes={finding.notes || ''}
        apiUpdateFunction={api.findings.typosquat.updateNotes}
        onNotesUpdate={handleNotesUpdate}
      />

      {/* Related Typosquat Domains */}
      <Card className="mb-4">
        <Card.Header>
          <h6 className="mb-0">🌐 Related Typosquat Domains</h6>
        </Card.Header>
        <Card.Body>
          {finding?.typo_domain && (
            <div className="mb-3">
              <small className="text-muted">
                Showing all typosquat domains sharing the same base domain as <strong>{getApexDomain(finding.typo_domain)}</strong>
              </small>
            </div>
          )}
          {relatedDomainsLoading ? (
            <div className="text-center">
              <Spinner animation="border" size="sm" />
              <span className="ms-2">Loading related domains...</span>
            </div>
          ) : relatedDomains.length > 0 ? (
            <>
            <div className="table-responsive">
              <Table hover size="sm">
                <thead className="table-light">
                  <tr>
                    <th>Typo Domain</th>
                    <th>Status</th>
                    <th>IP Addresses</th>
                    <th>Country</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(relatedDomainsShowAll ? relatedDomains : relatedDomains.slice(0, 10)).map((domain) => (
                    <tr key={domain.id}>
                      <td>
                        <div className="d-flex align-items-center">
                          <span className="me-2">
                            {domain.typo_domain === finding.typo_domain ? (
                              <Badge bg="warning" className="me-2">Current</Badge>
                            ) : null}
                            <strong>{domain.typo_domain}</strong>
                          </span>
                        </div>
                      </td>
                      <td>
                        <Badge bg={getStatusBadgeVariant(domain.status)}>
                          {formatStatus(domain.status)}
                        </Badge>
                      </td>
                      <td>
                        {domain.dns_a_records && domain.dns_a_records.length > 0 ? (
                          <div>
                            {domain.dns_a_records.slice(0, 2).map((ip, idx) => (
                              <Badge key={idx} bg="secondary" className="me-1 mb-1 small">
                                {ip}
                              </Badge>
                            ))}
                            {domain.dns_a_records.length > 2 && (
                              <Badge bg="info" className="small">
                                +{domain.dns_a_records.length - 2} more
                              </Badge>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted">No IPs</span>
                        )}
                      </td>
                      <td>
                        {domain.geoip_country ? (
                          <Badge bg="info">{domain.geoip_country}</Badge>
                        ) : (
                          <span className="text-muted">N/A</span>
                        )}
                      </td>
                      <td>
                        <Button
                          variant="outline-primary"
                          size="sm"
                          onClick={() => navigate(`/findings/typosquat/details?id=${encodeURIComponent(domain.id)}`)}
                          title="View typosquat finding details"
                        >
                          <i className="bi bi-eye"></i>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
            {relatedDomains.length > 10 && (
              <Button
                variant="outline-primary"
                size="sm"
                className="mt-2"
                onClick={() => setRelatedDomainsShowAll(!relatedDomainsShowAll)}
              >
                {relatedDomainsShowAll ? 'Show less' : `Show all ${relatedDomains.length} domains`}
              </Button>
            )}
            </>
          ) : (
            <Alert variant="info" className="py-2 mb-0">
              <i className="fas fa-info-circle me-2"></i>
              No related typosquat domains found for this base domain.
            </Alert>
          )}
        </Card.Body>
      </Card>

      {/* Related Domain URLs */}
      <Card className="mb-4">
        <Card.Header>
          <h6 className="mb-0">🔗 Related Domain URLs</h6>
        </Card.Header>
        <Card.Body>
          {finding?.typo_domain && (
            <div className="mb-3">
              <small className="text-muted">
                Showing URLs from all domains sharing the same apex domain as <strong>{finding.typo_domain}</strong>
              </small>
            </div>
          )}
          {urlsLoading ? (
            <div className="text-center">
              <Spinner animation="border" size="sm" />
              <span className="ms-2">Loading URLs from related domains...</span>
            </div>
          ) : typosquatUrls.length > 0 ? (
            <>
            <div className="table-responsive">
              <Table hover size="sm">
                <thead className="table-light">
                  <tr>
                    <th>Domain</th>
                    <th>URL</th>
                    <th>Status Code</th>
                    <th>Content Type</th>
                    <th>Response Time</th>
                    <th>Technologies</th>
                  </tr>
                </thead>
                <tbody>
                  {(relatedUrlsShowAll ? typosquatUrls : typosquatUrls.slice(0, 10)).map((urlData) => (
                    <tr key={urlData.id || urlData._id}>
                      <td>
                        {urlData.typo_domain ? (
                          <Badge 
                            bg={urlData.typo_domain === finding?.typo_domain ? 'primary' : 'secondary'}
                            className="text-wrap"
                            title={urlData.typo_domain === finding?.typo_domain ? 'Current domain' : 'Related domain'}
                          >
                            {urlData.typo_domain}
                          </Badge>
                        ) : (
                          <span className="text-muted">Unknown</span>
                        )}
                      </td>
                      <td>
                        <div className="text-break" style={{ maxWidth: '300px' }}>
                          <button
                            onClick={() => navigate(`/findings/typosquat-urls/details?id=${urlData.id || urlData._id}`)}
                            className="btn btn-link text-decoration-none text-primary p-0 border-0 bg-transparent"
                            style={{ cursor: 'pointer' }}
                            title="Click to view URL details"
                          >
                            {urlData.url}
                          </button>
                        </div>
                      </td>
                      <td>
                        {urlData.http_status_code ? (
                          <Badge bg={
                            urlData.http_status_code >= 200 && urlData.http_status_code < 300 ? 'success' :
                            urlData.http_status_code >= 300 && urlData.http_status_code < 400 ? 'warning' :
                            urlData.http_status_code >= 400 ? 'danger' : 'secondary'
                          }>
                            {urlData.http_status_code}
                          </Badge>
                        ) : (
                          <span className="text-muted">N/A</span>
                        )}
                      </td>
                      <td>
                        {urlData.content_type ? (
                          <code className="small">{urlData.content_type}</code>
                        ) : (
                          <span className="text-muted">N/A</span>
                        )}
                      </td>
                      <td>
                        {urlData.response_time_ms ? (
                          <span>{urlData.response_time_ms} ms</span>
                        ) : (
                          <span className="text-muted">N/A</span>
                        )}
                      </td>
                      <td>
                        {urlData.technologies && urlData.technologies.length > 0 ? (
                          <div>
                            {urlData.technologies.slice(0, 3).map((tech, idx) => (
                              <Badge key={idx} bg="info" className="me-1 mb-1 small">
                                {tech}
                              </Badge>
                            ))}
                            {urlData.technologies.length > 3 && (
                              <Badge bg="secondary" className="small">
                                +{urlData.technologies.length - 3} more
                              </Badge>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted">None</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
            {typosquatUrls.length > 10 && (
              <Button
                variant="outline-primary"
                size="sm"
                className="mt-2"
                onClick={() => setRelatedUrlsShowAll(!relatedUrlsShowAll)}
              >
                {relatedUrlsShowAll ? 'Show less' : `Show all ${typosquatUrls.length} URLs`}
              </Button>
            )}
            </>
          ) : (
            <Alert variant="info" className="py-2 mb-0">
              <i className="fas fa-info-circle me-2"></i>
              No URLs found for any related domains.
            </Alert>
          )}
        </Card.Body>
      </Card>

      {/* Screenshots Section */}
      <Card className="mb-4">
        <Card.Header>
          <h6 className="mb-0">📸 Screenshots from Related URLs</h6>
        </Card.Header>
        <Card.Body>
          <RelatedScreenshotsViewer
            relatedUrls={typosquatUrls}
            programName={finding?.program_name}
          />
        </Card.Body>
      </Card>

      {/* Fuzzing Techniques */}
      {finding.fuzzers && finding.fuzzers.length > 0 && (
        <Card className="mb-4">
          <Card.Header>
            <h6 className="mb-0">Fuzzing Techniques Used</h6>
          </Card.Header>
          <Card.Body>
            <div className="d-flex flex-wrap gap-2">
              {finding.fuzzers.map((fuzzer, index) => (
                <Badge key={index} bg="primary" className="fs-6 px-3 py-2">
                  🪄 {formatFuzzerName(fuzzer)}
                </Badge>
              ))}
            </div>
            <div className="mt-3">
              <small className="text-muted">
                ℹ️ These are the fuzzing techniques that were used to generate this typosquat domain from the original domain.
              </small>
            </div>
          </Card.Body>
        </Card>
      )}

      {/* SSL Certificate
      {sslCertificate && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">SSL Certificate</h6>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => toggleSection('ssl')}
            >
              {expandedSections.ssl ? 'Hide' : 'Show'}
            </Button>
          </Card.Header>
          <Collapse in={expandedSections.ssl}>
            <Card.Body>
              <Table borderless size="sm">
                <tbody>
                  {sslCertificate.subject && (
                    <tr>
                      <td><strong>Subject:</strong></td>
                      <td>{formatCertField(sslCertificate.subject, 'subject')}</td>
                    </tr>
                  )}
                  {sslCertificate.issuer && (
                    <tr>
                      <td><strong>Issuer:</strong></td>
                      <td>{formatCertField(sslCertificate.issuer, 'issuer')}</td>
                    </tr>
                  )}
                  {sslCertificate.valid_from && (
                    <tr>
                      <td><strong>Valid From:</strong></td>
                      <td>{sslCertificate.valid_from}</td>
                    </tr>
                  )}
                  {sslCertificate.valid_to && (
                    <tr>
                      <td><strong>Valid To:</strong></td>
                      <td>{sslCertificate.valid_to}</td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </Card.Body>
          </Collapse>
        </Card>
      )}

      {httpInfo && (
        <Card className="mb-4">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">HTTP Information</h6>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => toggleSection('http')}
            >
              {expandedSections.http ? 'Hide' : 'Show'}
            </Button>
          </Card.Header>
          <Collapse in={expandedSections.http}>
            <Card.Body>
              <Table borderless size="sm">
                <tbody>
                  {httpInfo.status_code && (
                    <tr>
                      <td><strong>Status Code:</strong></td>
                      <td>
                        <Badge 
                          bg={
                            httpInfo.status_code >= 200 && httpInfo.status_code < 300 ? 'success' :
                            httpInfo.status_code >= 300 && httpInfo.status_code < 400 ? 'warning' :
                            httpInfo.status_code >= 400 && httpInfo.status_code < 500 ? 'danger' :
                            httpInfo.status_code >= 500 ? 'dark' : 'secondary'
                          }
                        >
                          {httpInfo.status_code}
                        </Badge>
                      </td>
                    </tr>
                  )}
                  {httpInfo.title && (
                    <tr>
                      <td><strong>Page Title:</strong></td>
                      <td>
                        <span className="text-white">
                          {httpInfo.title}
                        </span>
                      </td>
                    </tr>
                  )}
                  {httpInfo.server && (
                    <tr>
                      <td><strong>Server:</strong></td>
                      <td>
                        <Badge bg="info">
                          {httpInfo.server}
                        </Badge>
                      </td>
                    </tr>
                  )}
                  {httpInfo.redirects !== undefined && (
                    <tr>
                      <td><strong>Redirects:</strong></td>
                      <td>
                        {httpInfo.redirects ? (
                          <Badge bg="warning">Yes</Badge>
                        ) : (
                          <Badge bg="success">No</Badge>
                        )}
                      </td>
                    </tr>
                  )}
                  {httpInfo.content_type && (
                    <tr>
                      <td><strong>Content Type:</strong></td>
                      <td>
                        <Badge bg="secondary">
                          {httpInfo.content_type}
                        </Badge>
                      </td>
                    </tr>
                  )}
                  {httpInfo.content_length && (
                    <tr>
                      <td><strong>Content Length:</strong></td>
                      <td>
                        <span className="text-body">
                          {httpInfo.content_length} bytes
                        </span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </Card.Body>
          </Collapse>
        </Card>
      )} */}

      {/* Full Finding JSON */}
      <Card className="mb-4">
        <Card.Header className="d-flex justify-content-between align-items-center">
          <h6 className="mb-0">Full Finding (JSON)</h6>
          <div>
            <Button
              variant="outline-primary"
              size="sm"
              onClick={copyJsonToClipboard}
              className="me-2"
            >
              📋 Copy JSON
            </Button>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => toggleSection('json')}
            >
              {expandedSections.json ? 'Hide' : 'Show'}
            </Button>
          </div>
        </Card.Header>
        <Collapse in={expandedSections.json}>
          <Card.Body>
            <pre className="bg-body-tertiary text-body p-3 rounded border" style={{ fontSize: '0.875rem', maxHeight: '500px', overflow: 'auto' }}>
              {JSON.stringify(finding, null, 2)}
            </pre>
          </Card.Body>
        </Collapse>
      </Card>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => {
        setShowDeleteModal(false);
        setDeleteRelated(false);
      }}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Typosquat Finding</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete this typosquat finding?</p>
          <p className="text-muted">
            <strong>Typo Domain:</strong> {finding?.typo_domain}
          </p>
          
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
              <strong>Warning:</strong> Enabling "delete related" may delete many more findings than this one.
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
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Deleting...
              </>
            ) : (
              <>
                <i className="bi bi-trash"></i> Delete
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* PhishLabs Action Modal */}
      <Modal
        show={showPhishlabsModal}
        onHide={() => {
          // Prevent closing while polling unless job is completed or failed
          if (!pollingJobId || jobStatus?.status === 'completed' || jobStatus?.status === 'failed') {
            if (pollingJobId) {
              stopJobPolling();
            }
            setShowPhishlabsModal(false);
            setPhishlabsComment('');
            setReportToGsb(false);
            setSelectedCatcode('');
          }
        }}
        backdrop={pollingJobId && jobStatus?.status !== 'completed' && jobStatus?.status !== 'failed' ? 'static' : true}
        keyboard={!pollingJobId || jobStatus?.status === 'completed' || jobStatus?.status === 'failed'}
      >
        <Modal.Header closeButton>
          <Modal.Title>
            {phishlabsAction === 'fetch' ? 'Fetch PhishLabs Data' : 'Create PhishLabs Incident'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {/* Job Polling Progress Section */}
          {pollingJobId && jobPollingProgress && (
            <div className="mb-4 p-3 bg-info-subtle border border-info rounded">
              <div className="d-flex align-items-center mb-2">
                <Spinner animation="border" size="sm" className="me-2" />
                <strong>Job Status: {jobStatus?.status || 'Processing'}</strong>
              </div>
              <div className="text-info mb-2">{jobPollingProgress}</div>
              {jobStatus?.progress !== undefined && (
                <div className="progress mb-2">
                  <div
                    className="progress-bar"
                    role="progressbar"
                    style={{width: `${jobStatus.progress}%`}}
                    aria-valuenow={jobStatus.progress}
                    aria-valuemin="0"
                    aria-valuemax="100"
                  >
                    {jobStatus.progress}%
                  </div>
                </div>
              )}
              <small className="text-muted">
                Job ID: {pollingJobId}
                {jobStatus && (
                  <span className="ms-2">• Status: {jobStatus.status}</span>
                )}
              </small>
            </div>
          )}

          {!pollingJobId && (
            <p>
              {phishlabsAction === 'fetch'
                ? `Fetch PhishLabs data for ${finding.typo_domain}?`
                : `Create PhishLabs incident for ${finding.typo_domain}?`
              }
            </p>
          )}

          {phishlabsAction === 'create' && !pollingJobId && (
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
                  Select the appropriate category for this typosquat finding
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
                  id="report-to-gsb-single"
                  label="Also report to Google Safe Browsing"
                  checked={reportToGsb}
                  onChange={(e) => setReportToGsb(e.target.checked)}
                />
                <Form.Text className="text-muted">
                  If checked, the domain will also be reported to Google Safe Browsing before creating the PhishLabs incident
                </Form.Text>
              </Form.Group>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          {pollingJobId ? (
            // Polling mode: Show different buttons
            <>
              <Button
                variant="outline-danger"
                onClick={() => {
                  stopJobPolling();
                  setShowPhishlabsModal(false);
                  setPhishlabsComment('');
                  setReportToGsb(false);
                  setSelectedCatcode('');
                }}
                disabled={jobStatus?.status === 'completed'}
              >
                Stop Polling & Close
              </Button>
              {jobStatus?.status === 'completed' && (
                <Button variant="success" onClick={() => {
                  setShowPhishlabsModal(false);
                  setPhishlabsComment('');
                  setReportToGsb(false);
                  setSelectedCatcode('');
                }}>
                  <i className="bi bi-check-circle me-2"></i>
                  Close
                </Button>
              )}
            </>
          ) : (
            // Normal mode: Show regular buttons
            <>
              <Button variant="secondary" onClick={() => {
                setShowPhishlabsModal(false);
                setPhishlabsComment('');
                setReportToGsb(false);
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
                    <i className={`bi bi-${phishlabsAction === 'fetch' ? 'cloud-download' : 'plus-circle'} me-2`}></i>
                    {phishlabsAction === 'fetch' ? 'Fetch Data' : 'Create Incident'}
                  </>
                )}
              </Button>
            </>
          )}
        </Modal.Footer>
      </Modal>

    </Container>
  );
}

export default TyposquatFindingDetail;