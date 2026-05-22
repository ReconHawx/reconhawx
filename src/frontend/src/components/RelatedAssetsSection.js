import React from 'react';
import { Card, Table, Spinner, Alert, Badge, Button } from 'react-bootstrap';
import { Link } from 'react-router-dom';

/**
 * @param {{ title?: string, groups: Array<{
 *   key: string,
 *   label: string,
 *   items?: Array,
 *   links?: Array<{ label: string, value: string, detailPath: string, listPath?: string }>,
 *   totalCount?: number,
 *   loading?: boolean,
 *   error?: string | null,
 *   columns?: Array<{ header: string, render: (item: any) => React.ReactNode }>,
 *   detailPath?: (item: any) => string,
 *   viewAllPath?: string,
 *   emptyMessage?: string,
 * }> }} props
 */
function RelatedAssetsSection({ title = 'Related Assets', groups = [] }) {
  const visibleGroups = groups.filter(
    (g) => g.loading || g.error || (g.links && g.links.length > 0) || (g.items && g.items.length > 0)
  );

  if (visibleGroups.length === 0) {
    return null;
  }

  return (
    <Card className="rh-elevated-card mb-4">
      <Card.Header>
        <h5 className="mb-0">{title}</h5>
      </Card.Header>
      <Card.Body>
        {visibleGroups.map((group, index) => (
          <div key={group.key} className={index > 0 ? 'mt-4 pt-3 border-top' : ''}>
            <div className="d-flex justify-content-between align-items-center mb-2">
              <h6 className="mb-0">{group.label}</h6>
              {group.viewAllPath && (group.totalCount ?? group.items?.length ?? 0) > (group.items?.length ?? 0) && (
                <Link to={group.viewAllPath} className="small">
                  View all {group.totalCount}
                </Link>
              )}
            </div>

            {group.loading ? (
              <div className="text-center py-3">
                <Spinner animation="border" size="sm" />
                <span className="ms-2 text-muted">Loading…</span>
              </div>
            ) : group.error ? (
              <Alert variant="warning" className="mb-0">
                {group.error}
              </Alert>
            ) : group.links && group.links.length > 0 ? (
              <div className="list-group list-group-flush">
                {group.links.map((link) => (
                  <div key={link.label} className="list-group-item px-0">
                    <div className="d-flex justify-content-between align-items-center">
                      <div>
                        <h6 className="mb-1">{link.label}</h6>
                        <p className="mb-1 small text-break">{link.value}</p>
                      </div>
                      <Link to={link.detailPath} className="btn btn-sm btn-outline-primary">
                        View
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            ) : group.items && group.items.length > 0 ? (
              <Table striped bordered hover responsive size="sm" className="mb-0">
                <thead>
                  <tr>
                    {(group.columns || []).map((col) => (
                      <th key={col.header}>{col.header}</th>
                    ))}
                    {group.detailPath && <th>Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {group.items.map((item) => (
                    <tr key={item.id || item.name || JSON.stringify(item)}>
                      {(group.columns || []).map((col) => (
                        <td key={col.header}>{col.render(item)}</td>
                      ))}
                      {group.detailPath && (
                        <td>
                          <Button
                            as={Link}
                            to={group.detailPath(item)}
                            variant="outline-primary"
                            size="sm"
                          >
                            View
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <Alert variant="info" className="mb-0">
                {group.emptyMessage || `No ${group.label.toLowerCase()} found.`}
              </Alert>
            )}
          </div>
        ))}
      </Card.Body>
    </Card>
  );
}

export function subdomainColumns() {
  return [
    {
      header: 'Name',
      render: (item) => <code>{item.name}</code>,
    },
    {
      header: 'Program',
      render: (item) =>
        item.program_name ? <Badge bg="primary">{item.program_name}</Badge> : <span className="text-muted">-</span>,
    },
    {
      header: 'Apex',
      render: (item) =>
        item.apex_domain ? <Badge bg="info">{item.apex_domain}</Badge> : <span className="text-muted">-</span>,
    },
  ];
}

export function urlColumns() {
  return [
    {
      header: 'URL',
      render: (item) => <code className="small text-break">{item.url}</code>,
    },
    {
      header: 'Status',
      render: (item) =>
        item.http_status_code != null ? (
          <Badge bg={item.http_status_code < 400 ? 'success' : 'warning'}>{item.http_status_code}</Badge>
        ) : (
          <span className="text-muted">-</span>
        ),
    },
  ];
}

export function serviceColumns() {
  return [
    {
      header: 'Service',
      render: (item) => <code>{item.ip}:{item.port}</code>,
    },
    {
      header: 'Name',
      render: (item) => item.service_name || <span className="text-muted">-</span>,
    },
    {
      header: 'Protocol',
      render: (item) => item.protocol || <span className="text-muted">-</span>,
    },
  ];
}

export default RelatedAssetsSection;
