import { useEffect, useMemo } from 'react'
import { describeGroup, fieldGroupRef, parseFieldRef, resolveRowScope, resolveScope, type GroupInfo, type GroupRef, type RowScopeSpec, type Scope, type ScopeSpec } from './groups'
import { activeSavedGroups, activeView, fieldKey, useStore } from './store'
import type { CellField } from './types'
import { loadFieldValues } from './useOmicsLoader'

const NO_FIELDS: CellField[] = []

/** Categorical cell fields of the active dataset (the source of automatic groups). */
export function useCategoryFields(): CellField[] {
  const fields = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.cell_fields) ?? NO_FIELDS
  return useMemo(() => fields.filter((f) => f.kind === 'category'), [fields])
}

/**
 * Resolve group refs to name / colour / cells for the active dataset.
 * Field groups need that field's values: they are loaded on demand.
 */
export function useGroupInfos(refs: readonly (GroupRef | null | undefined)[]): (GroupInfo | null)[] {
  const dsId = useStore((s) => s.activeDatasetId)
  const fields = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.cell_fields) ?? NO_FIELDS
  const saved = useStore(activeSavedGroups)
  const selection = useStore((s) => activeView(s).selection)
  const cellValues = useStore((s) => s.cellValues)
  const key = refs.join('\u0001')
  useEffect(() => {
    if (!dsId) return
    for (const r of refs) {
      const f = r ? parseFieldRef(r) : null
      if (f) loadFieldValues(dsId, f.field)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dsId, key])
  return useMemo(
    () =>
      refs.map((r) =>
        r && dsId ? describeGroup(r, { fields, saved, selection, values: (f) => cellValues[fieldKey(dsId, f)] }) : null,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, dsId, fields, saved, selection, cellValues],
  )
}

export function useGroupInfo(ref: GroupRef | null | undefined): GroupInfo | null {
  return useGroupInfos([ref])[0]
}

/** The global focus (a cell, else a group / lasso selection). */
export function useFocusState() {
  const focusCell = useStore((s) => activeView(s).focusCell)
  const focusGroup = useStore((s) => activeView(s).focusGroup)
  return useMemo(() => ({ focusCell, focusGroup }), [focusCell, focusGroup])
}

/** What a pane's cells setting shows right now (absent = follow the focus). */
export function usePaneScope(pane: { scope?: ScopeSpec } | undefined): Scope {
  const focus = useFocusState()
  const key = JSON.stringify(pane?.scope ?? null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => resolveScope(pane?.scope, focus), [key, focus])
}

/** What a genome row's cells setting shows right now ("same as view" → the pane's). */
export function useRowScope(spec: RowScopeSpec | undefined, view: Scope): Scope {
  const focus = useFocusState()
  const key = JSON.stringify(spec ?? null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => resolveRowScope(spec, view, focus), [key, view, focus])
}

/** Cells of a scope as a set (null = all cells, or a group still loading → empty set). */
export function useScopeCells(scope: Scope): ReadonlySet<string> | null {
  const info = useGroupInfo(scope.kind === 'group' ? scope.group : null)
  return useMemo(() => {
    if (scope.kind === 'all') return null
    if (scope.kind === 'cell') return new Set([scope.cell])
    return new Set(info?.cells ?? [])
  }, [scope, info])
}

/** Every group on offer: one per category of each categorical field, then the saved ones. */
export function useGroupChoices(): { fields: { field: CellField; refs: GroupRef[] }[]; saved: GroupRef[] } {
  const cats = useCategoryFields()
  const saved = useStore(activeSavedGroups)
  return useMemo(
    () => ({
      fields: cats.map((f) => ({ field: f, refs: (f.categories ?? []).map((c) => fieldGroupRef(f.name, c.value)) })),
      saved: saved.map((g) => g.id),
    }),
    [cats, saved],
  )
}
