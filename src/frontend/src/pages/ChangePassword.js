import React, { useState } from 'react';
import { Container, Row, Col, Card, Form, Button, Alert } from 'react-bootstrap';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import apiObject from '../services/api';

function ChangePassword() {
  const { user, updateUser } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const forced = Boolean(user?.must_change_password);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword.length < 4) {
      setError('New password must be at least 4 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.');
      return;
    }

    try {
      setSubmitting(true);
      const updated = await apiObject.auth.changeOwnPassword(currentPassword, newPassword);
      updateUser(updated);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === 'string' ? d : err.message || 'Could not change password');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container>
      <Row className="justify-content-center py-4">
        <Col md={6} lg={5}>
          <Card>
            <Card.Body>
              <Card.Title className="mb-3">Change password</Card.Title>
              {forced && (
                <Alert variant="warning">
                  You must set a new password before continuing.
                </Alert>
              )}
              {error && (
                <Alert variant="danger" className="small">
                  {error}
                </Alert>
              )}
              <Form onSubmit={handleSubmit}>
                <Form.Group className="mb-3">
                  <Form.Label>Current password</Form.Label>
                  <Form.Control
                    type="password"
                    autoComplete="current-password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    required
                  />
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Label>New password</Form.Label>
                  <Form.Control
                    type="password"
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={4}
                  />
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Label>Confirm new password</Form.Label>
                  <Form.Control
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    minLength={4}
                  />
                </Form.Group>
                <Button variant="primary" type="submit" disabled={submitting} className="w-100">
                  {submitting ? 'Saving…' : 'Update password'}
                </Button>
              </Form>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default ChangePassword;
