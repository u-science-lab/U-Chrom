import { useEffect, useState } from 'react'
import { fetchStore } from '../api'
import { fmtSize } from '../datasets'
import { useStore } from '../store'
import type { StoreNode } from '../types'

/**
 * Left side bar, "Store" tab: the on-disk structure of the active dataset's store —
 * Zarr groups and arrays (shape, dtype, chunks), Parquet tables (rows, columns), sizes and
 * attributes.  Groups open with a click; arrays and tables show their details.
 */
export function StorePanel() {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const [tree, setTree] = useState<StoreNode | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!ds) return
    let live = true
    setTree(null)
    setError(null)
    fetchStore(ds.id)
      .then((t) => live && setTree(t))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [ds?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!ds) return <p className="muted small store-empty">Open a dataset.</p>
  if (error) return <p className="muted small store-empty">{error}</p>
  if (!tree) return <p className="muted small store-empty">Reading the store…</p>
  const meta = tree.meta ?? parseAttr(tree.attrs?.uchrom)
  return (
    <div className="store-panel">
      <div className="store-head">
        <div className="store-title" title={ds.path}>
          {tree.name}
        </div>
        <div className="muted small">
          {tree.container === 'cdz' ? 'one zip file (.cdz)' : 'Zarr v3 directory'} · {fmtSize(tree.bytes)}
          {meta?.format_version ? ` · format ${meta.format_version}` : ''}
        </div>
        {meta && (
          <div className="store-facts small">
            {(['n_spots', 'n_bins', 'n_traces', 'n_cells'] as const).map((k) =>
              typeof meta[k] === 'number' ? (
                <span key={k}>
                  <b>{(meta[k] as number).toLocaleString('en-US')}</b> {k.slice(2)}
                </span>
              ) : null,
            )}
          </div>
        )}
      </div>
      <ul className="store-tree" role="tree">
        {(tree.children ?? []).map((c) => (
          <StoreRow key={c.path} node={c} depth={0} />
        ))}
      </ul>
      {tree.attrs && <Attrs attrs={tree.attrs} />}
    </div>
  )
}

function StoreRow({ node, depth }: { node: StoreNode; depth: number }) {
  const container = node.kind === 'group' || node.kind === 'dir'
  // top-level groups open; deeper ones on demand
  const [open, setOpen] = useState(container && depth === 0 && (node.children?.length ?? 0) <= 12)
  const hasDetails = node.kind === 'table' || node.kind === 'array' || !!node.attrs
  const expandable = container ? (node.children?.length ?? 0) > 0 || !!node.attrs : hasDetails
  return (
    <li role="treeitem" aria-expanded={expandable ? open : undefined}>
      <button className={`store-row k-${node.kind}`} style={{ paddingLeft: 4 + depth * 12 }} onClick={() => expandable && setOpen(!open)} title={node.path}>
        <span className="store-caret" aria-hidden>
          {expandable ? (open ? '▾' : '▸') : ''}
        </span>
        <span className="store-icon" aria-hidden>
          {ICON[node.kind]}
        </span>
        <span className="store-name">{node.name}</span>
        <span className="store-size">{fmtSize(node.bytes)}</span>
      </button>
      <div className="store-sub muted" style={{ paddingLeft: 30 + depth * 12 }}>
        {summary(node)}
      </div>
      {open && (
        <>
          {node.kind === 'table' && node.columns && (
            <div className="store-cols" style={{ marginLeft: 30 + depth * 12 }}>
              {node.columns.map((c) => (
                <code key={c}>{c}</code>
              ))}
            </div>
          )}
          {node.attrs && (
            <div style={{ marginLeft: 30 + depth * 12 }}>
              <Attrs attrs={node.attrs} />
            </div>
          )}
          {container && (
            <ul role="group">
              {(node.children ?? []).map((c) => (
                <StoreRow key={c.path} node={c} depth={depth + 1} />
              ))}
              {!!node.more && (
                <li className="muted small" style={{ paddingLeft: 30 + depth * 12 }}>
                  … {node.more} more
                </li>
              )}
            </ul>
          )}
        </>
      )}
    </li>
  )
}

function Attrs({ attrs }: { attrs: Record<string, string> }) {
  return (
    <dl className="store-attrs">
      {Object.entries(attrs).map(([k, v]) => (
        <div key={k}>
          <dt>@{k}</dt>
          <dd title={v}>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

const ICON: Record<StoreNode['kind'], string> = { group: '▣', dir: '▢', array: '▦', table: '▤', file: '·' }

/** One line under a node: what it holds. */
export function summary(n: StoreNode): string {
  const f = (x: number) => x.toLocaleString('en-US')
  switch (n.kind) {
    case 'array':
      return [n.shape ? n.shape.map(f).join(' × ') || 'scalar' : null, n.dtype, n.n_chunks !== undefined ? `${n.n_chunks} chunk${n.n_chunks === 1 ? '' : 's'}` : null].filter(Boolean).join(' · ')
    case 'table':
      return n.error ?? `${f(n.rows ?? 0)} rows · ${n.columns?.length ?? 0} columns · ${n.row_groups ?? 0} row group${n.row_groups === 1 ? '' : 's'}`
    case 'group':
    case 'dir': {
      const k = n.children?.length ?? 0
      return `${n.kind === 'group' ? 'group' : 'folder'} · ${k} item${k === 1 ? '' : 's'}`
    }
    default:
      return 'file'
  }
}

/** A JSON attribute preview → object (null when cut short or not an object). */
function parseAttr(v: string | undefined): Record<string, unknown> | null {
  if (!v) return null
  try {
    const o = JSON.parse(v)
    return o && typeof o === 'object' && !Array.isArray(o) ? o : null
  } catch {
    return null
  }
}
