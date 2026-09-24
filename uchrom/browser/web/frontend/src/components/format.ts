/** Compact number: 1234 → "1,234", 0.01234 → "0.0123", 12.5 → "12.5". */
export function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  if (Number.isInteger(v)) return v.toLocaleString('en-US')
  const a = Math.abs(v)
  if (a >= 100) return Math.round(v).toLocaleString('en-US')
  if (a >= 1) return (+v.toFixed(2)).toString()
  return (+v.toPrecision(3)).toString()
}

import type { CellField, CellValue } from '../types'

/** A cell-field value for display: category strings as-is, numbers compact. */
export function fmtValue(v: CellValue | undefined): string {
  if (typeof v === 'string') return v
  return fmtNum(v)
}

/**
 * Cell fields worth colouring by: drop id-like columns (`*_id`) and put 0/1
 * flag columns last; otherwise keep the server's order.
 */
export function colourableFields(fields: CellField[]): CellField[] {
  const flag = (f: CellField) => f.min === 0 && f.max === 1
  return fields
    .filter((f) => !/(^|_)id$/i.test(f.name))
    .map((f, i) => ({ f, i }))
    .sort((a, b) => Number(flag(a.f)) - Number(flag(b.f)) || a.i - b.i)
    .map((x) => x.f)
}

/** Human label for a cell field name ("nucleus_area_um2" → "nucleus area (µm²)"). */
export function fieldLabel(name: string): string {
  const base = name.includes('.') ? name.slice(name.indexOf('.') + 1) : name
  return base
    .replace(/_um2$/, ' (µm²)')
    .replace(/_um$/, ' (µm)')
    .replace(/_/g, ' ')
}
