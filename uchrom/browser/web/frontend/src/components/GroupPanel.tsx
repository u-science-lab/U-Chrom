import { useMemo, useState } from 'react'
import type { GroupInfo, GroupRef } from '../groups'
import { activeView, hasCoords, useStore } from '../store'
import { useGroupChoices, useGroupInfos } from '../useGroups'
import { addGroupPane } from '../workspace'
import { fieldLabel } from './format'

/**
 * Left side bar (shared by every view): cell groups.  One automatic group
 * per category of each categorical field, collapsed by field; groups saved
 * from a lasso selection (rename / delete); and the current selection.
 * Click a group to focus it — its cells are drawn in full everywhere and
 * views that follow the focus aggregate over it; ↗ opens a view of it.
 */
export function GroupPanel() {
  const choices = useGroupChoices()
  const view = useStore(activeView)
  const focusGroup = useStore((s) => s.focusGroup)
  const setSelection = useStore((s) => s.setSelection)
  const saveSelection = useStore((s) => s.saveSelection)
  const rename = useStore((s) => s.renameSavedGroup)
  const remove = useStore((s) => s.deleteSavedGroup)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const coords = useStore((s) => hasCoords(s.datasets.find((d) => d.id === s.activeDatasetId)))
  const hasEmbeddings = useStore((s) => (s.datasets.find((d) => d.id === s.activeDatasetId)?.embeddings?.length ?? 0) > 0)
  const refs = useMemo(() => [...choices.fields.flatMap((f) => f.refs), ...choices.saved, view.selection?.id ?? null], [choices, view.selection])
  const infos = useGroupInfos(refs)
  const byRef = useMemo(() => new Map(infos.filter((i): i is GroupInfo => !!i).map((i) => [i.ref, i])), [infos])
  // the first categorical field starts open, the others collapsed
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [selName, setSelName] = useState('')

  const toggle = (ref: GroupRef) => focusGroup(view.focusGroup === ref ? null : ref)
  const openView = (ref: GroupRef) => setWorkspace((w) => addGroupPane(w, coords ? 'genome' : 'matrix', ref))
  const row = (info: GroupInfo | undefined, ref: GroupRef, extra?: React.ReactNode) => (
    <li key={ref} className={view.focusGroup === ref ? 'selected' : ''} onClick={() => toggle(ref)} title={view.focusGroup === ref ? 'Focused — click to release' : 'Focus this group in every view'}>
      <span className="swatch round" style={{ background: info?.color ?? '#888' }} />
      <span className="group-name">{info?.name ?? ref}</span>
      <span className="muted small">{info?.cells ? info.cells.length.toLocaleString('en-US') : '…'}</span>
      {extra}
      <button
        className="cell-open"
        onClick={(e) => {
          e.stopPropagation()
          openView(ref)
        }}
        title="Open a new view aggregating over this group"
      >
        ↗
      </button>
    </li>
  )

  const nothing = !choices.fields.length && !choices.saved.length && !view.selection
  return (
    <section className="panel groups">
      <h2>
        Groups
        {view.focusGroup && (
          <button className="link" onClick={() => focusGroup(null)} title="Release the focused group">
            clear
          </button>
        )}
      </h2>
      {view.selection && (
        <div className="group-selection">
          <div>
            <b>{view.selection.cells.length.toLocaleString('en-US')}</b> cells selected
          </div>
          <input
            placeholder="name…"
            value={selName}
            onChange={(e) => setSelName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                saveSelection(selName)
                setSelName('')
              }
            }}
          />
          <button
            onClick={() => {
              saveSelection(selName)
              setSelName('')
            }}
            title="Keep this selection as a named group"
          >
            Save as group
          </button>
          <button onClick={() => setSelection(null)} title="Discard the selection">
            ×
          </button>
        </div>
      )}
      <ul className="group-list">
        {choices.fields.map(({ field, refs: frefs }, k) => {
          const isOpen = open[field.name] ?? k === 0
          return (
            <li key={field.name} className="group-field">
              <div className="group-field-head" onClick={() => setOpen((o) => ({ ...o, [field.name]: !isOpen }))}>
                <span className="caret">{isOpen ? '▾' : '▸'}</span>
                {fieldLabel(field.name)} <span className="muted small">{frefs.length}</span>
              </div>
              {isOpen && <ul>{frefs.map((r) => row(byRef.get(r), r))}</ul>}
            </li>
          )
        })}
        {choices.saved.length > 0 && (
          <li className="group-field">
            <div className="group-field-head static">saved</div>
            <ul>
              {choices.saved.map((r) =>
                editing === r ? (
                  <li key={r} className="editing">
                    <input
                      autoFocus
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={() => {
                        rename(r, draft)
                        setEditing(null)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                        if (e.key === 'Escape') setEditing(null)
                      }}
                    />
                  </li>
                ) : (
                  row(
                    byRef.get(r),
                    r,
                    <>
                      <button
                        className="cell-open"
                        onClick={(e) => {
                          e.stopPropagation()
                          setDraft(byRef.get(r)?.name ?? '')
                          setEditing(r)
                        }}
                        title="Rename"
                      >
                        ✎
                      </button>
                      <button
                        className="cell-open"
                        onClick={(e) => {
                          e.stopPropagation()
                          remove(r)
                        }}
                        title="Delete this group"
                      >
                        ×
                      </button>
                    </>,
                  )
                ),
              )}
            </ul>
          </li>
        )}
      </ul>
      <div className="muted small">
        {nothing ? 'No groups yet. ' : ''}
        {hasEmbeddings ? 'Lasso cells in an Embedding view (shift-drag, or the ◌ tool) to make a group.' : 'Groups come from categorical cell fields.'}
      </div>
    </section>
  )
}
