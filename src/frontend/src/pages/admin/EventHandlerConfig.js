import React, { useState, useEffect } from 'react';
import {
  Container,
  Card,
  Button,
  Alert,
  Spinner,
  Table,
  Modal,
  Badge
} from 'react-bootstrap';
import { adminAPI } from '../../services/api';
import EventHandlerForm from '../../components/EventHandlerForm';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

function EventHandlerConfig() {
  usePageTitle(formatPageTitle('Event Handler Config'));
  const [handlers, setHandlers] = useState([]);
  const [systemHandlers, setSystemHandlers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingIndex, setEditingIndex] = useState(null); // null = add new
  const [editingHandler, setEditingHandler] = useState(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError('');
      const [globalRes, systemRes] = await Promise.all([
        adminAPI.getEventHandlerConfig(),
        adminAPI.getEventHandlerSystemConfig()
      ]);
      setHandlers(globalRes.handlers || []);
      setSystemHandlers(systemRes.handlers || []);
    } catch (err) {
      setError('Failed to load event handler config: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      await adminAPI.updateEventHandlerConfig(handlers);
      setSuccess('Event handler config saved successfully');
    } catch (err) {
      setError('Failed to save: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  const handleResetToDefaults = async () => {
    if (!window.confirm('Reset to built-in defaults? This will replace the current global config (system handlers are unchanged).')) return;
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      const response = await adminAPI.getEventHandlerConfigDefaults();
      const defaults = response.handlers || [];
      setHandlers(defaults);
      await adminAPI.updateEventHandlerConfig(defaults);
      setSuccess(`Reset to defaults (${defaults.length} handlers)`);
    } catch (err) {
      setError('Failed to reset: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  const openEditModal = (index) => {
    setEditingIndex(index);
    setEditingHandler(JSON.parse(JSON.stringify(handlers[index])));
    setError('');
    setShowEditModal(true);
  };

  const handleEditSave = () => {
    if (!editingHandler?.id?.trim()) {
      setError('Handler ID is required');
      return;
    }
    if (!(editingHandler?.actions?.length > 0)) {
      setError('At least one action is required');
      return;
    }
    setError('');
    const newHandlers = [...handlers];
    if (editingIndex !== null) {
      newHandlers[editingIndex] = editingHandler;
    } else {
      newHandlers.push(editingHandler);
    }
    setHandlers(newHandlers);
    setShowEditModal(false);
  };

  const handleAddHandler = () => {
    const newHandler = {
      id: 'new_handler',
      event_type: 'assets.subdomain.created',
      description: 'New handler',
      conditions: [],
      actions: [{ type: 'log', level: 'info', message_template: 'Event: {event_type}' }]
    };
    setEditingIndex(null);
    setEditingHandler(newHandler);
    setError('');
    setShowEditModal(true);
  };

  const handleRemoveHandler = (index) => {
    if (!window.confirm('Remove this handler?')) return;
    setHandlers(handlers.filter((_, i) => i !== index));
  };

  if (loading) {
    return (
      <Container className="py-4">
        <Spinner animation="border" /> Loading event handler config...
      </Container>
    );
  }

  return (
    <Container className="py-4">
      <h4 className="mb-4">Event Handler Configuration</h4>

      {error && <Alert variant="danger" onClose={() => setError('')} dismissible>{error}</Alert>}
      {success && <Alert variant="success" onClose={() => setSuccess('')} dismissible>{success}</Alert>}

      <Card className="mb-4">
        <Card.Header>
          <span>System handlers ({systemHandlers.length})</span>
        </Card.Header>
        <Card.Body>
          <p className="text-muted small mb-3">
            Mandatory handlers shipped with the API. They always run first and cannot be edited here or overridden by program managers.
            Change them in the API codebase (<code>src/api/app/config/system_event_handlers.yaml</code>).
          </p>
          <Table responsive size="sm" className="mb-0">
            <thead>
              <tr>
                <th>ID</th>
                <th>Event Type</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {systemHandlers.map((h, i) => (
                <tr key={i}>
                  <td><code>{h.id || '-'}</code></td>
                  <td><Badge bg="dark">{h.event_type || '-'}</Badge></td>
                  <td>{h.description || '-'}</td>
                </tr>
              ))}
            </tbody>
          </Table>
          {systemHandlers.length === 0 && (
            <p className="text-muted mb-0">No system handlers defined.</p>
          )}
        </Card.Body>
      </Card>

      <Card className="mb-4">
        <Card.Header className="d-flex justify-content-between align-items-center">
          <span>Global handlers ({handlers.length})</span>
          <div>
            <Button variant="outline-primary" size="sm" className="me-2" onClick={handleAddHandler}>
              Add Handler
            </Button>
            <Button variant="outline-secondary" size="sm" className="me-2" onClick={handleResetToDefaults} disabled={saving}>
              Reset to Defaults
            </Button>
            <Button variant="primary" size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </Card.Header>
        <Card.Body>
          <p className="text-muted small mb-3">
            Global handlers apply to every program (after system handlers). Program managers can add optional handlers on top; notification handlers are built from each program&apos;s notification settings.
          </p>
          <Table responsive size="sm">
            <thead>
              <tr>
                <th>ID</th>
                <th>Event Type</th>
                <th>Description</th>
                <th style={{ width: 100 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {handlers.map((h, i) => (
                <tr key={i}>
                  <td><code>{h.id || '-'}</code></td>
                  <td><Badge bg="secondary">{h.event_type || '-'}</Badge></td>
                  <td>{h.description || '-'}</td>
                  <td>
                    <Button variant="link" size="sm" className="p-0 me-2" onClick={() => openEditModal(i)}>Edit</Button>
                    <Button variant="link" size="sm" className="p-0 text-danger" onClick={() => handleRemoveHandler(i)}>Remove</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          {handlers.length === 0 && (
            <p className="text-muted">No handlers configured. Click &quot;Reset to Defaults&quot; to load built-in global handlers.</p>
          )}
        </Card.Body>
      </Card>

      <Modal show={showEditModal} onHide={() => setShowEditModal(false)} size="xl" scrollable>
        <Modal.Header closeButton>
          <Modal.Title>{editingIndex !== null ? 'Edit Handler' : 'Add Handler'}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {editingHandler && (
            <EventHandlerForm handler={editingHandler} onChange={setEditingHandler} />
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowEditModal(false)}>Cancel</Button>
          <Button variant="primary" onClick={handleEditSave}>Save</Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

export default EventHandlerConfig;
