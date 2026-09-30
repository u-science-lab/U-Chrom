"""Scoring code of the consensus benchmark on toys (seconds; no data, no engine)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _bc  # noqa: E402,F401  (path order)
from _bc import Model, map_loci_to_bins  # noqa: E402
from imaging import embed, pair_medians  # noqa: E402
from score import distance_metrics, rmsd_metrics  # noqa: E402


def test_map_loci_to_bins():
    bins = pd.DataFrame({"chrom": ["chr1"] * 3 + ["chr2"] * 2, "start": [0, 100, 200, 0, 100],
                         "end": [100, 200, 300, 100, 200]})
    loci = pd.DataFrame({"chrom": ["chr1", "chr2", "chr1", "chr3"], "start": [150, 20, 290, 0], "end": [170, 60, 330, 10]})
    assert map_loci_to_bins(loci, bins).tolist() == [1, 3, -1, -1]


def test_pair_medians_pooling():
    # 2 structures, 2 copies, 3 loci on 2 chromosomes
    X = np.zeros((2, 2, 3, 3), np.float32)
    X[..., 1, 0] = [[1, 5], [3, 7]]          # locus 1 (chr1): x per (structure, copy)
    X[..., 2, 0] = [[10, 20], [30, 40]]      # locus 2 (chr2)
    med, mean, cnt = pair_medians(X, np.array(["chr1", "chr1", "chr2"]))
    assert cnt[0, 1] == 4 and np.isclose(med[0, 1], 4.0)          # cis: same copy, 2 x 2 samples
    assert cnt[0, 2] == 8 and np.isclose(med[0, 2], np.median([10, 20, 10, 20, 30, 40, 30, 40]))  # trans: all combos


def test_distance_metrics_and_rmsd():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 3)) * 5
    chrom = np.array(["chr1"] * 20 + ["chr2"] * 20)
    mid = np.r_[np.arange(20), np.arange(20)] * 2e6
    D = np.linalg.norm(X[:, None] - X[None], axis=2)
    cnt = np.full(D.shape, 100)
    m = distance_metrics(2 * D, D, cnt, chrom, mid, 20)
    assert m["all"]["spearman"] > 0.999 and m["trans"]["n"] == 400 and m["cis"]["n"] == 380
    emb, ok, info = embed(D)
    assert info["distance_r_embedding_vs_input"] > 0.999
    r = rmsd_metrics(3 * X + 1, emb, chrom)
    assert r["rmsd_over_rg"] < 1e-3
    bins = pd.DataFrame({"chrom": chrom, "start": mid.astype(int), "end": mid.astype(int) + 100})
    Dm, Xm = Model("m", bins, X).loci_distances(bins)
    assert np.allclose(np.nan_to_num(Dm), D)
