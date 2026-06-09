const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface DatasetSummary {
  id: string;
  title: string;
  organism: string;
  technology: string;
  n_cells: number;
  n_markers: number;
  thumbnail_url: string | null;
}

export interface FileEntry {
  label: string;
  url: string;
  size_mb: number | null;
  format: string;
}

export interface DatasetDetail {
  id: string;
  title: string;
  description: string;
  organism: string;
  assembly: string;
  technology: string;
  doi: string;
  citation: string;
  n_cells: number;
  n_traces: number;
  n_spots: number;
  n_markers: number;
  cell_types: Record<string, number>;
  genome_coverage: string;
  xyz_unit: string;
  files: FileEntry[];
  notebook_available: boolean;
  analyzer_url: string | null;
}

export const apiBase = API_BASE;

export async function listDatasets(params: Record<string, string> = {}): Promise<DatasetSummary[]> {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/api/datasets${qs ? `?${qs}` : ""}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`list failed: ${res.status}`);
  return res.json();
}

export async function getDataset(id: string): Promise<DatasetDetail | null> {
  const res = await fetch(`${API_BASE}/api/datasets/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`detail failed: ${res.status}`);
  return res.json();
}

export async function getFacets(): Promise<{ organism: string[]; technology: string[] }> {
  const res = await fetch(`${API_BASE}/api/facets`, { cache: "no-store" });
  if (!res.ok) return { organism: [], technology: [] };
  return res.json();
}
