import { describe, expect, it } from 'vitest'
import { extent, fmtAxis, hasOverlappingCells, histogram, integerBins, linear, logScale, mannWhitneyTwoSided, perCellMedians, statsChrom, statsRegion, trackRange } from './stats'
import { binIndexAt, defaultTrackSelection, resolveTracks } from './tracks'
import { defaultWorkspace, paneSignature, parseWorkspace, addPane, supportedPaneTypes, workspaceOf } from './workspace'
import { resolveSource } from './components/MatrixView'
import { availableKinds, drawPsChart, resolveKind, resolvePsMapKey } from './components/StatsView'
import { SvgContext2D } from './svgctx'

describe('histogram / scales', () => {
  it('bins finite values, max in the last bin', () => {
    const h = histogram([0, 1, 2, 3, 4, null, NaN], 4)
    expect(h.edges).toEqual([0, 1, 2, 3, 4])
    expect(h.counts).toEqual([1, 1, 1, 2])
    expect(histogram([], 3).counts).toEqual([0, 0, 0])
    expect(histogram([5, 5], 2).edges[0]).toBe(4.5)
  })
  it('integer values: bins of whole width, every bin the same number of integers', () => {
    const lig = Array.from({ length: 50 }, (_, i) => i + 1)
    const b = integerBins(lig, 40)!
    expect(b).toEqual({ nbins: 25, range: [0.5, 50.5] })
    expect(histogram(lig, b.nbins, b.range).counts.every((c) => c === 2)).toBe(true)
    expect(integerBins([1, 2, 3], 40)).toEqual({ nbins: 3, range: [0.5, 3.5] })
    expect(integerBins([1, 2.5], 40)).toBeNull()
    expect(integerBins([], 40)).toBeNull()
  })
  it('linear / log maps and extents', () => {
    expect(linear(0, 10, 100, 200)(5)).toBe(150)
    expect(logScale(1, 100, 0, 2)(10)).toBeCloseTo(1)
    expect(Number.isNaN(logScale(1, 100, 0, 2)(0))).toBe(true)
    expect(extent([3, null, 1])).toEqual([1, 3])
    expect(extent([])).toEqual([0, 1])
    expect(fmtAxis(1_500_000)).toBe('1.5M')
    expect(fmtAxis(0.01234)).toBe('0.012')
    expect(fmtAxis(0.00001)).toBe('1e-5')
  })
  it('track ranges: symmetric for z-scores, from 0 otherwise', () => {
    expect(trackRange([-1, 0.5, 2])).toEqual({ lo: -2, hi: 2, diverging: true })
    expect(trackRange([1, 5])).toEqual({ lo: 0, hi: 5, diverging: false })
    expect(trackRange([-3, -1])).toEqual({ lo: -3, hi: 0, diverging: false })
  })
})

describe('stats chromosome scope & window region', () => {
  it('uses all chromosomes by default, locus chromosome for locus, and locus interval for window', () => {
    expect(statsChrom(undefined, { chrom: 'chr15', start: 100, end: 200 })).toBeNull()
    expect(statsChrom('all', { chrom: 'chr15', start: 100, end: 200 })).toBeNull()
    expect(statsChrom('locus', { chrom: 'chr15', start: 100, end: 200 })).toBe('chr15')
    expect(statsChrom('locus', { chrom: '*', start: 0, end: 10_000 })).toBeNull()

    expect(statsRegion(undefined, { chrom: 'chr15', start: 100, end: 200 })).toEqual({ chrom: null, start: null, end: null })
    expect(statsRegion('locus', { chrom: 'chr15', start: 100, end: 200 })).toEqual({ chrom: 'chr15', start: null, end: null })
    expect(statsRegion('window', { chrom: 'chr15', start: 100, end: 200 })).toEqual({ chrom: 'chr15', start: 100, end: 200 })
    expect(statsRegion('window', { chrom: '*', start: 0, end: 10_000 })).toEqual({ chrom: null, start: null, end: null })
  })
})

describe('perCellMedians and mannWhitneyTwoSided', () => {
  it('computes per-cell medians ignoring nulls and handles ties/edge cases in Mann-Whitney', () => {
    const med = perCellMedians({
      trace_ids: ['t1', 't2', 't3', 't4', 't5'],
      cell_ids: ['c1', 'c1', 'c2', null, 'c3'],
      chroms: ['chr1', 'chr2', 'chr1', 'chr1', 'chr1'],
      rg: [1.0, 3.0, 5.0, 99.0, null],
      n_spots: [10, 10, 10, 10, 1],
      unit: 'um',
    })
    expect(med).toEqual([2.0, 5.0])

    expect(mannWhitneyTwoSided([], [1, 2])).toBeNull()
    expect(mannWhitneyTwoSided([1, 2], [NaN])).toBeNull()

    // No ties: separated small samples -> exact u and exploratory=true
    const sep = mannWhitneyTwoSided([10, 11, 12], [1, 2, 3])!
    expect(sep.u).toBe(9)
    expect(sep.rankBiserial).toBeCloseTo(1)
    expect(sep.exploratory).toBe(true)
    expect(sep.p).toBeGreaterThan(0)
    expect(sep.p).toBeLessThan(0.15)

    // Swapping groups complements U and negates rankBiserial
    const rev = mannWhitneyTwoSided([1, 2, 3], [10, 11, 12])!
    expect(rev.u).toBe(0)
    expect(rev.rankBiserial).toBeCloseTo(-1)
    expect(rev.p).toBeCloseTo(sep.p)

    // Exact ties -> p=1, r=0
    const allTied = mannWhitneyTwoSided([2, 2, 2, 2, 2], [2, 2, 2, 2, 2])!
    expect(allTied.p).toBe(1)
    expect(allTied.rankBiserial).toBe(0)
    expect(allTied.exploratory).toBe(false)

    // Partial ties with continuity correction: sum([0, 0.5, 0.5, 1.5, 2.5]) = 5
    const partial = mannWhitneyTwoSided([1, 2, 2, 3, 4], [2, 3, 4, 5, 6])!
    expect(partial.u).toBe(5)
    expect(partial.rankBiserial).toBeCloseTo(2 * 5 / 25 - 1)
    expect(partial.exploratory).toBe(false)
    expect(partial.p).toBeGreaterThan(0)
    expect(partial.p).toBeLessThanOrEqual(1)

    expect(hasOverlappingCells(['c0', 'c1', null], ['c2', 'c3'])).toBe(false)
    expect(hasOverlappingCells(['c0', 'c1'], ['c1', 'c2'])).toBe(true)
  })
})

describe('tracks', () => {
  const names = ['CPSF6', 'H3K9me3', 'h3k27ac', 'LaminB1', 'polyA_RNA']
  it('defaults to known marks, else the first tracks', () => {
    expect(defaultTrackSelection(names)).toEqual(['h3k27ac', 'H3K9me3', 'LaminB1'])
    expect(defaultTrackSelection(['a', 'b', 'c'], 2)).toEqual(['a', 'b'])
    expect(resolveTracks(['LaminB1', 'gone'], names)).toEqual(['LaminB1'])
    expect(resolveTracks(['gone'], names)).toEqual(['h3k27ac', 'H3K9me3', 'LaminB1'])
  })
  it('finds the bin under a position with slack', () => {
    expect(binIndexAt([0, 100], [25, 125], 110)).toBe(1)
    expect(binIndexAt([0, 100], [25, 125], 60)).toBe(-1)
    expect(binIndexAt([0, 100], [25, 125], 97, 5)).toBe(1)
  })
})

describe('default views per kind of data', () => {
  const sig = (k: Parameters<typeof defaultWorkspace>[0]) => paneSignature(defaultWorkspace(k))
  it('follows coords / embeddings / tracks', () => {
    expect(sig({ hasCoords: true, hasEmbeddings: true, hasTracks: true })).toBe('3d,embedding,genome,stats')
    expect(sig({ hasCoords: true, hasEmbeddings: false, hasTracks: false })).toBe('3d,genome,stats')
    expect(sig({ hasCoords: false, hasEmbeddings: true, hasTracks: false })).toBe('embedding')
    expect(sig({ hasCoords: false, hasEmbeddings: false, hasTracks: true, manyCells: true })).toBe('genome,stats')
    expect(sig({ hasCoords: false, hasEmbeddings: false, hasTracks: false })).toBe('matrix')
    expect(sig(true)).toBe('3d,embedding,genome,stats')
  })
  it('persists pane options and drops malformed ones', () => {
    const ws = addPane(workspaceOf(['3d', 'matrix']), 'matrix')
    ws.panes[1] = { ...ws.panes[1], source: 'distance', stat: 'contact', threshold: 0.3, tracks: ['H3K27ac'] }
    expect(parseWorkspace(JSON.parse(JSON.stringify(ws)))).toEqual(ws)
    const bad = parseWorkspace({ layout: 'tabs', panes: [{ id: 'a', type: 'stats', statsKind: 'pie', threshold: -1, tracks: [1] }] })
    expect(bad?.panes[0]).toEqual({ id: 'a', type: 'stats', embeddingKey: null, dims: [0, 1] })
  })
  it('resolves matrix sources and stats kinds against the data', () => {
    const maps = [{ key: 'bulk', kind: 'cool', label: '', resolutions: [1], chroms: [], per_cell: false, n_cells: 0 }]
    const p = { id: 'x', type: 'matrix' as const, embeddingKey: null, dims: [0, 1] as [number, number] }
    expect(resolveSource(p, maps, true)).toBe('bulk')
    expect(resolveSource({ ...p, source: 'distance' }, maps, true)).toBe('distance')
    expect(resolveSource({ ...p, source: 'distance' }, maps, false)).toBe('bulk')
    expect(resolveSource(p, [], true)).toBe('distance')
    expect(resolveSource(p, [], false)).toBeNull()
    expect(resolveKind({ ...p, statsKind: 'scatter' }, ['rg', 'scaling'])).toBe('rg')
    expect(resolveKind({ ...p, statsKind: 'hist' }, ['rg', 'hist'])).toBe('hist')
    expect(resolveKind(p, [])).toBeNull()
  })

  it('supports stats panes on contact-map-only datasets, ps/window/cell workspace options, and SvgContext2D ps capture', () => {
    expect(supportedPaneTypes({ hasCoords: false, hasEmbeddings: false, hasTracks: false, hasContactMaps: true })).toContain('stats')
    expect(availableKinds(false, false, true)).toEqual(['ps'])
    expect(availableKinds(true, true, true)).toEqual(['rg', 'scaling', 'ps', 'hist', 'scatter'])

    const maps = [
      { key: 'broken', kind: 'error' as const, label: '', resolutions: [], chroms: [], per_cell: false, n_cells: 0 },
      { key: 'cells', kind: 'scool' as const, label: '', resolutions: [500_000], chroms: [{ name: 'chr1', length: 1_000_000 }], per_cell: true, n_cells: 10 },
      { key: 'bulk', kind: 'cool' as const, label: '', resolutions: [500_000], chroms: [{ name: 'chr1', length: 1_000_000 }], per_cell: false, n_cells: 0 },
    ]
    expect(resolvePsMapKey(undefined, maps)).toBe('cells')
    expect(resolvePsMapKey('bulk', maps)).toBe('bulk')
    expect(resolvePsMapKey('broken', maps)).toBe('cells')

    const parsed = parseWorkspace({
      layout: 'tabs',
      panes: [{ id: 's1', type: 'stats', statsKind: 'ps', chromScope: 'window', rgUnit: 'cell', source: 'cells' }],
    })
    expect(parsed?.panes[0]).toMatchObject({ statsKind: 'ps', chromScope: 'window', rgUnit: 'cell', source: 'cells' })

    const rec = new SvgContext2D(1)
    drawPsChart(
      rec as unknown as CanvasRenderingContext2D,
      { x: 62, y: 14, w: 540, h: 350 },
      {
        pop: {
          key: 'cells',
          resolution: 500_000,
          chrom: 'chr1',
          start: 0,
          end: 100_000_000,
          sep_bp: [500_000, 1_000_000, 2_000_000],
          p: [0.2, 0.1, 0.05],
          n_pairs: [200, 199, 198],
          n_contacts: [40, 20, 10],
          slope: -1.0,
          intercept: 5.0,
          fit_range_bp: [500_000, 2_000_000],
          total_cis_contacts: 70,
          n_cells: 10,
        },
        cell: null,
      },
      [],
      null,
      null,
      null,
      '#ffffff',
    )
    expect(rec.unsupported.size).toBe(0)
    expect(rec.elements.length).toBeGreaterThan(0)
  })
})
