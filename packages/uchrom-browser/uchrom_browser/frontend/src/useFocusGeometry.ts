import { useEffect, useMemo, useRef } from 'react'
import { fetchGeometry } from './api'
import { isPartial, missingCells } from './geometry'
import { useFocusState, useGroupInfos } from './useGroups'
import { useStore } from './store'
import type { GroupRef } from './groups'

/** Points fetched at most per request for cells missing from an overview (whole segments, in order). */
const MAX_EXTRA_POINTS = 1_000_000

/**
 * Cells drawn in full -- the global focus (a cell or a group) and the 3-D views' own cell or group -- that a
 * layer's sampled or truncated overview does not hold are fetched and merged into that layer, so that they are
 * drawn (a large store's overview is a sample of its cells).  Each cell is requested once per layer.
 */
export function useFocusGeometry() {
  const focus = useFocusState()
  const panes = useStore((s) => s.workspace.panes)
  const layers = useStore((s) => s.layers)
  const dsId = useStore((s) => s.activeDatasetId)
  const requested = useRef(new Map<string, Set<string>>())

  const cells: string[] = []
  const groups: (GroupRef | null)[] = []
  if (focus.focusCell) cells.push(focus.focusCell)
  else if (focus.focusGroup) groups.push(focus.focusGroup)
  for (const p of panes) {
    if (p.type !== '3d' || !p.scope) continue
    if (p.scope.kind === 'cell') cells.push(p.scope.cell)
    else if (p.scope.kind === 'group') groups.push(p.scope.group)
  }
  const infos = useGroupInfos(groups)
  const key = JSON.stringify([cells, infos.map((i) => i?.cells?.length ?? -1), groups])
  const wanted = useMemo(() => {
    const out = new Set(cells)
    for (const i of infos) for (const c of i?.cells ?? []) out.add(c)
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => {
    if (!dsId || !wanted.size) return
    for (const l of layers) {
      if (l.datasetId !== dsId || !l.geometry || l.loading || !isPartial(l.geometry)) continue
      const asked = requested.current.get(l.id) ?? new Set<string>()
      const allowed = l.filter.cell_ids ? new Set(l.filter.cell_ids) : null
      const missing = missingCells(l.geometry, wanted).filter((c) => !asked.has(c) && (!allowed || allowed.has(c)))
      if (!missing.length) continue
      for (const c of missing) asked.add(c)
      requested.current.set(l.id, asked)
      // the global focus (not a view's own scope) flies the camera once its cells arrive
      const focusCells = new Set(focus.focusCell ? [focus.focusCell] : focus.focusGroup ? infos[0]?.cells ?? [] : [])
      fetchGeometry(dsId, { ...l.filter, cell_ids: missing }, MAX_EXTRA_POINTS)
        .then((g) => useStore.getState().extendGeometry(l.id, g, missing.some((c) => focusCells.has(c))))
        .catch(() => {
          for (const c of missing) asked.delete(c)        // try again with the next focus change
        })
    }
  }, [wanted, layers, dsId, focus, infos])
}
