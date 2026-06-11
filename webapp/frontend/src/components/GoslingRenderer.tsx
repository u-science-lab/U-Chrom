import { useRef, useEffect } from 'react'
import { GoslingComponent } from 'gosling.js'
import { useAppStore } from '../store'

interface GoslingRendererProps {
  spec: object
}

// Use any for the ref since GoslingRef types may vary across versions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyGoslingRef = any

export default function GoslingRenderer({ spec }: GoslingRendererProps) {
  const gosRef = useRef<AnyGoslingRef>(null)
  const { viewport, setViewport } = useAppStore()
  const exportRequest = useAppStore((s) => s.exportRequest)
  const suppressingRef = useRef(false)
  const lastExportRef = useRef<number>(0)

  // Subscribe to location changes from Gosling → sync to store
  // Gosling ref is populated after render, so we use a callback ref pattern:
  // subscribe on mount via a short retry loop until the API is available
  useEffect(() => {
    let cancelled = false
    let retries = 0
    const maxRetries = 20  // up to 2 seconds

    function trySubscribe() {
      if (cancelled) return
      const gos = gosRef.current
      if (!gos || typeof gos.subscribe !== 'function') {
        if (retries++ < maxRetries) {
          setTimeout(trySubscribe, 100)
        }
        return
      }
      try {
        gos.subscribe('location', (_: string, data: { genomicRange?: Array<{ chromosome: string; position: number }> }) => {
          if (suppressingRef.current) return
          const range = data.genomicRange
          if (range && range.length >= 2) {
            setViewport({
              chrom: range[0].chromosome,
              start: range[0].position,
              end: range[1].position,
            }, true) // notify agent of user's manual pan/zoom
          }
        })
      } catch {
        // Gosling may not support subscribe in this version
      }
    }

    trySubscribe()

    return () => {
      cancelled = true
      try { gosRef.current?.unsubscribe?.('location') } catch { /* ignore */ }
    }
  }, [setViewport])

  // Sync store viewport → Gosling when viewport changes externally
  useEffect(() => {
    const gos = gosRef.current
    if (!gos) return
    try {
      const ids = gos.getViewIds?.()
      if (!ids || ids.length === 0) return
      suppressingRef.current = true
      gos.zoomTo(ids[0], `${viewport.chrom}:${viewport.start}-${viewport.end}`, 0, 400)
      setTimeout(() => { suppressingRef.current = false }, 500)
    } catch {
      // Gosling may not be mounted yet
    }
  }, [viewport.chrom, viewport.start, viewport.end])

  // Respond to export requests (from agent export_view or manual Export button).
  // The Gosling ref exposes exportPng/exportPdf in v0.9.x (top-level on the API
  // object); guard each so a version mismatch degrades gracefully.
  useEffect(() => {
    if (!exportRequest || exportRequest.id === lastExportRef.current) return
    lastExportRef.current = exportRequest.id
    const gos = gosRef.current
    if (!gos) return
    try {
      if (exportRequest.format === 'pdf') {
        if (typeof gos.exportPdf === 'function') gos.exportPdf()
        else if (typeof gos.api?.exportPdf === 'function') gos.api.exportPdf()
      } else {
        if (typeof gos.exportPng === 'function') gos.exportPng()
        else if (typeof gos.api?.exportPng === 'function') gos.api.exportPng()
      }
    } catch {
      // Export API not available in this Gosling version
    }
  }, [exportRequest])

  return (
    <div className="w-full h-full overflow-auto bg-white">
      <GoslingComponent
        ref={gosRef}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        spec={spec as any}
        padding={0}
        theme={{
          base: 'light',
          root: {
            background: '#ffffff',
            titleColor: '#1f2937',
          }
        }}
      />
    </div>
  )
}
