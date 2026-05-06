import React from 'react';
import { Card, Button } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { getAgeFromDate, truncateText } from '../dashboardUtils';

export default function LatestActivityList({
  title,
  items = [],
  emptyText = 'No items',
  programParam = '',
  viewAllTo,
  viewAllLabel = 'View all',
}) {
  return (
    <Card className="rh-elevated-card h-100">
      <Card.Header className="rh-card-header-table d-flex justify-content-between align-items-center">
        <h6 className="mb-0">{title}</h6>
      </Card.Header>
      <Card.Body className="d-flex flex-column pt-2">
        <div className="flex-grow-1">
          {items.length > 0 ? (
            <div className="list-group list-group-flush">
              {items.map((row) => (
                <div
                  key={row.key}
                  className="list-group-item px-0 py-2 d-flex justify-content-between align-items-center"
                >
                  <Link to={row.href} className="text-decoration-none flex-grow-1 me-2 text-truncate">
                    <small>{truncateText(row.label, 40)}</small>
                  </Link>
                  <div className="d-flex align-items-center gap-2 flex-shrink-0">
                    {row.right}
                    <span className="text-muted small">{getAgeFromDate(row.createdAt)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted text-center small mb-0 py-3">{emptyText}</p>
          )}
        </div>
        {viewAllTo && (
          <div className="mt-auto pt-2">
            <Button as={Link} to={`${viewAllTo}${programParam}`} variant="outline-primary" size="sm" className="w-100">
              {viewAllLabel}
            </Button>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
