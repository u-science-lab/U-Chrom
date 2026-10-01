"""robust_compare.py: development-set guard and paired statistics; robust_diag.py: noise-flag regeneration."""

import json

import numpy as np
import pytest

import robust_compare as rc
from conftest import toy_polymer


def _score(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"methods": {"robust" if "robust" in str(path) else "nucdyn_gpu": {
        "median_over_models": {"dist_spearman_cis": value, "rmsd_rel": 1 - value}}}}))


def test_compare_pairs_dev_units_and_refuses_test_units(tmp_path):
    names = [f"truth_{t}_d40_rc1_e{e}_s1" for t in (1, 2) for e in (0, 0.2)]
    for k, n in enumerate(names):
        _score(tmp_path / "base" / "su2020_chr21" / f"{n}.json", 0.7)
        _score(tmp_path / "robust" / "v" / "su2020_chr21" / f"{n}.json", 0.75)
    _score(tmp_path / "base" / "su2020_chr21" / "truth_3_d40_rc1_e0_s1.json", 0.1)  # test unit: ignored
    df = rc.sim_table(tmp_path / "robust", tmp_path / "base")
    assert set(df["truth"]) == {"truth_1", "truth_2"}
    lines, recs = rc.sim_report(df)
    allrow = [r for r in recs if r["stratum"] == "all"][0]
    assert allrow["n"] == 4 and abs(allrow["diff"] - 0.05) < 1e-12
    _score(tmp_path / "robust" / "v" / "su2020_chr21" / "truth_4_d40_rc1_e0_s1.json", 0.9)
    with pytest.raises(SystemExit):
        rc.sim_table(tmp_path / "robust", tmp_path / "base")


def test_boot_ci_brackets_mean():
    d = np.random.default_rng(0).normal(0.02, 0.01, 50)
    m, lo, hi = rc.boot_ci(d)
    assert lo < m < hi and lo > 0


def test_noise_flags_regenerate_simulated_reads():
    import simulate
    from robust_diag import noise_flags

    t = toy_polymer(n_chrom=1, n_bins=80)
    ca, pa, cb, pb, info = simulate.simulate_reads(t, reads=500, rc_rel=1.0, eps=0.2, seed=3)
    is_noise, ra, rb, _ = noise_flags(t, info)
    assert np.array_equal(ra, pa) and np.array_equal(rb, pb)
    assert is_noise.sum() == info["n_noise"]
