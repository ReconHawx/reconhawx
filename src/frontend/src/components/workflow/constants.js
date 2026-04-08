// Task types configuration
export const TASK_TYPES = {
  resolve_domain: {
    name: 'Domain Resolution',
    description: 'Resolve domain names to IP addresses using dnsx',
    category: 'DNS',
    icon: '🔍',
    inputs: ['domains'],
    outputs: ['domains', 'ips'],
    params: {
      timeout: { type: 'number', default: 120, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  whois_domain_check: {
    name: 'WHOIS Domain Check',
    description: 'WHOIS lookup on apex domains (subdomains are normalized to apex); results stored on apex domain assets',
    category: 'DNS',
    icon: '📇',
    inputs: ['domains'],
    outputs: ['apex_domains'],
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
    inputs: ['ips'],
    outputs: ['domains', 'ips'],
    params: {
      timeout: { type: 'number', default: 120, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  resolve_ip_cidr: {
    name: 'CIDR IP Resolution',
    description: 'Progressively resolve IP addresses from CIDR blocks with stateful processing',
    category: 'DNS',
    icon: '🌐',
    inputs: ['cidrs'],
    outputs: ['domains', 'ips'],
    params: {
      ip_limit: { type: 'number', default: 500, description: 'Maximum IPs to process from CIDR blocks' },
      max_cidr_size: { type: 'number', default: 65536, description: 'Maximum CIDR size to process (safety limit)' },
      ips_per_worker: { type: 'number', default: 50, description: 'Number of IPs per worker for parallel processing' },
      timeout: { type: 'number', default: 300, description: 'Optional timeout override in seconds (uses system default if not specified)' },
      force_ip: { type: 'boolean', default: false, description: 'Force IP resolution' }
    }
  },
  subdomain_finder: {
    name: 'Subdomain Discovery',
    description: 'Find subdomains using subfinder',
    category: 'Discovery',
    icon: '🔎',
    inputs: ['domains'],
    outputs: ['domains'],
    params: {
      timeout: { type: 'number', default: 300, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  subdomain_permutations: {
    name: 'Subdomain Permutations',
    description: 'Generate and test subdomain permutations using gotator with intelligent wildcard filtering',
    category: 'Discovery',
    icon: '🔀',
    inputs: ['domains'],
    outputs: ['domains'],
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
    inputs: ['domains'],
    outputs: ['domains', 'ips'],
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
    inputs: ['ips'],
    outputs: ['services'],
    params: {
      timeout: { type: 'number', default: 900, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  nuclei_scan: {
    name: 'Nuclei Vulnerability Scan',
    description: 'Run nuclei vulnerability scanner on target',
    category: 'Vulnerability',
    icon: '🔬',
    inputs: ['domains', 'ips', 'urls'],
    outputs: ['findings', 'domains', 'ips', 'services', 'urls'],
    params: {
      template: { 
        type: 'nuclei_template_object', 
        default: { official: [], custom: [] }, 
        description: 'Nuclei templates to use (official and custom arrays)' 
      },
      cmd_args: { type: 'array', default: [], description: 'Additional command arguments (one per line, e.g., -silent, -rate-limit 100)' }
    }
  },
  wpscan: {
    name: 'WPScan Vulnerability Scan',
    description: 'Scan WordPress sites for vulnerabilities in WordPress core, plugins, and themes',
    category: 'Vulnerability',
    icon: '🔒',
    inputs: ['urls'],
    outputs: ['findings'],
    params: {
      api_token: { type: 'string', default: '', description: 'WPScan API token (optional, improves vulnerability detection)' },
      enumerate: { type: 'array', default: [], description: 'Enumeration options (one per line, e.g., vp, vt, u, p, t, tt, u1-10). Default: vp,vt,u (vulnerable plugins, vulnerable themes, users)' }
    }
  },
  test_http: {
    name: 'HTTP Testing',
    description: 'Test HTTP endpoints using httpx',
    category: 'Discovery',
    icon: '🌐',
    inputs: ['domains', 'urls'],
    outputs: ['services', 'domains', 'ips', 'urls', 'certificates'],
    params: {
      timeout: { type: 'number', default: 900, description: 'Optional timeout override in seconds (uses system default if not specified)' }
    }
  },
  typosquat_detection: {
    name: 'Typosquat Detection',
    description: 'Detect typosquatting domains using dnstwist and risk analysis. Supports both variation generation and direct input domain analysis modes.',
    category: 'Security',
    icon: '🎯',
    inputs: ['domains'],
    outputs: ['findings'],
    params: {
      analyze_input_as_variations: { type: 'boolean', default: false, description: 'Analyze input domains directly as typosquat variations (no variation generation)' },
      source: { type: 'string', default: '', description: 'Source of the typosquat detection (e.g. "ct_monitoring", "domain_analysis", "variation_detection")' },
      max_variations: { type: 'number', default: 100, description: 'Maximum variations per domain (only used when analyze_input_as_variations is false)' },
      max_workers: { type: 'number', default: 5, description: 'Maximum parallel workers' },
      domains_per_worker: { type: 'number', default: 20, description: 'Domains per worker batch' },
      fuzzers: { type: 'array', default: [], description: 'Specific dnstwist fuzzers to use (one per line, e.g., addition, bitsquatting, dictionary)' },
      active_checks: { type: 'boolean', default: true, description: 'Enable SSL/HTTP checks' },
      geoip_checks: { type: 'boolean', default: true, description: 'Enable GeoIP lookups' },
      exclude_tested: { type: 'boolean', default: true, description: 'Exclude already tested domains' },
      include_subdomains: { type: 'boolean', default: false, description: 'Include subdomain discovery' },
      recalculate_risk: { type: 'boolean', default: false, description: 'Recalculate risk scores' }
    }
  },
  detect_broken_links: {
    name: 'Broken Link Detection',
    description: 'Detect broken social media links (Facebook, Instagram, Twitter/X, LinkedIn)',
    category: 'Security',
    icon: '🔗',
    inputs: ['urls'],
    outputs: ['findings'],
    params: {}
  },
  screenshot_website: {
    name: 'Website Screenshot',
    description: 'Take screenshots of websites',
    category: 'Discovery',
    icon: '📸',
    inputs: ['urls'],
    outputs: ['screenshots'],
    params: {
      timeout: { type: 'number', default: 60, description: 'Optional timeout override per URL in seconds (uses system default if not specified)' }
    }
  },
  crawl_website: {
    name: 'Website Crawling',
    description: 'Crawl websites to discover URLs',
    category: 'Discovery',
    icon: '🕷️',
    inputs: ['urls'],
    outputs: ['urls'],
    params: {
      timeout: { type: 'number', default: 1800, description: 'Optional timeout override in seconds (uses system default if not specified)' },
      depth: { type: 'number', default: 5, description: 'Crawling depth for katana' }
    }
  },
  fuzz_website: {
    name: 'Website Fuzzing',
    description: 'Fuzz websites to discover hidden paths',
    category: 'Discovery',
    icon: '🕷️',
    inputs: ['urls'],
    outputs: ['urls'],
    params: {
      wordlist: { type: 'string', default: '/workspace/files/webcontent_test.txt', description: 'Wordlist to use for fuzzing' }
    }
  },
  shell_command: {
    name: 'Shell Command',
    description: 'Execute custom shell commands',
    category: 'Utility',
    icon: '🔧',
    inputs: ['strings'],
    outputs: ['strings'],
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