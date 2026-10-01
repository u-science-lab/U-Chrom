"""Bulk deconvolution benchmark: population I/O, forward model, metrics, baselines, twins.

Synthetic toys only check correctness of the code (a population scored against itself is
perfect, copy relabelling does not matter, pooled definitions match brute force, ...).
"""

import json

import numpy as np
import pandas as pd
import pytest
from bulk_toys import toy_population

from _common import load_preprocess
from bulk_baselines import consensus, contact_gaussian, dimes_oracle, hipps, maxwell_cdf, maxwell_sigma, random_polymer, truth_halves
from forward import contact_sums, igm_radii, model_bins, probability_matrix, simulate_counts
from bulk_metrics import (all_pairs, diploid_rmsd, pair_samples, sample_triplets, score_population, triplet_frequencies)
from population import Population, from_arrays, map_to_loci, remap
from twins import chrom_shuffle, pair_match


def test_population_roundtrip_and_remap(tmp_path, toy):
    toy.save(tmp_path / "p.npz")
    back = Population.load(tmp_path / "p.npz")
    assert np.allclose(back.coords, toy.coords, equal_nan=True) and back.meta["dataset"] == "toy"
    bins = pd.DataFrame({"chrom": toy.chrom, "start": toy.start - 1_000_000, "end": toy.start + 2_000_000})
    idx = map_to_loci(bins.chrom, bins.start, bins.end, toy.chrom, toy.start, toy.end)
    assert (idx == np.arange(toy.n_loci)).all()
    # engine-style arrays: beads = (copy, bin)
    S, P, L, _ = toy.coords.shape
    coords = toy.coords.reshape(S, P * L, 3)
    pop = from_arrays(coords, np.tile(np.arange(L), P), np.repeat(np.arange(P), L), bins)
    got = remap(pop, pd.DataFrame({"chrom": toy.chrom, "start": toy.start, "end": toy.end}))
    assert np.allclose(got.coords, toy.coords)


def test_contact_sums_match_bruteforce():
    T = toy_population(S=4, n_loci=6)
    rc = 700.0
    s = contact_sums(T, rc, "step")
    L = T.n_loci
    f_ref = np.zeros((L, L))
    hic_ref = np.zeros((L, L))
    for i in range(L):
        for j in range(L):
            vals = []
            for x in T.coords:
                combos = [(0, 0), (1, 1)] if T.chrom[i] == T.chrom[j] else [(a, b) for a in (0, 1) for b in (0, 1)]
                vals += [np.linalg.norm(x[a, i] - x[b, j]) < rc for a, b in combos]
                hic_ref[i, j] += sum(np.linalg.norm(x[a, i] - x[b, j]) < rc for a in (0, 1) for b in (0, 1))
            f_ref[i, j] = np.mean(vals)
    f = probability_matrix(s, pd.DataFrame({"chrom": T.chrom}))
    np.fill_diagonal(f_ref, 1.0)
    assert np.allclose(f, f_ref)
    assert np.allclose(s["hic"], hic_ref / len(T.coords))


def test_igm_radii_fill_occupancy():
    bins = pd.DataFrame({"chrom": ["chr1"] * 10 + ["chr2"] * 5, "start": 0, "end": 1_000_000})
    r = igm_radii(bins, {"chr1": 2, "chr2": 2}, 5000.0, 0.2)
    V = 4 / 3 * np.pi * 5000.0 ** 3
    assert np.isclose(2 * (4 / 3 * np.pi * r ** 3).sum(), 0.2 * V)


def test_model_bins_centered(toy):
    b = model_bins(toy, "centered:3000000")
    mid = (toy.start + toy.end) // 2
    assert ((b.start <= mid) & (b.end > mid)).all()
    same = b.chrom.to_numpy()[1:] == b.chrom.to_numpy()[:-1]
    assert (b.start.to_numpy()[1:][same] >= b.end.to_numpy()[:-1][same]).all()


def test_simulated_counts_through_preprocessing(toy):
    s = contact_sums(toy, 800.0, "gauss")
    bins = model_bins(toy, "centered:3000000")
    m, fine = simulate_counts(s["hic"], bins, reads=200_000, eps=0.02, bias_sd=0.1, fine_sub=5, seed=1)
    assert m.shape == (len(fine), len(fine)) and len(fine) == 5 * len(bins) and m.sum() > 50_000
    pp = load_preprocess()
    f_exact = probability_matrix(contact_sums(toy, 800.0, "gauss"), bins)
    target = float(np.mean(f_exact.sum(1)))
    res = pp.preprocess_igm(m, fine, params=pp.IGMPreprocessParams(target_contacts=target), coarse_bins=bins)
    got = res.probabilities.toarray()
    iu = np.triu_indices(len(bins), 2)
    from scipy import stats
    assert stats.spearmanr(got[iu], f_exact[iu])[0] > 0.8


def test_pair_samples_pooling(toy):
    i, j = np.array([0, 0]), np.array([1, 30])                    # cis, trans
    d = pair_samples(toy, i, j)
    S = toy.n_structures
    assert np.isfinite(d[:, 0]).sum() == 2 * S and np.isfinite(d[:, 1]).sum() == 4 * S


def test_self_score_is_perfect_and_copy_invariant():
    T = toy_population(S=40, two_states=True)
    R = Population(T.chrom, T.start, T.end, T.coords[:, ::-1] * 3.0)       # swapped copies, other units
    rc = 700.0
    res = score_population(R, T, rc=rc, ks_pairs=500, n_triplets=300, max_query=10, k_candidates=3)
    assert np.isclose(res["scale"], 1 / 3, rtol=1e-4)
    assert res["pair"]["w1_median"] < 1e-4 and res["pair"]["ks_median"] < 0.02
    assert res["contact"]["r0.5"]["mae"] < 1e-9 and res["triplet"]["p3_mae"] < 1e-9
    assert res["radial"]["w1_median"] < 1e-6 and res["cluster"]["tv"] < 1e-9
    assert res["nearest"]["nearest_rmsd_rel_median"] < 1e-5


def test_metrics_see_differences():
    T = toy_population(S=60, two_states=True, seed=1)
    R = toy_population(S=60, two_states=False, seed=2)                  # no compact subpopulation
    res = score_population(R, T, rc=700.0, ks_pairs=500, n_triplets=300, max_query=10, k_candidates=3)
    ref = score_population(toy_population(S=60, two_states=True, seed=3), T, rc=700.0, ks_pairs=500,
                           n_triplets=300, max_query=10, k_candidates=3)
    assert res["pair"]["w1_median_cis"] > ref["pair"]["w1_median_cis"]
    assert res["c2st"]["auc"] > ref["c2st"]["auc"] and 0.3 < ref["c2st"]["auc"] < 0.7


def test_diploid_rmsd_recovers_swaps_rotation_mirror(toy):
    T = toy.coords[0].astype(float)
    rng = np.random.default_rng(0)
    Q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    Y = T.copy()
    m = toy.chrom == "chr2"
    Y[:, m] = T[::-1][:, m]                                       # chr2 copies swapped
    Y = -(2.5 * Y @ Q + 100.0)                                    # rotate, scale, translate, mirror
    assert diploid_rmsd(T, Y, toy.chrom) < 1e-6


def test_triplets_cooperativity_definition(toy):
    trip = sample_triplets(toy, 200, seed=1)
    assert len(trip) and (trip[:, 0] < trip[:, 1]).all() and (trip[:, 1] < trip[:, 2]).all()
    assert (toy.chrom[trip[:, 0]] == toy.chrom[trip[:, 2]]).all()
    f = triplet_frequencies(toy, trip, 700.0)
    assert (f["p3"] <= np.minimum(f["pij"], f["pik"]) + 1e-12).all()


def test_maxwell_inversion():
    sig = np.array([100.0, 300.0, 900.0])
    f = maxwell_cdf(500.0, sig)
    assert np.allclose(maxwell_sigma(f, 500.0), sig, rtol=1e-3)


def test_gaussian_baselines_and_oracle():
    T = toy_population(S=300, n_loci=12, seed=4)
    f = probability_matrix(contact_sums(T, 700.0, "step"), pd.DataFrame({"chrom": T.chrom}))
    G = contact_gaussian(f, 700.0, T.chrom, T.start, T.end, 3000, 2, seed=1)
    i, j = all_pairs(T)
    from bulk_metrics import contact_frequency
    cis = T.chrom[i] == T.chrom[j]
    got = contact_frequency(G, i, j, 700.0)
    want = f[i, j]
    assert np.mean(np.abs(got - want)[cis]) < 0.03              # pairwise contacts reproduced
    H = hipps(f, T.chrom, T.start, T.end, 50, 2)
    assert H.coords.shape == (50, 2, T.n_loci, 3) and np.isfinite(H.coords).all()
    D = dimes_oracle(T, 3000, seed=2)
    d2_T = np.nanmean(pair_samples(T, i, j) ** 2, 0)
    d2_D = np.nanmean(pair_samples(D, i, j) ** 2, 0)
    assert np.median(np.abs(d2_D / d2_T - 1)) < 0.1
    C = consensus(f, T.chrom, T.start, T.end, 10, 2)
    assert C.coords.shape == (10, 2, T.n_loci, 3)
    RP = random_polymer(T, 10)
    assert np.isfinite(RP.coords).all()
    A, B = truth_halves(T)
    assert A.n_structures + B.n_structures == T.n_structures


def test_chrom_shuffle_twin_preserves_cis():
    T = toy_population(S=200, seed=5)
    W = chrom_shuffle(T, 200, seed=1)
    for c in np.unique(T.chrom):                                   # each chromosome is a truth chromosome
        m = T.chrom == c
        Wc = W.coords[:, :, m] - np.nanmean(W.coords[:, :, m], axis=2, keepdims=True)
        Tc = T.coords[:, :, m] - np.nanmean(T.coords[:, :, m], axis=2, keepdims=True)
        assert any(np.allclose(Wc[0], Tc[s], atol=1e-2) for s in range(T.n_structures))
    pm = pair_match(T, W, 700.0)
    assert pm["r1rc"]["mae_cis"] < 0.03


def test_score_cli_end_to_end(tmp_path):
    from score import main as score_main
    T = toy_population(S=30, seed=6)
    T.save(tmp_path / "truth.npz")
    toy_population(S=30, seed=7).save(tmp_path / "pops" / "method_x.npz")
    A, B = truth_halves(T)
    A.save(tmp_path / "pops" / "truth_half_A.npz")
    B.save(tmp_path / "pops" / "truth_half_B.npz")
    score_main(["score", "--truth", str(tmp_path / "truth.npz"), "--pop-dir", str(tmp_path / "pops"), "--rc-nm", "700",
                "--ks-pairs", "200", "--n-triplets", "100", "--max-query", "5", "--k-candidates", "2",
                "--out", str(tmp_path / "s.json")])
    d = json.loads((tmp_path / "s.json").read_text())
    assert set(d["methods"]) == {"method_x", "truth_half_A"}
    from bulk_aggregate import main as agg_main
    agg_main(["--scores", str(tmp_path / "s.json"), "--out", str(tmp_path / "tables")])
    g = pd.read_csv(tmp_path / "tables" / "gain.csv")
    assert (g.method == "method_x").all() and len(g)
