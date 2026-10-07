import { useEffect, useState } from 'react'
import { fetchCellInfo } from '../api'
import { activeView, useStore } from '../store'
import type { CellDetails } from '../types'
import { fieldLabel, fmtNum } from './format'

const cache = new Map<string, CellDetails>()
const TOP = 12

/** Split cell_info fields into scalar attributes and RNA counts (by prefix). */
export function splitCellFields(fields: CellDetails['fields']) {
  const attrs: [string, number | string | null][] = []
  const rna: { name: string; label: string; value: number }[] = []
  for (const [k, v] of Object.entries(fields)) {
    if (k.startsWith('rna.')) {
      if (typeof v === 'number' && Number.isFinite(v)) rna.push({ name: k, label: k.slice(4), value: v })
    } else if (!/(^|_)id$/i.test(k)) attrs.push([k, v]) // ids are not attributes
  }
  rna.sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
  return { attrs, rna }
}

/** No focused cell: one line about the dataset instead. */
function DatasetSummaryLine() {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  if (!ds) return null
  const coords = ds.has_coords !== false && ds.n_spots > 0
  const parts = [
    ds.n_cells > 1 ? `${ds.n_cells.toLocaleString('en-US')} cells` : null,
    coords ? `${ds.n_traces.toLocaleString('en-US')} traces` : null,
    coords ? `${ds.n_spots.toLocaleString('en-US')} spots` : null,
    ds.chroms.length ? `${ds.chroms.length} chroms` : null,
    ds.contact_maps?.length ? `${ds.contact_maps.length} contact maps` : null,
    coords && ds.xyz_unit ? ds.xyz_unit : null,
  ].filter(Boolean)
  return (
    <section className="cell-info">
      <h2>{ds.name}</h2>
      <div className="muted small">{parts.join(' · ')}</div>
      {ds.n_cells > 1 && <div className="muted small">No cell focused — pick one in the list or any view.</div>}
    </section>
  )
}

/** Details of the focused cell: attributes and its RNA counts. */
export function CellInfoPanel() {
  const dsId = useStore((s) => s.activeDatasetId)
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const hasFields = !!ds?.cell_fields?.length
  const view = useStore(activeView)
  const setCellField = useStore((s) => s.setCellField)
  const [info, setInfo] = useState<CellDetails | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const cell = view.focusCell

  useEffect(() => {
    setInfo(null)
    setError(null)
    if (!dsId || !cell || !hasFields) return
    const key = `${dsId}\u0000${cell}`
    const hit = cache.get(key)
    if (hit) return setInfo(hit)
    let live = true
    fetchCellInfo(dsId, cell)
      .then((r) => {
        cache.set(key, r)
        if (live) setInfo(r)
      })
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [dsId, cell, hasFields])

  if (!cell) return <DatasetSummaryLine />
  if (!hasFields) return null
  const { attrs, rna } = info ? splitCellFields(info.fields) : { attrs: [], rna: [] }
  const shown = showAll ? rna : rna.slice(0, TOP)
  const max = rna.length ? Math.max(1e-9, rna[0].value) : 1
  return (
    <section className="cell-info">
      <h2>Cell {cell}</h2>
      {error && <div className="error">{error}</div>}
      {!info && !error && <div className="muted small">loading…</div>}
      {attrs.length > 0 && (
        <dl className="stats">
          {attrs.map(([k, v]) => (
            <div className="kv" key={k}>
              <dt>{fieldLabel(k)}</dt>
              <dd>{typeof v === 'number' ? fmtNum(v) : v ?? '—'}</dd>
            </div>
          ))}
        </dl>
      )}
      {rna.length > 0 && (
        <>
          <div className="muted small">RNA counts · click a gene to colour all cells by it</div>
          <ul className="bars">
            {shown.map((g) => (
              <li key={g.name} onClick={() => setCellField(g.name)} title={`Colour all cells by ${g.label}`}>
                <span className="bar-label">{g.label}</span>
                <span className="bar-track">
                  <span className="bar-fill" style={{ width: `${(100 * g.value) / max}%` }} />
                </span>
                <span className="bar-value">{fmtNum(g.value)}</span>
              </li>
            ))}
          </ul>
          {rna.length > TOP && (
            <button className="link" onClick={() => setShowAll(!showAll)}>
              {showAll ? 'show top' : `show all ${rna.length}`}
            </button>
          )}
        </>
      )}
    </section>
  )
}
