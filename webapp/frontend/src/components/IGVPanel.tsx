import React, { useEffect, useRef, useState } from 'react'
import igv from 'igv'
import { useAppStore } from '../store'

const IGVPanel: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null)
  const browserRef = useRef<any>(null)
  const [isLoaded, setIsLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const viewport = useAppStore(s => s.viewport)
  const setViewport = useAppStore(s => s.setViewport)

  // Track if the locus change originated from IGV (to avoid feedback loop)
  const updatingFromStore = useRef(false)

  useEffect(() => {
    if (!containerRef.current) return
    let mounted = true

    const initIGV = async () => {
      try {
        const config = {
          genome: 'hg19',
          locus: 'chr21',
          tracks: [
            {
              type: 'wig',
              name: 'ATAC',
              url: '/api/track_wig/atac',
            },
          ],
        }

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const browser = await igv.createBrowser(containerRef.current!, config as any)
        if (!mounted) return

        browserRef.current = browser
        setIsLoaded(true)

        browser.on('locuschange', (referenceFrame: any) => {
          if (!referenceFrame || !referenceFrame.length) return
          const frame = Array.isArray(referenceFrame) ? referenceFrame[0] : referenceFrame
          const chrom: string = frame.chr || frame.chrom || ''
          const start: number = Math.floor(frame.start ?? 0)
          const end: number = Math.ceil(frame.end ?? start + 1000000)
          if (chrom) {
            updatingFromStore.current = false
            setViewport({ chrom, start, end })
          }
        })
      } catch (err: any) {
        if (mounted) {
          console.error('IGV initialization failed:', err)
          setError(err.message || 'Failed to initialize IGV browser')
        }
      }
    }

    initIGV()

    return () => {
      mounted = false
      if (browserRef.current) {
        try {
          browserRef.current.remove?.()
        } catch (e) {
          // ignore cleanup errors
        }
        browserRef.current = null
      }
    }
  }, []) // Only init once

  // Navigate IGV when Zustand viewport changes (from external source)
  useEffect(() => {
    if (!browserRef.current || !isLoaded) return
    if (updatingFromStore.current) return
    updatingFromStore.current = true
    const { chrom, start, end } = viewport
    try {
      browserRef.current.search(`${chrom}:${start}-${end}`)
    } catch (e) {
      console.warn('IGV search failed:', e)
    } finally {
      // Reset flag after a tick to allow next locuschange to propagate
      setTimeout(() => { updatingFromStore.current = false }, 200)
    }
  }, [viewport, isLoaded])

  if (error) {
    return (
      <div style={{
        width: '100%', height: '100%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#1a1a2e', color: '#ff6b6b',
        flexDirection: 'column', gap: 8,
      }}>
        <div style={{ fontSize: 14, fontWeight: 'bold' }}>IGV Browser Error</div>
        <div style={{ fontSize: 12, opacity: 0.8 }}>{error}</div>
        <div style={{ fontSize: 11, opacity: 0.6 }}>
          Check that the backend is running and track data is available
        </div>
      </div>
    )
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {!isLoaded && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#1a1a2e', color: '#888', fontSize: 13, zIndex: 10,
        }}>
          Loading IGV Browser...
        </div>
      )}
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', background: '#1a1a2e' }}
      />
    </div>
  )
}

export default IGVPanel
