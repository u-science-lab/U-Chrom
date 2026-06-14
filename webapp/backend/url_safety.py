"""Centralized URL safety validation for agent-emitted artifacts.

Industry lesson (echoed by the assistant-ui docs): a component/handler
whitelist only gates *which* component renders, never *what* its props
carry. Our ``ALLOWED_COMPONENTS`` / ``ARTIFACT_HANDLERS`` whitelists are the
same — they vet the artifact shape, not the URLs inside it. The agent controls
those URLs (Gosling ``data.url``, patch values, component props), so a crafted
spec could smuggle a ``javascript:`` pseudo-protocol, a ``file://`` read, or an
``http://169.254.169.254/`` SSRF probe at the cloud metadata endpoint.

This module is the single place that decides whether an artifact URL may ship
to the client. The rules are deliberately permissive about the *legitimate*
case and strict about everything else:

  * **Relative references** (``/api/track_csv/x``, ``./foo``, ``foo?x=1``) →
    ALLOWED. Gosling's ``data.url`` is overwhelmingly a relative API path; these
    resolve same-origin and are exactly what the backend itself emits.
  * **Absolute http(s)** to a *public* host → ALLOWED. Same-origin in prod, and
    public tilesets are a legitimate Gosling data source.
  * **http(s) to localhost / loopback / private / link-local** → BLOCKED (SSRF).
  * **Protocol-relative** ``//host/...`` → BLOCKED (resolves to an unverifiable
    external host).
  * **Any non-http(s) scheme** (``javascript:``, ``data:``, ``file:``, ``vbscript:``)
    → BLOCKED.
"""
from __future__ import annotations

import copy
import ipaddress
import re
from urllib.parse import urlsplit

# Field names (case-insensitive) treated as URLs when walking an artifact.
URL_FIELD_NAMES = frozenset({"url", "href", "src", "uri"})

# Strip C0 controls + DEL + assorted whitespace that bypass naive scheme checks
# (e.g. "java\tscript:" or a leading newline before "javascript:").
_CONTROL_CHARS = re.compile(r"[\x00-\x20\x7f]")

# Hostnames that always denote the local machine.
_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def _is_blocked_host(host: str) -> bool:
    """True if *host* is loopback / private / link-local / otherwise non-public."""
    host = host.lower().strip(".")
    if not host:
        return True
    if host in _LOCAL_HOSTNAMES or host.endswith(".localhost"):
        return True
    # Literal IP (v4 or v6)? Block any non-public category. Covers 127.0.0.0/8,
    # 10/8, 172.16/12, 192.168/16, 169.254/16 (incl. 169.254.169.254 metadata),
    # ::1, fc00::/7, fe80::/10, 0.0.0.0, etc.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        )
    return False


def is_safe_url(url: object) -> bool:
    """Return True if *url* is safe to hand to the client for an artifact field.

    Permits relative references and public http(s); rejects pseudo-protocols and
    http(s) pointed at local / private / link-local addresses. Non-string input
    is rejected.
    """
    if not isinstance(url, str):
        return False
    raw = url.strip()
    if not raw:
        return False
    cleaned = _CONTROL_CHARS.sub("", raw)
    if not cleaned:
        return False
    # Protocol-relative (//host/path) → unverifiable external host.
    if cleaned.startswith("//"):
        return False
    parts = urlsplit(cleaned)
    scheme = parts.scheme.lower()
    if not scheme:
        # No scheme → relative reference (same-origin). Allow.
        return True
    if scheme not in ("http", "https"):
        return False
    host = parts.hostname
    if not host:
        return False
    return not _is_blocked_host(host)


def sanitize_artifact_urls(artifact: object) -> tuple[object, list[str]]:
    """Recursively validate every URL field in *artifact*.

    Walks dicts/lists; for any key in ``URL_FIELD_NAMES`` whose value is a string
    that fails :func:`is_safe_url`, the offending key is removed from the copy
    and a ``"<field>=<value>"`` record is appended to the rejected list.

    Returns a ``(cleaned_copy, rejected)`` tuple. The original is never mutated.
    """
    rejected: list[str] = []

    def _walk(node: object) -> object:
        if isinstance(node, dict):
            out: dict = {}
            for key, value in node.items():
                if (
                    isinstance(key, str)
                    and key.lower() in URL_FIELD_NAMES
                    and isinstance(value, str)
                ):
                    if is_safe_url(value):
                        out[key] = value
                    else:
                        rejected.append(f"{key}={value}")
                        # Drop the unsafe URL rather than ship it.
                        continue
                else:
                    out[key] = _walk(value)
            return out
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    cleaned = _walk(copy.deepcopy(artifact))
    return cleaned, rejected
