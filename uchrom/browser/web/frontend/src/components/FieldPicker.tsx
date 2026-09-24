import { useEffect, useMemo, useState } from 'react'
import type { CellField } from '../types'
import { fieldLabel } from './format'

/** Button / picker title for a cell-field group: rna → Gene, cell → Property. */
export function groupTitle(group: string): string {
  if (group === 'rna') return 'Gene'
  if (group === 'cell') return 'Property'
  if (group === 'atac') return 'ATAC' // gene activity (atac.<gene>)
  if (group === 'hic') return 'Hi-C'
  return group.length <= 3 ? group.toUpperCase() : group[0].toUpperCase() + group.slice(1)
}

/**
 * Searchable picker for one group of cell fields (type to filter — scales to
 * thousands of genes, unlike a <select>).  Genes sort alphabetically.
 */
export function FieldPicker({
  fields,
  value,
  placeholder,
  onPick,
}: {
  fields: CellField[]
  value: string | null
  placeholder: string
  onPick: (name: string) => void
}) {
  const current = fields.find((f) => f.name === value)
  const shown = (f: CellField) => (f.group === 'cell' ? fieldLabel(f.name) : f.label)
  const [text, setText] = useState(current ? shown(current) : '')
  const [open, setOpen] = useState(false)
  useEffect(() => setText(current ? shown(current) : ''), [value]) // eslint-disable-line react-hooks/exhaustive-deps
  const sorted = useMemo(
    () => (fields[0]?.group === 'cell' ? fields : [...fields].sort((a, b) => a.label.localeCompare(b.label))),
    [fields],
  )
  const q = text.trim().toLowerCase()
  const matches = !open || (current && shown(current).toLowerCase() === q) ? sorted : sorted.filter((f) => shown(f).toLowerCase().includes(q))
  const pick = (f: CellField) => {
    onPick(f.name)
    setText(shown(f))
    setOpen(false)
  }
  return (
    <div className="field-picker">
      <input
        value={text}
        placeholder={placeholder}
        onFocus={(e) => {
          setOpen(true)
          e.target.select()
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && matches.length) pick(matches[0])
          if (e.key === 'Escape') (e.target as HTMLInputElement).blur()
        }}
      />
      {open && (
        <ul className="field-options">
          {matches.slice(0, 200).map((f) => (
            <li key={f.name} className={f.name === value ? 'selected' : ''} onMouseDown={() => pick(f)}>
              {shown(f)}
            </li>
          ))}
          {!matches.length && <li className="muted">no match</li>}
        </ul>
      )}
    </div>
  )
}
