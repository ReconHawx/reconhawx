import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Form, Button, Alert, Spinner } from 'react-bootstrap';
import { useAuth } from '../contexts/AuthContext';
import { Navigate, useLocation } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';
import { usePageTitle, formatPageTitle } from '../hooks/usePageTitle';

const BANNER_DARK = `${process.env.PUBLIC_URL}/banner_dark_transparent.png`;
const BANNER_LIGHT = `${process.env.PUBLIC_URL}/banner_light_transparent.png`;

function Login() {
  usePageTitle(formatPageTitle('Sign In'));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [validated, setValidated] = useState(false);
  const { login, isAuthenticated, isLoading, error, user } = useAuth();
  const location = useLocation();
  const { isLight } = useTheme();
  const bannerUrl = isLight ? BANNER_LIGHT : BANNER_DARK;

  const from = location.state?.from?.pathname || '/dashboard';

  useEffect(() => {
    if (isAuthenticated) {
      return;
    }
  }, [isAuthenticated]);

  if (isAuthenticated) {
    if (user?.must_change_password) {
      return <Navigate to="/change-password" replace />;
    }
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    
    if (form.checkValidity() === false) {
      event.stopPropagation();
      setValidated(true);
      return;
    }

    setValidated(true);
    await login(username, password);
  };

  if (isLoading) {
    return (
      <Container className="d-flex justify-content-center align-items-center min-vh-100">
        <Spinner animation="border" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
      </Container>
    );
  }

  return (
    <Container>
      <Row className="justify-content-center align-items-center min-vh-100 flex-column py-4">
        <Col xs={12} className="login-banner-wrap text-center mb-3 px-2">
          <img
            src={bannerUrl}
            alt="ReconHawx — Continuous Asset Enumeration"
            className="login-banner d-block mx-auto"
          />
        </Col>
        <Col md={6} lg={4}>
          <Card>
            <Card.Body>
              <p className="text-muted small text-center mb-3">
                Sign in to access the reconnaissance platform
              </p>

              {error && (
                <Alert variant="danger" className="mb-3">
                  {error}
                </Alert>
              )}

              <Form noValidate validated={validated} onSubmit={handleSubmit}>
                <Form.Group className="mb-3">
                  <Form.Label>Username</Form.Label>
                  <Form.Control
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    autoComplete="username"
                    placeholder="Enter your username"
                  />
                  <Form.Control.Feedback type="invalid">
                    Please provide a valid username.
                  </Form.Control.Feedback>
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>Password</Form.Label>
                  <Form.Control
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    placeholder="Enter your password"
                  />
                  <Form.Control.Feedback type="invalid">
                    Please provide a valid password.
                  </Form.Control.Feedback>
                </Form.Group>

                <div className="d-grid">
                  <Button 
                    variant="primary" 
                    type="submit" 
                    disabled={isLoading}
                    size="lg"
                  >
                    {isLoading ? (
                      <>
                        <Spinner
                          as="span"
                          animation="border"
                          size="sm"
                          role="status"
                          aria-hidden="true"
                          className="me-2"
                        />
                        Signing in...
                      </>
                    ) : (
                      'Sign In'
                    )}
                  </Button>
                </div>
              </Form>

              <div className="text-center mt-3">
                <small className="text-muted">
                  Contact your administrator for access credentials
                </small>
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default Login;