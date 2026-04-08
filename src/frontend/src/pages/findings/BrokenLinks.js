import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Container, Card, Table, Badge, Form, Row, Col, Button, Pagination, Alert, Spinner, Modal } from 'react-bootstrap';
import { brokenLinksAPI } from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function BrokenLinks() {
  usePageTitle(formatPageTitle('Broken Links'));
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedProgram } = useProgramFilter();
  
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({});
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  
  // Filters
  const [linkTypeFilter, setLinkTypeFilter] = useState(searchParams.get('link_type') || '');
  const [mediaTypeFilter, setMediaTypeFilter] = useState(searchParams.get('media_type') || '');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || '');
  const [domainSearch, setDomainSearch] = useState(searchParams.get('domain_search') || '');
  const [currentPage, setCurrentPage] = useState(parseInt(searchParams.get('page') || '1', 10));
  const [pageSize, setPageSize] = useState(parseInt(searchParams.get('page_size') || '25', 10));
  const [sortBy, setSortBy] = useState(searchParams.get('sort_by') || 'checked_at');
  const [sortDir, setSortDir] = useState(searchParams.get('sort_dir') || 'desc');

  const fetchFindings = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const params = {
        program_name: selectedProgram || undefined,
        link_type: linkTypeFilter || undefined,
        media_type: mediaTypeFilter || undefined,
        status: statusFilter || undefined,
        domain_search: domainSearch || undefined,
        page: currentPage,
        page_size: pageSize,
        sort_by: sortBy,
        sort_dir: sortDir
      };
      
      const response = await brokenLinksAPI.search(params);
      setFindings(response.findings || []);
      setPagination({
        total: response.total || 0,
        page: response.page || currentPage,
        page_size: response.page_size || pageSize,
        total_pages: response.total_pages || 0
      });
    } catch (err) {
      setError(err.message || 'Failed to fetch broken links');
      console.error('Error fetching broken links:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedProgram, linkTypeFilter, mediaTypeFilter, statusFilter, domainSearch, currentPage, pageSize, sortBy, sortDir]);

  useEffect(() => {
    fetchFindings();
  }, [fetchFindings]);

  // Update URL params when filters change
  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedProgram) params.set('program', selectedProgram);
    if (linkTypeFilter) params.set('link_type', linkTypeFilter);
    if (mediaTypeFilter) params.set('media_type', mediaTypeFilter);
    if (statusFilter) params.set('status', statusFilter);
    if (domainSearch) params.set('domain_search', domainSearch);
    if (currentPage > 1) params.set('page', currentPage.toString());
    if (pageSize !== 25) params.set('page_size', pageSize.toString());
    if (sortBy !== 'checked_at') params.set('sort_by', sortBy);
    if (sortDir !== 'desc') params.set('sort_dir', sortDir);
    setSearchParams(params, { replace: true });
  }, [selectedProgram, linkTypeFilter, mediaTypeFilter, statusFilter, domainSearch, currentPage, pageSize, sortBy, sortDir, setSearchParams]);

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortDir('desc');
    }
    setCurrentPage(1);
  };

  const getLinkTypeBadgeVariant = (linkType) => {
    switch (linkType?.toLowerCase()) {
      case 'social_media': return 'primary';
      case 'general': return 'secondary';
      default: return 'secondary';
    }
  };

  const getStatusBadgeVariant = (status) => {
    switch (status) {
      case 'valid': return 'success';
      case 'broken': return 'danger';
      case 'error': return 'warning';
      case 'throttled': return 'info';
      default: return 'secondary';
    }
  };

  const getMediaTypeBadgeVariant = (mediaType) => {
    switch (mediaType?.toLowerCase()) {
      case 'facebook': return 'primary';
      case 'instagram': return 'danger';
      case 'twitter':
      case 'x': return 'info';
      case 'linkedin': return 'primary';
      default: return 'secondary';
    }
  };

  const handleFindingClick = (finding) => {
    navigate(`/findings/broken-links/details?id=${finding.id}`);
  };

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
      await brokenLinksAPI.deleteBatch(selectedIds);
      setShowDeleteModal(false);
      setSelectedItems(new Set());
      // Refresh the current page with current filters
      fetchFindings();
    } catch (err) {
      console.error('Error deleting broken links:', err);
      alert('Failed to delete broken links: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <Container fluid className="mt-4">
        <div className="text-center">
          <Spinner animation="border" />
          <p className="mt-2">Loading broken links...</p>
        </div>
      </Container>
    );
  }

  return (
    <Container fluid className="mt-4">
      <Row className="mb-4">
        <Col>
          <h1>Broken Links</h1>
          <p className="text-muted">
            Outbound links checked for reachability during reconnaissance
          </p>
        </Col>
      </Row>
      <Card>
        {selectedItems.size > 0 && (
          <Card.Header className="d-flex justify-content-end align-items-center">
            <Button
              variant="outline-danger"
              size="sm"
              onClick={() => setShowDeleteModal(true)}
            >
              <i className="bi bi-trash"></i> Delete Selected ({selectedItems.size})
            </Button>
          </Card.Header>
        )}
        <Card.Body>
          {error && <Alert variant="danger">{error}</Alert>}
          
          {/* Filters */}
          <Row className="mb-3">
            <Col md={3}>
              <Form.Group>
                <Form.Label>Link Type</Form.Label>
                <Form.Select
                  value={linkTypeFilter}
                  onChange={(e) => { setLinkTypeFilter(e.target.value); setCurrentPage(1); }}
                >
                  <option value="">All</option>
                  <option value="social_media">Social Media</option>
                  <option value="general">General</option>
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group>
                <Form.Label>Media Type</Form.Label>
                <Form.Select
                  value={mediaTypeFilter}
                  onChange={(e) => { setMediaTypeFilter(e.target.value); setCurrentPage(1); }}
                >
                  <option value="">All</option>
                  <option value="facebook">Facebook</option>
                  <option value="instagram">Instagram</option>
                  <option value="twitter">Twitter</option>
                  <option value="x">X</option>
                  <option value="linkedin">LinkedIn</option>
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group>
                <Form.Label>Status</Form.Label>
                <Form.Select
                  value={statusFilter}
                  onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1); }}
                >
                  <option value="">All</option>
                  <option value="valid">Valid</option>
                  <option value="broken">Broken</option>
                  <option value="error">Error</option>
                  <option value="throttled">Throttled</option>
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group>
                <Form.Label>Page Size</Form.Label>
                <Form.Select
                  value={pageSize}
                  onChange={(e) => { setPageSize(parseInt(e.target.value)); setCurrentPage(1); }}
                >
                  <option value="25">25</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                </Form.Select>
              </Form.Group>
            </Col>
          </Row>
          <Row className="mb-3">
            <Col md={6}>
              <Form.Group>
                <Form.Label>Domain Search</Form.Label>
                <Form.Control
                  type="text"
                  placeholder="Search domains..."
                  value={domainSearch}
                  onChange={(e) => { setDomainSearch(e.target.value); setCurrentPage(1); }}
                />
              </Form.Group>
            </Col>
          </Row>

          {/* Results */}
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>
                  <Form.Check
                    type="checkbox"
                    checked={selectedItems.size === findings.length && findings.length > 0}
                    onChange={(e) => handleSelectAll(e.target.checked)}
                  />
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => handleSort('link_type')}>
                  Link Type {sortBy === 'link_type' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => handleSort('media_type')}>
                  Media Type {sortBy === 'media_type' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => handleSort('domain')}>
                  Domain {sortBy === 'domain' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th>Reason</th>
                <th style={{ cursor: 'pointer' }} onClick={() => handleSort('status')}>
                  Status {sortBy === 'status' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th>URL</th>
                <th style={{ cursor: 'pointer' }} onClick={() => handleSort('checked_at')}>
                  Checked At {sortBy === 'checked_at' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th>Program</th>
              </tr>
            </thead>
            <tbody>
              {findings.length === 0 ? (
                <tr>
                  <td colSpan="9" className="text-center">No broken links found</td>
                </tr>
              ) : (
                findings.map((finding) => (
                  <tr
                    key={finding.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleFindingClick(finding)}
                  >
                    <td onClick={(e) => e.stopPropagation()}>
                      <Form.Check
                        type="checkbox"
                        checked={selectedItems.has(finding.id)}
                        onChange={(e) => handleSelectItem(finding.id, e.target.checked)}
                      />
                    </td>
                    <td>
                      <Badge bg={getLinkTypeBadgeVariant(finding.link_type)}>
                        {finding.link_type === 'social_media' ? 'Social Media' : 'General'}
                      </Badge>
                    </td>
                    <td>
                      {finding.media_type && (
                        <Badge bg={getMediaTypeBadgeVariant(finding.media_type)}>
                          {finding.media_type}
                        </Badge>
                      )}
                    </td>
                    <td>{finding.domain || '-'}</td>
                    <td>{finding.reason || '-'}</td>
                    <td>
                      <Badge bg={getStatusBadgeVariant(finding.status)}>
                        {finding.status}
                      </Badge>
                    </td>
                    <td>
                      {finding.url ? (
                        <a href={finding.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>
                          {finding.url}
                        </a>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td>{finding.checked_at ? formatDate(finding.checked_at) : '-'}</td>
                    <td>{finding.program_name || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>

          {/* Pagination */}
          {pagination.total_pages > 1 && (
            <Pagination className="justify-content-center">
              <Pagination.First
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(1)}
              />
              <Pagination.Prev
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(currentPage - 1)}
              />
              {[...Array(Math.min(5, pagination.total_pages))].map((_, i) => {
                const pageNum = Math.max(1, Math.min(pagination.total_pages - 4, currentPage - 2)) + i;
                if (pageNum > pagination.total_pages) return null;
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
                disabled={currentPage >= pagination.total_pages}
                onClick={() => setCurrentPage(currentPage + 1)}
              />
              <Pagination.Last
                disabled={currentPage >= pagination.total_pages}
                onClick={() => setCurrentPage(pagination.total_pages)}
              />
            </Pagination>
          )}

          <div className="text-center mt-3">
            <p className="text-muted">
              Showing {findings.length} of {pagination.total} broken links
            </p>
          </div>
        </Card.Body>
      </Card>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Broken Links</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected broken link(s)?</p>
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
                <i className="bi bi-trash"></i> Delete {selectedItems.size} Broken Link(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default BrokenLinks;

