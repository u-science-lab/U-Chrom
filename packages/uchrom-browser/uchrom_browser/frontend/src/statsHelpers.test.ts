import { describe, expect, it } from 'vitest'
import { extent, fmtAxis, histogram, integerBins, linear, logScale, statsChrom, trackRange } from './stats'
import { binIndexAt, defaultTrackSelection, resolveTracks } from './tracks'
import { defaultWorkspace, paneSignature, parseWorkspace, addPane, workspaceOf } from './workspace'
import { resolveSource } from './components/MatrixView'
import { resolveKind } from './components/StatsView'

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
  })
  it('track ranges: symmetric for z-scores, from 0 otherwise', () => {
    expect(trackRange([-1, 0.5, 2])).toEqual({ lo: -2, hi: 2, diverging: true })
    expect(trackRange([1, 5])).toEqual({ lo: 0, hi: 5, diverging: false })
    expect(trackRange([-3, -1])).toEqual({ lo: -3, hi: 0, diverging: false })
  })
})

describe('stats chromosome scope', () => {
  it('uses all chromosomes by default and the whole locus chromosome when requested', () => {
    expect(statsChrom(undefined, { chrom: 'chr15', start: 100, end: 200 })).toBeNull()
    expect(statsChrom('all', { chrom: 'chr15', start: 100, end: 200 })).toBeNull()
    expect(statsChrom('locus', { chrom: 'chr15', start: 100, end: 200 })).toBe('chr15')
    expect(statsChrom('locus', { chrom: '*', start: 0, end: 10_000 })).toBeNull()
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
})
