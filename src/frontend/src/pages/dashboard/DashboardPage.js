import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Alert,
  Spinner,
  Badge,
  Button,
  ButtonGroup,
  Form,
} from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { commonStatsAPI } from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';
import { useDashboardPrefs } from './useDashboardPrefs';
import {
  formatInt,
  buildTrendApiParams,
  buildDashboardListHref,
  itemInCustomRange,
  averageRiskScore,
} from './dashboardUtils';
import CustomizeDashboardModal from './CustomizeDashboardModal';
import KPICard from './widgets/KPICard';
import TrendsAreaChart from './widgets/TrendsAreaChart';
import LatestActivityList from './widgets/LatestActivityList';
import RecentWorkflowRuns from './widgets/RecentWorkflowRuns';
import QueueSnapshot from './widgets/QueueSnapshot';
import SecurityPostureCards from './widgets/SecurityPostureCards';
import TopTechCard from './widgets/TopTechCard';

const initialStats = {
  subdomains: 0,
  apexDomains: 0,
  ips: 0,
  services: 0,
  urls: 0,
  certificates: 0,
  nucleiFindings: 0,
  typosquatFindings: 0,
  activeWorkflows: 0,
  subdomainBreakdown: { resolved: 0, unresolved: 0, wildcard: 0 },
  ipBreakdown: { resolved: 0, unresolved: 0 },
  urlBreakdown: { root: 0, nonRoot: 0, rootHttps: 0, rootHttp: 0 },
  certificateBreakdown: {
    valid: 0,
    expiring_soon: 0,
    expired: 0,
    self_signed: 0,
    wildcards: 0,
  },
};

export default function DashboardPage() {
  usePageTitle(formatPageTitle('Dashboard'));
  const { selectedProgram } = useProgramFilter();
  const {
    order,
    visible,
    prefs,
    datePreset,
    setDatePreset,
    customFrom,
    setCustomFrom,
    customTo,
    setCustomTo,
    toggleWidget,
    moveWidget,
    resetDefaults,
  } = useDashboardPrefs();

  const [stats, setStats] = useState(initialStats);
  const [findingsDetails, setFindingsDetails] = useState({
    nuclei: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
    typosquat: { new: 0, inprogress: 0, resolved: 0, dismissed: 0 },
  });
  const [latestAssets, setLatestAssets] = useState({
    subdomains: [],
    urls: [],
  });
  const [latestFindings, setLatestFindings] = useState({ nuclei: [], typosquat: [] });
  const [assetTrends, setAssetTrends] = useState(null);
  const [findingsTrends, setFindingsTrends] = useState(null);
  const [recentRuns, setRecentRuns] = useState([]);
  const [queueStatus, setQueueStatus] = useState(null);
  const [queueErr, setQueueErr] = useState(null);
  const [techSummary, setTechSummary] = useState(null);
  const [totalPrograms, setTotalPrograms] = useState(0);
  const [loading, setLoading] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [customizeOpen, setCustomizeOpen] = useState(false);

  const programParam = selectedProgram ? `?program=${encodeURIComponent(selectedProgram)}` : '';

  const loadDashboardData = useCallback(
    async (opts = {}) => {
      const silent = opts.silent === true;
      if (silent) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const trendParams = buildTrendApiParams(selectedProgram, prefs);
      const programForApi = selectedProgram || null;

      try {
        const summary = await commonStatsAPI.getDashboardSummary({
          programName: programForApi,
          latestLimit: 10,
          days: trendParams.days,
          startDate: trendParams.startDate,
          endDate: trendParams.endDate,
        });

        if (summary.errors && Object.keys(summary.errors).length > 0) {
          console.warn('Dashboard summary partial errors', summary.errors);
        }

        const assetStats = summary.asset_stats || {};
        const findingsStats = summary.findings_stats || {};

        setStats({
          subdomains: assetStats.subdomain_details?.total || 0,
          apexDomains: assetStats.apex_domain_details?.total || 0,
          ips: assetStats.ip_details?.total || 0,
          services: assetStats.service_details?.total || 0,
          urls: assetStats.url_details?.total || 0,
          certificates: assetStats.certificate_details?.total || 0,
          nucleiFindings: findingsStats.nuclei_findings?.total || 0,
          typosquatFindings: findingsStats.typosquat_findings?.total || 0,
          activeWorkflows: summary.active_workflows ?? 0,
          subdomainBreakdown: {
            resolved: assetStats.subdomain_details?.resolved || 0,
            unresolved: assetStats.subdomain_details?.unresolved || 0,
            wildcard: assetStats.subdomain_details?.wildcard || 0,
          },
          ipBreakdown: {
            resolved: assetStats.ip_details?.resolved || 0,
            unresolved: assetStats.ip_details?.unresolved || 0,
          },
          urlBreakdown: {
            root: assetStats.url_details?.root || 0,
            nonRoot: assetStats.url_details?.non_root || 0,
            rootHttps: assetStats.url_details?.root_https || 0,
            rootHttp: assetStats.url_details?.root_http || 0,
          },
          certificateBreakdown: {
            valid: assetStats.certificate_details?.valid || 0,
            expiring_soon: assetStats.certificate_details?.expiring_soon || 0,
            expired: assetStats.certificate_details?.expired || 0,
            self_signed: assetStats.certificate_details?.self_signed || 0,
            wildcards: assetStats.certificate_details?.wildcards || 0,
          },
        });

        setFindingsDetails({
          nuclei: {
            critical: findingsStats.nuclei_findings?.critical || 0,
            high: findingsStats.nuclei_findings?.high || 0,
            medium: findingsStats.nuclei_findings?.medium || 0,
            low: findingsStats.nuclei_findings?.low || 0,
            info: findingsStats.nuclei_findings?.info || 0,
          },
          typosquat: {
            new: findingsStats.typosquat_findings?.new || 0,
            inprogress: findingsStats.typosquat_findings?.inprogress || 0,
            resolved: findingsStats.typosquat_findings?.resolved || 0,
            dismissed: findingsStats.typosquat_findings?.dismissed || 0,
          },
        });

        const la = summary.latest_assets || {};
        const lf = summary.latest_findings || {};
        const filterRow = (x) => itemInCustomRange(x.created_at, prefs);
        setLatestAssets({
          subdomains: (la.subdomains || []).filter(filterRow),
          urls: (la.urls || []).filter(filterRow),
        });
        setLatestFindings({
          nuclei: (lf.nuclei || []).filter(filterRow),
          typosquat: (lf.typosquat || []).filter(filterRow),
        });

        setAssetTrends(summary.asset_trends || null);
        setFindingsTrends(summary.findings_trends || null);
        setRecentRuns(summary.workflow_executions || []);

        if (summary.queue_status) {
          setQueueStatus(summary.queue_status);
          setQueueErr(null);
        } else {
          setQueueStatus(null);
          setQueueErr(
            summary.errors?.queue_status
              ? String(summary.errors.queue_status)
              : 'Queue unavailable'
          );
        }

        const techPayload = summary.technologies_summary;
        setTechSummary(
          techPayload
            ? {
                status: 'success',
                items: techPayload.items || [],
                pagination: techPayload.pagination || {},
              }
            : null
        );

        if (!selectedProgram) {
          setTotalPrograms(summary.total_programs ?? 0);
        } else {
          setTotalPrograms(1);
        }
      } catch (err) {
        console.error('Dashboard loading error:', err);
        setError('Failed to load dashboard data. Please try again.');
      } finally {
        setLoading(false);
        setRefreshing(false);
        setInitialLoad(false);
        setLastUpdated(new Date());
      }
    },
    [selectedProgram, prefs]
  );

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const avgRisk = useMemo(
    () => averageRiskScore(latestFindings.typosquat),
    [latestFindings.typosquat]
  );

  const assetBuckets = assetTrends?.buckets || [];
  const findingsBuckets = findingsTrends?.buckets || [];

  const trendXLabels = useMemo(() => {
    if (!assetBuckets.length) return [];
    return [assetBuckets[0].date, assetBuckets[assetBuckets.length - 1].date];
  }, [assetBuckets]);

  const combinedFindingsItems = useMemo(() => {
    const rows = [
      ...(latestFindings.nuclei || []).map((f) => ({
        key: `n-${f.id}`,
        label: f.name || f.url || 'Finding',
        href: `/findings/nuclei/details?id=${f.id}`,
        createdAt: f.created_at,
        right: <Badge bg="danger">{f.severity || '—'}</Badge>,
      })),
      ...(latestFindings.typosquat || []).map((f) => ({
        key: `t-${f.id}`,
        label: f.typo_domain || 'Typosquat',
        href: `/findings/typosquat/details?id=${f.id}`,
        createdAt: f.created_at,
        right: <Badge bg="info">{f.status || '—'}</Badge>,
      })),
    ];
    rows.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
    return rows.slice(0, 12);
  }, [latestFindings]);

  const renderWidget = (id) => {
    if (initialLoad) {
      return (
        <div key={id} className="mb-4 py-5 text-center rh-elevated-card border rounded">
          <Spinner animation="border" size="sm" className="me-2" />
          <span className="text-muted small">Loading…</span>
        </div>
      );
    }
    const overviewSparkDates = assetBuckets.map((b) => b.date);
    switch (id) {
      case 'kpiStrip':
        return (
          <Row className="g-3 mb-4" key={id}>
            <Col xs={12} className="mb-1">
              <h2 className="h5 text-muted mb-0">Overview</h2>
            </Col>
            {[{
              label: 'Subdomains',
              value: formatInt(stats.subdomains),
              link: `/assets/subdomains${programParam}`,
              breakdown: [
                {
                  key: 'r',
                  text: `R ${formatInt(stats.subdomainBreakdown.resolved)}`,
                  variant: 'success',
                  to: buildDashboardListHref('/assets/subdomains', selectedProgram, { has_ips: 'true' }),
                },
                {
                  key: 'u',
                  text: `U ${formatInt(stats.subdomainBreakdown.unresolved)}`,
                  variant: 'info',
                  to: buildDashboardListHref('/assets/subdomains', selectedProgram, { has_ips: 'false' }),
                },
              ],
              spark: assetBuckets.map((b) => b.subdomains),
            },
            {
              label: 'Apex',
              value: formatInt(stats.apexDomains),
              link: `/assets/apex-domains${programParam}`,
              breakdown: [],
              spark: assetBuckets.map((b) => b.apex_domains),
            },
            {
              label: 'IPs',
              value: formatInt(stats.ips),
              link: `/assets/ips${programParam}`,
              breakdown: [
                {
                  key: 'r',
                  text: `R ${formatInt(stats.ipBreakdown.resolved)}`,
                  variant: 'success',
                  to: buildDashboardListHref('/assets/ips', selectedProgram, { has_ptr: 'true' }),
                },
                {
                  key: 'u',
                  text: `U ${formatInt(stats.ipBreakdown.unresolved)}`,
                  variant: 'info',
                  to: buildDashboardListHref('/assets/ips', selectedProgram, { has_ptr: 'false' }),
                },
              ],
              spark: assetBuckets.map((b) => b.ips),
            },
            {
              label: 'URLs',
              value: formatInt(stats.urls),
              link: `/assets/urls${programParam}`,
              breakdown: [
                {
                  key: 'https',
                  text: `HTTPS ${formatInt(stats.urlBreakdown.rootHttps)}`,
                  variant: 'success',
                  to: buildDashboardListHref('/assets/urls', selectedProgram, {
                    protocol: 'https',
                    only_root: 'true',
                  }),
                },
                {
                  key: 'http',
                  text: `HTTP ${formatInt(stats.urlBreakdown.rootHttp)}`,
                  variant: 'info',
                  to: buildDashboardListHref('/assets/urls', selectedProgram, {
                    protocol: 'http',
                    only_root: 'true',
                  }),
                },
              ],
              spark: assetBuckets.map((b) => b.urls),
            },
            {
              label: 'Services',
              value: formatInt(stats.services),
              link: `/assets/services${programParam}`,
              breakdown: [],
              spark: assetBuckets.map((b) => b.services),
            },
            {
              label: 'Certificates',
              value: formatInt(stats.certificates),
              link: `/assets/certificates${programParam}`,
              breakdown: [],
              spark: assetBuckets.map((b) => b.certificates),
            }].map((k) => (
              <Col key={k.label} lg={4} md={6}>
                <KPICard
                  label={k.label}
                  value={k.value}
                  linkTo={k.link}
                  breakdown={k.breakdown}
                  sparklineValues={k.spark}
                  sparklinePointLabels={overviewSparkDates}
                  sparklineColor="var(--bs-primary)"
                />
              </Col>
            ))}
          </Row>
        );
      case 'securityPosture':
        return (
          <div key={id} className="mb-4">
            <h2 className="h5 mb-3">
              Security posture <span className="text-muted fs-6">· findings &amp; certificates</span>
            </h2>
            <SecurityPostureCards
              nucleiTotal={stats.nucleiFindings}
              nucleiDetails={findingsDetails.nuclei}
              typosquatTotal={stats.typosquatFindings}
              typosquatDetails={findingsDetails.typosquat}
              certificateStats={{
                total: stats.certificates,
                ...stats.certificateBreakdown,
              }}
              avgTyposquatRisk={avgRisk}
              programParam={programParam}
              programName={selectedProgram}
            />
          </div>
        );
      case 'operations':
        return (
          <div key={id} className="mb-4">
            <h2 className="h5 mb-3">Operations</h2>
            <Row className="g-3">
              <Col lg={8}>
                <RecentWorkflowRuns executions={recentRuns} programParam={programParam} />
              </Col>
              <Col lg={4}>
                <QueueSnapshot queue={queueStatus} error={queueErr} />
              </Col>
            </Row>
          </div>
        );
      case 'trends':
        return (
          <div key={id} className="mb-4">
            <h2 className="h5 mb-3">Trends</h2>
            <Row className="g-3">
              <Col lg={6}>
                <Card className="rh-elevated-card h-100">
                  <Card.Header className="rh-card-header-table">Asset creation (daily)</Card.Header>
                  <Card.Body>
                    <TrendsAreaChart
                      title=""
                      xLabels={trendXLabels}
                      pointLabels={assetBuckets.map((b) => b.date)}
                      series={[
                        { key: 'sub', label: 'Subdomains', color: 'var(--bs-primary)', values: assetBuckets.map((b) => b.subdomains) },
                        { key: 'url', label: 'URLs', color: 'var(--bs-warning)', values: assetBuckets.map((b) => b.urls) },
                        { key: 'ip', label: 'IPs', color: 'var(--bs-info)', values: assetBuckets.map((b) => b.ips) },
                      ]}
                    />
                  </Card.Body>
                </Card>
              </Col>
              <Col lg={6}>
                <Card className="rh-elevated-card h-100">
                  <Card.Header className="rh-card-header-table">Findings (daily)</Card.Header>
                  <Card.Body>
                    <TrendsAreaChart
                      title=""
                      xLabels={trendXLabels}
                      pointLabels={findingsBuckets.map((b) => b.date)}
                      series={[
                        {
                          key: 'n',
                          label: 'Nuclei',
                          color: 'var(--bs-danger)',
                          values: findingsBuckets.map((b) => b.nuclei_total),
                        },
                        {
                          key: 't',
                          label: 'Typosquat',
                          color: 'var(--bs-secondary)',
                          values: findingsBuckets.map((b) => b.typosquat_total),
                        },
                      ]}
                    />
                  </Card.Body>
                </Card>
              </Col>
            </Row>
          </div>
        );
      case 'latestActivity':
        return (
          <div key={id} className="mb-4">
            <h2 className="h5 mb-3">Recent activity</h2>
            <Row className="g-3">
              <Col lg={4}>
                <LatestActivityList
                  title="Latest subdomains"
                  items={(latestAssets.subdomains || []).slice(0, 10).map((sub) => ({
                    key: sub.id,
                    label: sub.name,
                    href: `/assets/subdomains/details?id=${sub.id}`,
                    createdAt: sub.created_at,
                    right: <Badge bg={sub.is_wildcard ? 'primary' : 'secondary'}>{sub.is_wildcard ? 'W' : 'R'}</Badge>,
                  }))}
                  emptyText="No subdomains in this range."
                  programParam={programParam}
                  viewAllTo="/assets/subdomains"
                  viewAllLabel="All subdomains"
                />
              </Col>
              <Col lg={4}>
                <LatestActivityList
                  title="Latest URLs"
                  items={(latestAssets.urls || []).slice(0, 10).map((u) => ({
                    key: u.id,
                    label: u.url,
                    href: `/assets/urls/details?id=${u.id}`,
                    createdAt: u.created_at,
                    right: (
                      <Badge bg={u.status_code >= 400 ? 'danger' : u.status_code >= 300 ? 'warning' : 'success'}>
                        {u.status_code ?? '—'}
                      </Badge>
                    ),
                  }))}
                  emptyText="No URLs in this range."
                  programParam={programParam}
                  viewAllTo="/assets/urls"
                  viewAllLabel="All URLs"
                />
              </Col>
              <Col lg={4}>
                <LatestActivityList
                  title="Latest findings"
                  items={combinedFindingsItems}
                  emptyText="No findings in this range."
                  programParam={programParam}
                  viewAllTo="/findings/nuclei"
                  viewAllLabel="All findings"
                />
              </Col>
            </Row>
          </div>
        );
      case 'insights':
        return (
          <div key={id} className="mb-4">
            <h2 className="h5 mb-3">Insights</h2>
            <Row className="g-3">
              <Col xs={12}>
                <TopTechCard summary={techSummary} programParam={programParam} />
              </Col>
            </Row>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <Container fluid className="p-4">
      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h1 className="mb-2 h2">Dashboard</h1>
          <div className="d-flex align-items-center gap-2 flex-wrap">
            {!selectedProgram && totalPrograms > 0 && (
              <Badge bg="secondary" className="fw-normal">
                {formatInt(totalPrograms)} programs
              </Badge>
            )}
            {selectedProgram && (
              <Badge bg="info" className="fw-normal">
                {selectedProgram}
              </Badge>
            )}
            <Link to={`/workflows/status${programParam}`} className="text-decoration-none">
              <Badge bg="warning" text="dark" className="hover-link">
                Active workflows: {formatInt(stats.activeWorkflows)}
              </Badge>
            </Link>
          </div>
        </div>
        <div className="d-flex flex-column align-items-end gap-2">
          <div className="d-flex flex-wrap align-items-center gap-2 justify-content-end">
            <span className="text-muted small me-1 d-none d-sm-inline">Range</span>
            <ButtonGroup size="sm">
              {['7d', '30d', '90d'].map((p) => (
                <Button
                  key={p}
                  variant={datePreset === p ? 'primary' : 'outline-secondary'}
                  onClick={() => setDatePreset(p)}
                >
                  {p.replace('d', '')}d
                </Button>
              ))}
              <Button
                variant={datePreset === 'custom' ? 'primary' : 'outline-secondary'}
                onClick={() => setDatePreset('custom')}
              >
                Custom
              </Button>
            </ButtonGroup>
            <Button variant="outline-secondary" size="sm" onClick={() => setCustomizeOpen(true)}>
              Customize
            </Button>
            <Button
              variant="outline-secondary"
              size="sm"
              disabled={loading || refreshing}
              onClick={() => loadDashboardData({ silent: true })}
            >
              {refreshing ? (
                <>
                  <Spinner animation="border" size="sm" className="me-1" />
                  Refresh…
                </>
              ) : (
                'Refresh'
              )}
            </Button>
          </div>
          {datePreset === 'custom' && (
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <Form.Control
                type="date"
                size="sm"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
              />
              <span className="text-muted small">to</span>
              <Form.Control
                type="date"
                size="sm"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
              />
            </div>
          )}
          <div className="d-flex align-items-center gap-2 justify-content-end flex-wrap">
            {(refreshing || (loading && !initialLoad)) && (
              <Spinner animation="border" size="sm" variant="secondary" role="status">
                <span className="visually-hidden">Updating dashboard</span>
              </Spinner>
            )}
            {lastUpdated && (
              <small className="text-muted">Updated {lastUpdated.toLocaleString()}</small>
            )}
          </div>
        </div>
      </div>

      <CustomizeDashboardModal
        show={customizeOpen}
        onHide={() => setCustomizeOpen(false)}
        order={order}
        visible={visible}
        toggleWidget={toggleWidget}
        moveWidget={moveWidget}
        resetDefaults={resetDefaults}
      />

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      {order.filter((id) => visible[id]).map((id) => renderWidget(id))}
    </Container>
  );
}
