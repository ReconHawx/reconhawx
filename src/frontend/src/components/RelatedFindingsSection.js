import React from 'react';
import { Card, Table, Spinner, Alert, Badge, Button } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { formatDate } from '../utils/dateUtils';
import { getSeverityBadgeVariant } from '../utils/severityUtils';

function FindingsTable({ items, type, viewAllPath }) {
  if (!items || items.length === 0) {
    return null;
  }

  const isNuclei = type === 'nuclei';
  const detailBase = isNuclei ? '/findings/nuclei/details' : '/findings/wpscan/details';
  const listBase = isNuclei ? '/findings/nuclei' : '/findings/wpscan';

  return (
    <div className="mb-3">
      <div className="d-flex justify-content-between align-items-center mb-2">
        <h6 className="mb-0">{isNuclei ? 'Nuclei' : 'WPScan'}</h6>
        {viewAllPath && (
          <Link to={viewAllPath || listBase} className="small">
            View all
          </Link>
        )}
      </div>
      <Table striped bordered hover responsive size="sm" className="mb-0">
        <thead>
          <tr>
            <th>Severity</th>
            <th>{isNuclei ? 'Finding' : 'Title'}</th>
            <th>{isNuclei ? 'Template' : 'Item'}</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <Badge bg={getSeverityBadgeVariant(item.severity)}>{item.severity || 'unknown'}</Badge>
              </td>
              <td className="small">{item.name || item.title || '-'}</td>
              <td className="small">
                <code>{isNuclei ? item.template_id || '-' : item.item_name || '-'}</code>
              </td>
              <td className="small text-muted">{item.created_at ? formatDate(item.created_at) : '-'}</td>
              <td>
                <Button
                  as={Link}
                  to={`${detailBase}?id=${encodeURIComponent(item.id)}`}
                  variant="outline-primary"
                  size="sm"
                >
                  View
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
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
          <>
            <FindingsTable
              items={nucleiItems}
              type="nuclei"
              viewAllPath={nucleiTotal > nucleiItems.length ? nucleiViewAllPath : null}
            />
            <FindingsTable
              items={wpscanItems}
              type="wpscan"
              viewAllPath={wpscanTotal > wpscanItems.length ? wpscanViewAllPath : null}
            />
          </>
        )}
      </Card.Body>
    </Card>
  );
}

export default RelatedFindingsSection;
