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
  bbox: { min: [number, number, number]; max: [number, number, number] }
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
export type ColorMode = 'rainbow' | 'custom' | 'trace'

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

export interface PickInfo {
  layerId: string
  pointIndex: number
  segment: SegmentInfo
  binStart: number
  screen: { x: number; y: number }
}
