"""Engine-agnostic validation and timing harness for NucDynamics (Fig. 3a).

Scores structure ensembles of the 8 haploid mESC cells of Stevens et al. 2017 (GEO GSE80280) at
100 kb against the paper and against the published (GEO) models, and times any engine on the same
inputs.  The engine is a black box: a command template (``run``) or a set of model files
(``evaluate``).  Reference algorithm: ``benchmarks/fig3/nucdyn_spec.md``.

Model files understood (one or many per cell; models are concatenated):

* ``.n3d``                 NucDynamics N3D (all models of a run in one file)
* ``.pdb`` / ``.pdb.gz``   extended PDB, sequence position in the last column (GEO / NucDynamics)
* ``.npz``                 keys ``chrom`` (str, N), ``pos`` (int, N), ``coords`` (M, N, 3)
                           [+ optional ``start``/``end`` (int, N)]
* ChromData stores         ``.chromdata.zarr`` / ``.cdz`` / ``.h5cd`` (one model per store, or
                           several models as ``layers`` named ``model_*``)

Particle convention.  NucDynamics particles are sequence *positions* ``pos``; a contact at ``p`` is
assigned to the first particle with ``pos >= p`` (spec §3), so the particle covers
``(pos - s, pos]``.  N3D / PDB / npz-without-start files use that convention; ChromData stores
and npz files with ``start``/``end`` use the half-open interval ``[start, end)``.  Particles
are matched between ensembles by the midpoint of their interval (same chromosome, nearest,
within half a particle).

Metrics per cell (``evaluate``):

* **precision** — RMSD of each model to the iteratively superposed ensemble mean
  (``rmsd_to_mean_mean``, radii): on the GEO models this reproduces ED Table 2 within 0.01 for
  all 8 cells, so it is the paper's number (the footnote says "mean pairwise"); also the mean
  pairwise RMSD without mirror (``rmsd_pair_mean``) and best of mirror (``rmsd_pair_mirror_mean``);
* **vs published** — every engine model vs every GEO model: RMSD (best of mirror) and the median
  over chromosomes of the Pearson r between distance matrices; the same for GEO vs GEO (ceiling);
* **restraints** — the cell's GEO contacts binned onto the ensemble's own particles; restraints
  between non-adjacent particles (``N_rest``, ED Table 2 definition) with ``n`` contacts get
  ``d_upper = 1.2 n^-0.33``; ``%V>3`` / ``%V>4`` = share with ``d > d_upper + 3 / 4``, mean over
  models.

Usage::

    python benchmarks/fig3/nucdyn_harness.py prepare --work W
    python benchmarks/fig3/nucdyn_harness.py run --work W --tag original \\
        --engine-cmd 'PY orig_run.py {ncc} {out}.n3d --models 10 --cpu 10 --seed {seed}' --cells 1
    python benchmarks/fig3/nucdyn_harness.py evaluate --label original \\
        --models 'W/original/cell{cell}/*.n3d' --cells 1-8 --out results.json
    python benchmarks/fig3/nucdyn_harness.py evaluate --label published --published-only --out x.json

Placeholders in ``--engine-cmd``: ``{ncc}`` (old 15-column NCC), ``{pairs}`` (7-column .pairs),
``{geo}`` (the GEO contact file), ``{out}`` (output stem, no suffix), ``{cell}``, ``{seed}``.
With ``--calls K`` the command runs K times per cell (seeds ``seed0 .. seed0+K-1``) for
engines that write one model per call.
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import glob
import gzip
import itertools
import json
import os
import platform
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GEO_DIR = data_dir() / "stevens2017_mesc"
GSM = {1: "GSM2219497", 2: "GSM2219498", 3: "GSM2219499", 4: "GSM2219500",
       5: "GSM2219501", 6: "GSM2219502", 7: "GSM2219503", 8: "GSM2219504"}
PDB_CHAINS = {chr(ord("a") + i): f"chr{i + 1}" for i in range(19)} | {"t": "chrX"}
PARTICLE_SIZE = 100_000

# Stevens et al. 2017, Extended Data Table 2: per stage (RMSD radii, N_rest, %V>3, %V>4).
# "100kb_final" = 100 kb with ambiguous restraints = the deposited GEO models.
ED_TABLE2 = {
    "400kb": {1: (0.13, 26453, 2.94, 0.76), 2: (0.29, 22838, 0.16, 0.00), 3: (0.24, 17944, 0.81, 0.28),
              4: (0.33, 25126, 2.35, 0.68), 5: (0.32, 23062, 1.18, 0.30), 6: (0.38, 25084, 0.60, 0.10),
              7: (0.81, 18301, 0.07, 0.04), 8: (0.49, 15877, 0.00, 0.00)},
    "200kb": {1: (2.32, 43150, 1.29, 0.08), 2: (0.50, 35244, 0.29, 0.00), 3: (0.51, 21049, 1.66, 0.08),
              4: (0.58, 37594, 1.26, 0.14), 5: (0.65, 34103, 0.86, 0.10), 6: (0.69, 35526, 0.70, 0.06),
              7: (1.26, 26585, 0.03, 0.00), 8: (0.93, 22956, 0.00, 0.00)},
    "100kb_unambig": {1: (0.56, 71729, 2.81, 0.57), 2: (0.88, 47598, 1.04, 0.15), 3: (0.89, 22822, 4.82, 1.36),
                      4: (1.03, 50516, 2.49, 0.94), 5: (1.08, 44298, 2.12, 0.73), 6: (1.09, 44687, 0.99, 0.22),
                      7: (1.91, 33588, 0.11, 0.01), 8: (1.52, 28083, 0.02, 0.02)},
    "100kb_final": {1: (0.41, 74945, 2.29, 0.22), 2: (0.63, 56159, 0.74, 0.13), 3: (0.70, 25952, 2.87, 0.42),
                    4: (0.74, 60420, 1.14, 0.17), 5: (0.86, 51824, 1.24, 0.21), 6: (0.91, 53710, 0.74, 0.17),
                    7: (1.75, 39257, 0.13, 0.02), 8: (1.26, 32482, 0.03, 0.02)},
}


# --------------------------------------------------------------------------- model sets
@dataclass
class ModelSet:
    chrom: np.ndarray    # (N,) str
    lo: np.ndarray       # (N,) int, particle interval start (exclusive for pos-convention, see below)
    hi: np.ndarray       # (N,) int
    coords: np.ndarray   # (M, N, 3) float64
    source: list

    @property
    def mid(self) -> np.ndarray:
        return (self.lo + self.hi) / 2.0

    @property
    def n_models(self) -> int:
        return self.coords.shape[0]

    def sorted(self) -> "ModelSet":
        order = np.lexsort((self.mid, self.chrom))
        return ModelSet(self.chrom[order], self.lo[order], self.hi[order], self.coords[:, order], self.source)


def _from_pos(chrom, pos, coords, source, size=None) -> ModelSet:
    chrom = np.asarray(chrom).astype(str)
    pos = np.asarray(pos, dtype=np.int64)
    if size is None:
        d = np.diff(pos)[(chrom[1:] == chrom[:-1])]
        size = int(np.median(d)) if len(d) else PARTICLE_SIZE
    return ModelSet(chrom, pos - size, pos, np.asarray(coords, float), source)


def read_n3d(path: str) -> ModelSet:
    chroms, poss, blocks = [], [], []
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as fh:
        lines = fh.read().split("\n")
    i = 0
    while i < len(lines):
        f = lines[i].split()
        i += 1
        if len(f) != 3 or f[0] == "#":
            continue
        c, n, m = f[0], int(f[1]), int(f[2])
        arr = np.array([lines[i + k].split() for k in range(n)], float)
        i += n
        chroms += [c] * n
        poss.append(arr[:, 0].astype(np.int64))
        blocks.append(arr[:, 1:].reshape(n, m, 3).transpose(1, 0, 2))
    return _from_pos(np.array(chroms), np.concatenate(poss), np.concatenate(blocks, axis=1), [path])


def read_pdb(path: str) -> ModelSet:
    models, rows = [], []
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as fh:
        for line in fh:
            if line.startswith("MODEL"):
                rows = []
            elif line.startswith("HETATM"):
                rows.append((PDB_CHAINS.get(line[21], line[21]), int(line.split()[-1]),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL"):
                models.append(pd.DataFrame(rows, columns=["chrom", "pos", "x", "y", "z"]))
    keys = models[0][["chrom", "pos"]]
    xyz = []
    for m in models:
        assert (m[["chrom", "pos"]].values == keys.values).all(), "models differ in particles"
        xyz.append(m[["x", "y", "z"]].to_numpy())
    return _from_pos(keys["chrom"].to_numpy(), keys["pos"].to_numpy(), np.stack(xyz), [path])


def read_npz(path: str) -> ModelSet:
    z = np.load(path, allow_pickle=False)
    if "start" in z and "end" in z:
        return ModelSet(z["chrom"].astype(str), z["start"].astype(np.int64), z["end"].astype(np.int64),
                        np.asarray(z["coords"], float), [path])
    return _from_pos(z["chrom"], z["pos"], z["coords"], [path])


def read_chromdata(path: str) -> ModelSet:
    for _pkg in ("uchrom", "chromdata"):   # this checkout's packages
        sys.path.insert(0, str(ROOT / "packages" / _pkg))
    from uchrom import ChromData

    cd = ChromData.read(path)
    loci = cd.spots_with_loci()
    models = [np.asarray(cd.coords, float)]
    names = sorted(k for k in cd.layers if str(k).startswith("model_"))
    if names:
        models = [np.asarray(cd.layers[k], float) for k in names]
    return ModelSet(loci["chrom"].astype(str).to_numpy(), loci["start"].to_numpy(np.int64),
                    loci["end"].to_numpy(np.int64), np.stack(models), [path])


def read_models(path: str) -> ModelSet:
    p = path.rstrip("/")
    if p.endswith(".n3d") or p.endswith(".n3d.gz"):
        return read_n3d(p)
    if p.endswith(".pdb") or p.endswith(".pdb.gz"):
        return read_pdb(p)
    if p.endswith(".npz"):
        return read_npz(p)
    return read_chromdata(p)


def concat_models(sets: list[ModelSet]) -> ModelSet:
    sets = [s.sorted() for s in sets]
    base = sets[0]
    for s in sets[1:]:
        if len(s.chrom) != len(base.chrom) or not (s.chrom == base.chrom).all() or not (s.mid == base.mid).all():
            raise ValueError(f"particle sets differ between {base.source} and {s.source}")
    return ModelSet(base.chrom, base.lo, base.hi, np.concatenate([s.coords for s in sets]),
                    sum((s.source for s in sets), []))


def load_ensemble(paths: list[str]) -> ModelSet:
    return concat_models([read_models(p) for p in paths])


def published(cell: int) -> ModelSet:
    return read_pdb(str(GEO_DIR / f"{GSM[cell]}_Cell_{cell}_genome_structure_model.pdb.gz")).sorted()


def geo_contacts(cell: int) -> pd.DataFrame:
    df = pd.read_csv(GEO_DIR / f"{GSM[cell]}_Cell_{cell}_contact_pairs.txt.gz", sep="\t")
    df.columns = ["c1", "p1", "c2", "p2"]
    return df


# --------------------------------------------------------------------------- geometry
def superpose(a: np.ndarray, b: np.ndarray, mirror: bool = False) -> tuple[float, np.ndarray]:
    """RMSD of b onto a after centring + optimal rotation (+ reflection if ``mirror``)."""
    a = a - a.mean(0)
    b = b - b.mean(0)
    u, _, vt = np.linalg.svd(b.T @ a)
    d = 1.0 if mirror else np.sign(np.linalg.det(u @ vt))
    r = u @ np.diag([1.0, 1.0, d]) @ vt
    bb = b @ r
    return float(np.sqrt(((bb - a) ** 2).sum(1).mean())), bb


def rmsd(a, b, mirror=False) -> float:
    return superpose(a, b, mirror)[0]


def rmsd_best_mirror(a, b) -> float:
    return min(rmsd(a, b, False), rmsd(a, -b, False))


def dist_r_by_chrom(chrom: np.ndarray, a: np.ndarray, b: np.ndarray, min_n: int = 10) -> float:
    rs = []
    for c in np.unique(chrom):
        idx = np.flatnonzero(chrom == c)
        if len(idx) < min_n:
            continue
        iu = np.triu_indices(len(idx), 1)
        da = np.linalg.norm(a[idx, None] - a[None, idx], axis=-1)[iu]
        db = np.linalg.norm(b[idx, None] - b[None, idx], axis=-1)[iu]
        rs.append(np.corrcoef(da, db)[0, 1])
    return float(np.median(rs))


def precision(ms: ModelSet) -> dict:
    X = ms.coords
    pairs = list(itertools.combinations(range(len(X)), 2))
    plain = [rmsd(X[i], X[j]) for i, j in pairs]
    mirr = [rmsd_best_mirror(X[i], X[j]) for i, j in pairs]
    # iterative superposition on the mean (mirror images flipped to the first model's hand)
    ref = X[0] - X[0].mean(0)
    al = []
    for x in X:
        x = -x if rmsd(ref, -x) < rmsd(ref, x) else x
        al.append(superpose(ref, x)[1])
    for _ in range(3):
        mean = np.mean(al, axis=0)
        al = [superpose(mean, x)[1] for x in al]
    mean = np.mean(al, axis=0)
    to_mean = [float(np.sqrt(((x - mean) ** 2).sum(1).mean())) for x in al]
    sem = lambda v: float(np.std(v, ddof=1) / np.sqrt(len(v))) if len(v) > 1 else float("nan")
    return {"n_models": len(X), "n_pairs": len(pairs),
            "rmsd_pair_mean": float(np.mean(plain)) if pairs else None, "rmsd_pair_sem": sem(plain) if pairs else None,
            "rmsd_pair_mirror_mean": float(np.mean(mirr)) if pairs else None,
            "rmsd_pair_mirror_sem": sem(mirr) if pairs else None,
            "n_mirror_pairs": int(sum(m < p - 1e-9 for m, p in zip(mirr, plain))),
            "rmsd_to_mean_mean": float(np.mean(to_mean)),
            "rg_mean": float(np.mean([np.sqrt(((x - x.mean(0)) ** 2).sum(1).mean()) for x in X]))}


def match(ours: ModelSet, ref: ModelSet) -> tuple[np.ndarray, np.ndarray]:
    """Indices (i_ours, i_ref) of particles matched by interval midpoint, same chromosome."""
    io, ir = [], []
    tol = 0.5 * np.median(ref.hi - ref.lo)
    for c in np.unique(ours.chrom):
        a = np.flatnonzero(ours.chrom == c)
        b = np.flatnonzero(ref.chrom == c)
        if len(b) == 0:
            continue
        mb = ref.mid[b]
        k = np.clip(np.searchsorted(mb, ours.mid[a]), 1, max(1, len(b) - 1))
        k = np.where(np.abs(mb[k - 1] - ours.mid[a]) <= np.abs(mb[np.minimum(k, len(b) - 1)] - ours.mid[a]), k - 1,
                     np.minimum(k, len(b) - 1))
        ok = np.abs(mb[k] - ours.mid[a]) <= tol
        io.append(a[ok])
        ir.append(b[k[ok]])
    return np.concatenate(io), np.concatenate(ir)


def versus(ours: ModelSet, ref: ModelSet, same: bool = False) -> dict:
    io, ir = match(ours, ref)
    chrom = ours.chrom[io]
    rm, rr = [], []
    for i in range(ours.n_models):
        for j in range(ref.n_models):
            if same and j <= i:
                continue
            a, b = ours.coords[i][io], ref.coords[j][ir]
            rm.append(rmsd_best_mirror(a, b))
            rr.append(dist_r_by_chrom(chrom, a, b))
    return {"n_matched": int(len(io)), "frac_matched_ours": float(len(io) / len(ours.chrom)),
            "frac_matched_ref": float(len(np.unique(ir)) / len(ref.chrom)),
            "n_pairs": len(rm), "rmsd_mirror_mean": float(np.mean(rm)), "rmsd_mirror_min": float(np.min(rm)),
            "rmsd_mirror_max": float(np.max(rm)), "dist_r_median_mean": float(np.mean(rr)),
            "dist_r_median_min": float(np.min(rr))}


def restraint_violations(ms: ModelSet, contacts: pd.DataFrame, exponent: float = -0.33,
                         upper: float = 1.2) -> dict:
    """GEO contacts binned onto the ensemble's particles; ED Table 2 style violation shares."""
    idx = {}
    for c in np.unique(ms.chrom):
        a = np.flatnonzero(ms.chrom == c)
        idx[c] = (a, ms.lo[a], ms.hi[a])

    def particle(chrom, pos):
        out = np.full(len(pos), -1)
        for c in np.unique(chrom):
            if c not in idx:
                continue
            a, lo, hi = idx[c]
            sel = np.flatnonzero(chrom == c)
            p = pos[sel]
            # half-open (lo, hi] for position-convention particles, [lo, hi) for intervals: use the
            # interval that contains p, preferring (lo, hi] (the NucDynamics rule) on exact edges
            k = np.searchsorted(hi, p, side="left")
            ok = (k < len(hi))
            kk = np.minimum(k, len(hi) - 1)
            ok &= p > lo[kk] - 1
            out[sel[ok]] = a[kk[ok]]
        return out

    i = particle(contacts["c1"].to_numpy().astype(str), contacts["p1"].to_numpy())
    j = particle(contacts["c2"].to_numpy().astype(str), contacts["p2"].to_numpy())
    ok = (i >= 0) & (j >= 0)
    lo, hi = np.minimum(i[ok], j[ok]), np.maximum(i[ok], j[ok])
    pairs, n = np.unique(np.c_[lo, hi], axis=0, return_counts=True)
    same_chrom = ms.chrom[pairs[:, 0]] == ms.chrom[pairs[:, 1]]
    nonadj = ~same_chrom | (pairs[:, 1] - pairs[:, 0] >= 2)
    pairs, n = pairs[nonadj], n[nonadj]
    d_up = upper * n.astype(float) ** exponent
    w = n / n.sum()
    stats = {k: [] for k in ("v3", "v4", "cv3", "cv4", "a3", "a4", "med")}
    for X in ms.coords:
        d = np.linalg.norm(X[pairs[:, 0]] - X[pairs[:, 1]], axis=1)
        stats["v3"].append(100 * np.mean(d > d_up + 3.0))          # per restraint, above d_upper
        stats["v4"].append(100 * np.mean(d > d_up + 4.0))
        stats["cv3"].append(100 * np.sum(w * (d > d_up + 3.0)))    # per contact (weighted by n)
        stats["cv4"].append(100 * np.sum(w * (d > d_up + 4.0)))
        stats["a3"].append(100 * np.mean(d > 3.0))                 # absolute distance, per restraint
        stats["a4"].append(100 * np.mean(d > 4.0))
        stats["med"].append(float(np.median(d)))
    m = {k: float(np.mean(v)) for k, v in stats.items()}
    return {"n_contacts": int(len(contacts)), "n_contacts_binned": int(ok.sum()), "N_rest": int(len(pairs)),
            "n_contacts_nonadjacent": int(n.sum()),
            "pct_viol_gt3": m["v3"], "pct_viol_gt4": m["v4"],
            "pct_viol_gt3_contact_weighted": m["cv3"], "pct_viol_gt4_contact_weighted": m["cv4"],
            "pct_dist_gt3_abs": m["a3"], "pct_dist_gt4_abs": m["a4"],
            "pct_viol_gt4_per_model": [float(x) for x in stats["v4"]], "median_restraint_dist": m["med"]}


def evaluate_cell(cell: int, ms: ModelSet | None, with_published: bool = True) -> dict:
    pub = published(cell)
    contacts = geo_contacts(cell)
    ed = {k: dict(zip(("rmsd", "N_rest", "pct_viol_gt3", "pct_viol_gt4"), v[cell])) for k, v in ED_TABLE2.items()}
    out = {"cell": cell, "ed_table2": ed}
    if with_published:
        out["published"] = {"n_particles": int(len(pub.chrom)), "precision": precision(pub),
                            "restraints": restraint_violations(pub, contacts),
                            "vs_published": versus(pub, pub, same=True)}
    if ms is not None:
        ms = ms.sorted()
        out["engine"] = {"n_particles": int(len(ms.chrom)), "sources": ms.source, "precision": precision(ms),
                         "restraints": restraint_violations(ms, contacts), "vs_published": versus(ms, pub)}
    return out


# --------------------------------------------------------------------------- inputs
def prepare(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    for cell in GSM:
        df = geo_contacts(cell)
        ncc, pairs = work / f"cell{cell}.ncc", work / f"cell{cell}.pairs"
        if not ncc.exists():
            with open(ncc, "w") as o:
                for k, (a, pa, b, pb) in enumerate(df.itertuples(index=False)):
                    o.write(f"{a} {pa} {pa} {pa} {pa} + {b} {pb} {pb} {pb} {pb} + 0 {k} 0\n")
        if not pairs.exists():
            with open(pairs, "w") as o:
                for k, (a, pa, b, pb) in enumerate(df.itertuples(index=False)):
                    o.write(f"r{k}\t{a}\t{pa}\t{b}\t{pb}\t+\t+\n")
        print(f"cell {cell}: {len(df):,} contacts -> {ncc.name}, {pairs.name}")


# --------------------------------------------------------------------------- timing
def hardware() -> dict:
    info = {"platform": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0]}
    try:
        import psutil
        info["logical_cpus"] = psutil.cpu_count()
        info["physical_cpus"] = psutil.cpu_count(logical=False)
        info["memory_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
    except ImportError:
        info["logical_cpus"] = os.cpu_count()
    if sys.platform == "darwin":
        def sysctl(k):
            try:
                return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True).stdout.strip()
            except OSError:
                return None
        info["cpu"] = sysctl("machdep.cpu.brand_string")
        info["perf_cores"] = sysctl("hw.perflevel0.physicalcpu")
        info["efficiency_or_second_tier_cores"] = sysctl("hw.perflevel1.physicalcpu")
        try:
            sp = subprocess.run(["system_profiler", "SPDisplaysDataType"], capture_output=True, text=True).stdout
            gpu = [l.strip() for l in sp.splitlines() if "Chipset Model" in l or "Total Number of Cores" in l]
            info["gpu"] = "; ".join(gpu)
        except OSError:
            pass
    else:
        try:
            info["cpu"] = [l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")][0]
        except (OSError, IndexError):
            pass
    return info


def run_timed(cmd: str, log: Path) -> dict:
    """Run ``cmd``; wall time, CPU time and peak RSS summed over the process tree (sampled 0.2 s)."""
    import psutil

    peak = {"rss": 0, "procs": 0}
    t0 = time.perf_counter()
    with open(log, "w") as fh:
        proc = subprocess.Popen(cmd, shell=True, stdout=fh, stderr=subprocess.STDOUT)
        root = psutil.Process(proc.pid)
        stop = threading.Event()
        cpu_seen = {}

        def sample():
            while not stop.is_set():
                try:
                    procs = [root] + root.children(recursive=True)
                    rss = 0
                    for p in procs:
                        try:
                            rss += p.memory_info().rss
                            ct = p.cpu_times()
                            cpu_seen[p.pid] = ct.user + ct.system
                        except psutil.Error:
                            pass
                    peak["rss"] = max(peak["rss"], rss)
                    peak["procs"] = max(peak["procs"], len(procs))
                except psutil.Error:
                    pass
                stop.wait(0.2)

        th = threading.Thread(target=sample, daemon=True)
        th.start()
        rc = proc.wait()
        stop.set()
        th.join()
    wall = time.perf_counter() - t0
    return {"cmd": cmd, "returncode": rc, "wall_s": wall, "peak_rss_tree_gb": peak["rss"] / 2**30,
            "max_processes": peak["procs"], "cpu_s_sampled": float(sum(cpu_seen.values()))}


def cmd_run(a) -> None:
    work = Path(a.work)
    res = {"tag": a.tag, "engine_cmd": a.engine_cmd, "hardware": hardware(), "runs": []}
    for cell in a.cells:
        outdir = work / a.tag / f"cell{cell}"
        outdir.mkdir(parents=True, exist_ok=True)
        for k in range(a.calls):
            seed = a.seed + k
            out = outdir / f"cell{cell}_s{seed}"
            cmd = a.engine_cmd.format(ncc=work / f"cell{cell}.ncc", pairs=work / f"cell{cell}.pairs",
                                      geo=GEO_DIR / f"{GSM[cell]}_Cell_{cell}_contact_pairs.txt.gz",
                                      out=out, cell=cell, seed=seed)
            r = run_timed(cmd, outdir / f"cell{cell}_s{seed}.log")
            r.update(cell=cell, seed=seed)
            print(json.dumps({k: v for k, v in r.items() if k != "cmd"}), flush=True)
            res["runs"].append(r)
            if a.json:
                Path(a.json).write_text(json.dumps(res, indent=1))


def parse_cells(s: str) -> list[int]:
    out = []
    for part in s.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            out += list(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    return out


def cmd_evaluate(a) -> None:
    res = {"label": a.label, "models_pattern": a.models, "particle_size": PARTICLE_SIZE, "cells": []}
    for cell in a.cells:
        ms = None
        if not a.published_only:
            paths = sorted(glob.glob(a.models.format(cell=cell)))
            if not paths:
                print(f"cell {cell}: no models for {a.models.format(cell=cell)}", file=sys.stderr)
                continue
            ms = load_ensemble(paths)
        t0 = time.perf_counter()
        r = evaluate_cell(cell, ms, with_published=not a.no_published)
        r["eval_s"] = time.perf_counter() - t0
        res["cells"].append(r)
        brief = {"cell": cell, "ED_rmsd": r["ed_table2"]["100kb_final"]["rmsd"]}
        for who in ("published", "engine"):
            if who in r:
                brief[who] = {"rmsd_to_mean": round(r[who]["precision"]["rmsd_to_mean_mean"], 3),
                              "rmsd_pair": round(r[who]["precision"]["rmsd_pair_mean"] or float("nan"), 3),
                              "rmsd_pair_mirror": round(r[who]["precision"]["rmsd_pair_mirror_mean"] or float("nan"), 3),
                              "vs_pub_rmsd": round(r[who]["vs_published"]["rmsd_mirror_mean"], 3),
                              "vs_pub_r": round(r[who]["vs_published"]["dist_r_median_mean"], 4),
                              "rg": round(r[who]["precision"]["rg_mean"], 2),
                              "N_rest": r[who]["restraints"]["N_rest"],
                              "V4": round(r[who]["restraints"]["pct_viol_gt4"], 3)}
        print(json.dumps(brief), flush=True)
        if a.out:
            Path(a.out).write_text(json.dumps(res, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--work", required=True)
    p = sub.add_parser("run")
    p.add_argument("--work", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--engine-cmd", required=True)
    p.add_argument("--cells", type=parse_cells, default=parse_cells("1-8"))
    p.add_argument("--calls", type=int, default=1)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--json")
    p = sub.add_parser("evaluate")
    p.add_argument("--label", required=True)
    p.add_argument("--models", default="", help="glob with {cell}, e.g. 'W/tag/cell{cell}/*.n3d'")
    p.add_argument("--cells", type=parse_cells, default=parse_cells("1-8"))
    p.add_argument("--published-only", action="store_true")
    p.add_argument("--no-published", action="store_true", help="skip the published-vs-published block")
    p.add_argument("--out")
    a = ap.parse_args()
    {"prepare": lambda: prepare(Path(a.work)), "run": lambda: cmd_run(a), "evaluate": lambda: cmd_evaluate(a)}[a.cmd]()


if __name__ == "__main__":
    main()
