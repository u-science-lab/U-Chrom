const RDBU: [number, number, number][] = [
  [5, 48, 97], [33, 102, 172], [67, 147, 195], [146, 197, 222], [209, 229, 240],
  [247, 247, 247], [253, 219, 199], [244, 165, 130], [214, 96, 77], [178, 24, 43], [103, 0, 31],
]

function rdbu(t: number): [number, number, number] {
  const clamped = Math.max(0, Math.min(1, t))
  const pos = clamped * 10
  const lo = Math.floor(pos)
  const hi = Math.min(10, lo + 1)
  const f = pos - lo
  const [r0, g0, b0] = RDBU[lo]
  const [r1, g1, b1] = RDBU[hi]
  return [r0 + f * (r1 - r0), g0 + f * (g1 - g0), b0 + f * (b1 - b0)]
}

self.onmessage = (e: MessageEvent<{ matrix: Float32Array; n: number; colormap: 'RdBu' }>) => {
  const { matrix, n } = e.data
  let maxAbs = 0
  for (let i = 0; i < matrix.length; i++) {
    const a = Math.abs(matrix[i])
    if (a > maxAbs) maxAbs = a
  }

  const pixels = new Uint8ClampedArray(n * n * 4)
  for (let i = 0; i < n * n; i++) {
    const t = maxAbs === 0 ? 0.5 : (matrix[i] / maxAbs) * 0.5 + 0.5
    const [r, g, b] = rdbu(t)
    pixels[i * 4] = r
    pixels[i * 4 + 1] = g
    pixels[i * 4 + 2] = b
    pixels[i * 4 + 3] = 255
  }

  postMessage({ pixels: pixels.buffer, n, maxAbs }, { transfer: [pixels.buffer] })
}
