import { decodeMatrix, type MatrixData } from './matrix'
import type { IntervalTable, RgStats, ScalingStats, TrackData, CellDetails, CellPage, CellValues, DatasetSummary, Embedding, Geometry, GeometryHeader, LayerFilter, PointSet, PointSetPayload, TracePage } from './types'

async function request(url: string, init?: RequestInit): Promise<Response> {
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

/** Build a query string, dropping null / undefined / '' values. */
function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

export interface RegionQuery {
  chrom: string
  start?: number
  end?: number
}

export async function fetchTracks(
  id: string,
  names: string[],
  r: RegionQuery,
  opts: { cellId?: string | null; agg?: string } = {},
): Promise<TrackData> {
  const q = query({ names: names.join(','), chrom: r.chrom, start: r.start, end: r.end, cell_id: opts.cellId, agg: opts.agg })
  return (await request(`${ds(id)}/tracks${q}`)).json()
}

export async function fetchIntervals(id: string, key: string, r: RegionQuery): Promise<IntervalTable> {
  return (await request(`${ds(id)}/intervals/${encodeURIComponent(key)}${query({ chrom: r.chrom, start: r.start, end: r.end })}`)).json()
}

export async function fetchContacts(
  id: string,
  key: string,
  r: RegionQuery,
  opts: { resolution?: number | null; balance?: boolean; cell?: string | null } = {},
): Promise<MatrixData> {
  const q = query({ chrom: r.chrom, start: r.start, end: r.end, resolution: opts.resolution, balance: opts.balance ? 'true' : 'false', cell: opts.cell })
  return decodeMatrix(await (await request(`${ds(id)}/contacts/${encodeURIComponent(key)}${q}`)).arrayBuffer())
}

export async function fetchDistance(
  id: string,
  r: RegionQuery,
  opts: { cellId?: string | null; traceId?: string | null; stat?: string; threshold?: number | null } = {},
): Promise<MatrixData> {
  const q = query({ chrom: r.chrom, start: r.start, end: r.end, cell_id: opts.cellId, trace_id: opts.traceId, stat: opts.stat, threshold: opts.threshold })
  return decodeMatrix(await (await request(`${ds(id)}/distance${q}`)).arrayBuffer())
}

export async function fetchRg(id: string, opts: { chrom?: string | null; cellId?: string | null } = {}): Promise<RgStats> {
  return (await request(`${ds(id)}/stats/rg${query({ chrom: opts.chrom, cell_id: opts.cellId })}`)).json()
}

export async function fetchScaling(id: string, opts: { chrom?: string | null; cellId?: string | null } = {}): Promise<ScalingStats> {
  return (await request(`${ds(id)}/stats/scaling${query({ chrom: opts.chrom, cell_id: opts.cellId })}`)).json()
}
