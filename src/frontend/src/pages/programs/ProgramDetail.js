import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Container, 
  Row, 
  Col, 
  Card, 
  Button, 
  Alert, 
  Spinner, 
  Badge,
  Table,
  Modal,
  Form,
  InputGroup,
  Tabs,
  Tab
} from 'react-bootstrap';
import { programAPI, aiAPI, authAPI } from '../../services/api';
import EventHandlerForm from '../../components/EventHandlerForm';
import ScopeDomainsEditor from '../../components/programs/ScopeDomainsEditor';
import { useAuth } from '../../contexts/AuthContext';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';
import {
  coerceHandlersList,
  formatEventTypesCell,
  sanitizeHandlerForSave,
  sanitizeHandlersList,
} from '../../utils/eventHandlerTypes';

const DEFAULT_NOTIFICATION_SETTINGS = {
  enabled: false,
  discord_webhook_url: '',
  events: {
    assets: {
      created: {
        subdomain: { enabled: false, webhook_url: '' },
        url: { enabled: false, webhook_url: '' },
        ip: { enabled: false, webhook_url: '' },
        service: { enabled: false, webhook_url: '' },
        certificate: { enabled: false, webhook_url: '' }
      },
      updated: {
        subdomain: { enabled: false, webhook_url: '' },
        url: { enabled: false, webhook_url: '' },
        ip: { enabled: false, webhook_url: '' },
        service: { enabled: false, webhook_url: '' },
        certificate: { enabled: false, webhook_url: '' }
      }
    },
    findings: { nuclei_severities: [], nuclei_webhook_url: '' },
    ct_alerts: { enabled: false, webhook_url: '' },
    ct_asset_alerts: { enabled: false, webhook_url: '' }
  },
};

function mergeProgramNotificationSettings(programSettings) {
  const normalizeEventVal = (v) => {
    if (v && typeof v === 'object' && 'enabled' in v) return v;
    return { enabled: Boolean(v), webhook_url: '' };
  };
  const normalizeAssetSection = (section) => {
    const out = {};
    for (const t of ['subdomain', 'url', 'ip', 'service', 'certificate']) {
      out[t] = normalizeEventVal(section?.[t]);
    }
    return out;
  };
  const psEvents = (programSettings || {}).events || {};
  return {
    ...DEFAULT_NOTIFICATION_SETTINGS,
    ...programSettings,
    events: {
      assets: {
        created: normalizeAssetSection(psEvents.assets?.created),
        updated: normalizeAssetSection(psEvents.assets?.updated),
      },
      findings: {
        nuclei_severities: Array.isArray(psEvents.findings?.nuclei_severities)
          ? psEvents.findings.nuclei_severities.filter((s) => typeof s === 'string')
          : [],
        nuclei_webhook_url: psEvents.findings?.nuclei_webhook_url || '',
      },
      ct_alerts: normalizeEventVal(psEvents.ct_alerts),
      ct_asset_alerts: normalizeEventVal(psEvents.ct_asset_alerts),
    },
  };
}

function ProgramDetail() {
  const { programName } = useParams();
  const navigate = useNavigate();
  const { hasProgramPermission, updateUser } = useAuth();
  const { selectedProgram, setSelectedProgram, refreshPrograms } = useProgramFilter();

  const [program, setProgram] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState('');
  const [programNameDraft, setProgramNameDraft] = useState('');
  const [savingProgramName, setSavingProgramName] = useState(false);
  const [savingNotifications, setSavingNotifications] = useState(false);
  const [savingAutoResolve, setSavingAutoResolve] = useState(false);
  const [typosquatAutoResolve, setTyposquatAutoResolve] = useState({
    min_parked_confidence_percent: '',
    min_similarity_percent: ''
  });
  const [savingFiltering, setSavingFiltering] = useState(false);
  const [savingCtMonitoring, setSavingCtMonitoring] = useState(false);
  const [savingCtAssetMonitoring, setSavingCtAssetMonitoring] = useState(false);
  const [ctMonitorProgram, setCtMonitorProgram] = useState({
    similarity_threshold: ''
  });
  const [savingCtMonitorProgram, setSavingCtMonitorProgram] = useState(false);
  const [typosquatFiltering, setTyposquatFiltering] = useState({
    enabled: false,
    min_similarity_percent: '',
    whitelisted_apex_domains_text: ''
  });
  // AI prompt settings
  const [aiPrompts, setAiPrompts] = useState({ typosquat: '' });
  const [aiDefaultPrompts, setAiDefaultPrompts] = useState({});
  const [savingAiPrompts, setSavingAiPrompts] = useState(false);
  // Import domains modal states
  const [showImportModal, setShowImportModal] = useState(false);
  const [importText, setImportText] = useState('');
  const [importWildcard, setImportWildcard] = useState(true);
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState('');
  const [importReplaceAll, setImportReplaceAll] = useState(false);
  // Invalid scope patterns returned by the API when importing domains. Kept
  // per-modal so the import dialog can stay open with the dropped entries in
  // view while the valid ones are already persisted server-side.
  const [importScopeWarnings, setImportScopeWarnings] = useState([]);

  // Edit modal states
  const [showEditModal, setShowEditModal] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  // Dropped scope entries ({pattern, reason}) returned by the API for the
  // current edit submission. Populated for scope_domains / out_of_scope_domains
  // only; surfaced inline in the edit modal so the user can fix bad rows.
  const [editScopeWarnings, setEditScopeWarnings] = useState([]);
  const [editType, setEditType] = useState(null); // 'domain_regex', 'out_of_scope_regex', 'cidr_list', 'safe_registrar', 'safe_ssl_issuer', 'phishlabs_api_key', or 'threatstream_credentials'
  const [editForm, setEditForm] = useState({
    newItems: '',
    scopeDomainRows: [],
    overwrite: false,
    api_user: '',
    api_key: ''
  });

  // Search states for each section
  const [searchTerms, setSearchTerms] = useState({
    domain_regex: '',
    out_of_scope_regex: '',
    cidr_list: '',
    safe_registrar: '',
    safe_ssl_issuer: '',
    protected_domains: '',
    protected_subdomain_prefixes: ''
  });

  // Search navigation states for each section
  const [searchIndices, setSearchIndices] = useState({
    domain_regex: 0,
    out_of_scope_regex: 0,
    cidr_list: 0,
    safe_registrar: 0,
    safe_ssl_issuer: 0,
    protected_domains: 0,
    protected_subdomain_prefixes: 0
  });

  // Field types that accept a single value instead of a list
  const singleValueTypes = ['phishlabs_api_key','recordedfuture_api_key'];

  // Search state for edit modal
  const [editModalSearch, setEditModalSearch] = useState('');
  const [editModalSearchIndex, setEditModalSearchIndex] = useState(0);

  // Copy to clipboard state
  const [copiedApexDomains, setCopiedApexDomains] = useState(false);

  // Tab navigation
  const [activeTab, setActiveTab] = useState('overview');

  // Copy notifications modal
  const [showCopyNotificationsModal, setShowCopyNotificationsModal] = useState(false);
  const [copySourceProgram, setCopySourceProgram] = useState('');
  const [otherPrograms, setOtherPrograms] = useState([]);
  const [copyNotificationsLoading, setCopyNotificationsLoading] = useState(false);

  // Event handler config (per-program override)
  const [eventHandlerUseGlobal, setEventHandlerUseGlobal] = useState(true);
  const [eventHandlerAddonMode, setEventHandlerAddonMode] = useState(true);
  const [eventHandlerHandlers, setEventHandlerHandlers] = useState([]);
  const [eventHandlerLoading, setEventHandlerLoading] = useState(false);
  const [eventHandlerSaving, setEventHandlerSaving] = useState(false);
  const [showEventHandlerEditModal, setShowEventHandlerEditModal] = useState(false);
  const [eventHandlerEditJson, setEventHandlerEditJson] = useState('');
  const [showEventHandlerFormModal, setShowEventHandlerFormModal] = useState(false);
  const [eventHandlerEditingIndex, setEventHandlerEditingIndex] = useState(null); // null = add new
  const [eventHandlerEditingHandler, setEventHandlerEditingHandler] = useState(null);

  const [notificationSettings, setNotificationSettings] = useState(DEFAULT_NOTIFICATION_SETTINGS);

  usePageTitle(formatPageTitle(program?.name || programName, 'Program'));

  const loadProgram = useCallback(async ({ silent = false } = {}) => {
    try {
      // When `silent` is true, skip toggling the page-level `loading` flag so
      // an open modal (e.g. the scope-domains editor) does not get unmounted
      // by the top-level `if (loading) return <Spinner/>` branch. Use this
      // after save-style actions where the user is already looking at a modal
      // and we just want to refresh `program` in place.
      if (!silent) {
        setLoading(true);
        setError(null);
      }

      const response = await programAPI.getByName(programName);
      setProgram(response);
    } catch (err) {
      console.error('Failed to load program:', err);
      setError('Failed to load program: ' + err.message);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [programName]);

  const loadEventHandlerConfig = useCallback(async () => {
    if (!programName) return;
    try {
      setEventHandlerLoading(true);
      const response = await programAPI.getEventHandlerConfig(programName);
      setEventHandlerUseGlobal(response.use_global !== false);
      setEventHandlerHandlers(coerceHandlersList(response.handlers || []));
      setEventHandlerAddonMode(response.event_handler_addon_mode === true);
    } catch (err) {
      console.error('Failed to load event handler config:', err);
      setEventHandlerUseGlobal(true);
      setEventHandlerHandlers([]);
      setEventHandlerAddonMode(false);
    } finally {
      setEventHandlerLoading(false);
    }
  }, [programName]);

  useEffect(() => {
    if (programName) {
      loadProgram();
    }
  }, [programName, loadProgram]);

  useEffect(() => {
    const settings = program?.typosquat_auto_resolve_settings || {};
    setTyposquatAutoResolve({
      min_parked_confidence_percent: settings.min_parked_confidence_percent ?? '',
      min_similarity_percent: settings.min_similarity_percent ?? ''
    });
    const filterSettings = program?.typosquat_filtering_settings || {};
    const wl = filterSettings.whitelisted_apex_domains;
    const wlText = Array.isArray(wl) && wl.length ? wl.join('\n') : '';
    setTyposquatFiltering({
      enabled: filterSettings.enabled ?? false,
      min_similarity_percent: filterSettings.min_similarity_percent ?? '',
      whitelisted_apex_domains_text: wlText
    });
    const prompts = (program?.ai_analysis_settings?.prompts) || {};
    setAiPrompts({ typosquat: prompts.typosquat || '' });
    const cms = program?.ct_monitor_program_settings || {};
    setCtMonitorProgram({
      similarity_threshold:
        cms.similarity_threshold !== undefined && cms.similarity_threshold !== null
          ? String(cms.similarity_threshold)
          : ''
    });
    if (program?.name != null) {
      setProgramNameDraft(program.name);
    }
  }, [program]);

  useEffect(() => {
    aiAPI.getDefaultPrompts()
      .then(data => setAiDefaultPrompts(data.prompts || {}))
      .catch(() => {});
  }, []);

  const loadOtherPrograms = async () => {
    try {
      const response = await programAPI.getAll();
      const programs = response.programs || response.programs_with_permissions?.map((p) => (typeof p === 'string' ? p : p?.name)) || [];
      setOtherPrograms(programs.filter((p) => p && p !== programName));
    } catch (err) {
      console.error('Failed to load programs for copy:', err);
      setOtherPrograms([]);
    }
  };

  const handleCopyNotificationsFrom = async (sourceName) => {
    if (!sourceName) return;
    try {
      setCopyNotificationsLoading(true);
      setError('');
      const sourceProgram = await programAPI.getByName(sourceName);
      const merged = mergeProgramNotificationSettings(sourceProgram?.notification_settings || {});
      setNotificationSettings(merged);
      setShowCopyNotificationsModal(false);
      setCopySourceProgram('');
      setSuccess(`Settings copied from ${sourceName}. Review and save.`);
    } catch (err) {
      console.error('Failed to copy notification settings:', err);
      setError('Failed to copy notification settings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setCopyNotificationsLoading(false);
    }
  };

  useEffect(() => {
    if (program && programName) loadEventHandlerConfig();
  }, [program, programName, loadEventHandlerConfig]);

  const handleRenameProgram = async () => {
    const trimmed = programNameDraft.trim();
    if (!trimmed || !program || trimmed === program.name) return;
    try {
      setSavingProgramName(true);
      setError('');
      await programAPI.update(programName, { name: trimmed }, true);
      const fresh = await authAPI.getCurrentUser();
      updateUser(fresh);
      if (selectedProgram === programName) {
        setSelectedProgram(trimmed);
      }
      try {
        await refreshPrograms();
      } catch (e) {
        console.warn('refreshPrograms after rename:', e);
      }
      setSuccess('Program name updated.');
      navigate(`/programs/${encodeURIComponent(trimmed)}`, { replace: true });
    } catch (err) {
      const d = err.response?.data?.detail;
      const msg =
        typeof d === 'string'
          ? d
          : Array.isArray(d)
            ? d.map((x) => (typeof x === 'string' ? x : x?.msg || '')).filter(Boolean).join(' ')
            : err.message;
      setError(msg || 'Failed to rename program');
    } finally {
      setSavingProgramName(false);
    }
  };

  useEffect(() => {
    // Sync local draft with program data when it loads/changes
    setNotificationSettings(mergeProgramNotificationSettings(program?.notification_settings || {}));
  }, [program]);

  const handleSaveTyposquatAutoResolve = async () => {
    try {
      setSavingAutoResolve(true);
      setError('');
      const minParked = typosquatAutoResolve.min_parked_confidence_percent === '' ? null : Number(typosquatAutoResolve.min_parked_confidence_percent);
      const minSim = typosquatAutoResolve.min_similarity_percent === '' ? null : Number(typosquatAutoResolve.min_similarity_percent);
      const payload = {};
      if (minParked != null) payload.min_parked_confidence_percent = minParked;
      if (minSim != null) payload.min_similarity_percent = minSim;
      await programAPI.update(programName, { typosquat_auto_resolve_settings: payload }, true);
      setSuccess('Typosquat auto-resolve settings updated');
      await loadProgram();
    } catch (err) {
      console.error('Failed to save typosquat auto-resolve settings:', err);
      setError('Failed to save: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingAutoResolve(false);
    }
  };

  const handleSaveTyposquatFiltering = async () => {
    try {
      setSavingFiltering(true);
      setError('');
      const minSim = typosquatFiltering.min_similarity_percent === '' ? null : Number(typosquatFiltering.min_similarity_percent);
      const whitelistLines = (typosquatFiltering.whitelisted_apex_domains_text || '')
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      const payload = {
        enabled: typosquatFiltering.enabled,
        whitelisted_apex_domains: whitelistLines
      };
      if (minSim != null) payload.min_similarity_percent = minSim;
      await programAPI.update(programName, { typosquat_filtering_settings: payload }, true);
      setSuccess('Typosquat filtering settings updated');
      await loadProgram();
    } catch (err) {
      console.error('Failed to save typosquat filtering settings:', err);
      setError('Failed to save: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingFiltering(false);
    }
  };

  const handleCtMonitoringToggle = async (enabled) => {
    try {
      setSavingCtMonitoring(true);
      setError('');
      await programAPI.update(programName, { ct_monitoring_enabled: enabled }, true);
      setSuccess(
        enabled
          ? 'Certificate transparency monitoring enabled for this program'
          : 'Certificate transparency monitoring disabled for this program'
      );
      await loadProgram();
    } catch (err) {
      console.error('Failed to save CT monitoring setting:', err);
      setError('Failed to save: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingCtMonitoring(false);
    }
  };

  const handleCtAssetMonitoringToggle = async (enabled) => {
    try {
      setSavingCtAssetMonitoring(true);
      setError('');
      await programAPI.update(programName, { ct_asset_monitoring_enabled: enabled }, true);
      setSuccess(
        enabled
          ? 'CT asset monitoring enabled for this program'
          : 'CT asset monitoring disabled for this program'
      );
      await loadProgram();
    } catch (err) {
      console.error('Failed to save CT asset monitoring setting:', err);
      setError('Failed to save: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingCtAssetMonitoring(false);
    }
  };

  const handleSaveCtMonitorProgram = async () => {
    try {
      setSavingCtMonitorProgram(true);
      setError('');
      const simRaw = ctMonitorProgram.similarity_threshold;
      let similarity_threshold = null;
      if (simRaw !== '') {
        const n = Number(simRaw);
        if (Number.isNaN(n) || n < 0 || n > 1) {
          setError('CT matcher similarity must be a number between 0 and 1');
          return;
        }
        similarity_threshold = n;
      }
      const settings = {
        similarity_threshold
      };
      await programAPI.update(programName, { ct_monitor_program_settings: settings }, true);
      setSuccess('CT monitor program settings updated');
      await loadProgram();
    } catch (err) {
      console.error('Failed to save CT monitor program settings:', err);
      setError('Failed to save: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingCtMonitorProgram(false);
    }
  };

  const handleSaveAiPrompts = async () => {
    try {
      setSavingAiPrompts(true);
      setError('');
      const existing = program?.ai_analysis_settings || {};
      const prompts = { ...(existing.prompts || {}) };
      if (aiPrompts.typosquat.trim()) {
        prompts.typosquat = aiPrompts.typosquat.trim();
      } else {
        delete prompts.typosquat;
      }
      await programAPI.update(programName, {
        ai_analysis_settings: { ...existing, prompts }
      }, true);
      setSuccess('AI analysis prompts updated');
      await loadProgram();
    } catch (err) {
      console.error('Failed to save AI prompts:', err);
      setError('Failed to save: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingAiPrompts(false);
    }
  };

  const handleSaveNotifications = async (nextSettings) => {
    try {
      setSavingNotifications(true);

      // Filter out removed parameters (batching and format) before saving
      const filteredSettings = { ...nextSettings };
      delete filteredSettings.batching;
      delete filteredSettings.format;

      await programAPI.updateNotificationSettings(programName, filteredSettings);
      setSuccess('Notification settings updated');
      await loadProgram();
      await loadEventHandlerConfig();
    } catch (err) {
      console.error('Failed to update notification settings:', err);
      setError('Failed to update notification settings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingNotifications(false);
    }
  };

  const handleSaveEventHandlers = async () => {
    try {
      setEventHandlerSaving(true);
      setError('');
      await programAPI.updateEventHandlerConfig(
        programName,
        sanitizeHandlersList(coerceHandlersList(eventHandlerHandlers)),
        eventHandlerAddonMode
      );
      setSuccess('Event handler config updated');
      setEventHandlerUseGlobal(false);
      await loadEventHandlerConfig();
    } catch (err) {
      setError('Failed to save event handler config: ' + (err.response?.data?.detail || err.message));
    } finally {
      setEventHandlerSaving(false);
    }
  };

  const handleRevertEventHandlers = async () => {
    if (!window.confirm('Revert to global defaults? This will remove the program override.')) return;
    try {
      setEventHandlerSaving(true);
      setError('');
      await programAPI.deleteEventHandlerConfig(programName);
      setSuccess('Reverted to global event handler config');
      setEventHandlerUseGlobal(true);
      await loadEventHandlerConfig();
    } catch (err) {
      setError('Failed to revert: ' + (err.response?.data?.detail || err.message));
    } finally {
      setEventHandlerSaving(false);
    }
  };

  const formatProgramDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  // Extract apex domain from regex pattern
  const extractApexDomain = (regexPattern) => {
    // Remove regex special characters and anchors
    let domain = regexPattern
      .replace(/\^/g, '')
      .replace(/\$/g, '')
      .replace(/\.\*/g, '')
      .replace(/\\\./g, '.')
      .replace(/\\/g, '')
      .replace(/\(\?:/g, '')
      .replace(/\)/g, '')
      .replace(/\[.*?\]/g, '')
      .trim();
    
    // Remove leading/trailing dots or wildcards
    domain = domain.replace(/^\.+/, '').replace(/\.+$/, '');
    
    // Split by dots and get the last two parts (apex domain)
    const parts = domain.split('.').filter(p => p.length > 0);
    if (parts.length >= 2) {
      // Handle common country-code TLDs (e.g., .co.uk, .com.au)
      const twoLevelTLDs = ['co', 'com', 'org', 'net', 'ac', 'gov', 'edu'];
      if (parts.length >= 3 && twoLevelTLDs.includes(parts[parts.length - 2])) {
        return parts.slice(-3).join('.');
      }
      return parts.slice(-2).join('.');
    }
    return domain;
  };

  // Get all unique apex domains from domain_regex list
  const getApexDomains = (domainRegexList) => {
    if (!domainRegexList || domainRegexList.length === 0) return [];
    
    const apexDomains = new Set();
    
    domainRegexList.forEach(pattern => {
      const apex = extractApexDomain(pattern);
      if (apex && apex.includes('.') && apex.length > 0) {
        apexDomains.add(apex);
      }
    });
    
    return Array.from(apexDomains).sort();
  };

  const twoLevelTlds = ['co', 'com', 'org', 'net', 'ac', 'gov', 'edu'];
  const apexFromStructuredPattern = (pattern) => {
    let pat = (pattern || '').trim().toLowerCase().replace(/^\.+|\.+$/g, '');
    if (!pat) return '';
    let labels = pat.split('.').filter((p) => p.length > 0);
    if (labels[0] === '*') labels = labels.slice(1);
    if (labels.length < 2) return '';
    if (labels.length >= 3 && twoLevelTlds.includes(labels[labels.length - 2])) {
      return labels.slice(-3).join('.');
    }
    return labels.slice(-2).join('.');
  };

  const getApexDomainsForProgram = (prog) => {
    const set = new Set();
    (prog.scope_domains || []).forEach((row) => {
      const a = apexFromStructuredPattern(row.pattern);
      if (a && a.includes('.')) set.add(a);
    });
    getApexDomains(prog.domain_regex || []).forEach((a) => set.add(a));
    return Array.from(set).sort();
  };

  /** Build API entries from structured scope rows (skip empty patterns; normalize like legacy line parser). */
  const scopeRowsToEntries = (rows) => {
    const out = [];
    (rows || []).forEach((row) => {
      const pattern = (row.pattern || '').trim().toLowerCase();
      if (!pattern) return;
      const wildcard = Boolean(row.wildcard) || pattern.includes('*');
      out.push({ pattern, wildcard });
    });
    return out;
  };

  const openEditModal = (type) => {
    setEditType(type);

    if (type === 'threatstream_credentials') {
      // Handle Threatstream credentials as a special case
      setEditForm({
        api_user: program.threatstream_api_user || '',
        api_key: program.threatstream_api_key || '',
        overwrite: true
      });
    } else if (type === 'scope_domains' || type === 'out_of_scope_domains') {
      const raw = Array.isArray(program[type]) ? program[type] : [];
      const scopeDomainRows = raw.map((r) => ({
        pattern: r.pattern != null ? String(r.pattern) : '',
        wildcard: Boolean(r.wildcard),
      }));
      setEditForm({
        newItems: '',
        scopeDomainRows,
        overwrite: true,
      });
    } else {
      // Handle regular fields
      const rawValue = program[type];
      const currentItems = Array.isArray(rawValue) ? rawValue : (rawValue ? [rawValue] : []);

      setEditForm({
        newItems: currentItems.join('\n'),
        overwrite: true // Default to overwrite mode for better list management
      });
    }
    setEditModalSearch(''); // Reset search in modal
    setEditModalSearchIndex(0);
    setEditScopeWarnings([]);
    setShowEditModal(true);
  };

  // Helper: sanitize and split lines into domains
  const parseDomainsFromText = (text) => {
    return text
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0);
  };

  // Helper: convert domains to regex patterns per rules
  const convertDomainsToRegex = (domains, wildcard) => {
    const escapeDots = (d) => d.replace(/\./g, '\\.');
    return domains.map((d) => {
      const escaped = escapeDots(d);
      if (wildcard) {
        // Match exact domain and any subdomain
        return `^(?:[A-Za-z0-9-]+\\.)*${escaped}$`;
      }
      // Match exact domain only
      return `^${escaped}$`;
    });
  };

  const openImportModal = () => {
    setImportText('');
    setImportWildcard(true);
    setImportError('');
    setImportReplaceAll(false);
    setImportScopeWarnings([]);
    setShowImportModal(true);
  };

  const handleImportFile = async (file) => {
    try {
      if (!file) return;
      const text = await file.text();
      // Append with newline if needed
      setImportText((prev) => (prev ? `${prev}\n${text}` : text));
    } catch (e) {
      setImportError('Failed to read file: ' + (e.message || String(e)));
    }
  };

  const handleImportSubmit = async (e) => {
    e.preventDefault();
    try {
      setImportLoading(true);
      setImportError('');

      const domains = parseDomainsFromText(importText);
      if (domains.length === 0) {
        setImportError('Please enter or upload at least one domain.');
        return;
      }

      const newEntries = domains.map((line) => {
        const lower = line.trim().toLowerCase();
        const wildcard = lower.includes('*') || importWildcard;
        return { pattern: lower, wildcard };
      });

      let payloadEntries = newEntries;
      if (!importReplaceAll) {
        const existing = Array.isArray(program.scope_domains) ? program.scope_domains : [];
        const seen = new Set(existing.map((e) => `${e.pattern}|${e.wildcard}`));
        const merged = [...existing];
        newEntries.forEach((e) => {
          const k = `${e.pattern}|${e.wildcard}`;
          if (!seen.has(k)) {
            seen.add(k);
            merged.push(e);
          }
        });
        payloadEntries = merged;
      }

      const resp = await programAPI.update(programName, { scope_domains: payloadEntries }, true);
      const dropped = resp?.scope_warnings?.ignored_in_scope || [];
      if (dropped.length > 0) {
        // Valid rows were saved; keep the modal open so the user can see which
        // entries were rejected and why. Silent reload avoids unmounting the
        // modal via the page-level loading spinner.
        setImportScopeWarnings(dropped);
        setSuccess(
          `Imported ${payloadEntries.length - dropped.length} valid domain pattern(s); ` +
          `${dropped.length} invalid entr${dropped.length === 1 ? 'y was' : 'ies were'} skipped.`
        );
        await loadProgram({ silent: true });
      } else {
        setImportScopeWarnings([]);
        setSuccess('Imported domains into structured in-scope patterns');
        setShowImportModal(false);
        await loadProgram();
      }
    } catch (err) {
      console.error('Failed to import domains:', err);
      setImportError('Failed to import domains: ' + (err.response?.data?.detail || err.message));
    } finally {
      setImportLoading(false);
    }
  };

  const handleEdit = async (e) => {
    e.preventDefault();

    try {
      setEditLoading(true);
      setError('');
      setEditScopeWarnings([]);

      let updateData = {};

      if (editType === 'threatstream_credentials') {
        // Handle Threatstream credentials specially
        updateData = {
          threatstream_api_user: editForm.api_user.trim() || null,
          threatstream_api_key: editForm.api_key.trim() || null
        };
      } else {
        const isSingleValue = singleValueTypes.includes(editType);

        if (isSingleValue) {
          // For single-value fields, use the trimmed string directly
          updateData = { [editType]: editForm.newItems.trim() };
        } else if (editType === 'scope_domains' || editType === 'out_of_scope_domains') {
          const entries = scopeRowsToEntries(editForm.scopeDomainRows);
          if (entries.length === 0 && !editForm.overwrite) {
            setError('Add at least one pattern or enable replace mode to clear the list');
            return;
          }
          updateData = { [editType]: entries };
        } else {
          // Parse the items (one per line) for list fields
          const items = editForm.newItems
            .split('\n')
            .map(item => item.trim())
            .filter(item => item.length > 0);

          // Allow empty lists only when overwrite mode is enabled
          if (items.length === 0 && !editForm.overwrite) {
            setError('Please enter at least one valid item or use overwrite mode to clear the list');
            return;
          }

          updateData = { [editType]: items };
        }
      }

      // Update the program
      const resp = await programAPI.update(
        programName,
        updateData,
        editType === 'threatstream_credentials'
          ? true
          : singleValueTypes.includes(editType)
            ? true
            : editType === 'scope_domains' || editType === 'out_of_scope_domains'
              ? true
              : editForm.overwrite
      );

      const typeLabels = {
        'scope_domains': 'In-scope domain patterns',
        'out_of_scope_domains': 'Out-of-scope domain patterns',
        'domain_regex': 'Domain regex patterns',
        'cidr_list': 'CIDR blocks',
        'safe_registrar': 'Safe registrars',
        'safe_ssl_issuer': 'Safe SSL issuers',
        'protected_domains': 'Protected domains',
        'protected_subdomain_prefixes': 'Protected keywords',
        'phishlabs_api_key': 'Phishlabs API key',
        'recordedfuture_api_key': 'RecordedFuture API key',
        'threatstream_credentials': 'Threatstream API credentials'
      };

      // Surface any scope patterns the API dropped as invalid (e.g. a user
      // typed ".*h3x.it"). Keep the modal open so the user can fix them.
      let droppedScope = [];
      if (editType === 'scope_domains') {
        droppedScope = resp?.scope_warnings?.ignored_in_scope || [];
      } else if (editType === 'out_of_scope_domains') {
        droppedScope = resp?.scope_warnings?.ignored_out_of_scope || [];
      }

      if (droppedScope.length > 0) {
        setEditScopeWarnings(droppedScope);
        const savedCount = (editForm.scopeDomainRows || []).filter((r) => (r.pattern || '').trim()).length - droppedScope.length;
        setSuccess(
          `${typeLabels[editType]}: ${savedCount >= 0 ? savedCount : 0} saved; ` +
          `${droppedScope.length} invalid entr${droppedScope.length === 1 ? 'y was' : 'ies were'} skipped.`
        );
        // Reload without flipping the page-level loading spinner so the modal
        // stays mounted while the user sees and fixes the invalid rows.
        await loadProgram({ silent: true });
      } else {
        setSuccess(`${typeLabels[editType]} updated successfully`);
        setShowEditModal(false);
        await loadProgram();
      }

    } catch (err) {
      console.error('Failed to update program:', err);
      setError('Failed to update program: ' + (err.response?.data?.detail || err.message));
    } finally {
      setEditLoading(false);
    }
  };

  // Get matching indices for search
  const getMatchingIndices = (items, searchTerm) => {
    if (!searchTerm) return [];
    return items
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => item.toLowerCase().includes(searchTerm.toLowerCase()))
      .map(({ index }) => index);
  };

  // Highlight text with search term
  const highlightText = (text, searchTerm) => {
    if (!searchTerm) return text;
    
    const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const parts = text.split(regex);
    
    return parts.map((part, index) => 
      regex.test(part) ? (
        <mark key={index} className="search-highlight">
          {part}
        </mark>
      ) : part
    );
  };

  // Navigation functions for search
  const navigateSearch = (type, direction) => {
    const items = program[type] || [];
    const matches = getMatchingIndices(items, searchTerms[type]);
    
    if (matches.length === 0) return;
    
    let newIndex = searchIndices[type];
    if (direction === 'next') {
      newIndex = (newIndex + 1) % matches.length;
    } else {
      newIndex = newIndex === 0 ? matches.length - 1 : newIndex - 1;
    }
    
    setSearchIndices({ ...searchIndices, [type]: newIndex });
    
    // Scroll to the highlighted row
    setTimeout(() => {
      const highlightedRow = document.querySelector(`[data-search-highlight="${type}-${matches[newIndex]}"]`);
      if (highlightedRow) {
        highlightedRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
  };

  // Navigation functions for edit modal
  const navigateEditModalSearch = (direction) => {
    const lines = editForm.newItems.split('\n');
    const matches = getMatchingIndices(lines, editModalSearch);
    
    if (matches.length === 0) return;
    
    let newIndex = editModalSearchIndex;
    if (direction === 'next') {
      newIndex = (newIndex + 1) % matches.length;
    } else {
      newIndex = newIndex === 0 ? matches.length - 1 : newIndex - 1;
    }
    
    setEditModalSearchIndex(newIndex);
  };

  // Handle search term changes
  const handleSearchChange = (type, value) => {
    setSearchTerms({ ...searchTerms, [type]: value });
    setSearchIndices({ ...searchIndices, [type]: 0 });
  };

  const handleEditModalSearchChange = (value) => {
    setEditModalSearch(value);
    setEditModalSearchIndex(0);
  };

  // Copy apex domains to clipboard
  const copyApexDomainsToClipboard = async () => {
    const apexDomains = getApexDomainsForProgram(program);
    const domainsText = apexDomains.join('\n');
    
    try {
      await navigator.clipboard.writeText(domainsText);
      setCopiedApexDomains(true);
      setTimeout(() => setCopiedApexDomains(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = domainsText;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        setCopiedApexDomains(true);
        setTimeout(() => setCopiedApexDomains(false), 2000);
      } catch (e) {
        console.error('Fallback copy failed:', e);
      }
      document.body.removeChild(textArea);
    }
  };

  // Theme-aware styles using CSS variables
  const getTableHeaderStyle = () => ({
    position: 'sticky',
    top: 0,
    backgroundColor: 'var(--bs-table-bg)',
    color: 'var(--bs-body-color)',
    zIndex: 1,
    borderBottom: '2px solid var(--bs-border-color)'
  });

  const getRowStyle = (isHighlighted, isCurrentMatch) => {
    if (isCurrentMatch) {
      return {
        backgroundColor: 'var(--bs-table-hover-bg)',
        color: 'var(--bs-body-color)',
        border: '2px solid var(--bs-primary)',
        boxShadow: '0 0 0 2px var(--bs-primary)'
      };
    } else if (isHighlighted) {
      return {
        backgroundColor: 'var(--bs-table-hover-bg)',
        color: 'var(--bs-body-color)'
      };
    }
    return { color: 'var(--bs-body-color)' };
  };

  const isUserManager = hasProgramPermission(programName, 'manager');

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading program...</span>
          </Spinner>
          <p className="mt-2">Loading program details...</p>
        </div>
      </Container>
    );
  }

  if (error) {
    return (
      <Container fluid className="p-4">
        <Row className="mb-3">
          <Col>
            <Alert variant="danger">
              {error}
            </Alert>
            <Button variant="secondary" onClick={() => navigate('/programs')}>
              ← Back to Programs
            </Button>
          </Col>
        </Row>
      </Container>
    );
  }

  if (!program) {
    return (
      <Container fluid className="p-4">
        <Row className="mb-3">
          <Col>
            <Alert variant="warning">
              Program not found.
            </Alert>
            <Button variant="secondary" onClick={() => navigate('/programs')}>
              ← Back to Programs
            </Button>
          </Col>
        </Row>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-center">
            <div>
              <h1>📁 {program.name}</h1>
              <p className="text-muted">
                Program details and scope configuration
                {isUserManager && (
                  <Badge bg="success" className="ms-2">Manager Access</Badge>
                )}
              </p>
            </div>
            <Button variant="secondary" onClick={() => navigate('/programs')}>
              ← Back to Programs
            </Button>
          </div>
        </Col>
      </Row>

      {error && (
        <Row className="mb-3">
          <Col>
            <Alert variant="danger" onClose={() => setError('')} dismissible>
              {error}
            </Alert>
          </Col>
        </Row>
      )}

      {success && (
        <Row className="mb-3">
          <Col>
            <Alert variant="success" onClose={() => setSuccess('')} dismissible>
              {success}
            </Alert>
          </Col>
        </Row>
      )}

      <Row>
        <Col md={8}>
          <Tabs activeKey={activeTab} onSelect={(k) => setActiveTab(k)} className="mb-3">
            <Tab eventKey="overview" title="Overview">
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <h5 className="mb-0">Program Information</h5>
            </Card.Header>
            <Card.Body>
              <Table borderless>
                <tbody>
                  <tr>
                    <td width="200"><strong>Program Name:</strong></td>
                    <td>
                      {isUserManager ? (
                        <InputGroup className="flex-nowrap" style={{ maxWidth: 'min(100%, 32rem)' }}>
                          <Form.Control
                            type="text"
                            value={programNameDraft}
                            onChange={(e) => setProgramNameDraft(e.target.value)}
                            disabled={savingProgramName}
                            maxLength={255}
                            aria-label="Program name"
                          />
                          <Button
                            variant="primary"
                            disabled={
                              savingProgramName ||
                              !programNameDraft.trim() ||
                              programNameDraft.trim() === program.name
                            }
                            onClick={handleRenameProgram}
                          >
                            {savingProgramName ? 'Saving…' : 'Save'}
                          </Button>
                        </InputGroup>
                      ) : (
                        program.name
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td>{formatProgramDate(program.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Last Updated:</strong></td>
                    <td>{formatProgramDate(program.updated_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Program ID:</strong></td>
                    <td><code>{program.id}</code></td>
                  </tr>
                </tbody>
              </Table>
            </Card.Body>
          </Card>

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  🌐 Apex Domains
                  {getApexDomainsForProgram(program).length > 0 && (
                    <Badge bg="primary" className="ms-2">
                      {getApexDomainsForProgram(program).length} domain{getApexDomainsForProgram(program).length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </h5>
                {getApexDomainsForProgram(program).length > 0 && (
                  <Button
                    variant={copiedApexDomains ? "success" : "outline-primary"}
                    size="sm"
                    onClick={copyApexDomainsToClipboard}
                  >
                    {copiedApexDomains ? '✓ Copied!' : '📋 Copy List'}
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {getApexDomainsForProgram(program).length > 0 ? (
                <div>
                  <p className="text-muted mb-3">
                    Apex domains derived from structured scope patterns and any legacy regex entries.
                  </p>
                  <div className="d-flex flex-wrap gap-2">
                    {getApexDomainsForProgram(program).map((domain, index) => (
                      <Badge 
                        key={index} 
                        bg="primary" 
                        className="px-3 py-2"
                        style={{ fontSize: '0.9em' }}
                      >
                        {domain}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No apex domains found. Add domain regex patterns to see apex domains here.</p>
                </div>
              )}
            </Card.Body>
          </Card>
            </Tab>
            <Tab eventKey="scope" title="Scope">
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <h5 className="mb-0">CT asset discovery</h5>
            </Card.Header>
            <Card.Body>
              <Form.Check
                type="switch"
                id="ct-asset-monitoring-enabled"
                label="Discover in-scope subdomains from certificate transparency logs"
                checked={!!program.ct_asset_monitoring_enabled}
                disabled={!isUserManager || savingCtAssetMonitoring}
                onChange={(e) => handleCtAssetMonitoringToggle(e.target.checked)}
              />
              <p className="text-muted small mb-0 mt-2">
                Matches certificate hostnames from CT logs against the scope patterns below and adds them as subdomain assets, whether or not they resolve to an IP. Toggling updates live config within seconds.
              </p>
            </Card.Body>
          </Card>

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  In-scope domain patterns
                  {(program.scope_domains || []).length > 0 && (
                    <Badge bg="info" className="ms-2">
                      {(program.scope_domains || []).length} entr{(program.scope_domains || []).length !== 1 ? 'ies' : 'y'}
                    </Badge>
                  )}
                </h5>
                {isUserManager && (
                  <div className="d-flex gap-2">
                    <Button
                      variant="outline-primary"
                      size="sm"
                      onClick={() => openEditModal('scope_domains')}
                    >
                      ✏️ Edit
                    </Button>
                    <Button
                      variant="outline-success"
                      size="sm"
                      onClick={openImportModal}
                    >
                      ⬆️ Import Domains
                    </Button>
                  </div>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {(program.scope_domains || []).length > 0 ? (
                <div>
                  <p className="text-muted mb-2">
                    Hostname patterns (use * as a full label, e.g. *.example.com or api.*.example.com). Use Edit to add rows with a pattern and wildcard switch.
                  </p>
                  <p className="text-muted mb-3 small">
                    Syntax quick guide: `domain.com` + Wildcard=Yes matches apex + subdomains, while `*.domain.com` matches subdomains only (not apex).
                  </p>
                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <Table striped bordered size="sm">
                      <thead>
                        <tr>
                          <th width="60" style={getTableHeaderStyle()}>#</th>
                          <th style={getTableHeaderStyle()}>Pattern</th>
                          <th width="100" style={getTableHeaderStyle()}>Wildcard</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(program.scope_domains || []).map((row, index) => (
                          <tr key={index}>
                            <td>{index + 1}</td>
                            <td><code>{row.pattern}</code></td>
                            <td>{row.wildcard ? 'Yes' : 'No'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No structured in-scope patterns yet. Use Edit or Import, or rely on legacy regex below.</p>
                </div>
              )}
            </Card.Body>
          </Card>

          {program.domain_regex && program.domain_regex.length > 0 && (
            <Card className="rh-elevated-card mb-4">
              <Card.Header className="rh-card-header-table">
                <div className="d-flex justify-content-between align-items-center">
                  <h5 className="mb-0">
                    Legacy in-scope regex
                    <Badge bg="secondary" className="ms-2">{program.domain_regex.length}</Badge>
                  </h5>
                  {isUserManager && (
                    <Button variant="outline-primary" size="sm" onClick={() => openEditModal('domain_regex')}>
                      ✏️ Edit legacy regex
                    </Button>
                  )}
                </div>
              </Card.Header>
              <Card.Body>
                <p className="text-muted small mb-2">Optional advanced regex lines; matching uses structured patterns first, then these.</p>
                <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                  <Table striped bordered size="sm">
                    <tbody>
                      {program.domain_regex.map((pattern, index) => (
                        <tr key={index}>
                          <td><code>{pattern}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </Card.Body>
            </Card>
          )}

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Out-of-scope domain patterns
                  {(program.out_of_scope_domains || []).length > 0 && (
                    <Badge bg="danger" className="ms-2">
                      {(program.out_of_scope_domains || []).length} exclusion{(program.out_of_scope_domains || []).length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={() => openEditModal('out_of_scope_domains')}
                  >
                    ✏️ Edit
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {(program.out_of_scope_domains || []).length > 0 ? (
                <div>
                  <p className="text-muted mb-2">
                    Exclusions use the same pattern format as in-scope. Out-of-scope wins over in-scope.
                  </p>
                  <p className="text-muted mb-3 small">
                    Syntax quick guide: `domain.com` + Wildcard=Yes matches apex + subdomains, while `*.domain.com` matches subdomains only (not apex).
                  </p>
                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <Table striped bordered size="sm">
                      <thead>
                        <tr>
                          <th width="60" style={getTableHeaderStyle()}>#</th>
                          <th style={getTableHeaderStyle()}>Pattern</th>
                          <th width="100" style={getTableHeaderStyle()}>Wildcard</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(program.out_of_scope_domains || []).map((row, index) => (
                          <tr key={index}>
                            <td>{index + 1}</td>
                            <td><code>{row.pattern}</code></td>
                            <td>{row.wildcard ? 'Yes' : 'No'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No structured out-of-scope patterns. Use Edit, or legacy regex below.</p>
                </div>
              )}
            </Card.Body>
          </Card>

          {program.out_of_scope_regex && program.out_of_scope_regex.length > 0 && (
            <Card className="rh-elevated-card mb-4">
              <Card.Header className="rh-card-header-table">
                <div className="d-flex justify-content-between align-items-center">
                  <h5 className="mb-0">
                    Legacy out-of-scope regex
                    <Badge bg="secondary" className="ms-2">{program.out_of_scope_regex.length}</Badge>
                  </h5>
                  {isUserManager && (
                    <Button variant="outline-primary" size="sm" onClick={() => openEditModal('out_of_scope_regex')}>
                      ✏️ Edit legacy regex
                    </Button>
                  )}
                </div>
              </Card.Header>
              <Card.Body>
                <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                  <Table striped bordered size="sm">
                    <tbody>
                      {program.out_of_scope_regex.map((pattern, index) => (
                        <tr key={index}>
                          <td><code>{pattern}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </Card.Body>
            </Card>
          )}

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  CIDR Blocks 
                  {program.cidr_list && program.cidr_list.length > 0 && (
                    <Badge bg="secondary" className="ms-2">
                      {program.cidr_list.length} CIDR{program.cidr_list.length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button 
                    variant="outline-primary" 
                    size="sm"
                    onClick={() => openEditModal('cidr_list')}
                  >
                    ✏️ Edit CIDR Blocks
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {program.cidr_list && program.cidr_list.length > 0 ? (
                <div>
                  <p className="text-muted mb-3">
                    These CIDR blocks define the IP address ranges for this program.
                  </p>
                  
                  {/* Search Box */}
                  <InputGroup className="mb-3">
                    <InputGroup.Text style={{ 
                      backgroundColor: 'var(--bs-input-bg)',
                      color: 'var(--bs-input-color)',
                      borderColor: 'var(--bs-border-color)'
                    }}>
                      🔍
                    </InputGroup.Text>
                    <Form.Control
                      type="text"
                      placeholder="Search CIDR blocks..."
                      value={searchTerms.cidr_list}
                      onChange={(e) => handleSearchChange('cidr_list', e.target.value)}
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)'
                      }}
                    />
                    {searchTerms.cidr_list && (
                      <>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('cidr_list', 'prev')}
                          disabled={getMatchingIndices(program.cidr_list, searchTerms.cidr_list).length === 0}
                        >
                          ↑
                        </Button>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('cidr_list', 'next')}
                          disabled={getMatchingIndices(program.cidr_list, searchTerms.cidr_list).length === 0}
                        >
                          ↓
                        </Button>
                        <Button 
                          variant="outline-secondary" 
                          onClick={() => handleSearchChange('cidr_list', '')}
                        >
                          Clear
                        </Button>
                      </>
                    )}
                  </InputGroup>

                  {/* Search Results Info */}
                  {searchTerms.cidr_list && (
                    <div className="mb-2">
                      <small className="text-muted">
                        {getMatchingIndices(program.cidr_list, searchTerms.cidr_list).length} match{getMatchingIndices(program.cidr_list, searchTerms.cidr_list).length !== 1 ? 'es' : ''}
                        {getMatchingIndices(program.cidr_list, searchTerms.cidr_list).length > 0 && (
                          <span> • Showing {searchIndices.cidr_list + 1} of {getMatchingIndices(program.cidr_list, searchTerms.cidr_list).length}</span>
                        )}
                      </small>
                    </div>
                  )}

                  {/* Scrollable Table */}
                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <Table striped bordered size="sm">
                      <thead>
                        <tr>
                          <th width="60" style={getTableHeaderStyle()}>#</th>
                          <th style={getTableHeaderStyle()}>CIDR Block</th>
                          <th style={getTableHeaderStyle()}>Network Range</th>
                        </tr>
                      </thead>
                      <tbody>
                        {program.cidr_list.map((cidr, index) => {
                          // Basic CIDR parsing for display
                          const [, prefix] = cidr.split('/');
                          const prefixNum = parseInt(prefix, 10);
                          const totalHosts = Math.pow(2, 32 - prefixNum);
                          
                          const matches = getMatchingIndices(program.cidr_list, searchTerms.cidr_list);
                          const isHighlighted = matches.includes(index) && searchTerms.cidr_list;
                          const isCurrentMatch = matches[searchIndices.cidr_list] === index && searchTerms.cidr_list;
                          
                          return (
                            <tr 
                              key={index}
                              data-search-highlight={`cidr_list-${index}`}
                              className={
                                isCurrentMatch
                                  ? 'search-current-match'
                                  : isHighlighted
                                  ? 'search-highlight-row'
                                  : ''
                              }
                              style={getRowStyle(isHighlighted, isCurrentMatch)}
                            >
                              <td>{index + 1}</td>
                              <td><code>{highlightText(cidr, searchTerms.cidr_list)}</code></td>
                              <td className="text-muted">
                                {totalHosts.toLocaleString()} addresses
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No CIDR blocks configured for this program.</p>
                </div>
              )}
            </Card.Body>
          </Card>
            </Tab>
            <Tab eventKey="typosquat" title="Typosquat">
            <Card className="rh-elevated-card mb-4">
              <Card.Header className="rh-card-header-table">
                <h5 className="mb-0">Certificate transparency monitoring</h5>
              </Card.Header>
              <Card.Body>
                <Form.Check
                  type="switch"
                  id="ct-monitoring-enabled"
                  label="Monitor public CT logs for certificates related to this program"
                  checked={!!program.ct_monitoring_enabled}
                  disabled={!isUserManager || savingCtMonitoring}
                  onChange={(e) => handleCtMonitoringToggle(e.target.checked)}
                />
                <p className="text-muted small mb-0 mt-2">
                  The CT monitor service stays up for config reloads; it only pulls from CT log providers while at least one program has CT monitoring enabled. Toggling updates live config within seconds.
                </p>
              </Card.Body>
            </Card>
            <Card className="rh-elevated-card mb-4">
              <Card.Header className="rh-card-header-table d-flex justify-content-between align-items-center flex-wrap gap-2">
                <h5 className="mb-0">CT monitor (this program)</h5>
                {isUserManager && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSaveCtMonitorProgram}
                    disabled={savingCtMonitorProgram}
                  >
                    {savingCtMonitorProgram ? 'Saving…' : 'Save'}
                  </Button>
                )}
              </Card.Header>
              <Card.Body>
                <p className="text-muted small">
                  These settings control how the CT monitor matches certificates for <strong>this program only</strong>.
                  They are separate from &quot;Typosquat filtering&quot; below (which applies when inserting typosquat findings into the database).
                </p>
                <p className="text-muted small mb-3">
                  The CT monitor matches certificates from <strong>all TLDs</strong> in the certificate stream
                  against this program&apos;s variations and keywords.
                </p>
                <Form.Group className="mb-0">
                  <Form.Label>CT matcher similarity threshold (0–1)</Form.Label>
                  <Form.Control
                    type="text"
                    inputMode="decimal"
                    placeholder="e.g. 0.75"
                    value={ctMonitorProgram.similarity_threshold}
                    onChange={(e) =>
                      setCtMonitorProgram({ ...ctMonitorProgram, similarity_threshold: e.target.value })
                    }
                    disabled={!isUserManager}
                  />
                  <Form.Text className="text-muted">
                    Minimum Levenshtein-style similarity for fallback domain matching. Leave empty for default (0.75).
                  </Form.Text>
                </Form.Group>
              </Card.Body>
            </Card>
<Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  🛡️ Protected Domains
                  {program.protected_domains && program.protected_domains.length > 0 && (
                    <Badge bg="success" className="ms-2">
                      {program.protected_domains.length} domain{program.protected_domains.length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button 
                    variant="outline-primary" 
                    size="sm"
                    onClick={() => openEditModal('protected_domains')}
                  >
                    ✏️ Edit Protected Domains
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {program.protected_domains && program.protected_domains.length > 0 ? (
                <div>
                  <p className="text-muted mb-3">
                    These apex domains are monitored for typosquatting and certificate transparency alerts.
                  </p>
                  
                  {/* Search Box */}
                  <InputGroup className="mb-3">
                    <InputGroup.Text style={{ 
                      backgroundColor: 'var(--bs-input-bg)',
                      color: 'var(--bs-input-color)',
                      borderColor: 'var(--bs-border-color)'
                    }}>
                      🔍
                    </InputGroup.Text>
                    <Form.Control
                      type="text"
                      placeholder="Search protected domains..."
                      value={searchTerms.protected_domains}
                      onChange={(e) => handleSearchChange('protected_domains', e.target.value)}
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)'
                      }}
                    />
                    {searchTerms.protected_domains && (
                      <>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('protected_domains', 'prev')}
                          disabled={getMatchingIndices(program.protected_domains, searchTerms.protected_domains).length === 0}
                        >
                          ↑
                        </Button>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('protected_domains', 'next')}
                          disabled={getMatchingIndices(program.protected_domains, searchTerms.protected_domains).length === 0}
                        >
                          ↓
                        </Button>
                        <Button 
                          variant="outline-secondary" 
                          onClick={() => handleSearchChange('protected_domains', '')}
                        >
                          Clear
                        </Button>
                      </>
                    )}
                  </InputGroup>

                  {/* Search Results Info */}
                  {searchTerms.protected_domains && (
                    <div className="mb-2">
                      <small className="text-muted">
                        {getMatchingIndices(program.protected_domains, searchTerms.protected_domains).length} match{getMatchingIndices(program.protected_domains, searchTerms.protected_domains).length !== 1 ? 'es' : ''}
                        {getMatchingIndices(program.protected_domains, searchTerms.protected_domains).length > 0 && (
                          <span> • Showing {searchIndices.protected_domains + 1} of {getMatchingIndices(program.protected_domains, searchTerms.protected_domains).length}</span>
                        )}
                      </small>
                    </div>
                  )}

                  {/* Scrollable Table */}
                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <Table striped bordered size="sm">
                      <thead>
                        <tr>
                          <th width="60" style={getTableHeaderStyle()}>#</th>
                          <th style={getTableHeaderStyle()}>Protected Domain</th>
                        </tr>
                      </thead>
                      <tbody>
                        {program.protected_domains.map((domain, index) => {
                          const matches = getMatchingIndices(program.protected_domains, searchTerms.protected_domains);
                          const isHighlighted = matches.includes(index) && searchTerms.protected_domains;
                          const isCurrentMatch = matches[searchIndices.protected_domains] === index && searchTerms.protected_domains;
                          
                          return (
                            <tr 
                              key={index}
                              data-search-highlight={`protected_domains-${index}`}
                              className={
                                isCurrentMatch
                                  ? 'search-current-match'
                                  : isHighlighted
                                  ? 'search-highlight-row'
                                  : ''
                              }
                              style={getRowStyle(isHighlighted, isCurrentMatch)}
                            >
                              <td>{index + 1}</td>
                              <td><code>{highlightText(domain, searchTerms.protected_domains)}</code></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No protected domains configured for this program.</p>
                  <p className="text-muted small">Add apex domains here to enable typosquatting monitoring and CT alerts.</p>
                </div>
              )}
            </Card.Body>
          </Card>

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Protected Keywords
                  {program.protected_subdomain_prefixes && program.protected_subdomain_prefixes.length > 0 && (
                    <Badge bg="success" className="ms-2">
                      {program.protected_subdomain_prefixes.length} keyword{program.protected_subdomain_prefixes.length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button 
                    variant="outline-primary" 
                    size="sm"
                    onClick={() => openEditModal('protected_subdomain_prefixes')}
                  >
                    Edit Keywords
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {program.protected_subdomain_prefixes && program.protected_subdomain_prefixes.length > 0 ? (
                <div>
                  <p className="text-muted mb-3">
                    Typosquat domains containing any of these keywords are automatically included regardless of similarity score.
                  </p>
                  
                  <InputGroup className="mb-2">
                    <InputGroup.Text style={{ backgroundColor: 'var(--bs-input-bg)', borderColor: 'var(--bs-border-color)' }}>
                      Search
                    </InputGroup.Text>
                    <Form.Control
                      type="text"
                      placeholder="Search keywords..."
                      value={searchTerms.protected_subdomain_prefixes}
                      onChange={(e) => handleSearchChange('protected_subdomain_prefixes', e.target.value)}
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)'
                      }}
                    />
                    {searchTerms.protected_subdomain_prefixes && (
                      <>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('protected_subdomain_prefixes', 'prev')}
                          disabled={getMatchingIndices(program.protected_subdomain_prefixes, searchTerms.protected_subdomain_prefixes).length === 0}
                        >
                          Up
                        </Button>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('protected_subdomain_prefixes', 'next')}
                          disabled={getMatchingIndices(program.protected_subdomain_prefixes, searchTerms.protected_subdomain_prefixes).length === 0}
                        >
                          Down
                        </Button>
                        <Button 
                          variant="outline-secondary" 
                          onClick={() => handleSearchChange('protected_subdomain_prefixes', '')}
                        >
                          Clear
                        </Button>
                      </>
                    )}
                  </InputGroup>

                  {searchTerms.protected_subdomain_prefixes && (
                    <div className="mb-2">
                      <small className="text-muted">
                        {getMatchingIndices(program.protected_subdomain_prefixes, searchTerms.protected_subdomain_prefixes).length} match{getMatchingIndices(program.protected_subdomain_prefixes, searchTerms.protected_subdomain_prefixes).length !== 1 ? 'es' : ''}
                        {getMatchingIndices(program.protected_subdomain_prefixes, searchTerms.protected_subdomain_prefixes).length > 0 && (
                          <span> - Showing {searchIndices.protected_subdomain_prefixes + 1} of {getMatchingIndices(program.protected_subdomain_prefixes, searchTerms.protected_subdomain_prefixes).length}</span>
                        )}
                      </small>
                    </div>
                  )}

                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <Table striped bordered hover size="sm">
                      <thead>
                        <tr>
                          <th width="60" style={getTableHeaderStyle()}>#</th>
                          <th style={getTableHeaderStyle()}>Keyword</th>
                        </tr>
                      </thead>
                      <tbody>
                        {program.protected_subdomain_prefixes.map((prefix, index) => {
                          const matches = getMatchingIndices(program.protected_subdomain_prefixes, searchTerms.protected_subdomain_prefixes);
                          const isHighlighted = matches.includes(index) && searchTerms.protected_subdomain_prefixes;
                          const isCurrentMatch = matches[searchIndices.protected_subdomain_prefixes] === index && searchTerms.protected_subdomain_prefixes;
                          
                          return (
                            <tr 
                              key={index}
                              data-search-highlight={`protected_subdomain_prefixes-${index}`}
                              className={
                                isCurrentMatch
                                  ? 'search-current-match'
                                  : isHighlighted
                                  ? 'search-highlight-row'
                                  : ''
                              }
                              style={getRowStyle(isHighlighted, isCurrentMatch)}
                            >
                              <td>{index + 1}</td>
                              <td><code>{highlightText(prefix, searchTerms.protected_subdomain_prefixes)}</code></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No protected keywords configured for this program.</p>
                  <p className="text-muted small">Add keywords to automatically include typosquat domains that contain them anywhere in the domain name (e.g. myorganization, mycompany).</p>
                </div>
              )}
            </Card.Body>
          </Card>
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">Typosquat Filtering Settings</h5>
                {isUserManager && (
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={handleSaveTyposquatFiltering}
                    disabled={savingFiltering}
                  >
                    {savingFiltering ? 'Saving...' : 'Save'}
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              <p className="text-muted mb-3">
                When enabled, new typosquat domains must meet the minimum similarity threshold with a protected domain OR contain a protected keyword to be inserted.
                Domains under a whitelisted apex are always discarded.
                Domains that don&apos;t pass are discarded (RecordedFuture alerts are auto-resolved).
              </p>
              <Row>
                <Col md={4}>
                  <Form.Group className="mb-3">
                    <Form.Check
                      type="switch"
                      id="filtering-enabled"
                      label="Enable filtering"
                      checked={typosquatFiltering.enabled}
                      onChange={(e) => setTyposquatFiltering({ ...typosquatFiltering, enabled: e.target.checked })}
                      disabled={!isUserManager}
                    />
                  </Form.Group>
                </Col>
                <Col md={4}>
                  <Form.Group className="mb-3">
                    <Form.Label>Min similarity (%)</Form.Label>
                    <Form.Control
                      type="number"
                      min={0}
                      max={100}
                      step={0.1}
                      placeholder="e.g. 60"
                      value={typosquatFiltering.min_similarity_percent}
                      onChange={(e) => setTyposquatFiltering({ ...typosquatFiltering, min_similarity_percent: e.target.value })}
                      disabled={!isUserManager}
                    />
                    <Form.Text className="text-muted">
                      Minimum Levenshtein similarity with any protected domain (0-100).
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>
              <Form.Group className="mb-0">
                <Form.Label>Whitelisted apex domains</Form.Label>
                <Form.Control
                  as="textarea"
                  rows={4}
                  placeholder={'One registrable apex per line, e.g.\npartner.com\naffiliate-brand.org'}
                  value={typosquatFiltering.whitelisted_apex_domains_text}
                  onChange={(e) =>
                    setTyposquatFiltering({
                      ...typosquatFiltering,
                      whitelisted_apex_domains_text: e.target.value
                    })
                  }
                  disabled={!isUserManager}
                />
                <Form.Text className="text-muted">
                  When filtering is enabled, new typosquat candidates whose registrable apex matches a line here are discarded (including all subdomains under that apex).
                  When you save newly added apex lines, existing open findings on those apexes are auto-dismissed with an explanatory note.
                </Form.Text>
              </Form.Group>
            </Card.Body>
          </Card>

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">Typosquat Auto-Resolve</h5>
                {isUserManager && (
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={handleSaveTyposquatAutoResolve}
                    disabled={savingAutoResolve}
                  >
                    {savingAutoResolve ? 'Saving...' : 'Save'}
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              <p className="text-muted mb-3">
                When both thresholds are met, a typosquat finding is flagged as &quot;Would auto-resolve&quot; (auto-resolve is not yet active).
              </p>
              <Row>
                <Col md={6}>
                  <Form.Group className="mb-3">
                    <Form.Label>Min parked confidence (%)</Form.Label>
                    <Form.Control
                      type="number"
                      min={0}
                      max={100}
                      placeholder="e.g. 80"
                      value={typosquatAutoResolve.min_parked_confidence_percent}
                      onChange={(e) => setTyposquatAutoResolve({ ...typosquatAutoResolve, min_parked_confidence_percent: e.target.value })}
                      disabled={!isUserManager}
                    />
                  </Form.Group>
                </Col>
                <Col md={6}>
                  <Form.Group className="mb-3">
                    <Form.Label>Min similarity with protected domain (%)</Form.Label>
                    <Form.Control
                      type="number"
                      min={0}
                      max={100}
                      step={0.1}
                      placeholder="e.g. 85"
                      value={typosquatAutoResolve.min_similarity_percent}
                      onChange={(e) => setTyposquatAutoResolve({ ...typosquatAutoResolve, min_similarity_percent: e.target.value })}
                      disabled={!isUserManager}
                    />
                  </Form.Group>
                </Col>
              </Row>
            </Card.Body>
          </Card>

<Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Safe Registrars 
                  {program.safe_registrar && program.safe_registrar.length > 0 && (
                    <Badge bg="success" className="ms-2">
                      {program.safe_registrar.length} registrar{program.safe_registrar.length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button 
                    variant="outline-primary" 
                    size="sm"
                    onClick={() => openEditModal('safe_registrar')}
                  >
                    ✏️ Edit Registrars
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {program.safe_registrar && program.safe_registrar.length > 0 ? (
                <div>
                  <p className="text-muted mb-3">
                    These registrars are considered safe/legitimate for this program.
                  </p>
                  
                  {/* Search Box */}
                  <InputGroup className="mb-3">
                    <InputGroup.Text style={{ 
                      backgroundColor: 'var(--bs-input-bg)',
                      color: 'var(--bs-input-color)',
                      borderColor: 'var(--bs-border-color)'
                    }}>
                      🔍
                    </InputGroup.Text>
                    <Form.Control
                      type="text"
                      placeholder="Search registrars..."
                      value={searchTerms.safe_registrar}
                      onChange={(e) => handleSearchChange('safe_registrar', e.target.value)}
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)'
                      }}
                    />
                    {searchTerms.safe_registrar && (
                      <>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('safe_registrar', 'prev')}
                          disabled={getMatchingIndices(program.safe_registrar, searchTerms.safe_registrar).length === 0}
                        >
                          ↑
                        </Button>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('safe_registrar', 'next')}
                          disabled={getMatchingIndices(program.safe_registrar, searchTerms.safe_registrar).length === 0}
                        >
                          ↓
                        </Button>
                        <Button 
                          variant="outline-secondary" 
                          onClick={() => handleSearchChange('safe_registrar', '')}
                        >
                          Clear
                        </Button>
                      </>
                    )}
                  </InputGroup>

                  {/* Search Results Info */}
                  {searchTerms.safe_registrar && (
                    <div className="mb-2">
                      <small className="text-muted">
                        {getMatchingIndices(program.safe_registrar, searchTerms.safe_registrar).length} match{getMatchingIndices(program.safe_registrar, searchTerms.safe_registrar).length !== 1 ? 'es' : ''}
                        {getMatchingIndices(program.safe_registrar, searchTerms.safe_registrar).length > 0 && (
                          <span> • Showing {searchIndices.safe_registrar + 1} of {getMatchingIndices(program.safe_registrar, searchTerms.safe_registrar).length}</span>
                        )}
                      </small>
                    </div>
                  )}

                  {/* Scrollable Table */}
                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <Table striped bordered size="sm">
                      <thead>
                        <tr>
                          <th width="60" style={getTableHeaderStyle()}>#</th>
                          <th style={getTableHeaderStyle()}>Registrar Name</th>
                        </tr>
                      </thead>
                      <tbody>
                        {program.safe_registrar.map((registrar, index) => {
                          const matches = getMatchingIndices(program.safe_registrar, searchTerms.safe_registrar);
                          const isHighlighted = matches.includes(index) && searchTerms.safe_registrar;
                          const isCurrentMatch = matches[searchIndices.safe_registrar] === index && searchTerms.safe_registrar;
                          
                          return (
                            <tr 
                              key={index}
                              data-search-highlight={`safe_registrar-${index}`}
                              className={
                                isCurrentMatch
                                  ? 'search-current-match'
                                  : isHighlighted
                                  ? 'search-highlight-row'
                                  : ''
                              }
                              style={getRowStyle(isHighlighted, isCurrentMatch)}
                            >
                              <td>{index + 1}</td>
                              <td><code>{highlightText(registrar, searchTerms.safe_registrar)}</code></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No safe registrars configured for this program.</p>
                </div>
              )}
            </Card.Body>
          </Card>

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Safe SSL Issuers 
                  {program.safe_ssl_issuer && program.safe_ssl_issuer.length > 0 && (
                    <Badge bg="warning" className="ms-2">
                      {program.safe_ssl_issuer.length} issuer{program.safe_ssl_issuer.length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button 
                    variant="outline-primary" 
                    size="sm"
                    onClick={() => openEditModal('safe_ssl_issuer')}
                  >
                    ✏️ Edit SSL Issuers
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {program.safe_ssl_issuer && program.safe_ssl_issuer.length > 0 ? (
                <div>
                  <p className="text-muted mb-3">
                    These SSL certificate issuers are considered safe/legitimate for this program.
                  </p>
                  
                  {/* Search Box */}
                  <InputGroup className="mb-3">
                    <InputGroup.Text style={{ 
                      backgroundColor: 'var(--bs-input-bg)',
                      color: 'var(--bs-input-color)',
                      borderColor: 'var(--bs-border-color)'
                    }}>
                      🔍
                    </InputGroup.Text>
                    <Form.Control
                      type="text"
                      placeholder="Search SSL issuers..."
                      value={searchTerms.safe_ssl_issuer}
                      onChange={(e) => handleSearchChange('safe_ssl_issuer', e.target.value)}
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)'
                      }}
                    />
                    {searchTerms.safe_ssl_issuer && (
                      <>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('safe_ssl_issuer', 'prev')}
                          disabled={getMatchingIndices(program.safe_ssl_issuer, searchTerms.safe_ssl_issuer).length === 0}
                        >
                          ↑
                        </Button>
                        <Button 
                          variant="outline-secondary"
                          onClick={() => navigateSearch('safe_ssl_issuer', 'next')}
                          disabled={getMatchingIndices(program.safe_ssl_issuer, searchTerms.safe_ssl_issuer).length === 0}
                        >
                          ↓
                        </Button>
                        <Button 
                          variant="outline-secondary" 
                          onClick={() => handleSearchChange('safe_ssl_issuer', '')}
                        >
                          Clear
                        </Button>
                      </>
                    )}
                  </InputGroup>

                  {/* Search Results Info */}
                  {searchTerms.safe_ssl_issuer && (
                    <div className="mb-2">
                      <small className="text-muted">
                        {getMatchingIndices(program.safe_ssl_issuer, searchTerms.safe_ssl_issuer).length} match{getMatchingIndices(program.safe_ssl_issuer, searchTerms.safe_ssl_issuer).length !== 1 ? 'es' : ''}
                        {getMatchingIndices(program.safe_ssl_issuer, searchTerms.safe_ssl_issuer).length > 0 && (
                          <span> • Showing {searchIndices.safe_ssl_issuer + 1} of {getMatchingIndices(program.safe_ssl_issuer, searchTerms.safe_ssl_issuer).length}</span>
                        )}
                      </small>
                    </div>
                  )}

                  {/* Scrollable Table */}
                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <Table striped bordered size="sm">
                      <thead>
                        <tr>
                          <th width="60" style={getTableHeaderStyle()}>#</th>
                          <th style={getTableHeaderStyle()}>SSL Issuer Name</th>
                        </tr>
                      </thead>
                      <tbody>
                        {program.safe_ssl_issuer.map((issuer, index) => {
                          const matches = getMatchingIndices(program.safe_ssl_issuer, searchTerms.safe_ssl_issuer);
                          const isHighlighted = matches.includes(index) && searchTerms.safe_ssl_issuer;
                          const isCurrentMatch = matches[searchIndices.safe_ssl_issuer] === index && searchTerms.safe_ssl_issuer;
                          
                          return (
                            <tr 
                              key={index}
                              data-search-highlight={`safe_ssl_issuer-${index}`}
                              className={
                                isCurrentMatch
                                  ? 'search-current-match'
                                  : isHighlighted
                                  ? 'search-highlight-row'
                                  : ''
                              }
                              style={getRowStyle(isHighlighted, isCurrentMatch)}
                            >
                              <td>{index + 1}</td>
                              <td><code>{highlightText(issuer, searchTerms.safe_ssl_issuer)}</code></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No safe SSL issuers configured for this program.</p>
                </div>
              )}
            </Card.Body>
          </Card>
            </Tab>
            <Tab eventKey="ai" title="AI">
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">AI Analysis Prompts</h5>
                {isUserManager && (
                  <div className="d-flex gap-2">
                    {aiPrompts.typosquat && (
                      <Button
                        variant="outline-secondary"
                        size="sm"
                        onClick={() => setAiPrompts({ ...aiPrompts, typosquat: '' })}
                        disabled={savingAiPrompts}
                      >
                        Reset to Default
                      </Button>
                    )}
                    <Button
                      variant="outline-primary"
                      size="sm"
                      onClick={handleSaveAiPrompts}
                      disabled={savingAiPrompts}
                    >
                      {savingAiPrompts ? 'Saving...' : 'Save'}
                    </Button>
                  </div>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              <p className="text-muted mb-3">
                Customize the system prompt sent to the LLM for each analysis type.
                Leave empty to use the built-in default. The JSON response format is enforced automatically.
              </p>
              <Form.Group className="mb-0">
                <Form.Label><strong>Typosquat Analysis Prompt</strong></Form.Label>
                <Form.Control
                  as="textarea"
                  rows={10}
                  placeholder={aiDefaultPrompts.typosquat || 'Loading default prompt...'}
                  value={aiPrompts.typosquat}
                  onChange={(e) => setAiPrompts({ ...aiPrompts, typosquat: e.target.value })}
                  disabled={!isUserManager}
                  style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                />
                <Form.Text className="text-muted">
                  {aiPrompts.typosquat ? 'Using custom prompt' : 'Using built-in default prompt'}
                </Form.Text>
              </Form.Group>
            </Card.Body>
          </Card>
            </Tab>
            <Tab eventKey="notifications" title="Notifications & Handlers">
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">Notifications</h5>
                {isUserManager && (
                  <Button
                    variant="outline-secondary"
                    size="sm"
                    onClick={() => {
                      setCopySourceProgram('');
                      loadOtherPrograms();
                      setShowCopyNotificationsModal(true);
                    }}
                  >
                    Copy from another program
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {(() => {
                const ns = notificationSettings;
                const canEdit = isUserManager;
                return (
                  <Form onSubmit={(e) => { e.preventDefault(); handleSaveNotifications(ns); }}>
                    <Row className="mb-3">
                      <Col md={6}>
                        <Form.Check
                          type="switch"
                          id="notify-enabled"
                          label="Enable Notifications"
                          checked={ns.enabled}
                          onChange={(e) => setNotificationSettings({ ...ns, enabled: e.target.checked })}
                          disabled={!canEdit || savingNotifications}
                        />
                      </Col>
                    </Row>

                    <Row className="mb-3">
                      <Col md={8}>
                        <Form.Label>Discord Webhook URL</Form.Label>
                        <Form.Control
                          type="text"
                          placeholder="https://discord.com/api/webhooks/..."
                          value={ns.discord_webhook_url || ''}
                          onChange={(e) => setNotificationSettings({ ...ns, discord_webhook_url: e.target.value })}
                          disabled={!canEdit || savingNotifications}
                        />
                      </Col>
                    </Row>

                    <Row className="mb-3">
                      <Col md={6}>
                        <h6>Asset Created Events</h6>
                        {['subdomain','url','ip','service','certificate'].map((t) => {
                          const ev = ns.events.assets.created[t] || { enabled: false, webhook_url: '' };
                          return (
                            <div key={`created-${t}`} className="mb-2">
                              <Form.Check
                                type="checkbox"
                                id={`notify-assets-created-${t}`}
                                label={`New ${t}`}
                                checked={Boolean(ev.enabled)}
                                onChange={(e) => setNotificationSettings({
                                  ...ns,
                                  events: {
                                    ...ns.events,
                                    assets: {
                                      ...ns.events.assets,
                                      created: {
                                        ...ns.events.assets.created,
                                        [t]: { ...ev, enabled: e.target.checked }
                                      }
                                    }
                                  },
                                })}
                                disabled={!canEdit || savingNotifications}
                              />
                              {ev.enabled && (
                                <Form.Control
                                  size="sm"
                                  className="mt-1 ms-4"
                                  placeholder="Webhook (optional, uses global)"
                                  value={ev.webhook_url || ''}
                                  onChange={(e) => setNotificationSettings({
                                    ...ns,
                                    events: {
                                      ...ns.events,
                                      assets: {
                                        ...ns.events.assets,
                                        created: {
                                          ...ns.events.assets.created,
                                          [t]: { ...ev, webhook_url: e.target.value }
                                        }
                                      }
                                    },
                                  })}
                                  disabled={!canEdit || savingNotifications}
                                />
                              )}
                            </div>
                          );
                        })}
                      </Col>
                      <Col md={6}>
                        <h6>Asset Updated Events</h6>
                        {['subdomain','url','ip','service','certificate'].map((t) => {
                          const ev = ns.events.assets.updated[t] || { enabled: false, webhook_url: '' };
                          return (
                            <div key={`updated-${t}`} className="mb-2">
                              <Form.Check
                                type="checkbox"
                                id={`notify-assets-updated-${t}`}
                                label={`Updated ${t}`}
                                checked={Boolean(ev.enabled)}
                                onChange={(e) => setNotificationSettings({
                                  ...ns,
                                  events: {
                                    ...ns.events,
                                    assets: {
                                      ...ns.events.assets,
                                      updated: {
                                        ...ns.events.assets.updated,
                                        [t]: { ...ev, enabled: e.target.checked }
                                      }
                                    }
                                  },
                                })}
                                disabled={!canEdit || savingNotifications}
                              />
                              {ev.enabled && (
                                <Form.Control
                                  size="sm"
                                  className="mt-1 ms-4"
                                  placeholder="Webhook (optional, uses global)"
                                  value={ev.webhook_url || ''}
                                  onChange={(e) => setNotificationSettings({
                                    ...ns,
                                    events: {
                                      ...ns.events,
                                      assets: {
                                        ...ns.events.assets,
                                        updated: {
                                          ...ns.events.assets.updated,
                                          [t]: { ...ev, webhook_url: e.target.value }
                                        }
                                      }
                                    },
                                  })}
                                  disabled={!canEdit || savingNotifications}
                                />
                              )}
                            </div>
                          );
                        })}
                      </Col>
                    </Row>

                    <Row className="mb-3">
                      <Col md={6}>
                        <h6>Findings (Nuclei)</h6>
                        <p className="text-muted small">One webhook for all severities (empty = use global)</p>
                        {['info','low','medium','high','critical'].map((sev) => (
                          <Form.Check
                            key={sev}
                            type="checkbox"
                            id={`notify-nuclei-${sev}`}
                            label={sev.charAt(0).toUpperCase() + sev.slice(1)}
                            checked={ns.events.findings.nuclei_severities.includes(sev)}
                            onChange={(e) => {
                              const set = new Set(ns.events.findings.nuclei_severities);
                              if (e.target.checked) set.add(sev); else set.delete(sev);
                              setNotificationSettings({
                                ...ns,
                                events: {
                                  ...ns.events,
                                  findings: {
                                    ...ns.events.findings,
                                    nuclei_severities: Array.from(set),
                                    nuclei_webhook_url: ns.events.findings.nuclei_webhook_url || ''
                                  }
                                },
                              });
                            }}
                            disabled={!canEdit || savingNotifications}
                          />
                        ))}
                        {(ns.events.findings.nuclei_severities?.length || 0) > 0 && (
                          <Form.Control
                            size="sm"
                            className="mt-2"
                            placeholder="Nuclei webhook (optional, uses global)"
                            value={ns.events.findings.nuclei_webhook_url || ''}
                            onChange={(e) => setNotificationSettings({
                              ...ns,
                              events: {
                                ...ns.events,
                                findings: {
                                  ...ns.events.findings,
                                  nuclei_webhook_url: e.target.value
                                }
                              },
                            })}
                            disabled={!canEdit || savingNotifications}
                          />
                        )}
                      </Col>
                    </Row>

                    <Row className="mb-3">
                      <Col md={6}>
                        <h6>CT Typosquat Alerts</h6>
                        <p className="text-muted small">Certificate Transparency typosquat alerts (critical/high)</p>
                        <Form.Check
                          type="checkbox"
                          id="notify-ct-alerts"
                          label="Enable CT typosquat alerts"
                          checked={Boolean(ns.events.ct_alerts?.enabled)}
                          onChange={(e) => setNotificationSettings({
                            ...ns,
                            events: {
                              ...ns.events,
                              ct_alerts: { ...(ns.events.ct_alerts || {}), enabled: e.target.checked, webhook_url: ns.events.ct_alerts?.webhook_url || '' }
                            }
                          })}
                          disabled={!canEdit || savingNotifications}
                        />
                        {ns.events.ct_alerts?.enabled && (
                          <Form.Control
                            size="sm"
                            className="mt-2"
                            placeholder="CT typosquat webhook (optional, uses global)"
                            value={ns.events.ct_alerts?.webhook_url || ''}
                            onChange={(e) => setNotificationSettings({
                              ...ns,
                              events: {
                                ...ns.events,
                                ct_alerts: { ...(ns.events.ct_alerts || {}), enabled: true, webhook_url: e.target.value }
                              }
                            })}
                            disabled={!canEdit || savingNotifications}
                          />
                        )}
                      </Col>
                      <Col md={6}>
                        <h6>CT Asset Discovery</h6>
                        <p className="text-muted small">In-scope subdomains discovered via CT asset monitoring</p>
                        <Form.Check
                          type="checkbox"
                          id="notify-ct-asset-alerts"
                          label="Enable CT asset discovery alerts"
                          checked={Boolean(ns.events.ct_asset_alerts?.enabled)}
                          onChange={(e) => setNotificationSettings({
                            ...ns,
                            events: {
                              ...ns.events,
                              ct_asset_alerts: { ...(ns.events.ct_asset_alerts || {}), enabled: e.target.checked, webhook_url: ns.events.ct_asset_alerts?.webhook_url || '' }
                            }
                          })}
                          disabled={!canEdit || savingNotifications}
                        />
                        {ns.events.ct_asset_alerts?.enabled && (
                          <Form.Control
                            size="sm"
                            className="mt-2"
                            placeholder="CT asset discovery webhook (optional, uses global)"
                            value={ns.events.ct_asset_alerts?.webhook_url || ''}
                            onChange={(e) => setNotificationSettings({
                              ...ns,
                              events: {
                                ...ns.events,
                                ct_asset_alerts: { ...(ns.events.ct_asset_alerts || {}), enabled: true, webhook_url: e.target.value }
                              }
                            })}
                            disabled={!canEdit || savingNotifications}
                          />
                        )}
                      </Col>
                    </Row>


                    <div className="mt-3">
                      <Button type="submit" variant="primary" disabled={!canEdit || savingNotifications}>
                        {savingNotifications ? 'Saving...' : 'Save Notifications'}
                      </Button>
                    </div>
                  </Form>
                );
              })()}
            </Card.Body>
          </Card>

          <Modal show={showCopyNotificationsModal} onHide={() => setShowCopyNotificationsModal(false)}>
            <Modal.Header closeButton>
              <Modal.Title>Copy Notification Settings</Modal.Title>
            </Modal.Header>
            <Modal.Body>
              <Form.Group className="mb-3">
                <Form.Label>Select program to copy from</Form.Label>
                <Form.Select
                  value={copySourceProgram}
                  onChange={(e) => setCopySourceProgram(e.target.value)}
                  disabled={copyNotificationsLoading}
                >
                  <option value="">-- Select program --</option>
                  {otherPrograms.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" onClick={() => setShowCopyNotificationsModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => handleCopyNotificationsFrom(copySourceProgram)}
                disabled={!copySourceProgram || copyNotificationsLoading}
              >
                {copyNotificationsLoading ? 'Copying...' : 'Copy'}
              </Button>
            </Modal.Footer>
          </Modal>

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">Event Handlers</h5>
              </div>
            </Card.Header>
            <Card.Body>
              <p className="text-muted small mb-3">
                System and global handlers always apply. You can add optional handlers for this program only (they merge on top of global).
                Discord notification handlers are driven by notification settings below, not stored here.
              </p>
              {eventHandlerLoading ? (
                <Spinner animation="border" size="sm" />
              ) : (
                <>
                  <Form.Check
                    type="switch"
                    id="event-handler-use-global"
                    label="Use global defaults"
                    checked={eventHandlerUseGlobal}
                    onChange={(e) => setEventHandlerUseGlobal(e.target.checked)}
                    disabled={!isUserManager || eventHandlerSaving}
                    className="mb-3"
                  />
                  {!eventHandlerUseGlobal && !eventHandlerAddonMode && eventHandlerHandlers.length > 0 && (
                    <Alert variant="warning" className="small py-2">
                      This program uses a <strong>legacy full override</strong> (a snapshot of handlers). Saving keeps that mode.
                      Use &quot;Revert to global&quot; to clear it, then &quot;Add program-specific handlers&quot; for additive handlers that stay merged with global updates.
                    </Alert>
                  )}
                  {!eventHandlerUseGlobal && (
                    <>
                      <p className="small text-muted mb-2">
                        {eventHandlerAddonMode
                          ? `Additional handlers for this program: ${eventHandlerHandlers.length}`
                          : `Program handler snapshot: ${eventHandlerHandlers.length} handler${eventHandlerHandlers.length !== 1 ? 's' : ''}`}
                      </p>
                      <Table responsive size="sm" className="mb-3">
                        <thead>
                          <tr>
                            <th>ID</th>
                            <th>Event types</th>
                            <th>Description</th>
                            {isUserManager && <th style={{ width: 120 }}>Actions</th>}
                          </tr>
                        </thead>
                        <tbody>
                          {eventHandlerHandlers.map((h, i) => (
                            <tr key={i}>
                              <td><code>{h.id || '-'}</code></td>
                              <td><Badge bg="secondary" className="text-wrap text-start" style={{ maxWidth: 420 }}>{formatEventTypesCell(h)}</Badge></td>
                              <td>{h.description || '-'}</td>
                              {isUserManager && (
                                <td>
                                  <Button variant="link" size="sm" className="p-0 me-2" onClick={() => { setEventHandlerEditingIndex(i); setEventHandlerEditingHandler(JSON.parse(JSON.stringify(h))); setShowEventHandlerFormModal(true); }}>Edit</Button>
                                  <Button variant="link" size="sm" className="p-0 text-danger" onClick={() => { if (window.confirm('Remove this handler?')) setEventHandlerHandlers(eventHandlerHandlers.filter((_, j) => j !== i)); }}>Remove</Button>
                                </td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                      <div className="d-flex flex-wrap gap-2 mb-2">
                        {isUserManager && (
                          <Button variant="outline-primary" size="sm" onClick={() => { setEventHandlerEditingIndex(null); setEventHandlerEditingHandler({ id: 'new_handler', event_type: ['assets.subdomain.created'], description: 'New handler', conditions: [], conditions_by_event_type: {}, actions: [{ type: 'log', level: 'info', message_template: 'Event: {event_type}' }] }); setShowEventHandlerFormModal(true); }}>
                            Add Handler
                          </Button>
                        )}
                        <Button variant="outline-secondary" size="sm" onClick={() => { setEventHandlerEditJson(JSON.stringify(eventHandlerHandlers, null, 2)); setShowEventHandlerEditModal(true); }}>
                          Edit as JSON
                        </Button>
                      </div>
                      <div className="d-flex gap-2">
                        <Button variant="primary" size="sm" onClick={handleSaveEventHandlers} disabled={!isUserManager || eventHandlerSaving}>
                          {eventHandlerSaving ? 'Saving...' : 'Save'}
                        </Button>
                        <Button variant="outline-secondary" size="sm" onClick={handleRevertEventHandlers} disabled={!isUserManager || eventHandlerSaving}>
                          Revert to Global
                        </Button>
                      </div>
                    </>
                  )}
                  {eventHandlerUseGlobal && isUserManager && (
                    <Button
                      variant="outline-primary"
                      size="sm"
                      onClick={() => {
                        setEventHandlerHandlers([]);
                        setEventHandlerAddonMode(true);
                        setEventHandlerUseGlobal(false);
                      }}
                    >
                      Add program-specific handlers
                    </Button>
                  )}
                </>
              )}
            </Card.Body>
          </Card>
            </Tab>
            <Tab eventKey="integrations" title="Integrations">
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Phishlabs API Key {program.phishlabs_api_key ? (
                    <Badge bg="primary" className="ms-2">Configured</Badge>
                  ) : (
                    <Badge bg="secondary" className="ms-2">Not Set</Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={() => openEditModal('phishlabs_api_key')}
                  >
                    ✏️ Edit API Key
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {program.phishlabs_api_key ? (
                <div>
                  <p className="text-muted mb-3">This key is used to integrate with the Phishlabs API.</p>
                  <Table borderless>
                    <tbody>
                      <tr>
                        <td width="200"><strong>Current Key:</strong></td>
                        <td style={{ maxWidth: '400px' }}>
                          <Form.Control
                            type="password"
                            value={program.phishlabs_api_key}
                            readOnly
                            plaintext
                            style={{ backgroundColor: 'transparent', paddingLeft: 0 }}
                          />
                        </td>
                      </tr>
                    </tbody>
                  </Table>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No Phishlabs API key configured for this program.</p>
                </div>
              )}
            </Card.Body>
          </Card>

          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  RecordedFuture API Key {program.recordedfuture_api_key ? (
                    <Badge bg="primary" className="ms-2">Configured</Badge>
                  ) : (
                    <Badge bg="secondary" className="ms-2">Not Set</Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={() => openEditModal('recordedfuture_api_key')}
                  >
                    ✏️ Edit API Key
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {program.recordedfuture_api_key ? (
                <div>
                  <p className="text-muted mb-3">This key is used to integrate with the RecordedFuture API.</p>
                  <Table borderless>
                    <tbody>
                      <tr>
                        <td width="200"><strong>Current Key:</strong></td>
                        <td style={{ maxWidth: '400px' }}>
                          <Form.Control
                            type="password"
                            value={program.recordedfuture_api_key}
                            readOnly
                            plaintext
                            style={{ backgroundColor: 'transparent', paddingLeft: 0 }}
                          />
                        </td>
                      </tr>
                    </tbody>
                  </Table>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted">No RecordedFuture API key configured for this program.</p>
                </div>
              )}
            </Card.Body>
          </Card>
              
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Threatstream API Configuration
                  {(program.threatstream_api_key || program.threatstream_api_user) ? (
                    <Badge bg="success" className="ms-2">Configured</Badge>
                  ) : (
                    <Badge bg="secondary" className="ms-2">Not Set</Badge>
                  )}
                </h5>
                {isUserManager && (
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={() => openEditModal('threatstream_credentials')}
                  >
                    ✏️ {(program.threatstream_api_key || program.threatstream_api_user) ? 'Edit' : 'Configure'} Credentials
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              {(program.threatstream_api_key || program.threatstream_api_user) ? (
                <div>
                  <p className="text-muted mb-3">These credentials are used to integrate with the Threatstream API for gathering threat intelligence.</p>
                  <Table borderless>
                    <tbody>
                      {program.threatstream_api_user && (
                        <tr>
                          <td width="200"><strong>API User:</strong></td>
                          <td>
                            <code>{program.threatstream_api_user}</code>
                          </td>
                        </tr>
                      )}
                      {program.threatstream_api_key && (
                        <tr>
                          <td><strong>API Key:</strong></td>
                          <td>
                            <Form.Control
                              type="password"
                              value={program.threatstream_api_key}
                              readOnly
                              plaintext
                              style={{ backgroundColor: 'transparent', paddingLeft: 0, maxWidth: '400px' }}
                            />
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </div>
              ) : (
                <div className="text-center py-3">
                  <p className="text-muted mb-3">No Threatstream API credentials configured for this program.</p>
                  <p className="text-muted">Configure both API user and API key to enable Threatstream integration.</p>
                </div>
              )}
            </Card.Body>
          </Card>
            </Tab>
            <Tab eventKey="wordlists" title="Wordlists">
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Program Wordlists 
                  <Badge bg="info" className="ms-2">Coming Soon</Badge>
                </h5>
                {isUserManager && (
                  <Button 
                    variant="outline-primary" 
                    size="sm"
                    disabled
                    title="Wordlist management will be available soon"
                  >
                    📚 Manage Wordlists
                  </Button>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              <div className="text-center py-3">
                <p className="text-muted">
                  Program-specific wordlist management will be available soon. 
                  This will allow you to upload and manage wordlists that are specific to this program.
                </p>
                <p className="text-muted">
                  For now, you can use global wordlists from the Admin section.
                </p>
                <Button 
                  variant="outline-secondary" 
                  size="sm"
                  onClick={() => window.open('/admin/wordlists', '_blank')}
                >
                  📚 View Global Wordlists
                </Button>
              </div>
            </Card.Body>
          </Card>
            </Tab>
          </Tabs>
        </Col>

        <Col md={4}>
          <Card className="rh-elevated-card mb-4">
            <Card.Header className="rh-card-header-table">
              <h5 className="mb-0">Program Data</h5>
            </Card.Header>
            <Card.Body>
              <p className="text-muted mb-3">Raw program data in JSON format:</p>
              <pre style={{ 
                fontSize: '0.8em', 
                backgroundColor: 'var(--bs-pre-bg)', 
                color: 'var(--bs-pre-color)',
                padding: '10px', 
                borderRadius: '4px',
                maxHeight: '400px',
                overflow: 'auto'
              }}>
                {JSON.stringify(program, null, 2)}
              </pre>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Edit Modal */}
      <Modal show={showEditModal} onHide={() => setShowEditModal(false)} size="lg">
        <Modal.Header closeButton>
                    <Modal.Title>
            Edit {editType === 'scope_domains' ? 'In-scope domain patterns' :
                  editType === 'out_of_scope_domains' ? 'Out-of-scope domain patterns' :
                  editType === 'domain_regex' ? 'Domain Regex Patterns' :
                  editType === 'out_of_scope_regex' ? 'Out-of-scope regex (legacy)' :
                  editType === 'cidr_list' ? 'CIDR Blocks' :
                  editType === 'safe_registrar' ? 'Safe Registrars' :
                  editType === 'safe_ssl_issuer' ? 'Safe SSL Issuers' :
                  editType === 'protected_domains' ? 'Protected Domains' :
                  editType === 'protected_subdomain_prefixes' ? 'Protected Keywords' :
                  editType === 'phishlabs_api_key' ? 'Phishlabs API Key' :
                  editType === 'threatstream_credentials' ? 'Threatstream API Credentials' :
                  'Configuration'}
          </Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleEdit}>
          <Modal.Body>
            <Alert variant="info">
              <strong>Manager Access Required:</strong> Only users with manager-level permissions can edit program settings.
            </Alert>

            {(editType === 'scope_domains' || editType === 'out_of_scope_domains') && editScopeWarnings.length > 0 && (
              <Alert variant="warning" onClose={() => setEditScopeWarnings([])} dismissible>
                <Alert.Heading className="h6 mb-2">
                  {editScopeWarnings.length} invalid pattern{editScopeWarnings.length === 1 ? '' : 's'} skipped
                </Alert.Heading>
                <p className="mb-2 small">
                  The entries below were not saved because they are not valid DNS patterns. Valid rows
                  have been saved. Fix or remove the bad rows and resubmit.
                </p>
                <ul className="mb-0 small">
                  {editScopeWarnings.map((w, i) => (
                    <li key={i}>
                      <code>{w.pattern}</code>
                      {w.reason ? <> — {w.reason}</> : null}
                    </li>
                  ))}
                </ul>
              </Alert>
            )}

            
            {/* Search Box for Edit Modal (list fields; not structured scope rows) */}
            {!singleValueTypes.includes(editType) &&
              editType !== 'scope_domains' &&
              editType !== 'out_of_scope_domains' && (
              <Form.Group className="mb-3">
                <Form.Label>Search in current content:</Form.Label>
                <InputGroup>
                  <InputGroup.Text style={{ 
                    backgroundColor: 'var(--bs-input-bg)',
                    color: 'var(--bs-input-color)',
                    borderColor: 'var(--bs-border-color)'
                  }}>
                    🔍
                  </InputGroup.Text>
                  <Form.Control
                    type="text"
                    placeholder="Search in current items..."
                    value={editModalSearch}
                    onChange={(e) => handleEditModalSearchChange(e.target.value)}
                    style={{
                      backgroundColor: 'var(--bs-input-bg)',
                      color: 'var(--bs-input-color)',
                      borderColor: 'var(--bs-border-color)'
                    }}
                  />
                  {editModalSearch && (
                    <>
                      <Button 
                        variant="outline-secondary"
                        onClick={() => navigateEditModalSearch('prev')}
                        disabled={getMatchingIndices(editForm.newItems.split('\n'), editModalSearch).length === 0}
                      >
                        ↑
                      </Button>
                      <Button 
                        variant="outline-secondary"
                        onClick={() => navigateEditModalSearch('next')}
                        disabled={getMatchingIndices(editForm.newItems.split('\n'), editModalSearch).length === 0}
                      >
                        ↓
                      </Button>
                      <Button 
                        variant="outline-secondary" 
                        onClick={() => handleEditModalSearchChange('')}
                      >
                        Clear
                      </Button>
                    </>
                  )}
                </InputGroup>
                <Form.Text className="text-muted">
                  Search through the current content to find specific items. Use ↑↓ buttons to navigate between matches.
                  {editModalSearch && getMatchingIndices(editForm.newItems.split('\n'), editModalSearch).length > 0 && (
                    <span> • Showing {editModalSearchIndex + 1} of {getMatchingIndices(editForm.newItems.split('\n'), editModalSearch).length} matches</span>
                  )}
                </Form.Text>
              </Form.Group>
            )}
            
            <Form.Group className="mb-3">
              <Form.Label>
                {editType === 'scope_domains' ? 'In-scope patterns' :
                 editType === 'out_of_scope_domains' ? 'Out-of-scope patterns' :
                 editType === 'domain_regex' ? 'Domain Regex Patterns' :
                 editType === 'out_of_scope_regex' ? 'Out-of-scope regex' :
                 editType === 'cidr_list' ? 'CIDR Blocks' :
                 editType === 'safe_registrar' ? 'Safe Registrars' : 
                 editType === 'safe_ssl_issuer' ? 'Safe SSL Issuers' :
                 editType === 'protected_domains' ? 'Protected Domains' :
                 editType === 'protected_subdomain_prefixes' ? 'Protected Keywords' :
                 editType === 'recordedfuture_api_key' ? 'RecordedFuture API Key' :
                 'Phishlabs API Key'}
                {!singleValueTypes.includes(editType) &&
                  editType !== 'scope_domains' &&
                  editType !== 'out_of_scope_domains' && (
                  <small className="text-muted"> (one per line)</small>
                )}
              </Form.Label>

              {editType === 'threatstream_credentials' ? (
                <div>
                  <Form.Group className="mb-3">
                    <Form.Label>API User</Form.Label>
                    <Form.Control
                      type="text"
                      value={editForm.api_user}
                      onChange={(e) => setEditForm({ ...editForm, api_user: e.target.value })}
                      placeholder="Enter your Threatstream API username"
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)'
                      }}
                    />
                  </Form.Group>
                  <Form.Group className="mb-3">
                    <Form.Label>API Key</Form.Label>
                    <Form.Control
                      type="password"
                      value={editForm.api_key}
                      onChange={(e) => setEditForm({ ...editForm, api_key: e.target.value })}
                      placeholder="Enter your Threatstream API key"
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)'
                      }}
                    />
                  </Form.Group>
                </div>
              ) : editType === 'scope_domains' || editType === 'out_of_scope_domains' ? (
                <ScopeDomainsEditor
                  rows={editForm.scopeDomainRows || []}
                  onChange={(scopeDomainRows) => setEditForm({ ...editForm, scopeDomainRows })}
                  disabled={editLoading}
                  invalidPatterns={editScopeWarnings}
                />
              ) : singleValueTypes.includes(editType) ? (
                <Form.Control
                  type="text"
                  value={editForm.newItems}
                  onChange={(e) => setEditForm({ ...editForm, newItems: e.target.value })}
                  placeholder={
                    editType === 'phishlabs_api_key' ? 'Enter your Phishlabs API key (e.g., 1234567890abcdef1234567890abcdef12345678)' :
                    'Enter value'
                  }
                  style={{
                    backgroundColor: 'var(--bs-input-bg)',
                    color: 'var(--bs-input-color)',
                    borderColor: 'var(--bs-border-color)'
                  }}
                />
              ) : (
                <Form.Control
                  as="textarea"
                  rows={8}
                  value={editForm.newItems}
                  onChange={(e) => setEditForm({ ...editForm, newItems: e.target.value })}
                  placeholder={
                    editType === 'domain_regex'
                      ? 'Enter regex patterns, one per line:\nexample\\.com$\n.*\\.example\\.org$'
                      : editType === 'cidr_list'
                      ? 'Enter CIDR blocks, one per line:\n192.168.1.0/24\n10.0.0.0/8'
                      : editType === 'safe_registrar'
                      ? 'Enter safe registrars, one per line:\nGoDaddy\nNamecheap\nCloudflare'
                      : editType === 'protected_domains'
                      ? 'Enter apex domains to monitor, one per line:\nexample.com\nmycompany.org\nbrand.io'
                      : editType === 'protected_subdomain_prefixes'
                      ? 'Enter keywords, one per line:\nmyorganization\nmycompany\nbrandname'
                      : 'Enter safe SSL issuers, one per line:\nLet\'s Encrypt\nDigiCert\nCloudflare'
                  }
                  style={{
                    backgroundColor: 'var(--bs-input-bg)',
                    color: 'var(--bs-input-color)',
                    borderColor: 'var(--bs-border-color)'
                  }}
                />
              )}
            </Form.Group>

                        <Form.Text className="text-muted">
              {editType === 'scope_domains' || editType === 'out_of_scope_domains'
                ? 'Use hostname patterns; * is only allowed as a full label. domain.com + Wildcard=Yes includes apex + subdomains, while *.domain.com includes subdomains only (not apex).'
                : editType === 'domain_regex'
                ? 'Enter regular expressions that match domain names for this program'
                : editType === 'out_of_scope_regex'
                ? 'Legacy regex exclusions (advanced)'
                : editType === 'cidr_list'
                ? 'Enter CIDR notation for IP address ranges (e.g., 192.168.1.0/24)'
                : editType === 'safe_registrar'
                ? 'Enter registrar names that are considered safe/legitimate for this program'
                : editType === 'safe_ssl_issuer'
                ? 'Enter SSL certificate issuer names that are considered safe/legitimate for this program'
                : editType === 'protected_domains'
                ? 'Enter apex domains to monitor for typosquatting and CT (Certificate Transparency) alerts'
                : editType === 'protected_subdomain_prefixes'
                ? 'Enter keywords that automatically qualify typosquat domains for insertion when found anywhere in the domain name (e.g. myorganization, mycompany)'
                : editType === 'phishlabs_api_key'
                ? 'Enter your Phishlabs API key.'
                : editType === 'recordedfuture_api_key'
                ? 'Enter your RecordedFuture API key.'
                : editType === 'threatstream_credentials'
                ? 'Enter both your Threatstream API username and API key for threat intelligence gathering. Both fields are required for the integration to work.'
                : 'Enter the required value.'
              }
              {!singleValueTypes.includes(editType) && editType !== 'threatstream_credentials' && editType !== 'recordedfuture_api_key' && (
                <>
                  <br/>
                  <strong>Tip:</strong> Delete lines to remove items, or clear all text to empty the list (with overwrite mode enabled).
                </>
              )}
            </Form.Text>
              {!singleValueTypes.includes(editType) && editType !== 'threatstream_credentials' && editType !== 'scope_domains' && editType !== 'out_of_scope_domains' && (
              <Form.Group className="mb-3">
                <Form.Check
                  type="checkbox"
                  label="Replace entire list (recommended)"
                  checked={editForm.overwrite}
                  onChange={(e) => setEditForm({ ...editForm, overwrite: e.target.checked })}
                />
                <Form.Text className="text-muted">
                  If checked, the entire list will be replaced with the values above (allows removal of items and clearing entire list).
                  If unchecked, new items will be added to existing ones without removing any.
                </Form.Text>
              </Form.Group>
            )}
            {(editType === 'scope_domains' || editType === 'out_of_scope_domains') && (
              <p className="text-muted small">Structured patterns always replace the full list from this editor. Tip: keep `domain.com` with Wildcard=Yes when you need to include the apex itself.</p>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={editLoading}>
              {editLoading ? 'Updating...' : `Update ${editType === 'scope_domains' || editType === 'out_of_scope_domains' ? 'patterns' :
                                                      editType === 'domain_regex' ? 'Patterns' :
                                                      editType === 'out_of_scope_regex' ? 'regex' :
                                                      editType === 'cidr_list' ? 'CIDR Blocks' :
                                                      editType === 'safe_registrar' ? 'Registrars' :
                                                      editType === 'safe_ssl_issuer' ? 'SSL Issuers' :
                                                      editType === 'protected_domains' ? 'Protected Domains' :
                                                      editType === 'protected_subdomain_prefixes' ? 'Keywords' :
                                                      editType === 'phishlabs_api_key' ? 'Phishlabs API Key' :
                                                      editType === 'recordedfuture_api_key' ? 'RecordedFuture API Key' :
                                                      editType === 'threatstream_credentials' ? 'Threatstream Credentials' :
                                                      'Configuration'}`}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Import Domains Modal */}
      <Modal show={showImportModal} onHide={() => setShowImportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Import Domains</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleImportSubmit}>
          <Modal.Body>
            {importError && (
              <Alert variant="danger" onClose={() => setImportError('')} dismissible>
                {importError}
              </Alert>
            )}
            {importScopeWarnings.length > 0 && (
              <Alert variant="warning" onClose={() => setImportScopeWarnings([])} dismissible>
                <Alert.Heading className="h6 mb-2">
                  {importScopeWarnings.length} invalid pattern{importScopeWarnings.length === 1 ? '' : 's'} skipped
                </Alert.Heading>
                <p className="mb-2 small">
                  Valid entries were imported. These were rejected as invalid DNS patterns:
                </p>
                <ul className="mb-0 small">
                  {importScopeWarnings.map((w, i) => (
                    <li key={i}>
                      <code>{w.pattern}</code>
                      {w.reason ? <> — {w.reason}</> : null}
                    </li>
                  ))}
                </ul>
              </Alert>
            )}
            <Alert variant="info">
              Paste domains below or choose a .txt file with one domain per line.
            </Alert>

            <Form.Group className="mb-3">
              <Form.Label>Domains (one per line)</Form.Label>
              <Form.Control
                as="textarea"
                rows={10}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder={"example.com\nsub.example.org\ninternal.example.net"}
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
              <Form.Text className="text-muted">
                Blank lines will be ignored. Duplicates will be removed when merging with existing patterns.
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Import from file</Form.Label>
              <Form.Control
                type="file"
                accept=".txt,text/plain"
                onChange={(e) => handleImportFile(e.target.files && e.target.files[0])}
              />
              <Form.Text className="text-muted">
                Select a .txt file containing domains, one per line. Its content will be appended to the textarea above.
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                id="import-wildcard"
                label="Import as wildcard (match domain and all subdomains)"
                checked={importWildcard}
                onChange={(e) => setImportWildcard(e.target.checked)}
              />
              <Form.Text className="text-muted">
                When enabled, generated regex will match the exact domain and any subdomains. When disabled, regex will match the exact domain only.
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                id="import-replace-all"
                label="Replace existing patterns instead of appending"
                checked={importReplaceAll}
                onChange={(e) => setImportReplaceAll(e.target.checked)}
              />
              <Form.Text className="text-muted">
                Disabled by default. When enabled, the imported list will overwrite the program's existing domain regex patterns.
              </Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowImportModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={importLoading}>
              {importLoading ? 'Importing...' : 'Import'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      <Modal show={showEventHandlerFormModal} onHide={() => setShowEventHandlerFormModal(false)} size="xl" scrollable>
        <Modal.Header closeButton>
          <Modal.Title>{eventHandlerEditingIndex !== null ? 'Edit Handler' : 'Add Handler'}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {eventHandlerEditingHandler && (
            <EventHandlerForm handler={eventHandlerEditingHandler} onChange={setEventHandlerEditingHandler} />
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowEventHandlerFormModal(false)}>Cancel</Button>
          <Button variant="primary" onClick={() => {
            if (!eventHandlerEditingHandler?.id?.trim()) { setError('Handler ID is required'); return; }
            if (!(eventHandlerEditingHandler?.actions?.length > 0)) { setError('At least one action is required'); return; }
            const coerced = sanitizeHandlerForSave(eventHandlerEditingHandler);
            if (!(coerced.event_type?.length > 0)) { setError('At least one event type is required'); return; }
            setError('');
            const next = [...eventHandlerHandlers];
            if (eventHandlerEditingIndex !== null) next[eventHandlerEditingIndex] = coerced;
            else next.push(coerced);
            setEventHandlerHandlers(next);
            setShowEventHandlerFormModal(false);
          }}>Save</Button>
        </Modal.Footer>
      </Modal>

      <Modal show={showEventHandlerEditModal} onHide={() => setShowEventHandlerEditModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Edit Event Handlers (JSON)</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Control
            as="textarea"
            rows={18}
            value={eventHandlerEditJson}
            onChange={(e) => setEventHandlerEditJson(e.target.value)}
            style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowEventHandlerEditModal(false)}>Cancel</Button>
          <Button variant="primary" onClick={() => {
            try {
              const parsed = JSON.parse(eventHandlerEditJson);
              if (!Array.isArray(parsed)) throw new Error('Must be an array of handlers');
              setEventHandlerHandlers(coerceHandlersList(parsed));
              setShowEventHandlerEditModal(false);
            } catch (e) {
              setError('Invalid JSON: ' + e.message);
            }
          }}>Apply</Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default ProgramDetail;