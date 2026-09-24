import { describe, expect, it } from 'vitest'
import { chromsOf, composeFilter, describeFilter, fmtBp, parseGenomicNumber, parseRange, parseRegion, parseTraceSelection } from './filters'

const chr1 = { name: 'chr1', start: 3_000_000, end: 195_000_000, n_spots: 10, n_traces: 1 }
const chr2 = { name: 'chr2', start: 0, end: 180_000_000, n_spots: 10, n_traces: 1 }

describe('genomic parsing', () => {
  it('parses numbers with separators and suffixes', () => {
    expect(parseGenomicNumber('10,000,000')).toBe(10_000_000)
    expect(parseGenomicNumber('10M')).toBe(10_000_000)
    expect(parseGenomicNumber('1.5kb')).toBe(1500)
    expect(parseGenomicNumber(' 2_000 ')).toBe(2000)
    expect(() => parseGenomicNumber('ten')).toThrow()
    expect(() => parseGenomicNumber('5q')).toThrow()
  })

  it('parses ranges', () => {
    expect(parseRange('10,000,000-20,000,000')).toEqual({ start: 10e6, end: 20e6 })
    expect(parseRange('10M - 20M')).toEqual({ start: 10e6, end: 20e6 })
    expect(parseRange('10M..20M')).toEqual({ start: 10e6, end: 20e6 })
    expect(() => parseRange('20M-10M')).toThrow(/greater/)
    expect(() => parseRange('10M')).toThrow()
  })

  it('validates regions against the chromosome', () => {
    expect(parseRegion(chr1, '10M-20M')).toEqual({ chrom: 'chr1', start: 10e6, end: 20e6 })
    expect(() => parseRegion(chr1, '1M-2M')).toThrow(/outside/)
  })
})

describe('parseTraceSelection', () => {
  const ids = ['a', 'b', 'c', 'd', '7']
  it('accepts ids, 1-based ranges and mixes', () => {
    expect(parseTraceSelection('b', ids)).toEqual(['b'])
    expect(parseTraceSelection('1-3', ids)).toEqual(['a', 'b', 'c'])
    expect(parseTraceSelection('d, 1-2, a', ids)).toEqual(['d', 'a', 'b'])
  })
  it('prefers exact ids over index syntax', () => {
    expect(parseTraceSelection('7', ids)).toEqual(['7'])
    expect(parseTraceSelection('1-2', ['1-2', 'x'])).toEqual(['1-2'])
  })
  it('rejects unknown ids and bad ranges', () => {
    expect(() => parseTraceSelection('zz', ids)).toThrow(/unknown/)
    expect(() => parseTraceSelection('3-9', ids)).toThrow(/outside/)
    expect(() => parseTraceSelection(' , ', ids)).toThrow(/empty/)
  })
})

describe('composeFilter', () => {
  it('ANDs a child onto its parent', () => {
    expect(composeFilter({}, { chroms: ['chr1'] })).toEqual({ chroms: ['chr1'] })
    expect(composeFilter({ chroms: ['chr1', 'chr2'] }, { chroms: ['chr2', 'chr3'] })).toEqual({ chroms: ['chr2'] })
    expect(composeFilter({ chroms: ['chr1'] }, { region: { chrom: 'chr1', start: 0, end: 10 } })).toEqual({
      chroms: ['chr1'],
      region: { chrom: 'chr1', start: 0, end: 10 },
    })
    expect(composeFilter({ trace_ids: ['a', 'b'] }, { trace_ids: ['b', 'c'] })).toEqual({ trace_ids: ['b'] })
  })
  it('intersects nested regions', () => {
    const p = { region: { chrom: 'chr1', start: 0, end: 100 } }
    expect(composeFilter(p, { region: { chrom: 'chr1', start: 50, end: 150 } })).toEqual({ region: { chrom: 'chr1', start: 50, end: 100 } })
  })
  it('returns null for provably empty selections', () => {
    expect(composeFilter({ chroms: ['chr1'] }, { chroms: ['chr2'] })).toBeNull()
    expect(composeFilter({ chroms: ['chr1'] }, { region: { chrom: 'chr2', start: 0, end: 1 } })).toBeNull()
    expect(composeFilter({ region: { chrom: 'chr1', start: 0, end: 10 } }, { region: { chrom: 'chr1', start: 20, end: 30 } })).toBeNull()
    expect(composeFilter({ trace_ids: ['a'] }, { trace_ids: ['b'] })).toBeNull()
  })
  it('does not mutate inputs', () => {
    const parent = { chroms: ['chr1', 'chr2'] }
    composeFilter(parent, { chroms: ['chr1'] })
    expect(parent.chroms).toEqual(['chr1', 'chr2'])
  })
})

describe('chromsOf / describeFilter', () => {
  it('lists covered chromosomes in dataset order', () => {
    expect(chromsOf({}, [chr1, chr2]).map((c) => c.name)).toEqual(['chr1', 'chr2'])
    expect(chromsOf({ chroms: ['chr2'] }, [chr1, chr2]).map((c) => c.name)).toEqual(['chr2'])
    expect(chromsOf({ region: { chrom: 'chr1', start: 0, end: 1 } }, [chr1, chr2]).map((c) => c.name)).toEqual(['chr1'])
  })
  it('labels subsets', () => {
    expect(describeFilter({ region: { chrom: 'chr1', start: 10e6, end: 20e6 } })).toBe('chr1:10M-20M')
    expect(describeFilter({ chroms: ['chr1', 'chr2'] })).toBe('chr1, chr2')
    expect(describeFilter({ trace_ids: ['a', 'b', 'c', 'd'] })).toBe('4 traces')
    expect(describeFilter({})).toBe('all')
  })
})

describe('fmtBp', () => {
  it('uses one consistent unit per magnitude', () => {
    expect(fmtBp(136_550_000)).toBe('136.55M')
    expect(fmtBp(135_875_000)).toBe('135.875M')
    expect(fmtBp(25_000)).toBe('25k')
    expect(fmtBp(1_234_567)).toBe('1,234,567')
  })
})
