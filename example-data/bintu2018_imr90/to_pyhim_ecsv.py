"""Convert Bintu 2018 IMR90 chr21 CSV to PyHiM ECSV format.

Bintu et al. 2018 (Science 362:eaau1783) published chromatin tracing data
as CSV with columns: Chromosome index, Segment index, Z, X, Y (nm).

This script converts it to PyHiM's ECSV schema:
    Spot_ID, Trace_ID, x, y, z, Chrom, Chrom_Start, Chrom_End,
    ROI #, Mask_id, Barcode #, label

Mapping:
- Each "Chromosome index" becomes a Trace_ID (1278 traces total)
- Each "Segment index" becomes a Spot_ID within that trace (up to 66 segments)
- X, Y, Z (nm) → x, y, z (convert to microns: divide by 1000)
- Chrom = chr21, Chrom_Start/End derived from segment index × 30 kb
- ROI # = 0 (single field of view), Mask_id = 1 (single cell per trace)
- Barcode # = Segment index (1..66)
- label = "None"

Note: Not all traces have all 66 segments (imaging failures are common in
chromatin tracing). The output ECSV contains only the observed spots.

Output: IMR90_chr21_pyhim.ecsv (~5.7 MB)
"""
from pathlib import Path
import pandas as pd
from astropy.table import Table

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "IMR90_chr21-18-20Mb.csv"
OUT_PATH = HERE / "IMR90_chr21_pyhim.ecsv"

# Bintu 2018 chr21:18,627,714–20,577,518 (hg38), up to 66 segments × 30 kb
CHR21_START = 18_627_714
SEGMENT_SIZE = 30_000

def main():
    df = pd.read_csv(CSV_PATH, skiprows=1)  # skip header comment
    df.columns = ["chrom_idx", "seg_idx", "z_nm", "x_nm", "y_nm"]

    # Convert nm → microns
    df["x"] = df["x_nm"] / 1000.0
    df["y"] = df["y_nm"] / 1000.0
    df["z"] = df["z_nm"] / 1000.0

    # Trace_ID = chromosome index (1..1278)
    df["Trace_ID"] = df["chrom_idx"].astype(str)

    # Spot_ID = chrom_idx + segment_idx (unique per spot)
    df["Spot_ID"] = (
        df["chrom_idx"].astype(str) + "_" + df["seg_idx"].astype(str)
    )

    # Genomic coordinates
    df["Chrom"] = "chr21"
    df["Chrom_Start"] = CHR21_START + (df["seg_idx"] - 1) * SEGMENT_SIZE
    df["Chrom_End"] = df["Chrom_Start"] + SEGMENT_SIZE

    # PyHiM metadata columns
    df["ROI #"] = 0
    df["Mask_id"] = df["chrom_idx"]  # each trace = one "cell"
    df["Barcode #"] = df["seg_idx"]
    df["label"] = "None"

    # Reorder to PyHiM schema
    cols = [
        "Spot_ID", "Trace_ID", "x", "y", "z", "Chrom", "Chrom_Start",
        "Chrom_End", "ROI #", "Mask_id", "Barcode #", "label",
    ]
    out = df[cols]

    # Write as ECSV with PyHiM-style metadata
    t = Table.from_pandas(out)
    n_traces = out["Trace_ID"].nunique()
    spots_per_trace = len(out) / n_traces
    t.meta["comments"] = [
        "xyz_unit=micron",
        "genome_assembly=hg38",
        "source=Bintu et al. 2018 Science 362:eaau1783",
        "region=chr21:18.6-20.6 Mb",
        "cell_type=IMR90",
        f"n_traces={n_traces}",
        f"mean_spots_per_trace={spots_per_trace:.1f}",
        "segment_spacing=30kb",
        "note=Not all traces have all 66 segments (imaging failures)",
    ]
    t.write(OUT_PATH, format="ascii.ecsv", overwrite=True)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(out)} spots, {n_traces} traces")
    print(f"  {spots_per_trace:.1f} spots/trace (max 66)")


if __name__ == "__main__":
    main()
