// Task types configuration.
// Input/output type lists are NOT here anymore - they come from the backend
// manifest (/admin/public/recon-tasks/effective-parameters) via
// src/stores/taskManifestStore.js. That store is the single source of truth,
// derived from each runner Task's input_type / output_types attribute and the
// matching recon_task_builtin_defaults.yaml entry on the API.
export const TASK_TYPES = {
  resolve_domain: {
    name: 'Domain Resolution',
    description: 'Resolve domain names to IP addresses using dnsx',
    category: 'DNS',
    icon: '🔍',
    params: {
      timeout: { type: 'number', default: 120, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  whois_domain_check: {
    name: 'WHOIS Domain Check',
    description: 'WHOIS lookup on apex domains (subdomains are normalized to apex); results stored on apex domain assets',
    category: 'DNS',
    icon: '📇',
    params: {
      timeout: { type: 'number', default: 600, description: 'Optional timeout override in seconds (uses system default if not specified)' },
      chunk_size: { type: 'number', default: 1, description: 'Apex domains per worker job (1 recommended for WHOIS rate limits)' }
    }
  },
  resolve_ip: {
    name: 'IP Resolution',
    description: 'Resolve IP addresses to domain names using dnsx',
    category: 'DNS',
    icon: '🔍',
    params: {
      timeout: { type: 'number', default: 120, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  resolve_ip_cidr: {
    name: 'CIDR IP Resolution',
    description: 'Progressively resolve IP addresses from CIDR blocks with stateful processing',
    category: 'DNS',
    icon: '🌐',
    params: {
      ip_limit: { type: 'number', default: 500, description: 'Maximum IPs to process from CIDR blocks' },
      max_cidr_size: { type: 'number', default: 65536, description: 'Maximum CIDR size to process (safety limit)' },
      ips_per_worker: { type: 'number', default: 50, description: 'IPs per spawned resolve_ip / port_scan worker job' },
      timeout: { type: 'number', default: 300, description: 'Per resolve_ip worker job timeout in seconds (Kubernetes deadline for each chunk; leave empty for runner default)' },
      enable_port_scan: { type: 'boolean', default: true, description: 'Spawn port_scan jobs for eligible IPs alongside reverse-DNS (resolve_ip)' },
      port_scan_timeout: { type: 'number', default: 300, description: 'Per port_scan worker job timeout in seconds (passed to child port_scan tasks)' },
      force_ip: { type: 'boolean', default: false, description: 'Force IP resolution (skip last-run / service checks where applicable)' }
    }
  },
  subdomain_finder: {
    name: 'Subdomain Discovery',
    description: 'Find subdomains using subfinder',
    category: 'Discovery',
    icon: '🔎',
    params: {
      timeout: { type: 'number', default: 300, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  subdomain_permutations: {
    name: 'Subdomain Permutations',
    description: 'Generate and test subdomain permutations using gotator with intelligent wildcard filtering',
    category: 'Discovery',
    icon: '🔀',
    params: {
      permutation_list: { type: 'string', default: 'files/permutations.txt', description: 'Permutation list to use (wordlist ID, URL, or file path)' },
      permutation_limit: { type: 'number', default: null, description: 'Maximum permutations to test (optional, no limit if not set)' },
      chunk_size: { type: 'number', default: 100, description: 'Number of permutations per resolve_domain job' },
      batch_size: { type: 'number', default: 10, description: 'Number of resolve_domain jobs to spawn in parallel' },
      timeout: { type: 'number', default: 300, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  dns_bruteforce: {
    name: 'DNS Bruteforce',
    description: 'Bruteforce subdomains using PureDNS with wordlist (skips wildcard domains)',
    category: 'Discovery',
    icon: '🔨',
    params: {
      wordlist: { type: 'string', default: '/workspace/files/subdomains.txt', description: 'Wordlist for bruteforcing (wordlist ID, URL, or file path)' },
      chunk_size: { type: 'number', default: 10, description: 'Number of domains per worker job' },
      batch_size: { type: 'number', default: 5, description: 'Number of worker jobs to spawn in parallel' },
      timeout: { type: 'number', default: 600, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  port_scan: {
    name: 'Port Scanning',
    description: 'Scan ports on target hosts using nmap',
    category: 'Scanning',
    icon: '🚪',
    params: {
      timeout: { type: 'number', default: 900, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  nuclei_scan: {
    name: 'Nuclei Vulnerability Scan',
    description: 'Run nuclei vulnerability scanner on target',
    category: 'Vulnerability',
    icon: '🔬',
    params: {
      template: {
        type: 'nuclei_template_object',
        default: { official: [], custom: [] },
        description: 'Nuclei templates to use (official and custom arrays)'
      },
      rate_limit: {
        type: 'number',
        description: 'Maximum requests per second (-rate-limit). Leave empty for nuclei default (150).',
        placeholder: '150'
      },
      automatic_scan: {
        type: 'boolean',
        default: false,
        description: 'Automatic web scan (-automatic-scan) using Wappalyzer technology-to-tags mapping.'
      },
      tags: {
        type: 'string',
        default: '',
        description: 'Run templates matching these tags (-tags), comma-separated.'
      },
      severity: {
        type: 'checkbox-group',
        default: [],
        description: 'Run templates matching these severities (-severity). Leave all unchecked to not filter by severity.',
        options: [
          { value: 'info', label: 'Info' },
          { value: 'low', label: 'Low' },
          { value: 'medium', label: 'Medium' },
          { value: 'high', label: 'High' },
          { value: 'critical', label: 'Critical' },
          { value: 'unknown', label: 'Unknown' }
        ]
      },
      interactsh_server: {
        type: 'string',
        default: '',
        description: 'Interactsh server URL for self-hosted instance (-interactsh-server). Leave empty for nuclei defaults.'
      },
      interactsh_token: {
        type: 'string',
        default: '',
        description: 'Interactsh authentication token (-interactsh-token) for self-hosted servers.'
      },
      http_timeout: {
        type: 'number',
        description: 'Per-request timeout in seconds (-timeout). Leave empty for nuclei default (10).',
        placeholder: '10'
      },
      retries: {
        type: 'number',
        description: 'Retries for failed requests (-retries). Leave empty for nuclei default (1).',
        placeholder: '1'
      },
      headless: {
        type: 'boolean',
        default: false,
        description: 'Enable templates that require headless browser support (-headless).'
      },
      cmd_args: {
        type: 'array',
        default: [],
        description: 'Additional nuclei arguments (one per line); appended after the options above.'
      }
    }
  },
  wpscan: {
    name: 'WPScan Vulnerability Scan',
    description: 'Scan WordPress sites for vulnerabilities in WordPress core, plugins, and themes',
    category: 'Vulnerability',
    icon: '🔒',
    params: {
      api_token: { type: 'string', default: '', description: 'WPScan API token (optional, improves vulnerability detection)' },
      enumerate: {
        type: 'checkbox-group',
        default: [],
        description: 'WPScan --enumerate options. Leave all unchecked so WPScan uses its built-in default enumeration.',
        options: [
          { value: 'vp', label: 'Vulnerable plugins (vp)', group: 'plugins' },
          { value: 'ap', label: 'All plugins (ap)', group: 'plugins' },
          { value: 'p', label: 'Popular plugins (p)', group: 'plugins' },
          { value: 'vt', label: 'Vulnerable themes (vt)', group: 'themes' },
          { value: 'at', label: 'All themes (at)', group: 'themes' },
          { value: 't', label: 'Popular themes (t)', group: 'themes' },
          { value: 'tt', label: 'Timthumbs (tt)' },
          { value: 'cb', label: 'Config backups (cb)' },
          { value: 'dbe', label: 'DB exports (dbe)' },
          { value: 'u', label: 'User IDs (u)' },
          { value: 'm', label: 'Media IDs (m)' },
        ],
        exclusiveGroups: ['plugins', 'themes'],
      },
    }
  },
  test_http: {
    name: 'HTTP Testing',
    description: 'Test HTTP endpoints using httpx',
    category: 'Discovery',
    icon: '🌐',
    params: {
      timeout: { type: 'number', default: 900, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  typosquat_detection: {
    name: 'Typosquat Detection',
    description: 'Detect typosquatting domains using dnstwist and risk analysis. Supports both variation generation and direct input domain analysis modes.',
    category: 'Security',
    icon: '🎯',
    params: {
      analyze_input_as_variations: { type: 'boolean', default: false, description: 'Analyze input domains directly as typosquat variations (no variation generation)' },
      source: { type: 'string', default: '', description: 'Source of the typosquat detection (e.g. "ct_monitoring", "domain_analysis", "variation_detection")' },
      max_variations: { type: 'number', default: 100, description: 'Maximum variations per domain (only used when analyze_input_as_variations is false)' },
      max_workers: { type: 'number', default: 5, description: 'Maximum parallel workers' },
      domains_per_worker: { type: 'number', default: 20, description: 'Domains per worker batch' },
      fuzzers: { type: 'array', default: [], description: 'Specific dnstwist fuzzers to use (one per line, e.g., addition, bitsquatting, dictionary)' },
      duplicate_tlds: {
        type: 'array',
        default: [],
        description:
          'Extra TLDs to emit for each generated variation (one per line, e.g. org, live). ' +
          'Keeps dnstwist TLDs and adds label.tld copies. Only used when analyze_input_as_variations is false. ' +
          'Total domains scale roughly as max_variations × (1 + count), minus overlaps.',
      },
      active_checks: { type: 'boolean', default: true, description: 'Enable SSL/HTTP checks' },
      geoip_checks: { type: 'boolean', default: true, description: 'Enable GeoIP lookups' },
      exclude_tested: { type: 'boolean', default: true, description: 'Exclude already tested domains' },
      include_subdomains: { type: 'boolean', default: false, description: 'Include subdomain discovery' },
      recalculate_risk: { type: 'boolean', default: false, description: 'Recalculate risk scores' },
      enable_fuzzing: { type: 'boolean', default: false, description: 'Enable post-detection URL fuzzing (wfuzz) when workflows support it' },
      fuzzer_wordlist: { type: 'string', default: '/workspace/files/webcontent_test.txt', description: 'Wordlist path/ID for optional fuzzing stage' }
    }
  },
  detect_broken_links: {
    name: 'Broken Link Detection',
    description: 'Detect broken social media links (Facebook, Instagram, Twitter/X, LinkedIn)',
    category: 'Security',
    icon: '🔗',
    params: {}
  },
  screenshot_website: {
    name: 'Website Screenshot',
    description: 'Take screenshots of websites',
    category: 'Discovery',
    icon: '📸',
    params: {
      timeout: { type: 'number', default: 60, description: 'Worker job timeout in seconds (Kubernetes active deadline for the whole screenshot batch; not passed per-URL to gowitness)' }
    }
  },
  crawl_website: {
    name: 'Website Crawling',
    description: 'Crawl websites to discover URLs',
    category: 'Discovery',
    icon: '🕷️',
    params: {
      timeout: { type: 'number', default: 1800, description: 'Optional timeout override in seconds (Katana discover jobs and httpx phase; uses system default if not specified)' },
      depth: { type: 'number', default: 5, description: 'Crawling depth for katana' },
      httpx_urls_per_job: { type: 'number', default: 100, description: 'Max discovered URLs per httpx worker job (fan-out across nodes)' },
      katana_timeout: { type: 'number', default: 900, description: 'Per-job timeout in seconds for Katana discover phase (falls back to timeout when omitted)' }
    }
  },
  fuzz_website: {
    name: 'Website Fuzzing',
    description: 'Fuzz websites to discover hidden paths',
    category: 'Discovery',
    icon: '🕷️',
    params: {
      wordlist: { type: 'string', default: '/workspace/files/webcontent_test.txt', description: 'Wordlist to use for fuzzing' }
    }
  },
  shell_command: {
    name: 'Shell Command',
    description: 'Execute custom shell commands',
    category: 'Utility',
    icon: '🔧',
    params: {
      command: { type: 'array', default: [], description: 'Command to execute (one per line, e.g., echo "Hello World", ls -la)' },
      timeout: { type: 'number', default: 300, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  }
};

// Categories for organizing tasks
export const TASK_CATEGORIES = {
  'DNS': { color: '#4CAF50', icon: '🔍' },
  'Discovery': { color: '#2196F3', icon: '🔎' },
  'Scanning': { color: '#FF9800', icon: '🚪' },
  'Vulnerability': { color: '#F44336', icon: '🔬' },
  'Security': { color: '#9C27B0', icon: '🎯' },
  'Utility': { color: '#607D8B', icon: '🔧' }
};

// Color mapping for different data types
export const DATA_TYPE_COLORS = {
  'domains': '#4CAF50',
  'apex_domains': '#00897B',
  'protected_domains': '#9C27B0',
  'ips': '#2196F3',
  'urls': '#FF9800',
  'cidrs': '#9C27B0',
  'services': '#F44336',
  'findings': '#E91E63',
  'typosquat_url': '#DC3545',
  'external_link': '#FF6B35',
  'screenshots': '#795548',
  'certificates': '#607D8B',
  'strings': '#FF5722',
  'default': 'var(--bs-text-muted)'
};

// Function to get color for a data type
export const getDataTypeColor = (dataType) => {
  return DATA_TYPE_COLORS[dataType] || DATA_TYPE_COLORS.default;
};
