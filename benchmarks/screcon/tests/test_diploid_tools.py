"""Diploid benchmark tools on toys: copy-chain names, phased I/O, forward model, held-out pairs,
phase hold-back, hickit imputation mapping (checks the plumbing only)."""

import gzip

import numpy as np

from diploid import Phased, copy_name, hickit_copy, read_phased, split_copy, write_phased, write_phased_subset
from diploid_heldout import build_eval_pairs_diploid, expand, ploidy_of
from diploid_real import cmd_mask, phase_mask_metrics, ref_copy
from diploid_sim import simulate_phased
from run_hickit import map_imputed


def toy_truth(seed=0):
    rng = np.random.default_rng(seed)
    chrom, start, coords = [], [], []
    for c in ("chr1", "chr2"):
        for h in (0, 1):
            w = np.cumsum(rng.normal(scale=300, size=(40, 3)), 0) + [0, h * 5000, 0]
            chrom += [copy_name(c, h)] * 40
            start += list(range(0, 40_000_000, 1_000_000))
            coords.append(w)
    chrom = np.array(chrom)
    start = np.array(start, np.int64)
    return {"chrom": chrom, "start": start, "end": start + 100_000, "coords": np.concatenate(coords),
            "measured": np.ones(len(chrom), bool), "meta": {}}


def test_names():
    assert copy_name("chr1", 1) == "chr1(1)" and copy_name("chrX", 0, 1) == "chrX"
    assert split_copy("chr1(1)") == ("chr1", 1) and split_copy("chrX") == ("chrX", 0)
    assert hickit_copy("1b") == "1(1)" and hickit_copy("chrXa") == "chrX(0)"
    assert hickit_copy("chrX", {"chrX": 1}) == "chrX"
    pl = {"1": 2, "X": 2}
    assert ref_copy("1(pat)", pl) == "1(0)" and ref_copy("1(mat)", pl) == "1(1)" and ref_copy("Xb", pl) == "X(1)"


def test_forward_model_and_phased_io(tmp_path):
    t = toy_truth()
    c, tr, info = simulate_phased(t, reads_per_mb=50, rc_rel=1.0, eps=0.1, phased=0.3, phase_err=0.0, seed=1)
    assert abs(info["frac_ends_phased"] - 0.3) < 0.03
    # phased ends carry the true haplotype (no phase errors)
    for h, th in ((c.hap_a, tr["true_hap_a"]), (c.hap_b, tr["true_hap_b"])):
        assert (h[h >= 0] == th[h >= 0]).all()
    write_phased(tmp_path / "t.pairs.gz", c, {"chr1": 50_000_000, "chr2": 50_000_000})
    r = read_phased(tmp_path / "t.pairs.gz")
    assert np.array_equal(r.pos_a, c.pos_a) and np.array_equal(r.hap_b, c.hap_b)
    write_phased_subset(tmp_path / "s.pairs.gz", r, np.arange(len(r)) % 2 == 0)
    s = read_phased(tmp_path / "s.pairs.gz")
    assert len(s) == (len(r) + 1) // 2 and s.header == r.header


def test_heldout_positives_are_copy_resolved():
    t = toy_truth()
    c, _, _ = simulate_phased(t, reads_per_mb=200, rc_rel=1.0, eps=0.0, phased=0.5, phase_err=0.0, seed=2)
    pl = ploidy_of(c.chroms)
    e, rd, res = expand(c, pl)
    n_cand = np.bincount(rd)
    both = (c.hap_a >= 0) & (c.hap_b >= 0)
    assert (n_cand[both] == 1).all() and (n_cand[~both] > 1).all()
    held = np.arange(0, len(c), 10)
    ev = build_eval_pairs_diploid(c, held, 1_000_000, n_neg=5, seed=1)
    g = ev["grid"]
    assert ev["stats"]["n_pos"] > 0
    # every positive comes from a held-out read with both ends phased
    keys = set()
    gi, gj = g.index(e.chrom_a, e.pos_a), g.index(e.chrom_b, e.pos_b)
    for k in np.flatnonzero(np.isin(rd, held) & res):
        keys.add((min(gi[k], gj[k]), max(gi[k], gj[k])))
    assert all((a, b) in keys for a, b in zip(ev["pos_a"], ev["pos_b"]))
    # negatives never contacted by any candidate of any read
    allk = {(min(a, b), max(a, b)) for a, b in zip(gi, gj)}
    assert not any((a, b) in allk for a, b in zip(ev["neg_a"], ev["neg_b"]))
    # cis same-homolog option resolves more reads
    ev2 = build_eval_pairs_diploid(c, held, 1_000_000, n_neg=5, seed=1, cis_same=10_000_000)
    assert ev2["stats"]["n_heldout_reads_resolved"] > ev["stats"]["n_heldout_reads_resolved"]


def test_phase_mask_and_hickit_mapping(tmp_path):
    t = toy_truth()
    c, _, _ = simulate_phased(t, reads_per_mb=30, rc_rel=1.0, eps=0.0, phased=0.5, phase_err=0.0, seed=3)
    write_phased(tmp_path / "t.pairs.gz", c, {"chr1": 50_000_000, "chr2": 50_000_000})

    class A:
        contacts = str(tmp_path / "t.pairs.gz")
        frac = 0.2
        seed = 1
        out = str(tmp_path / "m.pairs.gz")
    cmd_mask(A)
    m = read_phased(A.out)
    z = np.load(A.out + ".mask.npz")
    assert ((np.where(z["end"] == 0, m.hap_a[z["row"]], m.hap_b[z["row"]])) == -1).all()
    # oracle probabilities -> accuracy 1; flipped -> 0
    probs = np.full((len(c), 4), 0.25)
    for r, e, h in zip(z["row"], z["end"], z["true_hap"]):
        o = c.hap_b[r] if e == 0 else c.hap_a[r]
        o = 0 if o < 0 else o
        code = 2 * h + o if e == 0 else 2 * o + h
        probs[r] = 0.0
        probs[r, code] = 1.0
    assert phase_mask_metrics(A.out, A.out + ".mask.npz", probs)["acc_all"] == 1.0
    # hickit's sorted, upper-triangle output mapped back to the input rows (ends swapped -> p01 / p10 swapped)
    rows = [("chr2", 5, "chr1", 9, "0.1", "0.2", "0.3", "0.4")]
    with gzip.open(tmp_path / "imp.pairs.gz", "wt") as fh:
        fh.write("#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1 phase_prob00 phase_prob01 phase_prob10 phase_prob11\n")
        fh.write(".\tchr1\t9\tchr2\t5\t.\t.\t.\t.\t0.1\t0.2\t0.3\t0.4\n")
    q = Phased(["chr2"], [5], [-1], ["chr1"], [9], [-1])
    np.testing.assert_allclose(map_imputed(q, str(tmp_path / "imp.pairs.gz"))[0], [0.1, 0.3, 0.2, 0.4])
    del rows
