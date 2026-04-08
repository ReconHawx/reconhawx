import React, { useState, useEffect, useCallback } from 'react';
import { 
  Container, 
  Row, 
  Col, 
  Card, 
  Table, 
  Button, 
  Modal, 
  Form, 
  Alert, 
  Spinner, 
  Badge,
  InputGroup
} from 'react-bootstrap';
import { userManagementAPI, programAPI } from '../../services/api';
import ApiTokenManagement from '../../components/ApiTokenManagement';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function UserManagement() {
  usePageTitle(formatPageTitle('User Management'));
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [programs, setPrograms] = useState([]);
  
  const limit = 25;

  // Form states
  const [createForm, setCreateForm] = useState({
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    rf_uhash: '',
    hackerone_api_token: '',
    hackerone_api_user: '',
    intigriti_api_token: '',
    roles: ['user'],
    program_permissions: {},
    is_superuser: false,
    is_active: true,
    force_password_change: true,
  });
  
  const [editForm, setEditForm] = useState({
    email: '',
    first_name: '',
    last_name: '',
    rf_uhash: '',
    hackerone_api_token: '',
    hackerone_api_user: '',
    intigriti_api_token: '',
    roles: ['user'],
    program_permissions: {},
    is_superuser: false,
    is_active: true
  });
  
  const [passwordForm, setPasswordForm] = useState({
    new_password: '',
    confirm_password: '',
    force_password_change: false,
  });

  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const response = await userManagementAPI.getUsers(currentPage, limit, searchTerm);
      setUsers(response.users);
      setTotalUsers(response.total);
    } catch (err) {
      setError('Failed to load users: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  }, [currentPage, limit, searchTerm]);

  useEffect(() => {
    loadUsers();
    loadPrograms();
  }, [loadUsers]);

  const loadPrograms = async () => {
    try {
      const response = await programAPI.getAll();
      if (response.status === 'success' && response.programs) {
        setPrograms(response.programs);
      } else if (Array.isArray(response)) {
        setPrograms(response);
      }
    } catch (err) {
      console.error('Failed to load programs:', err);
      // Don't set error for programs as it's not critical for user management
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    
    if (!createForm.username || !createForm.password) {
      setError('Username and password are required');
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      
      await userManagementAPI.createUser(createForm);
      setSuccess('User created successfully');
      setShowCreateModal(false);
      setCreateForm({
        username: '',
        email: '',
        password: '',
        first_name: '',
        last_name: '',
        hackerone_api_token: '',
        hackerone_api_user: '',
        intigriti_api_token: '',
        roles: ['user'],
        program_permissions: {},
        is_superuser: false,
        is_active: true,
        rf_uhash: '',
        force_password_change: true,
      });
      loadUsers();
    } catch (err) {
      setError('Failed to create user: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditUser = async (e) => {
    e.preventDefault();
    
    if (!selectedUser) return;
    
    try {
      setActionLoading(true);
      setError('');
      
      const userId = selectedUser.id || selectedUser._id;
      if (!userId) {
        throw new Error('User ID is missing');
      }
      await userManagementAPI.updateUser(userId, editForm);
      setSuccess('User updated successfully');
      setShowEditModal(false);
      setSelectedUser(null);
      loadUsers();
    } catch (err) {
      setError('Failed to update user: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteUser = async (user) => {
    if (!window.confirm(`Are you sure you want to delete user "${user.username}"? This action cannot be undone.`)) {
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      
      const userId = user.id || user._id;
      if (!userId) {
        throw new Error('User ID is missing');
      }
      await userManagementAPI.deleteUser(userId);
      setSuccess('User deleted successfully');
      loadUsers();
    } catch (err) {
      setError('Failed to delete user: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    
    if (!selectedUser) return;
    
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setError('Passwords do not match');
      return;
    }
    
    if (passwordForm.new_password.length < 4) {
      setError('Password must be at least 4 characters long');
      return;
    }
    
    try {
      setActionLoading(true);
      setError('');
      
      const userId = selectedUser.id || selectedUser._id;
      if (!userId) {
        throw new Error('User ID is missing');
      }
      await userManagementAPI.changePassword(
        userId,
        passwordForm.new_password,
        passwordForm.force_password_change,
      );
      setSuccess('Password changed successfully');
      setShowPasswordModal(false);
      setSelectedUser(null);
      setPasswordForm({
        new_password: '',
        confirm_password: '',
        force_password_change: false,
      });
    } catch (err) {
      setError('Failed to change password: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const openEditModal = (user) => {
    setSelectedUser(user);
    setEditForm({
      email: user.email || '',
      first_name: user.first_name || '',
      last_name: user.last_name || '',
      roles: user.roles || ['user'],
      program_permissions: user.program_permissions || {},
      is_superuser: user.is_superuser,
      is_active: user.is_active,
      rf_uhash: user.rf_uhash || '',
      hackerone_api_token: user.hackerone_api_token || '',
      hackerone_api_user: user.hackerone_api_user || '',
      intigriti_api_token: user.intigriti_api_token || ''
    });
    setShowEditModal(true);
  };

  const openPasswordModal = (user) => {
    setSelectedUser(user);
    setPasswordForm({
      new_password: '',
      confirm_password: '',
      force_password_change: false,
    });
    setShowPasswordModal(true);
  };

  // Program permissions helper functions
  const handleProgramPermissionToggle = (programName, permissionLevel, isCreate = false) => {
    const form = isCreate ? createForm : editForm;
    const setForm = isCreate ? setCreateForm : setEditForm;
    
    const currentPermissions = form.program_permissions || {};
    let newPermissions = { ...currentPermissions };
    
    if (newPermissions[programName]) {
      // If program already has permission, remove it
      delete newPermissions[programName];
    } else {
      // Add permission with specified level
      newPermissions[programName] = permissionLevel;
    }
    
    setForm({ ...form, program_permissions: newPermissions });
  };

  const handlePermissionLevelChange = (programName, newLevel, isCreate = false) => {
    const form = isCreate ? createForm : editForm;
    const setForm = isCreate ? setCreateForm : setEditForm;
    
    const currentPermissions = form.program_permissions || {};
    const newPermissions = { ...currentPermissions, [programName]: newLevel };
    
    setForm({ ...form, program_permissions: newPermissions });
  };

  const isUserSuperuserOrAdmin = (user) => {
    return user?.is_superuser || (user?.roles && user.roles.includes('admin'));
  };

  const getUserRoleBadge = (user) => {
    if (user.is_superuser) {
      return <Badge bg="danger">Superuser</Badge>;
    } else if (user.roles && user.roles.includes('admin')) {
      return <Badge bg="warning">Admin</Badge>;
    } else {
      return <Badge bg="secondary">User</Badge>;
    }
  };

  const getStatusBadge = (user) => {
    return user.is_active ? 
      <Badge bg="success">Active</Badge> : 
      <Badge bg="danger">Inactive</Badge>;
  };

  const totalPages = Math.ceil(totalUsers / limit);

  return (
    <Container fluid className="mt-4">
      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h4>👥 User Management</h4>
              <Button 
                variant="primary" 
                onClick={() => setShowCreateModal(true)}
                disabled={actionLoading}
              >
                ➕ Create User
              </Button>
            </Card.Header>
            
            <Card.Body>
              {error && (
                <Alert variant="danger" onClose={() => setError('')} dismissible>
                  {error}
                </Alert>
              )}
              
              {success && (
                <Alert variant="success" onClose={() => setSuccess('')} dismissible>
                  {success}
                </Alert>
              )}

              {/* Search Bar */}
              <Row className="mb-3">
                <Col md={6}>
                  <InputGroup>
                    <Form.Control
                      type="text"
                      placeholder="Search users by username, email, or name..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                    />
                    <Button 
                      variant="outline-secondary" 
                      onClick={() => setSearchTerm('')}
                      disabled={!searchTerm}
                    >
                      Clear
                    </Button>
                  </InputGroup>
                </Col>
                <Col md={6} className="text-end">
                  <small className="text-muted">
                    Showing {users.length} of {totalUsers} users
                  </small>
                </Col>
              </Row>

              {loading ? (
                <div className="text-center py-4">
                  <Spinner animation="border" role="status">
                    <span className="visually-hidden">Loading...</span>
                  </Spinner>
                </div>
              ) : (
                <div style={{ overflow: 'visible' }}>
                  <Table striped bordered hover responsive>
                    <thead>
                      <tr>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Name</th>
                        <th>Role</th>
                        <th>Programs</th>
                        <th>Status</th>
                        <th>Last Login</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => (
                        <tr key={user.id} style={{ minHeight: '60px' }}>
                          <td><strong>{user.username}</strong></td>
                          <td>{user.email || <span className="text-muted">-</span>}</td>
                          <td>
                            {user.first_name || user.last_name ? 
                              `${user.first_name || ''} ${user.last_name || ''}`.trim() : 
                              <span className="text-muted">-</span>
                            }
                          </td>
                          <td>{getUserRoleBadge(user)}</td>
                          <td>
                            {isUserSuperuserOrAdmin(user) ? (
                              <Badge bg="success" title="Full access to all programs">All Programs</Badge>
                            ) : user.program_permissions && Object.keys(user.program_permissions).length > 0 ? (
                              <div>
                                <Badge bg="info">{Object.keys(user.program_permissions).length} Program{Object.keys(user.program_permissions).length !== 1 ? 's' : ''}</Badge>
                                <div style={{ fontSize: '0.75em' }} className="text-muted">
                                  {Object.entries(user.program_permissions).slice(0, 2).map(([program, level]) => (
                                    <div key={program}>
                                      {program} ({level === 'manager' ? 'Manager' : 'Analyst'})
                                    </div>
                                  ))}
                                  {Object.keys(user.program_permissions).length > 2 && 
                                    <div>... +{Object.keys(user.program_permissions).length - 2} more</div>
                                  }
                                </div>
                              </div>
                            ) : (
                              <Badge bg="warning" title="No program access configured">No Access</Badge>
                            )}
                          </td>
                          <td>{getStatusBadge(user)}</td>
                          <td>
                            <small className="text-muted">
                              {user.last_login ? 
                                new Date(user.last_login).toLocaleDateString() : 
                                'Never'
                              }
                            </small>
                          </td>
                          <td style={{ minHeight: '60px', verticalAlign: 'middle' }}>
                            <div className="d-flex gap-1">
                              <Button
                                variant="outline-secondary"
                                size="sm"
                                onClick={() => openEditModal(user)}
                                disabled={actionLoading}
                              >
                                ✏️ Edit
                              </Button>
                              
                              <Button
                                variant="outline-info"
                                size="sm"
                                onClick={() => openPasswordModal(user)}
                                disabled={actionLoading}
                              >
                                🔑 Password
                              </Button>
                              
                              <Button
                                variant="outline-danger"
                                size="sm"
                                onClick={() => handleDeleteUser(user)}
                                disabled={actionLoading}
                              >
                                🗑️ Delete
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="d-flex justify-content-center mt-3">
                      <Button
                        variant="outline-primary"
                        disabled={currentPage === 1}
                        onClick={() => setCurrentPage(currentPage - 1)}
                      >
                        Previous
                      </Button>
                      <span className="mx-3 align-self-center">
                        Page {currentPage} of {totalPages}
                      </span>
                      <Button
                        variant="outline-primary"
                        disabled={currentPage === totalPages}
                        onClick={() => setCurrentPage(currentPage + 1)}
                      >
                        Next
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
        
        {/* <Col lg={4}>
          <ApiTokenManagement />
        </Col> */}
      </Row>

      {/* Create User Modal */}
      <Modal show={showCreateModal} onHide={() => setShowCreateModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Create New User</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleCreateUser}>
          <Modal.Body>
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Username *</Form.Label>
                  <Form.Control
                    type="text"
                    value={createForm.username}
                    onChange={(e) => setCreateForm({...createForm, username: e.target.value})}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Email</Form.Label>
                  <Form.Control
                    type="email"
                    value={createForm.email}
                    onChange={(e) => setCreateForm({...createForm, email: e.target.value})}
                  />
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>First Name</Form.Label>
                  <Form.Control
                    type="text"
                    value={createForm.first_name}
                    onChange={(e) => setCreateForm({...createForm, first_name: e.target.value})}
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Last Name</Form.Label>
                  <Form.Control
                    type="text"
                    value={createForm.last_name}
                    onChange={(e) => setCreateForm({...createForm, last_name: e.target.value})}
                  />
                </Form.Group>
              </Col>
            </Row>
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>RecordedFuture User Hash</Form.Label>
                  <Form.Control
                    type="text"
                    value={createForm.rf_uhash}
                    onChange={(e) => setCreateForm({...createForm, rf_uhash: e.target.value})}
                  />
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={12}>
                <Form.Group className="mb-3">
                  <Form.Label>HackerOne API Credentials</Form.Label>
                  <Row>
                    <Col md={6}>
                      <Form.Label className="text-muted" style={{ fontSize: '0.875rem' }}>Username</Form.Label>
                      <Form.Control
                        type="text"
                        value={createForm.hackerone_api_user}
                        onChange={(e) => setCreateForm({...createForm, hackerone_api_user: e.target.value})}
                        placeholder="HackerOne username"
                      />
                    </Col>
                    <Col md={6}>
                      <Form.Label className="text-muted" style={{ fontSize: '0.875rem' }}>API Token</Form.Label>
                      <Form.Control
                        type="password"
                        value={createForm.hackerone_api_token}
                        onChange={(e) => setCreateForm({...createForm, hackerone_api_token: e.target.value})}
                        placeholder="HackerOne API token"
                      />
                    </Col>
                  </Row>
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Intigriti API Credentials</Form.Label>
                  <Form.Control
                    type="text"
                    value={createForm.intigriti_api_token}
                    onChange={(e) => setCreateForm({...createForm, intigriti_api_token: e.target.value})}
                    placeholder="Intigriti API token"
                  />
                </Form.Group>
              </Col>
            </Row>
            <Form.Group className="mb-3">
              <Form.Label>Password *</Form.Label>
              <Form.Control
                type="password"
                value={createForm.password}
                onChange={(e) => setCreateForm({...createForm, password: e.target.value})}
                required
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                id="create-force-password-change"
                label="Force password change on first login"
                checked={createForm.force_password_change}
                onChange={(e) =>
                  setCreateForm({ ...createForm, force_password_change: e.target.checked })
                }
              />
            </Form.Group>
            
            <Row>
              <Col md={4}>
                <Form.Check
                  type="checkbox"
                  label="Active User"
                  checked={createForm.is_active}
                  onChange={(e) => setCreateForm({...createForm, is_active: e.target.checked})}
                />
              </Col>
              <Col md={4}>
                <Form.Check
                  type="checkbox"
                  label="Admin Role"
                  checked={createForm.roles.includes('admin')}
                  onChange={(e) => {
                    const newRoles = e.target.checked 
                      ? [...createForm.roles.filter(r => r !== 'admin'), 'admin']
                      : createForm.roles.filter(r => r !== 'admin');
                    setCreateForm({...createForm, roles: newRoles.length ? newRoles : ['user']});
                  }}
                />
              </Col>
              <Col md={4}>
                <Form.Check
                  type="checkbox"
                  label="Superuser"
                  checked={createForm.is_superuser}
                  onChange={(e) => setCreateForm({...createForm, is_superuser: e.target.checked})}
                />
              </Col>
            </Row>
            
            {/* Program Permissions - only show for non-superusers */}
            {!createForm.is_superuser && (
              <Row className="mt-3">
                <Col>
                  <Form.Group>
                    <Form.Label>Program Access Permissions</Form.Label>
                    <div className="border rounded p-3" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                      {programs.length === 0 ? (
                        <small className="text-muted">No programs available</small>
                      ) : (
                        programs.map(program => {
                          const programName = typeof program === 'string' ? program : program.name;
                          return (
                            <div key={programName} className="d-flex align-items-center mb-2">
                              <Form.Check
                                type="checkbox"
                                label={programName}
                                checked={createForm.program_permissions && createForm.program_permissions[programName] !== undefined}
                                onChange={() => handleProgramPermissionToggle(programName, 'analyst', true)}
                                className="me-3"
                              />
                              {createForm.program_permissions && createForm.program_permissions[programName] && (
                                <Form.Select
                                  size="sm"
                                  style={{ width: 'auto' }}
                                  value={createForm.program_permissions[programName] || 'analyst'}
                                  onChange={(e) => handlePermissionLevelChange(programName, e.target.value, true)}
                                >
                                  <option value="analyst">Analyst</option>
                                  <option value="manager">Manager</option>
                                </Form.Select>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                    <Form.Text className="text-muted">
                      {Object.keys(createForm.program_permissions || {}).length === 0
                        ? "No programs selected - user will have no access to any programs"
                        : `User has access to ${Object.keys(createForm.program_permissions).length} program(s)`}
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? 'Creating...' : 'Create User'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Edit User Modal */}
      <Modal show={showEditModal} onHide={() => setShowEditModal(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Edit User: {selectedUser?.username}</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleEditUser}>
          <Modal.Body>
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Email</Form.Label>
                  <Form.Control
                    type="email"
                    value={editForm.email}
                    onChange={(e) => setEditForm({...editForm, email: e.target.value})}
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>First Name</Form.Label>
                  <Form.Control
                    type="text"
                    value={editForm.first_name}
                    onChange={(e) => setEditForm({...editForm, first_name: e.target.value})}
                  />
                </Form.Group>
              </Col>
            </Row>
            
            <Form.Group className="mb-3">
              <Form.Label>Last Name</Form.Label>
              <Form.Control
                type="text"
                value={editForm.last_name}
                onChange={(e) => setEditForm({...editForm, last_name: e.target.value})}
              />
            </Form.Group>
            <Row>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>RecordedFuture User Hash</Form.Label>
                  <Form.Control
                    type="text"
                    value={editForm.rf_uhash}
                    onChange={(e) => setEditForm({...editForm, rf_uhash: e.target.value})}
                  />
                </Form.Group>
              </Col>
            </Row>
            
            <Row>
              <Col md={12}>
                <Form.Group className="mb-3">
                  <Form.Label>HackerOne API Credentials</Form.Label>
                  <Row>
                    <Col md={6}>
                      <Form.Label className="text-muted" style={{ fontSize: '0.875rem' }}>Username</Form.Label>
                      <Form.Control
                        type="text"
                        value={editForm.hackerone_api_user}
                        onChange={(e) => setEditForm({...editForm, hackerone_api_user: e.target.value})}
                        placeholder="HackerOne username"
                      />
                    </Col>
                    <Col md={6}>
                      <Form.Label className="text-muted" style={{ fontSize: '0.875rem' }}>API Token</Form.Label>
                      <Form.Control
                        type="password"
                        value={editForm.hackerone_api_token}
                        onChange={(e) => setEditForm({...editForm, hackerone_api_token: e.target.value})}
                        placeholder="HackerOne API token"
                      />
                    </Col>
                  </Row>
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group className="mb-3">
                  <Form.Label>Intigriti API Credentials</Form.Label>
                  <Form.Control
                    type="text"
                    value={editForm.intigriti_api_token}
                    onChange={(e) => setEditForm({...editForm, intigriti_api_token: e.target.value})}
                    placeholder="Intigriti API token"
                  />
                </Form.Group>
              </Col>
            </Row>
            <Row>
              <Col md={4}>
                <Form.Check
                  type="checkbox"
                  label="Active User"
                  checked={editForm.is_active}
                  onChange={(e) => setEditForm({...editForm, is_active: e.target.checked})}
                />
              </Col>
              <Col md={4}>
                <Form.Check
                  type="checkbox"
                  label="Admin Role"
                  checked={editForm.roles.includes('admin')}
                  onChange={(e) => {
                    const newRoles = e.target.checked 
                      ? [...editForm.roles.filter(r => r !== 'admin'), 'admin']
                      : editForm.roles.filter(r => r !== 'admin');
                    setEditForm({...editForm, roles: newRoles.length ? newRoles : ['user']});
                  }}
                />
              </Col>
              <Col md={4}>
                <Form.Check
                  type="checkbox"
                  label="Superuser"
                  checked={editForm.is_superuser}
                  onChange={(e) => setEditForm({...editForm, is_superuser: e.target.checked})}
                />
              </Col>
            </Row>
            
            {/* Program Permissions - only show for non-superusers */}
            {!editForm.is_superuser && (
              <Row className="mt-3">
                <Col>
                  <Form.Group>
                    <Form.Label>Program Access Permissions</Form.Label>
                    <div className="border rounded p-3" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                      {programs.length === 0 ? (
                        <small className="text-muted">No programs available</small>
                      ) : (
                        programs.map(program => {
                          const programName = typeof program === 'string' ? program : program.name;
                          return (
                            <div key={programName} className="d-flex align-items-center mb-2">
                              <Form.Check
                                type="checkbox"
                                label={programName}
                                checked={editForm.program_permissions && editForm.program_permissions[programName] !== undefined}
                                onChange={() => handleProgramPermissionToggle(programName, 'analyst', false)}
                                className="me-3"
                              />
                              {editForm.program_permissions && editForm.program_permissions[programName] && (
                                <Form.Select
                                  size="sm"
                                  style={{ width: 'auto' }}
                                  value={editForm.program_permissions[programName] || 'analyst'}
                                  onChange={(e) => handlePermissionLevelChange(programName, e.target.value, false)}
                                >
                                  <option value="analyst">Analyst</option>
                                  <option value="manager">Manager</option>
                                </Form.Select>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                    <Form.Text className="text-muted">
                      {Object.keys(editForm.program_permissions || {}).length === 0
                        ? "No programs selected - user will have no access to any programs"
                        : `User has access to ${Object.keys(editForm.program_permissions).length} program(s)`}
                    </Form.Text>
                  </Form.Group>
                </Col>
              </Row>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? 'Updating...' : 'Update User'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Change Password Modal */}
      <Modal show={showPasswordModal} onHide={() => setShowPasswordModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Change Password: {selectedUser?.username}</Modal.Title>
        </Modal.Header>
        <Form onSubmit={handleChangePassword}>
          <Modal.Body>
            <Form.Group className="mb-3">
              <Form.Label>New Password</Form.Label>
              <Form.Control
                type="password"
                value={passwordForm.new_password}
                onChange={(e) => setPasswordForm({...passwordForm, new_password: e.target.value})}
                required
              />
            </Form.Group>
            
            <Form.Group className="mb-3">
              <Form.Label>Confirm Password</Form.Label>
              <Form.Control
                type="password"
                value={passwordForm.confirm_password}
                onChange={(e) => setPasswordForm({...passwordForm, confirm_password: e.target.value})}
                required
              />
            </Form.Group>

            <Form.Check
              type="checkbox"
              id="reset-password-force-change"
              label="Require password change on next login"
              checked={passwordForm.force_password_change}
              onChange={(e) =>
                setPasswordForm({
                  ...passwordForm,
                  force_password_change: e.target.checked,
                })
              }
            />
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowPasswordModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={actionLoading}>
              {actionLoading ? 'Changing...' : 'Change Password'}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </Container>
  );
}

export default UserManagement;