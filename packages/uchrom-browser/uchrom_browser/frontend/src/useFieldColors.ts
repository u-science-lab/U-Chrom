import { useMemo } from 'react'
import { categoryIndex, fieldRange } from './colors'
import { activeFieldValues, activeView, useStore } from './store'
import type { CellField, CellValue } from './types'

export interface FieldColors {
  /** the overview field (null when not colouring by a field) */
  field: CellField | null
  cellValues?: ReadonlyMap<string, CellValue>
  /** numeric fields: colour range */
  fieldRange?: [number, number]
  /** categorical fields: category → legend index (−1 = hidden) */
  categories?: ReadonlyMap<string, number>
}

/** Field info of the active overview colouring (stable reference). */
export function useOverviewField(): CellField | null {
  return useStore((s) => {
    const v = activeView(s)
    if (v.overviewColor !== 'field' || !v.cellField) return null
    return s.datasets.find((d) => d.id === s.activeDatasetId)?.cell_fields?.find((f) => f.name === v.cellField) ?? null
  })
}

/**
 * Colour options of the overview field, shared by every view that colours
 * cells (3-D overview, embedding, scatter, cell list, legend) so they agree.
 */
export function useFieldColors(): FieldColors {
  const field = useOverviewField()
  const values = useStore(activeFieldValues)
  const hidden = useStore((s) => activeView(s).hiddenCategories)
  return useMemo(() => {
    if (!field) return { field: null }
    const cellValues = values ?? undefined
    if (field.kind === 'category') return { field, cellValues, categories: categoryIndex(field, hidden, values?.values()) }
    return { field, cellValues, fieldRange: values ? fieldRange(values.values()) : undefined }
  }, [field, values, hidden])
}
