"""Tests for CTLogPoller._parse_entry (no HTTP)."""

import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID


def _self_signed_der(cn: str) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(Encoding.DER)


def _leaf_input_x509(cert_der: bytes, timestamp: int = 1_700_000_000_000) -> str:
    version = b"\x00"
    leaf_type = b"\x00"
    ts = timestamp.to_bytes(8, "big")
    entry_type = (0).to_bytes(2, "big")
    clen = len(cert_der).to_bytes(3, "big")
    raw = version + leaf_type + ts + entry_type + clen + cert_der
    return base64.b64encode(raw).decode("ascii")


@pytest.mark.asyncio
async def test_parse_entry_x509_extracts_cn():
    from ct_log_poller import CTLogPoller, CTLogState

    async def _noop(_cert):
        return None

    poller = CTLogPoller(callback=_noop, ct_logs=[])
    der = _self_signed_der("www.example.com")
    entry = {"leaf_input": _leaf_input_x509(der), "extra_data": ""}
    state = CTLogState(name="TestLog", url="https://example.invalid/", operator="t")
    info = poller._parse_entry(entry, state)
    assert info is not None
    assert "www.example.com" in info.domains
    assert info.source == "TestLog"
    assert info.update_type == "X509LogEntry"
    assert info.issuer_cn != "" or info.issuer != ""
