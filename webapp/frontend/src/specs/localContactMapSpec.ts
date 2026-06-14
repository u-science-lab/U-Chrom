/**
 * Default Gosling spec factory for the local contact map.
 * Uses our HiGlass-compatible tileset API at /api/v1 (server prefix).
 *
 * The default spec is no longer hardcoded to chr21/hg38 — it is built from the
 * chromosome (and optional genome assembly) of the actually-loaded dataset,
 * fetched from `/api/dataset_info`. Call `makeDefaultContactSpec(chrom, assembly)`
 * after data loads and feed the result into the Gosling renderer.
 *
 * NOTE: HiGlass/Gosling's matrix datafetcher builds tile requests from
 * `server` + `tilesetUid` as `${server}/tileset_info/?d=<uid>` and
 * `${server}/tiles/?d=<uid>.z.x.y` (with trailing slashes). The vite dev proxy
 * only forwards `/api/*`, and the backend serves these under `/api/v1`, so
 * `server` MUST include the `/api/v1` prefix.
 *
 * OVERLAY STRUCTURE (Gosling 1.x): a track that sets `alignment: 'overlay'`
 * MUST carry a nested `tracks: [...]` array of the layers to overlay. Setting
 * `alignment: 'overlay'` on a leaf track WITHOUT a nested `tracks` array makes
 * the compiler do `[...track.tracks]` on `undefined` → "track.tracks is not
 * iterable". So the heatmap + TAD boundaries are wrapped in ONE overlay track,
 * and the cytoband axis is a separate stacked track.
 */

const ORIGIN = typeof window !== 'undefined' ? window.location.origin : ''

/**
 * Build a default contact-map spec for a given chromosome.
 *
 * @param chrom    Chromosome name from the loaded dataset (e.g. "chr1").
 * @param assembly Optional genome assembly (e.g. "mm10", "hg38"). When omitted
 *                 the `assembly` field is left off the spec, so Gosling falls
 *                 back to its built-in default. The matrix tileset provides its
 *                 own coordinate range via `/api/v1/tileset_info`, so the
 *                 heatmap renders regardless of which assembly is assumed.
 */
export function makeDefaultContactSpec(chrom: string, assembly?: string | null) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const spec: any = {
    spacing: 0,
    style: { outlineWidth: 0 },
    views: [
      {
        layout: 'linear',
        xDomain: { chromosome: chrom },
        tracks: [
          {
            // Overlay parent: heatmap + TAD boundary rules share one canvas.
            alignment: 'overlay',
            title: `Contact Map (${chrom})`,
            width: 800,
            height: 400,
            tracks: [
              {
                // Layer 1: contact matrix heatmap.
                // Gosling 1.0.7 MatrixData schema accepts ONLY `url` (no
                // `server` / `tilesetUid`). The compiler derives
                // server+tilesetUid by splitting the url on the literal
                // "tileset_info/?d=" (note the trailing slash), so the url MUST
                // contain that exact substring. A matrix is a 2D track: it needs
                // all four positional channels (x/xe/y/ye) with the tile fields
                // xs/xe/ys/ye, and mark 'bar'.
                id: 'contact-heatmap',
                data: {
                  type: 'matrix',
                  url: `${ORIGIN}/api/v1/tileset_info/?d=contact-${chrom}`,
                },
                mark: 'bar',
                x: { field: 'xs', type: 'genomic', axis: 'top' },
                xe: { field: 'xe', type: 'genomic' },
                y: { field: 'ys', type: 'genomic', axis: 'left' },
                ye: { field: 'ye', type: 'genomic' },
                color: {
                  field: 'value',
                  type: 'quantitative',
                  range: 'warm',
                  legend: true,
                },
              },
              {
                // Layer 2: TAD start boundaries (vertical rules).
                // Gosling's json loader only accepts inline `values`; remote
                // data MUST use `type: 'csv'` (which supports `url`). Backend
                // serves text/csv at format=csv with a header row even when
                // empty.
                id: 'tad-boundaries',
                data: {
                  type: 'csv',
                  url: `${ORIGIN}/api/tads/${chrom}?format=csv`,
                  chromosomeField: 'chrom',
                  genomicFields: ['start', 'end'],
                },
                mark: 'rule',
                x: { field: 'start', type: 'genomic' },
                strokeWidth: { value: 2 },
                stroke: { value: '#ff1493' },
                opacity: { value: 0.7 },
              },
              {
                // Layer 3: TAD end boundaries (vertical rules)
                id: 'tad-boundaries-end',
                data: {
                  type: 'csv',
                  url: `${ORIGIN}/api/tads/${chrom}?format=csv`,
                  chromosomeField: 'chrom',
                  genomicFields: ['start', 'end'],
                },
                mark: 'rule',
                x: { field: 'end', type: 'genomic' },
                strokeWidth: { value: 2 },
                stroke: { value: '#ff1493' },
                opacity: { value: 0.7 },
              },
            ],
          },
          {
            // Separate stacked track: cytogenetic band axis below the heatmap.
            // The band CSV is hg38-based; for other assemblies the chrom filter
            // simply yields no bands (the heatmap above is the primary view).
            // Gosling 1.0.7 CsvData has no `quantitativeFields` (JSON-only); the
            // csv loader infers field types, so it is omitted here.
            id: 'axis',
            data: {
              type: 'csv',
              url: 'https://raw.githubusercontent.com/sehilyi/gemini-datasets/master/data/cytogenetic_band.csv',
              chromosomeField: 'Chr.',
              genomicFields: ['ISCN_start', 'ISCN_stop', 'Basepair_start', 'Basepair_stop'],
            },
            mark: 'rect',
            dataTransform: [{ type: 'filter', field: 'Chr.', oneOf: [chrom] }],
            x: {
              field: 'Basepair_start',
              type: 'genomic',
              domain: { chromosome: chrom },
              axis: 'top',
            },
            xe: { field: 'Basepair_stop', type: 'genomic' },
            color: {
              field: 'Density',
              type: 'nominal',
              domain: ['', '25', '50', '75', '100'],
              range: ['white', '#D9D9D9', '#979797', '#636363', 'black'],
            },
            width: 800,
            height: 30,
          },
        ],
      },
    ],
  }

  // Only set `assembly` when we actually know it. Gosling 1.0.7 accepts an
  // assembly name string (e.g. "mm10", "hg38"); omitting it falls back to the
  // built-in default rather than rendering an empty view.
  if (assembly) {
    spec.assembly = assembly
  }

  return spec
}

/**
 * Backward-compatible default (chr21/hg38). Prefer `makeDefaultContactSpec`
 * built from `/api/dataset_info` so the view follows the loaded dataset.
 */
export const LOCAL_CONTACT_MAP_SPEC = makeDefaultContactSpec('chr21', 'hg38')
