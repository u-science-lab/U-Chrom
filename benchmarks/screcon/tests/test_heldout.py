"""Held-out scorer on a synthetic toy: contacts sampled from a known polymer.

A model equal to the truth must score high; a random polymer must score ~0.5; the
separation-matched design must give a P(s)-only predictor exactly 0.5 in cis.
(Synthetic data here only check the scorer; the real-data runs are on Sherlock.)
"""

import numpy as np

from baselines import random_polymer
from contacts import Grid, read_contacts, write_geo
from heldout import build_eval_pairs, fold_indices, main as heldout_main, score_models
from simulate import simulate_reads
from conftest import toy_polymer


def _toy_contacts(tmp_path, seed=0):
    t = toy_polymer(n_bins=400, seed=seed)
    ca, pa, cb, pb, _ = simulate_reads(t, reads=15000, rc_rel=1.5, eps=0.0, seed=seed)
    f = tmp_path / "toy.txt.gz"
    write_geo(f, ca, pa, cb, pb)
    return t, f


def test_fold_indices_disjoint():
    f = fold_indices(1000, 0.1, 3, seed=1)
    assert [len(x) for x in f] == [100, 100, 100]
    assert len(np.unique(np.concatenate(f))) == 300
    assert [len(x) for x in fold_indices(10, None, 3, 1)] == [4, 3, 3]
    assert np.array_equal(fold_indices(1000, 0.1, 3, seed=1)[2], f[2])


def test_perfect_vs_random(tmp_path):
    t, f = _toy_contacts(tmp_path)
    c = read_contacts(f)
    held = fold_indices(len(c), 0.1, 1, seed=3)[0]
    ev = build_eval_pairs(c, held, 100_000, n_neg=10, seed=1)
    assert ev["stats"]["n_pos"] > 100 and ev["stats"]["n_pos_with_band_fallback"] == 0
    g = ev["grid"]
    # exact separation matching: every cis negative has its positive's separation
    cis_pos = g.chrom[ev["pos_a"]] == g.chrom[ev["pos_b"]]
    sep_pos = ev["pos_b"] - ev["pos_a"]
    cis_neg = g.chrom[ev["neg_a"]] == g.chrom[ev["neg_b"]]
    grp = ev["neg_group"]
    assert np.array_equal(cis_neg, cis_pos[grp])
    assert np.array_equal((ev["neg_b"] - ev["neg_a"])[cis_neg], sep_pos[grp][cis_neg])
    X = t["coords"][None]
    good = score_models(ev, t["chrom"], t["end"], X, n_boot=50)
    assert good["median"]["cis"]["roc_auc"] > 0.8 and good["median"]["trans"]["roc_auc"] > 0.8
    assert good["frac"]["all"]["roc_auc"] > 0.7
    assert good["ps_baseline_cis_auc"] == 0.5
    lo, hi = good["median"]["cis"]["roc_auc_ci95"]
    assert lo < good["median"]["cis"]["roc_auc"] < hi
    grid = Grid.from_contacts(c, 100_000)
    R = random_polymer(grid, n_models=10, seed=5)
    bad = score_models(ev, grid.chrom, (grid.bin + 1) * grid.res, R, n_boot=0)
    assert abs(bad["median"]["cis"]["roc_auc"] - 0.5) < 0.07
    assert abs(bad["median"]["all"]["roc_auc"] - 0.5) < 0.1


def test_split_cli(tmp_path):
    _, f = _toy_contacts(tmp_path, seed=1)
    heldout_main(["split", "--contacts", str(f), "--out", str(tmp_path / "s"), "--folds", "2", "--frac", "0.1",
                  "--eval-res", "100000"])
    tr = read_contacts(tmp_path / "s/fold1/train.txt.gz")
    ho = read_contacts(tmp_path / "s/fold1/heldout.txt.gz")
    full = read_contacts(f)
    assert len(tr) + len(ho) == len(full) and len(ho) == round(0.1 * len(full))
    assert set(tr.lines) | set(ho.lines) == set(full.lines)
    assert (tmp_path / "s/fold2/eval_pairs.npz").exists()
