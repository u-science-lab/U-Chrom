import { describe, expect, it } from 'vitest'
import { clampLocus, datasetChroms, defaultLocus, fmtLocus, fmtPos, fmtSpan, GENOME, genomeExtent, genomeToChrom, logTicks, niceTicks, panLocus, parseLocus, queryRegion, regionKey, zoomLocus } from './genome'

const chroms = [
  { name: 'chr7', start: 0, end: 150_000_000 },
  { name: 'chrX', start: 5_000_000, end: 170_000_000 },
]

describe('locus parsing', () => {
  it('parses chrom, chrom:range and bare ranges', () => {
    expect(parseLocus('chr7', chroms)).toEqual({ chrom: 'chr7', start: 0, end: 150_000_000 })
    expect(parseLocus('chr7:10.2M-12.5M', chroms)).toEqual({ chrom: 'chr7', start: 10_200_000, end: 12_500_000 })
    expect(parseLocus('CHRX:10,000,000-11,000,000', chroms)).toEqual({ chrom: 'chrX', start: 10_000_000, end: 11_000_000 })
    expect(parseLocus('20M-21M', chroms, { chrom: 'chrX', start: 0, end: 1 })).toEqual({ chrom: 'chrX', start: 20_000_000, end: 21_000_000 })
    expect(parseLocus('chr7:30M', chroms)).toEqual({ chrom: 'chr7', start: 29_500_000, end: 30_500_000 })
  })
  it('clamps into the chromosome and rejects nonsense', () => {
    expect(parseLocus('chrX:1M-6M', chroms)).toEqual({ chrom: 'chrX', start: 5_000_000, end: 6_000_000 })
    expect(() => parseLocus('chr9:1M-2M', chroms)).toThrow('unknown chromosome')
    expect(() => parseLocus('chr7:200M-210M', chroms)).toThrow('outside')
    expect(() => parseLocus('', chroms)).toThrow()
    expect(fmtLocus({ chrom: 'chr7', start: 10_200_000, end: 12_500_000 })).toBe('chr7:10.2M-12.5M')
  })
})

describe('zoom / pan', () => {
  const l = { chrom: 'chr7', start: 10_000_000, end: 20_000_000 }
  it('zooms around the centre or a given position and keeps it fixed', () => {
    expect(zoomLocus(l, 0.5, chroms[0])).toEqual({ chrom: 'chr7', start: 12_500_000, end: 17_500_000 })
    const z = zoomLocus(l, 0.5, chroms[0], 12_000_000) // 20 % into the window
    expect(z).toEqual({ chrom: 'chr7', start: 11_000_000, end: 16_000_000 })
    expect(zoomLocus(l, 100, chroms[0])).toEqual({ chrom: 'chr7', start: 0, end: 150_000_000 })
    const tiny = zoomLocus({ chrom: 'chr7', start: 0, end: 2000 }, 0.01, chroms[0])
    expect(tiny.end - tiny.start).toBe(1000) // MIN_SPAN
  })
  it('pans within bounds without shrinking', () => {
    expect(panLocus(l, 5_000_000, chroms[0])).toEqual({ chrom: 'chr7', start: 15_000_000, end: 25_000_000 })
    expect(panLocus(l, -50_000_000, chroms[0])).toEqual({ chrom: 'chr7', start: 0, end: 10_000_000 })
    expect(clampLocus({ chrom: 'chr7', start: 145_000_000, end: 155_000_000 }, chroms[0])).toEqual({ chrom: 'chr7', start: 140_000_000, end: 150_000_000 })
  })
})

describe('dataset chromosomes', () => {
  it('merges spot chromosomes with contact-map chromosomes', () => {
    const ds = {
      chroms: [{ name: 'chr1', start: 3_000_000, end: 4_000_000, n_spots: 1, n_traces: 1 }],
      contact_maps: [{ key: 'm', kind: 'cool', label: '', resolutions: [1], per_cell: false, n_cells: 0, chroms: [{ name: 'chr1', length: 195_000_000 }, { name: 'chr2', length: 180_000_000 }] }],
    }
    const c = datasetChroms(ds)
    expect(c).toEqual([
      { name: 'chr1', start: 0, end: 195_000_000 },
      { name: 'chr2', start: 0, end: 180_000_000 },
    ])
    expect(defaultLocus(c)).toEqual({ chrom: 'chr1', start: 0, end: 195_000_000 })
    expect(defaultLocus([])).toBeNull()
  })
})

describe('ticks', () => {
  it('nice linear and decade ticks', () => {
    expect(niceTicks(0, 10, 5)).toEqual([0, 2, 4, 6, 8, 10])
    expect(niceTicks(10_200_000, 12_500_000, 4)).toEqual([11_000_000, 12_000_000])
    expect(niceTicks(10_200_000, 12_500_000, 8)).toEqual([10_500_000, 11_000_000, 11_500_000, 12_000_000, 12_500_000])
    expect(niceTicks(1, 1)).toEqual([])
    expect(logTicks(3e4, 2e6)).toEqual([1e5, 1e6])
    expect(logTicks(0, 10)).toEqual([])
  })
})

describe('locus stays in whole bp', () => {
  it('zoom / pan without a chromosome extent round the window', () => {
    const l = { chrom: 'chr4', start: 14_000_000, end: 15_000_000 }
    const z = zoomLocus(l, 0.37, undefined, 14_326_200.86)
    expect(Number.isInteger(z.start) && Number.isInteger(z.end)).toBe(true)
    const p = panLocus(l, 1234.56)
    expect(p).toEqual({ chrom: 'chr4', start: 14_001_235, end: 15_001_235 })
  })
})

describe('whole genome', () => {
  const layout = [
    { name: 'chr1', offset: 0, length: 100 },
    { name: 'chr2', offset: 100, length: 50 },
    { name: 'chrX', offset: 150, length: 30 },
  ]
  const ds = {
    chroms: [
      { name: 'chr1', start: 0, end: 100, n_spots: 0, n_traces: 0 },
      { name: 'chr2', start: 0, end: 50, n_spots: 0, n_traces: 0 },
    ],
    contact_maps: [],
    genome: layout,
  } as unknown as Parameters<typeof datasetChroms>[0]
  it('offers All first; the default stays the first chromosome', () => {
    const chroms = datasetChroms(ds)
    expect(chroms[0]).toMatchObject({ name: GENOME, start: 0, end: 180 })
    expect(defaultLocus(chroms)).toEqual({ chrom: 'chr1', start: 0, end: 100 })
    expect(genomeExtent(layout.slice(0, 1))).toBeNull() // one chromosome: no genome view
  })
  it('maps genome coordinates to chromosomes', () => {
    expect(genomeToChrom(layout, 0)).toEqual({ chrom: 'chr1', pos: 0 })
    expect(genomeToChrom(layout, 120)).toEqual({ chrom: 'chr2', pos: 20 })
    expect(genomeToChrom(layout, 180)).toEqual({ chrom: 'chrX', pos: 30 })
    expect(genomeToChrom(layout, 181)).toBeNull()
    expect(fmtPos(GENOME, 120_000_000, [{ name: 'chr1', offset: 0, length: 100_000_000 }, { name: 'chr2', offset: 100_000_000, length: 90_000_000 }])).toBe('chr2:20M')
    expect(fmtPos('chr7', 1500)).toBe('chr7:1.5k')
    expect(fmtSpan(GENOME, 110, 120, layout)).toBe('chr2:10-20')
  })
  it('parses and formats genome windows', () => {
    const M = 1_000_000
    const big = {
      chroms: [
        { name: 'chr1', start: 0, end: 100 * M, n_spots: 0, n_traces: 0 },
        { name: 'chr2', start: 0, end: 50 * M, n_spots: 0, n_traces: 0 },
      ],
      contact_maps: [],
      genome: [
        { name: 'chr1', offset: 0, length: 100 * M },
        { name: 'chr2', offset: 100 * M, length: 50 * M },
      ],
    } as unknown as Parameters<typeof datasetChroms>[0]
    const chroms = datasetChroms(big)
    expect(parseLocus('All', chroms)).toEqual({ chrom: GENOME, start: 0, end: 150 * M })
    expect(parseLocus('genome', chroms).chrom).toBe(GENOME)
    const w = parseLocus('chr1:50M-chr2:20M', chroms)
    expect(w).toEqual({ chrom: GENOME, start: 50 * M, end: 120 * M })
    expect(fmtLocus({ chrom: GENOME, start: 0, end: 150 * M }, chroms)).toBe('All')
    expect(fmtLocus(w, chroms)).toBe('chr1:50M-chr2:20M')
    expect(parseLocus('chr2:10M-20M', chroms)).toEqual({ chrom: 'chr2', start: 10 * M, end: 20 * M })
    expect(queryRegion({ chrom: GENOME, start: 5, end: 9 })).toEqual({ chrom: GENOME })
    expect(regionKey({ chrom: GENOME, start: 5, end: 9 })).toBe(regionKey({ chrom: GENOME, start: 0, end: 180 }))
  })
})
