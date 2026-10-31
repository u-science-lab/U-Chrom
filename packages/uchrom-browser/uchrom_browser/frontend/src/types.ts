// Shapes shared with the Python server — see ../../API.md.

export interface ChromInfo {
  name: string
  start: number
  end: number
  n_spots: number
  n_traces: number
}

export interface DatasetSummary {
  id: string
  name: string
  path: string
  n_spots: number
  /** loci (absent from older servers) */
  n_bins?: number
  n_traces: number
  n_cells: number
  xyz_unit: string | null
  trace_mode: boolean
  /** 'set': a trace is an unordered set of reads / localisations (uns['trace_kind']), drawn as points */
  trace_kind?: 'fibre' | 'set'
  chroms: ChromInfo[]
  /** chromosomes end to end for the whole-genome view (absent from older servers) */
  genome?: GenomeChrom[]
  /** numeric columns of cd.cells (absent from older servers) */
  cell_fields?: CellField[]
  /** non-genomic 3D point sets (cd.points), e.g. nascent RNA spots */
  point_sets?: PointSetInfo[]
  /** cell embeddings (cd.cellm arrays with ≥2 columns) */
  embeddings?: EmbeddingInfo[]
  /** false → no 3-D spots (e.g. single-cell Hi-C / RNA only) */
  has_coords?: boolean
  /** numeric per-spot tracks (cd.tracks), e.g. IF / ChIP marks */
  tracks?: TrackInfo[]
  /** linked contact maps (cool / mcool / scool) */
  contact_maps?: ContactMapInfo[]
  /** interval tables in cd.results (TADs, loops, peaks) */
  intervals?: IntervalInfo[]
  clusters?: ClusterTableInfo[]
  /** cell-position sets (cd.cell_positions) with their regions and images */
  spatial?: SpatialInfo[]
  /** the cells' 3-D structures share one frame (each model centred on the origin): an all-cells view stacks them */
  cells_overlap?: boolean
}

export interface TrackInfo {
  name: string
  /** "bin" / "spot" (cd.bin_tracks / spot_tracks) or "cell_bin" (a linked cell × bin matrix) */
  level?: string
  /** the bins a track is reported on: tracks of one grid are requested together */
  grid?: string
  label?: string
}

/** One section / FOV of a cell-position set. */
export interface SpatialRegion {
  name: string
  n_cells: number
  /** name of its image (GET images/<name>), or null */
  image: string | null
}

export interface SpatialInfo {
  key: string
  unit: string | null
  frame: string | null
  /** "down": y grows downwards (image pixels, grid rows) */
  y_axis: 'up' | 'down'
  status: string | null
  source: string | null
  regions: SpatialRegion[]
  n_images: number
  /** the positions are the cells' places in the 3-D coordinates (the 3-D view shows the same layout) */
  in_coords_frame?: boolean
}

/** Cell positions of one region, with the region's image (extent [x0, x1, y0, y1] in position units). */
export interface SpatialPoints {
  key: string
  region: string | null
  unit: string | null
  y_axis: 'up' | 'down'
  cell_ids: string[]
  x: number[]
  y: number[]
  image: SpatialImage | null
  /** without a region: the region of each cell (null without a region column) */
  regions?: (string | null)[] | null
  /** without a region: the image of each region that has one */
  images?: Record<string, SpatialImage>
}

export interface SpatialImage {
  name: string
  /** [x0, x1, y0, y1] in position units, the image's first row at y0 */
  extent: [number, number, number, number]
  kind: string | null
}

export interface ContactMapInfo {
  key: string
  kind: 'cool' | 'mcool' | 'scool' | string
  label: string
  resolutions: number[]
  chroms: { name: string; length: number }[]
  per_cell: boolean
  n_cells: number
}

export interface IntervalInfo {
  key: string
  n: number
  /** domain | segment | peak | pair (cd.intervals), null for other result tables */
  kind?: string | null
}

/** GET tracks: per-genomic-bin aggregates of spot tracks. */
export interface TrackData {
  chrom: string
  group?: string | null
  bin_starts: number[]
  bin_ends: number[]
  n_spots: number[]
  values: Record<string, (number | null)[]>
}

/** A multi-way contact table (cd.clusters: SPRITE, SpaceA, Pore-C, ChIA-Drop). */
export interface ClusterTableInfo {
  key: string
  n_clusters: number
  n_fragments: number
  per_cell: boolean
  assay?: string | null
  /** a filtered table: the key of the table it was made from */
  filtered_from?: string | null
}

/** One cluster of a window (GET clusters/{key}): its size over all chromosomes, on this one, its span here and
 *  the fragments in the window. */
export interface ClusterInWindow {
  id: number
  cell: string | null
  size: number
  chrom_size: number
  span: [number, number]
  fragments: [number, number][]
}

/** GET clusters/{key}: the clusters with fragments in a window (n_clusters: all of them; at most a limit sent). */
export interface ClusterWindow {
  key: string
  chrom: string
  start: number
  end: number
  n_clusters: number
  clusters: ClusterInWindow[]
}

/** GET intervals/{key}. */
export interface IntervalTable {
  columns: string[]
  rows: (string | number | null)[][]
}

export interface RgStats {
  trace_ids: string[]
  cell_ids: (string | null)[]
  chroms: string[]
  rg: (number | null)[]
  n_spots: number[]
  unit: string | null
  group?: string | null
  n_cells?: number | null
}

export interface ScalingStats {
  sep_bp: number[]
  median: (number | null)[]
  q25: (number | null)[]
  q75: (number | null)[]
  n_pairs: number[]
  unit: string | null
  group?: string | null
  n_cells?: number | null
}

export interface EmbeddingInfo {
  key: string
  method: string
  source: string
  /** display group: "RNA", "Histone/IF", "ATAC", "Hi-C", "Published", "Other" */
  modality?: string
  label: string
  n_dims: number
}

/** Two components of an embedding (API: GET embedding/{key}?dims=a,b). */
export interface Embedding {
  key: string
  label: string
  cell_ids: string[]
  x: (number | null)[]
  y: (number | null)[]
  axis_labels: [string, string]
}

export interface CellField {
  name: string
  /** prefix before the first '.' ('rna.Nanog' → 'rna'), else 'cell' */
  group: string
  label: string
  /** 'category': string column with a few values (e.g. cell_type); absent → numeric */
  kind?: 'numeric' | 'category'
  min: number | null
  max: number | null
  n_valid: number
  /** category fields: values in natural order with their cell counts */
  categories?: { value: string; count: number }[]
}

/** One cell's value of a cell field (numbers, category strings, or missing). */
export type CellValue = number | string | null

export interface PointSetInfo {
  name: string
  n_points: number
  label_field: string | null
  labels: { value: string; count: number }[]
  value_fields: string[]
}

export interface CellValues {
  field: string
  kind?: 'numeric' | 'category'
  cell_ids: string[]
  values: CellValue[]
}

export interface CellDetails {
  cell_id: string
  fields: Record<string, number | string | null>
}

/** POST /points/{name} response (JSON). */
export interface PointSetPayload {
  n: number
  positions: number[]
  cell_ids: (string | null)[]
  labels: (string | null)[]
  values: Record<string, (number | null)[]>
}

/** Decoded point set held by the client. */
export interface PointSet {
  name: string
  n: number
  positions: Float32Array
  cellIds: (string | null)[]
  labels: string[]
  values: Record<string, (number | null)[]>
}

export interface TraceInfo {
  trace_id: string
  chrom: string
  cell_id: string | null
  n_spots: number
  start: number
  end: number
}

export interface CellInfo {
  cell_id: string
  n_spots: number
  n_traces: number
  n_chroms: number
}

export interface CellPage {
  total: number
  cells: CellInfo[]
}

export interface TracePage {
  total: number
  traces: TraceInfo[]
}

export interface Region {
  chrom: string
  start: number
  end: number
}

/** Layer filter; every field optional, combined with AND on the server. */
export interface LayerFilter {
  chroms?: string[]
  region?: Region
  trace_ids?: string[]
  cell_ids?: string[]
}

export interface SegmentInfo {
  trace_id: string
  chrom: string
  cell_id: string | null
  n_points: number
  start: number
  end: number
}

export interface GeometryHeader {
  n_points: number
  n_segments: number
  total_points: number
  truncated: boolean
  segments: SegmentInfo[]
  /** null when the selection has no points (API.md) */
  bbox: { min: [number, number, number]; max: [number, number, number] } | null
  chrom_extent: Record<string, [number, number]>
  /** a large store's overview: whole cells taken in a fixed random order (API.md, geometry) */
  sample?: { cells: number; of_cells: number } | null
}

export interface Geometry {
  header: GeometryHeader
  /** x0,y0,z0,x1,… (length 3·N) */
  positions: Float32Array
  /** genomic start of each point's bin (length N) */
  starts: Uint32Array
  /** segment offsets into the point arrays (length S+1) */
  offsets: Uint32Array
}

export type RenderMode = 'line' | 'tube' | 'points'
export type PointShape = 'sphere' | 'disc' | 'square'
export type ColorMode = 'rainbow' | 'custom' | 'trace' | 'cell' | 'field'

export interface LayerStyle {
  mode: RenderMode
  colorMode: ColorMode
  color: string
  opacity: number
  lineWidth: number
  /** null = auto (0.3% of the bbox diagonal) */
  tubeRadius: number | null
  pointSize: number
  /** points: shaded sphere (default), flat disc or square */
  pointShape?: PointShape
  /** points: grow with the zoom (a size in data units) instead of a fixed size on screen */
  pointScale?: boolean
  highQuality: boolean
}

export interface Layer {
  id: string
  name: string
  datasetId: string
  parentId: string | null
  /** the 3-D view (pane id) a subset was made in: listed and drawn only there (absent: every view) */
  paneId?: string | null
  /** own filter composed with all ancestors' filters */
  filter: LayerFilter
  visible: boolean
  style: LayerStyle
  geometry: Geometry | null
  loading: boolean
  error: string | null
}

/** A clicked chromatin spot. */
export interface TracePick {
  kind?: 'trace'
  /** workspace pane where the pick happened (label + highlight only there) */
  paneId?: string
  layerId: string
  pointIndex: number
  segment: SegmentInfo
  binStart: number
  screen: { x: number; y: number }
}

/** A clicked point of a point set (e.g. an RNA spot). */
export interface PointPick {
  kind: 'point'
  paneId?: string
  set: string
  index: number
  label: string
  cellId: string | null
  position: [number, number, number]
  values: Record<string, number | null>
  screen: { x: number; y: number }
}

export type PickInfo = TracePick | PointPick

export const isPointPick = (p: PickInfo | null | undefined): p is PointPick => !!p && p.kind === 'point'


/** One entry of a server directory (Open dataset dialog). */
export interface FileEntry {
  name: string
  path: string
  /** "dataset": something the browser opens (a *.chromdata.zarr directory is one) */
  kind: 'dir' | 'dataset' | 'file'
  format: string | null
  size: number | null
  mtime: number
}

export interface FileListing {
  path: string
  parent: string | null
  sep: string
  entries: FileEntry[]
  truncated: boolean
}

export interface FilePlace {
  label: string
  path: string
}

/** One dataset of an atlas catalog (`catalog.json`, written by `python -m chromdata.catalog build`). */
export interface AtlasDataset {
  id: string
  url: string
  title: string
  /** short name within its study (e.g. "Mouse brain") */
  name?: string
  /** id of its entry in the catalog's `studies` */
  study?: string
  description?: string
  paper?: string
  doi?: string
  source_url?: string
  license?: string
  organism?: string
  assembly?: string
  tissue?: string
  n_cells: number
  sections?: string[]
  modalities?: string[]
  contact_maps?: number
  images?: number
  size_mb?: number
}

/** A study of the atlas: the paper its datasets come from. */
export interface AtlasStudy {
  id: string
  citation?: string
  journal?: string
  title?: string
  /** the assay, e.g. "Spatial Hi-C-RNA" */
  kind?: string
  /** "Spatial", "Single-cell", "Imaging", … */
  category?: string
}

export interface AtlasResponse {
  root: string | null
  catalog: {
    title: string
    description?: string
    updated?: string
    studies?: AtlasStudy[]
    /** ids of the datasets the start page offers first */
    featured?: string[]
    datasets: AtlasDataset[]
  } | null
  /** where the datasets' thumbnails are (`<figures><id>.space.webp`); null when the atlas has none */
  figures?: string | null
}

/** A chromosome in the whole-genome layout: bp before it (offset) and its length. */
export interface GenomeChrom {
  name: string
  offset: number
  length: number
}

/** One node of a store's on-disk structure (GET /store; API.md). */
export interface StoreNode {
  name: string
  /** relative path in the store ('' = root) */
  path: string
  kind: 'group' | 'dir' | 'array' | 'table' | 'file'
  /** size on disk; null when unknown (an array of a store read over HTTP, a group holding one) */
  bytes: number | null
  /** Zarr attributes: key → JSON preview (shortened) */
  attrs?: Record<string, string>
  children?: StoreNode[]
  /** children not listed */
  more?: number
  /** array */
  shape?: number[]
  dtype?: string
  chunk_shape?: number[] | null
  n_chunks?: number
  /** array of a store read over HTTP: its uncompressed size (null for variable-length types) */
  nbytes?: number | null
  /** Parquet table */
  rows?: number
  columns?: string[]
  row_groups?: number
  error?: string
  /** root: 'zarr' (directory), 'cdz' (one zip) or 'remote' (a directory store at a URL) */
  container?: string
  /** root: how the listing was made, when it is not a full walk (a store read over HTTP) */
  note?: string
  /** root: the store header (attrs.uchrom: format_version, n_spots, …) in full */
  meta?: Record<string, string | number | boolean | null>
}
