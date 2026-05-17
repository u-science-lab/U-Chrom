import { useEffect, useRef } from 'react'
import embed, { VisualizationSpec } from 'vega-embed'
import { useAppStore } from '../store'
import PanelContainer from './PanelContainer'

interface Props {
  tracks?: string[]
}

export default function TrackPlot({ tracks = ['H3K27me3'] }: Props) {
  const { viewport, setViewport } = useAppStore()
  const containerRefs = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    const { chrom, start, end } = viewport

    tracks.forEach((name, i) => {
      const el = containerRefs.current[i]
      if (!el) return

      fetch(`/api/track/${name}?chrom=${chrom}&start=${start}&end=${end}&resolution=1000`)
        .then(r => r.arrayBuffer())
        .then(buf => {
          const floats = new Float32Array(buf)
          const values = Array.from(floats).map((value, j) => ({
            pos: start + (j / (floats.length - 1)) * (end - start),
            value,
          }))

          const spec: VisualizationSpec = {
            $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
            width: 'container' as const,
            height: 80,
            data: { values },
            mark: 'area' as const,
            params: [{ name: 'brush', select: { type: 'interval', encodings: ['x'] } }],
            encoding: {
              x: { field: 'pos', type: 'quantitative', axis: { title: null } },
              y: { field: 'value', type: 'quantitative', axis: { title: name } },
              opacity: { condition: { param: 'brush', value: 1 }, value: 0.3 },
            },
          }

          embed(el, spec, { actions: false, renderer: 'svg' }).then(result => {
            result.view.addSignalListener('brush', (_name: string, value: { pos?: [number, number] }) => {
              if (value.pos) {
                setViewport({ chrom, start: Math.round(value.pos[0]), end: Math.round(value.pos[1]) })
              }
            })
          })
        })
        .catch(() => {})
    })
  }, [viewport, tracks, setViewport])

  return (
    <PanelContainer title="Track Plot">
      <div style={{ overflowY: 'auto', height: '100%', padding: 8, boxSizing: 'border-box' }}>
        {tracks.map((name, i) => (
          <div key={name} style={{ marginBottom: 8 }}>
            <div
              ref={el => { containerRefs.current[i] = el }}
              style={{ width: '100%' }}
            />
          </div>
        ))}
      </div>
    </PanelContainer>
  )
}
