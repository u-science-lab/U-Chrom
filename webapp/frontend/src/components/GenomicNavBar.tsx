import { useAppStore } from '../store'

export default function GenomicNavBar() {
  const { viewport, setViewport } = useAppStore()

  const fmt = (pos: number) => pos >= 1e6 ? `${(pos/1e6).toFixed(2)}M` : pos >= 1e3 ? `${(pos/1e3).toFixed(1)}K` : String(pos)

  return (
    <div className="h-[48px] flex items-center justify-between px-6 border-t border-border-primary bg-bg-secondary">
      <div className="flex items-center gap-3">
        <label className="text-sm text-text-secondary">Chr:</label>
        <select
          value={viewport.chrom}
          onChange={(e) => setViewport({ ...viewport, chrom: e.target.value })}
          className="px-2 py-1 text-sm border border-border-primary rounded bg-bg-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
        >
          {Array.from({ length: 22 }, (_, i) => `chr${i + 1}`).concat(['chrX', 'chrY']).map(chr => (
            <option key={chr} value={chr}>{chr}</option>
          ))}
        </select>
      </div>
      <div className="text-sm text-text-secondary font-mono">
        {fmt(viewport.start)} — {fmt(viewport.end)}
      </div>
    </div>
  )
}
