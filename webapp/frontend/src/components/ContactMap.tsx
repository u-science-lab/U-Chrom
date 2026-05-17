import { useEffect, useRef } from 'react'
import { useAppStore } from '../store'
import PanelContainer from './PanelContainer'

const RDBU: [number, number, number][] = [
  [5, 48, 97], [33, 102, 172], [67, 147, 195], [146, 197, 222], [209, 229, 240],
  [247, 247, 247], [253, 219, 199], [244, 165, 130], [214, 96, 77], [178, 24, 43], [103, 0, 31],
]

const COLORBAR_H = 200
const COLORBAR_W = 16

export default function ContactMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const colorbarRef = useRef<HTMLCanvasElement>(null)
  const workerRef = useRef<Worker | null>(null)
  const maxAbsRef = useRef(0)
  const { viewport, cellSelection } = useAppStore()

  // Draw colorbar once
  useEffect(() => {
    const cb = colorbarRef.current
    if (!cb) return
    const ctx = cb.getContext('2d')!
    for (let y = 0; y < COLORBAR_H; y++) {
      const t = 1 - y / (COLORBAR_H - 1)
      const pos = t * 10
      const lo = Math.floor(pos)
      const hi = Math.min(10, lo + 1)
      const f = pos - lo
      const [r0, g0, b0] = RDBU[lo]
      const [r1, g1, b1] = RDBU[hi]
      const r = r0 + f * (r1 - r0), g = g0 + f * (g1 - g0), b = b0 + f * (b1 - b0)
      ctx.fillStyle = `rgb(${r},${g},${b})`
      ctx.fillRect(0, y, COLORBAR_W, 1)
    }
  }, [])

  useEffect(() => {
    workerRef.current = new Worker(
      new URL('../workers/contactMap.worker.ts', import.meta.url),
      { type: 'module' }
    )
    workerRef.current.onmessage = (e: MessageEvent<{ imageData: ImageData; maxAbs: number }>) => {
      const { imageData, maxAbs } = e.data
      maxAbsRef.current = maxAbs
      const canvas = canvasRef.current
      if (!canvas) return
      canvas.width = imageData.width
      canvas.height = imageData.height
      canvas.getContext('2d')!.putImageData(imageData, 0, 0)
    }
    return () => { workerRef.current?.terminate() }
  }, [])

  useEffect(() => {
    const { chrom, start, end } = viewport
    const params = new URLSearchParams({ start: String(start), end: String(end) })
    if (cellSelection.mode === 'cell_type' && cellSelection.label) {
      params.set('cell_type', cellSelection.label)
    }
    fetch(`/api/contact/${chrom}?${params}`)
      .then(r => r.arrayBuffer())
      .then(buf => {
        const matrix = new Float32Array(buf)
        const n = Math.round(Math.sqrt(matrix.length))
        workerRef.current?.postMessage({ matrix, n, colormap: 'RdBu' }, [matrix.buffer])
      })
      .catch(() => {})
  }, [viewport, cellSelection])

  return (
    <PanelContainer title="Contact Map">
      <div style={{ display: 'flex', height: '100%', padding: 8, gap: 8, boxSizing: 'border-box' }}>
        <canvas
          ref={canvasRef}
          style={{ flex: 1, minWidth: 0, imageRendering: 'pixelated', width: '100%', height: '100%', objectFit: 'contain' }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          <span style={{ fontSize: 10, color: '#a6adc8' }}>+max</span>
          <canvas ref={colorbarRef} width={COLORBAR_W} height={COLORBAR_H} style={{ border: '1px solid #313244' }} />
          <span style={{ fontSize: 10, color: '#a6adc8' }}>-max</span>
        </div>
      </div>
    </PanelContainer>
  )
}
