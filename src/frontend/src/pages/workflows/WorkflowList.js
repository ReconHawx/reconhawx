import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Table, Button, Badge, Alert, Spinner, Modal, Form } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { workflowAPI } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function WorkflowList() {
  usePageTitle(formatPageTitle('Workflow List'));
  // Use auth context to check superuser status
  const { isSuperuser } = useAuth();
  
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [workflowToDelete, setWorkflowToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showBatchDeleteModal, setShowBatchDeleteModal] = useState(false);
  const [batchDeleting, setBatchDeleting] = useState(false);

  useEffect(() => {
    loadWorkflows();
  }, []);

  const loadWorkflows = async () => {
    try {
      setLoading(true);
      const response = await workflowAPI.getWorkflows();
      setWorkflows(response.workflows || []);
      setError(null);
    } catch (err) {
      setError('Failed to load workflows: ' + err.message);
      setWorkflows([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteClick = (workflow) => {
    setWorkflowToDelete(workflow);
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!workflowToDelete) return;
    
    try {
      setDeleting(true);
      await workflowAPI.deleteWorkflow(workflowToDelete.id);
      await loadWorkflows(); // Reload the list
      setShowDeleteModal(false);
      setWorkflowToDelete(null);
    } catch (err) {
      setError('Failed to delete workflow: ' + err.message);
    } finally {
      setDeleting(false);
    }
  };

  // Batch delete handlers
  const handleSelectAll = (checked) => {
    if (checked) {
      // For non-superusers, exclude global workflows from selection
      const selectableWorkflows = isSuperuser() 
        ? workflows 
        : workflows.filter(workflow => workflow.program_name);
      setSelectedItems(new Set(selectableWorkflows.map(workflow => workflow.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (workflowId, checked) => {
    const newSelected = new Set(selectedItems);
    if (checked) {
      // For non-superusers, prevent selection of global workflows
      const workflow = workflows.find(w => w.id === workflowId);
      if (workflow && !workflow.program_name && !isSuperuser()) {
        return; // Don't allow selection
      }
      newSelected.add(workflowId);
    } else {
      newSelected.delete(workflowId);
    }
    setSelectedItems(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedItems.size === 0) return;

    try {
      setBatchDeleting(true);
      const selectedIds = Array.from(selectedItems);
      
      // Delete workflows one by one since there's no batch delete endpoint
      for (const workflowId of selectedIds) {
        try {
          await workflowAPI.deleteWorkflow(workflowId);
        } catch (err) {
          console.error(`Failed to delete workflow ${workflowId}:`, err);
          // Continue with other deletions even if one fails
        }
      }
      
      setShowBatchDeleteModal(false);
      setSelectedItems(new Set());
      await loadWorkflows(); // Reload the list
    } catch (err) {
      console.error('Error deleting workflows:', err);
      setError('Failed to delete some workflows: ' + err.message);
    } finally {
      setBatchDeleting(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  const getWorkflowScope = (workflow) => {
    if (!workflow.program_name) {
      return { badge: '🌍 Global', variant: 'success', tooltip: 'Visible to all users' };
    }
    return { badge: workflow.program_name, variant: 'primary', tooltip: 'Program-specific workflow' };
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading workflows...</p>
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
              <h1>📋 Saved Workflows</h1>
              <p className="text-muted">Manage your saved workflow definitions (global and program-specific)</p>
            </div>
            <Button as={Link} to="/workflows/create" variant="primary">
              ➕ Create Workflow
            </Button>
          </div>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">Workflow Definitions</h5>
              {selectedItems.size > 0 && (
                <Button
                  variant="outline-danger"
                  size="sm"
                  onClick={() => setShowBatchDeleteModal(true)}
                >
                  🗑️ Delete Selected ({selectedItems.size})
                </Button>
              )}
            </Card.Header>
            <Card.Body className="p-0">
              {workflows.length === 0 ? (
                <div className="text-center p-4">
                  <p className="text-muted mb-3">No workflows found.</p>
                  <Button as={Link} to="/workflows/create" variant="outline-primary">
                    Create your first workflow
                  </Button>
                </div>
              ) : (
                <Table responsive hover className="mb-0">
                  <thead>
                    <tr>
                      <th>
                        <Form.Check
                          type="checkbox"
                          checked={(() => {
                            // For non-superusers, only count selectable workflows
                            const selectableWorkflows = isSuperuser() 
                              ? workflows 
                              : workflows.filter(workflow => workflow.program_name);
                            return selectedItems.size === selectableWorkflows.length && selectableWorkflows.length > 0;
                          })()}
                          onChange={(e) => handleSelectAll(e.target.checked)}
                        />
                      </th>
                      <th>Name</th>
                      <th>Scope</th>
                      <th>Description</th>
                      <th>Tasks</th>
                      <th>Created</th>
                      <th>Updated</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workflows.map((workflow) => {
                      const scope = getWorkflowScope(workflow);
                      return (
                        <tr key={workflow.id}>
                          <td onClick={(e) => e.stopPropagation()}>
                            <Form.Check
                              type="checkbox"
                              checked={selectedItems.has(workflow.id)}
                              onChange={(e) => handleSelectItem(workflow.id, e.target.checked)}
                              disabled={!workflow.program_name && !isSuperuser()}
                              title={!workflow.program_name && !isSuperuser() ? "Only superusers can select global workflows" : ""}
                            />
                          </td>
                          <td>
                            <strong>{workflow.name}</strong>
                          </td>
                          <td>
                            <Badge 
                              bg={scope.variant} 
                              title={scope.tooltip}
                            >
                              {scope.badge}
                            </Badge>
                          </td>
                          <td>
                            <span className="text-muted">
                              {workflow.description || 'No description'}
                            </span>
                          </td>
                          <td>
                            <div className="d-flex gap-1">
                              <Badge bg="info">
                                {workflow.steps ? workflow.steps.length : 0} steps
                              </Badge>
                              <Badge bg="secondary">
                                {workflow.steps ? 
                                  workflow.steps.reduce((total, step) => total + (step.tasks ? step.tasks.length : 0), 0) : 0} tasks
                              </Badge>
                              {workflow.variables && Object.keys(workflow.variables).length > 0 && (
                                <Badge bg="warning" title="This workflow has variables">
                                  📝 {Object.keys(workflow.variables).length} vars
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td>{formatDate(workflow.created_at)}</td>
                          <td>{formatDate(workflow.updated_at)}</td>
                          <td>
                            <div className="btn-group" role="group">
                              <Button
                                as={Link}
                                to={`/workflows/run/${workflow.id}`}
                                variant="outline-success"
                                size="sm"
                                title="Run Workflow"
                              >
                                ▶️
                              </Button>
                              <Button
                                as={!workflow.program_name && !isSuperuser() ? "span" : Link}
                                to={!workflow.program_name && !isSuperuser() ? undefined : `/workflows/edit/${workflow.id}`}
                                variant={!workflow.program_name && !isSuperuser() ? "outline-secondary" : "outline-primary"}
                                size="sm"
                                title={!workflow.program_name && !isSuperuser() ? "Only superusers can edit global workflows" : "Edit Workflow"}
                                disabled={!workflow.program_name && !isSuperuser()}
                                style={!workflow.program_name && !isSuperuser() ? {pointerEvents: 'none'} : {}}
                              >
                                ✏️
                              </Button>
                              <Button
                                variant="outline-danger"
                                size="sm"
                                onClick={() => handleDeleteClick(workflow)}
                                title={!workflow.program_name && !isSuperuser() ? "Only superusers can delete global workflows" : "Delete Workflow"}
                                disabled={!workflow.program_name && !isSuperuser()}
                              >
                                🗑️
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Confirm Delete</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {workflowToDelete && (
            <p>
              Are you sure you want to delete the workflow <strong>"{workflowToDelete.name}"</strong>?
              This action cannot be undone.
            </p>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
            Cancel
          </Button>
          <Button 
            variant="danger" 
            onClick={handleDeleteConfirm}
            disabled={deleting}
          >
            {deleting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Deleting...
              </>
            ) : (
              'Delete Workflow'
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Batch Delete Confirmation Modal */}
      <Modal show={showBatchDeleteModal} onHide={() => setShowBatchDeleteModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Delete Workflows</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Are you sure you want to delete {selectedItems.size} selected workflow(s)?</p>
          <p className="text-danger">
            <i className="bi bi-exclamation-triangle"></i>
            This action cannot be undone.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowBatchDeleteModal(false)}>
            Cancel
          </Button>
          <Button 
            variant="danger" 
            onClick={handleBatchDelete}
            disabled={batchDeleting}
          >
            {batchDeleting ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Deleting...
              </>
            ) : (
              <>
                🗑️ Delete {selectedItems.size} Workflow(s)
              </>
            )}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default WorkflowList;