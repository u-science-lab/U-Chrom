import { useMemo } from 'react'
import { clampLocus, datasetChroms, defaultLocus, type ChromExtent, type Locus } from './genome'
import { activeView, useStore } from './store'

/**
 * The shared genomic window of the active dataset, resolved against the
 * chromosomes it offers (spots + contact maps); null when it has none.
 */
export function useLocus(): { locus: Locus | null; chroms: ChromExtent[]; ext: ChromExtent | undefined; setLocus(l: Locus): void } {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const stored = useStore((s) => activeView(s).locus)
  const setLocus = useStore((s) => s.setLocus)
  const chroms = useMemo(() => datasetChroms(ds), [ds])
  const locus = useMemo(() => {
    const ext = stored ? chroms.find((c) => c.name === stored.chrom) : undefined
    return ext && stored ? clampLocus(stored, ext) : defaultLocus(chroms)
  }, [stored, chroms])
  const ext = locus ? chroms.find((c) => c.name === locus.chrom) : undefined
  return { locus, chroms, ext, setLocus }
}
