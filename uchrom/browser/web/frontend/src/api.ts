import type { CellDetails, CellPage, CellValues, DatasetSummary, PointSet, PointSetPayload, Geometry, GeometryHeader, LayerFilter, TracePage } from './types'

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
