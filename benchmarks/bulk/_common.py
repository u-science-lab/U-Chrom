"""Shared helpers of the bulk deconvolution benchmark (numpy / pandas / scipy only).

The benchmark runs in the Sherlock ``venv-main`` (no U-Chrom install), so the one library
module it needs, ``uchrom/recon/bulk/deconv/preprocess.py`` (numpy / pandas / scipy only), is
loaded from its file path instead of ``import uchrom``; the screcon helpers are imported from
``benchmarks/screcon``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRECON = ROOT / "benchmarks" / "screcon"
for _p in (str(HERE), str(SCRECON)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def load_preprocess():
    """``uchrom.recon.bulk.deconv.preprocess`` without importing the ``uchrom`` package."""
    name = "uchrom_deconv_preprocess"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "uchrom/recon/bulk/deconv/preprocess.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def example_data() -> Path:
    if os.environ.get("UCHROM_EXAMPLE_DATA"):
        return Path(os.environ["UCHROM_EXAMPLE_DATA"])
    return ROOT / "example-data"


def jdump(obj) -> str:
    def default(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.bool_):
            return bool(o)
        return str(o)
    return json.dumps(obj, indent=1, default=default)


# 4DN / GEO sources of the real-data inputs (catalogued in example-data/README.md)
RAO_IMR90_4DN = ("https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
                 "d10655ab-5bdf-4449-ab5a-82188af29868/4DNFIR1JDZH7.mcool")        # GRCh38, 4,639,622,711 B
RAO_IMR90_GEO = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl/GSE63525_IMR90_combined.hic"  # hg19
BONEV_4DN = ("https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
             "2b448d99-d3fb-4bb9-a126-386ccb99a6fd/4DNFIC21MG3U.mcool")            # mm10, 12,551,353,248 B
