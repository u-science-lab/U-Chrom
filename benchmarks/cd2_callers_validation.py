"""ChromData 2.0 step 2 — structure callers before vs after the calling convention.

Runs the ArcFISH TAD / loop / compartment callers, FISHnet and the DI
caller on real data with one ``uchrom`` tree and pickles the outputs, so
two trees (e.g. ``origin/main`` exported with ``git archive`` and the
branch under test) can be compared::

    git archive origin/main uchrom | tar -x -C /tmp/old_main
    PYTHONPATH=/tmp/old_main python benchmarks/cd2_callers_validation.py old old.pkl
    PYTHONPATH=.             python benchmarks/cd2_callers_validation.py new new.pkl
    python benchmarks/cd2_callers_validation.py compare old.pkl new.pkl

"old" calls the 1.x per-chromosome API (``store=False``, ``call_*_multi``);
"new" calls ``chrom=None`` once per caller and also checks that every
result and its provenance survive an ``.h5cd`` round trip.

Data (see ``example-data/README.md``): Bintu 2018 IMR90 chr21
(``IMR90_chr21-18-20Mb.csv`` → ``IMR90_chr21_pyhim.ecsv`` via
``bintu_to_pyhim_ecsv.py``; needs astropy), Takei 2021 mESC FOF-CT
(``4DNFIHF3JCBY.csv``) and the in-repo ``K562_chr21_30kb.cool`` (K562 Hi-C,
Ray et al. 2019; only used to run the DI caller on a Hi-C matrix, not
paired with the IMR90 imaging).
Set ``UCHROM_EXAMPLE_DATA`` if the large files live elsewhere.  CPU only.
"""
import importlib.util
import os
import pickle
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("UCHROM_EXAMPLE_DATA", REPO / "example-data"))
DEV = "cpu"
MODE = sys.argv[1]


def compare(old_path, new_path):
    old = pickle.loads(Path(old_path).read_bytes())
    new = pickle.loads(Path(new_path).read_bytes())
    print(f"{'result':<16}{'rows old':>9}{'rows new':>9}  identical  max|diff|")
    for key in [k for k in old if isinstance(old[k], pd.DataFrame)]:
        a, b = old[key].reset_index(drop=True), new[key].reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(a, b, check_frame_type=False)
            same = True
        except AssertionError:
            same = False
        num = [c for c in a.columns if c in b.columns and pd.api.types.is_numeric_dtype(a[c])]
        diff = max([float(np.nanmax(np.abs(a[c].to_numpy(float) - b[c].to_numpy(float))))
                    for c in num if len(a) == len(b) and len(a)] or [0.0])
        print(f"{key:<16}{len(a):>9}{len(b):>9}  {str(same):>9}  {diff:.2g}")
    print("FISHnet ensemble mask identical:",
          np.array_equal(old["bintu.fishnet.mask"], new["bintu.fishnet.mask"]))
    print("DI domains identical:", old["di"] == new["di"], f"({len(old['di'])} domains)")
    for ds in ("bintu", "takei"):
        print(f"{ds}: provenance survives .h5cd:", all(new[f"{ds}.roundtrip"].values()))


if MODE == "compare":
    compare(sys.argv[2], sys.argv[3])
    sys.exit(0)

OUT = Path(sys.argv[2])
SCRATCH = Path(tempfile.mkdtemp(prefix="cd2_validation_"))
WT = REPO
MAIN_DATA = DATA

import uchrom  # noqa: E402
from uchrom import ChromData  # noqa: E402

print(MODE, uchrom.__file__)
warnings.simplefilter("ignore")


def bintu_ecsv() -> Path:
    out = DATA / "IMR90_chr21_pyhim.ecsv"
    if not out.exists():
        out = SCRATCH / "IMR90_chr21_pyhim.ecsv"
        spec = importlib.util.spec_from_file_location("b2p", WT / "example-data" / "bintu_to_pyhim_ecsv.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.CSV_PATH = DATA / "IMR90_chr21-18-20Mb.csv"
        mod.OUT_PATH = out
        mod.main()
    return out


def timed(label, fn):
    t0 = time.perf_counter()
    v = fn()
    print(f"  {label}: {time.perf_counter() - t0:.1f}s", flush=True)
    return v


res = {}
from uchrom.strc.comp import call_compartments_axes_pc
from uchrom.strc.loop import call_loops_axiswise_f
from uchrom.strc.tad import FISHnetParams, call_domains_fishnet, call_tads_by_pval, get_domains

FN_PARAMS = FISHnetParams(n_louvain_runs=5, max_thresholds=40)

# ---------------------------------------------------------------- Bintu 2018 IMR90 chr21
bintu = ChromData.from_pyhim_trace(bintu_ecsv())
print("bintu", bintu.n_spots, "spots", bintu.n_traces, "traces")
if MODE == "old":
    res["bintu.tads"] = timed("tads", lambda: call_tads_by_pval(bintu, chrom="chr21", device=DEV, store=False))
    res["bintu.loops"] = timed("loops", lambda: call_loops_axiswise_f(bintu, chrom="chr21", device=DEV, store=False))
    res["bintu.comp"] = timed("comp", lambda: call_compartments_axes_pc(bintu, chrom="chr21", device=DEV, store=False))
    res["bintu.fishnet"] = timed("fishnet", lambda: call_domains_fishnet(bintu, "chr21", params=FN_PARAMS, max_traces=40, store=True))
    res["bintu.fishnet.mask"] = bintu.results["fishnet_ensemble"]["mask"]
else:
    res["bintu.tads"] = timed("tads", lambda: call_tads_by_pval(bintu, device=DEV))
    res["bintu.loops"] = timed("loops", lambda: call_loops_axiswise_f(bintu, device=DEV))
    res["bintu.comp"] = timed("comp", lambda: call_compartments_axes_pc(bintu, device=DEV))
    res["bintu.fishnet"] = timed("fishnet", lambda: call_domains_fishnet(bintu, params=FN_PARAMS, max_traces=40))
    res["bintu.fishnet.mask"] = bintu.results["tads.fishnet.ensemble"]["chr21"]["mask"]
    # write / read the results and check they come back identical
    p = SCRATCH / "bintu_results.h5cd"
    bintu.write(p)
    back = ChromData.read(p).results
    res["bintu.roundtrip"] = {k: (back.record(k).provenance == bintu.results.record(k).provenance)
                              for k in bintu.results}
    res["bintu.roundtrip_values"] = {k: back[k] for k in bintu.results}
    res["bintu.provenance"] = {k: bintu.results.record(k).provenance for k in bintu.results}

# ---------------------------------------------------------------- Takei 2021 mESC FOF-CT
takei = ChromData.from_fofct(MAIN_DATA / "4DNFIHF3JCBY.csv")
print("takei", takei.n_spots, "spots", takei.n_traces, "traces", len(takei.chroms), "chroms")
if MODE == "old":
    from uchrom.strc import call_compartments_multi, call_loops_multi, call_tads_multi
    res["takei.tads"] = timed("tads", lambda: call_tads_multi(takei, device=DEV, store=False))
    res["takei.loops"] = timed("loops", lambda: call_loops_multi(takei, device=DEV, store=False))
    res["takei.comp"] = timed("comp", lambda: call_compartments_multi(takei, device=DEV, store=False))
    res["takei.fishnet"] = timed("fishnet", lambda: pd.concat(
        [call_domains_fishnet(takei, c, params=FN_PARAMS, max_traces=10, store=False)
         for c in ("chr1", "chr2")], ignore_index=True))
else:
    res["takei.tads"] = timed("tads", lambda: call_tads_by_pval(takei, device=DEV))
    res["takei.loops"] = timed("loops", lambda: call_loops_axiswise_f(takei, device=DEV))
    res["takei.comp"] = timed("comp", lambda: call_compartments_axes_pc(takei, device=DEV))
    res["takei.fishnet"] = timed("fishnet", lambda: call_domains_fishnet(
        takei, chrom=["chr1", "chr2"], params=FN_PARAMS, max_traces=10))
    p = SCRATCH / "takei_results.h5cd"
    takei.write(p)
    back = ChromData.read(p).results
    res["takei.roundtrip"] = {k: (back.record(k).provenance == takei.results.record(k).provenance)
                              for k in takei.results}
    res["takei.roundtrip_values"] = {k: back[k] for k in takei.results}

# ---------------------------------------------------------------- K562 Hi-C (DI TADs)
cool = WT / "example-data" / "K562_chr21_30kb.cool"
if MODE == "old":
    import cooler
    import torch
    clr = cooler.Cooler(str(cool))
    mat = np.asarray(clr.matrix(balance="weight" in clr.bins().columns).fetch("chr21"), dtype=np.float64)
    mat[~np.isfinite(mat)] = 0
    res["di"] = timed("di", lambda: [(int(s), int(e)) for s, e in get_domains(torch.as_tensor(mat), device=DEV)])
else:
    from uchrom.strc.tad import call_tads_di
    bintu.link_cool(cool, key="k562")  # K562 matrix; DI does not use the imaging
    t = timed("di", lambda: call_tads_di(bintu, contacts="k562", chrom="chr21", device=DEV))
    res["di"] = [(int(s), int(e)) for s, e in zip(t["start_bin"], t["end_bin"])]
    res["di.table"] = t

OUT.write_bytes(pickle.dumps(res))
print("wrote", OUT)
