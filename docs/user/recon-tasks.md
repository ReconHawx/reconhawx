# Recon tasks reference (workflows)

This guide describes **workflow recon tasks** implemented in the runner: what each task is for, which **input kinds** it expects, and which **outputs** it can produce for the rest of a workflow or for the platform.

For how to wire inputs and run workflows in the UI, see [Workflows](workflows.md).

## How to read this page

### Input type (technical)

Each task declares one or more **runner input types**. In the UI you usually connect **workflow inputs** or **program assets**; those map to the same underlying kinds:

| Input type | Meaning for you |
|------------|-----------------|
| **string** | Plain text lines the worker treats as targets (often hostnames, IPs, URLs, or CIDRs depending on the task). Multi-value workflow inputs become multiple lines. |
| **subdomain** | Subdomain records (hostnames), including from **Program assets → Subdomains**. |
| **ip** | IP addresses. |
| **url** | Full URLs (`http://` or `https://`). |

Some tasks accept **more than one** input kind (for example Nuclei).

### Output type

**Assets** (subdomains, IPs, services, URLs, certificates, screenshots, apex domains) are stored on the program and can feed **downstream tasks** in the same workflow.

**Findings** (Nuclei, WPScan, broken links, typosquat-related types) are stored as **findings** rather than generic assets. They appear in the findings areas of the product; not every downstream task can consume them as workflow input—check the task you want to chain.

A few tasks **write results only through the API** during the run (for example typosquat detection). They still complete successfully but may declare **no asset output types** because results are not emitted as standard workflow assets.

### Parameters and limits

Timeouts, chunk sizes, wordlists, and similar knobs are controlled by **recon task parameters** (built-in defaults, optionally overridden by administrators). This document does not list every parameter; use task **Configure → Parameters** in the UI and admin documentation for operational tuning.

---

## Task catalog

| Task | What it does | Input type | Output type |
|------|----------------|------------|---------------|
| **resolve_domain** | DNS forward lookup: resolves hostnames to IPv4/IPv6 addresses (dnsx). | string (hostnames) | subdomain, ip |
| **resolve_ip** | Reverse DNS: maps IP addresses to names (dnsx). | string (IPs) | subdomain, ip |
| **resolve_ip_cidr** | Expands a CIDR block into individual IPs, resolves PTR-style names where applicable, and can orchestrate follow-on jobs (including optional port scans). | string (CIDR such as `10.0.0.0/24`, or single IPs) | subdomain, ip, service |
| **subdomain_finder** | Passive subdomain discovery (subfinder) from seed domains. | string (apex or seed domains) | subdomain |
| **dns_bruteforce** | Active subdomain brute force using DNS and a wordlist (PureDNS-style pipeline). | string (parent domains / zones to brute force) | subdomain, ip |
| **subdomain_permutations** | Generates likely subdomain permutations (gotator) and resolves them. | string (base domains) | subdomain, ip |
| **port_scan** | TCP/UDP port scan: accepts bare IPs or `ip:port` targets for focused checks. | string | service |
| **nuclei_scan** | Runs the Nuclei template engine against targets; records template matches as findings and can also surface related hosts, URLs, and services from results. | subdomain, ip, or url | nuclei finding, subdomain, ip, service, url |
| **wpscan** | WordPress security scan (WPScan) for core, plugins, and themes. | url | wpscan finding |
| **test_http** | Probes HTTP/HTTPS with httpx: separates full URLs from bare hostnames, fingerprints TLS, detects technologies, and collects live services, hosts, IPs, URLs, and certificate material from responses. | string (URLs and/or hostnames) | service, subdomain, ip, url, certificate |
| **whois_domain_check** | WHOIS lookup for registrable domains; attaches structured WHOIS to apex domain records. | string (domain names) | apex_domain |
| **crawl_website** | Web crawl from seed URLs to discover more URLs on the same sites. | string (seed URLs) | url |
| **screenshot_website** | Captures rendered page screenshots for URLs. | string (URLs) | screenshot |
| **fuzz_website** | Directory/file discovery with ffuf using a wordlist. | string (base URLs to fuzz) | url |
| **detect_broken_links** | Checks pages for broken or risky outbound links (including social links and hijackable unregistered domains). | string (page URLs, `http://` or `https://`) | broken_link finding |
| **typosquat_detection** | Generates and analyzes typosquat candidates (dnstwist and related checks), risk scoring, optional screenshots; persists typosquat findings via the API. | subdomain | _(findings written during the run; no standard asset output list)_ |
| **shell_command** | Runs a configured shell pipeline; optional stdin from workflow input. Parameters define the command; mapped input is fed on standard input when provided. | string (stdin text) | string (raw stdout/stderr capture) |
| **asset_batch_generator** | **Testing only:** generates synthetic subdomains, IPs, services, URLs, certificates, and sample Nuclei-style findings for load tests. | string (program name seed) | subdomain, ip, service, url, certificate, nuclei finding, string (synthetic apex payloads) |

---

## Choosing the right task

- **Discovery:** `subdomain_finder` (passive) vs `dns_bruteforce` / `subdomain_permutations` (active / combinatorial)—start passive when you want less noise.
- **Resolution:** `resolve_domain` for names → IPs, `resolve_ip` for IPs → names; use `resolve_ip_cidr` only when the scope is an IP block you intentionally control.
- **Exposure:** `port_scan` then `nuclei_scan` or `wpscan` (for WordPress) is a common sequence; map the same assets or URLs forward.
- **Web surface:** `crawl_website` and `fuzz_website` expand URL lists; `screenshot_website` and `test_http` add evidence for review.

---

## Related documentation

- [Workflows](workflows.md) — builder, input sources, and mapping
- [Programs](programs.md) — where discovered assets and scope live
