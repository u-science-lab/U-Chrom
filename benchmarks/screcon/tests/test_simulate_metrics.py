import numpy as np
from scipy.spatial.transform import Rotation

from metrics import average_precision, bead_unit, precision, roc_auc, superpose, violations
from simulate import kernel, score_ensemble, simulate_reads
from truth import interpolate_missing, split_homologs


# --------------------------------------------------------------------------- forward model

def test_reads_depth_eps_seed(toy):
    a = simulate_reads(toy, reads=5000, rc_rel=1.0, eps=0.2, seed=7)
    b = simulate_reads(toy, reads=5000, rc_rel=1.0, eps=0.2, seed=7)
    c = simulate_reads(toy, reads=5000, rc_rel=1.0, eps=0.2, seed=8)
    info = a[4]
    assert info["n_reads"] == 5000 == len(a[1])
    assert abs(info["n_noise"] / 5000 - 0.2) < 0.03
    assert all(np.array_equal(x, y) for x, y in zip(a[:4], b[:4]))
    assert not np.array_equal(a[1], c[1])
    # positions inside the loci
    li = np.searchsorted(toy["start"], a[1], side="right") - 1
    assert np.all((a[1] > toy["start"][li]) & (a[1] < toy["end"][li]))
    # reads per Mb: 3 chromosomes x 15 Mb
    d = simulate_reads(toy, reads_per_mb=10, rc_rel=1.0, seed=1)[4]
    assert d["n_reads"] == 450 and abs(d["genome_span_mb"] - 45) < 1e-9


def test_step_kernel_only_close_pairs(toy):
    ca, pa, cb, pb, info = simulate_reads(toy, reads=3000, rc=150.0, kind="step", eps=0.0, seed=1)
    st = toy["start"][:150]                  # the same loci on every chromosome
    ia = np.searchsorted(st, pa, side="right") - 1 + 150 * (np.char.lstrip(ca.astype(str), "chr").astype(int) - 1)
    ib = np.searchsorted(st, pb, side="right") - 1 + 150 * (np.char.lstrip(cb.astype(str), "chr").astype(int) - 1)
    d = np.linalg.norm(toy["coords"][ia] - toy["coords"][ib], axis=1)
    assert np.all(d < 150.0)
    assert info["frac_cis"] > 0.5


def test_poisson_mode(toy):
    info = simulate_reads(toy, q=0.5, rc_rel=1.0, eps=0.1, seed=3)[4]
    assert info["n_signal"] > 0 and info["n_noise"] > 0 and info["reads_requested"] is None


def test_kernels():
    d = np.array([0.0, 1.0, 2.0])
    assert np.allclose(kernel(d, 1.0, "gauss"), np.exp(-d ** 2))
    assert kernel(d, 1.5, "step").tolist() == [1, 1, 0]
    s = kernel(d, 1.0, "sigmoid")
    assert s[0] > 0.99 and abs(s[1] - 0.5) < 1e-9 and s[2] < 0.01


def test_interpolate_missing():
    chrom = np.array(["a"] * 4)
    X = np.array([[0, 0, 0], [np.nan] * 3, [2, 2, 2], [np.nan] * 3], float)
    Y, m = interpolate_missing(chrom, np.arange(4) * 10, X)
    assert m.tolist() == [True, False, True, False] and np.allclose(Y[1], 1) and np.allclose(Y[3], 2)


# --------------------------------------------------------------------------- scoring

def test_superpose_similarity_mirror():
    rng = np.random.default_rng(0)
    A = rng.normal(size=(50, 3))
    R = Rotation.random(random_state=1).as_matrix()
    B = -(A @ R.T) * 0.01 + 5                        # rotated, mirrored, scaled, shifted
    fit, r, s, mirrored = superpose(A, B, scale=True, mirror=True)
    assert r < 1e-8 and mirrored and abs(s - 100) < 1e-6
    assert superpose(A, B, scale=True, mirror=False)[1] > 0.1


def test_score_ensemble_perfect(toy):
    R = Rotation.random(random_state=2).as_matrix()
    X = np.stack([toy["coords"] @ R.T * 0.02, -toy["coords"] * 0.03])
    r = score_ensemble(toy, toy["chrom"], toy["end"], X)
    m = r["median_over_models"]
    assert m["rmsd_rel"] < 1e-6 and m["dist_pearson_whole"] > 0.999 and m["dist_spearman_cis"] > 0.999
    assert r["coverage"] == 1.0
    noisy = score_ensemble(toy, toy["chrom"], toy["end"], np.random.default_rng(0).normal(size=(3, 450, 3)))
    assert noisy["median_over_models"]["rmsd_rel"] > 0.7


def test_auc_ap():
    assert roc_auc([3, 4], [1, 2]) == 1.0 and roc_auc([1], [1]) == 0.5
    rng = np.random.default_rng(0)
    p, n = rng.normal(1, 1, 200), rng.normal(0, 1, 300)
    brute = np.mean([(a > b) + 0.5 * (a == b) for a in p for b in n])
    assert abs(roc_auc(p, n) - brute) < 1e-12
    assert average_precision([2, 2], [2]) < 1 and average_precision([3], [1, 2]) == 1.0


def test_violations_and_precision():
    chrom = np.array(["a"] * 10)
    X = np.cumsum(np.ones((10, 3)) / np.sqrt(3), 0)[None] * 2.0      # bead unit 2
    assert abs(bead_unit(chrom, X) - 2.0) < 1e-12
    v = violations(chrom, X, np.array([[0, 1], [0, 9]]), np.array([1, 1]))
    assert v["sic_pct_viol_gt2units"] == 50.0 and v["nd_pct_viol_gt4"] == 50.0
    p = precision(np.stack([X[0], X[0] + 1.0]), chrom)
    assert p["rmsd_to_mean"] < 1e-9


def test_split_homologs_two_blobs():
    rng = np.random.default_rng(0)
    li = np.repeat(np.arange(40), 2)
    xyz = rng.normal(size=(80, 3)) * 0.3
    xyz[1::2] += 5.0                                   # homolog B far from A
    lab, sep = split_homologs(xyz, li)
    assert sep > 3 and (lab[0::2] != lab[1::2]).all()
