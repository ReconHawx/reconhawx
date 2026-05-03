"""Unit tests for hostname / URL-host normalization helpers."""

from app.utils.domain_utils import normalize_hostname
from app.utils.url_utils import lower_url_host


class TestNormalizeHostname:
    def test_lowercase_trim_trailing_dot(self):
        assert normalize_hostname("  Foo.EXAMPLE.COM. ") == "foo.example.com"

    def test_none(self):
        assert normalize_hostname(None) is None

    def test_empty_after_strip(self):
        assert normalize_hostname("   ") == ""


class TestLowerUrlHost:
    def test_full_url_preserves_path_query_fragment(self):
        assert (
            lower_url_host("HTTPS://WWW.Example.COM:8443/Path?Q=1#Frag")
            == "https://www.example.com:8443/Path?Q=1#Frag"
        )

    def test_scheme_relative(self):
        assert lower_url_host("//Foo.com/bar") == "//foo.com/bar"

    def test_ipv6_bracket_host(self):
        assert (
            lower_url_host("HTTP://[FEDC:BA98::7654]/p")
            == "http://[fedc:ba98::7654]/p"
        )

    def test_plain_path_unchanged(self):
        """No netloc → host portion not modified (consistent with ingestion using absolute URLs)."""
        assert lower_url_host("WWW.Example.COM") == "WWW.Example.COM"

    def test_none_and_empty(self):
        assert lower_url_host(None) is None
        assert lower_url_host("") == ""
