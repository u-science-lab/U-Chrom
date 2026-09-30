"""uchrom.recon.bulk.consensus: restraint construction, superposition and synthetic
end-to-end recovery (synthetic data test correctness only; real-data validation is
benchmarks/bulk/consensus/)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from uchrom.recon.bulk.consensus import (ConsensusParams, MatrixSource, fit_decay, fit_power_law, kabsch,
                                         native_available, reconstruct_consensus, stage_ladder)
from uchrom.recon.bulk.consensus._restraints import build_stage, load_stage, random_per_bin, top_per_bin

from ._consensus_synth import dist_r, forward_counts, similarity_rmsd, truth_genome

needs_engine = pytest.mark.skipif(not native_available(), reason="uchrom_nucdyn with the consensus protocol not installed")


def test_stage_ladder():
    p = ConsensusParams()
    assert stage_ladder(250_000, p) == [4_000_000, 1_000_000, 250_000]
    assert stage_ladder(10_000, p) == [2_560_000, 640_000, 160_000, 40_000, 10_000]
    assert stage_ladder(1_000_000, p) == [4_000_000, 1_000_000]
    assert stage_ladder(50_000, p.replace(stage_resolutions=[1_000_000, 200_000])) == [1_000_000, 200_000, 50_000]
    with pytest.raises(ValueError):
        stage_ladder(50_000, p.replace(stage_resolutions=[1_000_000, 130_000, 50_000]))


def test_fit_decay_and_power_law():
    s = np.arange(200, dtype=float)
    e = np.r_[np.nan, 3.0 * (s[1:] * 1e5) ** -1.1]
    g, info = fit_decay(e, 100_000, 10_000_000)
    assert abs(g - 1.1) < 1e-9 and info["n_points"] > 50
    f = np.logspace(-3, 0, 50)
    a, d0 = fit_power_law(f, 2.5 * f ** (-1 / 3.7))
    assert abs(a - 3.7) < 1e-9 and abs(d0 - 2.5) < 1e-9


def test_top_and_random_per_bin():
    i = np.array([0, 0, 0, 1, 1, 2])
    j = np.array([1, 2, 3, 2, 3, 3])
    score = np.array([5.0, 4.0, 3.0, 2.0, 1.0, 0.5])
    m = top_per_bin(i, j, score, 1)
    # bin 0 keeps (0,1); bin 1 keeps (0,1) too; bin 2 keeps (0,2); bin 3 keeps (0,3)
    assert m.tolist() == [True, True, True, False, False, False]
    r = random_per_bin(i, j, 2, np.random.default_rng(0))
    counts = np.bincount(np.concatenate([i[r], j[r]]), minlength=4)
    assert (counts >= np.minimum(2, np.bincount(np.concatenate([i, j])))).all()


def test_kabsch_similarity():
    rng = np.random.default_rng(0)
    a = rng.normal(size=(100, 3))
    th = 0.7
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    b = 2.5 * a @ R.T + 3.0
    b[:, 0] *= -1                                          # mirror
    fit, r = kabsch(a, b, reflection=True, scale=True)
    assert r < 1e-10 and np.allclose(fit, a)
    _, r2 = kabsch(a, b, reflection=False, scale=True)
    assert r2 > 0.1


def _two_chrom_matrix(biased=True):
    """Deterministic 2-chromosome matrix with an exact power-law decay and bin biases."""
    L = [60, 40]
    rows = []
    for c, n in enumerate(L):
        st = np.arange(n) * 100_000
        rows.append(pd.DataFrame({"chrom": f"chr{c + 1}", "start": st, "end": st + 100_000}))
    bins = pd.concat(rows, ignore_index=True)
    n = len(bins)
    chrom = bins["chrom"].to_numpy()
    pos = np.arange(n) - np.where(chrom == "chr2", L[0], 0)
    sep = np.abs(pos[:, None] - pos[None])
    cis = chrom[:, None] == chrom[None]
    f = np.where(cis, 1000.0 * np.maximum(sep, 1) ** -1.0, 8.0)
    bias = np.linspace(0.7, 1.3, n) if biased else np.ones(n)
    return sp.csr_matrix(np.triu(f * bias[:, None] * bias[None])), bins, f


def test_targets_bounds_and_weights():
    C, bins, f = _two_chrom_matrix()
    p = ConsensusParams(balance="kr", min_coverage=0.0, dense_max_bins=1000, alpha=4.0, nu=0.3, lower=0.8, upper=1.2,
                        relative_error=True, trans_weight=0.5)
    px = load_stage(MatrixSource(C, bins), 100_000, ["chr1", "chr2"], "genome", 100, p)
    # balancing removes the bin biases: same balanced values as the unbiased matrix
    C0, _, _ = _two_chrom_matrix(biased=False)
    px0 = load_stage(MatrixSource(C0, bins), 100_000, ["chr1", "chr2"], "genome", 100, p)
    assert np.array_equal(px.i, px0.i) and np.allclose(px.b, px0.b, rtol=1e-5)
    fb = sp.coo_matrix((px.b, (px.i, px.j)), shape=f.shape).toarray()
    fb = fb + fb.T
    sm = build_stage(px, 0, 100_000, None, None, 4.0, 0.3, p)
    assert sm.D == 1.0 and sm.radius == 0.5
    r = sm.rest[sm.rest["kind"] == "dense"]
    bi, bj = sm.bead_bin[r["i"].to_numpy()], sm.bead_bin[r["j"].to_numpy()]
    fnn = px.expected[1]
    expect = np.maximum((fb[bi, bj] / fnn) ** -0.25, 1.0)
    assert np.allclose(r["target"], expect, rtol=1e-6)
    assert np.allclose(r["lo"], 0.8 * r["target"]) and np.allclose(r["hi"], 1.2 * r["target"])
    # confidence n / (n + n0) x relative-error factor (D / hi)^2
    assert np.allclose(r["w"], r["n"] / (r["n"] + 10.0) * (1.0 / r["hi"]) ** 2)
    # dense = every measurable cis pair with sep >= 2 (adjacent pairs only as backbone); trans sparse
    same = bins["chrom"].to_numpy()[bi] == bins["chrom"].to_numpy()[bj]
    assert same.all() and (np.abs(bi - bj) >= 2).all()
    tr = sm.rest[sm.rest["kind"] == "trans"]
    ti, tj = sm.bead_bin[tr["i"].to_numpy()], sm.bead_bin[tr["j"].to_numpy()]
    assert len(tr) and (bins["chrom"].to_numpy()[ti] != bins["chrom"].to_numpy()[tj]).all()
    assert np.allclose(tr["w_conf"], tr["n"] / (tr["n"] + 10.0) * 0.5)
    # every bin gets at most trans_sample_per_bin random + max_trans_per_bin enriched partners (+ ties)
    assert np.bincount(np.r_[ti, tj]).max() <= 2 * (p.trans_sample_per_bin + p.max_trans_per_bin)
    bb = sm.rest[sm.rest["kind"] == "backbone"]
    assert len(bb) == len(bins) - 2 and np.allclose(bb["hi"], 1.2)
    assert sm.force_const == pytest.approx(p.force_scale * sm.n_beads / sm.rest["w"].sum())


def test_measurable_selection_and_carry():
    C, bins, f = _two_chrom_matrix()
    src = MatrixSource(C, bins)
    p = ConsensusParams(balance="kr", min_coverage=0.0, dense_max_bins=10, band_min_bins=3, band_factor=3.0,
                        long_ladder_ratio=1.5, max_long_per_bin=0, trans_max_resolution=200_000, min_expected=5.0)
    px0 = load_stage(src, 400_000, ["chr1", "chr2"], "genome", 100, p)
    s0 = build_stage(px0, 0, 100_000, None, None, 4.0, 0.3, p)
    px1 = load_stage(src, 100_000, ["chr1", "chr2"], "cis", 50, p)
    s1 = build_stage(px1, 1, 100_000, 400_000, s0, 4.0, 0.3, p)
    k = s1.counts()
    assert k["band"] > 0 and k["long_cis"] > 0 and k["carried"] > 0 and k["trans"] == 0
    band = s1.rest[s1.rest["kind"] == "band"]
    assert (np.abs(s1.bead_bin[band["j"]] - s1.bead_bin[band["i"]]) <= s1.band_bins).all()
    car = s1.rest[s1.rest["kind"] == "carried"]
    ci, cj = s1.bead_bin[car["i"]], s1.bead_bin[car["j"]]
    trans = bins["chrom"].to_numpy()[ci] != bins["chrom"].to_numpy()[cj]
    assert trans.any()                                      # trans comes down from the coarse stage
    assert (np.abs(cj - ci)[~trans] > s1.band_bins).all()   # carried only outside the band
    # no pair restrained twice
    key = s1.rest["i"] * s1.n_beads + s1.rest["j"]
    nb = s1.rest["kind"] != "backbone"
    assert not key[nb].duplicated().any()


@needs_engine
@pytest.mark.parametrize("sparse", [False, True])
def test_whole_genome_synthetic_recovery(sparse):
    X, bins = truth_genome(seed=0)
    C = forward_counts(X, seed=10)
    kw = dict(dense_max_bins=20, trans_max_resolution=800_000) if sparse else {}
    cd = reconstruct_consensus(C, bins=bins, n_runs=4, seed=0, device="cpu", **kw)
    bb = cd.spots["bin_id"].to_numpy()
    T = X[bb]
    ch = bins["chrom"].to_numpy()[bb]
    same = ch[:, None] == ch[None]
    r_all, r_cis = dist_r(T, cd.coords), dist_r(T, cd.coords, same)
    rmsd = similarity_rmsd(T, cd.coords)
    print(f"sparse={sparse}: r_all {r_all:.3f} r_cis {r_cis:.3f} r_trans {dist_r(T, cd.coords, ~same):.3f} "
          f"sim-RMSD/Rg {rmsd:.3f} precision {cd.uns['consensus']['precision']}")
    assert r_all > 0.93 and r_cis > 0.9 and rmsd < 0.4
    # output layout
    u = cd.uns["consensus"]
    assert u["chroms"] == ["chr1", "chr2", "chr3"] and u["stage_resolutions"][-1] == 50_000
    assert cd.spots["cell_id"].astype(str).unique().tolist() == ["consensus"]
    assert cd.spots["trace_id"].nunique() == 3
    assert sorted(k for k in cd.layers if k.startswith("run_")) == ["run_0", "run_1", "run_2", "run_3"]
    assert "mean_refined" in cd.layers
    assert {"consensus_spread", "consensus_spread_chrom", "n_restraints"} <= set(cd.bin_tracks.columns)
    assert len(cd.results["consensus.anneal"]) == 4
    assert u["precision"]["distance_r_median"] > 0.85


@needs_engine
def test_single_chromosome_and_gpu_matches_cpu_statistically():
    import uchrom_nucdyn

    X, bins = truth_genome(seed=1)
    C = forward_counts(X, seed=11)
    cpu = reconstruct_consensus(C, bins=bins, chrom="chr1", n_runs=3, device="cpu", refine_mean=False)
    assert cpu.spots["trace_id"].nunique() == 1
    T = X[cpu.spots["bin_id"].to_numpy()]
    r_cpu = dist_r(T, cpu.coords)
    assert r_cpu > 0.9
    if not uchrom_nucdyn.gpu_available():
        pytest.skip("no GPU")
    gpu = reconstruct_consensus(C, bins=bins, chrom="chr1", n_runs=3, device="gpu", refine_mean=False)
    r_gpu = dist_r(T, gpu.coords)
    print(f"single chromosome: r CPU {r_cpu:.3f}, GPU {r_gpu:.3f}, CPU vs GPU {dist_r(cpu.coords, gpu.coords):.3f}")
    assert r_gpu > 0.9 and dist_r(cpu.coords, gpu.coords) > 0.9


@needs_engine
def test_chromdata_with_linked_cool(tmp_path):
    cooler = pytest.importorskip("cooler")
    from uchrom.core import ChromData

    X, bins = truth_genome(lengths=(80, 60), seed=2)
    C = sp.triu(forward_counts(X, seed=12)).tocoo()
    path = str(tmp_path / "toy.cool")
    pix = pd.DataFrame({"bin1_id": C.row, "bin2_id": C.col, "count": C.data.astype(np.int32)})
    cooler.create_cooler(path, bins, pix, ordered=True)
    df = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [50_000], "x": [0.0], "y": [0.0], "z": [0.0]})
    cd = ChromData.from_dataframe(df)
    cd.link_cool(path)
    out = reconstruct_consensus(cd, resolution=50_000, n_runs=2, device="cpu", refine_mean=False,
                                temp_steps=100, refine_temp_steps=50)
    assert out.uns["consensus"]["input"]["kind"] == "cooler"
    tab = cd.results["consensus.anneal"]
    assert {"x", "y", "z", "spread"} <= set(tab.columns) and len(tab) == len(out.spots)
    # the cooler cis reader (row chunks) returns the matrix source's band pixels
    from uchrom.recon.bulk.consensus import CoolerSource
    a = CoolerSource(path, chunk_bp=700_000).cis(100_000, "chr1", 7)
    b = MatrixSource(sp.coo_matrix((C.data, (C.row, C.col)), shape=(len(bins),) * 2), bins).cis(100_000, "chr1", 7)
    ka = pd.Series(a[2], index=a[0] * 1000 + a[1]).sort_index()
    kb = pd.Series(b[2], index=b[0] * 1000 + b[1]).sort_index()
    assert ka.index.equals(kb.index) and np.allclose(ka.to_numpy(), kb.to_numpy())
