/**
 * The start page (no dataset open): which atlas datasets it offers as examples and how it describes them.
 */
import type { AtlasDataset, AtlasResponse, AtlasStudy } from './types'

type Catalog = NonNullable<AtlasResponse['catalog']>

/** Examples on the start page. */
export const N_FEATURED = 4

/**
 * The datasets the start page offers: the catalog's `featured` list when it has one; otherwise one dataset of each
 * kind of data (the studies' `category`: spatial, single-cell, imaging …), then one of each further study, in
 * catalog order — so that the examples show the assays the atlas holds.
 */
export function featuredDatasets(catalog: Catalog | null | undefined, n = N_FEATURED): AtlasDataset[] {
  const all = catalog?.datasets ?? []
  const byId = new Map(all.map((d) => [d.id, d]))
  const pinned = (catalog?.featured ?? []).map((id) => byId.get(id)).filter((d): d is AtlasDataset => !!d)
  if (pinned.length) return pinned.slice(0, n)
  const studies = studyIndex(catalog?.studies)
  const picked = new Set<AtlasDataset>()
  const categories = new Set<string>()
  const seenStudies = new Set<string>()
  const take = (d: AtlasDataset) => {
    picked.add(d)
    seenStudies.add(d.study ?? d.id)
  }
  for (const d of all) {
    const c = studies.get(d.study ?? '')?.category
    if (picked.size < n && c && !categories.has(c)) {
      categories.add(c)
      take(d)
    }
  }
  for (const d of all) if (picked.size < n && !seenStudies.has(d.study ?? d.id)) take(d)
  for (const d of all) if (picked.size < n) picked.add(d)
  return all.filter((d) => picked.has(d))
}

export function studyIndex(studies: AtlasStudy[] | undefined): Map<string, AtlasStudy> {
  return new Map((studies ?? []).map((s) => [s.id, s]))
}

/** What the catalog's modality names are called on the page (as on the atlas page); bulk maps and embeddings left out. */
const MODALITY_LABELS: Record<string, string | null> = {
  'Hi-C per spot': 'Contact maps',
  'Hi-C per cell': 'Contact maps',
  'Hi-C bulk': null,
  '3-D coordinates': '3-D structures',
  'A/B per spot': 'A/B compartments',
  RNA: 'RNA',
  'ATAC per spot': 'Accessibility',
  'ATAC per cell': 'Accessibility',
  images: 'Tissue images',
  'signals per spot': 'Signals per locus',
  embeddings: null,
}

export function modalityLabels(d: AtlasDataset): string[] {
  const out: string[] = []
  for (const m of d.modalities ?? []) {
    const label = m in MODALITY_LABELS ? MODALITY_LABELS[m] : m
    if (label && !out.includes(label)) out.push(label)
  }
  return out
}

/** "12,474 spots · 2 sections" (spots for spatial data, else cells). */
export function datasetFacts(d: AtlasDataset, study: AtlasStudy | undefined): string {
  const spatial = /spatial/i.test(study?.category ?? study?.kind ?? '')
  const facts = [`${d.n_cells.toLocaleString('en-US')} ${spatial ? (d.n_cells === 1 ? 'spot' : 'spots') : d.n_cells === 1 ? 'cell' : 'cells'}`]
  if (d.sections && d.sections.length > 1) facts.push(`${d.sections.length} sections`)
  return facts.join(' · ')
}

/** The dataset's thumbnail (drawn by the atlas app: `apps/atlas/build.py figures`), or null without one. */
export function thumbnailUrl(figures: string | null | undefined, d: AtlasDataset): string | null {
  if (!figures) return null
  return `${figures.replace(/\/*$/, '/')}${encodeURIComponent(d.id)}.space.webp`
}
