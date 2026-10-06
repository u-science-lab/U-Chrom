import type { DistanceStat, TrackAgg } from '../workspace'
import { Select } from './Select'

/**
 * What a 3-D distance matrix shows, and — only when its cells setting
 * covers more than one cell — how the traces are aggregated.  Contact
 * frequency is itself an aggregate (fraction of traces within a threshold).
 */
export function DistanceValueControls({
  stat,
  multi,
  onStat,
  threshold,
}: {
  stat: DistanceStat
  /** the scope has several cells: offer the aggregate */
  multi: boolean
  onStat(s: DistanceStat): void
  /** the threshold input (contact frequency only) */
  threshold?: React.ReactNode
}) {
  const contact = stat === 'contact'
  return (
    <>
      <label className="insp-text small" title="Distance, or the fraction of traces closer than a threshold">
        show
        <Select value={contact ? 'contact' : 'distance'} onChange={(e) => onStat(e.target.value === 'contact' ? 'contact' : 'median')}>
          <option value="distance">3-D distance</option>
          <option value="contact">contact frequency</option>
        </Select>
      </label>
      {!contact && multi && (
        <label className="insp-text small" title="Aggregate over the traces of the cells in scope">
          aggregate
          <Select value={stat} onChange={(e) => onStat(e.target.value as DistanceStat)}>
            <option value="median">median</option>
            <option value="mean">mean</option>
          </Select>
        </label>
      )}
      {contact && threshold}
    </>
  )
}

/** How spots of the cells in scope are aggregated per bin (only with more than one cell). */
export function TrackAggregateControl({ agg, multi, onAgg }: { agg: TrackAgg; multi: boolean; onAgg(a: TrackAgg): void }) {
  if (!multi) return null
  return (
    <label className="insp-text small" title="Aggregate the spots of the cells in scope in each bin">
      aggregate
      <Select value={agg} onChange={(e) => onAgg(e.target.value as TrackAgg)}>
        <option value="mean">mean</option>
        <option value="median">median</option>
        <option value="max">max</option>
      </Select>
    </label>
  )
}
