import React from 'react';
import { Card, Button } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { formatInt } from '../dashboardUtils';

export default function TopTechCard({ summary = null, programParam = '' }) {
  const items = summary?.items || [];
  return (
    <Card className="rh-elevated-card h-100">
      <Card.Header className="rh-card-header-table d-flex justify-content-between align-items-center">
        <h6 className="mb-0">Top technologies</h6>
        <span className="text-muted small">{formatInt(summary?.pagination?.total_items ?? items.length)}</span>
      </Card.Header>
      <Card.Body className="d-flex flex-column">
        {items.length === 0 ? (
          <p className="text-muted small mb-0">No technology data.</p>
        ) : (
          <ul className="list-unstyled small mb-3 flex-grow-1">
            {items.slice(0, 8).map((row) => (
              <li key={row.name || row.technology} className="d-flex justify-content-between py-1 border-bottom">
                <span className="text-truncate me-2" title={row.name}>
                  {row.name || row.technology}
                </span>
                <span className="text-muted flex-shrink-0">{formatInt(row.count)}</span>
              </li>
            ))}
          </ul>
        )}
        <Button as={Link} to={`/assets/urls${programParam}`} variant="outline-secondary" size="sm" className="w-100">
          Browse URLs
        </Button>
      </Card.Body>
    </Card>
  );
}
