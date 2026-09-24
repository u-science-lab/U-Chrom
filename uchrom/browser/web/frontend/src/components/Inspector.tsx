import { useEffect } from 'react'
import { ensureActivePane, inspectorSections, paneTitle, type DatasetFacts } from '../inspector'
import { hasCoords, useStore } from '../store'
import { ChromLegend } from './ChromLegend'
import { EmbeddingControls } from './EmbeddingView'
import { GenomeInspector } from './GenomeView'
import { LayerPanel } from './LayerPanel'
import { MatrixControls } from './MatrixView'
import { OperationsPanel } from './OperationsPanel'
import { PaneCellControl } from './PaneCell'
import { PointsPanel } from './PointsPanel'
import { StyleSection } from './PropertiesPanel'
import { StatsControls } from './StatsView'

/** What the active dataset offers, as plain facts for the section helpers. */
export function useDatasetFacts(): DatasetFacts | null {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const nCells = useStore((s) => ((s.activeDatasetId && s.cells[s.activeDatasetId]) || []).length)
  if (!ds) return null
  return { hasCoords: hasCoords(ds), nCells, nChroms: ds.chroms.length, nPointSets: ds.point_sets?.length ?? 0 }
}

/**
 * Right side bar = inspector of the ACTIVE pane: its title, pin state and
 * the settings of that kind of view (3-D: layers, subsets, style,
 * chromosomes, points; Genome: rows; Matrix / Embedding / Stats: inputs).
 */
export function Inspector() {
  const ws = useStore((s) => s.workspace)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const facts = useDatasetFacts()
  const layer = useStore((s) => s.layers.find((l) => l.id === s.selectedLayerId))
  // a workspace always has an active pane
  useEffect(() => setWorkspace(ensureActivePane), [ws.activePane, ws.panes, setWorkspace])
  const pane = ws.panes.find((p) => p.id === ws.activePane) ?? ws.panes[0]
  if (!pane) return <aside className="props panel inspector" />
  const sections = new Set(inspectorSections(pane, facts))
  return (
    <aside className="props panel inspector" key={pane.id}>
      <div className="insp-title">
        <span>{paneTitle(ws, pane)}</span>
        <span className="muted small">inspector</span>
      </div>
      {sections.has('pin') && (
        <div className="insp-pin">
          <PaneCellControl pane={pane} />
        </div>
      )}
      {sections.has('noCoords') && <p className="muted small">This dataset has no 3-D coordinates — use a Genome, Matrix or Embedding view.</p>}
      {sections.has('layers') && <LayerPanel />}
      {sections.has('subset') && <OperationsPanel />}
      {sections.has('style') &&
        (layer ? (
          <StyleSection layer={layer} hasCells={(facts?.nCells ?? 0) > 1} />
        ) : (
          <>
            <h2>Style</h2>
            <p className="muted">Select a layer.</p>
          </>
        ))}
      {sections.has('chroms') && <ChromLegend />}
      {sections.has('points') && <PointsPanel />}
      {sections.has('genomeRows') && <GenomeInspector pane={pane} />}
      {sections.has('matrix') && (
        <section className="insp-controls">
          <h2>Matrix</h2>
          <MatrixControls pane={pane} />
        </section>
      )}
      {sections.has('embedding') && (
        <section className="insp-controls">
          <h2>Embedding</h2>
          <EmbeddingControls pane={pane} />
        </section>
      )}
      {sections.has('stats') && (
        <section className="insp-controls">
          <h2>Chart</h2>
          <StatsControls pane={pane} />
        </section>
      )}
    </aside>
  )
}
