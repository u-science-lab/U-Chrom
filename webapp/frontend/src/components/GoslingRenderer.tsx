import { useRef, useEffect, useMemo } from 'react'
import { GoslingComponent, validateGoslingSpec } from 'gosling.js'
import { useAppStore } from '../store'
import { ws } from '../ws'
import { sanitizeUrls } from '../urlSafety'
import { registerCapturer } from '../snapshot'
import { reportViewDiagnostic } from '../diagnostics'

interface GoslingRendererProps {
  spec: object
}

// Use any for the ref since GoslingRef types may vary across versions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyGoslingRef = any

export default function GoslingRenderer({ spec }: GoslingRendererProps) {
  const gosRef = useRef<AnyGoslingRef>(null)
  // Fallback URL safety net: scrub agent-controlled data.url fields before the
  // spec reaches Gosling (which would otherwise fetch them). The backend
  // already sanitizes at emit; this guards stale snapshots / reconnect paths.
  const safeSpec = useMemo(() => sanitizeUrls(spec), [spec])
  const { viewport, setViewport } = useAppStore()
  const exportRequest = useAppStore((s) => s.exportRequest)
  const suppressingRef = useRef(false)
  const lastExportRef = useRef<number>(0)

  // Validate the spec with Gosling's own schema validator and feed any failure
  // back to the agent (view.diagnostic). A bad spec usually renders empty
  // WITHOUT throwing a React error, so the ErrorBoundary alone wouldn't catch
  // it — this surfaces "画崩了" to the agent via get_view_state so it can fix
  // and re-render. Keyed on the active view id so the diagnostic lands there.
  useEffect(() => {
    const viewId = useAppStore.getState().activeGoslingSpecId
    if (!viewId) return
    try {
      const result = validateGoslingSpec(safeSpec as never)
      if (result && result.state === 'error') {
        const msgs = Array.isArray(result.message)
          ? result.message.join('; ')
          : String(result.message ?? 'invalid Gosling spec')
        reportViewDiagnostic({
          view_id: viewId,
          level: 'error',
          source: 'gosling-spec',
          message: `Gosling spec validation failed: ${msgs}`.slice(0, 1000),
        })
      }
    } catch (e) {
      // Validator threw — report it too rather than silently swallow.
      reportViewDiagnostic({
        view_id: viewId,
        level: 'warning',
        source: 'gosling-spec',
        message: `Gosling spec validation error: ${e instanceof Error ? e.message : String(e)}`,
      })
    }
  }, [safeSpec])

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
            // Report the interaction to the backend view state so the agent
            // can SEE the region the user navigated to (state round-trip).
            const viewId = useAppStore.getState().activeGoslingSpecId
            if (viewId) {
              // If the agent is currently blocking on query_user_interaction,
              // echo its interaction_id so the backend resolves that exact
              // waiter (AG-UI round-trip); otherwise just report the brush.
              const pendingId = useAppStore.getState().pendingInteractionId
              ws.send('ui_event', {
                source_view_id: viewId,
                event_name: 'brush_selection',
                ...(pendingId ? { interaction_id: pendingId } : {}),
                payload: {
                  chrom: range[0].chromosome,
                  start: range[0].position,
                  end: range[1].position,
                },
              })
            }
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

  // Register the snapshot capturer for capture_view_snapshot ('genomic' view).
  // Gosling's API exposes getCanvas() which composites the rendered tracks into
  // an HTMLCanvasElement we can read as PNG. Retry briefly because the API ref
  // populates a moment after mount.
  useEffect(() => {
    return registerCapturer('genomic', async () => {
      const tryGetCanvas = (): string | null => {
        const gos = gosRef.current
        const getCanvas = gos?.getCanvas ?? gos?.api?.getCanvas
        if (typeof getCanvas !== 'function') return null
        try {
          const res = getCanvas.call(gos, { resolution: 2, transparentBackground: false })
          const canvas: HTMLCanvasElement | undefined = res?.canvas
          if (canvas && typeof canvas.toDataURL === 'function') {
            return canvas.toDataURL('image/png')
          }
        } catch {
          // fall through to retry / DOM fallback
        }
        return null
      }
      // Retry up to ~3s for the Gosling API to be ready.
      for (let i = 0; i < 30; i++) {
        const url = tryGetCanvas()
        if (url) return url
        await new Promise(r => setTimeout(r, 100))
      }
      throw new Error('Gosling canvas not available')
    })
  }, [])

  return (
    <div className="w-full h-full overflow-auto bg-white">
      <GoslingComponent
        ref={gosRef}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        spec={safeSpec as any}
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
