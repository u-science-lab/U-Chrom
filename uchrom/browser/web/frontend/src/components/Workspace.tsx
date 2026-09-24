import { Fragment, useEffect, useRef, useState } from 'react'
import { parseFieldRef } from '../groups'
import { activeSavedGroups, useStore } from '../store'
import {
  addPane,
  dropUnknownGroups,
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
import { EmbeddingView } from './EmbeddingView'
import { FocusBar } from './FocusBar'
import { GenomeView } from './GenomeView'
import { LocusBar } from './LocusBar'
import { MatrixView } from './MatrixView'
import { cellTitle, useCellTypes } from './PaneCell'
import { useGroupInfo } from '../useGroups'
import { savePanePng } from '../capture'
import { StatsView } from './StatsView'
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

  // Group scopes the active dataset doesn't know (another dataset's lasso group) are dropped.
  const fields = ds?.cell_fields
  const savedIds = useStore((s) => activeSavedGroups(s))
  useEffect(() => {
    if (!ds) return
    const saved = new Set(savedIds.map((g) => g.id))
    const known = (ref: string) => {
      const f = parseFieldRef(ref)
      return f ? !!fields?.some((x) => x.name === f.field) : saved.has(ref)
    }
    setWorkspace((w) => dropUnknownGroups(w, known))
  }, [ds, fields, savedIds, setWorkspace])

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
  const types = useCellTypes()
  const groupInfo = useGroupInfo(pane.group)
  const bodyRef = useRef<HTMLDivElement>(null)
  const [saving, setSaving] = useState(false)
  const saveImage = () => {
    if (!bodyRef.current || saving) return
    setSaving(true)
    savePanePng(bodyRef.current, pane)
      .catch((e: Error) => useStore.getState().setError(`Cannot save the image: ${e.message}`))
      .finally(() => setSaving(false))
  }
  return (
    <section
      className={`pane${active ? ' active' : ''}${hidden ? ' hidden' : ''}${pane.cell || pane.group ? ' pinned' : ''}`}
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
        {pane.cell && !pane.group && (
          <button className="pin-badge" onClick={() => activate()} title="Pinned to this cell — change or unpin it in the inspector (right)">
            📌 {cellTitle(pane.cell, types)}
          </button>
        )}
        {pane.group && (
          <button className="pin-badge group" onClick={() => activate()} title="This view aggregates over a group of cells — change it in the inspector (right)">
            <span className="swatch round" style={{ background: groupInfo?.color ?? '#888' }} />
            {groupInfo?.name ?? pane.group}
            {groupInfo?.cells && <span className="muted"> · {groupInfo.cells.length}</span>}
          </button>
        )}
        <span className="spacer" />
        <button className="pane-shot" onClick={saveImage} disabled={saving} title="Save image (PNG)" aria-label="Save image (PNG)">
          <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden>
            <path d="M2 5h2.6l1.2-1.8h4.4L11.4 5H14v8H2z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            <circle cx="8" cy="9" r="2.3" fill="none" stroke="currentColor" strokeWidth="1.3" />
          </svg>
        </button>
        {pane.type === '3d' && (
          <button onClick={onReset} title="Reset view: fit everything drawn in this view">
            ⟲
          </button>
        )}
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
      <div className="pane-body" ref={bodyRef} data-pane={pane.id}>
        {pane.type === '3d' && <Viewport paneId={pane.id} resetKey={resetKey} pinned={pane.cell ?? null} group={pane.group ?? null} />}
        {pane.type === 'embedding' && <EmbeddingView pane={pane} />}
        {pane.type === 'genome' && <GenomeView pane={pane} />}
        {pane.type === 'matrix' && <MatrixView pane={pane} />}
        {pane.type === 'stats' && <StatsView pane={pane} />}
      </div>
    </section>
  )
}
