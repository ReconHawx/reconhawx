import React from 'react';
import { Card, Row, Col, Spinner, Alert } from 'react-bootstrap';
import { Link } from 'react-router-dom';

function FindingsColumn({ items, type, viewAllPath }) {
  const isNuclei = type === 'nuclei';
  const detailBase = isNuclei ? '/findings/nuclei/details' : '/findings/wpscan/details';
  const label = isNuclei ? 'Nuclei' : 'WPScan';

  if (!items || items.length === 0) {
    return null;
  }

  return (
    <Col xs={12} md={6} className="mb-3 mb-md-0">
      <div className="d-flex justify-content-between align-items-center mb-2">
        <h6 className="mb-0">{label}</h6>
        {viewAllPath && (
          <Link to={viewAllPath} className="small">
            View all
          </Link>
        )}
      </div>
      <ul className="list-unstyled mb-0 small">
        {items.map((item) => (
          <li key={item.id} className="mb-1">
            <Link to={`${detailBase}?id=${encodeURIComponent(item.id)}`}>
              {item.name || item.title || '-'}
            </Link>
          </li>
        ))}
      </ul>
    </Col>
  );
}

function RelatedFindingsSection({
  nucleiItems = [],
  wpscanItems = [],
  nucleiTotal = 0,
  wpscanTotal = 0,
  nucleiViewAllPath,
  wpscanViewAllPath,
  loading = false,
  error = null,
}) {
  const hasFindings = nucleiItems.length > 0 || wpscanItems.length > 0;

  if (!loading && !error && !hasFindings) {
    return null;
  }

  return (
    <Card className="rh-elevated-card mb-4">
      <Card.Header>
        <h5 className="mb-0">Related Findings</h5>
      </Card.Header>
      <Card.Body>
        {loading ? (
          <div className="text-center py-3">
            <Spinner animation="border" size="sm" />
            <span className="ms-2 text-muted">Loading related findings…</span>
          </div>
        ) : error ? (
          <Alert variant="warning" className="mb-0">
            {error}
          </Alert>
        ) : !hasFindings ? (
          <Alert variant="info" className="mb-0">
            No related findings found.
          </Alert>
        ) : (
          <Row>
            <FindingsColumn
              items={nucleiItems}
              type="nuclei"
              viewAllPath={nucleiTotal > nucleiItems.length ? nucleiViewAllPath : null}
            />
            <FindingsColumn
              items={wpscanItems}
              type="wpscan"
              viewAllPath={wpscanTotal > wpscanItems.length ? wpscanViewAllPath : null}
            />
          </Row>
        )}
      </Card.Body>
    </Card>
  );
}

export default RelatedFindingsSection;
