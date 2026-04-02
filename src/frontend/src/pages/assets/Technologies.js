import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Container, Row, Col, Card, Badge, Pagination, Form, Button, Spinner, Alert, OverlayTrigger, Popover, Accordion } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';
import { urlAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function Technologies() {
  usePageTitle(formatPageTitle('Technologies'));
  const navigate = useNavigate();
  const { selectedProgram } = useProgramFilter();
  const [technologies, setTechnologies] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({
    total_items: 0,
    total_pages: 0,
    current_page: 1,
    page_size: 25,
    has_next: false,
    has_prev: false
  });
  const isInitialMount = useRef(true);
  
  // Helper function to safely get saved filters
  const getSavedFilters = () => {
    try {
      const saved = localStorage.getItem('technologies-filters');
      return saved ? JSON.parse(saved) : {};
    } catch (error) {
      console.warn('Error parsing saved filters:', error);
      return {};
    }
  };

  const [searchFilter, setSearchFilter] = useState(() => {
    const saved = getSavedFilters();
    return saved.searchFilter || '';
  });
  const [sortBy, setSortBy] = useState(() => {
    const saved = getSavedFilters();
    return saved.sortBy || 'count';
  });
  const [sortOrder, setSortOrder] = useState(() => {
    const saved = getSavedFilters();
    return saved.sortOrder || 'desc';
  });
  const [paginationState, setPaginationState] = useState({});
  const [pageSize, setPageSize] = useState(() => {
    const saved = getSavedFilters();
    return saved.pageSize || 25;
  });

  const fetchTechnologies = useCallback(async (page = 1, size = null, search = null, sort = null, order = null) => {
    try {
      setLoading(true);
      setError(null);
      
      // Use provided parameters or current state values
      const requestSize = size || pageSize;
      const requestSearch = search !== null ? search : searchFilter;
      const requestSort = sort || sortBy;
      const requestOrder = order || sortOrder;
      
      // Build query parameters for the API call
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: requestSize.toString(),
      });
      
      if (selectedProgram) {
        params.append('program_name', selectedProgram);
      }
      
      if (requestSearch) {
        params.append('search', requestSearch);
      }
      
      if (requestSort) {
        params.append('sort_by', requestSort);
      }
      
      if (requestOrder) {
        params.append('sort_order', requestOrder);
      }
      
      // Fetch technologies summary from the API with search and sort parameters
      const response = await urlAPI.getTechnologiesSummary(
        selectedProgram || null,
        page,
        requestSize,
        requestSearch || undefined,
        requestSort || undefined,
        requestOrder || undefined
      );
      
      if (!response || response.status !== 'success') {
        throw new Error('Failed to fetch technologies data');
      }
      
      const technologiesData = response.items || [];
      
      // Convert to the format expected by the rest of the component
      const techMap = {};
      technologiesData.forEach(tech => {
        techMap[tech.name] = {
          name: tech.name,
          count: tech.count,
          total_urls: tech.total_urls,
          websites: tech.websites || []
        };
      });
      
      setTechnologies(techMap);
      setPagination(response.pagination || {
        total_items: 0,
        total_pages: 0,
        current_page: page,
        page_size: requestSize,
        has_next: false,
        has_prev: false
      });
      
    } catch (err) {
      if (err.message !== 'Operation cancelled') {
        console.error('Error fetching technologies:', err);
        setError('Failed to fetch technologies: ' + err.message);
        setTechnologies({});
      }
    } finally {
      setLoading(false);
    }
  }, [selectedProgram, pageSize, searchFilter, sortBy, sortOrder]);
  
  const handlePageChange = (newPage) => {
    fetchTechnologies(newPage);
  };
  
  const handlePageSizeChange = (newPageSize) => {
    setPageSize(newPageSize);
    // Fetch with new page size immediately
    fetchTechnologies(1, newPageSize);
  };

  // Save filters to localStorage whenever they change
  useEffect(() => {
    try {
      const filtersToSave = {
        searchFilter,
        sortBy,
        sortOrder,
        pageSize
      };
      localStorage.setItem('technologies-filters', JSON.stringify(filtersToSave));
    } catch (error) {
      console.warn('Error saving filters to localStorage:', error);
    }
  }, [searchFilter, sortBy, sortOrder, pageSize]);

  // Fetch technologies when program filter changes or on initial mount
  useEffect(() => {
    fetchTechnologies(1);
    isInitialMount.current = false;
  }, [selectedProgram]); // eslint-disable-line react-hooks/exhaustive-deps

  // Refetch when search filter changes (with debounce, skip on initial mount)
  useEffect(() => {
    if (isInitialMount.current) {
      return; // Skip on initial mount - let the selectedProgram effect handle it
    }
    
    const timeoutId = setTimeout(() => {
      fetchTechnologies(1);
    }, 800); // Debounce search input - wait for user to finish typing

    return () => clearTimeout(timeoutId);
  }, [searchFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  // Refetch immediately when sort options change (no debounce needed, skip on initial mount)
  useEffect(() => {
    if (isInitialMount.current) {
      return; // Skip on initial mount
    }
    
    fetchTechnologies(1);
  }, [sortBy, sortOrder]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleWebsiteClick = (urlId) => {
    // Navigate to URL details page
    navigate(`/assets/urls/details?id=${urlId}`);
  };

  const getSortedTechnologies = () => {
    // Technologies are already filtered and sorted by the API
    // Just return them as-is
    return Object.values(technologies);
  };

  const clearFilters = () => {
    setSearchFilter('');
    setSortBy('count');
    setSortOrder('desc');
    // Clear saved filters from localStorage
    localStorage.removeItem('technologies-filters');
  };

  const handleSort = (column) => {
    if (sortBy === column) {
      // Toggle sort order if clicking the same column
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      // Set new column and default to descending for count, ascending for name
      setSortBy(column);
      setSortOrder(column === 'count' ? 'desc' : 'asc');
    }
  };

  const getSortIcon = (column) => {
    if (sortBy !== column) {
      return '⇅'; // Both arrows for unsorted
    }
    return sortOrder === 'asc' ? '↑' : '↓';
  };

  // Simple header popover filter for search (no per-row table here)
  const HeaderFilterPopover = ({ id, isActive, ariaLabel, children }) => {
    const buttonVariant = isActive ? 'primary' : 'outline-secondary';
    const overlay = (
      <Popover id={id} style={{ minWidth: 260 }} onClick={(e) => e.stopPropagation()}>
        <Popover.Body onClick={(e) => e.stopPropagation()}>
          {children}
        </Popover.Body>
      </Popover>
    );
    return (
      <OverlayTrigger trigger="click" rootClose placement="bottom" overlay={overlay}>
        <Button size="sm" variant={buttonVariant} aria-label={ariaLabel} onClick={(e) => e.stopPropagation()}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style={{ marginRight: 4 }}>
            <path d="M1.5 1.5a.5.5 0 0 0 0 1h13a.5.5 0 0 0 .4-.8L10 9.2V13a.5.5 0 0 1-.276.447l-2 1A.5.5 0 0 1 7 14V9.2L1.1 1.7a.5.5 0 0 0-.4-.2z" />
          </svg>
          {/* <span style={{ fontSize: '0.8rem' }}>Filter</span> */}
        </Button>
      </OverlayTrigger>
    );
  };

  const WEBSITES_PER_PAGE = 10;

  const getPaginatedWebsites = (tech) => {
    const currentPage = paginationState[tech.name] || 1;
    const startIndex = (currentPage - 1) * WEBSITES_PER_PAGE;
    const endIndex = startIndex + WEBSITES_PER_PAGE;
    return tech.websites.slice(startIndex, endIndex);
  };

  const getTotalPages = (tech) => {
    return Math.ceil(tech.websites.length / WEBSITES_PER_PAGE);
  };

  const setTechPage = (techName, page) => {
    setPaginationState(prev => ({
      ...prev,
      [techName]: page
    }));
  };

  const renderPagination = (tech) => {
    const totalPages = getTotalPages(tech);
    const currentPage = paginationState[tech.name] || 1;
    
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
          onClick={() => setTechPage(tech.name, i)}
        >
          {i}
        </Pagination.Item>
      );
    }

    return (
      <div className="d-flex justify-content-center mt-3">
        <Pagination size="sm">
          <Pagination.First 
            onClick={() => setTechPage(tech.name, 1)} 
            disabled={currentPage === 1} 
          />
          <Pagination.Prev 
            onClick={() => setTechPage(tech.name, currentPage - 1)} 
            disabled={currentPage === 1} 
          />
          {startPage > 1 && <Pagination.Ellipsis />}
          {pages}
          {endPage < totalPages && <Pagination.Ellipsis />}
          <Pagination.Next 
            onClick={() => setTechPage(tech.name, currentPage + 1)} 
            disabled={currentPage === totalPages} 
          />
          <Pagination.Last 
            onClick={() => setTechPage(tech.name, totalPages)} 
            disabled={currentPage === totalPages} 
          />
        </Pagination>
      </div>
    );
  };

  const totalTechnologies = pagination.total_items || Object.keys(technologies).length;
  const totalWebsites = Object.values(technologies).reduce((sum, tech) => sum + tech.count, 0);
  const filteredTechnologies = getSortedTechnologies();

  if (loading) {
    return (
      <Container fluid className="p-4">
        <Row>
          <Col className="text-center">
            <Card className="mx-auto" style={{ maxWidth: '500px' }}>
              <Card.Body>
                <h5>🔄 Loading Technologies</h5>
                <Spinner animation="border" role="status" className="mb-3">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
                <p>Fetching technologies data from server...</p>
                <small className="text-muted">
                  This should only take a moment.
                </small>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Container>
    );
  }

  if (error) {
    return (
      <Container fluid className="p-4">
        <Alert variant="danger">
          <Alert.Heading>❌ Error Loading Technologies</Alert.Heading>
          <p>{error}</p>
          <hr />
          <Button variant="outline-primary" onClick={fetchTechnologies}>
            🔄 Try Again
          </Button>
        </Alert>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <div className="d-flex justify-content-between align-items-start">
            <div>
              <h1>⚙️ Technologies</h1>
              <p className="text-muted">
                Technologies detected across all websites ({totalTechnologies} unique technologies across {totalWebsites} website instances)
                {selectedProgram && (
                  <><br />Filtered by program: "{selectedProgram}"</>
                )}
              </p>
            </div>
            <div>
              <Button 
                variant="outline-primary" 
                size="sm" 
                onClick={fetchTechnologies}
                disabled={loading}
              >
                🔄 Refresh
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {/* Technologies List */}
      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">Technology Assets</h5>
              <div className="d-flex align-items-center gap-2">
                <Badge bg="secondary">
                  Showing {filteredTechnologies.length} of {pagination.total_items} technologies
                </Badge>
                <Button variant="link" size="sm" className="p-0" onClick={clearFilters}>Reset filters</Button>
              </div>
            </Card.Header>
            <Card.Body className="p-0">
              {/* Sortable Column Headers */}
              <div className="d-flex justify-content-between align-items-center px-3 py-2 bg-light border-bottom">
                <div 
                  style={{ 
                    flex: 1, 
                    cursor: 'pointer', 
                    userSelect: 'none',
                    transition: 'color 0.2s',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}
                  onClick={(e) => {
                    // Don't trigger sort if clicking on the filter button
                    if (e.target.closest('button')) return;
                    handleSort('name');
                  }}
                  onMouseEnter={(e) => {
                    const span = e.currentTarget.querySelector('span');
                    if (span) span.style.color = '#0d6efd';
                  }}
                  onMouseLeave={(e) => {
                    const span = e.currentTarget.querySelector('span');
                    if (span) span.style.color = '';
                  }}
                  className="fw-bold"
                >
                  <span>Technology Name {getSortIcon('name')}</span>
                  <HeaderFilterPopover id="tech-filter" ariaLabel="Filter technologies" isActive={!!searchFilter}>
                    <div>
                      <Form.Group>
                        <Form.Label className="mb-1">Search Technologies</Form.Label>
                        <Form.Control
                          type="text"
                          placeholder="e.g., jquery, bootstrap, react"
                          value={searchFilter}
                          onChange={(e) => setSearchFilter(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') fetchTechnologies(1); }}
                        />
                      </Form.Group>
                      <div className="d-flex justify-content-end gap-2 mt-2">
                        <Button size="sm" variant="secondary" onClick={() => { setSearchFilter(''); fetchTechnologies(1); }}>Clear</Button>
                        <Button size="sm" variant="primary" onClick={() => fetchTechnologies(1)}>Apply</Button>
                      </div>
                    </div>
                  </HeaderFilterPopover>
                </div>
                <div 
                  style={{ 
                    width: '200px', 
                    cursor: 'pointer', 
                    userSelect: 'none', 
                    textAlign: 'right',
                    transition: 'color 0.2s'
                  }}
                  onClick={() => handleSort('count')}
                  onMouseEnter={(e) => e.currentTarget.style.color = '#0d6efd'}
                  onMouseLeave={(e) => e.currentTarget.style.color = ''}
                  className="fw-bold"
                >
                  Websites {getSortIcon('count')}
                </div>
              </div>
              
              {filteredTechnologies.length === 0 ? (
                <div className="text-center p-4">
                  <Alert variant="info" className="mb-0">
                    No technologies found matching your search criteria.
                  </Alert>
                </div>
              ) : (
                <Accordion>
                  {filteredTechnologies.map((tech, index) => (
                    <Accordion.Item eventKey={index.toString()} key={tech.name}>
                      <Accordion.Header>
                        <div className="d-flex justify-content-between align-items-center w-100 me-3">
                          <div>
                            <strong>{tech.name}</strong>
                          </div>
                          <div>
                            <Badge bg="primary" className="me-2">
                              {tech.count} website{tech.count !== 1 ? 's' : ''}
                            </Badge>
                          </div>
                        </div>
                      </Accordion.Header>
                      <Accordion.Body>
                        <div className="d-flex justify-content-between align-items-center mb-3">
                          <h6 className="mb-0">Websites using {tech.name}:</h6>
                          <small className="text-muted">
                            Showing {getPaginatedWebsites(tech).length} of {tech.websites.length} websites
                          </small>
                        </div>
                        <ul className="list-unstyled">
                          {getPaginatedWebsites(tech).map((website, websiteIndex) => (
                            <li key={websiteIndex} className="mb-2">
                              <Button
                                variant="link"
                                className="p-0 text-start text-decoration-none"
                                onClick={() => handleWebsiteClick(website.id)}
                              >
                                <Badge 
                                  bg={website.scheme === 'https' ? 'success' : 'warning'}
                                  className="me-2"
                                >
                                  {website.scheme.toUpperCase()}
                                </Badge>
                                {website.rootWebsite}
                              </Button>
                              <small className="text-muted ms-2">
                                ({website.technologies.length} technology{website.technologies.length !== 1 ? 'ies' : ''})
                              </small>
                            </li>
                          ))}
                        </ul>
                        {renderPagination(tech)}
                      </Accordion.Body>
                    </Accordion.Item>
                  ))}
                </Accordion>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Main Pagination Controls for Technologies List */}
      {pagination.total_pages > 1 && (
        <Row className="mt-4">
          <Col>
            {/* Info text */}
            <div className="text-center text-muted mb-2">
              Showing {filteredTechnologies.length} of {pagination.total_items} technologies
              (Page {pagination.current_page} of {pagination.total_pages})
            </div>
            
            {/* Centered pagination controls */}
            <div className="d-flex justify-content-center align-items-center gap-3">
              <Form.Select
                size="sm"
                value={pagination.page_size}
                onChange={(e) => handlePageSizeChange(parseInt(e.target.value))}
                style={{ width: 'auto' }}
              >
                <option value={10}>10 per page</option>
                <option value={25}>25 per page</option>
                <option value={50}>50 per page</option>
                <option value={100}>100 per page</option>
              </Form.Select>
              
              <Pagination className="mb-0">
                <Pagination.First 
                  onClick={() => handlePageChange(1)} 
                  disabled={!pagination.has_prev}
                />
                <Pagination.Prev 
                  onClick={() => handlePageChange(pagination.current_page - 1)} 
                  disabled={!pagination.has_prev}
                />
                
                {/* Show page numbers */}
                {(() => {
                  const pages = [];
                  const maxVisible = 5;
                  let startPage = Math.max(1, pagination.current_page - Math.floor(maxVisible / 2));
                  let endPage = Math.min(pagination.total_pages, startPage + maxVisible - 1);
                  
                  if (endPage - startPage < maxVisible - 1) {
                    startPage = Math.max(1, endPage - maxVisible + 1);
                  }
                  
                  if (startPage > 1) {
                    pages.push(<Pagination.Ellipsis key="start-ellipsis" disabled />);
                  }
                  
                  for (let i = startPage; i <= endPage; i++) {
                    pages.push(
                      <Pagination.Item
                        key={i}
                        active={i === pagination.current_page}
                        onClick={() => handlePageChange(i)}
                      >
                        {i}
                      </Pagination.Item>
                    );
                  }
                  
                  if (endPage < pagination.total_pages) {
                    pages.push(<Pagination.Ellipsis key="end-ellipsis" disabled />);
                  }
                  
                  return pages;
                })()}
                
                <Pagination.Next 
                  onClick={() => handlePageChange(pagination.current_page + 1)} 
                  disabled={!pagination.has_next}
                />
                <Pagination.Last 
                  onClick={() => handlePageChange(pagination.total_pages)} 
                  disabled={!pagination.has_next}
                />
              </Pagination>
            </div>
          </Col>
        </Row>
      )}
    </Container>
  );
}

export default Technologies; 