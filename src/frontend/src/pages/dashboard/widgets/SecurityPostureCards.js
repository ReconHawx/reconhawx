import React from 'react';
import { Row, Col, Card, Badge, ProgressBar } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { formatInt, buildDashboardListHref } from '../dashboardUtils';

function SeverityBar({ details }) {
  const c = details?.critical || 0;
  const h = details?.high || 0;
  const m = details?.medium || 0;
  const l = details?.low || 0;
  const inf = details?.info || 0;
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
  wpscanTotal = 0,
  wpscanDetails = {},
  certificateStats = {},
}) {
  const cert = certificateStats || {};
  const nucleiSeverityHref = (sev) => buildDashboardListHref('/findings/nuclei', programName, { severity: sev });
  const wpscanSeverityHref = (sev) => buildDashboardListHref('/findings/wpscan', programName, { severity: sev });
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
            <SeverityBar details={nucleiDetails} />
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
            <h6 className="mb-0">WPScan</h6>
            <Link to={`/findings/wpscan${programParam}`} className="small text-decoration-none">
              {formatInt(wpscanTotal)}
            </Link>
          </Card.Header>
          <Card.Body>
            <SeverityBar details={wpscanDetails} />
            <div className="d-flex flex-wrap gap-1 mt-3 small">
              {wpscanDetails?.critical > 0 && (
                <Link to={wpscanSeverityHref('critical')} className="text-decoration-none">
                  <Badge bg="danger">Critical {wpscanDetails.critical}</Badge>
                </Link>
              )}
              {wpscanDetails?.high > 0 && (
                <Link to={wpscanSeverityHref('high')} className="text-decoration-none">
                  <Badge bg="warning" text="dark">
                    High {wpscanDetails.high}
                  </Badge>
                </Link>
              )}
              {wpscanDetails?.medium > 0 && (
                <Link to={wpscanSeverityHref('medium')} className="text-decoration-none">
                  <Badge bg="info">Medium {wpscanDetails.medium}</Badge>
                </Link>
              )}
              {wpscanDetails?.low > 0 && (
                <Link to={wpscanSeverityHref('low')} className="text-decoration-none">
                  <Badge bg="secondary">Low {wpscanDetails.low}</Badge>
                </Link>
              )}
              {wpscanDetails?.info > 0 && (
                <Link to={wpscanSeverityHref('info')} className="text-decoration-none">
                  <Badge bg="dark">Info {wpscanDetails.info}</Badge>
                </Link>
              )}
            </div>
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
