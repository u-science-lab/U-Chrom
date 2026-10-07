"""uchrom.fea.compare: structures against each other, imaging and contacts — synthetic structures with known
answers."""

import numpy as np
import pandas as pd
import pytest
from scipy.spatial.transform import Rotation

from chromdata import ChromData

from uchrom.fea import (bin_index, compare_distances, compare_structures, contact_agreement, contact_distances,
                        distance_correlation, ensemble_agreement, ensemble_models, kabsch_rmsd, match_spots,
                        rebin_coords)


def _walk(n, seed=0):
    return np.cumsum(np.random.default_rng(seed).normal(size=(n, 3)), axis=0)


def _structure(chroms=(("chr1", 30), ("chr2", 20)), res=100, seed=0, models=0, end_convention=False):
    """One haploid structure: one trace per chromosome, bins of ``res`` bp from 0."""
    rows, xyz = [], []
    for k, (c, n) in enumerate(chroms):
        rows += [(c, i * res, (i + 1) * res, c, "cell") for i in range(n)]
        xyz.append(_walk(n, seed + k) + 20 * k)
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cd = ChromData(np.concatenate(xyz), spots)
    rng = np.random.default_rng(seed + 100)
    for m in range(models):
        cd.layers[f"model_{m}"] = cd.coords @ Rotation.random(random_state=rng).as_matrix().T + rng.normal(size=3)
    if models:
        cd.coords = cd.layers["model_0"].copy()
    if end_convention:
        cd.uns["nucdyn"] = {"particle_position": "end"}
    return cd


def test_kabsch_rmsd():
    a = _walk(40)
    R = Rotation.from_euler("xyz", [30, -50, 80], degrees=True).as_matrix()
    assert kabsch_rmsd(a, a @ R.T + [3, -1, 2]) == pytest.approx(0, abs=1e-9)
    mirror = a * [1, 1, -1]
    assert kabsch_rmsd(a, mirror) > 0.1
    assert kabsch_rmsd(a, mirror @ R.T, reflection=True) == pytest.approx(0, abs=1e-9)
    b = a + np.random.default_rng(1).normal(scale=0.5, size=a.shape)
    assert kabsch_rmsd(a, b) == pytest.approx(kabsch_rmsd(b, a))
    c = b.copy()
    c[3] = np.nan
    assert kabsch_rmsd(a, c) == pytest.approx(kabsch_rmsd(np.delete(a, 3, 0), np.delete(b, 3, 0)))
    with pytest.raises(ValueError):
        kabsch_rmsd(a, b[:5])


def test_distance_correlation_by_group():
    a = _walk(30)
    assert distance_correlation(a, a * 3 + 1) == pytest.approx(1)
    groups = np.r_[np.zeros(20), np.ones(10)]
    b = a.copy()
    b[20:] = _walk(10, seed=5)                   # group 1 differs, group 0 the same
    assert distance_correlation(a, b, groups=groups, min_size=11) == pytest.approx(1)
    r1 = distance_correlation(a[20:], b[20:])
    assert distance_correlation(a, b, groups=groups) == pytest.approx(np.median([1.0, r1]))
    assert np.isnan(distance_correlation(a, b, groups=groups, min_size=50))


def test_ensemble_models_and_agreement():
    cd = _structure(models=12)
    models = ensemble_models(cd)
    assert len(models) == 12                                    # coords = model_0: not repeated
    assert np.array_equal(models[2], cd.layers["model_2"]) and np.array_equal(models[10], cd.layers["model_10"])
    pub = _structure(models=0)
    pub.layers["model_3"] = pub.coords + 1
    pub.layers["model_2"] = pub.coords + 2
    order = ensemble_models(pub)
    assert [float(m[0, 0] - pub.coords[0, 0]) for m in order] == [0.0, 2.0, 1.0]   # coords, model_2, model_3
    ag = ensemble_agreement(cd)
    assert ag.n_models == 12 and ag.rmsd.shape == (12, 12)
    assert ag.rmsd_mean == pytest.approx(0, abs=1e-8) and ag.rmsd_per_chrom == pytest.approx(0, abs=1e-8)
    assert ag.distance_r == pytest.approx(1)
    assert set(ag.scores) == {"rmsd_mean", "rmsd_per_chrom", "distance_r", "n_models"}
    noisy = _structure(models=3)
    noisy.layers["model_1"] = noisy.layers["model_1"] + np.random.default_rng(3).normal(size=(50, 3))
    assert ensemble_agreement(noisy).rmsd[0, 1] > 0.5 and ensemble_agreement(noisy).rmsd[0, 2] < 1e-8


def test_bin_index_conventions():
    bins = pd.DataFrame({"chrom": ["c1", "c1", "c1", "c2"], "start": [0, 10, 30, 0], "end": [10, 20, 40, 5]})
    pos = np.array([0, 9, 10, 20, 25, 30, 40, 3])
    chrom = ["c1"] * 7 + ["c2"]
    assert bin_index(bins, chrom, pos).tolist() == [0, 0, 1, -1, -1, 2, -1, 3]
    assert bin_index(bins, chrom, pos, closed="right").tolist() == [-1, 0, 0, 1, -1, -1, 2, 3]
    assert bin_index(bins, "c3", [1]).tolist() == [-1]
    shuffled = bins.iloc[[2, 0, 3, 1]]
    assert bin_index(shuffled, chrom, pos).tolist() == [1, 1, 3, -1, -1, 0, -1, 2]


def test_rebin_coords_averages_per_trace():
    spots = pd.DataFrame({"chrom": "c1", "start": [0, 10, 20, 0, 10, 30], "end": [10, 20, 30, 10, 20, 40],
                          "trace_id": ["a", "a", "a", "b", "b", "b"]})
    xyz = np.arange(18, dtype=float).reshape(6, 3)
    cd = ChromData(xyz, spots)
    grid = pd.DataFrame({"chrom": "c1", "start": [0, 20, 40], "end": [20, 40, 60]})
    cube, groups = rebin_coords(cd, grid)
    assert cube.shape == (2, 3, 3) and set(groups) == {"a", "b"}
    a = list(groups).index("a")
    b = list(groups).index("b")
    assert np.allclose(cube[a, 0], xyz[:2].mean(0)) and np.allclose(cube[a, 1], xyz[2])
    assert np.allclose(cube[b, 0], xyz[3:5].mean(0)) and np.allclose(cube[b, 1], xyz[5])
    assert np.isnan(cube[:, 2]).all()
    one, g = rebin_coords(cd, grid, by=None)
    assert one.shape == (1, 3, 3) and np.allclose(one[0, 1], xyz[[2, 5]].mean(0))


def test_match_spots_pairs_rows():
    cd = _structure()
    cd.spots["spot_id"] = np.arange(cd.n_spots) * 7
    perm = np.random.default_rng(0).permutation(cd.n_spots)
    other = cd[perm]
    ia, ib = match_spots(cd, other)
    assert np.array_equal(cd.coords[ia], other.coords[ib])
    ia2, ib2 = match_spots(cd, other, on=["trace_id", "chrom", "start"])
    assert np.array_equal(cd.coords[ia2], other.coords[ib2])
    dup = cd.copy()
    dup.spots["spot_id"] = 1
    with pytest.raises(ValueError, match="duplicates"):
        match_spots(dup, other)


def test_compare_distances_population_vs_scaled_reference():
    rng = np.random.default_rng(0)
    base = _walk(12)
    rows, xyz, rows_ref, xyz_ref = [], [], [], []
    for t in range(15):
        noise = rng.normal(scale=0.01, size=base.shape)
        rows += [("c1", i * 100, (i + 1) * 100, f"m{t}") for i in range(12)]
        xyz.append(base + noise)
        for i in range(24):                                     # imaging: 50 bp segments, two per model bin
            rows_ref.append(("c1", i * 50, (i + 1) * 50, f"f{t}"))
        xyz_ref.append(np.repeat(base * 40, 2, axis=0) + rng.normal(scale=0.01, size=(24, 3)))
    cols = ["chrom", "start", "end", "trace_id"]
    model = ChromData(np.concatenate(xyz), pd.DataFrame(rows, columns=cols))
    ref = ChromData(np.concatenate(xyz_ref), pd.DataFrame(rows_ref, columns=cols))
    v = compare_distances(model, ref)
    assert v.n_bins == 12 and v.n_pairs == 66
    assert v.pearson > 0.999 and v.scale == pytest.approx(40, rel=1e-2)
    assert v.ratio == pytest.approx(1 / 40, rel=1e-2) and v.rel_error < 0.01
    assert v.model.shape == v.reference.shape == (12, 12) and len(v.bins) == 12
    assert set(v.scores) == {"pearson", "rel_error", "scale", "ratio", "n_bins", "n_pairs"}
    part = compare_distances(model, ref[(ref.spots_with_loci()["start"] < 600).to_numpy()])   # half imaged
    assert part.n_bins == 6 and part.pearson > 0.999
    with pytest.raises(ValueError, match="shared"):
        compare_distances(model, ChromData(np.zeros((2, 3)), pd.DataFrame(
            [("c9", 0, 10, "x"), ("c9", 10, 20, "x")], columns=cols)))


def test_compare_structures_maps_finer_particles():
    coarse = _structure(chroms=(("chr1", 30),), res=400, models=2)
    fine_rows, fine_xyz = [], []
    for i in range(120):                                       # four 100 bp particles per 400 bp particle
        fine_rows.append(("chr1", i * 100, (i + 1) * 100, "chr1"))
        fine_xyz.append(coarse.coords[i // 4] + 0.01 * (i % 4))
    fine = ChromData(np.array(fine_xyz), pd.DataFrame(fine_rows, columns=["chrom", "start", "end", "trace_id"]))
    v = compare_structures(coarse, fine)
    assert v.n_particles == 30 and v.r.shape == (2, 1) and v.distance_r > 0.999
    # NucDynamics particles are (start, end]: a particle starting at 400 belongs to the first one
    nd = _structure(chroms=(("chr1", 30),), res=400, end_convention=True)
    w = compare_structures(nd, fine, position="start")
    assert w.n_particles == 30 and w.distance_r > 0.9
    with pytest.raises(ValueError, match="haploid"):
        compare_structures(ChromData(np.zeros((2, 3)), pd.DataFrame(
            [("c1", 0, 10, "a"), ("c1", 0, 10, "b")], columns=["chrom", "start", "end", "trace_id"])), fine)


def test_contact_agreement_on_a_linked_map(tmp_path):
    cooler = pytest.importorskip("cooler")
    cd = _structure(chroms=(("chr1", 40),), res=1000, seed=4)
    X = cd.coords
    D = np.linalg.norm(X[:, None] - X[None], axis=-1)
    i, j = np.triu_indices(40, 1)
    px = pd.DataFrame({"bin1_id": i, "bin2_id": j, "count": np.rint(1000 * D[i, j] ** -2 + 1).astype(int)})
    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(40) * 1000, "end": np.arange(1, 41) * 1000})
    cooler.create_cooler(str(tmp_path / "m.cool"), bins, px, ordered=True)
    hic = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                   "end": pd.Series(dtype=np.int64),
                                                   "trace_id": pd.Series(dtype=str)}))
    hic.link_cool(str(tmp_path / "m.cool"), key="bulk")
    v = contact_agreement(cd, hic, balance=False)
    assert v.n_pairs == 780 and v.spearman > 0.99 and v.spearman_oe > 0.8
    near = contact_agreement(cd, hic, contacts="bulk", balance=False, max_separation=5000)
    assert near.n_pairs == sum(40 - k for k in range(1, 6)) and near.spearman > 0.9
    shuffled = cd.copy()
    shuffled.coords = np.random.default_rng(0).permutation(shuffled.coords)
    assert contact_agreement(shuffled, hic, balance=False).spearman < 0.5


def test_contact_distances_end_convention():
    cd = _structure(chroms=(("chr1", 5),), res=100, end_convention=True)
    X = cd.coords
    contacts = {"chrom_a": ["chr1", "chr1", "chr1", "chr2"], "pos_a": [100, 101, 50, 10],
                "chrom_b": ["chr1", "chr1", "chr1", "chr2"], "pos_b": [300, 150, 500, 20]}
    d = contact_distances(cd, contacts)                         # (start, end]: 100 -> particle 0, 101 -> 1
    assert d[0] == pytest.approx(np.linalg.norm(X[0] - X[2]))
    assert np.isnan(d[1])                                       # 101 and 150: the same particle
    assert d[2] == pytest.approx(np.linalg.norm(X[0] - X[4]))
    assert np.isnan(d[3])                                       # no chr2
    left = contact_distances(cd, contacts, closed="left")       # [start, end): 100 -> particle 1
    assert left[0] == pytest.approx(np.linalg.norm(X[1] - X[3])) and np.isnan(left[2])
