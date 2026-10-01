import { useEffect, useMemo, useState } from 'react'
import { listTraces } from '../api'
import { chromsOf, composeFilter, describeFilter, fmtBp, parseRegion, parseTraceSelection } from '../filters'
import { useStore } from '../store'
import type { DatasetSummary, Layer, LayerFilter, LayerStyle, TraceInfo } from '../types'
import { Select } from './Select'
import { layerInPane } from '../workspace'

type Tab = 'region' | 'trace'

const TAB_LABEL: Record<Tab, string> = { region: 'Region', trace: 'Trace' }

export function OperationsPanel() {
  const datasets = useStore((s) => s.datasets)
  const activeId = useStore((s) => s.activeDatasetId)
  const layers = useStore((s) => s.layers)
  const selectedId = useStore((s) => s.selectedLayerId)
  // subsets belong to the active 3-D view
  const paneId = useStore((s) => s.workspace.activePane)
  const ds = datasets.find((d) => d.id === activeId)
  const parent =
    layers.find((l) => l.id === selectedId && l.datasetId === activeId && layerInPane(l, { id: paneId })) ??
    layers.find((l) => l.datasetId === activeId && l.parentId === null)

  const tabs = useMemo(() => {
    if (!ds || !parent) return [] as Tab[]
    const t: Tab[] = ['region']
    if (ds.trace_mode) t.push('trace')
    return t
  }, [ds, parent])
  const [tab, setTab] = useState<Tab | null>(null)
  const current = tab && tabs.includes(tab) ? tab : tabs[0]

  if (!ds || !parent) return null
  return (
    <details className="panel subset">
      <summary>
        <h2>Highlight a region / traces</h2>
      </summary>
      <div className="muted small">
        a new layer from <b>{parent.name}</b>, styled on its own — e.g. the whole cell as grey lines (select{' '}
        <b>{parent.name}</b>, Style → Custom) with one region as coloured tubes (this layer, Style)
      </div>
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t} className={t === current ? 'active' : ''} onClick={() => setTab(t)}>
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {current === 'region' && <RegionTab ds={ds} parent={parent} paneId={paneId} />}
      {current === 'trace' && <TraceTab ds={ds} parent={parent} paneId={paneId} />}
    </details>
  )
}

function useCreateSubset(ds: DatasetSummary, parent: Layer, paneId: string) {
  const addLayer = useStore((s) => s.addLayer)
  const [error, setError] = useState<string | null>(null)
  const create = (own: LayerFilter, name?: string, style?: Partial<LayerStyle>) => {
    const filter = composeFilter(parent.filter, own)
    if (!filter) {
      setError(`Empty selection: ${describeFilter(own)} does not overlap ${parent.name}`)
      return
    }
    setError(null)
    // a subset reads as a highlight: coloured tubes over its parent (restyle it in Style)
    addLayer({ datasetId: ds.id, parentId: parent.id, name: name ?? describeFilter(own), filter, style: { ...parent.style, mode: 'tube', colorMode: 'rainbow', opacity: 1, ...style }, paneId })
  }
  return { create, error, setError }
}


function RegionTab({ ds, parent, paneId }: { ds: DatasetSummary; parent: Layer; paneId: string }) {
  const chroms = chromsOf(parent.filter, ds.chroms)
  const [chrom, setChrom] = useState(chroms[0]?.name ?? '')
  const [text, setText] = useState('')
  const { create, error, setError } = useCreateSubset(ds, parent, paneId)
  const info = chroms.find((c) => c.name === chrom) ?? chroms[0]
  if (!info) return null
  const lo = parent.filter.region?.chrom === info.name ? Math.max(info.start, parent.filter.region.start) : info.start
  const hi = parent.filter.region?.chrom === info.name ? Math.min(info.end, parent.filter.region.end) : info.end
  const submit = () => {
    try {
      // empty: the whole chromosome (within the parent)
      create({ region: text.trim() ? parseRegion({ ...info, start: lo, end: hi }, text) : { chrom: info.name, start: lo, end: hi } })
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <form
      className="op"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <Select value={info.name} onChange={(e) => setChrom(e.target.value)}>
        {chroms.map((c) => (
          <option key={c.name}>{c.name}</option>
        ))}
      </Select>
      <input placeholder="start-end, e.g. 10M-20M (empty: whole chromosome)" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="muted small">
        valid: {fmtBp(lo)}-{fmtBp(hi)}
      </div>
      <button type="submit">
        Create subset
      </button>
      {error && <div className="error">{error}</div>}
    </form>
  )
}

const PAGE = 500

function TraceTab({ ds, parent, paneId }: { ds: DatasetSummary; parent: Layer; paneId: string }) {
  const chroms = chromsOf(parent.filter, ds.chroms)
  const [chrom, setChrom] = useState<string>(chroms.length === 1 ? chroms[0].name : '')
  const [traces, setTraces] = useState<TraceInfo[]>([])
  const [total, setTotal] = useState(0)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const { create, error, setError } = useCreateSubset(ds, parent, paneId)

  const load = async (offset: number) => {
    setLoading(true)
    try {
      const page = await listTraces(ds.id, { chrom: chrom || undefined, offset, limit: PAGE })
      setTotal(page.total)
      setTraces((prev) => (offset === 0 ? page.traces : [...prev, ...page.traces]))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    setTraces([])
    void load(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds.id, chrom])

  // Restrict to the parent's trace subset when it has one.
  const visible = parent.filter.trace_ids ? traces.filter((t) => parent.filter.trace_ids!.includes(t.trace_id)) : traces
  const ids = visible.map((t) => t.trace_id)
  const submit = () => {
    try {
      const sel = parseTraceSelection(text, ids)
      create({ trace_ids: sel }, sel.length === 1 ? `trace ${sel[0]}` : `${text.trim()} (${sel.length} traces)`)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <form
      className="op"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <Select value={chrom} onChange={(e) => setChrom(e.target.value)}>
        {chroms.length > 1 && <option value="">all chromosomes</option>}
        {chroms.map((c) => (
          <option key={c.name}>{c.name}</option>
        ))}
      </Select>
      <ul className="trace-list">
        {visible.map((t, i) => (
          <li key={t.trace_id} onClick={() => setText(t.trace_id)} title={`${t.chrom}:${fmtBp(t.start)}-${fmtBp(t.end)}`}>
            <span className="idx">{i + 1}</span> {t.trace_id}
            <span className="muted"> {t.cell_id !== null ? `cell ${t.cell_id} · ` : ''}{t.n_spots} spots</span>
          </li>
        ))}
      </ul>
      {traces.length < total && (
        <button type="button" disabled={loading} onClick={() => void load(traces.length)}>
          {loading ? 'Loading…' : `Load more (${traces.length}/${total})`}
        </button>
      )}
      <input placeholder='id, "1-50", or "t1, t7, 3-5"' value={text} onChange={(e) => setText(e.target.value)} />
      <button type="submit" disabled={!text.trim()}>
        Create subset
      </button>
      {error && <div className="error">{error}</div>}
    </form>
  )
}

