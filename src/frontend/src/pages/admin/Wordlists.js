import React, { useState, useEffect, useCallback } from 'react';
import { 
  Container, 
  Row, 
  Col, 
  Card, 
  Button, 
  Table, 
  Modal, 
  Form, 
  Alert, 
  Badge, 
  InputGroup,
  Pagination,
  Tabs,
  Tab
} from 'react-bootstrap';
import { wordlistsAPI } from '../../services/api';
import { formatDate } from '../../utils/dateUtils';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';

function Wordlists() {
  const { programs, selectedProgram } = useProgramFilter();
  const [wordlists, setWordlists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [selectedWordlist, setSelectedWordlist] = useState(null);
  const [formData, setFormData] = useState({ 
    name: '', 
    description: '', 
    tags: '', 
    program_name: selectedProgram || '' 
  });
  const [formError, setFormError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalWordlists, setTotalWordlists] = useState(0);
  const [pageSize] = useState(10);
  const [uploadMode, setUploadMode] = useState('manual'); // 'manual' or 'file'
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  
  // Dynamic wordlist modal state
  const [showDynamicModal, setShowDynamicModal] = useState(false);
  const [dynamicFormData, setDynamicFormData] = useState({
    name: '',
    description: '',
    dynamic_type: 'subdomain_prefixes',
    program_name: selectedProgram || '',
    tags: ''
  });
  const [dynamicFormError, setDynamicFormError] = useState(null);
  const [dynamicLoading, setDynamicLoading] = useState(false);

  // Load wordlists
  const loadWordlists = useCallback(async (page = 1, search = '') => {
    try {
      setLoading(true);
      const response = await wordlistsAPI.list((page - 1) * pageSize, pageSize, true, null, null, search);
      setWordlists(response.wordlists);
      setTotalWordlists(response.total);
      setTotalPages(Math.ceil(response.total / pageSize));
      setCurrentPage(page);
    } catch (err) {
      setError('Failed to load wordlists');
      console.error('Error loading wordlists:', err);
    } finally {
      setLoading(false);
    }
  }, [pageSize]);

  useEffect(() => {
    loadWordlists();
  }, [loadWordlists]);

  // Update form data when selectedProgram changes
  useEffect(() => {
    setFormData(prev => ({
      ...prev,
      program_name: selectedProgram || ''
    }));
  }, [selectedProgram]);

  // Handle search
  const handleSearch = (e) => {
    e.preventDefault();
    loadWordlists(1, searchTerm);
  };

  // Handle file upload
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    setSelectedFile(file);
    setFileError(null);

    if (file) {
      // Validate file type
      if (!file.name.endsWith('.txt') && !file.name.endsWith('.csv')) {
        setFileError('Please select a text file (.txt or .csv)');
        setSelectedFile(null);
        return;
      }

      // Validate file size (max 50MB)
      if (file.size > 50 * 1024 * 1024) {
        setFileError('File size must be less than 50MB');
        setSelectedFile(null);
        return;
      }

      // Set name from filename if not already set
      if (!formData.name) {
        const nameWithoutExt = file.name.replace(/\.(txt|csv)$/i, '');
        setFormData(prev => ({ ...prev, name: nameWithoutExt }));
      }
    }
  };

  // Reset form data
  const resetFormData = () => {
    setFormData({ 
      name: '', 
      description: '', 
      tags: '', 
      program_name: selectedProgram || '' 
    });
    setSelectedFile(null);
    setFileError(null);
    setFormError(null);
  };

  // Handle upload
  const handleUpload = async (e) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      setFormError('Name is required');
      return;
    }

    if (uploadMode === 'file' && !selectedFile) {
      setFormError('Please select a file to upload');
      return;
    }

    try {
      setUploadLoading(true);
      setFormError(null);

      const uploadFormData = new FormData();
      uploadFormData.append('name', formData.name.trim());
      uploadFormData.append('description', formData.description.trim());
      uploadFormData.append('tags', formData.tags.trim());
      if (formData.program_name.trim()) {
        uploadFormData.append('program_name', formData.program_name.trim());
      }

      if (uploadMode === 'file') {
        uploadFormData.append('file', selectedFile);
      } else {
        // Create a text file from manual input
        const textContent = formData.content || '';
        const blob = new Blob([textContent], { type: 'text/plain' });
        const file = new File([blob], `${formData.name}.txt`, { type: 'text/plain' });
        uploadFormData.append('file', file);
      }

      await wordlistsAPI.upload(uploadFormData);
      
      setShowUploadModal(false);
      resetFormData();
      loadWordlists(currentPage, searchTerm);
      
    } catch (err) {
      console.error('Error uploading wordlist:', err);
      setFormError(err.response?.data?.detail || 'Failed to upload wordlist');
    } finally {
      setUploadLoading(false);
    }
  };

  // Handle update
  const handleUpdate = async (e) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      setFormError('Name is required');
      return;
    }

    try {
      setUploadLoading(true);
      setFormError(null);

      const updateData = {
        name: formData.name.trim(),
        description: formData.description.trim(),
        tags: formData.tags.split(',').map(tag => tag.trim()).filter(tag => tag),
        program_name: formData.program_name.trim() || null
      };

      await wordlistsAPI.update(selectedWordlist.id, updateData);
      
      setShowEditModal(false);
      resetFormData();
      loadWordlists(currentPage, searchTerm);
      
    } catch (err) {
      console.error('Error updating wordlist:', err);
      setFormError(err.response?.data?.detail || 'Failed to update wordlist');
    } finally {
      setUploadLoading(false);
    }
  };

  // Handle delete
  const handleDelete = async () => {
    try {
      await wordlistsAPI.delete(selectedWordlist.id);
      setShowDeleteModal(false);
      loadWordlists(currentPage, searchTerm);
    } catch (err) {
      console.error('Error deleting wordlist:', err);
      setError('Failed to delete wordlist');
    }
  };

  // Handle download
  const handleDownload = async (wordlist) => {
    try {
      const blob = await wordlistsAPI.download(wordlist.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      // For dynamic wordlists, use name.txt as filename
      a.download = wordlist.filename || `${wordlist.name}.txt`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Error downloading wordlist:', err);
      setError('Failed to download wordlist');
    }
  };

  // Handle create dynamic wordlist
  const handleCreateDynamic = async (e) => {
    e.preventDefault();
    
    if (!dynamicFormData.name.trim()) {
      setDynamicFormError('Name is required');
      return;
    }

    if (!dynamicFormData.program_name) {
      setDynamicFormError('Program is required for dynamic wordlists');
      return;
    }

    try {
      setDynamicLoading(true);
      setDynamicFormError(null);

      const createData = {
        name: dynamicFormData.name.trim(),
        description: dynamicFormData.description.trim() || null,
        dynamic_type: dynamicFormData.dynamic_type,
        program_name: dynamicFormData.program_name,
        tags: dynamicFormData.tags.split(',').map(tag => tag.trim()).filter(tag => tag)
      };

      await wordlistsAPI.createDynamic(createData);
      
      setShowDynamicModal(false);
      setDynamicFormData({
        name: '',
        description: '',
        dynamic_type: 'subdomain_prefixes',
        program_name: selectedProgram || '',
        tags: ''
      });
      loadWordlists(currentPage, searchTerm);
      
    } catch (err) {
      console.error('Error creating dynamic wordlist:', err);
      setDynamicFormError(err.response?.data?.detail || 'Failed to create dynamic wordlist');
    } finally {
      setDynamicLoading(false);
    }
  };

  // Handle edit
  const handleEdit = (wordlist) => {
    setSelectedWordlist(wordlist);
    setFormData({
      name: wordlist.name,
      description: wordlist.description || '',
      tags: wordlist.tags.join(', '),
      program_name: wordlist.program_name || ''
    });
    setShowEditModal(true);
  };

  // Handle delete click
  const handleDeleteClick = (wordlist) => {
    setSelectedWordlist(wordlist);
    setShowDeleteModal(true);
  };

  // Format file size
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Render upload form
  const renderUploadForm = () => (
    <Tabs
      activeKey={uploadMode}
      onSelect={(k) => setUploadMode(k)}
      className="mb-3"
    >
      <Tab eventKey="file" title="📁 File Upload">
        <Form.Group className="mb-3">
          <Form.Label>Upload Wordlist File</Form.Label>
          <Form.Control
            type="file"
            accept=".txt,.csv"
            onChange={handleFileUpload}
            isInvalid={!!fileError}
          />
          {fileError && (
            <Form.Control.Feedback type="invalid">
              {fileError}
            </Form.Control.Feedback>
          )}
          <Form.Text className="text-muted">
            Select a .txt or .csv file (max 50MB). The filename will be used as the wordlist name if not specified.
          </Form.Text>
          {selectedFile && (
            <div className="mt-2">
              <Badge bg="success">✓ {selectedFile.name} selected ({formatFileSize(selectedFile.size)})</Badge>
            </div>
          )}
        </Form.Group>
      </Tab>
      <Tab eventKey="manual" title="✏️ Manual Input">
        <Form.Group className="mb-3">
          <Form.Label>Wordlist Content</Form.Label>
          <Form.Control
            as="textarea"
            rows={8}
            value={formData.content || ''}
            onChange={(e) => setFormData({ ...formData, content: e.target.value })}
            placeholder="Enter words, one per line..."
            style={{
              backgroundColor: 'var(--bs-input-bg)',
              color: 'var(--bs-input-color)',
              borderColor: 'var(--bs-border-color)'
            }}
          />
          <Form.Text className="text-muted">
            Enter words, subdomains, or other data, one per line.
          </Form.Text>
        </Form.Group>
      </Tab>
    </Tabs>
  );

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <div className="spinner-border" role="status">
            <span className="visually-hidden">Loading wordlists...</span>
          </div>
          <p className="mt-2">Loading wordlists...</p>
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
              <h1>📚 Wordlists</h1>
              <p className="text-muted">Manage custom wordlists for recon tasks</p>
            </div>
            <div className="btn-group">
              <Button variant="primary" onClick={() => setShowUploadModal(true)}>
                📤 Upload Wordlist
              </Button>
              <Button variant="success" onClick={() => setShowDynamicModal(true)}>
                ⚡ Create Dynamic
              </Button>
            </div>
          </div>
        </Col>
      </Row>

      {error && (
        <Row className="mb-3">
          <Col>
            <Alert variant="danger" onClose={() => setError(null)} dismissible>
              {error}
            </Alert>
          </Col>
        </Row>
      )}

      <Row className="mb-3">
        <Col>
          <Card>
            <Card.Body>
              <Form onSubmit={handleSearch}>
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
                    placeholder="Search wordlists by name or description..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    style={{
                      backgroundColor: 'var(--bs-input-bg)',
                      color: 'var(--bs-input-color)',
                      borderColor: 'var(--bs-border-color)'
                    }}
                  />
                  <Button variant="outline-secondary" type="submit">
                    Search
                  </Button>
                  {searchTerm && (
                    <Button 
                      variant="outline-secondary" 
                      onClick={() => {
                        setSearchTerm('');
                        loadWordlists(1, '');
                      }}
                    >
                      Clear
                    </Button>
                  )}
                </InputGroup>
              </Form>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <Card>
            <Card.Header>
              <div className="d-flex justify-content-between align-items-center">
                <h5 className="mb-0">
                  Wordlists ({totalWordlists})
                </h5>
                <div>
                  <small className="text-muted">
                    Showing {wordlists.length} of {totalWordlists} wordlists
                  </small>
                </div>
              </div>
            </Card.Header>
            <Card.Body>
              {wordlists.length > 0 ? (
                <Table striped bordered hover responsive>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Description</th>
                      <th>Program</th>
                      <th>Tags</th>
                      <th>File Info</th>
                      <th>Created</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wordlists.map((wordlist) => (
                      <tr key={wordlist.id}>
                        <td>
                          <strong>{wordlist.name}</strong>
                          {wordlist.is_dynamic && (
                            <Badge bg="success" className="ms-2">Dynamic</Badge>
                          )}
                          {!wordlist.is_active && (
                            <Badge bg="secondary" className="ms-2">Inactive</Badge>
                          )}
                        </td>
                        <td>
                          {wordlist.description || (
                            <span className="text-muted">No description</span>
                          )}
                        </td>
                        <td>
                          {wordlist.program_name ? (
                            <Badge bg="info">{wordlist.program_name}</Badge>
                          ) : (
                            <Badge bg="light" text="dark">Global</Badge>
                          )}
                        </td>
                        <td>
                          {wordlist.tags && wordlist.tags.length > 0 ? (
                            wordlist.tags.map((tag, index) => (
                              <Badge key={index} bg="outline-secondary" className="me-1">
                                {tag}
                              </Badge>
                            ))
                          ) : (
                            <span className="text-muted">No tags</span>
                          )}
                        </td>
                        <td>
                          {wordlist.is_dynamic ? (
                            <div>
                              <small className="text-muted">
                                Type: {wordlist.dynamic_type?.replace(/_/g, ' ')}
                              </small>
                              <br />
                              <small>
                                {wordlist.word_count.toLocaleString()} words (auto-generated)
                              </small>
                            </div>
                          ) : (
                            <div>
                              <small className="text-muted">
                                {wordlist.filename}
                              </small>
                              <br />
                              <small>
                                {formatFileSize(wordlist.file_size)} • {wordlist.word_count.toLocaleString()} words
                              </small>
                            </div>
                          )}
                        </td>
                        <td>
                          <small>
                            {formatDate(wordlist.created_at)}
                            <br />
                            <span className="text-muted">by {wordlist.created_by}</span>
                          </small>
                        </td>
                        <td>
                          <div className="btn-group" role="group">
                            <Button
                              variant="outline-primary"
                              size="sm"
                              onClick={() => handleDownload(wordlist)}
                              title="Download wordlist"
                            >
                              📥
                            </Button>
                            {!wordlist.is_dynamic && (
                              <Button
                                variant="outline-secondary"
                                size="sm"
                                onClick={() => handleEdit(wordlist)}
                                title="Edit wordlist"
                              >
                                ✏️
                              </Button>
                            )}
                            <Button
                              variant="outline-danger"
                              size="sm"
                              onClick={() => handleDeleteClick(wordlist)}
                              title="Delete wordlist"
                            >
                              🗑️
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : (
                <div className="text-center py-4">
                  <p className="text-muted">No wordlists found.</p>
                  <Button variant="primary" onClick={() => setShowUploadModal(true)}>
                    Upload Your First Wordlist
                  </Button>
                </div>
              )}

              {totalPages > 1 && (
                <div className="d-flex justify-content-center mt-3">
                  <Pagination>
                    <Pagination.First 
                      onClick={() => loadWordlists(1, searchTerm)}
                      disabled={currentPage === 1}
                    />
                    <Pagination.Prev 
                      onClick={() => loadWordlists(currentPage - 1, searchTerm)}
                      disabled={currentPage === 1}
                    />
                    
                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                      const page = Math.max(1, Math.min(totalPages - 4, currentPage - 2)) + i;
                      return (
                        <Pagination.Item
                          key={page}
                          active={page === currentPage}
                          onClick={() => loadWordlists(page, searchTerm)}
                        >
                          {page}
                        </Pagination.Item>
                      );
                    })}
                    
                    <Pagination.Next 
                      onClick={() => loadWordlists(currentPage + 1, searchTerm)}
                      disabled={currentPage === totalPages}
                    />
                    <Pagination.Last 
                      onClick={() => loadWordlists(totalPages, searchTerm)}
                      disabled={currentPage === totalPages}
                    />
                  </Pagination>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Upload Modal */}
      <Modal show={showUploadModal} onHide={() => setShowUploadModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Upload Wordlist</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleUpload}>
          <Modal.Body>
            {renderUploadForm()}
            
            <Form.Group className="mb-3">
              <Form.Label>Wordlist Name *</Form.Label>
              <Form.Control
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Enter a name for this wordlist"
                required
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Description</Form.Label>
              <Form.Control
                as="textarea"
                rows={2}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Describe what this wordlist contains..."
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Tags</Form.Label>
              <Form.Control
                type="text"
                value={formData.tags}
                onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
                placeholder="subdomains, enumeration, common (comma-separated)"
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
              <Form.Text className="text-muted">
                Enter tags separated by commas to help categorize this wordlist.
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Program (Optional)</Form.Label>
              <Form.Select
                value={formData.program_name}
                onChange={(e) => setFormData({ ...formData, program_name: e.target.value })}
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              >
                <option value="">Global Wordlist (Available to all programs)</option>
                {programs.map((program) => {
                  const name = typeof program === 'string' ? program : program.name;
                  return (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  );
                })}
              </Form.Select>
              <Form.Text className="text-muted">
                If specified, this wordlist will only be available for the specified program.
              </Form.Text>
            </Form.Group>

            {formError && (
              <Alert variant="danger">
                {formError}
              </Alert>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowUploadModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={uploadLoading}>
              {uploadLoading ? 'Uploading...' : 'Upload Wordlist'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal show={showEditModal} onHide={() => setShowEditModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Edit Wordlist</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleUpdate}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>Wordlist Name *</Form.Label>
              <Form.Control
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Enter a name for this wordlist"
                required
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Description</Form.Label>
              <Form.Control
                as="textarea"
                rows={2}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Describe what this wordlist contains..."
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Tags</Form.Label>
              <Form.Control
                type="text"
                value={formData.tags}
                onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
                placeholder="subdomains, enumeration, common (comma-separated)"
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Program</Form.Label>
              <Form.Select
                value={formData.program_name}
                onChange={(e) => setFormData({ ...formData, program_name: e.target.value })}
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              >
                <option value="">Global Wordlist (Available to all programs)</option>
                {programs.map((program) => {
                  const name = typeof program === 'string' ? program : program.name;
                  return (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  );
                })}
              </Form.Select>
            </Form.Group>

            {formError && (
              <Alert variant="danger">
                {formError}
              </Alert>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={uploadLoading}>
              {uploadLoading ? 'Updating...' : 'Update Wordlist'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Dynamic Wordlist Creation Modal */}
      <Modal show={showDynamicModal} onHide={() => setShowDynamicModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>⚡ Create Dynamic Wordlist</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleCreateDynamic}>
          <Modal.Body>
            <Alert variant="info" className="mb-3">
              <strong>Dynamic wordlists</strong> generate their content automatically from program assets.
              The content is refreshed each time the wordlist is downloaded.
            </Alert>

            <Form.Group className="mb-3">
              <Form.Label>Wordlist Name *</Form.Label>
              <Form.Control
                type="text"
                value={dynamicFormData.name}
                onChange={(e) => setDynamicFormData({ ...dynamicFormData, name: e.target.value })}
                placeholder="e.g., MyProgram Subdomain Prefixes"
                required
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Description</Form.Label>
              <Form.Control
                as="textarea"
                rows={2}
                value={dynamicFormData.description}
                onChange={(e) => setDynamicFormData({ ...dynamicFormData, description: e.target.value })}
                placeholder="Describe what this dynamic wordlist generates..."
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Dynamic Type *</Form.Label>
              <Form.Select
                value={dynamicFormData.dynamic_type}
                onChange={(e) => setDynamicFormData({ ...dynamicFormData, dynamic_type: e.target.value })}
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              >
                <option value="subdomain_prefixes">Subdomain Prefixes - Extract prefixes from subdomains</option>
              </Form.Select>
              <Form.Text className="text-muted">
                <strong>Subdomain Prefixes:</strong> Extracts the subdomain prefix from each subdomain asset.
                For example, "sub1.domain.com" with apex "domain.com" yields "sub1".
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Program * </Form.Label>
              <Form.Select
                value={dynamicFormData.program_name}
                onChange={(e) => setDynamicFormData({ ...dynamicFormData, program_name: e.target.value })}
                required
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              >
                <option value="">Select a program...</option>
                {programs.map((program) => {
                  const name = typeof program === 'string' ? program : program.name;
                  return (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  );
                })}
              </Form.Select>
              <Form.Text className="text-muted">
                The wordlist will be generated from this program's assets.
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Tags</Form.Label>
              <Form.Control
                type="text"
                value={dynamicFormData.tags}
                onChange={(e) => setDynamicFormData({ ...dynamicFormData, tags: e.target.value })}
                placeholder="dynamic, subdomains, enumeration (comma-separated)"
                style={{
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: 'var(--bs-border-color)'
                }}
              />
            </Form.Group>

            {dynamicFormError && (
              <Alert variant="danger">
                {dynamicFormError}
              </Alert>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowDynamicModal(false)}>
              Cancel
            </Button>
            <Button variant="success" type="submit" disabled={dynamicLoading}>
              {dynamicLoading ? 'Creating...' : 'Create Dynamic Wordlist'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Wordlist</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>
            Are you sure you want to delete the wordlist <strong>"{selectedWordlist?.name}"</strong>?
          </p>
          <p className="text-muted">
            This action cannot be undone. The wordlist file and all associated metadata will be permanently removed.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            Delete Wordlist
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default Wordlists; 