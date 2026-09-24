import { useMemo, useState } from 'react'
import { nextGroupName, resolveRowScope, sameSpec, specLabel, type GroupInfo, type RowScopeSpec, type Scope } from '../groups'
import { activeSavedGroups, activeView, useStore } from '../store'
import { useFocusState, useGroupChoices, useGroupInfos } from '../useGroups'
import { useCellTypes } from './PaneCell'

const MAX_SHOWN = 80

/** Number of cells of the active dataset (the list, else the summary). */
export function useNCells(): number {
  return useStore((s) => (s.activeDatasetId && s.cells[s.activeDatasetId]?.length) || s.datasets.find((d) => d.id === s.activeDatasetId)?.n_cells || 0)
}

/**
 * The one "cells" setting of a view or a genome row:
 * - All cells — fixed, whatever is focused or lassoed;
 * - Follow focus — the focused cell / group / selection, else all cells;
 * - Cell… — one cell (search);
 * - Group… — a cell-type group, a saved group, or the current lasso
 *   selection (frozen: saved, named or not, so it no longer changes);
 * - Same as view (rows, `view` given) — the view's setting.
 * The button always says what the setting resolves to right now.
 */
export function ScopePicker({
  value,
  onChange,
  view,
  title = 'Which cells this shows',
}: {
  value: RowScopeSpec | undefined
  onChange(spec: RowScopeSpec): void
  /** rows: the view's resolved scope (offers "Same as view") */
  view?: Scope
  title?: string
}) {
  const allowView = view !== undefined
  const spec: RowScopeSpec = value ?? (allowView ? { kind: 'view' } : { kind: 'focus' })
  const focus = useFocusState()
  const resolved = allowView ? resolveRowScope(spec, view, focus) : resolveRowScope(spec, { kind: 'all' }, focus)
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const nAll = useNCells()
  const types = useCellTypes()
  const selection = useStore((s) => activeView(s).selection)
  const saved = useStore(activeSavedGroups)
  const saveSelection = useStore((s) => s.saveSelection)
  const choices = useGroupChoices()
  const groupRefs = useMemo(() => [...choices.fields.flatMap((f) => f.refs), ...choices.saved], [choices])
  const infos = useGroupInfos([...groupRefs, resolved.kind === 'group' ? resolved.group : null, selection?.id ?? null])
  const byRef = useMemo(() => new Map(infos.filter((i): i is GroupInfo => !!i).map((i) => [i.ref, i])), [infos])
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [naming, setNaming] = useState<string | null>(null)
  const t = q.trim().toLowerCase()
  const cellMatches = useMemo(() => {
    if (!open || !cells) return []
    const out: string[] = []
    for (const c of cells) {
      const ty = types?.get(c.cell_id)
      if (!t || c.cell_id.toLowerCase().includes(t) || (typeof ty === 'string' && ty.toLowerCase().includes(t))) out.push(c.cell_id)
      if (out.length >= MAX_SHOWN) break
    }
    return out
  }, [open, cells, t, types])
  const groupMatches = groupRefs.filter((r) => !t || (byRef.get(r)?.name ?? r).toLowerCase().includes(t))
  const info = resolved.kind === 'group' ? byRef.get(resolved.group) : null
  const label = specLabel(spec, resolved, info, nAll, types)

  const close = () => {
    setOpen(false)
    setQ('')
    setNaming(null)
  }
  const pick = (s: RowScopeSpec) => {
    onChange(s)
    close()
  }
  /** Freeze the lasso selection: keep it as a saved group (named or "unnamed n"), then use it. */
  const freeze = (name: string | null) => {
    if (!selection) return
    const id = selection.id
    saveSelection(name?.trim() || nextGroupName(saved, 'unnamed'))
    pick({ kind: 'group', group: id })
  }
  const on = (s: RowScopeSpec) => sameSpec(s, spec)
  const option = (s: RowScopeSpec, text: React.ReactNode, hint?: string) => (
    <li className={on(s) ? 'on' : ''} onClick={() => pick(s)} title={hint}>
      <span className="tick">{on(s) ? '✓' : ''}</span>
      {text}
    </li>
  )
  const swatch = (i: GroupInfo | null | undefined) => <span className="swatch round" style={{ background: i?.color ?? '#888' }} />
  return (
    <div className="pane-menu pane-cell scope-picker">
      <button className={spec.kind === 'focus' || spec.kind === 'view' ? '' : 'pinned'} onClick={() => setOpen(!open)} title={title}>
        {resolved.kind === 'group' && swatch(info)}
        {label} ▾
      </button>
      {open && (
        <div className="pane-popup" onMouseLeave={close}>
          <input autoFocus placeholder="search a cell or a group…" value={q} onChange={(e) => setQ(e.target.value)} />
          <ul>
            {allowView && option({ kind: 'view' }, <>Same as view <span className="muted">→ {specLabel({ kind: 'all' }, view!, view!.kind === 'group' ? byRef.get(view!.group) : null, nAll)}</span></>, "Use the view's cells setting (top of the inspector)")}
            {option({ kind: 'all' }, <>All cells <span className="muted">({nAll})</span></>, 'Every cell — never changes with focus, selection or lasso')}
            {option(
              { kind: 'focus' },
              <>
                Follow focus <span className="muted">→ {specLabel({ kind: 'all' }, resolveRowScope({ kind: 'focus' }, { kind: 'all' }, focus), focus.focusGroup ? byRef.get(focus.focusGroup) : null, nAll)}</span>
              </>,
              'Whatever is focused: a cell, a group or the lasso selection; all cells when nothing is',
            )}
            {selection && !saved.some((g) => g.id === selection.id) && (
              <>
                <li className="muted disabled head">current lasso selection · {selection.cells.length} cells</li>
                {naming === null ? (
                  <>
                    <li onClick={() => freeze(null)} title="Keep exactly these cells (saved as an unnamed group) — a new lasso won't change this">
                      <span className="tick">❄</span>freeze these {selection.cells.length} cells
                    </li>
                    <li onClick={() => setNaming('')} title="Save the selection as a named group and use it">
                      <span className="tick">＋</span>save as group…
                    </li>
                  </>
                ) : (
                  <li className="naming">
                    <input
                      autoFocus
                      placeholder="group name…"
                      value={naming}
                      onChange={(e) => setNaming(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && freeze(naming)}
                    />
                    <button onClick={() => freeze(naming)}>Save</button>
                  </li>
                )}
              </>
            )}
            {groupMatches.length > 0 && <li className="muted disabled head">groups</li>}
            {groupMatches.map((r) => (
              <li key={r} className={on({ kind: 'group', group: r }) ? 'on' : ''} onClick={() => pick({ kind: 'group', group: r })}>
                <span className="tick">{on({ kind: 'group', group: r }) ? '✓' : ''}</span>
                {swatch(byRef.get(r))}
                {byRef.get(r)?.name ?? r}
                <span className="muted"> · {byRef.get(r)?.cells ? `${byRef.get(r)!.cells!.length} cells` : '…'}</span>
              </li>
            ))}
            {cellMatches.length > 0 && <li className="muted disabled head">cells</li>}
            {cellMatches.map((id) => (
              <li key={id} className={on({ kind: 'cell', cell: id }) ? 'on' : ''} onClick={() => pick({ kind: 'cell', cell: id })}>
                <span className="tick">{on({ kind: 'cell', cell: id }) ? '✓' : ''}</span>
                {id}
                {typeof types?.get(id) === 'string' && <span className="muted"> · {types.get(id) as string}</span>}
              </li>
            ))}
            {cellMatches.length >= MAX_SHOWN && <li className="muted disabled">… type to narrow down</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
