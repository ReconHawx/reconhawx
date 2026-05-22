import React from 'react';
import { Card, Row, Col, Spinner, Alert } from 'react-bootstrap';
import { Link } from 'react-router-dom';

function columnSize(count) {
  if (count <= 1) return { xs: 12 };
  if (count === 2) return { xs: 12, md: 6 };
  if (count === 3) return { xs: 12, sm: 6, lg: 4 };
  if (count === 4) return { xs: 12, sm: 6, lg: 3 };
  return { xs: 12, sm: 6, md: 4, lg: 2 };
}

/**
 * @param {{ title?: string, groups: Array<{
 *   key: string,
 *   label: string,
 *   entries?: Array<{ text: string, detailPath: string }>,
 *   totalCount?: number,
 *   loading?: boolean,
 *   error?: string | null,
 *   viewAllPath?: string,
 *   emptyMessage?: string,
 * }> }} props
 */
function RelatedAssetsSection({ title = 'Related Assets', groups = [] }) {
  const visibleGroups = groups.filter(
    (g) => g.loading || g.error || (g.entries && g.entries.length > 0)
  );

  if (visibleGroups.length === 0) {
    return null;
  }

  const colProps = columnSize(visibleGroups.length);

  return (
    <Card className="rh-elevated-card mb-4">
      <Card.Header>
        <h5 className="mb-0">{title}</h5>
      </Card.Header>
      <Card.Body>
        <Row>
          {visibleGroups.map((group) => (
            <Col key={group.key} {...colProps} className="mb-3">
              <div className="d-flex justify-content-between align-items-center mb-2">
                <h6 className="mb-0">{group.label}</h6>
                {group.viewAllPath &&
                  (group.totalCount ?? group.entries?.length ?? 0) >
                    (group.entries?.length ?? 0) && (
                    <Link to={group.viewAllPath} className="small">
                      View all {group.totalCount}
                    </Link>
                  )}
              </div>

              {group.loading ? (
                <div className="text-center py-2">
                  <Spinner animation="border" size="sm" />
                  <span className="ms-2 text-muted small">Loading…</span>
                </div>
              ) : group.error ? (
                <Alert variant="warning" className="mb-0 py-2 small">
                  {group.error}
                </Alert>
              ) : group.entries && group.entries.length > 0 ? (
                <ul className="list-unstyled mb-0 small">
                  {group.entries.map((entry) => (
                    <li key={`${entry.detailPath}-${entry.text}`} className="mb-1">
                      <Link
                        to={entry.detailPath}
                        className="text-break"
                      >
                        <code className="small">{entry.text}</code>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <Alert variant="info" className="mb-0 py-2 small">
                  {group.emptyMessage || `No ${group.label.toLowerCase()} found.`}
                </Alert>
              )}
            </Col>
          ))}
        </Row>
      </Card.Body>
    </Card>
  );
}

export default RelatedAssetsSection;
