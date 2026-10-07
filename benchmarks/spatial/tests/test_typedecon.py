"""Code checks on synthetic toys (correctness of the pieces, not evidence for the method on data)."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

import run_typedecon as rt
import scoring as sc
import tissue as ts
import typedecon as td
from conftest import toy_layout, toy_pool


# --------------------------------------------------------------------------- layout / io

def test_layout_pair_index_is_a_bijection():
    lay = toy_layout(5_000_000)
    a = lay.bin_off[lay.pair_chrom] + lay.pair_i
    b = lay.bin_off[lay.pair_chrom] + lay.pair_j
    np.testing.assert_array_equal(lay.pair_index(a, b), np.arange(lay.n_pairs))
    np.testing.assert_array_equal(lay.pair_index(b, a), np.arange(lay.n_pairs))   # order free


def test_layout_from_base():
    base, coarse = toy_layout(1_000_000), toy_layout(5_000_000)
    bins = np.array([0, 4, 5, base.bin_off[1], base.bin_off[1] + 7])
    np.testing.assert_array_equal(coarse.from_base(bins, base), [0, 0, 1, coarse.bin_off[1], coarse.bin_off[1] + 1])


def test_real_layout_counts():
    lay = ts.Layout(1_000_000)
    assert lay.chroms[0] == "chr1" and lay.chroms[-1] == "chr19" and len(lay.chroms) == 19
    assert lay.n[0] == 196 and lay.n_pairs == int((lay.n * (lay.n + 1) // 2).sum())


def _write(path, lines):
    with gzip.open(path, "wt") as fh:
        fh.write("\n".join(lines) + "\n")


def test_read_cell_cis_geo_and_pairs(tmp_path):
    geo = tmp_path / "a.txt.gz"
    _write(geo, ["chr1\t1000\tchr1\t5000", "chr1\t1000\tchr1\t1500", "chr1\t10\tchr2\t20", "chrX\t1\tchrX\t9000",
                 "chr2\t3000000\tchr2\t100"])
    c, pa, pb = ts.read_cell_cis(geo)
    assert c.tolist() == [0, 1] and pa.tolist() == [1000, 3000000] and pb.tolist() == [5000, 100]
    pairs = tmp_path / "b.pairs.gz"
    _write(pairs, ["## pairs format v1.0", "#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1",
                   ".\tchr1(mat)\t1000\tchr1(pat)\t5000\t+\t-\t0\t1", ".\tchr3\t5\tchr3\t500\t+\t-\t.\t."])
    c, pa, pb = ts.read_cell_cis(pairs)
    assert c.tolist() == [0] and pa.tolist() == [1000] and pb.tolist() == [5000]
    b = ts.cell_bins(pairs)
    assert b.tolist() == [[0, 0]]


def test_split_registered_counts():
    d = ts.split_cells()
    n = d.groupby(["type", "role"]).size().unstack()
    assert n.loc["P"].tolist() == [40, 40, 80]          # dev, test, truth (columns sorted)
    assert n.loc["A"].tolist() == [7, 8, 15]
    assert n.loc["M"].tolist() == [9, 10, 18]
    assert set(d.role) == {"truth", "dev", "test"}
    assert d.name.is_unique
    # deterministic
    assert d.equals(ts.split_cells())


# --------------------------------------------------------------------------- tissue

def test_tissue_disjoint_contacts_and_composition(toy, toy_layers):
    lay, probs, pool, types = toy
    t = ts.build_tissue(pool, "high", seed=1, types=types, n_spots=20)
    depth = np.bincount(t.spot, minlength=20)
    assert depth.min() >= 30_000 * 0.99 and depth.max() <= 150_000 * 1.01
    comp = t.true_composition(len(types))
    np.testing.assert_allclose(comp.sum(1), 1)
    for s, lst in enumerate(t.spot_cells):
        assert 2 <= len(lst) <= 5
        assert sum(n for _c, n, _f in lst) == depth[s]
    # rows of one cell are distinct within the tissue unless reuse was needed
    if t.meta["reused_contacts"] == 0:
        for ci in range(len(t.cells)):
            sel = t.cell == ci
            assert len(np.unique(t.bins[sel], axis=0)) <= sel.sum()


def test_tissue_roundtrip(tmp_path, toy, toy_layers):
    lay, probs, pool, types = toy
    t = ts.build_tissue(pool, "low", seed=2, types=types, n_spots=30)
    ts.save_tissue(tmp_path / "t.npz", t)
    u = ts.load_tissue(tmp_path / "t.npz")
    np.testing.assert_array_equal(t.bins, u.bins)
    assert t.spot_cells == u.spot_cells and t.meta == u.meta


def test_observed_composition_levels():
    true = np.random.default_rng(0).dirichlet(np.ones(6), size=200)
    w0, c0 = ts.observed_composition(true, "exact", 1)
    np.testing.assert_allclose(w0, true)
    _, c1 = ts.observed_composition(true, "moderate", 1)
    _, c2 = ts.observed_composition(true, "heavy", 1)
    assert 0 < c1["mae"] < c2["mae"] and c1["r"] > c2["r"]


# --------------------------------------------------------------------------- method

def _toy_fit_inputs(regime="low", n_spots=150, seed=3):
    lay, probs, pool, types = toy_pool()
    import conftest
    old = ts.LAYERS
    ts.LAYERS = conftest.TOY_LAYERS
    try:
        t = ts.build_tissue(pool, regime, seed=seed, types=types, n_spots=n_spots)
    finally:
        ts.LAYERS = old
    Y = ts.spot_matrix(t.spot, t.bins, t.n_spots, lay, base=lay)
    tc = np.zeros((3, lay.n_pairs))
    np.add.at(tc, (t.contact_type(), lay.pair_index(t.bins[:, 0], t.bins[:, 1])), 1)
    return lay, probs, t, Y, tc


def test_td_loglik_monotone_and_close_to_oracle():
    lay, probs, t, Y, tc = _toy_fit_inputs()
    A = t.true_composition(3)
    fit = td.fit_td(Y, A, params=td.TDParams(n_iter=80, tol=0))
    ll = fit["loglik"]
    assert np.all(np.diff(ll) >= -1e-6 * np.abs(ll[:-1]))
    np.testing.assert_allclose(fit["P"].sum(1), 1)
    truth = sc.truth_features(probs, lay)
    s_td = sc.score_profiles(fit["P"], truth, lay)
    s_or = sc.score_profiles(td.oracle_pool(tc)["P"], truth, lay)
    s_rand = sc.score_profiles(td.fit_td(Y, ts.permuted_composition(A, 0))["P"], truth, lay)
    assert s_td["contrast_r"] > s_or["contrast_r"] - 0.05
    assert s_td["ident_accuracy"] == 1.0
    assert s_rand["contrast_r"] < s_td["contrast_r"] - 0.3


def test_td_learns_yield():
    lay, probs, t, Y, tc = _toy_fit_inputs("high", n_spots=60)
    true = t.true_composition(3)
    bias = np.array([2.0, 1.0, 0.5])
    A = true / bias          # given composition under-states type 0 by 2x, over-states type 2 by 2x
    A = A / A.sum(1, keepdims=True)
    fit = td.fit_td(Y, A, params=td.TDParams(learn_yield=True, n_iter=300))
    c = fit["yield"] / fit["yield"][1]
    assert c[0] > 1.4 and c[2] < 0.7


def test_td_shrinkage_and_ps_prior_run():
    lay, probs, t, Y, tc = _toy_fit_inputs()
    A = t.true_composition(3)
    for pm in ("pooled", "pooled_ps"):
        fit = td.fit_td(Y, A, params=td.TDParams(shrink=0.5, prior_mean=pm, n_iter=30), pair_sep=lay.pair_sep)
        assert np.all(np.isfinite(fit["P"])) and np.allclose(fit["P"].sum(1), 1)
    fit = td.fit_td(Y, A, params=td.TDParams(refine=20.0, n_iter=30))
    np.testing.assert_allclose(fit["a"].sum(1), 1)


def test_groups_and_baselines():
    lay, probs, t, Y, tc = _toy_fit_inputs()
    A = t.true_composition(3)
    g = (t.xy[:, 0] > 0.5).astype(int)
    out = td.fit_td_groups(Y, A, g, params=td.TDParams(n_iter=30))
    assert set(out["groups"]) == {0, 1}
    dom = td.dominant_pool(Y, A)
    assert dom["n_spots"].sum() == Y.shape[0]
    nn = td.nnls_profiles(Y, A)
    assert np.all(nn["P"][np.isfinite(nn["P"])] >= 0)


# --------------------------------------------------------------------------- scoring

def test_scores_identity_and_permutation():
    lay, probs = toy_layout(), toy_pool()[1]
    truth = sc.truth_features(probs, lay)
    s = sc.score_profiles(probs, truth, lay)
    assert s["contrast_r"] == pytest.approx(1.0) and s["comp_r"] == pytest.approx(1.0)
    assert s["ident_accuracy"] == 1.0
    sp_ = sc.score_profiles(probs[[1, 2, 0]], truth, lay)
    assert sp_["ident_accuracy"] == 0.0 and sp_["contrast_r"] < 0.5
    missing = probs.copy()
    missing[1] = np.nan
    sm = sc.score_profiles(missing, truth, lay)
    assert np.isnan(sm["contrast_r_type"][1]) and sm["contrast_r"] < 0.9


def test_bootstrap_ci():
    mu, lo, hi = sc.bootstrap_ci([1.0, 2.0, 3.0, 4.0])
    assert mu == 2.5 and lo < mu < hi


# --------------------------------------------------------------------------- end to end on the real layout

def test_pipeline_end_to_end(tmp_path, monkeypatch):
    """split -> cells -> truth -> tissue -> fit -> aggregate on fake cells (mm10 layout, 1 Mb)."""
    rng = np.random.default_rng(0)
    split = ts.split_cells()
    split = split.groupby(["type", "role"]).head(2)     # 2 cells per type and role
    (tmp_path / "split.tsv").write_text(split.to_csv(sep="\t", index=False))
    lay = ts.Layout(1_000_000)
    for _, r in split.iterrows():
        k = ts.TYPE_CODES.index(r["type"])
        c = rng.integers(0, 19, 6000)
        pa = rng.integers(1, 40_000_000, 6000)
        sep = (10 ** rng.uniform(3.5, 7.5, 6000)).astype(int) * (1 + (k % 2))
        pb = pa + sep
        d = tmp_path / "data" / "tan2021_cortex" / "cells" / r["name"]
        d.mkdir(parents=True)
        _write(d / f"{r['name']}.contacts.pairs.txt.gz",
               [f".\t{lay.chroms[ci]}\t{x}\t{lay.chroms[ci]}\t{y}\t+\t+" for ci, x, y in zip(c, pa, pb)])
    run = tmp_path / "run"
    rt.main(["cells", "--split", str(tmp_path / "split.tsv"), "--data", str(tmp_path / "data"),
             "--out", str(run / "cells"), "--workers", "1"])
    rt.main(["truth", "--split", str(tmp_path / "split.tsv"), "--cells", str(run / "cells"), "--out",
             str(run / "truth"), "--res", "1e6"])
    monkeypatch.setitem(ts.REGIMES, "low", {**ts.REGIMES["low"], "n_spots": 40, "depth": (500, 2000)})
    rt.main(["tissue", "--split", str(tmp_path / "split.tsv"), "--cells", str(run / "cells"), "--set", "dev",
             "--regime", "low", "--rep", "0", "--out", str(run / "tissues")])
    with pytest.raises(SystemExit):
        rt.main(["tissue", "--split", str(tmp_path / "split.tsv"), "--cells", str(run / "cells"), "--set",
                 "test", "--regime", "low", "--rep", "0", "--out", str(run / "tissues")])
    var = tmp_path / "variants.json"
    var.write_text(json.dumps({"TD": {"n_iter": 20}, "TD-shrink": {"n_iter": 20, "shrink": 0.1}}))
    rt.main(["fit", "--tissue", str(run / "tissues" / "dev_low_r0.npz"), "--truth", str(run / "truth"),
             "--res", "1e6", "--noise", "moderate", "--variants", str(var), "--spatial", "--out", str(run / "scores")])
    rt.main(["aggregate", "--scores", str(run / "scores"), "--out", str(run / "tables")])
    df = pd.read_csv(run / "tables" / "scores.csv")
    assert {"TD", "TD-shrink", "dominant", "nnls", "random", "oracle"} <= set(df.method)
    assert any(m.startswith("S1:") for m in df.method)
    assert (run / "tables" / "summary.md").exists()
