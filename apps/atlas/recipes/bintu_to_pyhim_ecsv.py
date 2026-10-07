"""Convert Bintu 2018 IMR90 chr21 CSV to PyHiM ECSV format.

Bintu et al. 2018 (Science 362:eaau1783) published chromatin tracing data
as CSV with columns: Chromosome index, Segment index, Z, X, Y (nm).

This script converts it to PyHiM's ECSV schema:
    Spot_ID, Trace_ID, x, y, z, Chrom, Chrom_Start, Chrom_End,
    ROI #, Mask_id, Barcode #, label

Mapping:
- Each "Chromosome index" becomes a Trace_ID (1,277 traces)
- Each "Segment index" becomes a Spot_ID within that trace (65 segments)
- X, Y, Z (nm) → x, y, z (convert to microns: divide by 1000)
- Chrom = chr21, Chrom_Start/End derived from segment index × 30 kb
- ROI # = 0 (single field of view), Mask_id = Chromosome index (one cell per trace)
- Barcode # = Segment index (1..65)
- label = "None"

Note: every trace has all 65 segments; segments that were not detected (6.3 %) have NaN
coordinates and are kept.

Output: IMR90_chr21_pyhim.ecsv (~5.7 MB), written by uchrom.io.read_bintu_tracing(keep_missing=True) +
uchrom.io.write_pyhim_trace (the same bytes the former hand-written conversion produced).
"""

from uchrom.datasets import data_dir, fetch
from uchrom.io import read_bintu_tracing, write_pyhim_trace

DATA = data_dir()                       # $UCHROM_DATA, else ~/.cache/uchrom
OUT_PATH = DATA / "IMR90_chr21_pyhim.ecsv"

# Bintu 2018 chr21:18,627,714–20,577,714 (hg38), 65 segments × 30 kb
CHR21_START = 18_627_714
SEGMENT_SIZE = 30_000


def main():
    cd = read_bintu_tracing(fetch("bintu_imr90"), chrom="chr21", start_bp=CHR21_START,
                            resolution_bp=SEGMENT_SIZE, keep_missing=True)
    n_traces = cd.n_traces
    write_pyhim_trace(cd, OUT_PATH, comments=[
        "source=Bintu et al. 2018 Science 362:eaau1783", "region=chr21:18.6-20.6 Mb", "cell_type=IMR90",
        f"n_traces={n_traces}", f"spots_per_trace={cd.n_spots / n_traces:.0f}", "segment_spacing=30kb",
        "note=undetected segments have NaN coordinates"])
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.1f} MB): {cd.n_spots} spots, {n_traces} traces")


if __name__ == "__main__":
    main()
