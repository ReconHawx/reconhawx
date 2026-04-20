"""Unit tests for YesWeHackService.convert_scopes_to_structured (no API calls)."""

from services.yeswehack_service import YesWeHackService


def _svc() -> YesWeHackService:
    return YesWeHackService("x" * 21)


def test_convert_wildcard_web_application():
    scopes = [
        {
            "scope": "*.cyber.gouv.qc.ca",
            "scope_type": "web-application",
            "asset_value": "HIGH",
        }
    ]
    in_scope, out_scope, cidrs, summary = _svc().convert_scopes_to_structured(scopes)
    assert out_scope == []
    assert cidrs == []
    assert summary == {"in_scope": 1, "out_of_scope": 0, "cidr_blocks": 0}
    assert len(in_scope) == 1
    assert in_scope[0]["pattern"] == "*.cyber.gouv.qc.ca"
    assert in_scope[0]["wildcard"] is True


def test_convert_api_url_hostname():
    scopes = [
        {
            "scope": "https://api.test.seao.si.gouv.qc.ca/ywh/",
            "scope_type": "api",
            "asset_value": "HIGH",
        }
    ]
    in_scope, _, cidrs, summary = _svc().convert_scopes_to_structured(scopes)
    assert cidrs == []
    assert summary["in_scope"] == 1
    assert in_scope[0]["pattern"] == "api.test.seao.si.gouv.qc.ca"
    assert in_scope[0]["wildcard"] is False


def test_skips_mobile_application():
    scopes = [
        {
            "scope": "Clic École Android",
            "scope_type": "mobile-application-android",
            "asset_value": "HIGH",
        },
        {
            "scope": "https://example.com/",
            "scope_type": "web-application",
            "asset_value": "HIGH",
        },
    ]
    in_scope, _, _, summary = _svc().convert_scopes_to_structured(scopes)
    assert summary["in_scope"] == 1
    assert len(in_scope) == 1
    assert in_scope[0]["pattern"] == "example.com"


def test_complex_scope_with_cidr_and_alternatives():
    scopes = [
        {
            "scope": "(*.post.ch:443|*.post.ch:80) AND 194.41.128.0/17",
            "scope_type": "other",
            "asset_value": "HIGH",
        }
    ]
    in_scope, _, cidrs, summary = _svc().convert_scopes_to_structured(scopes)
    assert summary["cidr_blocks"] == 1
    assert "194.41.128.0/17" in cidrs
    # Both alternatives normalize to the same *.post.ch after stripping ports
    assert summary["in_scope"] == 1
    assert in_scope[0]["pattern"] == "*.post.ch"
    assert in_scope[0]["wildcard"] is True
