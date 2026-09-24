import { useMemo, useState } from 'react'
import type { GroupInfo } from '../groups'
import { activeView, defaultCategoryField, fieldKey, useStore } from '../store'
import { useGroupChoices, useGroupInfos } from '../useGroups'
import { pinPane, setPaneGroup, type Pane } from '../workspace'

/** Category label of each cell (e.g. cell type), when the dataset has one. */
export function useCellTypes(): ReadonlyMap<string, unknown> | undefined {
  return useStore((s) => {
    const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
    const f = defaultCategoryField(ds)
    return ds && f ? s.cellValues[fieldKey(ds.id, f.name)] : undefined
  })
}

/** "cell 1_0_34 · Bergmann" */
export function cellTitle(cell: string, types?: ReadonlyMap<string, unknown>): string {
  const t = types?.get(cell)
  return typeof t === 'string' ? `cell ${cell} · ${t}` : `cell ${cell}`
}

const MAX_SHOWN = 80

/** Colour dot + name + cell count of a group. */
export function GroupLabel({ info }: { info: GroupInfo | null }) {
  if (!info) return <span className="muted">unknown group</span>
  return (
    <>
      <span className="swatch round" style={{ background: info.color }} />
      {info.name}
      <span className="muted"> · {info.cells ? `${info.cells.length} cells` : '…'}</span>
    </>
  )
}

/**
 * Inspector control of a pane's scope: follow the global focus, pin one
 * cell ("📌 cell …"), or aggregate over a group (a cell type, a saved or
 * lassoed selection).  Search filters cells and groups (id, type, name).
 */
export function PaneCellControl({ pane }: { pane: Pane }) {
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const focus = useStore((s) => activeView(s).focusCell)
  const focusGroup = useStore((s) => activeView(s).focusGroup)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const types = useCellTypes()
  const choices = useGroupChoices()
  const groupRefs = useMemo(() => [...choices.fields.flatMap((f) => f.refs), ...choices.saved], [choices])
  const infos = useGroupInfos([...groupRefs, pane.group, focusGroup])
  const byRef = useMemo(() => new Map(infos.filter((i): i is GroupInfo => !!i).map((i) => [i.ref, i])), [infos])
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const t = q.trim().toLowerCase()
  const matches = useMemo(() => {
    if (!open || !cells) return []
    const hit = (id: string) => {
      if (!t) return true
      const ty = types?.get(id)
      return id.toLowerCase().includes(t) || (typeof ty === 'string' && ty.toLowerCase().includes(t))
    }
    const out: string[] = []
    for (const c of cells) {
      if (hit(c.cell_id)) out.push(c.cell_id)
      if (out.length >= MAX_SHOWN) break
    }
    return out
  }, [open, cells, t, types])
  const groupMatches = groupRefs.filter((r) => !t || (byRef.get(r)?.name ?? r).toLowerCase().includes(t))
  if (!cells || cells.length < 2) return null
  const pinned = pane.group ? null : (pane.cell ?? null)
  const close = () => {
    setOpen(false)
    setQ('')
  }
  const pin = (cell: string | null) => {
    setWorkspace((w) => pinPane(w, pane.id, cell))
    close()
  }
  const scopeTo = (group: string) => {
    setWorkspace((w) => setPaneGroup(w, pane.id, group))
    close()
  }
  const following = !pinned && !pane.group
  return (
    <div className="pane-menu pane-cell">
      <button
        className={pinned || pane.group ? 'pinned' : ''}
        onClick={() => setOpen(!open)}
        title={
          pane.group
            ? 'This view aggregates over a group of cells — click to change'
            : pinned
              ? 'This view is pinned to one cell — click to change or unpin'
              : 'This view follows the focused cell or group — click to pin it to a cell or a group'
        }
      >
        {pane.group ? <GroupLabel info={byRef.get(pane.group) ?? null} /> : pinned ? `📌 ${cellTitle(pinned, types)}` : 'follow focus ▾'}
      </button>
      {open && (
        <div className="pane-popup" onMouseLeave={close}>
          <input autoFocus placeholder="cell or group… (id, type, name)" value={q} onChange={(e) => setQ(e.target.value)} />
          <ul>
            <li className={following ? 'on' : ''} onClick={() => pin(null)}>
              <span className="tick">{following ? '✓' : ''}</span>follow focus
              {focus ? ` (now ${focus})` : focusGroup ? ` (now ${byRef.get(focusGroup)?.name ?? 'a group'})` : ''}
            </li>
            {focus && focus !== pinned && (
              <li onClick={() => pin(focus)}>
                <span className="tick">📌</span>focused {cellTitle(focus, types)}
              </li>
            )}
            {focusGroup && focusGroup !== pane.group && (
              <li onClick={() => scopeTo(focusGroup)}>
                <span className="tick">▣</span>focused group: <GroupLabel info={byRef.get(focusGroup) ?? null} />
              </li>
            )}
            {groupMatches.length > 0 && <li className="muted disabled head">groups</li>}
            {groupMatches.map((r) => (
              <li key={r} className={r === pane.group ? 'on' : ''} onClick={() => scopeTo(r)}>
                <span className="tick">{r === pane.group ? '✓' : ''}</span>
                <GroupLabel info={byRef.get(r) ?? null} />
              </li>
            ))}
            {matches.length > 0 && <li className="muted disabled head">cells</li>}
            {matches.map((id) => (
              <li key={id} className={id === pinned ? 'on' : ''} onClick={() => pin(id)}>
                <span className="tick">{id === pinned ? '✓' : ''}</span>
                {id}
                {typeof types?.get(id) === 'string' && <span className="muted"> · {types.get(id) as string}</span>}
              </li>
            ))}
            {matches.length >= MAX_SHOWN && <li className="muted disabled">… type to narrow down</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
