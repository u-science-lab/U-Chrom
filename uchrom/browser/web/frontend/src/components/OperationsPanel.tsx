import { useEffect, useMemo, useState } from 'react'
import { listCells, listTraces } from '../api'
import { chromsOf, composeFilter, describeFilter, fmtBp, parseIdSelection, parseRegion, parseTraceSelection } from '../filters'
import { useStore } from '../store'
import type { CellInfo, DatasetSummary, Layer, LayerFilter, LayerStyle, TraceInfo } from '../types'

type Tab = 'cell' | 'chrom' | 'region' | 'trace'

const TAB_LABEL: Record<Tab, string> = { cell: 'Cell', chrom: 'Chromosome', region: 'Region', trace: 'Trace' }

export function OperationsPanel() {
  const datasets = useStore((s) => s.datasets)
  const activeId = useStore((s) => s.activeDatasetId)
  const layers = useStore((s) => s.layers)
  const selectedId = useStore((s) => s.selectedLayerId)
  const ds = datasets.find((d) => d.id === activeId)
  const parent =
    layers.find((l) => l.id === selectedId && l.datasetId === activeId) ??
    layers.find((l) => l.datasetId === activeId && l.parentId === null)

  const tabs = useMemo(() => {
    if (!ds || !parent) return [] as Tab[]
    const t: Tab[] = []
    // Imaging data with many cells: looking at one nucleus at a time is the
    // main way to see anything, so Cell comes first.
    if (ds.n_cells > 1 && !(parent.filter.cell_ids?.length === 1)) t.push('cell')
    if (chromsOf(parent.filter, ds.chroms).length > 1) t.push('chrom')
    t.push('region')
    if (ds.trace_mode) t.push('trace')
    return t
  }, [ds, parent])
  const [tab, setTab] = useState<Tab | null>(null)
  const current = tab && tabs.includes(tab) ? tab : tabs[0]

  if (!ds || !parent) return null
  return (
    <section className="panel">
      <h2>Operations</h2>
      <div className="muted small">
        subset of <b>{parent.name}</b>
      </div>
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t} className={t === current ? 'active' : ''} onClick={() => setTab(t)}>
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {current === 'cell' && <CellTab ds={ds} parent={parent} />}
      {current === 'chrom' && <ChromTab ds={ds} parent={parent} />}
      {current === 'region' && <RegionTab ds={ds} parent={parent} />}
      {current === 'trace' && <TraceTab ds={ds} parent={parent} />}
    </section>
  )
}

function useCreateSubset(ds: DatasetSummary, parent: Layer) {
  const addLayer = useStore((s) => s.addLayer)
  const [error, setError] = useState<string | null>(null)
  const create = (own: LayerFilter, name?: string, style?: Partial<LayerStyle>) => {
    const filter = composeFilter(parent.filter, own)
    if (!filter) {
      setError(`Empty selection: ${describeFilter(own)} does not overlap ${parent.name}`)
      return
    }
    setError(null)
    addLayer({ datasetId: ds.id, parentId: parent.id, name: name ?? describeFilter(own), filter, style: { ...parent.style, ...style } })
  }
  return { create, error, setError }
}

function ChromTab({ ds, parent }: { ds: DatasetSummary; parent: Layer }) {
  const chroms = chromsOf(parent.filter, ds.chroms)
  const [picked, setPicked] = useState<string[]>([])
  const { create, error } = useCreateSubset(ds, parent)
  return (
    <div className="op">
      <select multiple size={Math.min(8, chroms.length)} value={picked} onChange={(e) => setPicked(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {chroms.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name} ({c.n_spots.toLocaleString('en-US')})
          </option>
        ))}
      </select>
      <button disabled={!picked.length} onClick={() => create({ chroms: picked })}>
        Create subset
      </button>
      {error && <div className="error">{error}</div>}
    </div>
  )
}

function RegionTab({ ds, parent }: { ds: DatasetSummary; parent: Layer }) {
  const chroms = chromsOf(parent.filter, ds.chroms)
  const [chrom, setChrom] = useState(chroms[0]?.name ?? '')
  const [text, setText] = useState('')
  const { create, error, setError } = useCreateSubset(ds, parent)
  const info = chroms.find((c) => c.name === chrom) ?? chroms[0]
  if (!info) return null
  const lo = parent.filter.region?.chrom === info.name ? Math.max(info.start, parent.filter.region.start) : info.start
  const hi = parent.filter.region?.chrom === info.name ? Math.min(info.end, parent.filter.region.end) : info.end
  const submit = () => {
    try {
      create({ region: parseRegion({ ...info, start: lo, end: hi }, text) })
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
      <select value={info.name} onChange={(e) => setChrom(e.target.value)}>
        {chroms.map((c) => (
          <option key={c.name}>{c.name}</option>
        ))}
      </select>
      <input placeholder="start-end, e.g. 10M-20M" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="muted small">
        valid: {fmtBp(lo)}-{fmtBp(hi)}
      </div>
      <button type="submit" disabled={!text.trim()}>
        Create subset
      </button>
      {error && <div className="error">{error}</div>}
    </form>
  )
}

const PAGE = 500

function TraceTab({ ds, parent }: { ds: DatasetSummary; parent: Layer }) {
  const chroms = chromsOf(parent.filter, ds.chroms)
  const [chrom, setChrom] = useState<string>(chroms.length === 1 ? chroms[0].name : '')
  const [traces, setTraces] = useState<TraceInfo[]>([])
  const [total, setTotal] = useState(0)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const { create, error, setError } = useCreateSubset(ds, parent)

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
      <select value={chrom} onChange={(e) => setChrom(e.target.value)}>
        {chroms.length > 1 && <option value="">all chromosomes</option>}
        {chroms.map((c) => (
          <option key={c.name}>{c.name}</option>
        ))}
      </select>
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

function CellTab({ ds, parent }: { ds: DatasetSummary; parent: Layer }) {
  const [cells, setCells] = useState<CellInfo[]>([])
  const [total, setTotal] = useState(0)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const { create, error, setError } = useCreateSubset(ds, parent)

  const load = async (offset: number) => {
    setLoading(true)
    try {
      const page = await listCells(ds.id, { offset, limit: PAGE })
      setTotal(page.total)
      setCells((prev) => (offset === 0 ? page.cells : [...prev, ...page.cells]))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    setCells([])
    void load(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds.id])

  const visible = parent.filter.cell_ids ? cells.filter((c) => parent.filter.cell_ids!.includes(c.cell_id)) : cells
  const ids = visible.map((c) => c.cell_id)
  const submit = (raw = text) => {
    try {
      const sel = parseIdSelection(raw, ids, 'cell')
      // a single nucleus is small enough to draw as tubes
      create({ cell_ids: sel }, sel.length === 1 ? `cell ${sel[0]}` : `${raw.trim()} (${sel.length} cells)`, { mode: 'tube' })
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
      <ul className="trace-list">
        {visible.map((c, i) => (
          <li
            key={c.cell_id}
            onClick={() => setText(c.cell_id)}
            onDoubleClick={() => submit(c.cell_id)}
            title="double-click to open this cell"
          >
            <span className="idx">{i + 1}</span> {c.cell_id}
            <span className="muted">
              {' '}
              {c.n_traces} traces · {c.n_chroms} chroms · {c.n_spots.toLocaleString('en-US')} spots
            </span>
          </li>
        ))}
      </ul>
      {cells.length < total && (
        <button type="button" disabled={loading} onClick={() => void load(cells.length)}>
          {loading ? 'Loading…' : `Load more (${cells.length}/${total})`}
        </button>
      )}
      <input placeholder='cell id, "1-10", or "c1, c7"' value={text} onChange={(e) => setText(e.target.value)} />
      <button type="submit" disabled={!text.trim()}>
        Create subset
      </button>
      {error && <div className="error">{error}</div>}
    </form>
  )
}
