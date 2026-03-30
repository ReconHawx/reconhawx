import React from 'react';
import { Spinner, Container } from 'react-bootstrap';

/**
 * Loading fallback component for React.Suspense
 * Displays a centered spinner while lazy-loaded components are loading
 */
const LoadingFallback = () => {
    return (
        <Container className="d-flex justify-content-center align-items-center" style={{ minHeight: '400px' }}>
            <div className="text-center">
                <Spinner animation="border" role="status" variant="primary">
                    <span className="visually-hidden">Loading...</span>
                </Spinner>
                <p className="mt-3 text-muted">Loading...</p>
            </div>
        </Container>
    );
};

export default LoadingFallback;
