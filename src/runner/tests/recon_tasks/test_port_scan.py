"""Tests for ``recon_tasks.port_scan.PortScan``."""

from __future__ import annotations

import base64
import json

import pytest

from recon_tasks.base import AssetType
from recon_tasks.port_scan import PortScan


@pytest.fixture
def task(monkeypatch) -> PortScan:
    t = PortScan()
    # Short-circuit the API call so unit tests don't require network.
    monkeypatch.setattr(t, "get_ips_with_provider", lambda program: [])
    return t


def test_get_timestamp_hash_is_reversible(task: PortScan) -> None:
    digest = task.get_timestamp_hash("1.2.3.4")
    decoded = base64.b64decode(digest).decode()
    assert "1.2.3.4" in decoded
    assert "port_scan" in decoded


def test_get_command_accepts_list_of_ips(task: PortScan) -> None:
    cmd = task.get_command(["1.1.1.1", "8.8.8.8"])
    assert "1.1.1.1" in cmd
    assert "8.8.8.8" in cmd
    assert "port_scan_wrapper.py" in cmd


def test_get_command_filters_invalid_ips(task: PortScan) -> None:
    cmd = task.get_command(["1.1.1.1", "not-an-ip", "999.999.999.999"])
    assert "1.1.1.1" in cmd
    assert "not-an-ip" not in cmd


def test_get_command_keeps_ip_port_format(task: PortScan) -> None:
    cmd = task.get_command(["1.1.1.1:443", "2.2.2.2:8080"])
    assert "1.1.1.1:443" in cmd
    assert "2.2.2.2:8080" in cmd


def test_get_command_drops_providers(monkeypatch) -> None:
    t = PortScan()
    monkeypatch.setattr(t, "get_ips_with_provider", lambda program: ["1.1.1.1"])
    cmd = t.get_command(["1.1.1.1", "8.8.8.8"])
    assert "8.8.8.8" in cmd
    # 1.1.1.1 is a known provider and should be filtered out.
    # (substring check is safe here since it's the full line.)
    lines = cmd.split("\n")
    assert not any(line == "1.1.1.1" for line in lines)


def test_get_command_returns_empty_when_all_filtered(monkeypatch) -> None:
    t = PortScan()
    monkeypatch.setattr(t, "get_ips_with_provider", lambda program: ["1.1.1.1"])
    assert t.get_command(["1.1.1.1"]) == []


def test_parse_output_json_services(task: PortScan) -> None:
    raw = json.dumps(
        {
            "services": [
                {"ip": "1.2.3.4", "port": 80, "protocol": "tcp", "service_name": "http"},
                {"ip": "1.2.3.4", "port": 443, "protocol": "tcp", "service_name": "https", "banner": "nginx"},
            ],
            "ips": ["1.2.3.4", "5.6.7.8"],
        }
    )
    result = task.parse_output(raw)

    services = result[AssetType.SERVICE]
    assert [s.port for s in services] == [80, 443]
    assert services[1].banner == "nginx"

    ips = {ip.ip for ip in result[AssetType.IP]}
    assert ips == {"1.2.3.4", "5.6.7.8"}


def test_parse_output_empty_returns_empty_services(task: PortScan) -> None:
    result = task.parse_output("")
    assert result == {AssetType.SERVICE: []}


def test_parse_output_nmap_xml_open_ports(task: PortScan) -> None:
    xml = """<?xml version="1.0"?>
    <nmaprun>
      <host>
        <address addr="10.0.0.1" addrtype="ipv4"/>
        <ports>
          <port protocol="tcp" portid="22">
            <state state="open"/>
            <service name="ssh"/>
          </port>
          <port protocol="tcp" portid="80">
            <state state="closed"/>
            <service name="http"/>
          </port>
        </ports>
      </host>
    </nmaprun>"""
    result = task.parse_output(xml)
    services = result[AssetType.SERVICE]
    assert len(services) == 1
    assert services[0].port == 22
    assert services[0].service_name == "ssh"


def test_parse_output_dict_with_output_key(task: PortScan) -> None:
    payload = {"services": [{"ip": "1.2.3.4", "port": 22, "protocol": "tcp", "service_name": "ssh"}], "ips": ["1.2.3.4"]}
    wrapped = {"output": json.dumps(payload)}
    result = task.parse_output(wrapped)
    assert len(result[AssetType.SERVICE]) == 1
