import React, { useState, useEffect, useCallback } from 'react';
import { Container, Row, Col, Card, Alert, Spinner, Badge, Button } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useProgramFilter } from '../contexts/ProgramFilterContext';
import { workflowAPI, commonStatsAPI } from '../services/api';
import { usePageTitle, formatPageTitle } from '../hooks/usePageTitle';
// Utility function to calculate age from created_at timestamp
const getAgeFromDate = (createdAt) => {
  if (!createdAt) return 'N/A';

  const now = new Date();
  const created = new Date(createdAt);
  const diffMs = now - created;
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  if (diffSeconds < 60) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffWeeks < 4) return `${diffWeeks}w ago`;
  if (diffMonths < 12) return `${diffMonths}mo ago`;
  return `${diffYears}y ago`;
};

// Add custom CSS for hover effects
const styles = `
  .hover-link:hover {
    opacity: 0.8;
    transform: scale(1.05);
    transition: all 0.2s ease;
    cursor: pointer;
  }
`;

const styleSheet = document.createElement("style");
styleSheet.type = "text/css";
styleSheet.innerText = styles;
document.head.appendChild(styleSheet);

function Dashboard() {
  usePageTitle(formatPageTitle('Dashboard'));
  const { selectedProgram } = useProgramFilter();
  const [stats, setStats] = useState({
    subdomains: 0, apexDomains: 0, ips: 0, services: 0, urls: 0, certificates: 0,
    nucleiFindings: 0, typosquatFindings: 0, activeWorkflows: 0,
    // Add detailed breakdowns
    subdomainBreakdown: { resolved: 0, unresolved: 0, wildcard: 0 },
    ipBreakdown: { resolved: 0, unresolved: 0 },
        urlBreakdown: { root: 0, nonRoot: 0, rootHttps: 0, rootHttp: 0 }
  });
  const [totalPrograms, setTotalPrograms] = useState(0);
  const [findingsDetails, setFindingsDetails] = useState({
    nuclei: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
    typosquat: { new: 0, inprogress: 0, resolved: 0, dismissed: 0 }
  });
  const [latestAssets, setLatestAssets] = useState({
    subdomains: [], apex_domains: [], ips: [], urls: [], services: [], certificates: []
  });
  const [latestFindings, setLatestFindings] = useState({
    nuclei: [], typosquat: []
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const getActiveWorkflowCount = useCallback(async (programName) => {
    try {
      // Get workflows with running/started status only
      const response = await workflowAPI.getWorkflowStatus(1, 100, programName, 'started_at', 'desc');
      if (response && response.executions) {
        // Count only workflows with running or started status
        const activeCount = response.executions.filter(workflow =>
          workflow.status === 'running' || workflow.status === 'started'
        ).length;
        return { total_items: activeCount };
      }
      return { total_items: 0 };
    } catch (err) {
      console.error('Failed to get active workflow count:', err);
      return { total_items: 0 };
    }
  }, []);

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Load statistics using the new common stats endpoints
      let assetStats, findingsStats;
      
      if (selectedProgram) {
        // Get stats for specific program
        [assetStats, findingsStats] = await Promise.allSettled([
          commonStatsAPI.getProgramAssetStats(selectedProgram),
          commonStatsAPI.getProgramFindingsStats(selectedProgram)
        ]);
      } else {
        // Get aggregated stats across all accessible programs
        [assetStats, findingsStats] = await Promise.allSettled([
          commonStatsAPI.getAggregatedAssetStats(),
          commonStatsAPI.getAggregatedFindingsStats()
        ]);
      }

      // Get workflow stats
      const workflowsRes = await getActiveWorkflowCount(selectedProgram);

      // Get latest assets and findings
      const latestData = await commonStatsAPI.getLatestAssetsAndFindings(selectedProgram, 5);

      // Update statistics from the new endpoints
      setStats({
        subdomains: assetStats.status === 'fulfilled' ? assetStats.value.subdomain_details?.total || 0 : 0,
        apexDomains: assetStats.status === 'fulfilled' ? assetStats.value.apex_domain_details?.total || 0 : 0,
        ips: assetStats.status === 'fulfilled' ? assetStats.value.ip_details?.total || 0 : 0,
        services: assetStats.status === 'fulfilled' ? assetStats.value.service_details?.total || 0 : 0,
        urls: assetStats.status === 'fulfilled' ? assetStats.value.url_details?.total || 0 : 0,
        certificates: assetStats.status === 'fulfilled' ? assetStats.value.certificate_details?.total || 0 : 0,
        nucleiFindings: findingsStats.status === 'fulfilled' ? findingsStats.value.nuclei_findings?.total || 0 : 0,
        typosquatFindings: findingsStats.status === 'fulfilled' ? findingsStats.value.typosquat_findings?.total || 0 : 0,
        activeWorkflows: workflowsRes.total_items || 0,
        // Add detailed breakdowns
        subdomainBreakdown: assetStats.status === 'fulfilled' ? {
          resolved: assetStats.value.subdomain_details?.resolved || 0,
          unresolved: assetStats.value.subdomain_details?.unresolved || 0,
          wildcard: assetStats.value.subdomain_details?.wildcard || 0
        } : { resolved: 0, unresolved: 0, wildcard: 0 },
        ipBreakdown: assetStats.status === 'fulfilled' ? {
          resolved: assetStats.value.ip_details?.resolved || 0,
          unresolved: assetStats.value.ip_details?.unresolved || 0
        } : { resolved: 0, unresolved: 0 },
        urlBreakdown: assetStats.status === 'fulfilled' ? {
          root: assetStats.value.url_details?.root || 0,
          nonRoot: assetStats.value.url_details?.non_root || 0,
          rootHttps: assetStats.value.url_details?.root_https || 0,
          rootHttp: assetStats.value.url_details?.root_http || 0
        } : { root: 0, nonRoot: 0, rootHttps: 0, rootHttp: 0 }
      });

      // Update detailed findings stats for severity distribution
      if (findingsStats.status === 'fulfilled') {
        setFindingsDetails({
          nuclei: {
            critical: findingsStats.value.nuclei_findings?.critical || 0,
            high: findingsStats.value.nuclei_findings?.high || 0,
            medium: findingsStats.value.nuclei_findings?.medium || 0,
            low: findingsStats.value.nuclei_findings?.low || 0,
            info: findingsStats.value.nuclei_findings?.info || 0
          },
          typosquat: {
            new: findingsStats.value.typosquat_findings?.new || 0,
            inprogress: findingsStats.value.typosquat_findings?.inprogress || 0,
            resolved: findingsStats.value.typosquat_findings?.resolved || 0,
            dismissed: findingsStats.value.typosquat_findings?.dismissed || 0
          }
        });
      }

      // Update latest assets and findings
      if (latestData.status === 'success') {
        setLatestAssets(latestData.data.latest_assets || {});
        setLatestFindings(latestData.data.latest_findings || {});
      } else {
        console.error('Latest data not successful:', latestData);
      }

      // Update total programs count for aggregated stats
      if (!selectedProgram && assetStats.status === 'fulfilled') {
        setTotalPrograms(assetStats.value.total_programs || 0);
      } else {
        setTotalPrograms(1); // Single program selected
      }

    } catch (err) {
      console.error('Dashboard loading error:', err);
      setError('Failed to load dashboard data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [selectedProgram, getActiveWorkflowCount]);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const getSeverityBadge = (severity) => {
    const severityColors = {
      critical: 'danger',
      high: 'primary',
      medium: 'info',
      low: 'secondary',
      info: 'primary'
    };
    return <Badge bg={severityColors[severity] || 'secondary'}>{severity}</Badge>;
  };

  const getStatusBadge = (status) => {
    const statusColors = {
      new: 'info',
      inprogress: 'primary',
      resolved: 'success',
      dismissed: 'secondary'
    };
    return <Badge bg={statusColors[status] || 'secondary'}>{status}</Badge>;
  };

  const truncateText = (text, maxLength = 50) => {
    if (!text) return 'N/A';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
  };

  if (loading) {
    return (
      <Container fluid className="p-4 text-center">
        <Spinner animation="border" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
        <p className="mt-3">Loading dashboard data...</p>
      </Container>
    );
  }

  const programParam = selectedProgram ? `?program=${selectedProgram}` : '';

  return (
    <Container fluid className="p-4">
      {/* Header Section with Consolidated Navigation */}
      <div className="d-flex justify-content-between align-items-start mb-4">
        <div>
          <h1 className="mb-2">🔍 Reconnaissance Dashboard</h1>
          <div className="d-flex align-items-center gap-3">
            {!selectedProgram && totalPrograms > 0 && (
              <Badge bg="success" className="fs-6 px-3 py-2">
                📊 {totalPrograms} Programs
              </Badge>
            )}
            {selectedProgram && (
              <Badge bg="info" className="fs-6 px-3 py-2">
                🎯 {selectedProgram}
              </Badge>
            )}
          </div>
        </div>


      </div>

      {/* Quick Links */}
      <Card className="border-primary mb-4">
        <Card.Header className="bg-primary">
          <h5 className="mb-0">⚡ Quick Links</h5>
        </Card.Header>
        <Card.Body>
          <Row>
            {/* Assets Section */}
            <Col md={6} className="mb-3">
              <h6 className="mb-3">📦 Assets</h6>
              <Row className="g-1">
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to={`/assets/subdomains${programParam}`} variant="outline-primary" size="sm" className="w-100 py-1 px-2" style={{fontSize: '0.75rem'}}>
                    🌐 Subdomains
                  </Button>
                </Col>
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to={`/assets/apex-domains${programParam}`} variant="outline-primary" size="sm" className="w-100 py-1 px-2" style={{fontSize: '0.75rem'}}>
                    🎯 Apex
                  </Button>
                </Col>
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to={`/assets/ips${programParam}`} variant="outline-primary" size="sm" className="w-100 py-1 px-2" style={{fontSize: '0.75rem'}}>
                    🖥️ IPs
                  </Button>
                </Col>
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to={`/assets/urls${programParam}`} variant="outline-primary" size="sm" className="w-100 py-1 px-2" style={{fontSize: '0.75rem'}}>
                    🔗 URLs
                  </Button>
                </Col>
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to={`/assets/services${programParam}`} variant="outline-primary" size="sm" className="w-100 py-1 px-2">
                    ⚡ Services
                  </Button>
                </Col>
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to={`/assets/certificates${programParam}`} variant="outline-primary" size="sm" className="w-100 py-1 px-2">
                    🔒 Certificates
                  </Button>
                </Col>
              </Row>
              <Row className="g-2">
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to="/assets/screenshots" variant="outline-primary" size="sm" className="w-100 py-1 px-2">
                    📸 Screenshots
                  </Button>
                </Col>
              </Row>
            </Col>

            {/* Findings Section */}
            <Col md={3} className="mb-3">
              <h6 className="mb-3">🚨 Findings</h6>
              <div className="d-flex flex-column gap-2">
                <Button as={Link} to={`/findings/nuclei${programParam}`} variant="outline-danger" size="sm" className="w-100">
                  🎯 Nuclei Findings
                </Button>
                <Button as={Link} to={`/findings/typosquat${programParam}`} variant="outline-danger" size="sm" className="w-100">
                  🔍 Typosquat Findings
                </Button>
                <Button as={Link} to="/findings/ssl-dashboard" variant="outline-warning" size="sm" className="w-100">
                  🔒 SSL Dashboard
                </Button>
              </div>
            </Col>

            {/* Workflows Section */}
            <Col md={3} className="mb-3">
              <h6 className="mb-3">🔄 Workflows</h6>
              <div className="d-flex flex-column gap-2">
                <Button as={Link} to="/workflows/status" variant="outline-success" size="sm" className="w-100">
                  📊 Workflow Status
                </Button>
                <Button as={Link} to="/workflows/saved" variant="outline-success" size="sm" className="w-100">
                  💾 Saved Workflows
                </Button>
                <Button as={Link} to="/workflows/run" variant="outline-success" size="sm" className="w-100">
                  ▶️ Run Workflow
                </Button>
                <Button as={Link} to="/workflows?tab=single-task" variant="outline-success" size="sm" className="w-100">
                  ▶️ Run Single Task
                </Button>
              </div>
            </Col>
          </Row>
          <Row className="mt-3">
            {/* Tools & Settings Section */}
            <Col md={6} className="mb-3">
              <h6 className="mb-3">🛠️ Tools & Settings</h6>
              <Row className="g-2">
                <Col xs={6} sm={4} md={4}>
                  <Button as={Link} to="/programs" variant="outline-secondary" size="sm" className="w-100">
                    📋 Manage Programs
                  </Button>
                </Col>
                {selectedProgram && (
                  <Col xs={6} sm={4} md={4}>
                    <Button as={Link} to={`/programs/${selectedProgram}`} variant="outline-secondary" size="sm" className="w-100">
                      ⚙️ Program Settings
                    </Button>
                  </Col>
                )}
              </Row>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      {/* Key Metrics Overview */}
      <Card className="mb-4 border-primary">
        <Card.Header className="bg-primary">
          <h4 className="mb-0">📊 Key Metrics</h4>
        </Card.Header>
        <Card.Body>
          <Row className="text-center">
            <Col md={2}>
              <Link to={`/assets/subdomains${programParam}`} className="text-decoration-none">
                <div className="h3 text-primary mb-1 hover-link">{stats.subdomains.toLocaleString()}</div>
              </Link>
              <div className="text-muted small">Subdomains</div>
              <div className="text-muted small">
                <Badge bg="success" className="me-1">{stats.subdomainBreakdown.resolved.toLocaleString()}</Badge>
                <Badge bg="info" className="me-1">{stats.subdomainBreakdown.unresolved.toLocaleString()}</Badge>
                {stats.subdomainBreakdown.wildcard > 0 && (
                  <Badge bg="secondary">{stats.subdomainBreakdown.wildcard.toLocaleString()}</Badge>
                )}
              </div>
              <div className="text-muted small">
                <span className="text-success">Resolved</span> | <span className="text-info">Unresolved</span>
                {stats.subdomainBreakdown.wildcard > 0 && (
                  <span> | <span className="text-secondary">Wildcard</span></span>
                )}
              </div>
            </Col>
            <Col md={2}>
              <Link to={`/assets/apex-domains${programParam}`} className="text-decoration-none">
                <div className="h3 text-success mb-1 hover-link">{stats.apexDomains.toLocaleString()}</div>
              </Link>
              <div className="text-muted small">Apex Domains</div>
            </Col>
            <Col md={2}>
              <Link to={`/assets/ips${programParam}`} className="text-decoration-none">
                <div className="h3 text-info mb-1 hover-link">{stats.ips.toLocaleString()}</div>
              </Link>
              <div className="text-muted small">IP Addresses</div>
              <div className="text-muted small">
                <Badge bg="success" className="me-1">{stats.ipBreakdown.resolved.toLocaleString()}</Badge>
                <Badge bg="info">{stats.ipBreakdown.unresolved.toLocaleString()}</Badge>
              </div>
              <div className="text-muted small">
                <span className="text-success">Resolved</span> | <span className="text-info">Unresolved</span>
              </div>
            </Col>
            <Col md={2}>
              <Link to={`/assets/urls${programParam}`} className="text-decoration-none">
                <div className="h3 text-warning mb-1 hover-link">{stats.urls.toLocaleString()}</div>
              </Link>
              <div className="text-muted small">URLs</div>
              <div className="text-muted small">
                <Badge bg="primary" className="me-1">{stats.urlBreakdown.root.toLocaleString()}</Badge>
                <Badge bg="secondary">{stats.urlBreakdown.nonRoot.toLocaleString()}</Badge>
              </div>
              <div className="text-muted small">
                <span className="text-primary">Websites</span> | <span className="text-secondary">URLs</span>
              </div>
              <div className="text-muted small mt-1">
                <Badge bg="success" className="me-1">{stats.urlBreakdown.rootHttps.toLocaleString()}</Badge>
                <Badge bg="info">{stats.urlBreakdown.rootHttp.toLocaleString()}</Badge>
              </div>
              <div className="text-muted small">
                <span className="text-success">HTTPS</span> | <span className="text-info">HTTP</span>
              </div>
            </Col>
            <Col md={2}>
              <Link to={`/assets/services${programParam}`} className="text-decoration-none">
                <div className="h3 text-secondary mb-1 hover-link">{stats.services.toLocaleString()}</div>
              </Link>
              <div className="text-muted small">Services</div>
            </Col>
            <Col md={2}>
              <Link to={`/assets/certificates${programParam}`} className="text-decoration-none">
                <div className="h3 text-danger mb-1 hover-link">{stats.certificates.toLocaleString()}</div>
              </Link>
              <div className="text-muted small">Certificates</div>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {/* Security Findings Overview */}
      <Row className="mb-4">
        <Col md={6}>
          <Card className="h-100 border-danger">
            <Card.Header className="bg-danger d-flex justify-content-between align-items-center">
              <h5 className="mb-0">🎯 Nuclei Findings</h5>
              <Link to={`/findings/nuclei${programParam}`} className="text-decoration-none">
                <Badge bg="light" text="dark" className="fs-6 hover-link">{stats.nucleiFindings.toLocaleString()}</Badge>
              </Link>
            </Card.Header>
            <Card.Body>
              <div className="mb-3">
                <h6>Severity Breakdown:</h6>
                <div className="d-flex flex-wrap gap-1">
                  {findingsDetails.nuclei.critical > 0 && (
                    <Badge bg="danger" className="px-2 py-1">
                      Critical: {findingsDetails.nuclei.critical}
                    </Badge>
                  )}
                  {findingsDetails.nuclei.high > 0 && (
                    <Badge bg="primary" className="px-2 py-1">
                      High: {findingsDetails.nuclei.high}
                    </Badge>
                  )}
                  {findingsDetails.nuclei.medium > 0 && (
                    <Badge bg="info" className="px-2 py-1">
                      Medium: {findingsDetails.nuclei.medium}
                    </Badge>
                  )}
                  {(findingsDetails.nuclei.low > 0 || findingsDetails.nuclei.info > 0) && (
                    <Badge bg="secondary" className="px-2 py-1">
                      Low/Info: {findingsDetails.nuclei.low + findingsDetails.nuclei.info}
                    </Badge>
                  )}
                </div>
              </div>
            </Card.Body>
          </Card>
        </Col>

                  <Col md={6}>
            <Card className="h-100 border-secondary">
              <Card.Header className="bg-secondary d-flex justify-content-between align-items-center">
                <h5 className="mb-0">🔍 Typosquat Findings</h5>
                <Link to={`/findings/typosquat${programParam}`} className="text-decoration-none">
                  <Badge bg="light" text="dark" className="fs-6 hover-link">{stats.typosquatFindings.toLocaleString()}</Badge>
                </Link>
              </Card.Header>
            <Card.Body>
              <div className="mb-3">
                <h6>Status Breakdown:</h6>
                <div className="d-flex flex-wrap gap-1">
                  {findingsDetails.typosquat.new > 0 && (
                    <Badge bg="info" className="px-2 py-1">
                      New: {findingsDetails.typosquat.new}
                    </Badge>
                  )}
                  {findingsDetails.typosquat.inprogress > 0 && (
                    <Badge bg="primary" className="px-2 py-1">
                      In Progress: {findingsDetails.typosquat.inprogress}
                    </Badge>
                  )}
                  {findingsDetails.typosquat.dismissed > 0 && (
                    <Badge bg="danger" className="px-2 py-1">
                      Dismissed: {findingsDetails.typosquat.dismissed}
                    </Badge>
                  )}
                  {(findingsDetails.typosquat.resolved > 0) && (
                    <Badge bg="success" className="px-2 py-1">
                      Resolved: {findingsDetails.typosquat.resolved}
                    </Badge>
                  )}
                </div>
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Latest Assets Section */}
      <div className="mb-4">
        <h3 className="mb-3">📦 Latest Assets</h3>
        <Row>
          {/* Recent Subdomains */}
          <Col md={4} className="mb-3">
            <Card className="h-100 border-primary">
              <Card.Header className="bg-primary d-flex justify-content-between align-items-center">
                <h6 className="mb-0">🌐 Recent Subdomains</h6>
                <Link to={`/assets/subdomains${programParam}`} className="text-decoration-none">
                  <Badge bg="light" text="dark hover-link">{latestAssets.subdomains?.length || 0}</Badge>
                </Link>
              </Card.Header>
              <Card.Body className="d-flex flex-column">
                <div className="flex-grow-1">
                  {latestAssets.subdomains && latestAssets.subdomains.length > 0 ? (
                    <div className="list-group list-group-flush">
                      {latestAssets.subdomains.slice(0, 10).map((subdomain) => (
                        <div key={subdomain.id} className="list-group-item px-0 py-2 d-flex justify-content-between align-items-center">
                          <Link to={`/assets/subdomains/details?id=${subdomain.id}`} className="text-decoration-none flex-grow-1 me-2">
                            <small>{truncateText(subdomain.name, 30)}</small>
                          </Link>
                          <div className="d-flex align-items-center gap-2">
                            <span className="text-muted small">{getAgeFromDate(subdomain.created_at)}</span>
                            <Badge bg={subdomain.is_wildcard ? 'primary' : 'secondary'}>
                              {subdomain.is_wildcard ? 'W' : 'R'}
                            </Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted text-center small">No subdomains found</p>
                  )}
                </div>
                <div className="mt-auto pt-2">
                  <Link to={`/assets/subdomains${programParam}`} className="btn btn-sm btn-outline-primary w-100">
                    View All Subdomains
                  </Link>
                </div>
              </Card.Body>
            </Card>
          </Col>

          {/* Recent URLs */}
          <Col md={4} className="mb-3">
            <Card className="h-100 border-success">
              <Card.Header className="bg-success d-flex justify-content-between align-items-center">
                <h6 className="mb-0">🔗 Recent URLs</h6>
                <Link to={`/assets/urls${programParam}`} className="text-decoration-none">
                  <Badge bg="light" text="dark hover-link">{latestAssets.urls?.length || 0}</Badge>
                </Link>
              </Card.Header>
              <Card.Body className="d-flex flex-column">
                <div className="flex-grow-1">
                  {latestAssets.urls && latestAssets.urls.length > 0 ? (
                    <div className="list-group list-group-flush">
                      {latestAssets.urls.slice(0, 10).map((url) => (
                        <div key={url.id} className="list-group-item px-0 py-2 d-flex justify-content-between align-items-center">
                          <Link to={`/assets/urls/details?id=${url.id}`} className="text-decoration-none flex-grow-1 me-2">
                            <small>{truncateText(url.url, 30)}</small>
                          </Link>
                          <div className="d-flex align-items-center gap-2">
                            <span className="text-muted small">{getAgeFromDate(url.created_at)}</span>
                            <Badge bg={url.status_code >= 400 ? 'danger' : url.status_code >= 300 ? 'warning' : 'success'}>
                              {url.status_code || 'N/A'}
                            </Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted text-center small">No URLs found</p>
                  )}
                </div>
                <div className="mt-auto pt-2">
                  <Link to={`/assets/urls${programParam}`} className="btn btn-sm btn-outline-success w-100">
                    View All URLs
                  </Link>
                </div>
              </Card.Body>
            </Card>
          </Col>

          {/* Recent IP Addresses */}
          <Col md={4} className="mb-3">
            <Card className="h-100 border-info">
              <Card.Header className="bg-info d-flex justify-content-between align-items-center">
                <h6 className="mb-0">🖥️ Recent IP Addresses</h6>
                <Link to={`/assets/ips${programParam}`} className="text-decoration-none">
                  <Badge bg="light" text="dark hover-link">{latestAssets.ips?.length || 0}</Badge>
                </Link>
              </Card.Header>
              <Card.Body className="d-flex flex-column">
                <div className="flex-grow-1">
                  {latestAssets.ips && latestAssets.ips.length > 0 ? (
                    <div className="list-group list-group-flush">
                      {latestAssets.ips.slice(0, 10).map((ip) => (
                        <div key={ip.id} className="list-group-item px-0 py-2 d-flex justify-content-between align-items-center">
                          <Link to={`/assets/ips/details?id=${ip.id}`} className="text-decoration-none flex-grow-1 me-2">
                            <small>{ip.ip}</small>
                          </Link>
                          <span className="text-muted small ms-auto">{getAgeFromDate(ip.created_at)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted text-center small">No IP addresses found</p>
                  )}
                </div>
                <div className="mt-auto pt-2">
                  <Link to={`/assets/ips${programParam}`} className="btn btn-sm btn-outline-info w-100">
                    View All IPs
                  </Link>
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </div>

      {/* Latest Findings Section */}
      <div className="mb-4">
        <h3 className="mb-3">🚨 Latest Findings</h3>
        <Row>
          {/* Recent Nuclei Findings */}
          <Col md={6} className="mb-3">
            <Card className="h-100 border-danger">
              <Card.Header className="bg-danger d-flex justify-content-between align-items-center">
                <h6 className="mb-0">🎯 Recent Nuclei Findings</h6>
                <Link to={`/findings/nuclei${programParam}`} className="text-decoration-none">
                  <Badge bg="light" text="dark hover-link">{latestFindings.nuclei?.length || 0}</Badge>
                </Link>
              </Card.Header>
              <Card.Body className="d-flex flex-column">
                <div className="flex-grow-1">
                  {latestFindings.nuclei && latestFindings.nuclei.length > 0 ? (
                    <div className="list-group list-group-flush">
                      {latestFindings.nuclei.slice(0, 10).map((finding) => (
                        <div key={finding.id} className="list-group-item px-0 py-2 d-flex justify-content-between align-items-center">
                          <Link to={`/findings/nuclei/details?id=${finding.id}`} className="text-decoration-none flex-grow-1 me-2">
                            <small>{truncateText(finding.name || finding.url, 30)}</small>
                          </Link>
                          <div className="d-flex align-items-center gap-2">
                            <span className="text-muted small">{getAgeFromDate(finding.created_at)}</span>
                            {getSeverityBadge(finding.severity)}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted text-center small">No nuclei findings found</p>
                  )}
                </div>
                <div className="mt-auto pt-2">
                  <Link to={`/findings/nuclei${programParam}`} className="btn btn-sm btn-outline-danger w-100">
                    View All Nuclei Findings
                  </Link>
                </div>
              </Card.Body>
            </Card>
          </Col>

          {/* Recent Typosquat Findings */}
          <Col md={6} className="mb-3">
            <Card className="h-100 border-secondary">
              <Card.Header className="bg-secondary d-flex justify-content-between align-items-center">
                <h6 className="mb-0">🔍 Recent Typosquat Findings</h6>
                <Link to={`/findings/typosquat${programParam}`} className="text-decoration-none">
                  <Badge bg="light" text="dark hover-link">{latestFindings.typosquat?.length || 0}</Badge>
                </Link>
              </Card.Header>
              <Card.Body className="d-flex flex-column">
                <div className="flex-grow-1">
                  {latestFindings.typosquat && latestFindings.typosquat.length > 0 ? (
                    <div className="list-group list-group-flush">
                      {latestFindings.typosquat.slice(0, 10).map((finding) => (
                        <div key={finding.id} className="list-group-item px-0 py-2 d-flex justify-content-between align-items-center">
                          <Link to={`/findings/typosquat/details?id=${finding.id}`} className="text-decoration-none flex-grow-1 me-2">
                            <small>{truncateText(finding.typo_domain, 30)}</small>
                          </Link>
                          <div className="d-flex align-items-center gap-2">
                            <span className="text-muted small">{getAgeFromDate(finding.created_at)}</span>
                            {getStatusBadge(finding.status)}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted text-center small">No typosquat findings found</p>
                  )}
                </div>
                <div className="mt-auto pt-2">
                  <Link to={`/findings/typosquat${programParam}`} className="btn btn-sm btn-outline-secondary w-100">
                    View All Typosquat Findings
                  </Link>
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </div>

    </Container>
  );
}

export default Dashboard;