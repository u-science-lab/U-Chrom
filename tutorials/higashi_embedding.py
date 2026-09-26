"""FastHigashi cell embedding tutorial.

End-to-end worked example: convert sci-Hi-C single-cell data to Higashi
v2 inputs, run FastHigashi, score the resulting cell embedding against
known cell-type labels with ARI / NMI.

Dataset: Kim et al. 2020 sci-Hi-C H1Esc + HFF mix (1 931 cells, 500 kb,
hg19).  See ``example-data/README.md`` for source and download details.

Run from the repo root::

    python tutorials/higashi_embedding.py

Requires: ``pip install -e .[emb]`` (FastHigashi).  On Apple Silicon the
``uchrom.emb.higashi`` wrapper applies a CPU-pinning shim automatically.

Performance reference (Mac mini M2 16 GB, CPU only, no MPS/CUDA):

==========  ===========  =========  =====
n cells     resolution   wall (s)   ARI
==========  ===========  =========  =====
40          500 kb       8          0.07
150         500 kb       52         0.42
300         500 kb       136        0.55
==========  ===========  =========  =====

ARI grows with cell count — Tucker decomposition needs population
diversity to separate cell types.  150 cells is a reasonable default
for a Mac-mini-friendly demo; 300+ matches what the paper validates on
GPU at multi-thousand cell scale.
"""
from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


RESOLUTION = 500_000
KIM2020_BASE = (
    "https://noble.gs.washington.edu/proj/schic-topic-model/data/"
)
HG19_CHROMSIZES_500K = {
    "chr1":  249250621, "chr2":  243199373, "chr3":  198022430, "chr4":  191154276,
    "chr5":  180915260, "chr6":  171115067, "chr7":  159138663, "chr8":  146364022,
    "chr9":  141213431, "chr10": 135534747, "chr11": 135006516, "chr12": 133851895,
    "chr13": 115169878, "chr14": 107349540, "chr15": 102531392, "chr16":  90354753,
    "chr17":  81195210, "chr18":  78077248, "chr19":  59128983, "chr20":  63025520,
    "chr21":  48129895, "chr22":  51304566, "chrX":  155270560,
}


def _repo_root() -> Path:
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / "pyproject.toml").exists():
            return p
    return Path.cwd()


def find_kim2020() -> tuple[Path, Path]:
    """Locate (or fetch) the Kim 2020 sci-Hi-C tarball + labels.

    Returns (matrices_dir, labels_path).  Tarball is extracted on first
    use — the extracted directory is reused on subsequent runs.
    """
    root = _repo_root()
    data = root / "example-data" / "h1esc_hff_scihic"
    data.mkdir(parents=True, exist_ok=True)

    tar_path = data / "H1Esc-HFF.R1.tar.gz"
    matrices_dir = data / "H1Esc-HFF.R1"
    labels_path = data / "H1Esc-HFF.R1.labeled"

    if not labels_path.exists():
        url = KIM2020_BASE + "matrix_labels/H1Esc-HFF.R1.labeled"
        print(f"[data] fetching cell-type labels (~92 KB) → {labels_path}")
        urllib.request.urlretrieve(url, labels_path)

    if not matrices_dir.exists():
        if not tar_path.exists():
            url = KIM2020_BASE + "matrix_files/H1Esc-HFF.R1.tar.gz"
            print(f"[data] fetching sci-Hi-C tarball (~128 MB) → {tar_path}")
            urllib.request.urlretrieve(url, tar_path)
        print(f"[data] extracting {tar_path.name} → {matrices_dir}")
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(data)

    n_files = sum(1 for _ in matrices_dir.glob("*.matrix"))
    assert n_files > 100, f"only {n_files} matrices in {matrices_dir}"
    return matrices_dir, labels_path


def discover_bin_offsets(matrices_dir: Path, sample: int = 200) -> dict[str, int]:
    """The matrices use a global bin index across the whole genome.  Derive
    each chromosome's offset by scanning a few cells and taking the
    minimum global bin observed for that chrom across the sample."""
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


def main(n_per_type: int = 75, rank: int = 64) -> None:
    from uchrom.io.contacts import (
        write_label_info, make_higashi_config, _materialise_chromsizes,
    )
    from uchrom.core import ChromData
    from uchrom.emb.higashi import run as higashi_run

    matrices_dir, labels_path = find_kim2020()

    label_df = pd.read_csv(
        labels_path, sep="\t", header=None, names=["matrix", "cell_type"]
    )
    h1 = label_df[label_df.cell_type == "H1Esc"].head(n_per_type)
    hff = label_df[label_df.cell_type == "HFF"].head(n_per_type)
    sub = pd.concat([h1, hff]).reset_index(drop=True)
    sub["cell_name"] = sub["matrix"].str.replace(".matrix", "", regex=False)
    print(f"\nsubset: {len(sub)} cells, {dict(Counter(sub.cell_type))}")

    td = Path(tempfile.mkdtemp(prefix="higashi_tut_"))
    higashi_dir = td / "higashi"
    data_dir = higashi_dir / "data"
    data_dir.mkdir(parents=True)
    print(f"work dir: {td}")

    t0 = time.time()
    print("[step 1/4] discovering bin offsets...")
    bin_offsets = discover_bin_offsets(matrices_dir)

    print("[step 2/4] writing per-cell Higashi v2 inputs...")
    chrom_list = list(HG19_CHROMSIZES_500K.keys())
    filelist_lines = []
    for _, row in sub.iterrows():
        df = matrix_to_higashi(matrices_dir / row.matrix, bin_offsets)
        df = df[df["chrom1"].isin(chrom_list) & df["chrom2"].isin(chrom_list)]
        out = data_dir / f"{row.cell_name}.txt"
        df.to_csv(out, sep="\t", index=False, header=False)
        filelist_lines.append(str(out.resolve()))
    (higashi_dir / "filelist.txt").write_text("\n".join(filelist_lines) + "\n")
    write_label_info(sub[["cell_name", "cell_type"]],
                     higashi_dir / "label_info.pickle")
    chromsizes_path = _materialise_chromsizes(HG19_CHROMSIZES_500K, higashi_dir)
    cfg = make_higashi_config(
        data_dir=str(higashi_dir),
        genome_reference="hg19",
        resolution=RESOLUTION,
        chrom_list=chrom_list,
        overrides={"genome_reference_path": str(chromsizes_path)},
    )
    (higashi_dir / "config.JSON").write_text(json.dumps(cfg, indent=2))
    print(f"  inputs ready in {time.time()-t0:.1f}s")

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

    print(f"[step 3/4] running FastHigashi (rank={rank}, CPU)...")
    cd = higashi_run(
        cd,
        contacts_dir=higashi_dir,
        rank=rank,
        cache_dir=td / "cache",
        result_dir=td / "result",
        wrapper_kwargs={"do_conv": True, "do_rwr": True, "do_col": True},
    )
    elapsed = time.time() - t0

    print("[step 4/4] scoring ARI / NMI vs known cell types...")
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    emb = cd.cellm["higashi"]
    true_labels = pd.Categorical(cd.cells["cell_type"]).codes
    pred = KMeans(n_clusters=2, n_init=10, random_state=0).fit_predict(emb)
    ari = adjusted_rand_score(true_labels, pred)
    nmi = normalized_mutual_info_score(true_labels, pred)

    print(f"\n=== higashi_embedding tutorial — Kim 2020 sci-Hi-C ===")
    print(f"  cells       : {len(sub)} (H1Esc + HFF, balanced)")
    print(f"  resolution  : {RESOLUTION:,} bp")
    print(f"  rank        : {rank}")
    print(f"  preprocessing: do_conv + do_rwr + do_col")
    print(f"  wall clock  : {elapsed:.1f} s")
    print(f"  ARI         : {ari:.3f}  (random = 0)")
    print(f"  NMI         : {nmi:.3f}")
    print(f"\nembedding stored at cd.cellm['higashi']  shape={emb.shape}")
    print(f"provenance:    cd.uns['higashi'] = {dict(cd.uns['higashi'])}")
    print(f"\n(work dir kept at {td})")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 75
    rank = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    main(n_per_type=n, rank=rank)
