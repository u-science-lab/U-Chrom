import { useEffect, useState } from 'react'
import { fmtLocus, parseLocus, zoomLocus } from '../genome'
import { useLocus } from '../useLocus'
import { Select } from './Select'

/**
 * The genomic window, in the header of each view that shows it (Genome, Matrix, Stats on the locus
 * chromosome).  One window is shared: moving it in one view moves the others.
 */
export function LocusBar() {
  const { locus, chroms, ext, setLocus } = useLocus()
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (locus) setText(fmtLocus(locus))
    setError(null)
  }, [locus?.chrom, locus?.start, locus?.end]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!locus || !chroms.length) return null
  const go = () => {
    try {
      setLocus(parseLocus(text, chroms, locus))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <div className="locus-bar" title={error ?? 'Genomic window, shared by the Genome / Matrix / Stats views'}>
      <Select
        value={locus.chrom}
        onChange={(e) => {
          const c = chroms.find((x) => x.name === e.target.value)
          if (c) setLocus({ chrom: c.name, start: c.start, end: c.end })
        }}
      >
        {chroms.map((c) => (
          <option key={c.name}>{c.name}</option>
        ))}
      </Select>
      <input
        className={error ? 'bad' : ''}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && go()}
        onBlur={() => locus && setText(fmtLocus(locus))}
        spellCheck={false}
      />
      <button onClick={() => setLocus(zoomLocus(locus, 0.5, ext))} title="Zoom in">
        +
      </button>
      <button onClick={() => setLocus(zoomLocus(locus, 2, ext))} title="Zoom out">
        −
      </button>
      <button onClick={() => ext && setLocus({ chrom: ext.name, start: ext.start, end: ext.end })} title="Whole chromosome">
        full
      </button>
    </div>
  )
}
