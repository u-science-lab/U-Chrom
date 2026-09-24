import { describe, expect, it } from 'vitest'
import {
  activePaneOf,
  addPane,
  addPinnedPane,
  defaultWorkspace,
  dropUnknownPins,
  MAX_SPLIT_PANES,
  paneCell,
  parseWorkspace,
  pinPane,
  setLayout,
  show3dPanels,
  type WorkspaceState,
} from './workspace'

const base = (): WorkspaceState => defaultWorkspace({ hasCoords: true, hasEmbeddings: true, hasTracks: false }) // 3D | Embedding

describe('pinning panes to cells', () => {
  it('pins and unpins a pane', () => {
    const ws = pinPane(base(), 'P2', 'c7')
    expect(ws.panes[1].cell).toBe('c7')
    expect(ws.panes[0].cell).toBeUndefined()
    expect(pinPane(ws, 'P2', null).panes[1].cell).toBeNull()
  })
  it('opens a cell in a new pinned pane and makes it active', () => {
    const ws = addPinnedPane(base(), '3d', 'c7')
    expect(ws.panes.map((p) => [p.type, p.cell ?? null])).toEqual([
      ['3d', null],
      ['embedding', null],
      ['3d', 'c7'],
    ])
    expect(ws.activePane).toBe(ws.panes[2].id)
    expect(ws.layout).toBe('columns')
    expect(ws.sizes.reduce((a, b) => a + b, 0)).toBeCloseTo(1)
  })
  it('switches columns / rows to a grid beyond MAX_SPLIT_PANES; keeps tabs', () => {
    let ws = base()
    for (let i = 0; ws.panes.length <= MAX_SPLIT_PANES; i++) ws = addPinnedPane(ws, '3d', `c${i}`)
    expect(ws.layout).toBe('grid')
    const tabs = addPinnedPane(addPinnedPane(setLayout(base(), 'tabs'), '3d', 'a'), '3d', 'b')
    expect(tabs.layout).toBe('tabs')
  })
  it('resolves the cell a pane shows: its pin, else the focus', () => {
    expect(paneCell({ cell: 'c7' }, 'c1')).toBe('c7')
    expect(paneCell({ cell: null }, 'c1')).toBe('c1')
    expect(paneCell({}, null)).toBeNull()
    expect(paneCell(undefined, 'c1')).toBe('c1')
  })
})

describe('3-D side panels follow the active pane', () => {
  it('shows them only while a 3-D pane is active', () => {
    const ws = base()
    expect(show3dPanels(ws)).toBe(true) // P1 = 3D
    expect(show3dPanels({ ...ws, activePane: 'P2' })).toBe(false) // embedding
    // no 3-D pane at all
    const no3d = defaultWorkspace({ hasCoords: false, hasEmbeddings: true, hasTracks: false })
    expect(no3d.panes.some((p) => p.type === '3d')).toBe(false)
    for (const p of no3d.panes) expect(show3dPanels({ ...no3d, activePane: p.id })).toBe(false)
    // unknown active id → first pane
    expect(activePaneOf({ ...ws, activePane: 'nope' })?.id).toBe('P1')
    expect(show3dPanels(addPane(ws, 'genome'))).toBe(false) // the new pane is active
  })
})

describe('persisted pins', () => {
  it('round-trips the pinned cell and drops malformed values', () => {
    const ws = pinPane(base(), 'P1', 'c7')
    const back = parseWorkspace(JSON.parse(JSON.stringify(ws)))!
    expect(back.panes[0].cell).toBe('c7')
    const bad = parseWorkspace({ layout: 'columns', panes: [{ id: 'a', type: '3d', cell: 5 }, { id: 'b', type: '3d', cell: '' }] })!
    expect(bad.panes.map((p) => p.cell)).toEqual([undefined, undefined])
  })
  it('unpins cells the active dataset does not have', () => {
    const ws = pinPane(pinPane(addPinnedPane(base(), '3d', 'gone'), 'P1', 'c1'), 'P2', null)
    const out = dropUnknownPins(ws, new Set(['c1', 'c2']))
    expect(out.panes.map((p) => p.cell ?? null)).toEqual(['c1', null, null])
    // nothing to drop → same object (no needless save / re-render)
    expect(dropUnknownPins(out, new Set(['c1']))).toBe(out)
  })
})
