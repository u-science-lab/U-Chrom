"""Scripts of the load-data, call-structures and associate-modalities skills (and the compare-groups
extensions) on synthetic data with known answers."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData

SKILLS = Path(__file__).resolve().parents[2] / "skills"


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, SKILLS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


insp = _load("load-data/scripts/inspect_data.py", "inspect_data")
strc = _load("call-structures/scripts/structures.py", "structures")
assoc = _load("associate-modalities/scripts/associate.py", "associate")
cg = _load("compare-groups/scripts/compare_groups.py", "compare_groups_ext")


def _chain(n, step=1.0, rng=None):
    """A random walk with bond length `step` (one particle per locus)."""
    rng = rng or np.random.default_rng(0)
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return np.cumsum(v * step, axis=0)


def _tracing(n_cells=6, loci=40, bin_bp=25_000, extra_trace_cell=None, dup=False, rng=np.random.default_rng(1)):
    rows, xyz, cells = [], [], []
    for c in range(n_cells):
        cid = f"c{c}"
        ct = "A" if c % 2 == 0 else "B"
        cells.append((cid, ct, 100.0 + 10 * c, float(c)))
        n_tr = 3 if cid == extra_trace_cell else 2
        for t in range(n_tr):
            p = _chain(loci, 1.0 if ct == "A" else 0.5, rng)
            for k in range(loci):
                rows.append(("chr1", k * bin_bp, (k + 1) * bin_bp, f"{cid}_t{t}", cid))
                xyz.append(p[k])
            if dup and t == 0:
                rows.append(("chr1", 0, bin_bp, f"{cid}_t{t}", cid))
                xyz.append(p[0] + 0.01)
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cdf = pd.DataFrame(cells, columns=["cell_id", "cell_type", "nuc_volume_um3", "if.X"]).set_index("cell_id")
    tracks = pd.DataFrame({"sig": np.arange(len(spots)) % loci, "rad": (np.arange(len(spots)) % loci)[::1] * -1.0})
    return ChromData(np.array(xyz), spots, cells=cdf, tracks=tracks, uns={"xyz_unit": "um", "genome_assembly": "mm10"})


# ------------------------------------------------------------------ load-data
def test_inspect_counts_and_qc():
    cd = _tracing(extra_trace_cell="c0", dup=True)
    s = insp.summarize(cd)
    assert s["counts"]["n_cells_table"] == 6 and s["counts"]["n_traces"] == 13
    assert s["cells"]["by_prefix"]["if."]["n"] == 1
    tp = s["qc"]["traces_per_cell_chrom"]
    assert tp["distribution"] == {2: 5, 3: 1} and tp["n_cell_chrom_without_traces"] == 0
    assert s["qc"]["duplicate_loci"]["n_trace_locus_with_gt1_spot"] == 6
    assert abs(s["qc"]["consecutive_loci"]["median_distance"] - 0.75) < 0.3
    joined = " ".join(s["checks"])
    assert ">2 traces" in joined and ">1 spot" in joined


def test_inspect_contacts_only_dataset():
    spots = pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cells = pd.DataFrame({"cell_type": ["a", "b"], "rna.G": [1.0, 2.0]}, index=["x", "y"])
    cd = ChromData(np.zeros((0, 3)), spots, cells=cells, uns={"coordinate_status": "contacts only"})
    s = insp.summarize(cd)
    assert s["counts"]["n_spots"] == 0 and s["qc"] == {}
    assert any("no 3-D coordinates" in c for c in s["checks"])


# ------------------------------------------------------------------ call-structures
def test_distance_at_separation_on_straight_line():
    # straight chain: locus k at x = k (µm), 25 kb loci -> 1 Mb apart = 40 loci = 40 µm
    spots = pd.DataFrame({"chrom": "chr1", "start": np.arange(100) * 25_000, "end": np.arange(1, 101) * 25_000,
                          "trace_id": "t0", "cell_id": "c0"})
    xyz = np.column_stack([np.arange(100.0), np.zeros(100), np.zeros(100)])
    cd = ChromData(xyz, spots, uns={"xyz_unit": "um"})
    r = strc.distance_at_separation(cd, "chr1", 1e6, tol=0.0)
    assert r["median_over_pairs"] == pytest.approx(40.0) and r["n_pairs"] == 60
    sc = strc.scaling(cd, "chr1")
    assert sc["exponent_alpha"] == pytest.approx(1.0, abs=0.05)


def test_rg_binning_and_coverage():
    cd = _tracing()
    rg = strc.rg_by_chrom(cd)
    assert rg["per_chrom"]["chr1"]["n_traces"] == 12
    b = strc.bin_traces(cd, "chr1", 100_000)                  # 4 loci per bin
    assert b.n_spots == 12 * 10 and set(b.spots["end"] - b.spots["start"]) == {100_000}
    cov = strc.coverage(cd, "chr1")
    assert cov.iloc[0]["bin_size"] == 25_000 and cov.iloc[0]["median_detected_frac"] == pytest.approx(1.0)
    assert strc.choose_bin_size(cd, "chr1") == 25_000


def test_contact_ps_power_law(tmp_path):
    import cooler
    bs, n = 100_000, 60
    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(n) * bs, "end": np.arange(1, n + 1) * bs})
    i, j = np.triu_indices(n, 1)
    counts = np.round(1e6 * ((j - i) * bs / 1e5) ** -1.0).astype(int)   # P(s) ~ s^-1
    pix = pd.DataFrame({"bin1_id": i, "bin2_id": j, "count": counts})
    uri = str(tmp_path / "m.cool")
    cooler.create_cooler(uri, bins, pix)
    clr = cooler.Cooler(uri)
    r = strc.contact_ps(clr, "chr1", 2e5, 2e6)
    assert r["slope"] == pytest.approx(-1.0, abs=0.01) and r["n_diagonals"] == 19
    r2 = strc.contact_ps([clr, clr], "chr1", 2e5, 2e6)           # pseudo-bulk: same shape, same slope
    assert r2["slope"] == pytest.approx(r["slope"]) and r2["total_cis_contacts"] == 2 * r["total_cis_contacts"]


# ------------------------------------------------------------------ associate-modalities
def test_cell_level_partial_and_within_group():
    rng = np.random.default_rng(3)
    n = 60
    size = rng.normal(size=n)
    ct = np.where(np.arange(n) < 30, "A", "B")
    cells = pd.DataFrame({"cell_type": ct, "nuc_volume_um3": size,
                          "if.M": size + 0.1 * rng.normal(size=n), "y": size + 0.1 * rng.normal(size=n)},
                         index=[f"c{k}" for k in range(n)])
    spots = pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cd = ChromData(np.zeros((0, 3)), spots, cells=cells)
    r = assoc.cell_level(cd, "if.M", "y", covariates=["nuc_volume_um3"])
    assert r["rho"] > 0.9 and abs(r["partial"]["rho"]) < 0.4
    assert any("nuc_volume_um3 correlates with both" in c for c in r["checks"])
    # association driven by cell type only
    cells2 = pd.DataFrame({"cell_type": ct, "a": (ct == "A") + 0.01 * rng.normal(size=n),
                           "b": (ct == "A") + 0.01 * rng.normal(size=n)}, index=cells.index)
    r2 = assoc.cell_level(ChromData(np.zeros((0, 3)), spots, cells=cells2), "a", "b", covariates=[])
    assert r2["rho"] > 0.7 and any("driven by differences between cell_types" in c for c in r2["checks"])


def test_bin_level_and_rg_per_cell():
    cd = _tracing()
    r = assoc.bin_level(cd, "sig", "rad", "chr1", bin_size=100_000, min_spots=1)
    assert r["n_bins"] == 10 and r["rho"] == pytest.approx(-1.0)
    rg = assoc.per_cell(cd, "rg")
    assert len(rg) == 6 and rg["c0"] > rg["c1"]            # type A (step 1.0) larger than B (step 0.5)


def test_knn_purity():
    n = 40
    lab = np.repeat(["a", "b"], n // 2)
    X = np.where(lab[:, None] == "a", 0.0, 100.0) + np.random.default_rng(0).normal(size=(n, 2))
    cells = pd.DataFrame({"cell_type": lab}, index=[f"c{k}" for k in range(n)])
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"]),
                   cells=cells, cellm={"emb": X})
    r = assoc.knn_purity(cd, "emb", k=5)
    assert r["purity"] == 1.0 and r["chance_purity"] == pytest.approx(0.5)


# ------------------------------------------------------------------ compare-groups extensions
def test_rest_nspots_equalize_and_scan():
    cd = _tracing(n_cells=10)
    assert sorted(cg.resolve_group(cd, "rest", other="field:cell_type=A")) == sorted(
        cg.resolve_group(cd, "field:cell_type=B"))
    assert sorted(cg.resolve_group(cd, "field:cell_type!=A")) == sorted(cg.resolve_group(cd, "field:cell_type=B"))
    r = cg.compare(cd, "field:cell_type=A", "rest", stat="n_spots", confounder=None)
    assert r["a"]["median"] == 40 and r["b"]["median"] == 40
    e = cg.compare(cd, "field:cell_type=A", "rest", stat="rg", confounder=None, equalize=20)
    assert e["equalized_loci_per_trace"] == 20 and e["a"]["median"] > e["b"]["median"]
    s = cg.scan(cd, "field:cell_type=A", "rest", columns=["nuc_volume_um3", "if.X"])
    assert s["n_fields_tested"] == 2 and all("q" in t for t in s["top"])
    assert s["composition"]["cell_type"]["enrichment"]["value"] == "A"
