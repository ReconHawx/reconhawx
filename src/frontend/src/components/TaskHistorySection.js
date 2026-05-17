import React, { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Row, Col, Card, Button, Table, Badge, Collapse, Spinner } from 'react-bootstrap';
import { formatDistanceToNow, parseISO } from 'date-fns';
import { taskHistoryAPI } from '../services/api';

const statusVariant = (status) => {
  if (!status) return 'secondary';
  const s = String(status).toLowerCase();
  if (s === 'success' || s === 'completed') return 'success';
  if (s === 'failed' || s === 'error') return 'danger';
  if (s === 'running' || s === 'pending') return 'warning';
  return 'secondary';
};

function TaskHistorySection({ assetType, assetId }) {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [initialLoadDone, setInitialLoadDone] = useState(false);

  const loadPage = useCallback(
    async (nextPage, append) => {
      if (!assetId) return;
      setLoading(true);
      setError(null);
      try {
        const data = await taskHistoryAPI.getForAsset(assetType, assetId, {
          page: nextPage,
          pageSize: 25,
        });
        const newItems = data.items || [];
        setPagination(data.pagination || null);
        if (append) {
          setItems((prev) => [...prev, ...newItems]);
        } else {
          setItems(newItems);
        }
        setPage(nextPage);
        setInitialLoadDone(true);
      } catch (e) {
        setError(e?.message || 'Failed to load task history');
        if (!append) setItems([]);
      } finally {
        setLoading(false);
      }
    },
    [assetType, assetId]
  );

  const toggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !initialLoadDone && assetId) {
      loadPage(1, false);
    }
  };

  const loadMore = () => {
    if (pagination?.has_next && !loading) {
      loadPage(page + 1, true);
    }
  };

  if (!assetId) {
    return null;
  }

  return (
    <Row className="mb-4">
      <Col>
        <Card className="rh-elevated-card">
          <Card.Header className="d-flex justify-content-between align-items-center">
            <h6 className="mb-0">Task running history</h6>
            <Button variant="outline-secondary" size="sm" onClick={toggle}>
              {expanded ? 'Hide' : 'Show'}
            </Button>
          </Card.Header>
          <Collapse in={expanded}>
            <Card.Body>
              {error && <div className="text-danger small mb-2">{error}</div>}
              {loading && items.length === 0 && (
                <div className="text-center py-3">
                  <Spinner animation="border" size="sm" />
                </div>
              )}
              {!loading && items.length === 0 && initialLoadDone && (
                <p className="text-muted small mb-0">No workflow tasks recorded for this asset.</p>
              )}
              {items.length > 0 && (
                <>
                  <Table responsive hover size="sm" className="mb-2">
                    <thead>
                      <tr>
                        <th>Task</th>
                        <th>When</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((row, idx) => (
                        <tr
                          key={`${row.execution_id}-${row.task_name}-${row.started_at}-${idx}`}
                          style={{ cursor: 'pointer' }}
                        >
                          <td>
                            <Link
                              to={`/workflows/status/${encodeURIComponent(row.execution_id)}`}
                              className="text-decoration-none"
                            >
                              {row.task_name || row.task_type || '—'}
                            </Link>
                          </td>
                          <td className="text-muted small">
                            {row.started_at
                              ? formatDistanceToNow(parseISO(row.started_at), {
                                  addSuffix: true,
                                })
                              : '—'}
                          </td>
                          <td>
                            {row.status ? (
                              <Badge bg={statusVariant(row.status)}>{row.status}</Badge>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                  {pagination?.has_next && (
                    <Button variant="outline-primary" size="sm" onClick={loadMore} disabled={loading}>
                      {loading ? 'Loading…' : 'Load more'}
                    </Button>
                  )}
                </>
              )}
            </Card.Body>
          </Collapse>
        </Card>
      </Col>
    </Row>
  );
}

export default TaskHistorySection;
