import type { CellPage, DatasetSummary, Geometry, GeometryHeader, LayerFilter, TracePage } from './types'

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
