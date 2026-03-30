#!/usr/bin/env python3
"""
Port scan wrapper: runs nmap to find open ports, then nerva to identify services.
Outputs JSON compatible with PortScan.parse_output().
"""

import os
import subprocess
import sys
import json
import tempfile
import xml.etree.ElementTree as ET
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)
NERVA_TIMEOUT = 10
NERVA_MAX_WORKERS = 10


def read_targets_from_stdin() -> Tuple[List[str], List[str]]:
    """Read targets from stdin. Returns (ip_targets, ip_port_targets)."""
    ip_targets = []
    ip_port_targets = []
    for line in sys.stdin:
        target = line.strip()
        if not target:
            continue
        if ":" in target and not target.startswith("["):
            parts = target.split(":")
            if len(parts) == 2 and parts[1].isdigit():
                ip_port_targets.append(target)
                continue
        ip_targets.append(target)
    return ip_targets, ip_port_targets


def run_nmap(targets: List[str], port_spec: str) -> Optional[str]:
    """Run nmap and return XML output. port_spec is e.g. '-p- --top-ports 1000' or '-p 80'."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(targets))
        target_file = f.name
    try:
        cmd = [
            "nmap",
            "--script=banner",
            "-oX",
            "-",
            "-iL",
            target_file,
        ] + port_spec.split()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            logger.warning(f"nmap stderr: {result.stderr[:500]}")
        return result.stdout if result.stdout else None
    except subprocess.TimeoutExpired:
        logger.error("nmap timed out")
        return None
    except Exception as e:
        logger.error(f"nmap failed: {e}")
        return None
    finally:
        try:
            os.unlink(target_file)
        except OSError:
            pass


def parse_nmap_xml(xml_output: str) -> List[Dict[str, Any]]:
    """Parse nmap XML and return list of open port dicts: {ip, port, protocol, service_name, banner}."""
    services = []
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError as e:
        logger.error(f"Failed to parse nmap XML: {e}")
        return services

    for host in root.findall(".//host"):
        addr_elem = host.find('.//address[@addrtype="ipv4"]')
        if addr_elem is None:
            continue
        ip = addr_elem.get("addr")
        if not ip:
            continue

        for port_elem in host.findall(".//port"):
            port_id = port_elem.get("portid")
            protocol = port_elem.get("protocol", "tcp")
            if not port_id:
                continue

            state = port_elem.find("state")
            if state is None or state.get("state") != "open":
                continue

            service_elem = port_elem.find("service")
            service_name = (
                service_elem.get("name") if service_elem is not None else "unknown"
            )
            if not service_name:
                service_name = "unknown"

            banner = None
            script = port_elem.find('.//script[@id="banner"]')
            if script is not None:
                banner = script.get("output")

            services.append(
                {
                    "ip": ip,
                    "port": int(port_id),
                    "protocol": protocol,
                    "service_name": service_name,
                    "banner": banner,
                }
            )
    return services


def run_nerva(ip: str, port: int) -> Optional[Dict[str, Any]]:
    """Run nerva on IP:PORT and return JSON result or None.
    Nerva fingerprints the service (e.g. SSH) regardless of port; nmap often guesses from port only.
    """
    target = f"{ip}:{port}"
    try:
        result = subprocess.run(
            ["nerva", "-t", target, "--json"],
            capture_output=True,
            text=True,
            timeout=NERVA_TIMEOUT,
        )
        # Prefer stdout, fallback to stderr (some tools output JSON to stderr)
        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            return None
        data = json.loads(output)
        # Accept valid JSON even when returncode != 0
        if not isinstance(data, dict) or "ip" not in data:
            return None
        return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


def merge_nerva_into_service(
    service: Dict[str, Any], nerva_result: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Merge nerva result into service dict.
    Nerva fingerprints the actual service (e.g. SSH on non-standard port 1022);
    nmap guesses from port only (e.g. 'exp2' for 1022). Always prefer nerva's detection.
    """
    if not nerva_result:
        return service

    out = service.copy()
    # Nerva's protocol is the actual service (ssh, ftp, http, etc.); always use it over nmap's guess
    if nerva_result.get("protocol"):
        out["service_name"] = nerva_result["protocol"]
        out["protocol"] = nerva_result.get("transport", "tcp")
    metadata = nerva_result.get("metadata", {})
    if metadata.get("banner"):
        out["banner"] = metadata["banner"]
    # Store full nerva metadata in its own field (cpes, confidence, algo, auth_methods, etc.)
    if metadata:
        out["nerva_metadata"] = metadata
    return out


def main():
    ip_targets, ip_port_targets = read_targets_from_stdin()
    if not ip_targets and not ip_port_targets:
        print(json.dumps({"services": [], "ips": []}))
        sys.exit(0)

    all_services = []
    seen_ips = set()

    # IP-only: port range scan
    if ip_targets:
        xml_out = run_nmap(ip_targets, "-p- --top-ports 1000")
        if xml_out:
            all_services.extend(parse_nmap_xml(xml_out))

    # IP:PORT: specific port scans (group by port)
    if ip_port_targets:
        port_groups = {}
        for ip_port in ip_port_targets:
            ip, port = ip_port.split(":")
            if port not in port_groups:
                port_groups[port] = []
            port_groups[port].append(ip)

        for port, ips in port_groups.items():
            xml_out = run_nmap(ips, f"-p {port}")
            if xml_out:
                all_services.extend(parse_nmap_xml(xml_out))

    # Deduplicate by (ip, port)
    seen = set()
    unique_services = []
    for s in all_services:
        key = (s["ip"], s["port"])
        if key not in seen:
            seen.add(key)
            unique_services.append(s)
    all_services = unique_services

    if not all_services:
        ips = list(seen_ips) if seen_ips else []
        print(json.dumps({"services": [], "ips": ips}))
        sys.exit(0)

    # Run nerva on each open port (parallel)
    def process_one(svc: Dict[str, Any]) -> Dict[str, Any]:
        nerva_result = run_nerva(svc["ip"], svc["port"])
        return merge_nerva_into_service(svc, nerva_result)

    merged = []
    with ThreadPoolExecutor(max_workers=NERVA_MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, s): s for s in all_services}
        for future in as_completed(futures):
            try:
                merged.append(future.result())
            except Exception as e:
                logger.warning(f"Nerva merge failed: {e}")
                merged.append(futures[future])

    for s in merged:
        seen_ips.add(s["ip"])

    output = {
        "services": [
            {
                "ip": s["ip"],
                "port": s["port"],
                "protocol": s.get("protocol", "tcp"),
                "service_name": s.get("service_name", "unknown"),
                "banner": s.get("banner"),
                "nerva_metadata": s.get("nerva_metadata"),
            }
            for s in merged
        ],
        "ips": list(seen_ips),
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
