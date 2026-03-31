import React from 'react';
import { Nav, Navbar, Button, Dropdown, Form, Container } from 'react-bootstrap';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useProgramFilter } from '../contexts/ProgramFilterContext';
import { useTheme } from '../contexts/ThemeContext';
import ThemeToggle from './ThemeToggle';
import BrandLogo from './BrandLogo';

function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, user, logout, isSuperuser, isAdmin } = useAuth();
  const { selectedProgram, setSelectedProgram, programs, clearFilter } = useProgramFilter();
  const { isLight } = useTheme();

  const isActive = (path) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  const hasAnyManagerPermission = () => {
    if (isSuperuser() || isAdmin()) return true;
    
    // Check if user has manager permission on any program
    if (!user || !user.program_permissions) return false;
    
    const programPermissions = user.program_permissions || {};
    
    // Handle both old list format and new dict format
    if (typeof programPermissions === 'object' && !Array.isArray(programPermissions)) {
      // New dict format: check if any permission level is 'manager'
      return Object.values(programPermissions).includes('manager');
    }
    
    return false;
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  // Theme-aware navbar styling
  const navbarVariant = isLight ? 'light' : 'dark';
  const titleTextClass = isLight ? 'text-dark' : 'text-light';

  return (
    <Navbar bg={navbarVariant} variant={navbarVariant} expand="lg" className="px-3 py-2" sticky="top">
      <Container fluid>
        {/* Brand */}
        <Navbar.Brand as={Link} to="/" className="me-4 d-flex align-items-center gap-2 text-decoration-none">
          <BrandLogo height={36} className={isLight ? 'brand-logo--navbar-light' : ''} />
          <span className={`fw-semibold mb-0 ${titleTextClass}`}>ReconHawx</span>
        </Navbar.Brand>

        <Navbar.Toggle aria-controls="main-navbar" />
        <Navbar.Collapse id="main-navbar">
          {isAuthenticated && (
          <Nav className="me-auto">
            {/* Dashboard */}
            <Nav.Link 
              as={Link} 
              to="/dashboard" 
              className={isActive('/dashboard') || isActive('/') ? 'active' : ''}
            >
              📊 Dashboard
            </Nav.Link>

            {/* Assets Dropdown */}
            <Dropdown as={Nav.Item} className="me-2">
              <Dropdown.Toggle as={Nav.Link} className="dropdown-toggle">
                🎯 Assets
              </Dropdown.Toggle>
              <Dropdown.Menu>
                <Dropdown.Item as={Link} to="/assets/subdomains">
                  🌐 Subdomains
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/assets/apex-domains">
                  🎯 Apex Domains
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/assets/ips">
                  🖥️ IP Addresses
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/assets/urls">
                  🔗 URLs
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/assets/services">
                  ⚙️ Services
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/assets/certificates">
                  🔐 Certificates
                </Dropdown.Item>
                <Dropdown.Divider />
                <Dropdown.Item as={Link} to="/assets/technologies">
                  ⚙️ Technologies
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/assets/screenshots">
                  📸 Screenshots
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>

            {/* Findings Dropdown */}
            <Dropdown as={Nav.Item} className="me-2">
              <Dropdown.Toggle as={Nav.Link} className="dropdown-toggle">
                🎯 Findings
              </Dropdown.Toggle>
              <Dropdown.Menu>
                <Dropdown.Item as={Link} to="/findings/nuclei">
                  🎯 Nuclei Findings
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/findings/wpscan">
                  🔒 WPScan Findings
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/findings/broken-links">
                  🔗 Broken Links
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/findings/external-links">
                  🔗 External Links
                </Dropdown.Item>
                <Dropdown.Divider />
                <Dropdown.Header>🔤 Typosquats</Dropdown.Header>
                <Dropdown.Item as={Link} to="/findings/typosquat/dashboard">
                  📊 Typosquat Dashboard
                </Dropdown.Item>
                <Dropdown.Divider />
                <Dropdown.Item as={Link} to="/findings/typosquat">
                  🔤 Typosquat Domains
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/findings/typosquat-urls">
                  🔗 Typosquat URLs
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/findings/typosquat-screenshots">
                  📸 Typosquat Screenshots
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>

            {/* Workflows Dropdown */}
            <Dropdown as={Nav.Item} className="me-2">
              <Dropdown.Toggle as={Nav.Link} className="dropdown-toggle">
                📊 Workflows
              </Dropdown.Toggle>
              <Dropdown.Menu>
                <Dropdown.Item as={Link} to="/workflows">
                  📊 Dashboard
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/workflows/run">
                  ▶️ Run Workflow
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/workflows?tab=single-task">
                  🔧 Run Single Task
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/workflows/list">
                  📋 Saved Workflows
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/workflows/status">
                  📈 Status Monitor
                </Dropdown.Item>
                <Dropdown.Divider />
                <Dropdown.Item as={Link} to="/scheduled-jobs">
                  ⏰ Scheduled Jobs
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>

            {/* Templates Dropdown */}
            <Dropdown as={Nav.Item} className="me-2">
              <Dropdown.Toggle as={Nav.Link} className="dropdown-toggle">
                📚 Templates
              </Dropdown.Toggle>
              <Dropdown.Menu>
                <Dropdown.Item as={Link} to="/admin/nuclei-templates">
                  🎯 Nuclei Templates
                </Dropdown.Item>
                <Dropdown.Item as={Link} to="/admin/wordlists">
                  📚 Wordlists
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>

            {/* Administration Dropdown */}
            {(isSuperuser() || hasAnyManagerPermission()) && (
              <Dropdown as={Nav.Item} className="me-2">
                <Dropdown.Toggle as={Nav.Link} className="dropdown-toggle">
                  ⚙️ Administration
                </Dropdown.Toggle>
                <Dropdown.Menu>
                  <Dropdown.Item as={Link} to="/programs">
                    📁 Programs
                  </Dropdown.Item>
                  {(isSuperuser() || isAdmin()) && (
                    <>
                      <Dropdown.Divider />
                      <Dropdown.Item as={Link} to="/admin/events">
                        📊 Event Queue Stats
                      </Dropdown.Item>
                    </>
                  )}
                  {isSuperuser() && (
                    <>
                      <Dropdown.Item as={Link} to="/admin/users">
                        👥 User Management
                      </Dropdown.Item>
                      <Dropdown.Item as={Link} to="/admin/jobs">
                        ⚙️ Job Management
                      </Dropdown.Item>
                      <Dropdown.Item as={Link} to="/admin/settings">
                        ⚙️ System Settings
                      </Dropdown.Item>
                      <Dropdown.Item as={Link} to="/admin/social-media-credentials">
                        🔑 Social Media Credentials
                      </Dropdown.Item>
                      <Dropdown.Item as={Link} to="/admin/ct-monitor">
                        🔍 CT Monitor
                      </Dropdown.Item>
                      <Dropdown.Item as={Link} to="/admin/event-handler-config">
                        ⚡ Event Handlers
                      </Dropdown.Item>
                      <Dropdown.Divider />
                      <Dropdown.Item as={Link} to="/admin/system-status">
                        🖥️ System Status
                      </Dropdown.Item>
                    </>
                  )}
                </Dropdown.Menu>
              </Dropdown>
            )}
          </Nav>
          )}

          {/* Right side controls */}
          <Nav className="ms-auto align-items-center">
            {/* Theme Toggle */}
            <div className="me-3">
              <ThemeToggle />
            </div>

            {/* Global Program Filter */}
            {isAuthenticated && user && (
              <div className="me-3" style={{ minWidth: '200px' }}>
                <Form.Group className="mb-0">
                  <Form.Select
                    size="sm"
                    value={selectedProgram}
                    onChange={(e) => setSelectedProgram(e.target.value)}
                    style={{ fontSize: '0.875rem' }}
                  >
                    <option value="">🎯 All Programs</option>
                    {programs.map((program) => {
                      const programName = typeof program === 'string' ? program : program.name;
                      return (
                        <option key={programName} value={programName}>
                          {programName}
                        </option>
                      );
                    })}
                  </Form.Select>
                </Form.Group>
                {selectedProgram && (
                  <div className="d-flex align-items-center mt-1">
                    <small className={`me-2 ${isLight ? 'text-dark' : 'text-light'}`}>
                      Filtering: <strong>{selectedProgram}</strong>
                    </small>
                    <Button
                      variant={isLight ? 'outline-dark' : 'outline-light'}
                      size="sm"
                      onClick={clearFilter}
                      title="Clear filter"
                      style={{ padding: '0.125rem 0.25rem', fontSize: '0.75rem' }}
                    >
                      ×
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* User Menu */}
            {isAuthenticated && user && (
              <Dropdown>
                <Dropdown.Toggle variant={isLight ? 'outline-dark' : 'outline-light'} size="sm" className="d-flex align-items-center">
                  👤 {user.username}
                  {isSuperuser() && <span className="badge bg-danger ms-2">Superuser</span>}
                  {isAdmin() && !isSuperuser() && <span className="badge bg-warning ms-2">Admin</span>}
                </Dropdown.Toggle>
                <Dropdown.Menu align="end">
                  <Dropdown.Item disabled>
                    <strong>{user.username}</strong>
                    <br />
                    <small className="text-muted">{user.email || 'No email'}</small>
                  </Dropdown.Item>
                  <Dropdown.Divider />
                  <Dropdown.Item as={Link} to="/settings/api-tokens">
                    🔑 API Tokens
                  </Dropdown.Item>
                  <Dropdown.Divider />
                  <Dropdown.Item onClick={handleLogout}>
                    🚪 Sign Out
                  </Dropdown.Item>
                </Dropdown.Menu>
              </Dropdown>
            )}
          </Nav>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}

export default Navigation;