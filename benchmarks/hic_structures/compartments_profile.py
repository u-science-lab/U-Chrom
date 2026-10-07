"""Run time and memory of ``call_compartments_eig`` and ``compartment_strength`` on IMR90 chr1 (Rao et al.
2014; the largest chromosome) at 100 kb, 25 kb and 5 kb, with the time split by stage (cProfile): reading
the pixels (HDF5), the clipping percentile, the Lanczos iterations (sparse matrix-vector products of
``O/E - 1``), the rest.  Each resolution runs in its own process (peak resident memory).  Writes
``compartments_profile.json`` to ``--out`` (default ``$UCHROM_BENCH_OUT``, else a temporary directory)::

    python benchmarks/hic_structures/compartments_profile.py --out /path/to/scratch
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _worker(path: str) -> dict:
    import cProfile
    import pstats
    import resource
    import time
    import warnings

    import cooler

    from uchrom.strc.comp.eig import call_compartments_eig, compartment_strength

    warnings.filterwarnings("ignore")
    clr = cooler.Cooler(path)
    out = {"bins": int(len(clr.bins())), "pixels": int(clr.info["nnz"]), "resolution": int(clr.binsize)}

    def stages(prof):
        st = pstats.Stats(prof).stats
        tot = {"read_pixels_hdf5": 0.0, "lanczos_matvec": 0.0, "clip_percentile": 0.0, "matvec_calls": 0}
        for (file, _, name), (_, ncalls, tottime, cumtime, _) in st.items():
            if name == "__getitem__" and "h5py" in file:
                tot["read_pixels_hdf5"] += tottime
            elif name in ("csr_matvec", "csc_matvec") or "csr_matvec" in name or "csc_matvec" in name:
                tot["lanczos_matvec"] += tottime
                tot["matvec_calls"] += ncalls
            elif name == "_clip_threshold":
                tot["clip_percentile"] += cumtime
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in tot.items()}

    prof = cProfile.Profile()
    t = time.time()
    prof.enable()
    table = call_compartments_eig(path)
    prof.disable()
    out["eig_s"] = round(time.time() - t, 3)
    out["eig_stages"] = stages(prof)
    out["valid_bins"] = int(len(table))
    out["eig_maxrss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 30, 2)  # macOS: bytes
    prof = cProfile.Profile()
    t = time.time()
    prof.enable()
    sad = compartment_strength(path, compartments=table)
    prof.disable()
    out["saddle_s"] = round(time.time() - t, 3)
    out["saddle_stages"] = stages(prof)
    out["strength"] = round(float(sad["strength"]), 4)
    out["total_maxrss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 30, 2)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.environ.get("UCHROM_BENCH_OUT") or tempfile.mkdtemp(prefix="hic_comp_"))
    ap.add_argument("--worker", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.worker:
        print(json.dumps(_worker(args.worker)))
        return None
    import uchrom.datasets as ds
    from uchrom.fea.maps import rebin_map

    out = Path(args.out)
    (out / "maps").mkdir(parents=True, exist_ok=True)
    src = Path(ds.fetch("rao2014_imr90_chr1"))
    rows = []
    for res in (100_000, 25_000, 5_000):
        path = out / "maps" / f"imr90_chr1_{res // 1000}k.cool"
        if not path.exists():
            rebin_map(str(src), resolution=res, out=str(path))          # balanced (ICE) at every resolution
        run = subprocess.run([sys.executable, __file__, "--worker", str(path)], check=True, capture_output=True,
                             text=True)
        row = json.loads(run.stdout.strip().splitlines()[-1])
        rows.append(row)
        print(row, flush=True)
    (out / "compartments_profile.json").write_text(json.dumps(rows, indent=1))
    print(f"wrote {out / 'compartments_profile.json'}")
    return rows


if __name__ == "__main__":
    main(sys.argv[1:])
