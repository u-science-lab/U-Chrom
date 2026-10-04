import { decodeMatrix, type MatrixData } from './matrix'
import type { AtlasResponse, FileListing, FilePlace, IntervalTable, RgStats, ScalingStats, TrackData, CellDetails, CellPage, CellValues, DatasetSummary, Embedding, Geometry, GeometryHeader, LayerFilter, PointSet, PointSetPayload, SpatialPoints, StoreNode, TracePage } from './types'

async function fetchChecked(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body && body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res
}

/** GETs in flight, by URL: panes asking for the same thing at once (e.g. the same cell field) share one request. */
const inflight = new Map<string, Promise<Response>>()

async function request(url: string, init?: RequestInit): Promise<Response> {
  const isGet = !init || ((init.method ?? 'GET') === 'GET' && !init.signal)
  if (!isGet) return fetchChecked(url, init)
  let p = inflight.get(url)
  if (!p) {
    p = fetchChecked(url, init).finally(() => inflight.delete(url))
    inflight.set(url, p)
  }
  return (await p).clone() // each caller reads its own copy of the body
}

export async function fetchHealth(): Promise<{ status: string; version: string; bundle?: string | null }> {
  return (await request('api/health')).json()
}

export async function listDatasets(): Promise<DatasetSummary[]> {
  return (await request('api/datasets')).json()
}

export async function openDataset(path: string): Promise<DatasetSummary> {
  const res = await request('api/datasets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return res.json()
}

/** A server directory for the Open dataset dialog (null: the server's working directory). */
export async function listFiles(path: string | null, hidden = false): Promise<FileListing> {
  const q = new URLSearchParams()
  if (path) q.set('path', path)
  if (hidden) q.set('hidden', 'true')
  return (await request(`api/files?${q}`)).json()
}

export async function filePlaces(): Promise<FilePlace[]> {
  return (await request('api/files/places')).json()
}

/** The atlas catalog the server is configured with (`root: null` when none). */
export async function fetchAtlas(refresh = false): Promise<AtlasResponse> {
  return (await request(`api/atlas${refresh ? '?refresh=true' : ''}`)).json()
}

export async function closeDataset(id: string): Promise<void> {
  await request(`api/datasets/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export async function listTraces(
  id: string,
  opts: { chrom?: string; offset?: number; limit?: number } = {},
): Promise<TracePage> {
  const q = new URLSearchParams()
  if (opts.chrom) q.set('chrom', opts.chrom)
  q.set('offset', String(opts.offset ?? 0))
  q.set('limit', String(opts.limit ?? 500))
  return (await request(`api/datasets/${encodeURIComponent(id)}/traces?${q}`)).json()
}

export async function listCells(id: string, opts: { offset?: number; limit?: number } = {}): Promise<CellPage> {
  const q = new URLSearchParams({ offset: String(opts.offset ?? 0), limit: String(opts.limit ?? 500) })
  return (await request(`api/datasets/${encodeURIComponent(id)}/cells?${q}`)).json()
}

export async function fetchCellValues(id: string, field: string): Promise<CellValues> {
  const q = new URLSearchParams({ field })
  return (await request(`api/datasets/${encodeURIComponent(id)}/cell_values?${q}`)).json()
}

export async function fetchCellInfo(id: string, cellId: string): Promise<CellDetails> {
  const q = new URLSearchParams({ cell_id: cellId })
  return (await request(`api/datasets/${encodeURIComponent(id)}/cell_info?${q}`)).json()
}

export async function fetchEmbedding(id: string, key: string, dims: [number, number]): Promise<Embedding> {
  const q = new URLSearchParams({ dims: `${dims[0]},${dims[1]}` })
  return (await request(`api/datasets/${encodeURIComponent(id)}/embedding/${encodeURIComponent(key)}?${q}`)).json()
}

export async function fetchSpatial(id: string, key: string, region: string | null): Promise<SpatialPoints> {
  const q = region !== null ? `?${new URLSearchParams({ region })}` : ''
  return (await request(`api/datasets/${encodeURIComponent(id)}/spatial/${encodeURIComponent(key)}${q}`)).json()
}

/** URL of a linked image (a region's tissue image). */
export const imageUrl = (id: string, name: string) => `api/datasets/${encodeURIComponent(id)}/images/${encodeURIComponent(name)}`

export async function fetchPointSet(id: string, name: string): Promise<PointSet> {
  const res = await request(`api/datasets/${encodeURIComponent(id)}/points/${encodeURIComponent(name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  return decodePointSet(name, await res.json())
}

/** JSON point payload → typed arrays; null positions become NaN (never drawn). */
export function decodePointSet(name: string, p: PointSetPayload): PointSet {
  if (p.positions.length !== 3 * p.n || p.cell_ids.length !== p.n || p.labels.length !== p.n) {
    throw new Error(`point set ${name}: inconsistent lengths`)
  }
  return {
    name,
    n: p.n,
    positions: Float32Array.from(p.positions, (v) => (v === null ? NaN : v)),
    cellIds: p.cell_ids.map((c) => (c === null ? null : String(c))),
    labels: p.labels.map((l) => (l === null ? '' : String(l))),
    values: p.values ?? {},
  }
}

export async function fetchGeometry(
  id: string,
  filter: LayerFilter,
  maxPoints?: number,
): Promise<Geometry> {
  const body: Record<string, unknown> = { ...filter }
  if (maxPoints !== undefined) body.max_points = maxPoints
  const res = await request(`api/datasets/${encodeURIComponent(id)}/geometry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return decodeGeometry(await res.arrayBuffer())
}

/**
 * Decode the binary geometry payload (API.md, "Geometry (binary)"):
 * uint32 H | H bytes JSON header | float32[3N] | uint32[N] | uint32[S+1].
 */
export function decodeGeometry(buf: ArrayBuffer): Geometry {
  if (buf.byteLength < 4) throw new Error('geometry payload too short')
  const headerLen = new DataView(buf).getUint32(0, true)
  if (headerLen % 4 !== 0) throw new Error(`header length ${headerLen} is not a multiple of 4`)
  const headerBytes = new Uint8Array(buf, 4, headerLen)
  const header = JSON.parse(new TextDecoder().decode(headerBytes)) as GeometryHeader
  const n = header.n_points
  const s = header.n_segments
  let off = 4 + headerLen
  const expected = off + 12 * n + 4 * n + 4 * (s + 1)
  if (buf.byteLength !== expected) {
    throw new Error(`geometry payload is ${buf.byteLength} bytes, expected ${expected}`)
  }
  const positions = new Float32Array(buf, off, 3 * n)
  off += 12 * n
  const starts = new Uint32Array(buf, off, n)
  off += 4 * n
  const offsets = new Uint32Array(buf, off, s + 1)
  return { header, positions, starts, offsets }
}

// ---- genome-coordinate views (API.md "Genome-coordinate views") ----------

const ds = (id: string) => `api/datasets/${encodeURIComponent(id)}`

// ---- cell groups (API.md "Cell groups") ----------------------------------

export interface GroupRegistration {
  id: string
  name: string | null
  n_cells: number
  n_unknown: number
}

export async function registerGroup(id: string, cells: string[], name?: string | null): Promise<GroupRegistration> {
  const res = await request(`${ds(id)}/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cells, name: name ?? null }),
  })
  return res.json()
}

export async function fetchGroupCells(id: string, group: string): Promise<{ group: string; name: string | null; n_cells: number; cells: string[] }> {
  return (await request(`${ds(id)}/group_cells${query({ group })}`)).json()
}

/**
 * Registered-group lookup for requests: a saved / selected group lives in
 * the browser; the server learns it on first use (after a restart too).
 * Set by the store: (dataset id, ref) → the group's cells, or null.
 */
let groupCellsOf: (datasetId: string, ref: string) => string[] | null = () => null
export function setGroupResolver(f: typeof groupCellsOf) {
  groupCellsOf = f
}
const registered = new Map<string, Promise<string>>()

/**
 * The group parameter to send: field groups as they are; other refs are
 * registered once per (dataset, ref) — the server answers with the id to use.
 */
export async function groupParam(datasetId: string, ref: string | null | undefined): Promise<string | null> {
  if (!ref) return null
  if (ref.startsWith('field:')) return ref
  const key = `${datasetId}\u0000${ref}`
  let p = registered.get(key)
  if (!p) {
    const cells = groupCellsOf(datasetId, ref)
    if (!cells) return ref // unknown here: let the server say 404
    p = registerGroup(datasetId, cells).then((r) => r.id)
    p.catch(() => registered.delete(key))
    registered.set(key, p)
  }
  return p
}

/** Forget registrations (tests; a dataset re-opened under the same id). */
export function resetGroupRegistrations() {
  registered.clear()
}

/** Build a query string, dropping null / undefined / '' values. */
/** Genomic coordinates the server takes as integers (bp). */
const BP_PARAMS = new Set(['start', 'end'])

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue
    // a window moved by the wheel / a drag can be fractional: the server wants whole bp
    q.set(k, BP_PARAMS.has(k) && typeof v === 'number' ? String(Math.round(v)) : String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

export interface RegionQuery {
  chrom: string
  start?: number
  end?: number
}

/** The store's on-disk structure (groups, arrays, Parquet tables, sizes). */
export async function fetchStore(id: string): Promise<StoreNode> {
  return (await request(`${ds(id)}/store`)).json()
}

export async function fetchTracks(
  id: string,
  names: string[],
  r: RegionQuery,
  opts: { cellId?: string | null; agg?: string; group?: string | null } = {},
): Promise<TrackData> {
  const group = await groupParam(id, opts.group)
  const q = query({ names: names.join(','), chrom: r.chrom, start: r.start, end: r.end, cell_id: opts.cellId, agg: opts.agg, group })
  return (await request(`${ds(id)}/tracks${q}`)).json()
}

export async function fetchIntervals(id: string, key: string, r: RegionQuery): Promise<IntervalTable> {
  return (await request(`${ds(id)}/intervals/${encodeURIComponent(key)}${query({ chrom: r.chrom, start: r.start, end: r.end })}`)).json()
}

export async function fetchContacts(
  id: string,
  key: string,
  r: RegionQuery,
  opts: { resolution?: number | null; balance?: boolean; cell?: string | null; group?: string | null } = {},
): Promise<MatrixData> {
  const group = await groupParam(id, opts.group)
  const q = query({ chrom: r.chrom, start: r.start, end: r.end, resolution: opts.resolution, balance: opts.balance ? 'true' : 'false', cell: opts.cell, group })
  return decodeMatrix(await (await request(`${ds(id)}/contacts/${encodeURIComponent(key)}${q}`)).arrayBuffer())
}

export async function fetchDistance(
  id: string,
  r: RegionQuery,
  opts: { cellId?: string | null; traceId?: string | null; stat?: string; threshold?: number | null; group?: string | null } = {},
): Promise<MatrixData> {
  const group = await groupParam(id, opts.group)
  const q = query({ chrom: r.chrom, start: r.start, end: r.end, cell_id: opts.cellId, trace_id: opts.traceId, stat: opts.stat, threshold: opts.threshold, group })
  return decodeMatrix(await (await request(`${ds(id)}/distance${q}`)).arrayBuffer())
}

export async function fetchRg(id: string, opts: { chrom?: string | null; cellId?: string | null; group?: string | null } = {}): Promise<RgStats> {
  const group = await groupParam(id, opts.group)
  return (await request(`${ds(id)}/stats/rg${query({ chrom: opts.chrom, cell_id: opts.cellId, group })}`)).json()
}

export async function fetchScaling(id: string, opts: { chrom?: string | null; cellId?: string | null; group?: string | null } = {}): Promise<ScalingStats> {
  const group = await groupParam(id, opts.group)
  return (await request(`${ds(id)}/stats/scaling${query({ chrom: opts.chrom, cell_id: opts.cellId, group })}`)).json()
}
