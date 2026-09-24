import { useEffect } from 'react'
import { fetchCellValues, fetchPointSet } from './api'
import { activeView, fieldKey, useStore } from './store'

const requested = new Set<string>()

/**
 * Lazy loaders for the multi-omics layers: the overview field's per-cell
 * values (once per dataset+field) and every point set (once per dataset).
 */
export function useOmicsLoader() {
  const datasets = useStore((s) => s.datasets)
  const activeId = useStore((s) => s.activeDatasetId)
  const view = useStore(activeView)

  useEffect(() => {
    const { setPointSet, setError } = useStore.getState()
    for (const ds of datasets) {
      for (const info of ds.point_sets ?? []) {
        const key = `points\u0000${ds.id}\u0000${info.name}`
        if (requested.has(key)) continue
        requested.add(key)
        fetchPointSet(ds.id, info.name)
          .then((ps) => setPointSet(ds.id, ps))
          .catch((e: Error) => setError(`Cannot load point set ${info.name}: ${e.message}`))
      }
    }
  }, [datasets])

  useEffect(() => {
    const field = view.cellField
    if (!activeId || !field) return
    const key = fieldKey(activeId, field)
    if (requested.has(key) || useStore.getState().cellValues[key]) return
    requested.add(key)
    fetchCellValues(activeId, field)
      .then((r) => {
        const m = new Map<string, number | null>()
        r.cell_ids.forEach((c, i) => m.set(String(c), r.values[i]))
        useStore.getState().setCellValues(activeId, field, m)
      })
      .catch((e: Error) => {
        requested.delete(key)
        useStore.getState().setError(`Cannot load ${field}: ${e.message}`)
      })
  }, [activeId, view.cellField])
}
