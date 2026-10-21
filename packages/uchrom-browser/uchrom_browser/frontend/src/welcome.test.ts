import { describe, expect, it } from 'vitest'
import { datasetFacts, featuredDatasets, modalityLabels, thumbnailUrl } from './welcome'
import type { AtlasDataset, AtlasStudy } from './types'

const ds = (id: string, study: string, extra: Partial<AtlasDataset> = {}): AtlasDataset => ({ id, study, url: `https://a/${id}.chromdata.zarr`, title: id, n_cells: 10, ...extra })
const studies: AtlasStudy[] = [
  { id: 'guo', category: 'Spatial' },
  { id: 'chen', category: 'Spatial' },
  { id: 'stevens', category: 'Single-cell' },
  { id: 'liu', category: 'Single-cell' },
  { id: 'takei', category: 'Imaging' },
]
// in catalog order, as the public atlas lists them
const datasets = [ds('brain', 'guo'), ds('embryo', 'guo'), ds('e13', 'chen'), ds('mesc', 'stevens'), ds('hires', 'liu'), ds('cerebellum', 'takei')]

describe('start page examples', () => {
  it('one dataset of each kind of data, then of further studies, in catalog order', () => {
    expect(featuredDatasets({ title: 'a', studies, datasets }).map((d) => d.id)).toEqual(['brain', 'e13', 'mesc', 'cerebellum'])
    expect(featuredDatasets({ title: 'a', studies, datasets }, 3).map((d) => d.id)).toEqual(['brain', 'mesc', 'cerebellum'])
    expect(featuredDatasets({ title: 'a', studies, datasets }, 6)).toHaveLength(6)
  })
  it("the catalog's own choice first, unknown ids left out", () => {
    const featured = ['hires', 'nope', 'cerebellum', 'brain']
    expect(featuredDatasets({ title: 'a', studies, featured, datasets }).map((d) => d.id)).toEqual(['hires', 'cerebellum', 'brain'])
  })
  it('without studies or datasets', () => {
    expect(featuredDatasets({ title: 'a', datasets: [ds('x', 's1'), ds('y', 's1'), ds('z', 's2')] }, 2).map((d) => d.id)).toEqual(['x', 'z'])
    expect(featuredDatasets(null)).toEqual([])
  })
  it('modalities as the atlas page names them, bulk maps and embeddings left out', () => {
    expect(modalityLabels(ds('a', 's', { modalities: ['Hi-C per spot', 'Hi-C bulk', 'RNA', 'images', 'embeddings'] }))).toEqual(['Contact maps', 'RNA', 'Tissue images'])
    expect(modalityLabels(ds('a', 's', { modalities: ['ATAC per cell', 'new thing'] }))).toEqual(['Accessibility', 'new thing'])
  })
  it('spots for spatial data, cells otherwise; thumbnails by id', () => {
    expect(datasetFacts(ds('a', 'guo', { n_cells: 12474, sections: ['r1', 'r2'] }), studies[0])).toBe('12,474 spots · 2 sections')
    expect(datasetFacts(ds('a', 'stevens', { n_cells: 1 }), studies[2])).toBe('1 cell')
    expect(thumbnailUrl('https://atlas/figures', datasets[0])).toBe('https://atlas/figures/brain.space.webp')
    expect(thumbnailUrl(null, datasets[0])).toBeNull()
  })
})
