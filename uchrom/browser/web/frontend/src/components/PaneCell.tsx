import type { GroupInfo } from '../groups'
import { defaultCategoryField, fieldKey, useStore } from '../store'

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

