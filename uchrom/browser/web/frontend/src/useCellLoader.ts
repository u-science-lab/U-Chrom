import { useEffect } from 'react'
import { listCells } from './api'
import { useStore } from './store'

/** Fetch the cell table once per dataset that has cells. */
export function useCellLoader() {
  const datasets = useStore((s) => s.datasets)
  useEffect(() => {
    const { cells, setCells, setError } = useStore.getState()
    for (const ds of datasets) {
      if (ds.n_cells < 2 || cells[ds.id]) continue
      setCells(ds.id, []) // mark as requested
      listCells(ds.id, { limit: 100_000 })
        .then((page) => setCells(ds.id, page.cells))
        .catch((e: Error) => setError(`Cannot list cells: ${e.message}`))
    }
  }, [datasets])
}
