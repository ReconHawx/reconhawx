import React, { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Container } from 'react-bootstrap';
import { AuthProvider } from './contexts/AuthContext';
import { ProgramFilterProvider } from './contexts/ProgramFilterContext';
import { ThemeProvider } from './contexts/ThemeContext';
import Navigation from './components/Navigation';
import Login from './components/Login';
import ProtectedRoute from './components/ProtectedRoute';
import PublicHealthStatus from './components/PublicHealthStatus';
import LoadingFallback from './components/LoadingFallback';

// Lazy load all page components for better code splitting
const Dashboard = lazy(() => import('./pages/Dashboard'));
const ChangePassword = lazy(() => import('./pages/ChangePassword'));

// Assets
const Subdomains = lazy(() => import('./pages/assets/Subdomains'));
const SubdomainDetail = lazy(() => import('./pages/assets/SubdomainDetail'));
const IPs = lazy(() => import('./pages/assets/IPs'));
const IPDetail = lazy(() => import('./pages/assets/IPDetail'));
const URLs = lazy(() => import('./pages/assets/URLs'));
const URLDetail = lazy(() => import('./pages/assets/URLDetail'));
const Services = lazy(() => import('./pages/assets/Services'));
const ServiceDetail = lazy(() => import('./pages/assets/ServiceDetail'));
const Certificates = lazy(() => import('./pages/assets/Certificates'));
const CertificateDetail = lazy(() => import('./pages/assets/CertificateDetail'));
const Technologies = lazy(() => import('./pages/assets/Technologies'));
const Screenshots = lazy(() => import('./pages/assets/Screenshots'));
const ApexDomains = lazy(() => import('./pages/assets/ApexDomains'));
const ApexDomainDetail = lazy(() => import('./pages/assets/ApexDomainDetail'));

// Findings
const NucleiFindings = lazy(() => import('./pages/findings/NucleiFindings'));
const NucleiFindingDetail = lazy(() => import('./pages/findings/NucleiFindingDetail'));
const WPScanFindings = lazy(() => import('./pages/findings/WPScanFindings'));
const WPScanFindingDetail = lazy(() => import('./pages/findings/WPScanFindingDetail'));
const TyposquatFindings = lazy(() => import('./pages/findings/TyposquatFindings'));
const TyposquatFindingDetail = lazy(() => import('./pages/findings/TyposquatFindingDetail'));
const BrokenLinks = lazy(() => import('./pages/findings/BrokenLinks'));
const BrokenLinkDetail = lazy(() => import('./pages/findings/BrokenLinkDetail'));
const TyposquatUrlDetails = lazy(() => import('./pages/findings/TyposquatUrlDetails'));
const TyposquatUrls = lazy(() => import('./pages/findings/TyposquatUrls'));
const TyposquatScreenshots = lazy(() => import('./pages/findings/TyposquatScreenshots'));
const SSLCertificateDashboard = lazy(() => import('./pages/findings/SSLCertificateDashboard'));
const ExternalLinks = lazy(() => import('./pages/findings/ExternalLinks'));

// Dashboards
const TyposquatDashboard = lazy(() => import('./pages/dashboards/TyposquatDashboard'));
const TyposquatActionLogs = lazy(() => import('./pages/dashboards/TyposquatActionLogs'));

// Programs
const Programs = lazy(() => import('./pages/programs/Programs'));
const ProgramDetail = lazy(() => import('./pages/programs/ProgramDetail'));

// Workflows
const Workflows = lazy(() => import('./pages/workflows/Workflows'));
const WorkflowList = lazy(() => import('./pages/workflows/WorkflowList'));
const WorkflowRun = lazy(() => import('./pages/workflows/WorkflowRun'));
const WorkflowStatus = lazy(() => import('./pages/workflows/WorkflowStatus'));
const WorkflowStatusDetail = lazy(() => import('./pages/workflows/WorkflowStatusDetail'));
const WorkflowCreate = lazy(() => import('./pages/workflows/WorkflowCreate'));

// Scheduled Jobs
const ScheduledJobs = lazy(() => import('./pages/scheduled-jobs/ScheduledJobs'));
const ScheduledJobDetail = lazy(() => import('./pages/scheduled-jobs/ScheduledJobDetail'));
const ScheduledJobCreate = lazy(() => import('./pages/scheduled-jobs/ScheduledJobCreate'));

// Admin
const UserManagement = lazy(() => import('./pages/admin/UserManagement'));
const ApiTokens = lazy(() => import('./pages/admin/ApiTokens'));
const NucleiTemplates = lazy(() => import('./pages/admin/NucleiTemplates'));
const Wordlists = lazy(() => import('./pages/admin/Wordlists'));
const SystemSettings = lazy(() => import('./pages/admin/SystemSettings'));
const SystemStatus = lazy(() => import('./pages/admin/SystemStatus'));
const SystemMaintenance = lazy(() => import('./pages/admin/SystemMaintenance'));

function AppContent() {
  return (
    <Router>
      <div className="d-flex flex-column min-vh-100">
        <Navigation />
        <main className="flex-grow-1" style={{ paddingTop: '20px' }}>
          <Container fluid>
            <Suspense fallback={<LoadingFallback />}>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/status" element={<PublicHealthStatus />} />
                <Route path="/change-password" element={
                  <ProtectedRoute>
                    <ChangePassword />
                  </ProtectedRoute>
                } />
                <Route path="/" element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                } />
                <Route path="/dashboard" element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                } />
                <Route path="/assets/domains" element={
                  <ProtectedRoute>
                    <Subdomains />
                  </ProtectedRoute>
                } />
                <Route path="/assets/subdomains" element={
                  <ProtectedRoute>
                    <Subdomains />
                  </ProtectedRoute>
                } />
                <Route path="/assets/subdomains/details" element={
                  <ProtectedRoute>
                    <SubdomainDetail />
                  </ProtectedRoute>
                } />
                <Route path="/assets/apex-domains" element={
                  <ProtectedRoute>
                    <ApexDomains />
                  </ProtectedRoute>
                } />
                <Route path="/assets/apex-domain/details" element={
                  <ProtectedRoute>
                    <ApexDomainDetail />
                  </ProtectedRoute>
                } />
                <Route path="/assets/ips" element={
                  <ProtectedRoute>
                    <IPs />
                  </ProtectedRoute>
                } />
                <Route path="/assets/ips/details" element={
                  <ProtectedRoute>
                    <IPDetail />
                  </ProtectedRoute>
                } />
                <Route path="/assets/urls" element={
                  <ProtectedRoute>
                    <URLs />
                  </ProtectedRoute>
                } />
                <Route path="/assets/urls/details" element={
                  <ProtectedRoute>
                    <URLDetail />
                  </ProtectedRoute>
                } />
                <Route path="/assets/services" element={
                  <ProtectedRoute>
                    <Services />
                  </ProtectedRoute>
                } />
                <Route path="/assets/services/details" element={
                  <ProtectedRoute>
                    <ServiceDetail />
                  </ProtectedRoute>
                } />
                <Route path="/assets/certificates" element={
                  <ProtectedRoute>
                    <Certificates />
                  </ProtectedRoute>
                } />
                <Route path="/assets/certificates/details" element={
                  <ProtectedRoute>
                    <CertificateDetail />
                  </ProtectedRoute>
                } />
                <Route path="/assets/technologies" element={
                  <ProtectedRoute>
                    <Technologies />
                  </ProtectedRoute>
                } />
                <Route path="/assets/screenshots" element={
                  <ProtectedRoute>
                    <Screenshots />
                  </ProtectedRoute>
                } />
                <Route path="/findings/nuclei" element={
                  <ProtectedRoute>
                    <NucleiFindings />
                  </ProtectedRoute>
                } />
                <Route path="/findings/nuclei/details" element={
                  <ProtectedRoute>
                    <NucleiFindingDetail />
                  </ProtectedRoute>
                } />
                <Route path="/findings/wpscan" element={
                  <ProtectedRoute>
                    <WPScanFindings />
                  </ProtectedRoute>
                } />
                <Route path="/findings/wpscan/details" element={
                  <ProtectedRoute>
                    <WPScanFindingDetail />
                  </ProtectedRoute>
                } />
                <Route path="/findings/typosquat" element={
                  <ProtectedRoute>
                    <TyposquatFindings />
                  </ProtectedRoute>
                } />
                <Route path="/findings/typosquat/dashboard" element={
                  <ProtectedRoute>
                    <TyposquatDashboard />
                  </ProtectedRoute>
                } />
                <Route path="/findings/typosquat/logs" element={
                  <ProtectedRoute>
                    <TyposquatActionLogs />
                  </ProtectedRoute>
                } />
                <Route path="/findings/typosquat/details" element={
                  <ProtectedRoute>
                    <TyposquatFindingDetail />
                  </ProtectedRoute>
                } />
                <Route path="/findings/typosquat-urls" element={
                  <ProtectedRoute>
                    <TyposquatUrls />
                  </ProtectedRoute>
                } />
                <Route path="/findings/typosquat-urls/details" element={
                  <ProtectedRoute>
                    <TyposquatUrlDetails />
                  </ProtectedRoute>
                } />
                <Route path="/findings/typosquat-screenshots" element={
                  <ProtectedRoute>
                    <TyposquatScreenshots />
                  </ProtectedRoute>
                } />
                <Route path="/findings/ssl-dashboard" element={
                  <ProtectedRoute>
                    <SSLCertificateDashboard />
                  </ProtectedRoute>
                } />
                <Route path="/findings/external-links" element={
                  <ProtectedRoute>
                    <ExternalLinks />
                  </ProtectedRoute>
                } />
                <Route path="/findings/broken-links" element={
                  <ProtectedRoute>
                    <BrokenLinks />
                  </ProtectedRoute>
                } />
                <Route path="/findings/broken-links/details" element={
                  <ProtectedRoute>
                    <BrokenLinkDetail />
                  </ProtectedRoute>
                } />
                <Route path="/programs" element={
                  <ProtectedRoute>
                    <Programs />
                  </ProtectedRoute>
                } />
                <Route path="/programs/:programName" element={
                  <ProtectedRoute>
                    <ProgramDetail />
                  </ProtectedRoute>
                } />
                <Route path="/workflows" element={
                  <ProtectedRoute>
                    <Workflows />
                  </ProtectedRoute>
                } />
                <Route path="/workflows/list" element={
                  <ProtectedRoute>
                    <WorkflowList />
                  </ProtectedRoute>
                } />
                <Route path="/workflows/create" element={
                  <ProtectedRoute>
                    <WorkflowCreate />
                  </ProtectedRoute>
                } />
                <Route path="/workflows/edit/:workflowId" element={
                  <ProtectedRoute>
                    <WorkflowCreate />
                  </ProtectedRoute>
                } />
                <Route path="/workflows/run" element={
                  <ProtectedRoute>
                    <WorkflowRun />
                  </ProtectedRoute>
                } />
                <Route path="/workflows/run/:workflowId" element={
                  <ProtectedRoute>
                    <WorkflowRun />
                  </ProtectedRoute>
                } />
                <Route path="/workflows/status" element={
                  <ProtectedRoute>
                    <WorkflowStatus />
                  </ProtectedRoute>
                } />
                <Route path="/workflows/status/:workflowId" element={
                  <ProtectedRoute>
                    <WorkflowStatusDetail />
                  </ProtectedRoute>
                } />
                <Route path="/scheduled-jobs" element={
                  <ProtectedRoute>
                    <ScheduledJobs />
                  </ProtectedRoute>
                } />
                <Route path="/scheduled-jobs/:jobId" element={
                  <ProtectedRoute>
                    <ScheduledJobDetail />
                  </ProtectedRoute>
                } />
                <Route path="/scheduled-jobs/create" element={
                  <ProtectedRoute>
                    <ScheduledJobCreate />
                  </ProtectedRoute>
                } />
                <Route path="/admin/users" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <UserManagement />
                  </ProtectedRoute>
                } />
                <Route path="/admin/nuclei-templates" element={
                  <ProtectedRoute>
                    <NucleiTemplates />
                  </ProtectedRoute>
                } />
                <Route path="/admin/wordlists" element={
                  <ProtectedRoute>
                    <Wordlists />
                  </ProtectedRoute>
                } />
                <Route path="/admin/jobs" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <Navigate to="/workflows/status?tab=jobs" replace />
                  </ProtectedRoute>
                } />
                <Route path="/settings/api-tokens" element={
                  <ProtectedRoute>
                    <ApiTokens />
                  </ProtectedRoute>
                } />
                <Route path="/admin/settings" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <SystemSettings />
                  </ProtectedRoute>
                } />
                <Route path="/admin/social-media-credentials" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <Navigate to="/admin/settings?tab=social-media" replace />
                  </ProtectedRoute>
                } />
                <Route path="/admin/ct-monitor" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <Navigate to="/admin/system-status?tab=ct-monitor" replace />
                  </ProtectedRoute>
                } />
                <Route path="/admin/event-handler-config" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <Navigate to="/admin/settings?tab=event-handlers" replace />
                  </ProtectedRoute>
                } />
                <Route path="/admin/events" element={
                  <ProtectedRoute requireAdmin={true}>
                    <Navigate to="/admin/system-status?tab=events" replace />
                  </ProtectedRoute>
                } />
                <Route path="/admin/system-status" element={
                  <ProtectedRoute requireAdmin={true}>
                    <SystemStatus />
                  </ProtectedRoute>
                } />
                <Route path="/admin/database-backup" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <Navigate to="/admin/system-maintenance" replace />
                  </ProtectedRoute>
                } />
                <Route path="/admin/system-maintenance" element={
                  <ProtectedRoute requireSuperuser={true}>
                    <SystemMaintenance />
                  </ProtectedRoute>
                } />
                {/* Catch-all route - redirect unknown paths to dashboard */}
                <Route path="*" element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                } />
              </Routes>
            </Suspense>
          </Container>
        </main>
      </div>
    </Router>
  );
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ProgramFilterProvider>
          <AppContent />
        </ProgramFilterProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;