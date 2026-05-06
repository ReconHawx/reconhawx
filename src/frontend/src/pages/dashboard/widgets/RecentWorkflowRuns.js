import React from 'react';
import { Card, Table, Badge, ProgressBar } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { getAgeFromDate } from '../dashboardUtils';

function formatDuration(startedAt, completedAt) {
  if (!startedAt) return '—';
  const a = new Date(startedAt).getTime();
  const b = completedAt ? new Date(completedAt).getTime() : Date.now();
  const sec = Math.max(0, Math.floor((b - a) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

function statusVariant(st) {
  const s = (st || '').toLowerCase();
  if (s === 'success' || s === 'completed') return 'success';
  if (s === 'failed') return 'danger';
  if (s === 'running' || s === 'started') return 'primary';
  if (s === 'cancelled_waf' || s === 'partial_waf') return 'warning';
  return 'secondary';
}

export default function RecentWorkflowRuns({ executions = [], programParam = '' }) {
  return (
    <Card className="rh-elevated-card h-100">
      <Card.Header className="rh-card-header-table d-flex justify-content-between align-items-center">
        <h6 className="mb-0">Recent workflow runs</h6>
        <Link to={`/workflows/status${programParam}`} className="small">
          Status
        </Link>
      </Card.Header>
      <Card.Body className="p-0">
        {executions.length === 0 ? (
          <p className="text-muted small p-3 mb-0">No recent executions.</p>
        ) : (
          <Table responsive hover size="sm" className="mb-0 align-middle">
            <thead className="text-muted small">
              <tr>
                <th>Workflow</th>
                <th>Program</th>
                <th>Status</th>
                <th>Started</th>
                <th>Duration</th>
                <th className="d-none d-md-table-cell">Progress</th>
              </tr>
            </thead>
            <tbody>
              {executions.map((ex) => {
                const pct = ex.progress?.percentage ?? 0;
                return (
                  <tr key={ex.id}>
                    <td>
                      <Link to={`/workflows/status/${ex.id}`} className="text-decoration-none fw-medium">
                        {ex.workflow_name || ex.id}
                      </Link>
                    </td>
                    <td className="small text-muted">{ex.program_name || '—'}</td>
                    <td>
                      <Badge bg={statusVariant(ex.status)}>{ex.status || '—'}</Badge>
                    </td>
                    <td className="small text-muted">{getAgeFromDate(ex.started_at)}</td>
                    <td className="small">{formatDuration(ex.started_at, ex.completed_at)}</td>
                    <td className="d-none d-md-table-cell" style={{ minWidth: 100 }}>
                      <ProgressBar now={Math.min(100, Math.max(0, pct || 0))} style={{ height: 6 }} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card.Body>
    </Card>
  );
}
