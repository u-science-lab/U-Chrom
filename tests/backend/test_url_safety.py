"""Tests for webapp.backend.url_safety.

Covers the artifact URL safety policy: relative paths and public http(s) pass;
pseudo-protocols, protocol-relative refs, and private/loopback/link-local hosts
are blocked. Also covers sanitize_artifact_urls deep-walk behaviour on a
Gosling-shaped spec.
"""
import pytest

from webapp.backend.url_safety import is_safe_url, sanitize_artifact_urls


# --- allowed ---------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "/api/track_csv/H3K27ac",
    "/api/v1/tileset_info/?d=contact-chr1",
    "/api/custom/myfunc/chr1?format=gosling",
    "./relative/path",
    "relative/path?x=1",
    "data.json",
    "https://example.com/data.csv",
    "http://example.com:8080/track",
    "https://4dn-open-data.s3.amazonaws.com/file.beddb",
    "https://sub.domain.example.org/path",
])
def test_safe_urls_allowed(url):
    assert is_safe_url(url) is True


# --- blocked: pseudo-protocols ---------------------------------------------

@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "data:image/png;base64,iVBOR",
    "file:///etc/passwd",
    "vbscript:msgbox(1)",
])
def test_pseudo_protocols_blocked(url):
    assert is_safe_url(url) is False


# --- blocked: SSRF / local / private ---------------------------------------

@pytest.mark.parametrize("url", [
    "http://localhost:8080/x",
    "https://localhost/x",
    "http://localhost.localdomain/x",
    "http://foo.localhost/x",
    "http://127.0.0.1/x",
    "http://127.0.0.53:53/x",
    "http://0.0.0.0/x",
    "http://169.254.169.254/",            # cloud metadata endpoint
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/x",
    "http://10.255.255.255/x",
    "http://172.16.0.1/x",
    "http://172.31.255.255/x",
    "http://192.168.1.1/x",
    "https://[::1]/x",                     # IPv6 loopback
    "http://[fe80::1]/x",                  # IPv6 link-local
])
def test_ssrf_targets_blocked(url):
    assert is_safe_url(url) is False


# --- blocked: protocol-relative & malformed --------------------------------

@pytest.mark.parametrize("url", [
    "//evil.com/x",
    "//169.254.169.254/x",
    "",
    "   ",
    "\t\n",
    "http://",
])
def test_protocol_relative_and_malformed_blocked(url):
    assert is_safe_url(url) is False


def test_non_string_rejected():
    assert is_safe_url(None) is False
    assert is_safe_url(123) is False
    assert is_safe_url({"url": "/x"}) is False


# --- public 172.x (outside private 172.16-31) is allowed -------------------

def test_public_172_allowed():
    # 172.15 and 172.32 are NOT in the private 172.16.0.0/12 block.
    assert is_safe_url("http://172.15.0.1/x") is True
    assert is_safe_url("http://172.32.0.1/x") is True


# --- sanitize_artifact_urls ------------------------------------------------

def test_sanitize_keeps_safe_drops_unsafe():
    spec = {
        "tracks": [
            {"data": {"type": "csv", "url": "/api/track_csv/H3K27ac"}},
            {"data": {"type": "json", "url": "javascript:alert(1)"}},
            {"data": {"type": "json", "url": "http://169.254.169.254/"}},
        ],
        "views": [
            {"tracks": [{"data": {"url": "https://example.com/ok.csv"}}]},
        ],
    }
    cleaned, rejected = sanitize_artifact_urls(spec)

    # Safe URLs survive.
    assert cleaned["tracks"][0]["data"]["url"] == "/api/track_csv/H3K27ac"
    assert cleaned["views"][0]["tracks"][0]["data"]["url"] == "https://example.com/ok.csv"
    # Unsafe URL keys are removed entirely.
    assert "url" not in cleaned["tracks"][1]["data"]
    assert "url" not in cleaned["tracks"][2]["data"]
    # Both rejections are reported.
    assert len(rejected) == 2
    assert any("javascript:alert(1)" in r for r in rejected)
    assert any("169.254.169.254" in r for r in rejected)


def test_sanitize_does_not_mutate_original():
    spec = {"data": {"url": "javascript:alert(1)"}}
    cleaned, rejected = sanitize_artifact_urls(spec)
    # Original untouched.
    assert spec["data"]["url"] == "javascript:alert(1)"
    assert "url" not in cleaned["data"]
    assert rejected == ["url=javascript:alert(1)"]


def test_sanitize_handles_href_src_uri_fields():
    art = {"href": "file:///etc/passwd", "src": "/ok.png", "uri": "vbscript:x"}
    cleaned, rejected = sanitize_artifact_urls(art)
    assert cleaned == {"src": "/ok.png"}
    assert len(rejected) == 2


def test_sanitize_clean_spec_no_rejections():
    spec = {"tracks": [{"data": {"url": "/api/track_csv/x"}}]}
    cleaned, rejected = sanitize_artifact_urls(spec)
    assert rejected == []
    assert cleaned == spec
