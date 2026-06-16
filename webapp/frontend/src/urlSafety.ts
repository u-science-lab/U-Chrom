/**
 * Client-side URL safety check — the fallback half of the defense.
 *
 * The backend (`url_safety.py`) sanitizes agent-emitted artifact URLs at the
 * emit boundary, which is the authoritative gate. This module re-checks any
 * agent-controlled URL right before the client consumes it (e.g. a Gosling
 * `data.url`), so a spec arriving from a stale snapshot, a reconnect path, or a
 * future emit site that forgot to sanitize still can't smuggle a
 * `javascript:`/`file:` pseudo-protocol or an SSRF target to the renderer.
 *
 * Rules mirror the backend:
 *   - relative references (no scheme, not protocol-relative) → allowed
 *   - http(s) to a public host → allowed
 *   - http(s) to the current page origin → allowed
 *   - http(s) to other localhost / loopback / private / link-local → blocked
 *   - protocol-relative `//host` → blocked
 *   - any non-http(s) scheme → blocked
 */

const LOCAL_HOSTNAMES = new Set([
  'localhost',
  'localhost.localdomain',
  'ip6-localhost',
])

// IPv4 dotted-quad; we range-check the octets for the private/loopback blocks.
const IPV4_RE = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/

function isBlockedIpv4(host: string): boolean {
  const m = IPV4_RE.exec(host)
  if (!m) return false
  const a = Number(m[1])
  const b = Number(m[2])
  if (a === 127) return true // loopback 127.0.0.0/8
  if (a === 10) return true // private 10.0.0.0/8
  if (a === 0) return true // 0.0.0.0/8 "this host"
  if (a === 172 && b >= 16 && b <= 31) return true // 172.16.0.0/12
  if (a === 192 && b === 168) return true // 192.168.0.0/16
  if (a === 169 && b === 254) return true // link-local 169.254/16 (cloud metadata)
  return false
}

function isBlockedHost(rawHost: string): boolean {
  const host = rawHost.toLowerCase().replace(/\.+$/, '')
  if (!host) return true
  if (LOCAL_HOSTNAMES.has(host) || host.endsWith('.localhost')) return true
  if (isBlockedIpv4(host)) return true
  // IPv6 loopback / link-local / unique-local. URL.hostname wraps v6 in [].
  const v6 = host.replace(/^\[/, '').replace(/\]$/, '')
  if (v6 === '::1' || v6 === '::') return true
  if (v6.startsWith('fe80:') || v6.startsWith('fc') || v6.startsWith('fd')) return true
  return false
}

export function isSafeUrl(url: unknown): boolean {
  if (typeof url !== 'string') return false
  const raw = url.trim()
  if (!raw) return false
  // Strip C0 controls, space, and DEL that can split a scheme (e.g. "java\tscript:").
  // eslint-disable-next-line no-control-regex
  const cleaned = raw.replace(/[\u0000-\u0020\u007f]/g, '')
  if (!cleaned) return false
  if (cleaned.startsWith('//')) return false // protocol-relative

  // Detect an explicit scheme. A leading "scheme:" where scheme is
  // [a-z][a-z0-9+.-]* per RFC 3986. No match → treat as relative (allowed).
  const schemeMatch = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(cleaned)
  if (!schemeMatch) return true

  const scheme = schemeMatch[1].toLowerCase()
  if (scheme !== 'http' && scheme !== 'https') return false

  try {
    const parsed = new URL(cleaned)
    if (!parsed.hostname) return false
    if (
      typeof window !== 'undefined'
      && parsed.origin === window.location.origin
    ) {
      return true
    }
    return !isBlockedHost(parsed.hostname)
  } catch {
    return false
  }
}

/**
 * Recursively strip unsafe URL fields (url/href/src/uri) from a JSON-ish value,
 * returning a cleaned deep copy. Used to scrub a Gosling spec before handing it
 * to the renderer. Non-object input is returned unchanged.
 */
const URL_FIELDS = new Set(['url', 'href', 'src', 'uri'])

export function sanitizeUrls<T>(value: T): T {
  const walk = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(walk)
    if (node && typeof node === 'object') {
      const out: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
        if (URL_FIELDS.has(k.toLowerCase()) && typeof v === 'string') {
          if (isSafeUrl(v)) out[k] = v
          // else: drop the unsafe URL
        } else {
          out[k] = walk(v)
        }
      }
      return out
    }
    return node
  }
  return walk(value) as T
}
