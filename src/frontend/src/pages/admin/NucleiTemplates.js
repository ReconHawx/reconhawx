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
  Dropdown,
  Pagination,
  Tabs,
  Tab
} from 'react-bootstrap';
import { nucleiTemplatesAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function NucleiTemplates() {
  usePageTitle(formatPageTitle('Nuclei Templates'));
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showViewModal, setShowViewModal] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [formData, setFormData] = useState({ content: '' });
  const [formError, setFormError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalTemplates, setTotalTemplates] = useState(0);
  const [pageSize] = useState(10);
  const [inputMode, setInputMode] = useState('manual'); // 'manual' or 'file'
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [showUpdateConfirmModal, setShowUpdateConfirmModal] = useState(false);
  const [existingTemplate, setExistingTemplate] = useState(null);
  const [pendingTemplateData, setPendingTemplateData] = useState(null);

  // Load templates
  const loadTemplates = useCallback(async (page = 1, search = '') => {
    try {
      setLoading(true);
      const response = await nucleiTemplatesAPI.list((page - 1) * pageSize, pageSize, true, null, null, search);
      setTemplates(response.templates);
      setTotalTemplates(response.total);
      setTotalPages(Math.ceil(response.total / pageSize));
      setCurrentPage(page);
    } catch (err) {
      setError('Failed to load templates');
      console.error('Error loading templates:', err);
    } finally {
      setLoading(false);
    }
  }, [pageSize]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  // Handle search
  const handleSearch = (e) => {
    e.preventDefault();
    loadTemplates(1, searchTerm);
  };

  // Handle file upload
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    setSelectedFile(file);
    setFileError(null);

    if (file) {
      // Validate file type
      if (!file.name.endsWith('.yaml') && !file.name.endsWith('.yml')) {
        setFileError('Please select a YAML file (.yaml or .yml)');
        setSelectedFile(null);
        return;
      }

      // Validate file size (max 1MB)
      if (file.size > 1024 * 1024) {
        setFileError('File size must be less than 1MB');
        setSelectedFile(null);
        return;
      }

      // Read file content
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target.result;
        setFormData({ content });
        // Check for existing template ID (exclude current template if editing)
        checkForExistingTemplate(content, selectedTemplate?.id);
      };
      reader.onerror = () => {
        setFileError('Failed to read file');
      };
      reader.readAsText(file);
    }
  };

  // Extract template ID from YAML content
  const extractTemplateId = (content) => {
    try {
      // Simple regex to extract the id field from YAML
      const idMatch = content.match(/^id:\s*([^\s\n]+)/m);
      return idMatch ? idMatch[1].trim() : null;
    } catch (error) {
      console.error('Error extracting template ID:', error);
      return null;
    }
  };

  // Check if template with the same ID already exists
  const checkForExistingTemplate = async (content, excludeTemplateId = null) => {
    const templateId = extractTemplateId(content);
    if (!templateId) return;

    try {
      const result = await nucleiTemplatesAPI.checkExists(templateId);
      if (result.exists && (!excludeTemplateId || result.template.id !== excludeTemplateId)) {
        setFormError(`Template with ID '${templateId}' already exists (${result.template.name}). You can update the existing template or use a different ID.`);
      } else {
        setFormError(null);
      }
    } catch (error) {
      console.error('Error checking template existence:', error);
    }
  };

  // Reset form data
  const resetFormData = () => {
    setFormData({ content: '' });
    setSelectedFile(null);
    setFileError(null);
    setFormError(null);
    setInputMode('manual');
  };

  // Create template
  const handleCreate = async () => {
    try {
      setFormError(null);
      if (!formData.content.trim()) {
        setFormError('Template content is required');
        return;
      }

      // Check for existing template ID
      const templateId = extractTemplateId(formData.content);
      if (templateId) {
        const result = await nucleiTemplatesAPI.checkExists(templateId);
        if (result.exists) {
          // Show confirmation modal instead of alert
          setExistingTemplate(result.template);
          setPendingTemplateData(formData);
          setShowUpdateConfirmModal(true);
          return;
        }
      }

      await nucleiTemplatesAPI.create(formData);
      setShowCreateModal(false);
      resetFormData();
      loadTemplates(currentPage, searchTerm);
      setError(null);
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to create template');
    }
  };

  // Update template
  const handleUpdate = async () => {
    try {
      setFormError(null);
      if (!formData.content.trim()) {
        setFormError('Template content is required');
        return;
      }
      const updateData = {};
      if (formData.content) {
        updateData.content = formData.content;
      }
      
      await nucleiTemplatesAPI.update(selectedTemplate.id, updateData);
      setShowEditModal(false);
      resetFormData();
      setSelectedTemplate(null);
      loadTemplates(currentPage, searchTerm);
      setError(null);
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to update template');
    }
  };

  // Delete template
  const handleDelete = async (hardDelete = false) => {
    try {
      await nucleiTemplatesAPI.delete(selectedTemplate.id, hardDelete);
      setShowDeleteModal(false);
      setSelectedTemplate(null);
      loadTemplates(currentPage, searchTerm);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete template');
    }
  };

  // View template
  const handleView = (template) => {
    setSelectedTemplate(template);
    setShowViewModal(true);
  };

  // Edit template
  const handleEdit = (template) => {
    setSelectedTemplate(template);
    setFormData({ content: template.content });
    setInputMode('manual');
    setFormError(null); // Clear any previous errors
    setShowEditModal(true);
  };

  // Delete template confirmation
  const handleDeleteClick = (template) => {
    setSelectedTemplate(template);
    setShowDeleteModal(true);
  };

  // Get severity badge color
  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical': return 'danger';
      case 'high': return 'warning';
      case 'medium': return 'info';
      case 'low': return 'secondary';
      case 'info': return 'primary';
      default: return 'secondary';
    }
  };

  // Format date
  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString();
  };

  // Handle template update confirmation
  const handleConfirmUpdate = async () => {
    try {
      const templateId = existingTemplate.id;
      await nucleiTemplatesAPI.update(templateId, pendingTemplateData);
      setShowUpdateConfirmModal(false);
      setShowCreateModal(false);
      resetFormData();
      setExistingTemplate(null);
      setPendingTemplateData(null);
      loadTemplates(currentPage, searchTerm);
      setError(null);
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to update template');
      setShowUpdateConfirmModal(false);
    }
  };

  // Handle template update cancellation
  const handleCancelUpdate = () => {
    setShowUpdateConfirmModal(false);
    setExistingTemplate(null);
    setPendingTemplateData(null);
    setFormError(`Template with ID '${existingTemplate?.id}' already exists. Please use a different ID or update the existing template.`);
  };

  // Render input form based on mode
  const renderInputForm = () => (
    <Tabs
      activeKey={inputMode}
      onSelect={(k) => setInputMode(k)}
      className="mb-3"
    >
      <Tab eventKey="manual" title="📝 Manual Input">
        <Form.Group className="mb-3">
          <Form.Label>YAML Content</Form.Label>
          <Form.Control
            as="textarea"
            rows={15}
            value={formData.content}
            onChange={(e) => {
              setFormData({ content: e.target.value });
              // Check for existing template ID when content changes
              if (e.target.value.trim()) {
                checkForExistingTemplate(e.target.value, selectedTemplate?.id);
              } else {
                setFormError(null);
              }
            }}
            placeholder="Paste your nuclei template YAML content here..."
          />
          <Form.Text className="text-muted">
            The API will automatically extract metadata (id, name, author, severity, description, tags) from the YAML content.
          </Form.Text>
        </Form.Group>
      </Tab>
      <Tab eventKey="file" title="📁 File Upload">
        <Form.Group className="mb-3">
          <Form.Label>Upload YAML File</Form.Label>
          <Form.Control
            type="file"
            accept=".yaml,.yml"
            onChange={handleFileUpload}
            isInvalid={!!fileError}
          />
          {fileError && (
            <Form.Control.Feedback type="invalid">
              {fileError}
            </Form.Control.Feedback>
          )}
          <Form.Text className="text-muted">
            Select a .yaml or .yml file (max 1MB). The file content will be loaded into the form.
          </Form.Text>
          {selectedFile && (
            <div className="mt-2">
              <Badge bg="success">✓ {selectedFile.name} loaded</Badge>
            </div>
          )}
        </Form.Group>
        {formData.content && (
          <Form.Group className="mb-3">
            <Form.Label>File Content Preview</Form.Label>
            <Form.Control
              as="textarea"
              rows={8}
              value={formData.content}
              onChange={(e) => setFormData({ content: e.target.value })}
            />
            <Form.Text className="text-muted">
              You can edit the content above if needed before saving.
            </Form.Text>
          </Form.Group>
        )}
      </Tab>
    </Tabs>
  );

  return (
    <Container fluid className="p-4">
      <Row className="mb-3">
        <Col>
          <h2>🎯 Nuclei Templates</h2>
        </Col>
        <Col xs="auto">
          <Button 
            variant="primary" 
            onClick={() => setShowCreateModal(true)}
          >
            ➕ Add Template
          </Button>
        </Col>
      </Row>

      {/* Help Section */}
      <Card className="mb-3">
        <Card.Header>
          <h5 className="mb-0">💡 Template Format</h5>
        </Card.Header>
        <Card.Body>
          <p>
            Nuclei templates should follow the standard nuclei template format. The API automatically extracts metadata from the YAML content.
          </p>
          <details>
            <summary>Example Template</summary>
            <pre className="mt-2 p-3 bg-light rounded">
{`id: example-template

info:
  name: Example Template
  author: your-name
  severity: medium
  description: An example nuclei template
  tags:
    - example
    - test

http:
- raw:
  - |
    GET / HTTP/1.1
    Host: {{Hostname}}
    User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

  matchers:
  - type: dsl
    dsl:
    - "status_code == 200"`}
            </pre>
          </details>
        </Card.Body>
      </Card>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Search and Filters */}
      <Card className="mb-3">
        <Card.Body>
          <Form onSubmit={handleSearch}>
            <Row>
              <Col md={6}>
                <InputGroup>
                  <Form.Control
                    type="text"
                    placeholder="Search templates..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                  <Button variant="outline-secondary" type="submit">
                    🔍 Search
                  </Button>
                </InputGroup>
              </Col>
              <Col md={6} className="text-end">
                <small className="text-muted">
                  Total: {totalTemplates} templates
                </small>
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {/* Templates Table */}
      <Card>
        <Card.Body>
          {loading ? (
            <div className="text-center py-4">
              <div className="spinner-border" role="status">
                <span className="visually-hidden">Loading...</span>
              </div>
            </div>
          ) : templates.length === 0 ? (
            <div className="text-center py-4">
              <p className="text-muted">No templates found</p>
              <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                Create your first template
              </Button>
            </div>
          ) : (
            <>
              <Table responsive hover>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Author</th>
                    <th>Severity</th>
                    <th>Tags</th>
                    <th>Created</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {templates.map((template) => (
                    <tr key={template.id}>
                      <td>
                        <code>{template.id}</code>
                      </td>
                      <td>
                        <strong>{template.name}</strong>
                        {template.description && (
                          <div className="text-muted small">
                            {template.description}
                          </div>
                        )}
                      </td>
                      <td>{template.author || '-'}</td>
                      <td>
                        {template.severity && (
                          <Badge bg={getSeverityColor(template.severity)}>
                            {template.severity}
                          </Badge>
                        )}
                      </td>
                      <td>
                        {template.tags?.map((tag, index) => (
                          <Badge key={index} bg="light" text="dark" className="me-1">
                            {tag}
                          </Badge>
                        ))}
                      </td>
                      <td>{formatDate(template.created_at)}</td>
                      <td>
                        <Badge bg={template.is_active ? 'success' : 'secondary'}>
                          {template.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td>
                        <Dropdown>
                          <Dropdown.Toggle variant="outline-secondary" size="sm">
                            Actions
                          </Dropdown.Toggle>
                          <Dropdown.Menu>
                            <Dropdown.Item onClick={() => handleView(template)}>
                              👁️ View
                            </Dropdown.Item>
                            <Dropdown.Item onClick={() => handleEdit(template)}>
                              ✏️ Edit
                            </Dropdown.Item>
                            <Dropdown.Item onClick={() => handleDeleteClick(template)}>
                              🗑️ Delete
                            </Dropdown.Item>
                          </Dropdown.Menu>
                        </Dropdown>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="d-flex justify-content-center">
                  <Pagination>
                    <Pagination.First 
                      onClick={() => loadTemplates(1, searchTerm)}
                      disabled={currentPage === 1}
                    />
                    <Pagination.Prev 
                      onClick={() => loadTemplates(currentPage - 1, searchTerm)}
                      disabled={currentPage === 1}
                    />
                    
                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                      const page = Math.max(1, Math.min(totalPages - 4, currentPage - 2)) + i;
                      return (
                        <Pagination.Item
                          key={page}
                          active={page === currentPage}
                          onClick={() => loadTemplates(page, searchTerm)}
                        >
                          {page}
                        </Pagination.Item>
                      );
                    })}
                    
                    <Pagination.Next 
                      onClick={() => loadTemplates(currentPage + 1, searchTerm)}
                      disabled={currentPage === totalPages}
                    />
                    <Pagination.Last 
                      onClick={() => loadTemplates(totalPages, searchTerm)}
                      disabled={currentPage === totalPages}
                    />
                  </Pagination>
                </div>
              )}
            </>
          )}
        </Card.Body>
      </Card>

      {/* Create Modal */}
      <Modal show={showCreateModal} onHide={() => {
        setShowCreateModal(false);
        resetFormData();
      }} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>➕ Add New Template</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {formError && (
            <Alert variant="danger" dismissible onClose={() => setFormError(null)}>
              {formError}
            </Alert>
          )}
          {renderInputForm()}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => {
            setShowCreateModal(false);
            resetFormData();
          }}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleCreate}>
            Create Template
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Edit Modal */}
      <Modal show={showEditModal} onHide={() => {
        setShowEditModal(false);
        resetFormData();
        setSelectedTemplate(null);
      }} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>✏️ Edit Template: {selectedTemplate?.name}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {formError && (
            <Alert variant="danger" dismissible onClose={() => setFormError(null)}>
              {formError}
            </Alert>
          )}
          {renderInputForm()}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => {
            setShowEditModal(false);
            resetFormData();
            setSelectedTemplate(null);
          }}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleUpdate}>
            Update Template
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>🗑️ Delete Template</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>
            Are you sure you want to delete the template <strong>{selectedTemplate?.name}</strong>?
          </p>
          <p className="text-muted">
            This will perform a soft delete by default (sets the template as inactive). 
            You can permanently delete it using the "Hard Delete" option.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
            Cancel
          </Button>
          <Button variant="warning" onClick={() => handleDelete(false)}>
            Soft Delete
          </Button>
          <Button variant="danger" onClick={() => handleDelete(true)}>
            Hard Delete
          </Button>
        </Modal.Footer>
      </Modal>

      {/* View Modal */}
      <Modal show={showViewModal} onHide={() => setShowViewModal(false)} size="xl">
        <Modal.Header closeButton>
          <Modal.Title>👁️ View Template: {selectedTemplate?.name}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Row>
            <Col md={6}>
              <h6>Template Details</h6>
              <Table size="sm">
                <tbody>
                  <tr>
                    <td><strong>ID:</strong></td>
                    <td><code>{selectedTemplate?.id}</code></td>
                  </tr>
                  <tr>
                    <td><strong>Name:</strong></td>
                    <td>{selectedTemplate?.name}</td>
                  </tr>
                  <tr>
                    <td><strong>Author:</strong></td>
                    <td>{selectedTemplate?.author || '-'}</td>
                  </tr>
                  <tr>
                    <td><strong>Severity:</strong></td>
                    <td>
                      {selectedTemplate?.severity && (
                        <Badge bg={getSeverityColor(selectedTemplate.severity)}>
                          {selectedTemplate.severity}
                        </Badge>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Description:</strong></td>
                    <td>{selectedTemplate?.description || '-'}</td>
                  </tr>
                  <tr>
                    <td><strong>Tags:</strong></td>
                    <td>
                      {selectedTemplate?.tags?.map((tag, index) => (
                        <Badge key={index} bg="light" text="dark" className="me-1">
                          {tag}
                        </Badge>
                      ))}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Status:</strong></td>
                    <td>
                      <Badge bg={selectedTemplate?.is_active ? 'success' : 'secondary'}>
                        {selectedTemplate?.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td>{selectedTemplate?.created_at && formatDate(selectedTemplate.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Updated:</strong></td>
                    <td>{selectedTemplate?.updated_at && formatDate(selectedTemplate.updated_at)}</td>
                  </tr>
                </tbody>
              </Table>
            </Col>
            <Col md={6}>
              <h6>YAML Content</h6>
              <pre className="bg-light p-3 rounded" style={{ fontSize: '0.8rem', maxHeight: '400px', overflow: 'auto' }}>
                {selectedTemplate?.content}
              </pre>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowViewModal(false)}>
            Close
          </Button>
          <Button variant="primary" onClick={() => {
            setShowViewModal(false);
            handleEdit(selectedTemplate);
          }}>
            Edit Template
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Update Confirmation Modal */}
      <Modal show={showUpdateConfirmModal} onHide={handleCancelUpdate} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>🔄 Update Existing Template</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Alert variant="warning" className="mb-3">
            <Alert.Heading>⚠️ Template Already Exists</Alert.Heading>
            <p>
              A template with ID <strong>{existingTemplate?.id}</strong> already exists in the system. 
              You can update the existing template with your new content or cancel to modify your template.
            </p>
          </Alert>

          <Row>
            <Col md={6}>
              <h6>📋 Existing Template Details</h6>
              <Table size="sm" className="mb-3">
                <tbody>
                  <tr>
                    <td><strong>ID:</strong></td>
                    <td><code>{existingTemplate?.id}</code></td>
                  </tr>
                  <tr>
                    <td><strong>Name:</strong></td>
                    <td>{existingTemplate?.name}</td>
                  </tr>
                  <tr>
                    <td><strong>Author:</strong></td>
                    <td>{existingTemplate?.author || '-'}</td>
                  </tr>
                  <tr>
                    <td><strong>Severity:</strong></td>
                    <td>
                      {existingTemplate?.severity && (
                        <Badge bg={getSeverityColor(existingTemplate.severity)}>
                          {existingTemplate.severity}
                        </Badge>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Description:</strong></td>
                    <td>{existingTemplate?.description || '-'}</td>
                  </tr>
                  <tr>
                    <td><strong>Tags:</strong></td>
                    <td>
                      {existingTemplate?.tags?.map((tag, index) => (
                        <Badge key={index} bg="light" text="dark" className="me-1">
                          {tag}
                        </Badge>
                      ))}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Created:</strong></td>
                    <td>{existingTemplate?.created_at && formatDate(existingTemplate.created_at)}</td>
                  </tr>
                  <tr>
                    <td><strong>Status:</strong></td>
                    <td>
                      <Badge bg={existingTemplate?.is_active ? 'success' : 'secondary'}>
                        {existingTemplate?.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                  </tr>
                </tbody>
              </Table>
            </Col>
            <Col md={6}>
              <h6>🆕 New Template Content</h6>
              <div className="mb-2">
                <small className="text-muted">Preview of your new template content:</small>
              </div>
              <pre className="bg-light p-2 rounded" style={{ fontSize: '0.75rem', maxHeight: '300px', overflow: 'auto' }}>
                {pendingTemplateData?.content}
              </pre>
            </Col>
          </Row>

          <Alert variant="info" className="mt-3">
            <strong>What will happen:</strong>
            <ul className="mb-0 mt-2">
              <li>The existing template will be updated with your new content</li>
              <li>All metadata (name, author, severity, etc.) will be re-extracted from your new content</li>
              <li>The template's <code>updated_at</code> timestamp will be updated</li>
              <li>Any changes to the template ID will be ignored (the existing ID will be preserved)</li>
            </ul>
          </Alert>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={handleCancelUpdate}>
            ❌ Cancel
          </Button>
          <Button variant="warning" onClick={handleConfirmUpdate}>
            🔄 Update Existing Template
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default NucleiTemplates; 