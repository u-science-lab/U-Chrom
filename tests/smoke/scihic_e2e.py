"""End-to-end PR3-B validation: real scHi-C, real FastHigashi, real ARI.

Uses Kim et al. 2020 sci-Hi-C (Noble lab) — H1Esc + HFF mix at 500kb.
Source: https://noble.gs.washington.edu/proj/schic-topic-model/

Run from repo root after extracting the tarball to /tmp/H1Esc-HFF.R1/:
    .venv/bin/python tests/smoke/scihic_e2e.py
"""
from __future__ import annotations

import json
import pickle
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


RESOLUTION = 500_000

# Chrom sizes at 500 kb (in bp = bin_offset_next * resolution).
HG19_CHROMSIZES_500K = {
    "chr1":  249250621, "chr2":  243199373, "chr3":  198022430, "chr4":  191154276,
    "chr5":  180915260, "chr6":  171115067, "chr7":  159138663, "chr8":  146364022,
    "chr9":  141213431, "chr10": 135534747, "chr11": 135006516, "chr12": 133851895,
    "chr13": 115169878, "chr14": 107349540, "chr15": 102531392, "chr16":  90354753,
    "chr17":  81195210, "chr18":  78077248, "chr19":  59128983, "chr20":  63025520,
    "chr21":  48129895, "chr22":  51304566, "chrX":  155270560,
}


def discover_bin_offsets(matrices_dir: Path, sample: int = 50) -> dict[str, int]:
    """The matrices use a global bin index across the whole genome.  Derive
    each chromosome's offset by scanning a few cells and taking the minimum
    global bin observed for that chrom — assumes coverage extends near the
    start of every chromosome across the sampled cells."""
    files = sorted(matrices_dir.glob("*.matrix"))[:sample]
    per_chrom_min: dict[str, int] = {}
    for f in files:
        df = pd.read_csv(
            f, sep="\t", header=None,
            names=["bin1", "bin2", "count", "weight", "chrom1", "chrom2"],
        )
        for col_bin, col_chrom in [("bin1", "chrom1"), ("bin2", "chrom2")]:
            for chrom, mn in df.groupby(col_chrom)[col_bin].min().items():
                if chrom not in per_chrom_min or mn < per_chrom_min[chrom]:
                    per_chrom_min[chrom] = int(mn)
    return per_chrom_min


def matrix_to_higashi(matrix_path: Path, bin_offsets: dict[str, int]) -> pd.DataFrame:
    """Convert a sci-Hi-C global-bin matrix to higashi (chrom, pos) pairs."""
    df = pd.read_csv(
        matrix_path, sep="\t", header=None,
        names=["bin1", "bin2", "count", "weight", "chrom1_full", "chrom2_full"],
    )
    df["chrom1"] = df["chrom1_full"].str.replace("human_", "", regex=False)
    df["chrom2"] = df["chrom2_full"].str.replace("human_", "", regex=False)
    df["pos1"] = (df["bin1"] - df["chrom1_full"].map(bin_offsets)) * RESOLUTION
    df["pos2"] = (df["bin2"] - df["chrom2_full"].map(bin_offsets)) * RESOLUTION
    out = df[["chrom1", "pos1", "chrom2", "pos2", "count"]].dropna()
    out = out[(out["pos1"] >= 0) & (out["pos2"] >= 0)]
    return out.astype({"pos1": int, "pos2": int, "count": int})


def main() -> None:
    from uchrom.io.contacts import (
        write_label_info, make_higashi_config, _materialise_chromsizes,
    )
    from uchrom.core import ChromData
    from uchrom.emb.higashi import run as higashi_run

    # 1. Locate inputs (downloaded by the user beforehand).
    matrices_dir = Path("/tmp/H1Esc-HFF.R1")
    labels_path = Path("/tmp/labels.txt")
    assert matrices_dir.exists(), f"unzip the tarball to {matrices_dir} first"
    assert labels_path.exists(), f"download labels to {labels_path} first"

    # 2. Pick a balanced subset.
    label_df = pd.read_csv(
        labels_path, sep="\t", header=None, names=["matrix", "cell_type"]
    )
    n_per = 150
    h1 = label_df[label_df.cell_type == "H1Esc"].head(n_per)
    hff = label_df[label_df.cell_type == "HFF"].head(n_per)
    sub = pd.concat([h1, hff]).reset_index(drop=True)
    sub["cell_name"] = sub["matrix"].str.replace(".matrix", "", regex=False)
    print(f"subset: {len(sub)} cells, types: {Counter(sub.cell_type)}")

    # 3. Build Higashi v2 inputs from the .matrix files (skipping .pairs route).
    td = Path(tempfile.mkdtemp(prefix="uchrom_scihic_"))
    print(f"work dir: {td}")
    higashi_dir = td / "higashi"
    data_dir = higashi_dir / "data"
    data_dir.mkdir(parents=True)

    t0 = time.time()
    print(f"[{time.time()-t0:.1f}s] discovering bin offsets...")
    bin_offsets = discover_bin_offsets(matrices_dir, sample=200)
    print(f"  offsets: {sorted(bin_offsets.items(), key=lambda x: x[1])[:5]}...")

    filelist_lines: list[str] = []
    chrom_list = list(HG19_CHROMSIZES_500K.keys())
    for _, row in sub.iterrows():
        df = matrix_to_higashi(matrices_dir / row.matrix, bin_offsets)
        df = df[df["chrom1"].isin(chrom_list) & df["chrom2"].isin(chrom_list)]
        out = data_dir / f"{row.cell_name}.txt"
        df.to_csv(out, sep="\t", index=False, header=False)
        filelist_lines.append(str(out.resolve()))
    (higashi_dir / "filelist.txt").write_text("\n".join(filelist_lines) + "\n")
    print(f"[{time.time()-t0:.1f}s] per-cell files written")

    write_label_info(sub[["cell_name", "cell_type"]], higashi_dir / "label_info.pickle")

    chromsizes_path = _materialise_chromsizes(HG19_CHROMSIZES_500K, higashi_dir)
    cfg = make_higashi_config(
        data_dir=str(higashi_dir),
        genome_reference="hg19",
        resolution=RESOLUTION,
        chrom_list=chrom_list,
        overrides={"genome_reference_path": str(chromsizes_path)},
    )
    (higashi_dir / "config.JSON").write_text(json.dumps(cfg, indent=2))

    # 4. Build a stub ChromData (one spot per cell — embedding lives in cellm).
    cd = ChromData(
        coords=np.zeros((len(sub), 3)),
        spots=pd.DataFrame({
            "chrom": ["chr1"] * len(sub),
            "start": np.arange(len(sub)) * RESOLUTION,
            "end":   np.arange(len(sub)) * RESOLUTION + RESOLUTION,
            "trace_id": [f"t{i}" for i in range(len(sub))],
            "cell_id": list(sub.cell_name),
        }),
        cells=sub[["cell_name", "cell_type"]].reset_index(drop=True),
    )

    # 5. Run FastHigashi.
    rank = 64
    print(f"[{time.time()-t0:.1f}s] starting FastHigashi (rank={rank}, {len(sub)} cells, CPU)")
    cd = higashi_run(
        cd,
        contacts_dir=higashi_dir,
        rank=rank,
        cache_dir=td / "cache",
        result_dir=td / "result",
        wrapper_kwargs={
            # Recommended preprocessing per Higashi wiki for noisy/sparse scHi-C.
            "do_conv": True,
            "do_rwr": True,
            "do_col": True,
        },
    )
    elapsed = time.time() - t0
    print(f"[{elapsed:.1f}s] FastHigashi done")
    print(f"emb shape: {cd.cellm['higashi'].shape}")

    # 6. ARI metric.
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    emb = cd.cellm["higashi"]
    true_labels = pd.Categorical(cd.cells["cell_type"]).codes
    pred = KMeans(n_clusters=2, n_init=10, random_state=0).fit_predict(emb)
    ari = adjusted_rand_score(true_labels, pred)
    nmi = normalized_mutual_info_score(true_labels, pred)
    print(f"\n=== Validation metrics ===")
    print(f"  cells       : {len(sub)} (H1Esc + HFF, ~half each)")
    print(f"  resolution  : {RESOLUTION:,} bp")
    print(f"  rank        : {rank}")
    print(f"  wall clock  : {elapsed:.1f} s")
    print(f"  ARI         : {ari:.3f}")
    print(f"  NMI         : {nmi:.3f}")

    # cleanup
    print(f"\n(work dir kept at {td})")


if __name__ == "__main__":
    main()
