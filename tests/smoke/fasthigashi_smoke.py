"""Smoke test: drive a real FastHigashi run on the in-repo cell1+cell2 .pairs.

Run from repo root:
    .venv/bin/python tests/smoke/fasthigashi_smoke.py
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd


# Minimal mm10 chrom sizes; only entries listed in chrom_list are used.
MM10 = {
    "chr1": 195471971, "chr2": 182113224, "chr3": 160039680, "chr4": 156508116,
    "chr5": 151834684, "chr6": 149736546, "chr7": 145441459, "chr8": 129401213,
    "chr9": 124595110, "chr10": 130694993, "chr11": 122082543, "chr12": 120129022,
    "chr13": 120421639, "chr14": 124902244, "chr15": 104043685, "chr16": 98207768,
    "chr17": 94987271, "chr18": 90702639, "chr19": 61431566, "chrX": 171031299,
}


def main() -> None:
    from uchrom.io import write_higashi_inputs
    from uchrom.core import ChromData
    from uchrom.emb.higashi import run as higashi_run

    repo = Path(__file__).resolve().parent.parent.parent
    p1 = repo / "example-data" / "cell1.pairs"
    p2 = repo / "example-data" / "cell2.pairs.gz"
    assert p1.exists() and p2.exists(), "example pairs missing"

    labels = pd.DataFrame({"cell_name": ["cell1", "cell2"]})
    td = Path(tempfile.mkdtemp(prefix="uchrom_fh_"))
    print(f"work dir: {td}")

    t0 = time.time()
    contacts_dir = write_higashi_inputs(
        pairs_files={"cell1": p1, "cell2": p2},
        out_dir=td / "higashi",
        label_info=labels,
        resolution=1_000_000,
        genome_reference="mm10",
        chrom_list=list(MM10.keys()),
        chromsizes=MM10,
    )
    print(f"[{time.time()-t0:.1f}s] write_higashi_inputs done")

    cd = ChromData(
        coords=np.zeros((2, 3)),
        spots=pd.DataFrame({
            "chrom": ["chr1", "chr1"],
            "start": [0, 1_000_000],
            "end": [1_000_000, 2_000_000],
            "trace_id": ["t0", "t1"],
            "cell_id": ["cell1", "cell2"],
        }),
        cells=labels.copy(),
    )

    cd = higashi_run(
        cd,
        contacts_dir=contacts_dir,
        rank=2,
        cache_dir=td / "cache",
        result_dir=td / "result",
    )
    print(f"[{time.time()-t0:.1f}s] higashi_run done")
    print(f"emb shape: {cd.cellm['higashi'].shape}")
    print(f"emb:\n{cd.cellm['higashi']}")
    print(f"uns provenance: {cd.uns['higashi']}")

    # leave td around for inspection
    print(f"\n(work dir kept at {td})")


if __name__ == "__main__":
    main()
