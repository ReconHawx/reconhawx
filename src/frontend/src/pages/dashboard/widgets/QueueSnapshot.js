import React from 'react';
import { Card, Badge } from 'react-bootstrap';
import { formatInt } from '../dashboardUtils';

export default function QueueSnapshot({ queue = null, error = null }) {
  return (
    <Card className="rh-elevated-card h-100">
      <Card.Header className="rh-card-header-table">
        <h6 className="mb-0">Workflow queue</h6>
      </Card.Header>
      <Card.Body>
        {error && <p className="text-warning small mb-2">{error}</p>}
        {!queue && !error && <p className="text-muted small mb-0">Queue status unavailable.</p>}
        {queue && (
          <ul className="list-unstyled small mb-0">
            <li className="d-flex justify-content-between py-1 border-bottom">
              <span className="text-muted">Length</span>
              <span className="fw-medium">{formatInt(queue.queue_length)}</span>
            </li>
            <li className="d-flex justify-content-between py-1 border-bottom">
              <span className="text-muted">Capacity</span>
              <Badge bg={queue.has_capacity ? 'success' : 'warning'}>{queue.has_capacity ? 'Available' : 'Full'}</Badge>
            </li>
            <li className="d-flex justify-content-between py-1 border-bottom">
              <span className="text-muted">Est. wait</span>
              <span>{formatInt(queue.estimated_wait_time)}s</span>
            </li>
            <li className="d-flex justify-content-between py-1">
              <span className="text-muted">Queue</span>
              <span className="text-truncate ms-2" title={queue.queue_name}>
                {queue.queue_name || '—'}
              </span>
            </li>
            {queue.error && (
              <li className="text-danger pt-2 small">{queue.error}</li>
            )}
          </ul>
        )}
      </Card.Body>
    </Card>
  );
}
