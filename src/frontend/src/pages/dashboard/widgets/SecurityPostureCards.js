import React from 'react';
import { Row, Col, Card, Badge, ProgressBar } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { formatInt, buildDashboardListHref } from '../dashboardUtils';

function SeverityBar({ nuclei }) {
  const c = nuclei?.critical || 0;
  const h = nuclei?.high || 0;
  const m = nuclei?.medium || 0;
  const l = nuclei?.low || 0;
  const inf = nuclei?.info || 0;
  const sum = c + h + m + l + inf || 1;
  return (
    <div className="rounded overflow-hidden" style={{ height: 10 }}>
      <ProgressBar className="h-100">
        <ProgressBar variant="danger" now={(100 * c) / sum} key="c" />
        <ProgressBar variant="warning" now={(100 * h) / sum} key="h" />
        <ProgressBar variant="info" now={(100 * m) / sum} key="m" />
        <ProgressBar variant="secondary" now={(100 * l) / sum} key="l" />
        <ProgressBar variant="dark" now={(100 * inf) / sum} key="inf" />
      </ProgressBar>
    </div>
  );
}

export default function SecurityPostureCards({
  programParam = '',
  programName = null,
  nucleiTotal = 0,
  nucleiDetails = {},
  typosquatTotal = 0,
  typosquatDetails = {},
  certificateStats = {},
  avgTyposquatRisk = null,
}) {
  const cert = certificateStats || {};
  const nucleiSeverityHref = (sev) => buildDashboardListHref('/findings/nuclei', programName, { severity: sev });
  const typosquatStatusHref = (status) => buildDashboardListHref('/findings/typosquat', programName, { status });
  const certStatusHref = (status) => buildDashboardListHref('/assets/certificates', programName, { status });
  const certListHref = buildDashboardListHref('/assets/certificates', programName, {});

  return (
    <Row className="g-3">
      <Col md={4}>
        <Card className="rh-elevated-card h-100">
          <Card.Header className="rh-card-header-table d-flex justify-content-between align-items-center">
            <h6 className="mb-0">Nuclei</h6>
            <Link to={`/findings/nuclei${programParam}`} className="small text-decoration-none">
              {formatInt(nucleiTotal)}
            </Link>
          </Card.Header>
          <Card.Body>
            <SeverityBar nuclei={nucleiDetails} />
            <div className="d-flex flex-wrap gap-1 mt-3 small">
              {nucleiDetails?.critical > 0 && (
                <Link to={nucleiSeverityHref('critical')} className="text-decoration-none">
                  <Badge bg="danger">Critical {nucleiDetails.critical}</Badge>
                </Link>
              )}
              {nucleiDetails?.high > 0 && (
                <Link to={nucleiSeverityHref('high')} className="text-decoration-none">
                  <Badge bg="warning" text="dark">
                    High {nucleiDetails.high}
                  </Badge>
                </Link>
              )}
              {nucleiDetails?.medium > 0 && (
                <Link to={nucleiSeverityHref('medium')} className="text-decoration-none">
                  <Badge bg="info">Medium {nucleiDetails.medium}</Badge>
                </Link>
              )}
              {nucleiDetails?.low > 0 && (
                <Link to={nucleiSeverityHref('low')} className="text-decoration-none">
                  <Badge bg="secondary">Low {nucleiDetails.low}</Badge>
                </Link>
              )}
              {nucleiDetails?.info > 0 && (
                <Link to={nucleiSeverityHref('info')} className="text-decoration-none">
                  <Badge bg="dark">Info {nucleiDetails.info}</Badge>
                </Link>
              )}
            </div>
          </Card.Body>
        </Card>
      </Col>
      <Col md={4}>
        <Card className="rh-elevated-card h-100">
          <Card.Header className="rh-card-header-table d-flex justify-content-between align-items-center">
            <h6 className="mb-0">Typosquat</h6>
            <Link to={`/findings/typosquat${programParam}`} className="small text-decoration-none">
              {formatInt(typosquatTotal)}
            </Link>
          </Card.Header>
          <Card.Body>
            <div className="d-flex flex-wrap gap-1 small mb-2">
              {(typosquatDetails?.new || 0) > 0 && (
                <Link to={typosquatStatusHref('new')} className="text-decoration-none">
                  <Badge bg="info">New {typosquatDetails.new}</Badge>
                </Link>
              )}
              {(typosquatDetails?.inprogress || 0) > 0 && (
                <Link to={typosquatStatusHref('inprogress')} className="text-decoration-none">
                  <Badge bg="primary">In progress {typosquatDetails.inprogress}</Badge>
                </Link>
              )}
              {(typosquatDetails?.resolved || 0) > 0 && (
                <Link to={typosquatStatusHref('resolved')} className="text-decoration-none">
                  <Badge bg="success">Resolved {typosquatDetails.resolved}</Badge>
                </Link>
              )}
              {(typosquatDetails?.dismissed || 0) > 0 && (
                <Link to={typosquatStatusHref('dismissed')} className="text-decoration-none">
                  <Badge bg="secondary">Dismissed {typosquatDetails.dismissed}</Badge>
                </Link>
              )}
            </div>
            {avgTyposquatRisk != null && (
              <div className="text-muted small">
                Avg. risk score: <span className="text-body fw-semibold">{avgTyposquatRisk.toFixed(1)}</span>
              </div>
            )}
          </Card.Body>
        </Card>
      </Col>
      <Col md={4}>
        <Card className="rh-elevated-card h-100">
          <Card.Header className="rh-card-header-table d-flex justify-content-between align-items-center">
            <h6 className="mb-0">Certificates</h6>
            <Link to={`/assets/certificates${programParam}`} className="small text-decoration-none">
              {formatInt(cert.total)}
            </Link>
          </Card.Header>
          <Card.Body className="small">
            <div className="d-flex justify-content-between py-1 border-bottom">
              <Link to={certStatusHref('valid')} className="text-muted text-decoration-none">
                Valid
              </Link>
              <Link to={certStatusHref('valid')} className="text-decoration-none text-body">
                {formatInt(cert.valid)}
              </Link>
            </div>
            <div className="d-flex justify-content-between py-1 border-bottom">
              <Link to={certStatusHref('expiring_soon')} className="text-muted text-decoration-none">
                Expiring (30d)
              </Link>
              <Link to={certStatusHref('expiring_soon')} className="text-decoration-none text-warning">
                {formatInt(cert.expiring_soon)}
              </Link>
            </div>
            <div className="d-flex justify-content-between py-1 border-bottom">
              <Link to={certStatusHref('expired')} className="text-muted text-decoration-none">
                Expired
              </Link>
              <Link to={certStatusHref('expired')} className="text-decoration-none text-danger">
                {formatInt(cert.expired)}
              </Link>
            </div>
            <div className="d-flex justify-content-between py-1 border-bottom">
              <Link to={certListHref} className="text-muted text-decoration-none">
                Self-signed
              </Link>
              <Link to={certListHref} className="text-decoration-none text-body">
                {formatInt(cert.self_signed)}
              </Link>
            </div>
            <div className="d-flex justify-content-between py-1">
              <Link to={certListHref} className="text-muted text-decoration-none">
                Wildcard
              </Link>
              <Link to={certListHref} className="text-decoration-none text-body">
                {formatInt(cert.wildcards)}
              </Link>
            </div>
          </Card.Body>
        </Card>
      </Col>
    </Row>
  );
}
