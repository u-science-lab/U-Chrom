import { Fragment, useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import {
  addPane,
  dropUnknownPins,
  handleWorkspaceKey,
  LAYOUTS,
  moveSplitter,
  normalizeSizes,
  PANE_LABEL,
  PANE_TYPES,
  removePane,
  retypePane,
  setLayout,
  type Pane,
  type PaneType,
  type WsLayout,
} from '../workspace'
import { ColorBar } from './ColorBar'
import { EmbeddingControls, EmbeddingView } from './EmbeddingView'
import { FocusBar } from './FocusBar'
import { GenomeControls, GenomeView } from './GenomeView'
import { LocusBar } from './LocusBar'
import { MatrixControls, MatrixView } from './MatrixView'
import { PaneCellControl } from './PaneCell'
import { StatsControls, StatsView } from './StatsView'
import { Viewport } from './Viewport'

const TYPE_LABEL = PANE_LABEL
const MENU_LABEL: Record<PaneType, string> = {
  '3d': '3D view',
  embedding: 'Embedding view',
  genome: 'Genome (Hi-C / distance / tracks)',
  matrix: 'Matrix (Hi-C / distance)',
  stats: 'Statistics',
}
/** Views that follow the shared genomic locus. */
const GENOME_PANES = new Set<PaneType>(['genome', 'matrix', 'stats'])
const LAYOUT_LABEL: Record<WsLayout, [string, string]> = {
  tabs: ['Tabs', 'One view at a time, switch with tabs'],
  columns: ['Columns', 'Views side by side'],
  rows: ['Rows', 'Views stacked'],
  grid: ['Grid', 'Views in a 2-column grid'],
}

/**
 * Centre area: views (3-D, embedding, …) as equal panes in a tabs / columns /
 * rows / grid layout, plus a bar with the controls that belong to no single
 * view (cell focus, colour scale, layout, + View).
 *
 * Panes are keyed children of one container, so changing the layout moves
 * them without remounting (a 3-D pane keeps its renderer and camera).
 */
export function Workspace() {
  const ws = useStore((s) => s.workspace)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const ensureDefault = useStore((s) => s.ensureDefaultWorkspace)
  const datasetId = useStore((s) => s.activeDatasetId)
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const hasEmbeddings = (ds?.embeddings?.length ?? 0) > 0
  const hasCoords = !!ds && ds.has_coords !== false && ds.n_spots > 0
  const hasTracks = (ds?.tracks?.length ?? 0) > 0
  const hasContactMaps = (ds?.contact_maps?.length ?? 0) > 0
  const [resetKeys, setResetKeys] = useState<Record<string, number>>({})
  const [menu, setMenu] = useState(false)
  const panesRef = useRef<HTMLDivElement>(null)

  // Until the user arranges views, the default follows the data.
  useEffect(() => {
    if (datasetId) ensureDefault({ hasEmbeddings, hasCoords, hasTracks, hasContactMaps })
  }, [datasetId, hasEmbeddings, hasCoords, hasTracks, hasContactMaps, ensureDefault])

  // Pins to cells the active dataset doesn't have (e.g. after switching) are dropped.
  const cellList = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  useEffect(() => {
    if (!cellList) return
    setWorkspace((w) => dropUnknownPins(w, new Set(cellList.map((c) => c.cell_id))))
  }, [cellList, setWorkspace])

  // Keyboard shortcuts once for the whole workspace (not per 3-D pane).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const st = useStore.getState()
      const handled = handleWorkspaceKey(e, {
        hasPick: !!st.pick,
        clearPick: () => st.setPick(null),
        clearFocus: () => st.focusCell(null),
        step: (d) => st.stepCell(d),
      })
      if (handled && e.key !== 'Escape') e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const sizes = normalizeSizes(ws.sizes, ws.panes.length)
  const split = (ws.layout === 'columns' || ws.layout === 'rows') && !ws.maximized
  const visible = (p: Pane) =>
    ws.maximized ? p.id === ws.maximized : ws.layout === 'tabs' ? p.id === ws.activePane : true

  const onSplitStart = (index: number) => (e: React.PointerEvent) => {
    e.preventDefault()
    const box = panesRef.current?.getBoundingClientRect()
    if (!box) return
    const cols = ws.layout === 'columns'
    const move = (ev: PointerEvent) => {
      const frac = cols ? (ev.clientX - box.left) / box.width : (ev.clientY - box.top) / box.height
      setWorkspace((w) => moveSplitter(w, index, frac))
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      document.body.classList.remove('resizing', 'resizing-rows')
    }
    document.body.classList.add(cols ? 'resizing' : 'resizing-rows')
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const add = (type: PaneType) => {
    setWorkspace((w) => addPane(w, type))
    setMenu(false)
  }

  return (
    <div className="workspace">
      <div className="ws-bar">
        <FocusBar />
        <ColorBar inline />
        {ws.panes.some((p) => GENOME_PANES.has(p.type)) && <LocusBar />}
        <span className="spacer" />
        <div className="ws-add">
          <button onClick={() => setMenu(!menu)} title="Add a view">
            + View
          </button>
          {menu && (
            <ul className="ws-menu" onMouseLeave={() => setMenu(false)}>
              {PANE_TYPES.map((t) => (
                <li key={t} onClick={() => add(t)}>
                  {MENU_LABEL[t]}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="seg ws-layouts" role="group" aria-label="Layout">
          {LAYOUTS.map((l) => (
            <button key={l} className={ws.layout === l ? 'active' : ''} title={LAYOUT_LABEL[l][1]} onClick={() => setWorkspace((w) => setLayout(w, l))}>
              {LAYOUT_LABEL[l][0]}
            </button>
          ))}
        </div>
      </div>
      {ws.layout === 'tabs' && !ws.maximized && (
        <div className="ws-tabs">
          {ws.panes.map((p, i) => (
            <button key={p.id} className={p.id === ws.activePane ? 'active' : ''} onClick={() => setWorkspace((w) => ({ ...w, activePane: p.id }))}>
              {TYPE_LABEL[p.type]} {ws.panes.filter((q) => q.type === p.type).length > 1 ? i + 1 : ''}
            </button>
          ))}
        </div>
      )}
      <div
        ref={panesRef}
        className={`ws-panes layout-${ws.layout}${ws.maximized ? ' maximized' : ''}`}
        style={ws.layout === 'grid' && !ws.maximized ? { gridTemplateColumns: ws.panes.length > 1 ? '1fr 1fr' : '1fr' } : undefined}
      >
        {ws.panes.map((p, i) => (
          <Fragment key={p.id}>
            <PaneBox
              pane={p}
              active={p.id === ws.activePane && ws.panes.length > 1}
              hidden={!visible(p)}
              style={split ? { flex: `${sizes[i]} 1 0` } : undefined}
              canClose={ws.panes.length > 1}
              maximized={ws.maximized === p.id}
              resetKey={resetKeys[p.id] ?? 0}
              onReset={() => setResetKeys((k) => ({ ...k, [p.id]: (k[p.id] ?? 0) + 1 }))}
            />
            {split && i < ws.panes.length - 1 && (
              <div className={`ws-splitter ${ws.layout}`} onPointerDown={onSplitStart(i)} title="Drag to resize" />
            )}
          </Fragment>
        ))}
      </div>
    </div>
  )
}

function PaneBox({
  pane,
  active,
  hidden,
  style,
  canClose,
  maximized,
  resetKey,
  onReset,
}: {
  pane: Pane
  active: boolean
  hidden: boolean
  style?: React.CSSProperties
  canClose: boolean
  maximized: boolean
  resetKey: number
  onReset(): void
}) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const activate = () => setWorkspace((w) => (w.activePane === pane.id ? w : { ...w, activePane: pane.id }))
  return (
    <section
      className={`pane${active ? ' active' : ''}${hidden ? ' hidden' : ''}${pane.cell ? ' pinned' : ''}`}
      style={style}
      onPointerDownCapture={activate}
      onFocusCapture={activate}
    >
      <header className="pane-head">
        <select value={pane.type} onChange={(e) => setWorkspace((w) => retypePane(w, pane.id, e.target.value as PaneType))} title="View type">
          {PANE_TYPES.map((t) => (
            <option key={t} value={t}>
              {TYPE_LABEL[t]}
            </option>
          ))}
        </select>
        <PaneCellControl pane={pane} />
        {pane.type === '3d' && (
          <button onClick={onReset} title="Fit everything drawn in this view">
            Reset view
          </button>
        )}
        {pane.type === 'embedding' && <EmbeddingControls pane={pane} />}
        {pane.type === 'genome' && <GenomeControls pane={pane} />}
        {pane.type === 'matrix' && <MatrixControls pane={pane} />}
        {pane.type === 'stats' && <StatsControls pane={pane} />}
        <span className="spacer" />
        <button
          onClick={() => setWorkspace((w) => ({ ...w, maximized: w.maximized === pane.id ? null : pane.id, activePane: pane.id }))}
          title={maximized ? 'Restore layout' : 'Maximise this view'}
        >
          {maximized ? '⤡' : '⤢'}
        </button>
        <button onClick={() => setWorkspace((w) => removePane(w, pane.id))} disabled={!canClose} title={canClose ? 'Close this view' : 'The last view cannot be closed'}>
          ×
        </button>
      </header>
      <div className="pane-body">
        {pane.type === '3d' && <Viewport paneId={pane.id} resetKey={resetKey} pinned={pane.cell ?? null} />}
        {pane.type === 'embedding' && <EmbeddingView pane={pane} />}
        {pane.type === 'genome' && <GenomeView pane={pane} />}
        {pane.type === 'matrix' && <MatrixView pane={pane} />}
        {pane.type === 'stats' && <StatsView pane={pane} />}
      </div>
    </section>
  )
}
