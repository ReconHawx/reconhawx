import React from 'react';
import { Card, Button } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { formatInt } from '../dashboardUtils';

export default function BrokenLinksCard({ stats = null, programParam = '' }) {
  const s = stats?.data || stats || {};
  const total = s.total ?? s.total_findings ?? Object.values(s).reduce((a, v) => a + (typeof v === 'number' ? v : 0), 0);
  return (
    <Card className="rh-elevated-card h-100">
      <Card.Header className="rh-card-header-table">
        <h6 className="mb-0">Broken links</h6>
      </Card.Header>
      <Card.Body className="d-flex flex-column">
        <p className="small text-muted mb-2">
          Summary of broken link findings{typeof total === 'number' ? (
            <> ({formatInt(total)} total)</>
          ) : null}
          .
        </p>
        {s && typeof s === 'object' && !Array.isArray(s) && (
          <ul className="list-unstyled small mb-3">
            {Object.entries(s)
              .filter(([k, v]) => typeof v === 'number' && k !== 'total' && k !== 'total_findings')
              .slice(0, 6)
              .map(([k, v]) => (
                <li key={k} className="d-flex justify-content-between py-1">
                  <span className="text-muted text-capitalize">{k.replace(/_/g, ' ')}</span>
                  <span>{formatInt(v)}</span>
                </li>
              ))}
          </ul>
        )}
        <Button as={Link} to={`/findings/broken-links${programParam}`} variant="outline-warning" size="sm" className="w-100 mt-auto">
          Open findings
        </Button>
      </Card.Body>
    </Card>
  );
}
