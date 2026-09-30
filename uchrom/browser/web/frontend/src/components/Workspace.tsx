import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { parseFieldRef } from '../groups'
import { activeSavedGroups, useStore } from '../store'
import {
  addPane,
  dropUnknownGroups,
  dropUnknownPins,
  pinnedCell,
  pinnedGroup,
  handleWorkspaceKey,
  LAYOUTS,
  moveSplitter,
  normalizeSizes,
  PANE_LABEL,
  removePane,
  retypePane,
  setLayout,
  supportedPaneTypes,
  type DataKind,
  type Pane,
  type PaneType,
  type WsLayout,
} from '../workspace'
import { EmbeddingView } from './EmbeddingView'
import { GenomeView } from './GenomeView'
import { LocusBar } from './LocusBar'
import { MatrixView } from './MatrixView'
import { Popover } from './Popover'
import { cellTitle, useCellTypes } from './PaneCell'
import { useGroupInfo } from '../useGroups'
import { savePanePng } from '../capture'
import { StatsView } from './StatsView'
import { RegionPicker, SpatialView } from './SpatialView'
import { Viewport } from './Viewport'

const TYPE_LABEL = PANE_LABEL
/** What each view shows (menu descriptions). */
const MENU_HINT: Record<PaneType, string> = {
  '3d': '3-D chromatin structures',
  spatial: 'cells in the tissue, over its image',
  embedding: 'UMAP / t-SNE / PCA of the cells',
  genome: 'contact maps, distances and tracks along a locus',
  matrix: 'contact or distance matrix of a locus',
  stats: 'distributions and per-cell statistics',
}
const MENU_ICON: Record<PaneType, string> = { '3d': '◈', spatial: '▦', embedding: '⁘', genome: '≋', matrix: '▤', stats: '▥' }

/** What the active dataset offers, for the default views and the view menus. */
function useDataKind(): DataKind {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  return {
    hasEmbeddings: (ds?.embeddings?.length ?? 0) > 0,
    hasCoords: !!ds && ds.has_coords !== false && ds.n_spots > 0,
    hasTracks: (ds?.tracks?.length ?? 0) > 0,
    hasContactMaps: (ds?.contact_maps?.length ?? 0) > 0,
    hasSpatial: (ds?.spatial?.length ?? 0) > 0,
    manyCells: (ds?.n_cells ?? 0) > 1,
  }
}

/**
 * Menu of view types (the + View menu and each pane's type switch): only
 * the views this dataset can fill, each with what it shows; the current
 * type is checked (and kept listed, marked, if the data lacks it).
 */
function ViewMenu({ current, onPick }: { current?: PaneType; onPick(t: PaneType): void }) {
  const supported = supportedPaneTypes(useDataKind())
  const types = current && !supported.includes(current) ? [...supported, current] : supported
  return (
    <ul className="view-menu" role="menu">
      {types.map((t) => (
        <li
          key={t}
          role="menuitemradio"
          aria-checked={t === current}
          className={`${t === current ? 'current' : ''}${supported.includes(t) ? '' : ' unsupported'}`}
          onClick={() => onPick(t)}
        >
          <span className="vm-icon" aria-hidden>
            {MENU_ICON[t]}
          </span>
          <span className="vm-text">
            <span className="vm-name">{PANE_LABEL[t]}</span>
            <span className="vm-hint">{supported.includes(t) ? MENU_HINT[t] : 'not available for this dataset'}</span>
          </span>
          <span className="vm-check" aria-hidden>
            {t === current ? '✓' : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** A pane's type switch: the view name with a caret, opening the view menu. */
function PaneTypeSwitch({ pane }: { pane: Pane }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  return (
    <>
      <button ref={ref} className={`pane-type${open ? ' open' : ''}`} onClick={() => setOpen(!open)} title="View type" aria-haspopup="menu">
        <span className="vm-icon" aria-hidden>
          {MENU_ICON[pane.type]}
        </span>
        <span className="pane-type-label">{TYPE_LABEL[pane.type]}</span>
        <span className="caret" aria-hidden>
          ▾
        </span>
      </button>
      <Popover anchor={ref} open={open} onClose={close} className="menu-popup">
        <ViewMenu
          current={pane.type}
          onPick={(t) => {
            setWorkspace((w) => retypePane(w, pane.id, t))
            setOpen(false)
          }}
        />
      </Popover>
    </>
  )
}
/** Whether a pane shows the shared genomic locus (Stats only when it looks at the locus chromosome). */
const usesLocus = (p: Pane) => p.type === 'genome' || p.type === 'matrix' || (p.type === 'stats' && p.chromScope === 'locus')
const LAYOUT_LABEL: Record<WsLayout, [string, string]> = {
  tabs: ['Tabs', 'one view at a time, switch with tabs'],
  columns: ['Columns', 'views side by side'],
  rows: ['Rows', 'views stacked'],
  grid: ['Grid', 'views in a 2-column grid'],
}

/** Small drawing of a layout (menu and button). */
function LayoutIcon({ layout }: { layout: WsLayout }) {
  const r = (x: number, y: number, w: number, h: number) => <rect x={x} y={y} width={w} height={h} rx="1" />
  return (
    <svg className="layout-icon" viewBox="0 0 16 12" width="16" height="12" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.2">
      {layout === 'tabs' && (
        <>
          {r(1, 3, 14, 8)}
          <path d="M1.5 3V1.5h5V3" />
        </>
      )}
      {layout === 'columns' && (
        <>
          {r(1, 1, 6.2, 10)}
          {r(8.8, 1, 6.2, 10)}
        </>
      )}
      {layout === 'rows' && (
        <>
          {r(1, 1, 14, 4.2)}
          {r(1, 6.8, 14, 4.2)}
        </>
      )}
      {layout === 'grid' && (
        <>
          {r(1, 1, 6.2, 4.2)}
          {r(8.8, 1, 6.2, 4.2)}
          {r(1, 6.8, 6.2, 4.2)}
          {r(8.8, 6.8, 6.2, 4.2)}
        </>
      )}
    </svg>
  )
}

/** The layout switch: the current layout as a button (like + View), the four layouts in a menu. */
function LayoutMenu({ layout, onPick }: { layout: WsLayout; onPick(l: WsLayout): void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  return (
    <div className="ws-add">
      <button ref={ref} className={`ws-layout-btn${open ? ' open' : ''}`} onClick={() => setOpen(!open)} title="Layout of the views" aria-haspopup="menu">
        <LayoutIcon layout={layout} />
        {LAYOUT_LABEL[layout][0]}
        <span className="caret" aria-hidden>
          ▾
        </span>
      </button>
      <Popover anchor={ref} open={open} onClose={close} className="menu-popup">
        <ul className="view-menu" role="menu">
          {LAYOUTS.map((l) => (
            <li
              key={l}
              role="menuitemradio"
              aria-checked={l === layout}
              className={l === layout ? 'current' : ''}
              onClick={() => {
                onPick(l)
                setOpen(false)
              }}
            >
              <span className="vm-icon" aria-hidden>
                <LayoutIcon layout={l} />
              </span>
              <span className="vm-text">
                <span className="vm-name">{LAYOUT_LABEL[l][0]}</span>
                <span className="vm-hint">{LAYOUT_LABEL[l][1]}</span>
              </span>
              <span className="vm-check" aria-hidden>
                {l === layout ? '✓' : ''}
              </span>
            </li>
          ))}
        </ul>
      </Popover>
    </div>
  )
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
  const { hasEmbeddings, hasCoords, hasTracks, hasContactMaps, hasSpatial, manyCells } = useDataKind()
  const [resetKeys, setResetKeys] = useState<Record<string, number>>({})
  const [menu, setMenu] = useState(false)
  const addRef = useRef<HTMLButtonElement>(null)
  const closeMenu = useCallback(() => setMenu(false), [])
  const panesRef = useRef<HTMLDivElement>(null)

  // Until the user arranges views, the default follows the data.
  useEffect(() => {
    if (datasetId) ensureDefault({ hasEmbeddings, hasCoords, hasTracks, hasContactMaps, hasSpatial, manyCells })
  }, [datasetId, hasEmbeddings, hasCoords, hasTracks, hasContactMaps, hasSpatial, manyCells, ensureDefault])

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
        <span className="spacer" />
        <div className="ws-add">
          <button ref={addRef} onClick={() => setMenu(!menu)} title="Add a view">
            + View
          </button>
          <Popover anchor={addRef} open={menu} onClose={closeMenu} className="menu-popup">
            <ViewMenu onPick={add} />
          </Popover>
        </div>
        <LayoutMenu layout={ws.layout} onPick={(l) => setWorkspace((w) => setLayout(w, l))} />
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
  const groupInfo = useGroupInfo(pinnedGroup(pane))
  const cellPin = pinnedCell(pane)
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
      className={`pane${active ? ' active' : ''}${hidden ? ' hidden' : ''}${pane.scope && pane.scope.kind !== 'focus' ? ' pinned' : ''}`}
      style={style}
      onPointerDownCapture={activate}
      onFocusCapture={activate}
    >
      <header className="pane-head">
        <PaneTypeSwitch pane={pane} />
        {pane.type === 'spatial' && <RegionPicker pane={pane} />}
        {usesLocus(pane) && <LocusBar />}
        {cellPin && (
          <button className="pin-badge" onClick={() => activate()} title="Pinned to this cell — change it in the inspector (right, “cells”)">
            📌 {cellTitle(cellPin, types)}
          </button>
        )}
        {pane.scope?.kind === 'all' && (
          <button className="pin-badge" onClick={() => activate()} title="Always all cells — change it in the inspector (right, “cells”)">
            All cells
          </button>
        )}
        {pane.scope?.kind === 'group' && (
          <button className="pin-badge group" onClick={() => activate()} title="This view aggregates over a group of cells — change it in the inspector (right)">
            <span className="swatch round" style={{ background: groupInfo?.color ?? '#888' }} />
            {groupInfo?.name ?? pane.scope.group}
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
        {pane.type === '3d' && <Viewport paneId={pane.id} resetKey={resetKey} scope={pane.scope} />}
        {pane.type === 'spatial' && <SpatialView pane={pane} />}
        {pane.type === 'embedding' && <EmbeddingView pane={pane} />}
        {pane.type === 'genome' && <GenomeView pane={pane} />}
        {pane.type === 'matrix' && <MatrixView pane={pane} />}
        {pane.type === 'stats' && <StatsView pane={pane} />}
      </div>
    </section>
  )
}
