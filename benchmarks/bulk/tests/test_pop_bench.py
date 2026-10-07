"""EMber-pop benchmark helpers (``pop_metrics``, ``pop_split``): correctness on synthetic toys."""

import numpy as np
import pandas as pd
from bulk_toys import toy_population

from bulk_metrics import all_pairs, pair_samples
from pop_metrics import (block_sums_locus, block_sums_pair, bootstrap_mean, chrom_codes, ellip_radius,
                         pair_w1, score_arrays, shape_stats, territory_neighbourhood)
from pop_split import split_ids
from population import Population


def _ellipsoid_population(S=30, L=400, axes=(9.0, 4.0, 1.0), seed=0):
    rng = np.random.default_rng(seed)
    X = np.zeros((S, 2, L, 3))
    for s in range(S):
        u = rng.normal(size=(2 * L, 3))
        u /= np.linalg.norm(u, axis=1)[:, None]
        r = rng.random(2 * L) ** (1 / 3)
        Y = u * r[:, None] * np.asarray(axes)
        R, _ = np.linalg.qr(rng.normal(size=(3, 3)))         # random orientation and offset
        X[s] = (Y @ R.T + rng.normal(size=3) * 50).reshape(2, L, 3)
    chrom = np.repeat(["chr1", "chr2"], L // 2)
    start = np.concatenate([np.arange(L // 2), np.arange(L // 2)]) * 1_000_000
    return Population(chrom, start, start + 100_000, X)


def test_ellip_radius_uniform_ellipsoid():
    P = _ellipsoid_population()
    rho = ellip_radius(P)
    # uniform ellipsoid: rho in [0, 1] (up to sampling of the gyration tensor), E[rho^3] uniform
    assert np.nanmax(rho) < 1.08
    q = np.nanquantile(rho ** 3, [0.25, 0.5, 0.75])
    assert np.allclose(q, [0.25, 0.5, 0.75], atol=0.03)
    # invariant to scale, rotation and translation
    R, _ = np.linalg.qr(np.random.default_rng(3).normal(size=(3, 3)))
    Q = Population(P.chrom, P.start, P.end, 3.0 * P.coords @ R.T + 7.0)
    assert np.allclose(ellip_radius(Q), rho, atol=1e-4)
    st = shape_stats(P)
    assert abs(np.median(st["r31"]) - 1 / 9) < 0.02 and abs(np.median(st["r21"]) - 4 / 9) < 0.03


def test_score_arrays_self_is_perfect(toy):
    i, j = all_pairs(toy, 2000, 0)
    arr, summ = score_arrays(toy, toy, i=i, j=j, rc=700.0, territory_structures=20)
    assert summ["P1_rho_w1_mean"] < 1e-9 and summ["P2_pair_w1_mean"] < 1e-6
    assert abs(summ["scale"] - 1) < 1e-9 and summ["territory_mae"] == 0
    # a shifted population is worse
    other = toy_population(seed=5)
    _, s2 = score_arrays(other, toy, i=i, j=j, rc=700.0, territory_structures=20)
    assert s2["P2_pair_w1_mean"] > 0.05 and s2["P1_rho_w1_mean"] > 0.0


def test_pair_w1_matches_bruteforce(toy):
    other = toy_population(seed=2)
    i, j = all_pairs(toy, 300, 1)
    got = pair_w1(other, toy, i, j, unit=1.0)
    q = (np.arange(100) + 0.5) / 100
    dr, dt = pair_samples(other, i, j), pair_samples(toy, i, j)
    want = np.mean(np.abs(np.nanquantile(dr, q, axis=0) - np.nanquantile(dt, q, axis=0)), axis=0)
    assert np.allclose(got["w1"], want)


def test_territory_neighbourhood_bruteforce():
    T = toy_population(S=5, n_chrom=3, n_loci=6)
    F, chroms = territory_neighbourhood(T, 900.0)
    assert chroms == ["chr1", "chr2", "chr3"]
    for a in range(3):
        for b in range(3):
            ia, ib = np.flatnonzero(T.chrom == chroms[a]), np.flatnonzero(T.chrom == chroms[b])
            hit = tot = 0
            for s in range(T.n_structures):
                for pa in range(2):
                    for pb in range(2):
                        if a == b and pa >= pb:
                            continue
                        d = np.linalg.norm(T.coords[s, pa, ia][:, None] - T.coords[s, pb, ib][None], axis=-1)
                        tot += 1
                        hit += d.min() < 900.0
            want = hit / tot if (a != b or tot) else np.nan
            if a <= b:
                assert np.isclose(F[a, b], want), (a, b)


def test_block_bootstrap_sums_and_ci():
    rng = np.random.default_rng(0)
    chrom = np.repeat(["c1", "c2", "c3", "c4"], 50)
    cc, names = chrom_codes(chrom)
    assert names == ["c1", "c2", "c3", "c4"]
    v = rng.normal(0.3, 1.0, len(chrom))
    s, n = block_sums_locus(v, cc, 4)
    assert np.isclose(s.sum() / n.sum(), v.mean())
    i, j = np.triu_indices(len(chrom), 1)
    pv = rng.normal(0.1, 0.5, len(i))
    S, N = block_sums_pair(pv, cc[i], cc[j], 4)
    iu = np.triu_indices(4)
    assert np.isclose(S[iu].sum() / N[iu].sum(), pv.mean())
    res = bootstrap_mean([(s, n), (S, N)], ["locus", "pair"], 4, n_boot=300)
    assert np.isclose(res["estimate"], (v.mean() + pv.mean()) / 2)
    assert res["ci"][0] < res["estimate"] < res["ci"][1]


def test_split_is_a_partition():
    ids = [f"c{k}" for k in range(20)]
    df = split_ids(ids, [("a", 5), ("b", 5), ("c", 10)])
    assert sorted(df.cell_id) == sorted(ids) and df.groupby("set").size().to_dict() == {"a": 5, "b": 5, "c": 10}
    assert split_ids(ids, [("a", 5), ("b", 15)]).cell_id.tolist()[:5] == df.cell_id.tolist()[:5]


def test_committed_split_file():
    from pop_split import load_split
    sp = load_split()
    assert not sp.duplicated(["dataset", "cell_id"]).any()
    n = sp.groupby(["dataset", "set"]).size().to_dict()
    assert n == {("su2020_genome", "dev_bulk"): 447, ("su2020_genome", "dev_truth"): 447,
                 ("su2020_genome", "test_bulk"): 447, ("su2020_genome", "test_truth"): 446,
                 ("takei2021_1mb", "test_bulk"): 100, ("takei2021_1mb", "test_truth"): 101}
