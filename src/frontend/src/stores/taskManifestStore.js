import { create } from 'zustand';
import { adminAPI } from '../services/api/admin';

// Backend AssetType/FindingType -> frontend UI type name. The frontend speaks in
// plural, UI-friendly labels (domains, urls, ips, cidrs, services, certificates,
// screenshots, findings, strings) while the API manifest returns the canonical
// singular enum values (subdomain, url, ip, cidr, service, certificate, screenshot,
// apex_domain, string, nuclei, typosquat_*, broken_link, wpscan).
const BACKEND_TO_FRONTEND = {
  subdomain: 'domains',
  apex_domain: 'apex_domains',
  ip: 'ips',
  url: 'urls',
  cidr: 'cidrs',
  service: 'services',
  certificate: 'certificates',
  screenshot: 'screenshots',
  string: 'strings',
  nuclei: 'findings',
  typosquat_domain: 'findings',
  typosquat_url: 'findings',
  typosquat_screenshot: 'findings',
  broken_link: 'findings',
  wpscan: 'findings',
};

const translateTypes = (types) => {
  const out = [];
  for (const t of types || []) {
    const mapped = BACKEND_TO_FRONTEND[t] || t;
    if (!out.includes(mapped)) out.push(mapped);
  }
  return out;
};

// Built-in fallback mirroring recon_task_builtin_defaults.yaml. Used before the
// API manifest is fetched (and as a safety net if the fetch fails), so the
// workflow builder renders coherent handles without blocking on a network round-trip.
const FALLBACK_MANIFEST = {
  resolve_domain:         { inputs: ['domains'],                  outputs: ['domains', 'ips'] },
  whois_domain_check:     { inputs: ['domains'],                  outputs: ['apex_domains'] },
  resolve_ip:             { inputs: ['ips'],                      outputs: ['domains', 'ips'] },
  resolve_ip_cidr:        { inputs: ['cidrs'],                    outputs: ['domains', 'ips', 'services'] },
  subdomain_finder:       { inputs: ['domains'],                  outputs: ['domains'] },
  subdomain_permutations: { inputs: ['domains'],                  outputs: ['domains', 'ips'] },
  dns_bruteforce:         { inputs: ['domains'],                  outputs: ['domains', 'ips'] },
  port_scan:              { inputs: ['ips'],                      outputs: ['services'] },
  nuclei_scan:            { inputs: ['domains', 'ips', 'urls'],   outputs: ['findings', 'domains', 'ips', 'services', 'urls'] },
  wpscan:                 { inputs: ['urls'],                     outputs: ['findings'] },
  test_http:              { inputs: ['domains', 'urls'],          outputs: ['services', 'domains', 'ips', 'urls', 'certificates'] },
  typosquat_detection:    { inputs: ['domains'],                  outputs: ['findings'] },
  detect_broken_links:    { inputs: ['urls'],                     outputs: ['findings'] },
  screenshot_website:     { inputs: ['urls'],                     outputs: ['screenshots'] },
  crawl_website:          { inputs: ['urls'],                     outputs: ['urls'] },
  fuzz_website:           { inputs: ['urls'],                     outputs: ['urls'] },
  shell_command:          { inputs: ['strings'],                  outputs: ['strings'] },
};

let hydratePromise = null;

export const useTaskManifestStore = create((set, get) => ({
  manifest: { ...FALLBACK_MANIFEST },
  hydrated: false,
  error: null,

  getInputs: (taskType) => get().manifest[taskType]?.inputs || [],
  getOutputs: (taskType) => get().manifest[taskType]?.outputs || [],

  hydrateFromApi: async () => {
    if (hydratePromise) return hydratePromise;
    hydratePromise = (async () => {
      try {
        const data = await adminAPI.getPublicReconTaskManifest();
        const tasks = (data && data.tasks) || {};
        const next = { ...FALLBACK_MANIFEST };
        for (const [name, entry] of Object.entries(tasks)) {
          if (!entry || typeof entry !== 'object') continue;
          next[name] = {
            inputs: translateTypes(entry.input_types),
            outputs: translateTypes(entry.output_types),
          };
        }
        set({ manifest: next, hydrated: true, error: null });
      } catch (err) {
        // Keep fallback data and record the error; workflow builder keeps working.
        console.warn('Failed to hydrate task manifest from API, using fallback', err);
        set({ error: err });
      } finally {
        hydratePromise = null;
      }
    })();
    return hydratePromise;
  },
}));

// Non-hook accessors for non-React code paths (e.g. zustand stores).
export const getTaskInputs = (taskType) => useTaskManifestStore.getState().getInputs(taskType);
export const getTaskOutputs = (taskType) => useTaskManifestStore.getState().getOutputs(taskType);
