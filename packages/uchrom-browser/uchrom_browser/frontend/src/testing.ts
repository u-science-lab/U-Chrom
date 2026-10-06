import type { GeometryHeader } from './types'

/** Build a geometry payload exactly as the server encodes it (API.md). */
export function encodeGeometry(
  header: Omit<GeometryHeader, 'n_points' | 'n_segments'>,
  positions: number[],
  starts: number[],
  offsets: number[],
): ArrayBuffer {
  const full: GeometryHeader = { ...header, n_points: starts.length, n_segments: offsets.length - 1 }
  let json = new TextEncoder().encode(JSON.stringify(full))
  const pad = (4 - (json.length % 4)) % 4
  if (pad) {
    const padded = new Uint8Array(json.length + pad)
    padded.set(json)
    padded.fill(0x20, json.length)
    json = padded
  }
  const n = starts.length
  const buf = new ArrayBuffer(4 + json.length + 12 * n + 4 * n + 4 * offsets.length)
  new DataView(buf).setUint32(0, json.length, true)
  new Uint8Array(buf, 4, json.length).set(json)
  let off = 4 + json.length
  new Float32Array(buf, off, 3 * n).set(positions)
  off += 12 * n
  new Uint32Array(buf, off, n).set(starts)
  off += 4 * n
  new Uint32Array(buf, off, offsets.length).set(offsets)
  return buf
}

export function sampleHeader(): Omit<GeometryHeader, 'n_points' | 'n_segments'> {
  return {
    total_points: 5,
    truncated: false,
    segments: [
      { trace_id: 't1', chrom: 'chr1', cell_id: 'c1', n_points: 3, start: 0, end: 300 },
      { trace_id: 't2', chrom: 'chr1', cell_id: null, n_points: 2, start: 100, end: 300 },
    ],
    bbox: { min: [0, 0, 0], max: [3, 4, 0] },
    chrom_extent: { chr1: [0, 400] },
  }
}
