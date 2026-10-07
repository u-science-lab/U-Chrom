import { useEffect, useMemo, useState } from 'react'
import { autoRange, cmap, cmapGradient, COLORMAPS, effectiveRange, resolveColorScale, type ColorScale, type ColorScaleSetting, type MatrixKind } from '../colormaps'
import { hexToRgb, type RGB } from '../colors'
import { matrixPixels, scaleFor, type MatrixData } from '../matrix'
import { fmtAxis } from '../stats'
import { useStore } from '../store'
import { useTheme } from '../useTheme'
import { rgb } from './chart'
import { Select } from './Select'

/**
 * Colour scale of one matrix display (a Genome matrix row or the Matrix
 * view): colormap (with a preview strip), reverse, linear / log, and the
 * range — empty = automatic (percentile clip, shown as placeholders).
 * `value` holds only what differs from the defaults of `kind`.
 */
export function ColorScaleControls({
  kind,
  value,
  onChange,
  auto,
}: {
  kind: MatrixKind
  value: ColorScaleSetting | undefined
  onChange(next: ColorScaleSetting | undefined): void
  /** automatic range of the matrix on screen, if drawn */
  auto?: [number, number]
}) {
  const s = resolveColorScale(kind, value)
  const set = (patch: ColorScaleSetting) => {
    const next: ColorScaleSetting = { ...(value ?? {}), ...patch }
    for (const k of Object.keys(next) as (keyof ColorScaleSetting)[]) if (next[k] === null || next[k] === undefined) delete next[k]
    onChange(Object.keys(next).length ? next : undefined)
  }
  return (
    <div className="colorscale">
      <label className="insp-text small" title="Colormap">
        colormap
        <Select value={s.cmap} onChange={(e) => set({ cmap: e.target.value as ColorScaleSetting['cmap'] })}>
          {COLORMAPS.map((c) => (
            <option key={c.name} value={c.name}>
              {c.label}
            </option>
          ))}
        </Select>
      </label>
      <div className="cmap-preview" style={{ background: cmapGradient(s.cmap, s.reverse) }} title={`${s.cmap}${s.reverse ? ' (reversed)' : ''}: low → high`} />
      <div className="insp-line">
        <label className="check small" title="Swap the ends of the colormap">
          <input type="checkbox" checked={s.reverse} onChange={(e) => set({ reverse: e.target.checked })} /> reverse
        </label>
        <label className="insp-text small" title="Map values linearly, or log-scaled (log1p of the offset from the range start)">
          scale
          <Select value={s.log ? 'log' : 'linear'} onChange={(e) => set({ log: e.target.value === 'log' })}>
            <option value="linear">linear</option>
            <option value="log">log</option>
          </Select>
        </label>
      </div>
      <div className="insp-line">
        <span className="muted small">range</span>
        <RangeInput value={s.min} placeholder={auto ? fmtAxis(auto[0]) : 'auto'} onCommit={(v) => set({ min: v })} title="Minimum (empty = automatic)" />
        <span className="muted small">–</span>
        <RangeInput value={s.max} placeholder={auto ? fmtAxis(auto[1]) : 'auto'} onCommit={(v) => set({ max: v })} title="Maximum (empty = automatic: 99th percentile)" />
        {value && (
          <button className="link" onClick={() => onChange(undefined)} title="Back to the defaults for this matrix">
            reset
          </button>
        )}
      </div>
    </div>
  )
}

/** Number input committed on blur / Enter; empty → null (automatic). */
function RangeInput({ value, placeholder, title, onCommit }: { value: number | null; placeholder: string; title: string; onCommit(v: number | null): void }) {
  const [text, setText] = useState(value === null ? '' : String(value))
  useEffect(() => setText(value === null ? '' : String(value)), [value])
  const commit = () => {
    const t = text.trim()
    if (!t) return onCommit(null)
    const v = Number(t)
    if (Number.isFinite(v)) onCommit(v)
    else setText(value === null ? '' : String(value))
  }
  return (
    <input
      className="num range-input"
      value={text}
      placeholder={placeholder}
      title={title}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
    />
  )
}

/**
 * Everything a view needs to draw a matrix under its colour setting: the
 * resolved scale, the automatic and effective ranges (the automatic one is
 * published under `autoKey` for the inspector's placeholders), RGBA pixels
 * (missing values in the theme's colour) and the colour bar.
 */
export function useMatrixScale(mat: MatrixData | null, setting: ColorScaleSetting | undefined, autoKey: string) {
  const pal = useTheme()
  const kind: MatrixKind | null = mat ? scaleFor(mat.header.value) : null
  const settingKey = JSON.stringify(setting ?? null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const cs = useMemo<ColorScale | null>(() => (kind ? resolveColorScale(kind, setting) : null), [kind, settingKey])
  const diverging = !!cs && !!COLORMAPS.find((c) => c.name === cs.cmap)?.diverging
  const auto = useMemo<[number, number] | null>(() => (mat && kind ? autoRange(mat.data, kind, diverging) : null), [mat, kind, diverging])
  const setAuto = useStore((s) => s.setMatrixAuto)
  useEffect(() => {
    if (auto) setAuto(autoKey, auto)
  }, [auto, autoKey, setAuto])
  const range: [number, number] = auto && cs ? effectiveRange(auto, cs) : [0, 1]
  const missing = useMemo<RGB>(() => {
    try {
      return hexToRgb(pal.missing)
    } catch {
      return [0.38, 0.38, 0.4]
    }
  }, [pal.missing])
  const pixels = useMemo(() => (mat && cs ? matrixPixels(mat, cs, range, missing) : null), [mat, cs, range[0], range[1], missing]) // eslint-disable-line react-hooks/exhaustive-deps
  const ramp = (t: number) => (cs ? rgb(cmap(cs.cmap, t, cs.reverse)) : '#000')
  const lo = fmtAxis(range[0])
  // an automatic top is a percentile clip: values above share its colour
  const hi = `${cs && cs.max === null && kind !== 'frequency' ? '≥' : ''}${fmtAxis(range[1])}`
  const unit = mat?.header.unit ? ` (${mat.header.unit})` : ''
  const log = cs?.log ? ' (log)' : ''
  const title =
    kind === 'contacts' ? `${mat?.header.value === 'balanced' ? 'balanced' : 'contacts'}${log}` : kind === 'distance' ? `distance${unit}${log}` : `contact frequency${log}`
  return { kind, cs, auto, range, pixels, ramp, lo, hi, title }
}
