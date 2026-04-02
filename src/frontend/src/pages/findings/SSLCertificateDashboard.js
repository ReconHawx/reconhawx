import React, { useState, useEffect, useCallback } from 'react';
import { Container, Row, Col, Card, Badge, Spinner, Alert, Button, Table } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { useProgramFilter } from '../../contexts/ProgramFilterContext';
import { formatDate } from '../../utils/dateUtils';
import { usePageTitle, formatPageTitle } from '../../hooks/usePageTitle';

// Enhanced parsing functions for SSL/TLS extracted results (outside component to prevent re-creation)
const parseExtractedResults = (extracted) => {
  if (!extracted) return 'N/A';

  // Handle JSON strings
  if (typeof extracted === 'string') {
    try {
      const parsed = JSON.parse(extracted);
      if (Array.isArray(parsed)) {
        return parsed.join(', ');
      }
      return parsed;
    } catch {
      return extracted;
    }
  }

  if (Array.isArray(extracted)) {
    return extracted.join(', ');
  }

  return String(extracted);
};

// Parse TLS version from extracted results
const parseTLSVersion = (extractedResults) => {
  if (!extractedResults) return null;

  const results = parseExtractedResults(extractedResults).toLowerCase();

  // Check for specific TLS versions in the extracted results (most common formats)
  if (results.includes('tls13') || results.includes('tls1.3') || results.includes('tls 1.3') || results.includes('tlsv1.3') || results.includes('tls_1_3')) {
    return 'TLS 1.3';
  }
  if (results.includes('tls12') || results.includes('tls1.2') || results.includes('tls 1.2') || results.includes('tlsv1.2') || results.includes('tls_1_2')) {
    return 'TLS 1.2';
  }
  if (results.includes('tls11') || results.includes('tls1.1') || results.includes('tls 1.1') || results.includes('tlsv1.1') || results.includes('tls_1_1')) {
    return 'TLS 1.1';
  }
  if (results.includes('tls10') || results.includes('tls1.0') || results.includes('tls 1.0') || results.includes('tlsv1.0') || results.includes('tls_1_0')) {
    return 'TLS 1.0';
  }
  if (results.includes('sslv3') || results.includes('ssl3') || results.includes('ssl 3.0') || results.includes('ssl_3_0')) {
    return 'SSL 3.0';
  }
  if (results.includes('sslv2') || results.includes('ssl2') || results.includes('ssl 2.0') || results.includes('ssl_2_0')) {
    return 'SSL 2.0';
  }

  // If we can't parse a specific version, return the original for manual inspection
  return results;
};

// Get cipher strength by name
const getCipherStrength = (cipherName) => {
  const cipher = cipherName.toLowerCase();

  // Strong ciphers - AEAD ciphers
  if (cipher.includes('aes256-gcm') || cipher.includes('aes-256-gcm') ||
      cipher.includes('chacha20') || cipher.includes('aes128-gcm') ||
      cipher.includes('aes-128-gcm')) {
    return 'strong';
  }

  // Medium strength ciphers
  if (cipher.includes('aes256-cbc') || cipher.includes('aes-256-cbc') ||
      cipher.includes('aes128-cbc') || cipher.includes('aes-128-cbc') ||
      cipher.includes('3des')) {
    return 'medium';
  }

  // Weak ciphers
  if (cipher.includes('rc4') || cipher.includes('des') || cipher.includes('md5') ||
      cipher.includes('sha1') || cipher.includes('null')) {
    return 'weak';
  }

  return 'unknown';
};

// Parse cipher suites from extracted results
const parseCipherSuites = (extractedResults) => {
  if (!extractedResults) return [];

  const results = parseExtractedResults(extractedResults).toLowerCase();
  const ciphers = [];

  // Strong ciphers - modern AEAD ciphers
  if (results.includes('aes256-gcm') || results.includes('aes_256_gcm') || results.includes('aes256gcm')) {
    ciphers.push({ name: 'AES-256-GCM', strength: 'strong' });
  }
  if (results.includes('chacha20') || results.includes('chacha20-poly1305') || results.includes('chacha20poly1305')) {
    ciphers.push({ name: 'ChaCha20-Poly1305', strength: 'strong' });
  }
  if (results.includes('aes128-gcm') || results.includes('aes_128_gcm') || results.includes('aes128gcm')) {
    ciphers.push({ name: 'AES-128-GCM', strength: 'strong' });
  }

  // Medium strength ciphers
  if (results.includes('aes256-cbc') || results.includes('aes_256_cbc') || results.includes('aes256cbc')) {
    ciphers.push({ name: 'AES-256-CBC', strength: 'medium' });
  }
  if (results.includes('aes128-cbc') || results.includes('aes_128_cbc') || results.includes('aes128cbc')) {
    ciphers.push({ name: 'AES-128-CBC', strength: 'medium' });
  }
  if (results.includes('3des') || results.includes('des-ede3') || results.includes('tripledes')) {
    ciphers.push({ name: '3DES', strength: 'medium' });
  }

  // Weak ciphers
  if (results.includes('rc4') || results.includes('arcfour')) {
    ciphers.push({ name: 'RC4', strength: 'weak' });
  }
  if (results.includes('des') && !results.includes('3des') && !results.includes('aes')) {
    ciphers.push({ name: 'DES', strength: 'weak' });
  }
  if (results.includes('md5')) {
    ciphers.push({ name: 'MD5', strength: 'weak' });
  }
  if (results.includes('sha1') && !results.includes('sha256') && !results.includes('sha384')) {
    ciphers.push({ name: 'SHA1', strength: 'weak' });
  }
  if (results.includes('null') && (results.includes('cipher') || results.includes('encryption'))) {
    ciphers.push({ name: 'NULL Cipher', strength: 'weak' });
  }

  // If no specific ciphers were identified, don't return unknown - return empty array instead
  return ciphers;
};

// Parse certificate issuer from extracted results
const parseCertificateIssuer = (extractedResults) => {
  if (!extractedResults) return 'Unknown';

  const results = parseExtractedResults(extractedResults);

  // Try to extract organization from common formats
  if (results.includes('O=')) {
    const match = results.match(/O=([^,]+)/);
    return match ? match[1].trim() : results;
  }

  // Handle quoted formats
  if (results.includes('"') && results.includes(':')) {
    return results.replace(/["{}"]/g, '').trim();
  }

  return results;
};

const SSLCertificateDashboard = () => {
  usePageTitle(formatPageTitle('SSL Certificate Dashboard'));
  const { selectedProgram } = useProgramFilter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sslFindings, setSslFindings] = useState([]);
  const [summary, setSummary] = useState({
    total: 0,
    severityBreakdown: {},
    templateBreakdown: {},
    hostBreakdown: {},
    tlsVersions: {},
    deprecatedProtocols: {},
    cipherSuites: {},
    securityIssues: {},
    certificateIssuers: {},
    wildcardCerts: {},
    certificateStats: {
      total: 0,
      expired: 0,
      expiringSoon: 0,
      valid: 0,
      selfSigned: 0,
      wildcards: 0
    }
  });
  const [refreshing, setRefreshing] = useState(false);

  // Severity colors mapping
  const severityColors = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: 'secondary',
    info: 'primary'
  };

  // TLS/SSL Security Configuration
  const tlsVersionSecurity = {
    'tls13': { level: 'excellent', color: 'success', description: 'Latest TLS version with enhanced security' },
    'tls12': { level: 'good', color: 'info', description: 'Secure when properly configured' },
    'tls11': { level: 'deprecated', color: 'warning', description: 'Deprecated - should be disabled' },
    'tls10': { level: 'vulnerable', color: 'danger', description: 'Vulnerable - must be disabled' },
    'ssl30': { level: 'critical', color: 'danger', description: 'Critical vulnerability - POODLE attack' },
    'ssl20': { level: 'critical', color: 'danger', description: 'Critically insecure - immediate action required' }
  };

  const securityIssueTypes = {
    'deprecated-tls': { name: 'Deprecated TLS/SSL', severity: 'high', icon: '⚠️' },
    'weak-cipher': { name: 'Weak Cipher Suites', severity: 'medium', icon: '🔓' },
    'self-signed': { name: 'Self-Signed Certificate', severity: 'low', icon: '📝' },
    'certificate-mismatch': { name: 'Certificate Mismatch', severity: 'medium', icon: '❌' },
    'expired-certificate': { name: 'Expired Certificate', severity: 'high', icon: '⏰' },
    'weak-key': { name: 'Weak Key Size', severity: 'medium', icon: '🔑' }
  };

  // Template type descriptions focused on specific SSL intelligence
  const templateDescriptions = {
    'tls-version': {
      name: 'TLS Version Detection',
      description: 'Identifies TLS/SSL protocol versions in use - critical for security assessment',
      icon: '🔒',
      priority: 'critical'
    },
    'deprecated-tls': {
      name: 'Deprecated TLS Detection',
      description: 'Specifically identifies deprecated and insecure TLS/SSL protocol versions',
      icon: '⚠️',
      priority: 'critical'
    },
    'weak-cipher-suites': {
      name: 'Weak Cipher Detection',
      description: 'Identifies vulnerable cryptographic cipher suites that should be disabled',
      icon: '🔐',
      priority: 'critical'
    },
    'mismatched-ssl-certificate': {
      name: 'Certificate Hostname Mismatch',
      description: 'Detects certificates where hostname doesn\'t match CN/SAN entries',
      icon: '❌',
      priority: 'high'
    },
    'ssl-issuer': {
      name: 'Certificate Authority Analysis',
      description: 'Extracts and analyzes certificate issuing authorities',
      icon: '🏛️',
      priority: 'medium'
    },
    'wildcard-tls': {
      name: 'Wildcard Certificate Detection',
      description: 'Identifies wildcard certificates and their coverage patterns',
      icon: '🌟',
      priority: 'medium'
    },
    'self-signed-ssl': {
      name: 'Self-Signed Certificates',
      description: 'Detects certificates not issued by trusted certificate authorities',
      icon: '📝',
      priority: 'medium'
    },
    'ssl-dns-names': {
      name: 'Certificate SAN Extraction',
      description: 'Extracts Subject Alternative Names from SSL certificates',
      icon: '🌐',
      priority: 'low'
    },
    'kubernetes-fake-certificate': {
      name: 'Default Kubernetes Certificates',
      description: 'Identifies default/fake certificates from Kubernetes ingress controllers',
      icon: '🔧',
      priority: 'medium'
    }
  };

  const loadSSLFindings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Target specific SSL/TLS template IDs for comprehensive analysis
      const sslTemplateIds = [
        'tls-version',           // Detects TLS/SSL protocol versions
        'deprecated-tls',        // Specifically detects deprecated TLS versions
        'wildcard-tls',          // Identifies wildcard certificates
        'ssl-issuer',            // Extracts certificate authority information
        'mismatched-ssl-certificate', // Finds hostname/certificate mismatches
        'weak-cipher-suites',    // Identifies vulnerable cipher suites
        'ssl-dns-names',         // Extracts Subject Alternative Names
        'self-signed-ssl',       // Detects self-signed certificates
        'kubernetes-fake-certificate' // Identifies default/fake Kubernetes certs
      ];

      // Try to search for SSL findings by template IDs
      // Since we don't know the exact search parameter format, let's try multiple approaches
      let findings = [];

      try {
        // Approach 1: Search for type = ssl first (based on API response format)
        const sslTypeParams = {
          type: 'ssl',
          program: selectedProgram || undefined,
          page: 1,
          page_size: 1000,
          sort_by: 'created_at',
          sort_dir: 'desc'
        };

        const sslResponse = await api.findings.nuclei.search(sslTypeParams);
        const sslFindings = sslResponse.items || [];

        // Filter by our specific template IDs
        const filteredSslFindings = sslFindings.filter(finding =>
          sslTemplateIds.includes(finding.template_id)
        );

        findings = [...findings, ...filteredSslFindings];

        // Approach 2: Also try searching by each template ID individually if we need more data
        if (findings.length < 100) { // Only do additional searches if we don't have many findings
          for (const templateId of sslTemplateIds.slice(0, 3)) { // Limit to first 3 to avoid too many requests
            try {
              const templateParams = {
                template_contains: templateId,
                program: selectedProgram || undefined,
                page: 1,
                page_size: 100,
                sort_by: 'created_at',
                sort_dir: 'desc'
              };

              const templateResponse = await api.findings.nuclei.search(templateParams);
              const templateFindings = templateResponse.items || [];

              // Add findings that aren't already in our list
              for (const finding of templateFindings) {
                if (!findings.some(f => f.id === finding.id) && sslTemplateIds.includes(finding.template_id)) {
                  findings.push(finding);
                }
              }
            } catch (err) {
            }
          }
        }

      } catch (err) {

        // Approach 3: Fallback - search without specific filters and filter client-side
        const fallbackParams = {
          program: selectedProgram || undefined,
          page: 1,
          page_size: 500,
          sort_by: 'created_at',
          sort_dir: 'desc'
        };

        const fallbackResponse = await api.findings.nuclei.search(fallbackParams);
        const allFindings = fallbackResponse.items || [];

        // Filter for SSL templates client-side
        findings = allFindings.filter(finding =>
          sslTemplateIds.includes(finding.template_id) ||
          (finding.tags && finding.tags.toLowerCase().includes('ssl')) ||
          (finding.tags && finding.tags.toLowerCase().includes('tls'))
        );
      }

      setSslFindings(findings);

      // Calculate comprehensive SSL/TLS security statistics with enhanced parsing
      const severityBreakdown = {};
      const templateBreakdown = {};
      const hostBreakdown = {};
      const tlsVersions = {};
      const deprecatedProtocols = {};
      const cipherSuites = {};
      const securityIssues = {};
      const certificateIssuers = {};
      const wildcardCerts = {};

      findings.forEach(finding => {
        // Severity breakdown
        const severity = finding.severity || 'unknown';
        severityBreakdown[severity] = (severityBreakdown[severity] || 0) + 1;

        // Template breakdown
        const templateId = finding.template_id || 'unknown';
        templateBreakdown[templateId] = (templateBreakdown[templateId] || 0) + 1;

        // Host breakdown
        const hostname = finding.matched_at || finding.hostname || 'unknown';
        const host = hostname.split(':')[0]; // Remove port if present
        hostBreakdown[host] = (hostBreakdown[host] || 0) + 1;

        // TLS Version Analysis with enhanced parsing
        if (finding.template_id === 'tls-version' && finding.extracted_results) {
          const tlsVersion = parseTLSVersion(finding.extracted_results);
          if (tlsVersion) {
            const versionKey = tlsVersion.replace(/[. ]/g, '').toLowerCase();
            tlsVersions[versionKey] = (tlsVersions[versionKey] || 0) + 1;

            // Track deprecated protocols based on actual TLS version found
            const isDeprecated =
              tlsVersion.includes('1.1') ||
              tlsVersion.includes('1.0') ||
              tlsVersion.includes('SSL 3.0') ||
              tlsVersion.includes('SSL 2.0') ||
              tlsVersion.toLowerCase().includes('sslv3') ||
              tlsVersion.toLowerCase().includes('sslv2') ||
              tlsVersion.toLowerCase().includes('tls 1.1') ||
              tlsVersion.toLowerCase().includes('tls 1.0');

            if (isDeprecated) {
              deprecatedProtocols[versionKey] = (deprecatedProtocols[versionKey] || 0) + 1;
              securityIssues['deprecated-tls'] = (securityIssues['deprecated-tls'] || 0) + 1;
            }
          }
        }

        // Deprecated TLS Template Analysis (specific template for deprecated protocols)
        if (finding.template_id === 'deprecated-tls' && finding.extracted_results) {
          const extractedArray = Array.isArray(finding.extracted_results) ? finding.extracted_results : [finding.extracted_results];
          extractedArray.forEach(result => {
            const tlsVersion = parseTLSVersion(result);
            if (tlsVersion) {
              const versionKey = tlsVersion.replace(/[. ]/g, '').toLowerCase();
              tlsVersions[versionKey] = (tlsVersions[versionKey] || 0) + 1;

              // All findings from deprecated-tls template are by definition deprecated
              deprecatedProtocols[versionKey] = (deprecatedProtocols[versionKey] || 0) + 1;
              securityIssues['deprecated-tls'] = (securityIssues['deprecated-tls'] || 0) + 1;

            }
          });
        }

        // Cipher Suite Analysis - check multiple template IDs that might contain cipher information
        const cipherTemplates = ['weak-cipher-suites', 'ssl-cipher-suites', 'cipher-suites', 'tls-cipher-suites', 'ssl-ciphers'];
        if (cipherTemplates.includes(finding.template_id) && finding.extracted_results) {
          const ciphers = parseCipherSuites(finding.extracted_results);

          if (ciphers.length > 0) {
            ciphers.forEach(cipher => {
              // Track individual cipher names instead of grouping by strength
              cipherSuites[cipher.name] = (cipherSuites[cipher.name] || 0) + 1;
              if (cipher.strength === 'weak') {
                securityIssues['weak-cipher'] = (securityIssues['weak-cipher'] || 0) + 1;
              }
            });
          } else {
            // If no specific ciphers identified, show the raw extracted results
            const rawResults = parseExtractedResults(finding.extracted_results);
            cipherSuites[rawResults] = (cipherSuites[rawResults] || 0) + 1;
          }
        }

        // Certificate Issuer Analysis
        if (finding.template_id === 'ssl-issuer' && finding.extracted_results) {
          const issuer = parseCertificateIssuer(finding.extracted_results);
          certificateIssuers[issuer] = (certificateIssuers[issuer] || 0) + 1;
        }

        // Wildcard Certificate Analysis
        if (finding.template_id === 'wildcard-tls' && finding.extracted_results) {
          const extractedData = parseExtractedResults(finding.extracted_results);
          wildcardCerts[extractedData] = (wildcardCerts[extractedData] || 0) + 1;
        }

        // Security Issue Classification
        if (finding.template_id === 'self-signed-ssl') {
          securityIssues['self-signed'] = (securityIssues['self-signed'] || 0) + 1;
        }
        if (finding.template_id === 'mismatched-ssl-certificate') {
          securityIssues['certificate-mismatch'] = (securityIssues['certificate-mismatch'] || 0) + 1;
        }
        if (finding.template_id === 'kubernetes-fake-certificate') {
          securityIssues['fake-certificate'] = (securityIssues['fake-certificate'] || 0) + 1;
        }
      });

      // Load certificate stats from the assets stats API
      let certificateStats = {
        total: 0,
        expired: 0,
        expiringSoon: 0, // within 30 days
        valid: 0,
        selfSigned: 0,
        wildcards: 0
      };

      try {
        // Use the stats API to get certificate statistics
        const statsResponse = selectedProgram 
          ? await api.commonStats.getProgramAssetStats(selectedProgram)
          : await api.commonStats.getAggregatedAssetStats();

        if (statsResponse.certificate_details) {
          const certStats = statsResponse.certificate_details;
          certificateStats = {
            total: certStats.total || 0,
            valid: certStats.valid || 0,
            expiringSoon: certStats.expiring_soon || 0,
            expired: certStats.expired || 0,
            selfSigned: certStats.self_signed || 0,
            wildcards: certStats.wildcards || 0
          };
        }

      } catch (err) {
      }

      setSummary({
        total: findings.length,
        severityBreakdown,
        templateBreakdown,
        hostBreakdown,
        tlsVersions,
        deprecatedProtocols,
        cipherSuites,
        securityIssues,
        certificateIssuers,
        wildcardCerts,
        certificateStats
      });

    } catch (err) {
      console.error('Error loading SSL findings:', err);
      setError('Failed to load SSL certificate findings. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [selectedProgram]);

  useEffect(() => {
    loadSSLFindings();
  }, [loadSSLFindings]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadSSLFindings();
    setRefreshing(false);
  };

  const truncateText = (text, maxLength = 40) => {
    if (!text) return 'N/A';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
  };

  const getSeverityBadge = (severity) => {
    const color = severityColors[severity] || 'secondary';
    return <Badge bg={color}>{severity}</Badge>;
  };


  // Calculate overall security score
  const calculateSecurityScore = () => {
    let score = 100;
    const totalFindings = summary.total || 1;

    // Penalize for deprecated protocols
    Object.entries(summary.deprecatedProtocols).forEach(([protocol, count]) => {
      const severity = protocol.includes('ssl') ? 30 : 20;
      score -= (count / totalFindings) * severity;
    });

    // Penalize for security issues
    Object.entries(summary.securityIssues).forEach(([issue, count]) => {
      const penalties = {
        'deprecated-tls': 25,
        'weak-cipher': 20,
        'certificate-mismatch': 15,
        'self-signed': 10,
        'fake-certificate': 15
      };
      const penalty = penalties[issue] || 10;
      score -= (count / totalFindings) * penalty;
    });

    return Math.max(0, Math.round(score));
  };

  // Get security score color
  const getSecurityScoreColor = (score) => {
    if (score >= 90) return 'success';
    if (score >= 70) return 'info';
    if (score >= 50) return 'warning';
    return 'danger';
  };

  // Get TLS version security assessment with proper key mapping
  const getTLSVersionSecurity = (versionKey) => {
    // Map parsed version keys back to our security config
    const keyMap = {
      'tls13': 'tls13',
      'tls12': 'tls12',
      'tls11': 'tls11',
      'tls10': 'tls10',
      'ssl30': 'ssl30',
      'ssl20': 'ssl20'
    };

    const mappedKey = keyMap[versionKey] || versionKey;
    const security = tlsVersionSecurity[mappedKey];
    if (!security) return { level: 'unknown', color: 'secondary', description: 'Unknown version' };
    return security;
  };

  // Format version display name
  const formatVersionName = (versionKey) => {
    const nameMap = {
      'tls13': 'TLS 1.3',
      'tls12': 'TLS 1.2',
      'tls11': 'TLS 1.1',
      'tls10': 'TLS 1.0',
      'ssl30': 'SSL 3.0',
      'ssl20': 'SSL 2.0'
    };
    return nameMap[versionKey] || versionKey.toUpperCase();
  };

  // Check if there are any critical security issues
  const hasCriticalIssues = () => {
    return Object.keys(summary.deprecatedProtocols).some(protocol =>
      protocol.includes('ssl') || protocol === 'tls10'
    ) || summary.securityIssues['weak-cipher'] > 0;
  };

  if (loading && sslFindings.length === 0) {
    return (
      <Container fluid className="p-4 text-center">
        <Spinner animation="border" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
        <p className="mt-3">Loading SSL certificate findings...</p>
      </Container>
    );
  }

  const programParam = selectedProgram ? `?program=${selectedProgram}` : '';

  return (
    <Container fluid className="p-4">
      {/* Header */}
      <div className="d-flex justify-content-between align-items-start mb-4">
        <div>
          <h1 className="mb-2">🔒 SSL/TLS Certificate Dashboard</h1>
          <p className="text-muted mb-1">Security analysis of SSL/TLS certificates discovered by Nuclei</p>
          {selectedProgram && (
            <Badge bg="info" className="fs-6 px-3 py-2">
              🎯 {selectedProgram}
            </Badge>
          )}
        </div>
        <Button
          variant="outline-primary"
          onClick={handleRefresh}
          disabled={refreshing}
          className="d-flex align-items-center gap-2"
        >
          {refreshing ? <Spinner size="sm" /> : '🔄'}
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      {/* Show helpful guidance when no SSL findings are available */}
      {!loading && sslFindings.length === 0 && (
        <Alert variant="info" className="mb-4">
          <Alert.Heading className="h5">🔍 No SSL/TLS Findings Available</Alert.Heading>
          <p className="mb-3">
            This dashboard analyzes SSL/TLS security findings from Nuclei scans. To get comprehensive SSL intelligence, run the following Nuclei templates:
          </p>

          <Row>
            <Col md={6}>
              <h6>🔒 Essential SSL Templates:</h6>
              <div className="font-monospace small bg-light p-2 rounded mb-2">
                nuclei -t ssl/tls-version.yaml -l hosts.txt
              </div>
              <div className="font-monospace small bg-light p-2 rounded mb-2">
                nuclei -t ssl/deprecated-tls.yaml -l hosts.txt
              </div>
              <div className="font-monospace small bg-light p-2 rounded mb-2">
                nuclei -t ssl/ssl-issuer.yaml -l hosts.txt
              </div>
              <div className="font-monospace small bg-light p-2 rounded mb-3">
                nuclei -t ssl/mismatched-ssl-certificate.yaml -l hosts.txt
              </div>
            </Col>
            <Col md={6}>
              <h6>⚡ Advanced Analysis:</h6>
              <div className="font-monospace small bg-light p-2 rounded mb-2">
                nuclei -t ssl/weak-cipher-suites.yaml -l hosts.txt
              </div>
              <div className="font-monospace small bg-light p-2 rounded mb-2">
                nuclei -t ssl/wildcard-tls.yaml -l hosts.txt
              </div>
              <div className="font-monospace small bg-light p-2 rounded mb-3">
                nuclei -t ssl/self-signed-ssl.yaml -l hosts.txt
              </div>
            </Col>
          </Row>

          <div className="border-top pt-3 mt-3">
            <p className="small mb-2">
              <strong>💡 Pro Tip:</strong> Run all SSL templates at once:
            </p>
            <div className="font-monospace small bg-dark text-light p-2 rounded">
              nuclei -t ssl/ -l hosts.txt -o ssl_findings.json -json
            </div>
          </div>
        </Alert>
      )}

      {/* Quick Navigation */}
      <Card className="border-primary mb-4">
        <Card.Header className="bg-primary">
          <h5 className="mb-0">⚡ Quick Actions</h5>
        </Card.Header>
        <Card.Body>
          <Row>
            <Col md={4}>
              <Button
                as={Link}
                to={`/findings/nuclei${programParam}&finding_type=ssl`}
                variant="outline-primary"
                className="w-100 mb-2"
              >
                🎯 View All SSL Findings
              </Button>
            </Col>
            <Col md={4}>
              <Button
                as={Link}
                to={`/assets/certificates${programParam}`}
                variant="outline-success"
                className="w-100 mb-2"
              >
                🔒 Certificate Assets
              </Button>
            </Col>
            <Col md={4}>
              <Button
                as={Link}
                to="/dashboard"
                variant="outline-secondary"
                className="w-100 mb-2"
              >
                📊 Main Dashboard
              </Button>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {/* Security Overview Cards */}
      <Row className="mb-4">
        <Col md={3}>
          <Card className={`border-${getSecurityScoreColor(calculateSecurityScore())} text-center h-100`}>
            <Card.Body>
              <h2 className={`text-${getSecurityScoreColor(calculateSecurityScore())} mb-1`}>
                {calculateSecurityScore()}%
              </h2>
              <p className="text-muted mb-0">Security Score</p>
              {hasCriticalIssues() && <Badge bg="danger" className="mt-1">Critical Issues</Badge>}
            </Card.Body>
          </Card>
        </Col>
        <Col md={3}>
          <Card className="border-primary text-center h-100">
            <Card.Body>
              <h2 className="text-primary mb-1">
                {Object.keys(summary.tlsVersions).length}
              </h2>
              <p className="text-muted mb-0">TLS Versions Found</p>
              {Object.keys(summary.deprecatedProtocols).length > 0 && (
                <Badge bg="warning" className="mt-1">
                  {Object.keys(summary.deprecatedProtocols).length} Deprecated
                </Badge>
              )}
            </Card.Body>
          </Card>
        </Col>
        <Col md={3}>
          <Card className="border-warning text-center h-100">
            <Card.Body>
              <h2 className="text-warning mb-1">
                {Object.values(summary.deprecatedProtocols).reduce((a, b) => a + b, 0)}
              </h2>
              <p className="text-muted mb-0">Deprecated Protocols</p>
              {summary.deprecatedProtocols.ssl20 && <Badge bg="danger" className="mt-1">SSL 2.0</Badge>}
              {summary.deprecatedProtocols.ssl30 && <Badge bg="danger" className="mt-1">SSL 3.0</Badge>}
            </Card.Body>
          </Card>
        </Col>
        <Col md={3}>
          <Card className="border-success text-center h-100">
            <Card.Body>
              <h2 className="text-success mb-1">
                {Object.keys(summary.hostBreakdown).length.toLocaleString()}
              </h2>
              <p className="text-muted mb-0">Hosts Analyzed</p>
              <small className="text-muted">{summary.total} total findings</small>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* TLS Version Analysis & Critical Issues */}
      <Row className="mb-4">
        <Col md={6}>
          <Card className="h-100 border-primary">
            <Card.Header className="bg-primary">
              <h5 className="mb-0">🔒 TLS Version Distribution</h5>
            </Card.Header>
            <Card.Body>
              {Object.keys(summary.tlsVersions).length > 0 ? (
                <div>
                  {Object.entries(summary.tlsVersions)
                    .sort(([a], [b]) => {
                      const versionOrder = { 'tls13': 4, 'tls12': 3, 'tls11': 2, 'tls10': 1, 'ssl30': 0, 'ssl20': -1 };
                      return (versionOrder[b] || 0) - (versionOrder[a] || 0);
                    })
                    .map(([versionKey, count]) => {
                      const security = getTLSVersionSecurity(versionKey);
                      const displayName = formatVersionName(versionKey);
                      return (
                        <div key={versionKey} className="d-flex justify-content-between align-items-center mb-3 p-2 border rounded">
                          <div>
                            <Badge bg={security.color} className="me-2 font-monospace">
                              {displayName}
                            </Badge>
                            <strong>{count}</strong> host{count !== 1 ? 's' : ''}
                          </div>
                          <div className="text-end small">
                            <div className={`text-${security.color} fw-bold text-capitalize`}>{security.level}</div>
                            <div className="text-muted" style={{fontSize: '0.75rem'}}>{security.description}</div>
                          </div>
                        </div>
                      );
                    })}
                </div>
              ) : (
                <div className="text-center text-muted">
                  <div className="mb-3">
                    <i className="bi bi-info-circle" style={{fontSize: '2rem'}}></i>
                  </div>
                  <p className="mb-2">
                    <strong>No TLS Version Data Available</strong>
                  </p>
                  <p className="small">
                    To get TLS version analysis, run Nuclei scans with the <code>tls-version</code> template:
                  </p>
                  <div className="bg-light p-2 rounded font-monospace small text-start">
                    nuclei -t ssl/tls-version.yaml -l hosts.txt
                  </div>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col md={6}>
          <Card className="h-100 border-danger">
            <Card.Header className="bg-danger">
              <h5 className="mb-0">⚠️ Critical Security Issues</h5>
            </Card.Header>
            <Card.Body>
              {Object.keys(summary.securityIssues).length > 0 || Object.keys(summary.deprecatedProtocols).length > 0 ? (
                <div>
                  {/* Deprecated Protocols */}
                  {Object.keys(summary.deprecatedProtocols).length > 0 && (
                    <div className="mb-3 p-3 border border-danger rounded">
                      <h6 className="text-danger mb-2">🚨 Deprecated Protocols Detected</h6>
                      {Object.entries(summary.deprecatedProtocols).map(([protocol, count]) => (
                        <div key={protocol} className="d-flex justify-content-between mb-1">
                          <span>{protocol.toUpperCase().replace('TLS', 'TLS ').replace('SSL', 'SSL ')}</span>
                          <Badge bg="danger">{count} host{count !== 1 ? 's' : ''}</Badge>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Security Issues */}
                  {Object.entries(summary.securityIssues)
                    .sort(([,a], [,b]) => b - a)
                    .map(([issue, count]) => {
                      const issueInfo = securityIssueTypes[issue] || { name: issue, severity: 'info', icon: '🔍' };
                      return (
                        <div key={issue} className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                          <div>
                            <span className="me-2">{issueInfo.icon}</span>
                            <strong>{issueInfo.name}</strong>
                          </div>
                          <div className="text-end">
                            <Badge bg={severityColors[issueInfo.severity]} className="me-2">
                              {issueInfo.severity}
                            </Badge>
                            <Badge bg="secondary">{count}</Badge>
                          </div>
                        </div>
                      );
                    })}
                </div>
              ) : (
                <div className="text-center text-success">
                  <h4>✅</h4>
                  <p className="mb-0">No critical security issues detected</p>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      Cipher Analysis & Security Recommendations
      <Row className="mb-4">
        <Col md={6}>
          <Card className="h-100 border-info">
            <Card.Header className="bg-info">
              <h5 className="mb-0">🔐 Cipher Suite Analysis</h5>
            </Card.Header>
            <Card.Body>
              {Object.keys(summary.cipherSuites).length > 0 ? (
                <div>
                  <div className="mb-3">
                    <small className="text-muted">
                      Cipher suites discovered from SSL/TLS scans (sorted by count)
                    </small>
                  </div>

                  {Object.entries(summary.cipherSuites)
                    .sort(([,a], [,b]) => b - a) // Sort by count descending
                    .map(([cipherName, count]) => {
                      const strength = getCipherStrength(cipherName);
                      const colors = { 'strong': 'success', 'medium': 'info', 'weak': 'danger', 'unknown': 'secondary' };

                      return (
                        <div key={cipherName} className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                          <div className="d-flex align-items-center">
                            <Badge bg={colors[strength]} className="me-2">
                              {strength === 'strong' ? '🔒' : strength === 'medium' ? '⚠️' : strength === 'weak' ? '❌' : '❓'}
                            </Badge>
                            <span className="font-monospace small fw-medium text-truncate" style={{maxWidth: '200px'}} title={cipherName}>
                              {cipherName}
                            </span>
                          </div>
                          <div className="text-end">
                            <Badge bg="primary" className="me-1">
                              {count}
                            </Badge>
                            <small className="text-muted">
                              {count === 1 ? 'host' : 'hosts'}
                            </small>
                          </div>
                        </div>
                      );
                    })}

                  {/* Summary stats */}
                  <div className="mt-3 pt-3 border-top">
                    <div className="row text-center">
                      <div className="col-4">
                        <small className="text-muted d-block">Total Ciphers</small>
                        <strong className="text-primary">{Object.keys(summary.cipherSuites).length}</strong>
                      </div>
                      <div className="col-4">
                        <small className="text-muted d-block">Total Hosts</small>
                        <strong className="text-info">{Object.values(summary.cipherSuites).reduce((a, b) => a + b, 0)}</strong>
                      </div>
                      <div className="col-4">
                        <small className="text-muted d-block">Weak Ciphers</small>
                        <strong className="text-danger">
                          {Object.entries(summary.cipherSuites).filter(([name]) => getCipherStrength(name) === 'weak').length}
                        </strong>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center text-muted">
                  <div className="mb-3">
                    <i className="bi bi-key" style={{fontSize: '2rem'}}></i>
                  </div>
                  <p className="mb-2">
                    <strong>No Cipher Suite Data</strong>
                  </p>
                  <p className="small">
                    To analyze cipher strengths, run:
                  </p>
                  <div className="bg-light p-2 rounded font-monospace small text-start">
                    nuclei -t ssl/weak-cipher-suites.yaml -l hosts.txt
                  </div>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col md={6}>
          <Card className="h-100 border-success">
            <Card.Header className="bg-success">
              <h5 className="mb-0">📜 Certificate Assets</h5>
            </Card.Header>
            <Card.Body>
              {summary.certificateStats && summary.certificateStats.total > 0 ? (
                <div>
                  <div className="d-flex justify-content-between align-items-center mb-3">
                    <span className="text-muted">Total Certificates</span>
                    <Badge bg="primary" className="fs-6">
                      {summary.certificateStats.total}
                    </Badge>
                  </div>

                  {/* Certificate Status Stats */}
                  <div className="mb-3">
                    <div className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                      <div>
                        <span className="me-2">✅</span>
                        <strong>Valid Certificates</strong>
                      </div>
                      <Badge bg="success">{summary.certificateStats.valid}</Badge>
                    </div>

                    {summary.certificateStats.expiringSoon > 0 && (
                      <div className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                        <div>
                          <span className="me-2">⚠️</span>
                          <strong>Expiring Soon</strong>
                          <small className="text-muted ms-2">(≤30 days)</small>
                        </div>
                        <Badge bg="warning">{summary.certificateStats.expiringSoon}</Badge>
                      </div>
                    )}

                    {summary.certificateStats.expired > 0 && (
                      <div className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                        <div>
                          <span className="me-2">❌</span>
                          <strong>Expired Certificates</strong>
                        </div>
                        <Badge bg="danger">{summary.certificateStats.expired}</Badge>
                      </div>
                    )}

                    {summary.certificateStats.selfSigned > 0 && (
                      <div className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                        <div>
                          <span className="me-2">📝</span>
                          <strong>Self-Signed</strong>
                        </div>
                        <Badge bg="secondary">{summary.certificateStats.selfSigned}</Badge>
                      </div>
                    )}

                    {summary.certificateStats.wildcards > 0 && (
                      <div className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                        <div>
                          <span className="me-2">🌟</span>
                          <strong>Wildcard Certificates</strong>
                        </div>
                        <Badge bg="info">{summary.certificateStats.wildcards}</Badge>
                      </div>
                    )}
                  </div>


                  <div className="text-center mt-3">
                    <Link
                      to={`/assets/certificates${selectedProgram ? `?program=${selectedProgram}` : ''}`}
                      className="btn btn-outline-success btn-sm"
                    >
                      View All {summary.certificateStats.total} Certificates →
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="text-center text-muted">
                  <div className="mb-3">
                    <i className="bi bi-file-earmark-lock" style={{fontSize: '2rem'}}></i>
                  </div>
                  <p className="mb-2">
                    <strong>No Certificate Assets Found</strong>
                  </p>
                  <p className="small">
                    Certificate assets are discovered through SSL scans and reconnaissance
                  </p>
                  <Link
                    to={`/assets/certificates${selectedProgram ? `?program=${selectedProgram}` : ''}`}
                    className="btn btn-outline-secondary btn-sm"
                  >
                    View Certificate Assets →
                  </Link>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Certificate Intelligence & Wildcard Analysis */}
      <Row className="mb-4">
        <Col md={6}>
          <Card className="h-100 border-success">
            <Card.Header className="bg-success">
              <h5 className="mb-0">🏛️ Certificate Authorities</h5>
            </Card.Header>
            <Card.Body>
              {Object.keys(summary.certificateIssuers).length > 0 ? (
                <div>
                  {Object.entries(summary.certificateIssuers)
                    .sort(([,a], [,b]) => b - a)
                    .slice(0, 8)
                    .map(([issuer, count]) => (
                      <div key={issuer} className="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                        <div className="flex-grow-1">
                          <div className="fw-medium text-truncate" style={{maxWidth: '200px'}} title={issuer}>
                            {issuer === 'Acme Co' ? '🔧 Acme Co (Test CA)' :
                             issuer.includes('Let') ? '🟢 ' + issuer :
                             issuer.includes('Kubernetes') ? '⚙️ ' + issuer :
                             '🏛️ ' + issuer}
                          </div>
                          {issuer === 'Acme Co' && (
                            <small className="text-warning">Default/Test Certificate Authority</small>
                          )}
                        </div>
                        <Badge bg="primary">{count}</Badge>
                      </div>
                    ))}

                  {Object.keys(summary.certificateIssuers).length > 8 && (
                    <div className="text-center mt-2">
                      <small className="text-muted">
                        +{Object.keys(summary.certificateIssuers).length - 8} more certificate authorities
                      </small>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center text-muted">
                  <div className="mb-3">
                    <i className="bi bi-building" style={{fontSize: '2rem'}}></i>
                  </div>
                  <p className="mb-2">
                    <strong>No Certificate Authority Data</strong>
                  </p>
                  <p className="small">
                    To analyze certificate issuers, run:
                  </p>
                  <div className="bg-light p-2 rounded font-monospace small text-start">
                    nuclei -t ssl/ssl-issuer.yaml -l hosts.txt
                  </div>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col md={6}>
          <Card className="h-100 border-secondary">
            <Card.Header className="bg-secondary">
              <h5 className="mb-0">🌟 Wildcard Certificates</h5>
            </Card.Header>
            <Card.Body>
              {Object.keys(summary.wildcardCerts).length > 0 ? (
                <div>
                  {Object.entries(summary.wildcardCerts)
                    .sort(([,a], [,b]) => b - a)
                    .slice(0, 6)
                    .map(([pattern, count]) => (
                      <div key={pattern} className="d-flex justify-content-between align-items-start mb-2 p-2 border rounded">
                        <div className="flex-grow-1">
                          {(() => {
                            const parts = pattern.split(',').map(p => p.trim());
                            return (
                              <div>
                                <div className="fw-medium font-monospace" title={pattern}>
                                  {parts[0].startsWith('*.') ? parts[0] : `*.${parts[0]}`}
                                </div>
                                {parts.length > 1 && (
                                  <div className="mt-1">
                                    {parts.slice(1).map((part, idx) => (
                                      <div key={idx} className="small text-muted font-monospace">
                                        {part.startsWith('*.') ? part : `*.${part}`}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })()}
                          {/* <small className="text-muted">
                            {pattern.includes(',') ? 'CN + SAN patterns' : 'Wildcard pattern'}
                          </small> */}
                        </div>
                        <Badge bg="info">{count}</Badge>
                      </div>
                    ))}

                  {/* <Alert variant="info" className="mt-3 mb-0">
                    <small>
                      <strong>ℹ️ Wildcard Certificates:</strong> Can secure multiple subdomains but require careful management and monitoring.
                    </small>
                  </Alert> */}
                </div>
              ) : (
                <div className="text-center text-muted">
                  <div className="mb-3">
                    <i className="bi bi-asterisk" style={{fontSize: '2rem'}}></i>
                  </div>
                  <p className="mb-2">
                    <strong>No Wildcard Certificate Data</strong>
                  </p>
                  <p className="small">
                    To find wildcard certificates, run:
                  </p>
                  <div className="bg-light p-2 rounded font-monospace small text-start">
                    nuclei -t ssl/wildcard-tls.yaml -l hosts.txt
                  </div>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* High Priority Security Checks */}
      <Card className="mb-4 border-success">
        <Card.Header className="bg-success">
          <h5 className="mb-0">🔍 Security Assessment Results</h5>
        </Card.Header>
        <Card.Body>
          <Row>
            {Object.entries(summary.templateBreakdown)
              .sort(([templateA], [templateB]) => {
                const priorityA = templateDescriptions[templateA]?.priority || 'low';
                const priorityB = templateDescriptions[templateB]?.priority || 'low';
                const priorityOrder = { 'critical': 4, 'high': 3, 'medium': 2, 'low': 1 };
                return (priorityOrder[priorityB] || 1) - (priorityOrder[priorityA] || 1);
              })
              .map(([templateId, count]) => {
              const template = templateDescriptions[templateId] || {
                name: templateId,
                description: 'SSL/TLS security check',
                icon: '🔒',
                priority: 'low'
              };

              const priorityColors = {
                'critical': 'danger',
                'high': 'warning',
                'medium': 'info',
                'low': 'secondary'
              };

              return (
                <Col md={4} key={templateId} className="mb-3">
                  <Card className={`border-${priorityColors[template.priority]} h-100`}>
                    <Card.Body className="text-center">
                      <div className="d-flex justify-content-between align-items-start mb-2">
                        <div className="fs-3">{template.icon}</div>
                        <Badge bg={priorityColors[template.priority]} className="text-uppercase">
                          {template.priority}
                        </Badge>
                      </div>
                      <h6 className="card-title">{template.name}</h6>
                      <p className="card-text small text-muted">{template.description}</p>
                      <Badge bg="primary" className="fs-6 px-3 py-2">
                        {count} finding{count !== 1 ? 's' : ''}
                      </Badge>
                    </Card.Body>
                  </Card>
                </Col>
              );
            })}
          </Row>
        </Card.Body>
      </Card>

      {/* Critical SSL/TLS Security Findings */}
      <Card className="mb-4 border-danger">
        <Card.Header className="bg-danger d-flex justify-content-between align-items-center">
          <h5 className="mb-0">🚨 SSL/TLS Security Analysis</h5>
          <Link
            to={`/findings/nuclei${programParam}&finding_type=ssl`}
            className="btn btn-sm btn-outline-light"
          >
            View All Findings →
          </Link>
        </Card.Header>
        <Card.Body className="p-0">
          {sslFindings.length > 0 ? (
            <div className="table-responsive">
              <Table className="mb-0" hover>
                <thead className="table-light">
                  <tr>
                    <th>Security Issue</th>
                    <th>Severity</th>
                    <th>Host:Port</th>
                    <th>TLS/SSL Details</th>
                    <th>Risk Level</th>
                    <th>Discovery</th>
                  </tr>
                </thead>
                <tbody>
                  {sslFindings
                    .sort((a, b) => {
                      // Prioritize critical security issues
                      const severityOrder = { 'critical': 5, 'high': 4, 'medium': 3, 'low': 2, 'info': 1 };
                      const priorityOrder = {
                        'self-signed-ssl': 3,
                        'mismatched-ssl-certificate': 4,
                        'kubernetes-fake-certificate': 2,
                        'tls-version': 5, // TLS version is most important
                        'deprecated-tls': 6,
                        'ssl-cipher-suites': 5
                      };

                      const sevA = severityOrder[a.severity] || 0;
                      const sevB = severityOrder[b.severity] || 0;
                      const priA = priorityOrder[a.template_id] || 1;
                      const priB = priorityOrder[b.template_id] || 1;

                      return (sevB + priB) - (sevA + priA);
                    })
                    .slice(0, 15)
                    .map((finding) => {
                      const extractedData = parseExtractedResults(finding.extracted_results);
                      let riskLevel = 'Low';
                      let riskColor = 'success';

                      // Determine risk level based on findings
                      if (finding.template_id === 'tls-version') {
                        const versions = extractedData.toLowerCase();
                        if (versions.includes('ssl') || versions.includes('tls10')) {
                          riskLevel = 'Critical';
                          riskColor = 'danger';
                        } else if (versions.includes('tls11')) {
                          riskLevel = 'High';
                          riskColor = 'warning';
                        } else if (versions.includes('tls12')) {
                          riskLevel = 'Medium';
                          riskColor = 'info';
                        } else if (versions.includes('tls13')) {
                          riskLevel = 'Low';
                          riskColor = 'success';
                        }
                      } else if (finding.severity === 'critical' || finding.severity === 'high') {
                        riskLevel = 'High';
                        riskColor = 'danger';
                      } else if (finding.severity === 'medium') {
                        riskLevel = 'Medium';
                        riskColor = 'warning';
                      }

                      return (
                        <tr key={finding.id}>
                          <td>
                            <Link
                              to={`/findings/nuclei/details?id=${finding.id}`}
                              className="text-decoration-none"
                            >
                              <div className="fw-medium text-primary">
                                {finding.template_id === 'tls-version' ? '🔒 TLS Version' :
                                 finding.template_id === 'self-signed-ssl' ? '📝 Self-Signed Cert' :
                                 finding.template_id === 'mismatched-ssl-certificate' ? '❌ Cert Mismatch' :
                                 finding.template_id === 'kubernetes-fake-certificate' ? '🔧 Fake Certificate' :
                                 truncateText(finding.name, 25)}
                              </div>
                            </Link>
                            <small className="text-muted">
                              {templateDescriptions[finding.template_id]?.name || finding.template_id}
                            </small>
                          </td>
                          <td>
                            {getSeverityBadge(finding.severity)}
                          </td>
                          <td className="small font-monospace">
                            {truncateText(finding.matched_at || finding.hostname, 30)}
                          </td>
                          <td className="small">
                            {finding.template_id === 'tls-version' ? (
                              (() => {
                                const tlsVersion = parseTLSVersion(finding.extracted_results);
                                const versionKey = tlsVersion ? tlsVersion.replace(/[. ]/g, '').toLowerCase() : '';
                                const security = getTLSVersionSecurity(versionKey);
                                return (
                                  <Badge bg={security.color} className="font-monospace">
                                    {tlsVersion || extractedData}
                                  </Badge>
                                );
                              })()
                            ) : finding.template_id === 'weak-cipher-suites' ? (
                              (() => {
                                const ciphers = parseCipherSuites(finding.extracted_results);
                                return (
                                  <div>
                                    {ciphers.slice(0, 2).map((cipher, idx) => (
                                      <Badge
                                        key={idx}
                                        bg={cipher.strength === 'weak' ? 'danger' : cipher.strength === 'strong' ? 'success' : 'info'}
                                        className="me-1 small"
                                      >
                                        {cipher.name}
                                      </Badge>
                                    ))}
                                    {ciphers.length > 2 && <small className="text-muted">+{ciphers.length - 2} more</small>}
                                  </div>
                                );
                              })()
                            ) : finding.template_id === 'ssl-issuer' ? (
                              <span className="text-primary font-monospace small">
                                {parseCertificateIssuer(finding.extracted_results)}
                              </span>
                            ) : finding.template_id === 'wildcard-tls' ? (
                              <span className="text-info font-monospace">
                                *.{truncateText(extractedData, 20)}
                              </span>
                            ) : finding.template_id === 'mismatched-ssl-certificate' ? (
                              <span className="text-danger small">
                                <i className="bi bi-exclamation-triangle me-1"></i>
                                {truncateText(extractedData, 20)}
                              </span>
                            ) : (
                              <span className="text-muted">
                                {truncateText(extractedData, 25)}
                              </span>
                            )}
                          </td>
                          <td>
                            <Badge bg={riskColor}>{riskLevel}</Badge>
                          </td>
                          <td className="small text-muted">
                            <div>{formatDate(finding.created_at)}</div>
                            <Badge bg="outline-secondary" className="small">
                              {finding.program_name}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </Table>
            </div>
          ) : (
            <div className="text-center p-4">
              <div className="text-success">
                <h4>✅</h4>
                <p className="mb-0">
                  {loading ? 'Loading SSL security analysis...' : 'No SSL/TLS security issues found'}
                </p>
                {!loading && (
                  <small className="text-muted">
                    Your SSL/TLS configuration appears to be secure
                  </small>
                )}
              </div>
            </div>
          )}
        </Card.Body>
      </Card>

    </Container>
  );
};

export default SSLCertificateDashboard;