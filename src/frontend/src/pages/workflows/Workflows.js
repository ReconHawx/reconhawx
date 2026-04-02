import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Button, Badge, Alert, Spinner } from 'react-bootstrap';
import { Link, useSearchParams } from 'react-router-dom';
import { workflowAPI } from '../../services/api';
import SingleTaskModal from '../../components/workflow/SingleTaskModal';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function Workflows() {
  usePageTitle(formatPageTitle('Workflows'));
  const [searchParams, setSearchParams] = useSearchParams();
  const [recentExecutions, setRecentExecutions] = useState([]);
  const [savedWorkflows, setSavedWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({
    totalWorkflows: 0,
    runningExecutions: 0,
    completedToday: 0
  });

  // Single task modal state
  const [showSingleTaskModal, setShowSingleTaskModal] = useState(false);

  useEffect(() => {
    loadDashboardData();
  }, []);

  // Handle query parameter for single task modal
  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab === 'single-task') {
      setShowSingleTaskModal(true);
      // Clear the query parameter to avoid reopening on refresh
      setSearchParams(new URLSearchParams());
    }
  }, [searchParams, setSearchParams]);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const [workflowsResponse, statusResponse] = await Promise.all([
        workflowAPI.getWorkflows(),
        workflowAPI.getWorkflowStatus(1, 10, null, 'started_at', 'desc') // Get last 10 executions
      ]);

      const workflows = workflowsResponse.workflows || [];
      const executions = statusResponse.executions || [];

      setSavedWorkflows(workflows);
      setRecentExecutions(executions);

      // Calculate stats
      const today = new Date().toDateString();
      const runningCount = executions.filter(e => e.status === 'running').length;
      const completedTodayCount = executions.filter(e => 
        e.completed_at && new Date(e.completed_at).toDateString() === today
      ).length;

      setStats({
        totalWorkflows: workflows.length,
        runningExecutions: runningCount,
        completedToday: completedTodayCount
      });

      setError(null);
    } catch (err) {
      setError('Failed to load workflow data: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const statusMap = {
      'running': 'primary',
      'completed': 'success',
      'failed': 'danger',
      'pending': 'warning',
      'cancelled': 'secondary'
    };
    return statusMap[status?.toLowerCase()] || 'secondary';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  if (loading) {
    return (
      <Container fluid className="p-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <p className="mt-2">Loading workflow dashboard...</p>
        </div>
      </Container>
    );
  }

  return (
    <Container fluid className="p-4">
      <Row className="mb-4">
        <Col>
          <h1>🔄 Workflows</h1>
          <p className="text-muted">Manage and monitor your reconnaissance workflows</p>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Stats Cards */}
      <Row className="mb-4">
        <Col md={4}>
          <Card className="text-center">
            <Card.Body>
              <h2 className="text-primary">{stats.totalWorkflows}</h2>
              <p className="mb-0">Saved Workflows</p>
            </Card.Body>
          </Card>
        </Col>
        <Col md={4}>
          <Card className="text-center">
            <Card.Body>
              <h2 className="text-warning">{stats.runningExecutions}</h2>
              <p className="mb-0">Currently Running</p>
            </Card.Body>
          </Card>
        </Col>
        <Col md={4}>
          <Card className="text-center">
            <Card.Body>
              <h2 className="text-success">{stats.completedToday}</h2>
              <p className="mb-0">Completed Today</p>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Quick Actions */}
      <Row className="mb-4">
        <Col>
          <Card>
            <Card.Header>
              <h5 className="mb-0">Quick Actions</h5>
            </Card.Header>
            <Card.Body>
              <div className="d-grid gap-2 d-md-flex">
                <Button as={Link} to="/workflows/run" variant="success" size="lg">
                  ▶️ Run Workflow
                </Button>
                <Button
                  variant="warning"
                  size="lg"
                  onClick={() => setShowSingleTaskModal(true)}
                >
                  🔧 Run Single Task
                </Button>
                <Button as={Link} to="/workflows/list" variant="primary" size="lg">
                  📋 Manage Workflows
                </Button>
                <Button as={Link} to="/workflows/create" variant="outline-primary" size="lg">
                  ➕ Create New
                </Button>
                <Button as={Link} to="/workflows/status" variant="outline-secondary" size="lg">
                  📊 View Status
                </Button>
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        {/* Recent Workflows */}
        <Col md={6}>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">Recent Workflows</h5>
              <Button as={Link} to="/workflows/list" variant="outline-primary" size="sm">
                View All
              </Button>
            </Card.Header>
            <Card.Body>
              {savedWorkflows.length === 0 ? (
                <p className="text-muted text-center">
                  No workflows found.{' '}
                  <Link to="/workflows/create">Create your first workflow</Link>
                </p>
              ) : (
                <div>
                  {savedWorkflows.slice(0, 5).map((workflow) => (
                    <div key={workflow.id} className="d-flex justify-content-between align-items-center py-2 border-bottom">
                      <div>
                        <strong>{workflow.name}</strong>
                        <br />
                        <small className="text-muted">
                          <Badge bg="primary" className="me-1">{workflow.program_name}</Badge>
                          {workflow.steps ? workflow.steps.reduce((total, step) => total + (step.tasks ? step.tasks.length : 0), 0) : 0} tasks
                        </small>
                      </div>
                      <div>
                        <Button
                          as={Link}
                          to={`/workflows/run/${workflow.id}`}
                          variant="outline-success"
                          size="sm"
                        >
                          ▶️ Run
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>

        {/* Recent Executions */}
        <Col md={6}>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">Recent Executions</h5>
              <Button as={Link} to="/workflows/status" variant="outline-primary" size="sm">
                View All
              </Button>
            </Card.Header>
            <Card.Body>
              {recentExecutions.length === 0 ? (
                <p className="text-muted text-center">
                  No recent executions.{' '}
                  <Link to="/workflows/run">Run a workflow</Link>
                </p>
              ) : (
                <div>
                  {recentExecutions.slice(0, 5).map((execution) => (
                    <div key={execution.id} className="d-flex justify-content-between align-items-center py-2 border-bottom">
                      <div>
                        <strong>{execution.workflow_name}</strong>
                        <br />
                        <small className="text-muted">
                          <Badge bg="primary" className="me-1">{execution.program_name}</Badge>
                          {formatDate(execution.started_at)}
                        </small>
                      </div>
                      <div>
                        <Badge bg={getStatusBadge(execution.status)}>
                          {execution.status || 'unknown'}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Single Task Modal */}
      <SingleTaskModal
        show={showSingleTaskModal}
        onHide={() => setShowSingleTaskModal(false)}
        onSuccess={(response) => {
          // Optionally refresh the recent executions or show a success message
        }}
      />
    </Container>
  );
}

export default Workflows;