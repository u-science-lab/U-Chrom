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
  n_traces: number
  n_cells: number
  xyz_unit: string | null
  trace_mode: boolean
  chroms: ChromInfo[]
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
}

export interface TrackInfo {
  name: string
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
}

/** GET tracks: per-genomic-bin aggregates of spot tracks. */
export interface TrackData {
  chrom: string
  bin_starts: number[]
  bin_ends: number[]
  n_spots: number[]
  values: Record<string, (number | null)[]>
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
}

export interface ScalingStats {
  sep_bp: number[]
  median: (number | null)[]
  q25: (number | null)[]
  q75: (number | null)[]
  n_pairs: number[]
  unit: string | null
}

export interface EmbeddingInfo {
  key: string
  method: string
  source: string
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
  highQuality: boolean
}

export interface Layer {
  id: string
  name: string
  datasetId: string
  parentId: string | null
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

