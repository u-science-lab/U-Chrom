/** Helpers of the dataset switcher and the Open dataset dialog (pure — tested). */
import type { DatasetSummary } from './types'

/** Path -> breadcrumb segments (label, full path), root first. */
export function breadcrumbs(path: string, sep = '/'): { label: string; path: string }[] {
  if (sep === '\\') {
    const parts = path.split('\\').filter(Boolean)
    return parts.map((p, i) => ({ label: p, path: parts.slice(0, i + 1).join('\\') + (i === 0 ? '\\' : '') }))
  }
  const parts = path.split('/').filter(Boolean)
  return [{ label: '/', path: '/' }, ...parts.map((p, i) => ({ label: p, path: '/' + parts.slice(0, i + 1).join('/') }))]
}

export function fmtSize(n: number | null | undefined): string {
  if (n === null || n === undefined) return ''
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1000 && i < u.length - 1) {
    v /= 1000
    i++
  }
  return `${i === 0 ? v : v < 10 ? v.toFixed(1) : Math.round(v)} ${u[i]}`
}

export function fmtDate(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** What a dataset holds, as short labels. */
export function datasetBadges(d: DatasetSummary): string[] {
  const out: string[] = []
  if (d.has_coords !== false && d.n_spots > 0) out.push('3D')
  if (d.spatial?.length) out.push('spatial')
  if (d.contact_maps?.length) out.push('contacts')
  if (d.tracks?.length) out.push('tracks')
  if (d.embeddings?.length) out.push('embeddings')
  return out
}

/** "4,290 cells · 2,000 spots" (spots only when there are any). */
export function datasetCounts(d: DatasetSummary): string {
  const f = (n: number) => n.toLocaleString('en-US')
  return [`${f(d.n_cells)} cells`, d.n_spots > 0 ? `${f(d.n_spots)} spots` : null].filter(Boolean).join(' · ')
}

// ---- recently opened paths (per viewer) ----
export const RECENT_KEY = 'uchrom.browser.recent'
export const RECENT_MAX = 8

export function parseRecent(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === 'string' && x.length > 0).slice(0, RECENT_MAX) : []
}

/** `path` first, without duplicates, at most RECENT_MAX. */
export function addRecent(list: readonly string[], path: string): string[] {
  return [path, ...list.filter((p) => p !== path)].slice(0, RECENT_MAX)
}

export function loadRecent(): string[] {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(RECENT_KEY) : null
    return raw ? parseRecent(JSON.parse(raw)) : []
  } catch {
    return []
  }
}

export function saveRecent(list: string[]): void {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  } catch {
    /* blocked storage: no recent list */
  }
}

/** Last path component ("…/mouse_brain.chromdata.zarr" -> "mouse_brain.chromdata.zarr"). */
export const baseName = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? p

/**
 * Datasets named by `?open=<url>` in the page address (an atlas page links here): only remote
 * `.chromdata.zarr` stores (http, https, s3, gs), each once.  A link may not make the server read anything else.
 */
export function openParams(search: string): string[] {
  const out: string[] = []
  for (const v of new URLSearchParams(search).getAll('open')) {
    const u = v.trim().replace(/\/+$/, '')
    if (/^(https?|s3|gs):\/\/[^\s]+\.chromdata\.zarr$/i.test(u) && !out.includes(u)) out.push(u)
  }
  return out
}
