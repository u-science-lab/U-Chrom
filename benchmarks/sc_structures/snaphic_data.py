"""Inputs of the SnapHiC validation: the Nagano 2017 diploid serum mES cells as a ``ChromData`` (10 kb maps).

    python benchmarks/sc_structures/snaphic_data.py [--out DIR]

SnapHiC (Yu et al. 2021) used the 1,175 diploid serum mES cells of Nagano et al. 2017 (GEO GSE94489) and kept
the 742 with the most contacts.  The loader ``nagano2017_dip_serum`` (``uchrom/datasets/_load_snaphic.py``)
builds them from the Tanay lab's fend-pair tables; its files are the proposed fetch() entry
``nagano2017_dip_serum``.  Until that entry is registered, this script downloads the same files from the same
URLs (md5-checked; GATC.fends and the mm9 -> mm10 chain are those of the registered ``nagano2017_hap``) and runs
the loader with ``fetch`` pointed at them.  Prints the cells' contact numbers and writes
``snaphic_data.json`` to ``--out``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snaphic_common as C  # noqa: E402

SCHIC2 = "https://schic2.s3.eu-west-1.amazonaws.com"
GSE = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE94nnn/GSE94489/suppl"
#: the files of the proposed registry entry nagano2017_dip_serum (path, URL, md5)
FILES = [
    ("nagano2017_dip/schic_hyb_1CDS1_adj_files.tar.gz", f"{SCHIC2}/schic_hyb_1CDS1_adj_files.tar.gz",
     "fa1f498f25c3ee19788583b4bc2975ea"),
    ("nagano2017_dip/schic_hyb_1CDS2_adj_files.tar.gz", f"{SCHIC2}/schic_hyb_1CDS2_adj_files.tar.gz",
     "fa594c9750f16da95e13d97edf6b6c15"),
    ("nagano2017_dip/GSE94489_serum_diploids_features_table.txt.gz",
     f"{GSE}/GSE94489_serum_diploids_features_table.txt.gz", "f0b506709c078f5ce5252ae4ed17a27a"),
]


def ensure_files(root: Path) -> None:
    import uchrom.datasets as ds
    from uchrom.datasets._fetch import download, md5
    from uchrom.datasets._sources import DATASETS

    if "nagano2017_dip_serum" in DATASETS:
        ds.fetch("nagano2017_dip_serum", root=root)
        return
    for rel, url, want in FILES:
        p = download(url, root / rel, rel)
        if md5(p) != want:
            raise IOError(f"md5 mismatch for {p}")
    for rel in ("nagano2017_hap/GATC.fends", "nagano2017_hap/mm9ToMm10.over.chain.gz"):
        if not (root / rel).exists():
            ds.fetch("nagano2017_hap", root=root)
            break


def build(root: Path):
    """The store (built once; the loader's version decides when it is rebuilt)."""
    import uchrom.datasets as ds
    import uchrom.datasets._load_snaphic  # noqa: F401  (registers the loader until _loaders lists the module)
    from uchrom.datasets._sources import DATASETS

    if "nagano2017_dip_serum" not in DATASETS:
        ds.fetch = lambda name, root=None, **kw: root            # files checked by ensure_files
    return ds.load("nagano2017_dip_serum", root=root)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    root = C.data_dir()
    t0 = time.time()
    ensure_files(root)
    t1 = time.time()
    cd = build(root)
    t2 = time.time()
    cells = cd.cells
    top = cells[cells["snaphic_top742"]]
    res = {"n_cells": int(len(cells)), "n_top742": int(len(top)),
           "min_contacts_top742": int(top["n_contacts"].min()),
           "median_contacts_top742": float(top["n_contacts"].median()),
           "median_cis_top742": float(top["n_cis"].median()),
           "n_tanay_over_150k": int((cells["total_contacts"] > 150_000).sum()),
           "overlap_top742_with_top742_by_tanay_total": int(
               (cells["total_contacts"].rank(ascending=False, method="first") <= 742)[cells["snaphic_top742"]].sum()),
           "download_s": t1 - t0, "build_s": t2 - t1, "peak_rss_gb": C.peak_rss_gb()}
    print(cells[["n_contacts", "n_cis", "total_contacts"]].describe().to_string())
    for k, v in res.items():
        print(f"{k:45s} {v}")
    C.write_json(res, args.out / "snaphic_data.json")


if __name__ == "__main__":
    main()
