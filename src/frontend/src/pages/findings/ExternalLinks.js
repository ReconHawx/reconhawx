import React, { useState, useEffect, useContext, useCallback } from 'react';
import { Container, Card, Form, Col, Button, Table, Collapse, Row, Modal, Spinner, Pagination, OverlayTrigger, Popover } from 'react-bootstrap';
import { ProgramFilterContext } from '../../contexts/ProgramFilterContext';
import api from '../../services/api';
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

function ExternalLinks() {
  usePageTitle(formatPageTitle('External Links'));
  const [externalLinksData, setExternalLinksData] = useState({});
  const [rootSitesList, setRootSitesList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedGroups, setExpandedGroups] = useState({});
  
  // Export state
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const [exporting, setExporting] = useState(false);
  const [customFilename, setCustomFilename] = useState('');
  
  // Filter states
  const [linkSearch, setLinkSearch] = useState('');
  const [debouncedLinkSearch, setDebouncedLinkSearch] = useState('');
  const [linkNegative, setLinkNegative] = useState(false);
  const [selectedRoot, setSelectedRoot] = useState('');
  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);
  const [pagination, setPagination] = useState(null);
  const [linkUrlFilter, setLinkUrlFilter] = useState('');
  
  const { selectedProgram } = useContext(ProgramFilterContext);

  // Column filter popover utilities
  const ColumnFilterPopover = ({ id, isActive, ariaLabel, placement = 'bottom', children }) => {
    const buttonVariant = isActive ? 'primary' : 'outline-secondary';
    const overlay = (
      <Popover id={id} style={{ minWidth: 300, maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
        <Popover.Body onClick={(e) => e.stopPropagation()}>
          {children}
        </Popover.Body>
      </Popover>
    );
    return (
      <OverlayTrigger trigger="click" rootClose placement={placement} overlay={overlay}>
        <Button size="sm" variant={buttonVariant} aria-label={ariaLabel} onClick={(e) => e.stopPropagation()}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M1.5 1.5a.5.5 0 0 0 0 1h13a.5.5 0 0 0 .4-.8L10 9.2V13a.5.5 0 0 1-.276.447l-2 1A.5.5 0 0 1 7 14V9.2L1.1 1.7a.5.5 0 0 0-.4-.2z" />
          </svg>
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

  // Debounce the search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedLinkSearch(linkSearch);
    }, 300);

    return () => clearTimeout(timer);
  }, [linkSearch]);

  const fetchExternalLinks = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await api.findings.externalLinks.getExternalLinks(
        selectedProgram || '',
        debouncedLinkSearch,
        linkNegative,
        selectedRoot,
        currentPage,
        pageSize
      );

      if (response.dest_grouped_links) {
        setExternalLinksData(response.dest_grouped_links);
      }

      if (response.root_sites_list) {
        setRootSitesList(response.root_sites_list);
      }

      if (response.pagination) {
        setPagination(response.pagination);
      } else {
        // Fallback for backward compatibility when pagination is not provided
        setPagination(null);
      }
    } catch (err) {
      console.error('Error fetching external links:', err);
      setError('Failed to load external links data');
    } finally {
      setLoading(false);
    }
  }, [selectedProgram, debouncedLinkSearch, linkNegative, selectedRoot, currentPage, pageSize]);

  useEffect(() => {
    fetchExternalLinks();
  }, [fetchExternalLinks]);

  // Reset current page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedProgram, debouncedLinkSearch, linkNegative, selectedRoot]);

  // Load Font Awesome CSS
  useEffect(() => {
    loadFontAwesome();
  }, []);

  const toggleGroup = (groupIndex) => {
    setExpandedGroups(prev => ({
      ...prev,
      [groupIndex]: !prev[groupIndex]
    }));
  };

  const truncateUrl = (url, maxLength = 80) => {
    if (!url) return '';
    return url.length > maxLength ? url.substring(0, maxLength) + '...' : url;
  };

  const handleExport = () => {
    setShowExportModal(true);
  };

  const handleExportConfirm = async () => {
    try {
      setExporting(true);
      
      let exportData;
      let fileExtension;
      let mimeType;
      
      if (exportFormat === 'txt') {
        // Plain text export - only destination URLs
        const allLinks = [];
        Object.values(externalLinksData).forEach(links => {
          links.forEach(entry => {
            allLinks.push(entry.destination);
          });
        });
        exportData = allLinks.join('\n');
        fileExtension = 'txt';
        mimeType = 'text/plain';
      } else if (exportFormat === 'csv') {
        // CSV export with destination and sources
        const headers = 'Destination,Source Pages';
        const rows = [];
        Object.values(externalLinksData).forEach(links => {
          links.forEach(entry => {
            const destination = entry.destination.includes(',') ? `"${entry.destination.replace(/"/g, '""')}"` : entry.destination;
            const sources = entry.sources.join('; ');
            const sourcesEscaped = sources.includes(',') ? `"${sources.replace(/"/g, '""')}"` : sources;
            rows.push(`${destination},${sourcesEscaped}`);
          });
        });
        exportData = [headers, ...rows].join('\n');
        fileExtension = 'csv';
        mimeType = 'text/csv';
      } else {
        // JSON export with metadata
        exportData = JSON.stringify({
          filters: {
            program: selectedProgram || '',
            linkSearch: debouncedLinkSearch,
            linkNegative,
            selectedRoot
          },
          rootSitesList,
          externalLinksData,
          exportDate: new Date().toISOString(),
          totalGroups: Object.keys(externalLinksData).length,
          totalLinks: Object.values(externalLinksData).reduce((sum, links) => sum + links.length, 0)
        }, null, 2);
        fileExtension = 'json';
        mimeType = 'application/json';
      }
      
      // Create and download the file
      const dataUri = `data:${mimeType};charset=utf-8,${encodeURIComponent(exportData)}`;
      const exportFileDefaultName = customFilename.trim() 
        ? `${customFilename.trim()}.${fileExtension}` 
        : `external_links_export_${new Date().toISOString().split('T')[0]}.${fileExtension}`;
      
      const linkElement = document.createElement('a');
      linkElement.setAttribute('href', dataUri);
      linkElement.setAttribute('download', exportFileDefaultName);
      linkElement.click();
      
      setShowExportModal(false);
      
    } catch (err) {
      console.error('Error exporting external links:', err);
      alert('Failed to export external links: ' + err.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <h1>🔗 External Links</h1>
          <p className="text-muted">External links discovered during reconnaissance</p>
        </Col>
      </Row>

      {/* Filters moved to column header popover */}

      {/* Results */}
      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center ms-auto">
                <Button variant="link" size="sm" className="me-2 p-0" onClick={() => {
                  setLinkSearch('');
                  setDebouncedLinkSearch('');
                  setLinkNegative(false);
                  setSelectedRoot('');
                  setCurrentPage(1);
                  setLinkUrlFilter('');
                }}>Reset filters</Button>
                {Object.keys(externalLinksData).length > 0 && (
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={handleExport}
                    className="me-2"
                  >
                    <i className="bi bi-download"></i> Export
                  </Button>
                )}
                {loading && (
                  <div className="spinner-border spinner-border-sm" role="status">
                    <span className="visually-hidden">Loading...</span>
                  </div>
                )}
              </div>
            </Card.Header>
            <Card.Body className="p-0">
              {loading ? (
                <div className="text-center p-4">
                  <div className="spinner-border" role="status">
                    <span className="visually-hidden">Loading...</span>
                  </div>
                </div>
              ) : error ? (
                <div className="text-center p-4 text-danger">
                  {error}
                </div>
              ) : Object.keys(externalLinksData).length === 0 ? (
                <div className="text-center p-4">
                  <p className="text-muted mb-0">No external links found</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <Table hover className="mb-0">
                    <thead className="table-light">
                      <tr>
                        <th style={{ width: '35%' }}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Destination Website</span>
                            <ColumnFilterPopover id="filter-destination" ariaLabel="Filter external links" isActive={!!selectedRoot || !!debouncedLinkSearch || linkNegative}>
                              <div>
                                <Form.Group className="mb-3">
                                  <Form.Label className="mb-1">Root Website</Form.Label>
                                  <Form.Select value={selectedRoot} onChange={(e) => setSelectedRoot(e.target.value)}>
                                    <option value="">All Roots</option>
                                    {rootSitesList.map((root, index) => (
                                      <option key={index} value={root}>{truncateUrl(root, 60)}</option>
                                    ))}
                                  </Form.Select>
                                </Form.Group>
                                <InlineTextFilter
                                  label="Filter External Links"
                                  placeholder="Contains..."
                                  initialValue={linkSearch}
                                  onApply={(val) => setLinkSearch(val)}
                                  onClear={() => setLinkSearch('')}
                                />
                                <Form.Check
                                  type="checkbox"
                                  label="Exclude matches"
                                  className="mt-3"
                                  checked={linkNegative}
                                  onChange={(e) => setLinkNegative(e.target.checked)}
                                />
                              </div>
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th style={{ width: '10%' }}>
                          <div className="d-flex align-items-center gap-2">
                            <span>Links</span>
                            <ColumnFilterPopover id="filter-link-url" ariaLabel="Filter by link URL" isActive={!!linkUrlFilter}>
                              <InlineTextFilter
                                label="Filter by Link URL"
                                placeholder="e.g., google.com, facebook.com"
                                initialValue={linkUrlFilter}
                                onApply={(val) => setLinkUrlFilter(val)}
                                onClear={() => setLinkUrlFilter('')}
                              />
                            </ColumnFilterPopover>
                          </div>
                        </th>
                        <th style={{ width: '55%' }}>(Click row to expand details)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(externalLinksData)
                        .map(([destRoot, links], index) => {
                          // Filter links within each group based on linkUrlFilter
                          const filteredLinks = linkUrlFilter 
                            ? links.filter(entry => 
                                entry.destination?.toLowerCase().includes(linkUrlFilter.toLowerCase())
                              )
                            : links;
                          
                          // If all links are filtered out, don't show the group
                          if (filteredLinks.length === 0 && linkUrlFilter) return null;
                          
                          return (
                            <React.Fragment key={index}>
                              <tr
                                className="cursor-pointer"
                                onClick={() => toggleGroup(index)}
                                style={{ cursor: 'pointer' }}
                              >
                                <td>
                                  <i className={`fas fa-chevron-${expandedGroups[index] ? 'down' : 'right'} me-2`}></i>
                                  {destRoot}
                                </td>
                                <td>{filteredLinks.length}</td>
                                <td></td>
                              </tr>
                              <tr>
                                <td colSpan={3} className="p-0 border-0">
                                  <Collapse in={expandedGroups[index]}>
                                    <div>
                                      <Table className="mb-0">
                                        <thead>
                                          <tr className="bg-light">
                                            <th style={{ width: '40%' }}>Destination Link</th>
                                            <th style={{ width: '60%' }}>Found On (Source Pages)</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {filteredLinks.map((entry, linkIndex) => (
                                        <tr key={linkIndex}>
                                          <td>
                                            <a 
                                              href={entry.destination} 
                                              target="_blank" 
                                              rel="noopener noreferrer"
                                            >
                                              {truncateUrl(entry.destination, 100)}
                                            </a>
                                          </td>
                                          <td>
                                            {entry.sources.map((src, srcIndex) => (
                                              <React.Fragment key={srcIndex}>
                                                <a 
                                                  href={src} 
                                                  target="_blank" 
                                                  rel="noopener noreferrer"
                                                >
                                                  {truncateUrl(src, 80)}
                                                </a>
                                                {srcIndex < entry.sources.length - 1 && <br />}
                                              </React.Fragment>
                                            ))}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </Table>
                                </div>
                              </Collapse>
                            </td>
                          </tr>
                        </React.Fragment>
                          );
                        })
                        .filter(item => item !== null)}
                    </tbody>
                  </Table>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Pagination */}
      {!loading && !error && pagination && pagination.total_items > pagination.page_size && (
        <Row className="mt-4">
          <Col>
            <div className="text-center mb-3">
              <div className="text-muted">
                Showing {((pagination.current_page - 1) * pagination.page_size) + 1} to {Math.min(pagination.current_page * pagination.page_size, pagination.total_items)} of {pagination.total_items} groups
                (Page {pagination.current_page} of {pagination.total_pages})
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
                  onClick={() => setCurrentPage(1)}
                  disabled={pagination.current_page === 1}
                />
                <Pagination.Prev
                  onClick={() => setCurrentPage(currentPage - 1)}
                  disabled={pagination.current_page === 1}
                />
                {(() => {
                  const totalPages = pagination.total_pages;
                  const items = [];
                  const maxVisiblePages = 5;
                  let startPage = Math.max(1, pagination.current_page - Math.floor(maxVisiblePages / 2));
                  let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

                  if (endPage - startPage + 1 < maxVisiblePages) {
                    startPage = Math.max(1, endPage - maxVisiblePages + 1);
                  }

                  // First page
                  if (startPage > 1) {
                    items.push(
                      <Pagination.Item key={1} onClick={() => setCurrentPage(1)}>
                        1
                      </Pagination.Item>
                    );
                    if (startPage > 2) {
                      items.push(<Pagination.Ellipsis key="ellipsis1" />);
                    }
                  }

                  // Visible pages
                  for (let page = startPage; page <= endPage; page++) {
                    items.push(
                      <Pagination.Item
                        key={page}
                        active={page === pagination.current_page}
                        onClick={() => setCurrentPage(page)}
                      >
                        {page}
                      </Pagination.Item>
                    );
                  }

                  // Last page
                  if (endPage < totalPages) {
                    if (endPage < totalPages - 1) {
                      items.push(<Pagination.Ellipsis key="ellipsis2" />);
                    }
                    items.push(
                      <Pagination.Item key={totalPages} onClick={() => setCurrentPage(totalPages)}>
                        {totalPages}
                      </Pagination.Item>
                    );
                  }

                  return items;
                })()}
                <Pagination.Next
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={pagination.current_page >= pagination.total_pages}
                />
                <Pagination.Last
                  onClick={() => setCurrentPage(pagination.total_pages)}
                  disabled={pagination.current_page >= pagination.total_pages}
                />
              </Pagination>
            </div>
          </Col>
        </Row>
      )}
      
      {/* Fallback pagination for backward compatibility when pagination is not provided */}
      {!loading && !error && !pagination && Object.keys(externalLinksData).length > pageSize && (
        <Row className="mt-4">
          <Col>
            <div className="text-center mb-3">
              <div className="text-muted">
                Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, Object.keys(externalLinksData).length)} of {Object.keys(externalLinksData).length} groups
                (Page {currentPage} of {Math.ceil(Object.keys(externalLinksData).length / pageSize)})
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
                  onClick={() => setCurrentPage(1)}
                  disabled={currentPage === 1}
                />
                <Pagination.Prev
                  onClick={() => setCurrentPage(currentPage - 1)}
                  disabled={currentPage === 1}
                />
                {(() => {
                  const totalPages = Math.ceil(Object.keys(externalLinksData).length / pageSize);
                  const items = [];
                  const maxVisiblePages = 5;
                  let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
                  let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

                  if (endPage - startPage + 1 < maxVisiblePages) {
                    startPage = Math.max(1, endPage - maxVisiblePages + 1);
                  }

                  // First page
                  if (startPage > 1) {
                    items.push(
                      <Pagination.Item key={1} onClick={() => setCurrentPage(1)}>
                        1
                      </Pagination.Item>
                    );
                    if (startPage > 2) {
                      items.push(<Pagination.Ellipsis key="ellipsis1" />);
                    }
                  }

                  // Visible pages
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

                  // Last page
                  if (endPage < totalPages) {
                    if (endPage < totalPages - 1) {
                      items.push(<Pagination.Ellipsis key="ellipsis2" />);
                    }
                    items.push(
                      <Pagination.Item key={totalPages} onClick={() => setCurrentPage(totalPages)}>
                        {totalPages}
                      </Pagination.Item>
                    );
                  }

                  return items;
                })()}
                <Pagination.Next
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={currentPage === Math.ceil(Object.keys(externalLinksData).length / pageSize)}
                />
                <Pagination.Last
                  onClick={() => setCurrentPage(Math.ceil(Object.keys(externalLinksData).length / pageSize))}
                  disabled={currentPage === Math.ceil(Object.keys(externalLinksData).length / pageSize)}
                />
              </Pagination>
            </div>
          </Col>
        </Row>
      )}

      {/* Export Modal */}
      <Modal show={showExportModal} onHide={() => setShowExportModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Export External Links</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Row className="mb-4">
            <Col>
              <h6>Export Format</h6>
              <Form.Check
                type="radio"
                name="exportFormat"
                id="format-json"
                label="JSON - Full data with metadata and grouping"
                checked={exportFormat === 'json'}
                onChange={() => setExportFormat('json')}
                className="mb-2"
              />
              <Form.Check
                type="radio"
                name="exportFormat"
                id="format-csv"
                label="CSV - Destination and source pages in spreadsheet format"
                checked={exportFormat === 'csv'}
                onChange={() => setExportFormat('csv')}
                className="mb-2"
              />
              <Form.Check
                type="radio"
                name="exportFormat"
                id="format-txt"
                label="Plain Text - Destination URLs only (one per line)"
                checked={exportFormat === 'txt'}
                onChange={() => setExportFormat('txt')}
              />
            </Col>
          </Row>
          
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
                  Leave empty to use default filename: external_links_export_YYYY-MM-DD.{exportFormat}
                </Form.Text>
              </Form.Group>
              <div className="mb-2">
                <strong>Export Summary:</strong>
              </div>
              <ul className="list-unstyled text-muted small">
                <li>• Total groups: {Object.keys(externalLinksData).length}</li>
                <li>• Total links: {Object.values(externalLinksData).reduce((sum, links) => sum + links.length, 0)}</li>
                <li>• Applied filters: {[
                  selectedProgram && `Program: ${selectedProgram}`,
                  debouncedLinkSearch && `Search: ${debouncedLinkSearch}`,
                  selectedRoot && `Root: ${selectedRoot}`,
                  linkNegative && 'Negative filter enabled'
                ].filter(Boolean).join(', ') || 'None'}</li>
              </ul>
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
            disabled={exporting || Object.keys(externalLinksData).length === 0}
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

export default ExternalLinks;