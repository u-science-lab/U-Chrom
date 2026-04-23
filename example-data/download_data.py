"""Pre-stage every large dataset used by the tutorials.

Idempotent: files already present are skipped.  Normally you don't need
to run this — each tutorial auto-downloads what it needs on first use.
It's convenient for offline / CI setups or when you want everything
ready before running nbconvert.

Usage::

    python example-data/download_data.py           # fetch everything
    python example-data/download_data.py --takei   # just Takei 2021 FOF-CT
    python example-data/download_data.py --seqfish # just seqFISH+ zip
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent

DATASETS = {
    "takei": {
        "filename": "4DNFIHF3JCBY.csv",
        "url": (
            "https://4dn-open-data-public.s3.amazonaws.com/"
            "fourfront-webprod/wfoutput/"
            "e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv"
        ),
        "size_mb": 22,
        "description": "Takei 2021 mESC FOF-CT chromatin tracing",
    },
    "seqfish": {
        "filename": "DNAseqFISH+.zip",
        "url": (
            "https://zenodo.org/records/3735329/files/"
            "DNAseqFISH%2B.zip?download=1"
        ),
        "size_mb": 144,
        "description": "Takei 2021 raw seqFISH+ spot detections",
    },
    "bintu_imr90": {
        "filename": "IMR90_chr21-18-20Mb.csv",
        "url": (
            "https://raw.githubusercontent.com/BogdanBintu/"
            "ChromatinImaging/master/Data/IMR90_chr21-18-20Mb.csv"
        ),
        "size_mb": 2,
        "description": "Bintu 2018 IMR90 chr21 chromatin tracing",
    },
}


def _download(url: str, dest: Path, description: str, size_mb: int) -> None:
    if dest.exists():
        print(f"[skip] {dest.name} already present ({description})")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"[pull] {description} (~{size_mb} MB) → {dest}")
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        print(f"[fail] {dest.name}: {exc}", file=sys.stderr)
        raise


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    for key, info in DATASETS.items():
        ap.add_argument(
            f"--{key}", action="store_true",
            help=f"fetch {info['description']} ({info['size_mb']} MB)",
        )
    args = ap.parse_args()
    selected = [k for k in DATASETS if getattr(args, k)]
    if not selected:
        selected = list(DATASETS)

    for key in selected:
        info = DATASETS[key]
        _download(info["url"], HERE / info["filename"],
                  info["description"], info["size_mb"])

    print(f"\nAll requested datasets staged under: {HERE}")


if __name__ == "__main__":
    main()
