"""Speed and memory of the native IGM protocol vs population size S and bead count N.

Each case runs ONE A-step at the final threshold (σ = 0.01) and ONE full M-step
(demo annealing protocol: 4 stages + relax blocks + CG; 47,000 MD steps) on a
population from the random start, and records the engine's per-step timings and the
peak GPU memory (``nvidia-smi`` polled every 0.5 s).

Inputs:
* ``demo``  — the IGM demo matrix (WTC11 2 Mb, 3,040 beads male); ``demo:chr1,chr2`` a subset;
* ``synthetic:<bin size>`` — hg38 chr1–22 + X at the given bin size (diploid; e.g.
  1000000 -> 6,2xx beads, 200000 -> 30,9xx beads) with a SYNTHETIC probability matrix
  (intra p(s) = min(1, s^-1) above 0.005, 5 % of inter pairs at U(0.01, 0.03)).  Used
  for timing / memory only — never for validation.

    python benchmarks/bulk/igm_scaling.py --inputs demo synthetic:1000000 --structures 100 1000 10000 \
        --device gpu --out runs/igm_scaling_h100.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _igm_bench as B  # noqa: E402

HG38 = {  # chromosome lengths (bp), GRCh38
    "chr1": 248956422, "chr2": 242193529, "chr3": 198295559, "chr4": 190214555, "chr5": 181538259,
    "chr6": 170805979, "chr7": 159345973, "chr8": 145138636, "chr9": 138394717, "chr10": 133797422,
    "chr11": 135086622, "chr12": 133275309, "chr13": 114364328, "chr14": 107043718, "chr15": 101991189,
    "chr16": 90338345, "chr17": 83257441, "chr18": 80373285, "chr19": 58617616, "chr20": 64444167,
    "chr21": 46709983, "chr22": 50818468, "chrX": 156040895,
}


def synthetic_input(res: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    chrom, start = [], []
    for c, L in HG38.items():
        s = np.arange(0, L, res)
        chrom += [c] * len(s)
        start.append(s)
    start = np.concatenate(start).astype(np.int64)
    chrom = np.array(chrom)
    end = np.minimum(start + res, np.array([HG38[c] for c in chrom]))
    n = len(chrom)
    ii, jj, vv = [], [], []
    cstart = {c: np.flatnonzero(chrom == c)[0] for c in HG38}
    for c in HG38:
        a = cstart[c]
        m = int((chrom == c).sum())
        smax = min(m - 1, 200)
        for s in range(1, smax + 1):
            p = min(1.0, s ** -1.0)
            if p < 0.005:
                break
            k = np.arange(a, a + m - s)
            ii.append(k)
            jj.append(k + s)
            vv.append(np.full(len(k), p))
    # sparse inter pairs
    n_inter = int(0.05 * n * n / 2 * 0.9)
    a = rng.integers(0, n, n_inter)
    b = rng.integers(0, n, n_inter)
    ok = chrom[a] != chrom[b]
    a, b = np.minimum(a[ok], b[ok]), np.maximum(a[ok], b[ok])
    ii.append(a)
    jj.append(b)
    vv.append(rng.uniform(0.01, 0.03, len(a)))
    i, j, v = np.concatenate(ii), np.concatenate(jj), np.concatenate(vv)
    key = i * n + j
    _, first = np.unique(key, return_index=True)
    return chrom, start, end, i[first], j[first], v[first]


class GpuMem:
    """Peak used GPU memory (MiB) from nvidia-smi while the context is open."""

    def __init__(self):
        self.peak = None
        self._stop = threading.Event()

    def _poll(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout
                v = max(int(x) for x in out.split())
                self.peak = v if self.peak is None else max(self.peak, v)
            except Exception:
                return
            self._stop.wait(0.5)

    def __enter__(self):
        self._t = threading.Thread(target=self._poll, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=5)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", nargs="+", default=["demo"])
    ap.add_argument("--structures", type=int, nargs="+", default=[100, 1000])
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--hcs", type=Path, default=None)
    ap.add_argument("--steps-scale", type=float, default=1.0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    import uchrom_nucdyn as un

    rows = []
    if a.out.exists():
        rows = json.loads(a.out.read_text())
    for spec in a.inputs:
        if spec.startswith("demo"):
            d = B.read_hcs(a.hcs or B.fetch_igm_demo())
            chrom, start, end, i, j, v = d["chrom"], d["start"], d["end"], d["i"], d["j"], d["v"]
            if ":" in spec:
                keep = np.isin(chrom, spec.split(":", 1)[1].split(","))
                new = np.full(len(chrom), -1)
                new[keep] = np.arange(keep.sum())
                m = keep[i] & keep[j]
                i, j, v = new[i[m]], new[j[m]], v[m]
                chrom, start, end = chrom[keep], start[keep], end[keep]
            ploidy = "male"
        elif spec.startswith("synthetic:"):
            chrom, start, end, i, j, v = synthetic_input(int(spec.split(":")[1]))
            ploidy = "diploid"
        else:
            raise ValueError(spec)
        for S in a.structures:
            params = dict(B.DEMO_PARAMS)
            if a.steps_scale != 1.0:
                params["stages"] = [dict(s, mdsteps=max(1, int(s["mdsteps"] * a.steps_scale))) for s in params["stages"]]
                params["relax"] = dict(params["relax"], mdsteps=max(1, int(params["relax"]["mdsteps"] * a.steps_scale)))
            params.update(intra_sigma_list=[0.01], inter_sigma_list=[0.01], max_iterations=1,
                          force_last_iteration=False, skip_relax_init=True)
            t0 = time.time()
            with GpuMem() as mem:
                try:
                    res = un.calc_population(chrom, start, end, i, j, v, ploidy=ploidy, n_structures=S,
                                             device=a.device, seed=1, **params)
                    err = None
                except Exception as e:  # out of memory, device limits
                    res, err = None, str(e)
            row = {"input": spec, "n_bins": int(len(chrom)), "n_pairs": int(len(v)), "n_structures": S,
                   "device": a.device, "steps_scale": a.steps_scale, "seconds_wall": time.time() - t0,
                   "gpu_mem_peak_mib": mem.peak, "error": err}
            if res is not None:
                r = res["rounds"][-1]
                nb = int(len(res["bead_bin"]))
                steps = sum(s["mdsteps"] for s in params["stages"]) + len(params["stages"]) * params["relax"]["mdsteps"]
                row.update(engine=res["engine"], n_beads=nb, seconds_astep=r["seconds_astep"],
                           seconds_mstep=r["seconds_mstep"], md_steps=steps,
                           hic_bonds_per_structure=r["n_hic_bonds"] / S,
                           n_pairs_restrained=r["n_pairs_restrained"],
                           particle_steps_per_s=nb * S * steps / r["seconds_mstep"])
            print(json.dumps(row), flush=True)
            rows.append(row)
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
