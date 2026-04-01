import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Spinner, Container } from 'react-bootstrap';

function ProtectedRoute({ children, requireSuperuser = false, requireAdmin = false, requiredPermission = null }) {
  const { isAuthenticated, isLoading, isSuperuser, isAdmin, hasPermission, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <Container className="d-flex justify-content-center align-items-center min-vh-100">
        <Spinner animation="border" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
      </Container>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (user?.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  if (requireSuperuser && !isSuperuser()) {
    return (
      <Container className="mt-4">
        <div className="alert alert-danger">
          <h4>Access Denied</h4>
          <p>This feature requires superuser privileges. Contact your administrator for access.</p>
        </div>
      </Container>
    );
  }

  if (requireAdmin && !isAdmin()) {
    return (
      <Container className="mt-4">
        <div className="alert alert-danger">
          <h4>Access Denied</h4>
          <p>This feature requires administrative privileges. Contact your administrator for access.</p>
        </div>
      </Container>
    );
  }

  if (requiredPermission && !hasPermission(requiredPermission)) {
    return (
      <Container className="mt-4">
        <div className="alert alert-danger">
          <h4>Access Denied</h4>
          <p>You don't have the required permission: {requiredPermission}</p>
        </div>
      </Container>
    );
  }

  return children;
}

export default ProtectedRoute;