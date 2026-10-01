"""Matched-modality comparison: I/O helpers and the scorers on synthetic toys (no real data)."""

import gzip

import numpy as np
import pandas as pd
import pytest

from matched import Axis, apply_masks, cell_units, compare, detection_masks, features, nuclei, ps_only, \
    random_polymer, run, summarise
from matched_data import Chain, dipc_to_loci, imaging_set_from_spots, load_set, models_to_loci, read_dipc_3dg, \
    read_loci, save_set, subset_set


def toy_axis(n_chrom=3, n_loci=40):
    chrom = np.repeat([f"chr{c + 1}" for c in range(n_chrom)], n_loci)
    start = np.tile(np.arange(n_loci) * 1_000_000 + 3_000_000, n_chrom)
    return chrom, start, start + 25_000


def toy_set(n=30, seed=0, H=1, scale=1.0):
    chrom, start, end = toy_axis()
    ax = Axis(chrom, start, end, n_pairs=2000)
    rng = np.random.default_rng(seed)
    X = np.concatenate([ps_only(n, ax, rng, 0.3, radius=4.0) for _ in range(H)], axis=1) * scale
    return {"X": X.astype(np.float32), "chrom": chrom, "start": start, "end": end,
            "cells": [{"cell_id": str(k), "grp": "a" if k % 2 else "b"} for k in range(n)], "meta": {}}, ax


def test_locus_axis_file():
    loci = read_loci()
    assert len(loci) == 2460 and loci.name.is_unique
    assert set(loci.chrom) == {f"chr{i}" for i in range(1, 20)} | {"chrX"}
    assert ((loci.end - loci.start) == 25_000).all()
    assert loci.groupby("chrom").start.apply(lambda s: s.is_monotonic_increasing).all()


def test_chain_liftover(tmp_path):
    p = tmp_path / "t.chain.gz"
    with gzip.open(p, "wt") as fh:
        # chain score tName tSize tStrand tStart tEnd qName qSize qStrand qStart qEnd id
        fh.write("chain 1 chr1 1000 + 100 400 chr1 2000 + 500 820 1\n100 50 70\n150\n\n")
        fh.write("chain 1 chr2 1000 + 0 100 chr3 1000 - 0 100 2\n100\n\n")
    c = Chain(p)
    oc, op = c.map(["chr1", "chr1", "chr1", "chr1", "chr2", "chrZ"], [100, 199, 220, 260, 10, 5])
    assert list(op) == [500, 599, -1, 500 + 100 + 70 + 10, 1000 - 1 - 10, -1]
    assert list(oc[:2]) == ["chr1", "chr1"] and oc[4] == "chr3"


def test_models_to_loci():
    loci = pd.DataFrame({"chrom": ["chr1", "chr1", "chr2"], "start": [150_000, 990_000, 50_000],
                         "end": [175_000, 1_015_000, 75_000]})
    chrom = np.array(["chr1"] * 10 + ["chr2"] * 2)
    pos = np.r_[np.arange(1, 11) * 100_000, np.arange(1, 3) * 100_000]       # 2017: particle k = (pos - 100k, pos]
    X = np.arange(2 * 12 * 3, dtype=float).reshape(2, 12, 3)
    Y = models_to_loci(chrom, pos, X, loci)
    assert np.allclose(Y[:, 0], X[:, 1])            # midpoint 162,500 -> (100k, 200k]
    assert np.isnan(Y[:, 1]).all()                  # 1,002,500 beyond the last chr1 particle
    assert np.allclose(Y[:, 2], X[:, 10])


def test_dipc_3dg(tmp_path):
    p = tmp_path / "c.3dg.gz"
    with gzip.open(p, "wt") as fh:
        fh.write("1(mat)\t140000\t1\t2\t3\n1(pat)\t160000\t4\t5\t6\nX(mat)\t0\t7\t8\t9\n")
    df = read_dipc_3dg(p)
    assert list(df.chrom) == ["chr1", "chr1", "chrX"] and list(df.hap) == ["mat", "pat", "mat"]
    loci = pd.DataFrame({"chrom": ["chr1", "chrX"], "start": [150_000, 0], "end": [175_000, 25_000]})
    Y = dipc_to_loci(df, loci)
    assert np.allclose(Y[1, 0], [4, 5, 6]) and np.isnan(Y[0, 0]).all()   # mid 162,500 -> 160,000 bin
    assert np.allclose(Y[0, 1], [7, 8, 9])


def test_imaging_split_two_homologs():
    rng = np.random.default_rng(0)
    loci = pd.DataFrame({"name": [f"l{i}" for i in range(30)], "chrom": "chr1",
                         "start": np.arange(30) * 1_000_000, "end": np.arange(30) * 1_000_000 + 25_000})
    rows = []
    for h, off in enumerate((0.0, 5000.0)):
        walk = np.cumsum(rng.normal(size=(30, 3)) * 150, 0) + off
        for i in range(30):
            if rng.random() < 0.9:
                rows.append({"cell": "c1", "name": f"l{i}", "x": walk[i, 0], "y": walk[i, 1], "z": walk[i, 2], "h": h})
    df = pd.DataFrame(rows)
    X, cells, st = imaging_set_from_spots(df, loci, {"c1": {"t": 1}}, min_detect=0.5)
    assert X.shape == (1, 2, 30, 3) and cells[0]["t"] == 1 and st["n_chrom_copies_2"] == 1
    # each slot holds exactly one homolog's spots
    for slot in (0, 1):
        pts = X[0, slot][np.isfinite(X[0, slot, :, 0])]
        assert (pts[:, 0] > 2500).all() or (pts[:, 0] < 2500).all()


def test_set_roundtrip_and_subset(tmp_path):
    s, _ = toy_set(6)
    save_set(tmp_path / "s.npz", s["X"], s["chrom"], s["start"], s["end"], s["cells"], {"x": 1})
    t = load_set(tmp_path / "s.npz")
    assert np.allclose(t["X"], s["X"]) and t["meta"] == {"x": 1}
    assert len(subset_set(t, {"grp": "a"})["cells"]) == 3


def test_scale_invariance_and_identity():
    s, ax = toy_set(40)
    rng = np.random.default_rng(1)
    f1 = features(s["X"], ax, rng)
    f2 = features(s["X"] * 37.0, ax, np.random.default_rng(1))
    m = compare(f1, f2, ax)
    assert m[("pair", "median_spearman")] == pytest.approx(1.0)
    assert m[("pair", "w1_median")] == pytest.approx(0.0, abs=1e-5)
    assert m[("scaling", "alpha_diff")] == pytest.approx(0.0, abs=1e-6)
    assert m[("radial", "locus_spearman")] == pytest.approx(1.0)
    assert np.allclose(cell_units(s["X"], ax) * 37.0, cell_units(s["X"] * 37.0, ax), rtol=1e-4)
    # the P(s)-only generator recovers its exponent roughly
    assert 0.2 < f1["alpha"] < 0.4


def test_pseudo_haploid_nucleus_and_masks():
    s, ax = toy_set(5, H=2)
    X = s["X"].copy()
    X[0, 0, ax.cidx == 0] = np.nan               # cell 0: copy 0 of chr1 missing -> copy 1 must be used
    N, li, cp = nuclei(X, ax, np.random.default_rng(0))
    assert N.shape == (5, ax.L, 3)
    assert np.allclose(N[0, ax.cidx == 0], X[0, 1, ax.cidx == 0])
    m = detection_masks(X, ax, np.random.default_rng(0), 1)
    assert m.shape == (5, 1, ax.L)
    Z = apply_masks(np.zeros((3, 1, ax.L, 3), np.float32), m, np.random.default_rng(0))
    assert np.isnan(Z).any() or m.all()


def test_run_ceiling_and_baselines():
    B, _ = toy_set(40, seed=3)
    A, _ = toy_set(10, seed=4)
    df = run(A, B, label="toy", n_rep=1, n_pairs=1500)
    assert set(df.kind) == {"model", "ceiling", "random_polymer", "ps_only"}
    s = summarise(df)
    row = s[(s.feature == "scaling") & (s.metric == "alpha_diff")].iloc[0]
    assert abs(row["ps_only"]) < 0.05 and row["random_polymer"] > 0.1      # RW exponent 0.5 vs 0.3
    assert len(random_polymer(2, Axis(*toy_axis(), n_pairs=10), np.random.default_rng(0))) == 2
