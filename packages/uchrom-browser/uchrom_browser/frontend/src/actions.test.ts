import { describe, expect, it } from 'vitest'
import { genomeRows, parseCells, TOOLS, ACTIONS } from './actions'
import { PANE_TYPES } from './workspace'

const cells = new Set(['c1', 'c2'])
const groups = new Set(['g0123456789ab'])

describe('actions', () => {
  it('every tool in ui_tools.json has an implementation and vice versa', () => {
    expect(TOOLS.map((t) => t.name).sort()).toEqual(Object.keys(ACTIONS).sort())
  })
  it('open_view can open every kind of view the workspace has', () => {
    const open = TOOLS.find((t) => t.name === 'open_view') as unknown as { inputSchema: { properties: { type: { enum: string[] } } } }
    expect([...open.inputSchema.properties.type.enum].sort()).toEqual([...PANE_TYPES].sort())
  })
  it('parses cells specs into view scopes', () => {
    expect(parseCells(undefined, cells, groups)).toEqual({ kind: 'focus' })
    expect(parseCells('all', cells, groups)).toEqual({ kind: 'all' })
    expect(parseCells('c1', cells, groups)).toEqual({ kind: 'cell', cell: 'c1' })
    expect(parseCells('field:cell_type=Bergmann', cells, groups)).toEqual({ kind: 'group', group: 'field:cell_type=Bergmann' })
    expect(parseCells('g0123456789ab', cells, groups)).toEqual({ kind: 'group', group: 'g0123456789ab' })
    expect(() => parseCells('nope', cells, groups)).toThrow(/unknown cells/)
  })
  it('turns open_view rows into genome rows', () => {
    const rows = genomeRows(
      [{ kind: 'track', track: 'H3K27ac' }, { kind: 'distance', cells: 'c2' }, { kind: 'contacts', source: 'bulk' }, { kind: 'intervals', key: 'tads' }],
      cells,
      groups,
    )
    expect(rows).toEqual([
      { kind: 'track', track: 'H3K27ac' },
      { kind: 'matrix', source: 'distance', stat: 'median', scope: { kind: 'cell', cell: 'c2' } },
      { kind: 'matrix', source: 'bulk' },
      { kind: 'intervals', key: 'tads' },
    ])
    expect(() => genomeRows([{ kind: 'x' }], cells, groups)).toThrow(/kind/)
  })
})
