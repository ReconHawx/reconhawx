import React, { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Form,
  Alert,
  Spinner,
  Badge,
  Table
} from 'react-bootstrap';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import api from '../../services/api';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';
import { chartTheme } from '../../utils/chartTheme';

// Simple chart components (you can replace these with a charting library like Chart.js or Recharts)
const SimpleBarChart = ({ data, title }) => {
  if (!data || Object.keys(data).length === 0) {
    return <div className="text-muted">No data available</div>;
  }

  const maxValue = Math.max(...Object.values(data));

  return (
    <div>
      <h6 className="mb-3">{title}</h6>
      <div className="chart-container">
        {Object.entries(data).map(([key, value]) => (
          <div key={key} className="mb-2">
            <div className="d-flex justify-content-between align-items-center mb-1">
              <span className="small">{key}</span>
              <span className="badge bg-secondary">{value}</span>
            </div>
            <div className="progress" style={{ height: '10px' }}>
              <div
                className="progress-bar"
                role="progressbar"
                style={{ width: `${(value / maxValue) * 100}%` }}
                aria-valuenow={value}
                aria-valuemin="0"
                aria-valuemax={maxValue}
              ></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Time series line chart component showing created, resolved, and dismissed (hourly or daily)
const TimeSeriesLineChart = ({ data, title, isHourly = true }) => {
  const containerRef = React.useRef(null);
  const [chartWidth, setChartWidth] = React.useState(1200);
  const gridPatternId = React.useId().replace(/:/g, '');

  React.useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setChartWidth(containerRef.current.offsetWidth);
      }
    };

    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  if (!data || data.length === 0) {
    return <div className="text-muted">No data available</div>;
  }

  // Calculate max value across all three series
  const maxValue = Math.max(
    1,
    ...data.map(d => Math.max(d.created || 0, d.resolved || 0, d.dismissed || 0))
  );

  const chartHeight = 280;
  const padding = { top: 20, right: 30, bottom: 60, left: 60 };
  const plotWidth = chartWidth - padding.left - padding.right;
  const plotHeight = chartHeight - padding.top - padding.bottom;

  const seriesColors = chartTheme.typosquatSeries;

  const seriesKeys = ['created', 'resolved', 'dismissed'];

  // Create SVG path for a data series
  const createPath = (points, seriesKey) => {
    if (points.length === 0) return '';

    const pathData = points
      .map((point, index) => {
        const x = (index / (points.length - 1)) * plotWidth;
        const value = point[seriesKey] || 0;
        const y = plotHeight - (value / maxValue) * plotHeight;
        return `${index === 0 ? 'M' : 'L'} ${x + padding.left} ${y + padding.top}`;
      })
      .join(' ');

    return pathData;
  };

  return (
    <div ref={containerRef}>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h6 className="mb-0">{title}</h6>
      </div>

      <div className="chart-container">
        <svg width={chartWidth} height={chartHeight} style={{ width: '100%', height: 'auto' }}>
          {/* Grid lines */}
          <defs>
            <pattern id={gridPatternId} width="40" height="40" patternUnits="userSpaceOnUse">
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke={chartTheme.gridStroke}
                strokeWidth="1"
              />
            </pattern>
          </defs>
          <rect
            width={plotWidth}
            height={plotHeight}
            x={padding.left}
            y={padding.top}
            fill={`url(#${gridPatternId})`}
          />

          {/* Y-axis labels */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = padding.top + plotHeight - (ratio * plotHeight);
            const value = Math.round(maxValue * ratio);
            return (
              <g key={ratio}>
                <line
                  x1={padding.left - 5}
                  y1={y}
                  x2={padding.left}
                  y2={y}
                  stroke={chartTheme.axisStroke}
                />
                <text
                  x={padding.left - 10}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="12"
                  fill={chartTheme.axisLabelFill}
                >
                  {value}
                </text>
              </g>
            );
          })}

          {/* X-axis labels */}
          {data.filter((_, index) => {
            // For hourly: show every 4 hours, for daily: show based on data length
            if (isHourly) return index % 4 === 0;
            if (data.length <= 7) return true; // Show all for week or less
            if (data.length <= 31) return index % 2 === 0; // Every other day for month
            return index % 7 === 0; // Weekly for longer periods
          }).map((point, index) => {
            const originalIndex = data.indexOf(point);
            const x = (originalIndex / (data.length - 1)) * plotWidth + padding.left;
            const label = isHourly
              ? `${point.hour}:00`
              : new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            return (
              <g key={originalIndex}>
                <line
                  x1={x}
                  y1={padding.top + plotHeight}
                  x2={x}
                  y2={padding.top + plotHeight + 5}
                  stroke={chartTheme.axisStroke}
                />
                <text
                  x={x}
                  y={padding.top + plotHeight + 18}
                  textAnchor="middle"
                  fontSize="12"
                  fill={chartTheme.axisLabelFill}
                >
                  {label}
                </text>
              </g>
            );
          })}

          {/* Data lines for created, resolved, dismissed */}
          {seriesKeys.map((seriesKey) => {
            const pathData = createPath(data, seriesKey);
            const color = seriesColors[seriesKey];
            return (
              <g key={seriesKey}>
                <path
                  d={pathData}
                  fill="none"
                  stroke={color}
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                {/* Data points */}
                {data.map((point, index) => {
                  const x = (index / (data.length - 1)) * plotWidth + padding.left;
                  const value = point[seriesKey] || 0;
                  const y = padding.top + plotHeight - (value / maxValue) * plotHeight;
                  const timeLabel = isHourly
                    ? `${point.hour}:00`
                    : new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  return (
                    <g key={`${seriesKey}-${index}`}>
                      <circle
                        cx={x}
                        cy={y}
                        r="3"
                        fill={color}
                        stroke={chartTheme.pointRingStroke}
                        strokeWidth="1"
                      />
                      <title>{`${timeLabel} - ${seriesKey}: ${value}`}</title>
                    </g>
                  );
                })}
              </g>
            );
          })}

          {/* Axis lines */}
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={padding.top + plotHeight}
            stroke={chartTheme.axisStroke}
            strokeWidth="2"
          />
          <line
            x1={padding.left}
            y1={padding.top + plotHeight}
            x2={padding.left + plotWidth}
            y2={padding.top + plotHeight}
            stroke={chartTheme.axisStroke}
            strokeWidth="2"
          />
        </svg>

        {/* Legend */}
        <div className="mt-3">
          <div className="d-flex flex-wrap gap-3 justify-content-center">
            {seriesKeys.map((seriesKey) => {
              const color = seriesColors[seriesKey];
              const displayName = seriesKey.charAt(0).toUpperCase() + seriesKey.slice(1);
              return (
                <div key={seriesKey} className="d-flex align-items-center">
                  <div
                    style={{
                      width: '12px',
                      height: '12px',
                      backgroundColor: color,
                      borderRadius: '2px',
                      marginRight: '6px'
                    }}
                  ></div>
                  <small>{displayName}</small>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

const StatusCard = ({ title, value, variant = 'primary', subtitle = null }) => {
  return (
    <Card className="dashboard-panel h-100">
      <Card.Body className="text-center">
        <div className={`text-${variant} mb-2`}>
          <h2 className="mb-0">{value}</h2>
        </div>
        <h6 className="card-title">{title}</h6>
        {subtitle && <small className="text-muted">{subtitle}</small>}
      </Card.Body>
    </Card>
  );
};

const TrendsTable = ({ data }) => {
  if (!data || data.length === 0) {
    return <div className="text-muted">No recent activity</div>;
  }


  // Group by date and aggregate
  const groupedData = data.reduce((acc, item) => {
    const date = item.date;
    if (!acc[date]) {
      acc[date] = { resolved: 0, dismissed: 0 };
    }
    acc[date][item.status] = item.count;
    return acc;
  }, {});

  return (
    <Table size="sm" responsive>
      <thead>
        <tr>
          <th>Date</th>
          <th>Resolved</th>
          <th>Dismissed</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(groupedData)
          .sort(([a], [b]) => new Date(b) - new Date(a))
          .slice(0, 10)
          .map(([date, counts]) => {
            return (
              <tr key={date}>
                <td>{date}</td>
                <td>
                  <Badge bg="success">{counts.resolved || 0}</Badge>
                </td>
                <td>
                  <Badge bg="warning">{counts.dismissed || 0}</Badge>
                </td>
              </tr>
            );
          })}
      </tbody>
    </Table>
  );
};

const DailyBreakdownTable = ({ data }) => {
  if (!data || data.length === 0) {
    return <div className="text-muted">No daily breakdown available</div>;
  }

  return (
    <Table size="sm" responsive>
      <thead>
        <tr>
          <th>Date</th>
          <th>Resolved</th>
          <th>Dismissed</th>
          <th>In Progress</th>
          <th>Assignments</th>
          <th>Takedown req.</th>
          <th>PhishLabs</th>
          <th>GSB Reports</th>
        </tr>
      </thead>
      <tbody>
        {data
          .sort((a, b) => new Date(b.date) - new Date(a.date))
          .map((day) => (
            <tr key={day.date}>
              <td>{day.date}</td>
              <td><Badge bg="success">{day.resolved_count}</Badge></td>
              <td><Badge bg="warning">{day.dismissed_count}</Badge></td>
              <td><Badge bg="info">{day.inprogress_count}</Badge></td>
              <td><Badge bg="primary">{day.assignment_count}</Badge></td>
              <td><Badge bg="secondary">{day.takedown_requested_count ?? 0}</Badge></td>
              <td><Badge bg="danger">{day.phishlabs_count}</Badge></td>
              <td><Badge bg="info">{day.gsb_count || 0}</Badge></td>
            </tr>
          ))}
      </tbody>
    </Table>
  );
};

const TeamPerformanceTable = ({ data }) => {
  if (!data || data.length === 0) {
    return <div className="text-muted">No team performance data available</div>;
  }

  return (
    <Table size="sm" responsive>
      <thead>
        <tr>
          <th>Team Member</th>
          <th>Resolved</th>
          <th>Dismissed</th>
          <th>Assignments</th>
          <th>PhishLabs</th>
          <th>GSB Reports</th>
          <th>Total Actions</th>
        </tr>
      </thead>
      <tbody>
        {data.map((member) => (
          <tr key={member.username}>
            <td><strong>{member.username}</strong></td>
            <td><Badge bg="success">{member.resolved_count}</Badge></td>
            <td><Badge bg="warning">{member.dismissed_count}</Badge></td>
            <td><Badge bg="primary">{member.assignment_count}</Badge></td>
            <td><Badge bg="danger">{member.phishlabs_count}</Badge></td>
            <td><Badge bg="info">{member.gsb_count || 0}</Badge></td>
            <td><Badge bg="dark">{member.total_actions}</Badge></td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
};

const DailyCreationBreakdownTable = ({ data }) => {
  if (!data || data.length === 0) {
    return <div className="text-muted">No daily creation data available</div>;
  }

  // Group data by date and aggregate by source
  const groupedData = data.reduce((acc, item) => {
    const date = item.date;
    if (!acc[date]) {
      acc[date] = { manual: 0, recordedfuture: 0, threatstream: 0 };
    }
    acc[date][item.source] = item.count;
    return acc;
  }, {});

  return (
    <Table size="sm" responsive>
      <thead>
        <tr>
          <th>Date</th>
          <th>Manual</th>
          <th>RecordedFuture</th>
          <th>ThreatStream</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(groupedData)
          .sort(([a], [b]) => new Date(b) - new Date(a))
          .slice(0, 10)
          .map(([date, counts]) => {
            const total = (counts.manual || 0) + (counts.recordedfuture || 0) + (counts.threatstream || 0);
            return (
              <tr key={date}>
                <td>{date}</td>
                <td>
                  <Badge bg="secondary">{counts.manual || 0}</Badge>
                </td>
                <td>
                  <Badge bg="primary">{counts.recordedfuture || 0}</Badge>
                </td>
                <td>
                  <Badge bg="info">{counts.threatstream || 0}</Badge>
                </td>
                <td>
                  <Badge bg="dark">{total}</Badge>
                </td>
              </tr>
            );
          })}
      </tbody>
    </Table>
  );
};

function getDefaultCustomRange() {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 29);
  return {
    from: start.toISOString().split('T')[0],
    to: end.toISOString().split('T')[0],
  };
}

function TyposquatDashboard() {
  usePageTitle(formatPageTitle('Typosquat Dashboard'));
  const { selectedProgram, programs } = useProgramFilter();

  const initialCustom = getDefaultCustomRange();
  // State
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);
  const [singleDate, setSingleDate] = useState(new Date().toISOString().split('T')[0]);
  const [dateMode, setDateMode] = useState('single'); // 'period', 'single', or 'custom'
  const [customDateFrom, setCustomDateFrom] = useState(initialCustom.from);
  const [customDateTo, setCustomDateTo] = useState(initialCustom.to);
  const [selectedProgramFilter, setSelectedProgramFilter] = useState('');
  const todayIso = new Date().toISOString().split('T')[0];

  // Fetch dashboard data
  const fetchDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const program = selectedProgramFilter || selectedProgram;
      let response;
      if (dateMode === 'custom') {
        response = await api.findings.typosquat.getDashboardKpis({
          dateFrom: customDateFrom,
          dateTo: customDateTo,
          program,
        });
      } else if (dateMode === 'single') {
        response = await api.findings.typosquat.getDashboardKpis({
          singleDate,
          program,
        });
      } else {
        response = await api.findings.typosquat.getDashboardKpis({
          days,
          program,
        });
      }

      if (response.status === 'success') {
        setDashboardData(response.data);
      } else {
        setError('Failed to load dashboard data');
      }
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
      setError(err.response?.data?.detail || 'Error loading dashboard data');
    } finally {
      setLoading(false);
    }
  }, [
    days,
    singleDate,
    dateMode,
    customDateFrom,
    customDateTo,
    selectedProgramFilter,
    selectedProgram,
  ]);

  // Load data on component mount and when filters change
  useEffect(() => {
    if (dateMode === 'period') {
      fetchDashboardData();
    } else if (dateMode === 'single' && singleDate) {
      fetchDashboardData();
    } else if (
      dateMode === 'custom' &&
      customDateFrom &&
      customDateTo &&
      customDateFrom <= customDateTo
    ) {
      fetchDashboardData();
    }
  }, [fetchDashboardData, dateMode, singleDate, customDateFrom, customDateTo]);

  const formatActionTaken = (actionTaken) => {
    const mapping = {
      'takedown_requested': 'Takedown Requested',
      'reported_google_safe_browsing': 'Reported to Google Safe Browsing',
      'blocked_firewall': 'Blocked on Firewall',
      'monitoring': 'Monitoring',
      'other': 'Other'
    };
    return mapping[actionTaken] || actionTaken;
  };

  if (loading) {
    return (
      <Container className="mt-4">
        <div className="text-center">
          <Spinner animation="border" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <div className="mt-2">Loading dashboard...</div>
        </div>
      </Container>
    );
  }

  if (error) {
    return (
      <Container className="mt-4">
        <Alert variant="danger">{error}</Alert>
      </Container>
    );
  }

  const lifetimeTotals = dashboardData?.lifetime_totals || {};
  const periodSummary = dashboardData?.period_summary || {};
  const statusDistribution = dashboardData?.status_distribution || {};
  const assigneeDistribution = dashboardData?.assignee_distribution || {};
  const resolutionTrends = dashboardData?.resolution_trends || [];
  const actionDistribution = dashboardData?.action_distribution || {};
  const dailyBreakdown = dashboardData?.daily_breakdown || [];
  const creationBreakdown = dashboardData?.creation_breakdown || [];

  const teamPerformance = dashboardData?.team_performance || [];
  const isSingleDay = dashboardData?.date_range?.is_single_day || false;

  return (
    <Container fluid className="mt-4">
      <Row className="mb-4">
        <Col md={8}>
          <h2>📊 Typosquat Findings Dashboard</h2>
          <p className="text-muted">
            Overview of typosquat domain findings and resolution activity
          </p>
        </Col>
        <Col md={4}>
          <Row>
            <Col md={12} className="mb-2">
              <Form.Group>
                <Form.Label>Date Selection Mode</Form.Label>
                <Form.Select
                  value={dateMode}
                  onChange={(e) => {
                    const v = e.target.value;
                    setDateMode(v);
                    if (v === 'custom') {
                      const d = getDefaultCustomRange();
                      setCustomDateFrom(d.from);
                      setCustomDateTo(d.to);
                    }
                  }}
                >
                  <option value="period">Time Period</option>
                  <option value="single">Single Day</option>
                  <option value="custom">Custom range</option>
                </Form.Select>
              </Form.Group>
            </Col>
            {dateMode === 'period' && (
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Time Period</Form.Label>
                  <Form.Select
                    value={days}
                    onChange={(e) => setDays(parseInt(e.target.value))}
                  >
                    <option value={7}>Last 7 days (including today)</option>
                    <option value={30}>Last 30 days (including today)</option>
                    <option value={90}>Last 90 days (including today)</option>
                    <option value={365}>Last year (including today)</option>
                  </Form.Select>
                </Form.Group>
              </Col>
            )}
            {dateMode === 'single' && (
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Select Date</Form.Label>
                  <Form.Control
                    type="date"
                    value={singleDate}
                    onChange={(e) => setSingleDate(e.target.value)}
                    max={todayIso}
                  />
                </Form.Group>
              </Col>
            )}
            {dateMode === 'custom' && (
              <>
                <Col md={6}>
                  <Form.Group>
                    <Form.Label>From</Form.Label>
                    <Form.Control
                      type="date"
                      value={customDateFrom}
                      onChange={(e) => setCustomDateFrom(e.target.value)}
                      max={customDateTo || todayIso}
                    />
                  </Form.Group>
                </Col>
                <Col md={6}>
                  <Form.Group>
                    <Form.Label>To</Form.Label>
                    <Form.Control
                      type="date"
                      value={customDateTo}
                      onChange={(e) => setCustomDateTo(e.target.value)}
                      min={customDateFrom}
                      max={todayIso}
                    />
                  </Form.Group>
                </Col>
              </>
            )}
            <Col md={6}>
              <Form.Group>
                <Form.Label>Program</Form.Label>
                <Form.Select
                  value={selectedProgramFilter}
                  onChange={(e) => setSelectedProgramFilter(e.target.value)}
                >
                  <option value="">All Programs</option>
                  {programs?.map((program) => (
                    <option key={program.id} value={program.name}>
                      {program.name}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
          </Row>
        </Col>
      </Row>

      {/* Lifetime Totals */}
      <Row className="mb-4">
        <Col md={12}>
          <Card className="dashboard-panel bg-light">
            <Card.Header>
              <h5 className="mb-0 text-muted">📊 Lifetime Totals (All Time)</h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={2}>
                  <StatusCard
                    title="Total Findings"
                    value={lifetimeTotals.total_findings}
                    variant="primary"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="New"
                    value={lifetimeTotals.new_count}
                    variant="secondary"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="In Progress"
                    value={lifetimeTotals.inprogress_count}
                    variant="info"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="Resolved"
                    value={lifetimeTotals.resolved_count}
                    variant="success"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="Dismissed"
                    value={lifetimeTotals.dismissed_count}
                    variant="warning"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="Assigned"
                    value={lifetimeTotals.assigned_count}
                    variant="dark"
                  />
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Period Activity */}
      <Row className="mb-4">
        <Col md={12}>
          <Card className="dashboard-panel bg-info-subtle">
            <Card.Header>
              <h5 className="mb-0 text-primary">
                ⚡ Activity in {isSingleDay ? 'Selected Day' : 'Selected Period'}
              </h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={2}>
                  <StatusCard
                    title="Resolved"
                    value={periodSummary.resolved_count || 0}
                    variant="success"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="Dismissed"
                    value={periodSummary.dismissed_count || 0}
                    variant="warning"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="In Progress"
                    value={periodSummary.inprogress_count || 0}
                    variant="info"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="Assignments"
                    value={periodSummary.assignment_count || 0}
                    variant="primary"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="PhishLabs Incidents"
                    value={periodSummary.phishlabs_count || 0}
                    variant="danger"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="GSB Reports"
                    value={periodSummary.gsb_count || 0}
                    variant="info"
                  />
                </Col>
                <Col md={2}>
                  <StatusCard
                    title="Recent Changes"
                    value={lifetimeTotals.recent_changes_24h}
                    variant="dark"
                    subtitle="Last 24 hours"
                  />
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Charts and Tables */}
      <Row className="mb-4">
        <Col md={6}>
          <Card className="dashboard-panel h-100">
            <Card.Header>
              <h5 className="mb-0">📋 Status Distribution</h5>
            </Card.Header>
            <Card.Body>
              <SimpleBarChart
                data={statusDistribution}
                title="Findings by Status"
              />
            </Card.Body>
          </Card>
        </Col>
        <Col md={6}>
          <Card className="dashboard-panel h-100">
            <Card.Header>
              <h5 className="mb-0">👥 Top Assignees</h5>
            </Card.Header>
            <Card.Body>
              <SimpleBarChart
                data={assigneeDistribution}
                title="Findings by Assignee"
              />
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="mb-4">
        <Col md={6}>
          <Card className="dashboard-panel h-100">
            <Card.Header>
              <h5 className="mb-0">📈 Recent Activity</h5>
            </Card.Header>
            <Card.Body>
              <TrendsTable data={resolutionTrends} />
            </Card.Body>
          </Card>
        </Col>
        <Col md={6}>
          <Card className="dashboard-panel h-100">
            <Card.Header>
              <h5 className="mb-0">⚡ Resolution Actions</h5>
            </Card.Header>
            <Card.Body>
              {Object.keys(actionDistribution).length > 0 ? (
                <SimpleBarChart
                  data={Object.fromEntries(
                    Object.entries(actionDistribution).map(([key, value]) => [
                      formatActionTaken(key),
                      value
                    ])
                  )}
                  title="Actions Taken for Resolved Findings"
                />
              ) : (
                <div className="text-muted">No resolution actions recorded</div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Time Series Activity Chart */}
      {dashboardData?.time_series_data && dashboardData.time_series_data.length > 0 && (
        <Row className="mb-4">
          <Col md={12}>
            <Card className="dashboard-panel">
              <Card.Header>
                <h5 className="mb-0">📊 {isSingleDay ? 'Hourly' : 'Daily'} Activity</h5>
              </Card.Header>
              <Card.Body>
                <TimeSeriesLineChart
                  data={dashboardData.time_series_data}
                  title="Findings Created, Resolved, and Dismissed"
                  isHourly={isSingleDay}
                />
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Daily Breakdown - Only show for multi-day periods */}
      {!isSingleDay && dailyBreakdown.length > 0 && (
        <Row className="mb-4">
          <Col md={12}>
            <Card className="dashboard-panel">
              <Card.Header>
                <h5 className="mb-0">📅 Daily Activity Breakdown</h5>
              </Card.Header>
              <Card.Body>
                <DailyBreakdownTable data={dailyBreakdown} />
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Daily Creation Breakdown by Source */}
      {creationBreakdown.length > 0 && (
        <Row className="mb-4">
          <Col md={12}>
            <Card className="dashboard-panel">
              <Card.Header>
                <h5 className="mb-0">🔍 Daily Creation Breakdown by Source</h5>
              </Card.Header>
              <Card.Body>
                <DailyCreationBreakdownTable data={creationBreakdown} />
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Team Performance */}
      {teamPerformance.length > 0 && (
        <Row className="mb-4">
          <Col md={12}>
            <Card className="dashboard-panel">
              <Card.Header>
                <h5 className="mb-0">👥 Team Performance {isSingleDay ? '(Selected Day)' : '(Selected Period)'}</h5>
              </Card.Header>
              <Card.Body>
                <TeamPerformanceTable data={teamPerformance} />
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* Additional Stats */}
      <Row>
        <Col md={12}>
          <Card className="dashboard-panel">
            <Card.Header>
              <h5 className="mb-0">📊 Statistics Summary</h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={3}>
                  <div className="text-center">
                    <h4 className="text-success">
                      {lifetimeTotals.total_findings > 0
                        ? Math.round((lifetimeTotals.resolved_count / lifetimeTotals.total_findings) * 100)
                        : 0}%
                    </h4>
                    <small className="text-muted">Overall Resolution Rate</small>
                  </div>
                </Col>
                <Col md={3}>
                  <div className="text-center">
                    <h4 className="text-info">
                      {lifetimeTotals.total_findings > 0
                        ? Math.round((lifetimeTotals.assigned_count / lifetimeTotals.total_findings) * 100)
                        : 0}%
                    </h4>
                    <small className="text-muted">Overall Assignment Rate</small>
                  </div>
                </Col>
                <Col md={3}>
                  <div className="text-center">
                    <h4 className="text-primary">
                      {lifetimeTotals.resolved_count + lifetimeTotals.dismissed_count}
                    </h4>
                    <small className="text-muted">Total Closed (Lifetime)</small>
                  </div>
                </Col>
                <Col md={3}>
                  <div className="text-center">
                    <h4 className="text-warning">
                      {(periodSummary.resolved_count || 0) + (periodSummary.dismissed_count || 0) + (periodSummary.inprogress_count || 0) + (periodSummary.assignment_count || 0) + (periodSummary.phishlabs_count || 0) + (periodSummary.gsb_count || 0)}
                    </h4>
                    <small className="text-muted">Period Activity Total</small>
                  </div>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Data Range Info */}
      <Row className="mt-3">
        <Col md={12}>
          <div className="text-muted small text-center">
            Data range: {new Date(dashboardData?.date_range?.start_date).toLocaleDateString()} - {new Date(dashboardData?.date_range?.end_date).toLocaleDateString()}
            {!dashboardData?.date_range?.is_single_day && ' (including current day)'}
            {selectedProgramFilter && ` • Filtered by: ${selectedProgramFilter}`}
          </div>
        </Col>
      </Row>
    </Container>
  );
}

export default TyposquatDashboard;