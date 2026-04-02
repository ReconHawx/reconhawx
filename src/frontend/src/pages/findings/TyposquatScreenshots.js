import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Container, Row, Col, Card, Table, Badge, Pagination, Form, InputGroup, Button, Spinner, Accordion, Modal, Image } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { typosquatScreenshotAPI, API_BASE_URL } from '../../services/api';
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

// Lazy loading image component
const LazyImage = ({ src, alt, style, onClick, onError, placeholder }) => {
  const [isLoaded, setIsLoaded] = useState(false);
  const [isInView, setIsInView] = useState(false);
  const [hasError, setHasError] = useState(false);
  const imgRef = useRef();

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1, rootMargin: '50px' }
    );

    if (imgRef.current) {
      observer.observe(imgRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const handleLoad = () => {
    setIsLoaded(true);
  };

  const handleError = (e) => {
    setHasError(true);
    if (onError) onError(e);
  };

  return (
    <div ref={imgRef} style={style} onClick={onClick}>
      {!isInView ? (
        // Placeholder while not in view
        <div
          style={{
            ...style,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#f8f9fa',
            border: '1px solid #dee2e6'
          }}
        >
          <i className="fas fa-image text-muted"></i>
        </div>
      ) : hasError ? (
        // Error state
        <div
          style={{
            ...style,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#f8f9fa'
          }}
        >
          <i className="fas fa-image text-muted" style={{ fontSize: '2rem' }}></i>
        </div>
      ) : (
        // Loading/loaded image
        <>
          {!isLoaded && (
            <div
              style={{
                ...style,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: '#f8f9fa',
                position: 'absolute',
                zIndex: 1
              }}
            >
              <Spinner animation="border" size="sm" />
            </div>
          )}
          <Image
            src={src}
            alt={alt}
            style={{
              ...style,
              opacity: isLoaded ? 1 : 0,
              transition: 'opacity 0.3s ease'
            }}
            onLoad={handleLoad}
            onError={handleError}
          />
        </>
      )}
    </div>
  );
};

function TyposquatScreenshots() {
  usePageTitle(formatPageTitle('Typosquat Screenshots'));
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProgram, setSelectedProgram } = useProgramFilter();
  const [screenshots, setScreenshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [searchFilter, setSearchFilter] = useState('');
  const [urlFilter, setUrlFilter] = useState('');
  const [typosquatTypeFilter, setTyposquatTypeFilter] = useState('');
  const [excludeParkedDomains, setExcludeParkedDomains] = useState(false);
  const [sortField, setSortField] = useState('updated_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const [showModal, setShowModal] = useState(false);
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);
  const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'table'
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showFullscreen, setShowFullscreen] = useState(false);
  const [fullscreenImageError, setFullscreenImageError] = useState(false);
  const [deletingItem, setDeletingItem] = useState(null);

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
    if (searchFilter) params.set('search_url', searchFilter);
    if (urlFilter) params.set('url_equals', urlFilter);
    if (typosquatTypeFilter) params.set('typosquat_type', typosquatTypeFilter);
    if (excludeParkedDomains) params.set('exclude_parked', '1');
    if (selectedProgram) params.set('program', selectedProgram);
    if (sortField) params.set('sort_by', sortField);
    if (sortDirection) params.set('sort_dir', sortDirection);
    if (currentPage && currentPage !== 1) params.set('page', String(currentPage));
    if (pageSize && pageSize !== 50) params.set('page_size', String(pageSize));
    return params;
  }, [searchFilter, urlFilter, typosquatTypeFilter, excludeParkedDomains, selectedProgram, sortField, sortDirection, currentPage, pageSize]);

  // Parse query params into state (runs on URL change and initial load)
  useEffect(() => {
    isSyncingFromUrl.current = true;
    const urlParams = new URLSearchParams(location.search);

    const urlSearch = urlParams.get('search_url') || '';
    if (urlSearch !== searchFilter) setSearchFilter(urlSearch);

    const urlEquals = urlParams.get('url_equals') || '';
    if (urlEquals !== urlFilter) setUrlFilter(urlEquals);

    const urlTyposquatType = urlParams.get('typosquat_type') || '';
    if (urlTyposquatType !== typosquatTypeFilter) setTyposquatTypeFilter(urlTyposquatType);

    const urlExcludeParked = urlParams.get('exclude_parked') === '1';
    if (urlExcludeParked !== excludeParkedDomains) setExcludeParkedDomains(urlExcludeParked);

    const urlProgram = urlParams.get('program') || '';
    if (urlProgram && urlProgram !== selectedProgram) setSelectedProgram(urlProgram);

    const urlSortBy = urlParams.get('sort_by');
    if (urlSortBy && urlSortBy !== sortField) setSortField(urlSortBy);

    const urlSortDir = urlParams.get('sort_dir');
    if (urlSortDir && (urlSortDir === 'asc' || urlSortDir === 'desc') && urlSortDir !== sortDirection) setSortDirection(urlSortDir);

    const urlPage = parseInt(urlParams.get('page') || '1', 10);
    if (!Number.isNaN(urlPage) && urlPage > 0 && urlPage !== currentPage) setCurrentPage(urlPage);

    const urlPageSize = parseInt(urlParams.get('page_size') || '50', 10);
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
  }, [navigate, location.pathname, searchFilter, urlFilter, typosquatTypeFilter, excludeParkedDomains, selectedProgram, sortField, sortDirection, currentPage, pageSize, buildUrlParamsFromState, location.search]);

  const fetchScreenshots = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = {};
      if (searchFilter) params.search_url = searchFilter;
      if (urlFilter) params.url_equals = urlFilter;
      if (typosquatTypeFilter) params.typosquat_type = typosquatTypeFilter;
      if (excludeParkedDomains) params.exclude_parked = true;
      if (selectedProgram) params.program = selectedProgram;
      params.sort_by = sortField;
      params.sort_dir = sortDirection;
      params.page = page;
      params.page_size = pageSize;
      
      // Use typosquat-specific API endpoint
      const data = await typosquatScreenshotAPI.searchTyposquatScreenshots(params);


      // The API now returns the correct structure with items and pagination
      const items = data.items || [];
      const totalPages = data.pagination?.total_pages || 1;
      const totalItems = data.pagination?.total_items || 0;


      setScreenshots(items);
      setTotalPages(totalPages);
      setTotalItems(totalItems);
      

      
      setError(null);
    } catch (err) {
      setError('Failed to fetch typosquat screenshots: ' + err.message);
      setScreenshots([]);
    } finally {
      setLoading(false);
    }
  }, [searchFilter, urlFilter, typosquatTypeFilter, excludeParkedDomains, selectedProgram, sortField, sortDirection, pageSize]);

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

  useEffect(() => {
    fetchScreenshots(currentPage);
  }, [currentPage, fetchScreenshots]);

  // Load Font Awesome CSS on component mount
  useEffect(() => {
    loadFontAwesome();
  }, []);

  // Handle keyboard shortcuts for fullscreen
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && showFullscreen) {
        setShowFullscreen(false);
      }
      if (event.key === 'f' && showModal && !showFullscreen) {
        setFullscreenImageError(false);
        setShowFullscreen(true);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [showFullscreen, showModal]);

  const clearFilters = () => {
    setSearchFilter('');
    setUrlFilter('');
    setTyposquatTypeFilter('');
    setExcludeParkedDomains(false);
    setPageSize(50);
    setCurrentPage(1);
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedItems(new Set(screenshots.map(screenshot => screenshot.id || screenshot._id || screenshot.file_id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (screenshotId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      newSelected.add(screenshotId);
    } else {
      newSelected.delete(screenshotId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setDeleting(true);
      const selectedIds = Array.from(selectedItems);
      await typosquatScreenshotAPI.deleteBatch(selectedIds);
      
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page
      fetchScreenshots(currentPage);
    } catch (err) {
      console.error('Error deleting typosquat screenshots:', err);
      alert('Failed to delete typosquat screenshots: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
    }
  };

  const handleIndividualDelete = async (screenshot, event) => {
    // Stop event propagation to prevent opening the screenshot modal
    event.stopPropagation();
    
    if (!window.confirm(`Are you sure you want to delete this screenshot of ${screenshot.url || 'unknown URL'}?`)) {
      return;
    }

    try {
      const screenshotId = screenshot.id || screenshot._id || screenshot.file_id;
      setDeletingItem(screenshotId);
      await typosquatScreenshotAPI.deleteBatch([screenshotId]);
      
      // Refresh the current page
      fetchScreenshots(currentPage);
    } catch (err) {
      console.error('Error deleting typosquat screenshot:', err);
      alert('Failed to delete typosquat screenshot: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeletingItem(null);
    }
  };

  const handleScreenshotClick = (screenshot) => {
    setSelectedScreenshot(screenshot);
    setShowModal(true);
    setFullscreenImageError(false); // Reset error state when selecting new screenshot
  };

  const handleUrlClick = (screenshot) => {
    if (!screenshot || !screenshot.url_id) return;
    navigate(`/findings/typosquat-urls/details?id=${screenshot.url_id}`);
  };

  const formatScreenshotDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  /** Vendor/sourced screenshots use source_created_at; hide runner/upload capture times in the UI. */
  const getRawSourceCreatedAt = (screenshot) =>
    screenshot?.source_created_at ?? screenshot?.metadata?.source_created_at;

  const hasSourceCreatedAt = (screenshot) => {
    const v = getRawSourceCreatedAt(screenshot);
    return v != null && String(v).trim() !== '';
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'N/A';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  };

  const getFirstCaptureDate = (screenshot) => {
    // Try to get from capture_timestamps array first
    if (screenshot.capture_timestamps && screenshot.capture_timestamps.length > 0) {
      return screenshot.capture_timestamps[0];
    }
    // For typosquat screenshots, use created_at as the first capture date
    return screenshot.created_at;
  };

  const getLastCaptureDate = (screenshot) => {
    if (hasSourceCreatedAt(screenshot)) {
      return getFirstCaptureDate(screenshot);
    }
    // Try to get from capture_timestamps array first
    if (screenshot.capture_timestamps && screenshot.capture_timestamps.length > 0) {
      return screenshot.capture_timestamps[screenshot.capture_timestamps.length - 1];
    }
    // For typosquat screenshots, use last_captured_at if available, otherwise created_at
    return screenshot.last_captured_at || screenshot.created_at;
  };

  const hasMultipleCaptures = (screenshot) => {
    if (hasSourceCreatedAt(screenshot)) {
      return false;
    }
    // First priority: If capture_count is explicitly set, use that as the source of truth
    if (screenshot.capture_count !== undefined) {
      return screenshot.capture_count > 1;
    }
    
    // Second priority: Check if there are actually multiple captures via timestamps array
    if (
      screenshot.capture_timestamps &&
      screenshot.capture_timestamps.length > 1 &&
      !hasSourceCreatedAt(screenshot)
    ) {
      return true;
    }
    
    // Third priority: For typosquat screenshots, check if last_captured_at differs from created_at
    if (!hasSourceCreatedAt(screenshot) && screenshot.last_captured_at && screenshot.created_at) {
      return screenshot.last_captured_at !== screenshot.created_at;
    }
    
    // Fourth priority: Check if first and last capture dates are different (indicating multiple captures)
    const firstDate = getFirstCaptureDate(screenshot);
    const lastDate = getLastCaptureDate(screenshot);
    return firstDate && lastDate && firstDate !== lastDate;
  };

  const getCaptureCount = (screenshot) => {
    if (hasSourceCreatedAt(screenshot)) {
      return 1;
    }
    // First priority: If capture_count is explicitly set, use that as the source of truth
    if (screenshot.capture_count !== undefined) {
      return screenshot.capture_count;
    }
    
    // Second priority: Check if there are actually multiple captures via timestamps array
    if (screenshot.capture_timestamps && screenshot.capture_timestamps.length > 0) {
      if (hasSourceCreatedAt(screenshot) && screenshot.capture_timestamps.length > 1) {
        return 1;
      }
      return screenshot.capture_timestamps.length;
    }
    
    // Third priority: For typosquat screenshots, check if last_captured_at differs from created_at
    if (!hasSourceCreatedAt(screenshot) && screenshot.last_captured_at && screenshot.created_at) {
      return screenshot.last_captured_at !== screenshot.created_at ? 2 : 1;
    }
    
    // Fourth priority: Check if first and last capture dates are different (indicating multiple captures)
    const firstDate = getFirstCaptureDate(screenshot);
    const lastDate = getLastCaptureDate(screenshot);
    return firstDate && lastDate && firstDate !== lastDate ? 2 : 1;
  };

  const getScreenshotUrl = (screenshot, thumbnailSize = null) => {
    // Use the API base URL to construct the screenshot URL
    const baseUrl = `${API_BASE_URL}/findings/typosquat-screenshot/${screenshot.file_id}`;
    const token = localStorage.getItem('access_token');
    const params = new URLSearchParams();
    if (thumbnailSize) params.append('thumbnail', thumbnailSize);
    if (token) params.append('token', token);
    const qs = params.toString();
    return qs ? `${baseUrl}?${qs}` : baseUrl;
  };

  const getTyposquatTypeBadge = (type) => {
    const typeColors = {
      'character_substitution': 'warning',
      'character_omission': 'danger',
      'character_addition': 'info',
      'homograph': 'secondary',
      'tld_swap': 'primary',
      'subdomain': 'success'
    };
    return typeColors[type] || 'secondary';
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
      <Pagination className="justify-content-center">
        <Pagination.First onClick={() => setCurrentPage(1)} disabled={currentPage === 1} />
        <Pagination.Prev onClick={() => setCurrentPage(currentPage - 1)} disabled={currentPage === 1} />
        {startPage > 1 && <Pagination.Ellipsis />}
        {pages}
        {endPage < totalPages && <Pagination.Ellipsis />}
        <Pagination.Next onClick={() => setCurrentPage(currentPage + 1)} disabled={currentPage === totalPages} />
        <Pagination.Last onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} />
      </Pagination>
    );
  };

  const renderGridView = () => (
    <Row>
      {screenshots.map((screenshot) => (
        <Col md={4} lg={3} key={screenshot.file_id} className="mb-4">
          <Card>
            <div style={{ position: 'relative' }}>
              <LazyImage
                src={getScreenshotUrl(screenshot, 400)}
                alt={`Typosquat screenshot of ${screenshot.url || 'unknown URL'}`}
                style={{ 
                  height: '200px', 
                  width: '100%',
                  cursor: 'pointer',
                  objectFit: 'contain',
                  backgroundColor: '#f8f9fa'
                }}
                onClick={() => handleScreenshotClick(screenshot)}
              />
              {/* Delete button */}
              <Button
                variant="outline-danger"
                size="sm"
                style={{
                  position: 'absolute',
                  top: '5px',
                  right: '5px',
                  zIndex: 2,
                  opacity: 0.9
                }}
                onClick={(e) => handleIndividualDelete(screenshot, e)}
                disabled={deletingItem === (screenshot.id || screenshot._id || screenshot.file_id)}
                title="Delete this screenshot"
              >
                {deletingItem === (screenshot.id || screenshot._id || screenshot.file_id) ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  "🗑️"
                )}
              </Button>
              {hasMultipleCaptures(screenshot) && (
                <Badge 
                  bg="info" 
                  style={{ 
                    position: 'absolute', 
                    top: '5px', 
                    right: '55px',
                    zIndex: 2
                  }}
                >
                  {getCaptureCount(screenshot)}x
                </Badge>
              )}
              {/* Typosquat type badge */}
              {screenshot.typosquat_type && (
                <Badge 
                  bg={getTyposquatTypeBadge(screenshot.typosquat_type)}
                  style={{ 
                    position: 'absolute', 
                    top: '5px', 
                    left: '5px',
                    zIndex: 2
                  }}
                >
                  {screenshot.typosquat_type}
                </Badge>
              )}
            </div>
            <Card.Body>
              <Card.Title 
                className="small text-truncate"
                style={{ cursor: 'pointer' }}
                onClick={() => handleUrlClick(screenshot)}
                title={screenshot.url}
              >
                {screenshot.url || 'No URL'}
              </Card.Title>
              <Card.Text className="small text-muted">
                {screenshot.typosquat_type && (
                  <div>
                    <strong>Type:</strong> 
                    <Badge bg={getTyposquatTypeBadge(screenshot.typosquat_type)} className="ms-1 small">
                      {screenshot.typosquat_type}
                    </Badge>
                  </div>
                )}
                <div>
                  <strong>Size:</strong> {formatFileSize(screenshot.file_size)}
                </div>
                {!hasSourceCreatedAt(screenshot) && formatScreenshotDate(getFirstCaptureDate(screenshot)) !== 'N/A' && (
                  <div>
                    <strong>First Captured:</strong> {formatScreenshotDate(getFirstCaptureDate(screenshot))}
                  </div>
                )}
                {!hasSourceCreatedAt(screenshot) && hasMultipleCaptures(screenshot) && getLastCaptureDate(screenshot) !== getFirstCaptureDate(screenshot) && formatScreenshotDate(getLastCaptureDate(screenshot)) !== 'N/A' && (
                  <div>
                    <strong>Last Captured:</strong> {formatScreenshotDate(getLastCaptureDate(screenshot))}
                  </div>
                )}
                {hasMultipleCaptures(screenshot) && (
                  <div>
                    <strong>Captures:</strong> 
                    <Badge bg="info" className="ms-1 small">
                      {getCaptureCount(screenshot)}x
                    </Badge>
                  </div>
                )}
                {screenshot.program_name && (
                  <Badge bg="primary" className="mt-1">
                    {screenshot.program_name}
                  </Badge>
                )}
                {(screenshot.source || screenshot.metadata?.source) && (
                  <div>
                    <strong>Source:</strong>{' '}
                    <Badge bg="secondary" className="small">
                      {screenshot.source || screenshot.metadata?.source}
                    </Badge>
                  </div>
                )}
                {(screenshot.source_created_at || screenshot.metadata?.source_created_at) && (
                  <div>
                    <strong>Source Captured:</strong>{' '}
                    {formatScreenshotDate(screenshot.source_created_at || screenshot.metadata?.source_created_at)}
                  </div>
                )}
              </Card.Text>
            </Card.Body>
          </Card>
        </Col>
      ))}
    </Row>
  );

  const renderTableView = () => (
    <Table hover responsive>
      <thead>
        <tr>
          <th>
            <Form.Check
              type="checkbox"
              checked={selectedItems.size === screenshots.length && screenshots.length > 0}
              onChange={(e) => handleSelectAll(e.target.checked)}
            />
          </th>
          <th>Preview</th>
          <th 
            style={{ cursor: 'pointer' }}
            onClick={() => handleSort('url')}
          >
            URL {getSortIcon('url')}
          </th>
          <th 
            style={{ cursor: 'pointer' }}
                            onClick={() => handleSort('created_at')}
              >
                Capture Dates {getSortIcon('created_at')}
          </th>
          <th 
            style={{ cursor: 'pointer' }}
            onClick={() => handleSort('file_size')}
          >
            Size {getSortIcon('file_size')}
          </th>
          <th>Program</th>
          <th>Source</th>
          <th>Captures</th>
        </tr>
      </thead>
      <tbody>
        {screenshots.map((screenshot) => (
          <tr key={screenshot.file_id}>
            <td onClick={(e) => e.stopPropagation()}>
              <Form.Check
                type="checkbox"
                checked={selectedItems.has(screenshot.id || screenshot._id || screenshot.file_id)}
                onChange={(e) => handleSelectItem(screenshot.id || screenshot._id || screenshot.file_id, e.target.checked)}
              />
            </td>
            <td>
              <LazyImage
                src={getScreenshotUrl(screenshot, 160)}
                alt={`Typosquat screenshot of ${screenshot.url || 'unknown URL'}`}
                style={{ 
                  width: '80px', 
                  height: '60px',
                  cursor: 'pointer',
                  border: '1px solid #dee2e6',
                  borderRadius: '4px',
                  objectFit: 'contain',
                  backgroundColor: '#f8f9fa'
                }}
                onClick={() => handleScreenshotClick(screenshot)}
              />
            </td>
            <td>
              <code 
                className="text-break"
                style={{ cursor: 'pointer' }}
                onClick={() => handleUrlClick(screenshot)}
                title={screenshot.url}
              >
                {screenshot.url 
                  ? (screenshot.url.length > 50 ? screenshot.url.substring(0, 50) + '...' : screenshot.url)
                  : 'No URL'
                }
              </code>
            </td>
            <td className="text-muted">
              <div className="small">
                {hasSourceCreatedAt(screenshot) ? (
                  <div>
                    <strong>Source captured:</strong> {formatScreenshotDate(getRawSourceCreatedAt(screenshot))}
                  </div>
                ) : formatScreenshotDate(getFirstCaptureDate(screenshot)) !== 'N/A' ? (
                  <>
                    <div>
                      <strong>First:</strong> {formatScreenshotDate(getFirstCaptureDate(screenshot))}
                    </div>
                    {hasMultipleCaptures(screenshot) && getLastCaptureDate(screenshot) !== getFirstCaptureDate(screenshot) && formatScreenshotDate(getLastCaptureDate(screenshot)) !== 'N/A' && (
                      <div>
                        <strong>Last:</strong> {formatScreenshotDate(getLastCaptureDate(screenshot))}
                      </div>
                    )}
                  </>
                ) : (
                  <span className="text-muted">-</span>
                )}
              </div>
            </td>
            <td>
              {formatFileSize(screenshot.file_size)}
            </td>
            <td>
              {screenshot.program_name ? (
                <Badge bg="primary">{screenshot.program_name}</Badge>
              ) : (
                <span className="text-muted">-</span>
              )}
            </td>
            <td>
              {(screenshot.source || screenshot.metadata?.source) ? (
                <Badge bg="secondary">{screenshot.source || screenshot.metadata?.source}</Badge>
              ) : (
                <span className="text-muted">-</span>
              )}
            </td>
            <td>
              {hasMultipleCaptures(screenshot) ? (
                <Badge bg="info" title={`Captured ${getCaptureCount(screenshot)} times`}>
                  {getCaptureCount(screenshot)}x
                </Badge>
              ) : (
                <Badge bg="secondary" title="Single capture">1x</Badge>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <h1>🔤 Typosquat Screenshots</h1>
          <p className="text-muted">Browse and manage typosquat screenshots captured during reconnaissance</p>
        </Col>
      </Row>

      <Row className="mb-4">
        <Col>
          <Accordion>
            <Accordion.Item eventKey="0">
              <Accordion.Header>🔍 Search & Filter Options</Accordion.Header>
              <Accordion.Body>
                <Row>
                  <Col md={6}>
                    <Form.Group className="mb-3">
                      <Form.Label>Search URL</Form.Label>
                      <InputGroup>
                        <Form.Control
                          type="text"
                          placeholder="Partial URL search (regex)..."
                          value={searchFilter}
                          onChange={(e) => setSearchFilter(e.target.value)}
                        />
                      </InputGroup>
                    </Form.Group>
                  </Col>
                  <Col md={6}>
                    <Form.Group className="mb-3">
                      <Form.Label>Filter by URL</Form.Label>
                      <InputGroup>
                        <Form.Control
                          type="text"
                          placeholder="Exact URL match..."
                          value={urlFilter}
                          onChange={(e) => setUrlFilter(e.target.value)}
                        />
                      </InputGroup>
                    </Form.Group>
                  </Col>
                </Row>
                <Row>
                  <Col md={6}>
                    <Form.Group className="mb-3">
                      <Form.Check
                        type="checkbox"
                        id="exclude-parked-domains"
                        label="Hide parked domains"
                        checked={excludeParkedDomains}
                        onChange={(e) => {
                          setExcludeParkedDomains(e.target.checked);
                          setCurrentPage(1);
                        }}
                      />
                    </Form.Group>
                  </Col>
                </Row>
                <Row>
                  <Col md={12} className="d-flex justify-content-end">
                    <Button variant="outline-secondary" onClick={clearFilters} className="me-2">
                      Clear
                    </Button>
                  </Col>
                </Row>
              </Accordion.Body>
            </Accordion.Item>
          </Accordion>
        </Col>
      </Row>

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">Typosquat Screenshots</h5>
              <div className="d-flex align-items-center">
                <Badge bg="secondary" className="me-3">Total: {totalItems}</Badge>
                <Badge bg="info" className="me-3">Page: {currentPage} of {totalPages}</Badge>
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
                <Button
                  variant={viewMode === 'grid' ? 'primary' : 'outline-primary'}
                  size="sm"
                  className="me-2"
                  onClick={() => setViewMode('grid')}
                >
                  <i className="fas fa-th"></i>
                </Button>
                <Button
                  variant={viewMode === 'table' ? 'primary' : 'outline-primary'}
                  size="sm"
                  onClick={() => setViewMode('table')}
                >
                  <i className="fas fa-list"></i>
                </Button>
              </div>
            </Card.Header>
            <Card.Body className={viewMode === 'table' ? 'p-0' : ''}>
              {loading ? (
                <div className="text-center p-4">
                  <Spinner animation="border" role="status">
                    <span className="visually-hidden">Loading...</span>
                  </Spinner>
                  <p className="mt-2">Loading typosquat screenshots...</p>
                </div>
              ) : error ? (
                <div className="p-4">
                  <p className="text-danger">{error}</p>
                </div>
              ) : screenshots.length === 0 ? (
                <div className="p-4 text-center">
                  <p className="text-muted">No typosquat screenshots found matching the current filters.</p>
                </div>
              ) : (
                viewMode === 'grid' ? renderGridView() : renderTableView()
              )}
            </Card.Body>
            {!loading && !error && totalPages > 1 && (
              <Card.Footer>
                <div className="text-center mb-3">
                  <div className="text-muted">
                    Showing {screenshots.length} of {totalItems} items
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
                  {renderPagination()}
                </div>
              </Card.Footer>
            )}
          </Card>
        </Col>
      </Row>

      {/* Screenshot Modal */}
      <Modal show={showModal} onHide={() => setShowModal(false)} size="xl" centered>
        <Modal.Header closeButton>
          <Modal.Title>Typosquat Screenshot Details</Modal.Title>
        </Modal.Header>
        <Modal.Body style={{ maxHeight: '80vh', overflowY: 'auto' }}>
          {selectedScreenshot && (
            <div>
              <div className="text-center mb-3" style={{ position: 'relative' }}>
                <div 
                  style={{ 
                    maxHeight: '600px', 
                    overflow: 'auto',
                    border: '1px solid #dee2e6',
                    borderRadius: '8px',
                    backgroundColor: '#f8f9fa',
                    position: 'relative'
                  }}
                >
                  <Image
                    src={getScreenshotUrl(selectedScreenshot)}
                    alt={`Typosquat screenshot of ${selectedScreenshot.url || 'unknown URL'}`}
                    style={{ 
                      width: '100%', 
                      height: 'auto',
                      cursor: 'pointer'
                    }}
                    onClick={() => {
                      setFullscreenImageError(false);
                      setShowFullscreen(true);
                    }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                      e.target.nextSibling.style.display = 'block';
                    }}
                  />
                  <div style={{ display: 'none' }} className="text-muted p-4">
                    <i className="fas fa-image" style={{ fontSize: '3rem' }}></i>
                    <p>Image could not be loaded</p>
                  </div>
                  
                  {/* Fullscreen button overlay */}
                  <Button
                    variant="dark"
                    size="sm"
                    style={{
                      position: 'absolute',
                      top: '10px',
                      right: '10px',
                      opacity: 0.8,
                      zIndex: 2
                    }}
                    onClick={() => {
                      setFullscreenImageError(false);
                      setShowFullscreen(true);
                    }}
                    title="View fullscreen"
                  >
                    <i className="fas fa-expand"></i>
                  </Button>
                </div>
                <div className="mt-2 text-muted small">
                  <i className="fas fa-search-plus me-1"></i>
                  Click image, fullscreen button, or press 'F' to view at full size
                </div>
              </div>
              <Table striped bordered>
                <tbody>
                  <tr>
                    <td><strong>URL:</strong></td>
                    <td>
                      <code 
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleUrlClick(selectedScreenshot)}
                      >
                        {selectedScreenshot.url || 'No URL'}
                      </code>
                    </td>
                  </tr>
                  {selectedScreenshot.typosquat_type && (
                    <tr>
                      <td><strong>Typosquat Type:</strong></td>
                      <td>
                        <Badge bg={getTyposquatTypeBadge(selectedScreenshot.typosquat_type)}>
                          {selectedScreenshot.typosquat_type}
                        </Badge>
                      </td>
                    </tr>
                  )}
                  {!hasSourceCreatedAt(selectedScreenshot) && (
                  <tr>
                    <td><strong>Upload Date:</strong></td>
                    <td>{formatScreenshotDate(selectedScreenshot.created_at)}</td>
                  </tr>
                  )}
                  <tr>
                    <td><strong>File Size:</strong></td>
                    <td>{formatFileSize(selectedScreenshot.file_size)}</td>
                  </tr>
                  {selectedScreenshot.program_name && (
                    <tr>
                      <td><strong>Program:</strong></td>
                      <td><Badge bg="primary">{selectedScreenshot.program_name}</Badge></td>
                    </tr>
                  )}
                  {selectedScreenshot.workflow_id && (
                    <tr>
                      <td><strong>Workflow ID:</strong></td>
                      <td><code>{selectedScreenshot.workflow_id}</code></td>
                    </tr>
                  )}
                  <tr>
                    <td><strong>Capture Count:</strong></td>
                    <td>
                      <Badge bg={hasMultipleCaptures(selectedScreenshot) ? "info" : "secondary"}>{getCaptureCount(selectedScreenshot)}x</Badge>
                    </td>
                  </tr>
                  {selectedScreenshot.image_hash && (
                    <tr>
                      <td><strong>Image Hash:</strong></td>
                      <td><code className="small">{selectedScreenshot.image_hash}</code></td>
                    </tr>
                  )}
                  {(selectedScreenshot.extracted_text || selectedScreenshot.metadata?.extracted_text) && (
                    <tr>
                      <td><strong>Extracted Text:</strong></td>
                      <td>
                        <div
                          className="small p-2 rounded"
                          style={{
                            maxHeight: '200px',
                            overflowY: 'auto',
                            backgroundColor: 'var(--bs-pre-bg)',
                            color: 'var(--bs-pre-color)',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word'
                          }}
                        >
                          {selectedScreenshot.extracted_text || selectedScreenshot.metadata?.extracted_text}
                        </div>
                      </td>
                    </tr>
                  )}
                  {(selectedScreenshot.source || selectedScreenshot.metadata?.source) && (
                    <tr>
                      <td><strong>Source:</strong></td>
                      <td>
                        <Badge bg="secondary">
                          {selectedScreenshot.source || selectedScreenshot.metadata?.source}
                        </Badge>
                      </td>
                    </tr>
                  )}
                  {(selectedScreenshot.source_created_at || selectedScreenshot.metadata?.source_created_at) && (
                    <tr>
                      <td><strong>Source Captured:</strong></td>
                      <td>{formatScreenshotDate(selectedScreenshot.source_created_at || selectedScreenshot.metadata?.source_created_at)}</td>
                    </tr>
                  )}
                  {!hasSourceCreatedAt(selectedScreenshot) && (
                  <tr>
                    <td><strong>Captured:</strong></td>
                    <td>
                      {hasMultipleCaptures(selectedScreenshot) && selectedScreenshot.capture_timestamps && selectedScreenshot.capture_timestamps.length > 1 ? (
                        <div className="small" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                          {selectedScreenshot.capture_timestamps.map((timestamp, idx) => (
                            <div key={idx} className="text-muted mb-1">
                              <Badge bg={idx === 0 ? "success" : "info"} className="me-2 small">
                                {idx + 1}
                              </Badge>
                              {formatScreenshotDate(timestamp)}
                              {idx === 0 && <span className="ms-2 small text-success">(First)</span>}
                              {idx === selectedScreenshot.capture_timestamps.length - 1 && idx > 0 && (
                                <span className="ms-2 small text-warning">(Latest)</span>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : hasMultipleCaptures(selectedScreenshot) && selectedScreenshot.last_captured_at ? (
                        <div className="small" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                          <div className="text-muted mb-1">
                            <Badge bg="success" className="me-2 small">1</Badge>
                            {formatScreenshotDate(selectedScreenshot.created_at)}
                            <span className="ms-2 small text-success">(First capture)</span>
                          </div>
                          <div className="text-muted mb-1">
                            <Badge bg="info" className="me-2 small">2</Badge>
                            {formatScreenshotDate(selectedScreenshot.last_captured_at)}
                            <span className="ms-2 small text-warning">(Latest capture)</span>
                          </div>
                        </div>
                      ) : (
                        <div className="text-muted">
                          <Badge bg="success" className="me-2 small">1</Badge>
                          {formatScreenshotDate(getFirstCaptureDate(selectedScreenshot))}
                          <span className="ms-2 small text-success">(Single capture)</span>
                        </div>
                      )}
                    </td>
                  </tr>
                  )}
                </tbody>
              </Table>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowModal(false)}>
            Close
          </Button>
          {selectedScreenshot && (
            <Button 
              variant="primary" 
              href={getScreenshotUrl(selectedScreenshot)} 
              download
            >
              <i className="fas fa-download"></i> Download
            </Button>
          )}
        </Modal.Footer>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Typosquat Screenshots</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected typosquat screenshot(s)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Typosquat Screenshot(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Fullscreen Modal */}
      <Modal 
        show={showFullscreen} 
        onHide={() => setShowFullscreen(false)} 
        fullscreen={true}
        className="fullscreen-modal"
      >
        <Modal.Header closeButton className="bg-dark text-white">
          <Modal.Title>
            <i className="fas fa-expand me-2"></i>
            Fullscreen View
          </Modal.Title>
        </Modal.Header>
        <Modal.Body 
          className="p-0 d-flex align-items-center justify-content-center bg-dark"
          style={{ minHeight: '90vh' }}
        >
          {selectedScreenshot && (
            <div className="w-100 h-100 d-flex align-items-center justify-content-center">
              {!fullscreenImageError ? (
                <Image
                  src={getScreenshotUrl(selectedScreenshot)}
                  alt={`Typosquat screenshot of ${selectedScreenshot.url || 'unknown URL'}`}
                  style={{ 
                    maxWidth: '100%', 
                    maxHeight: '90vh',
                    objectFit: 'contain'
                  }}
                  onError={() => setFullscreenImageError(true)}
                />
              ) : (
                <div className="text-white d-flex flex-column align-items-center justify-content-center">
                  <i className="fas fa-image" style={{ fontSize: '5rem' }}></i>
                  <p className="mt-3">Image could not be loaded</p>
                </div>
              )}
            </div>
          )}
        </Modal.Body>
        <Modal.Footer className="bg-dark border-top-0">
          <div className="d-flex justify-content-between w-100 align-items-center">
            <div className="text-white">
              {selectedScreenshot && (
                <small>
                  <i className="fas fa-link me-1"></i>
                  {selectedScreenshot.url || 'No URL'}
                </small>
              )}
            </div>
            <div>
              <Button variant="outline-light" onClick={() => setShowFullscreen(false)} className="me-2">
                <i className="fas fa-compress me-1"></i>
                Exit Fullscreen
              </Button>
              {selectedScreenshot && (
                <Button 
                  variant="primary" 
                  href={getScreenshotUrl(selectedScreenshot)} 
                  download
                >
                  <i className="fas fa-download me-1"></i>
                  Download
                </Button>
              )}
            </div>
          </div>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default TyposquatScreenshots;
