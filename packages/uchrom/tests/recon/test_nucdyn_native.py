"""NucDynamics on the native engine (``uchrom_recon``).

Skipped when the native package is not installed.  Uses chr19 of
``tests/fixtures/cell1.pairs.gz`` (Stevens et al. 2017, Cell 1) at 1 Mb / 0.5 Mb
with a short annealing schedule, so each run takes about a second.  These
are smoke and consistency checks; the real-data validation (all 8 Stevens
cells at 100 kb vs the published models) is in
``benchmarks/fig3/a_nucdyn_engine_*.py``.
"""

import warnings
from pathlib import Path

import numpy as np
import pytest
from tests import FIXTURES

un = pytest.importorskip("uchrom_recon")

PAIRS = FIXTURES / "cell1.pairs.gz"
QUICK = dict(genome_ranges=["chr19"], particle_sizes=[1e6, 5e5], temp_steps=[60], dynamics_steps=[50])


@pytest.fixture(autouse=True)
def _need_data():
    if not PAIRS.exists():
        pytest.skip("fixture cell1.pairs.gz missing")


def _backbone_ratio(X):
    rng = np.random.default_rng(0)
    nb = np.median(np.linalg.norm(X[1:] - X[:-1], axis=1))
    i, j = rng.integers(0, len(X), (2, 1000))
    return nb / np.median(np.linalg.norm(X[i] - X[j], axis=1))


def test_ensemble_chromdata_cpu():
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    cd = reconstruct_nucdyn(str(PAIRS), n_models=4, device="cpu", seed=1, cell_id="cell1", **QUICK)
    assert set(cd.spots["chrom"].astype(str)) == {"chr19"}
    assert sorted(cd.layers) == ["model_0", "model_1", "model_2", "model_3"]
    X = np.stack([cd.layers[k] for k in sorted(cd.layers)])
    assert np.isfinite(X).all()
    np.testing.assert_array_equal(cd.coords, cd.layers["model_0"])
    # 2017 protocol: particles at multiples of the size, interval (p - size, p]
    assert ((cd.bins["end"] - cd.bins["start"]) == 500_000).all()
    assert (cd.bins["end"] % 500_000 == 0).all()
    for x in X:
        assert _backbone_ratio(x) < 0.5
        # contact-bound particles are pulled together: sequence neighbours ~1 radius apart
        d = np.linalg.norm(np.diff(x, axis=0), axis=1)
        assert 0.3 < np.median(d) < 1.6
    # models differ (independent random starts) but not wildly
    assert not np.allclose(X[0], X[1])
    info = cd.uns["nucdyn"]
    assert info["protocol"] == "nuc_dynamics_2017" and info["n_models"] == 4
    stages = cd.results["nucdyn.stages"]
    assert list(stages["particle_size"]) == [1e6, 5e5]


def test_cpu_deterministic_across_thread_counts():
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    a = reconstruct_nucdyn(str(PAIRS), n_models=2, device="cpu", seed=7, n_threads=1, **QUICK)
    b = reconstruct_nucdyn(str(PAIRS), n_models=2, device="cpu", seed=7, n_threads=4, **QUICK)
    c = reconstruct_nucdyn(str(PAIRS), n_models=2, device="cpu", seed=8, n_threads=4, **QUICK)
    np.testing.assert_array_equal(a.layers["model_1"], b.layers["model_1"])
    assert not np.array_equal(a.layers["model_1"], c.layers["model_1"])


def test_release13_protocol_selects_models():
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    cd = reconstruct_nucdyn(str(PAIRS), n_models=3, device="cpu", seed=2, protocol="release_1.3",
                            genome_ranges=["chr19"], particle_sizes=[2e6, 5e5], temp_steps=[40],
                            dynamics_steps=[50])
    assert len(cd.layers) == 3
    st = cd.results["nucdyn.stages"]
    # 2 x n_models above 1 Mb, n_models after the selection
    assert list(st["n_models"]) == [6, 3]
    assert ((cd.bins["end"] - cd.bins["start"]) == 500_000).all()


def test_roundtrip_keeps_ensemble(tmp_path):
    from uchrom import ChromData
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    cd = reconstruct_nucdyn(str(PAIRS), n_models=3, device="cpu", seed=1, cell_id="c1", **QUICK)
    out = tmp_path / "nd.chromdata.zarr"
    cd.write(out)
    back = ChromData.read(out, original_order=True)
    assert sorted(back.layers) == sorted(cd.layers)
    np.testing.assert_allclose(back.layers["model_2"], cd.layers["model_2"])
    assert back.uns["nucdyn"]["n_models"] == 3


def test_cli_main_native(tmp_path):
    from uchrom import ChromData
    from uchrom.recon.sc.nucdyn import main

    out = tmp_path / "cell1.cdz"
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)  # native path: no deprecation
        main(str(PAIRS), str(out), arch="cpu", engine="native", n_models=2, genome_ranges=["chr19"],
             size_steps=[1, 0.5], dyns=40, dynamics_steps=50, random_seed=3)
    cd = ChromData.read(out)
    assert len(cd.layers) == 2
    assert cd.uns["nucdyn"]["seed"] == 3
    assert set(cd.spots["cell_id"].astype(str)) == {"cell1"}


def test_contacts_from_dataframe_and_bad_input():
    from uchrom.io import read_pairs
    from uchrom.recon.sc.nucdyn import load_contacts, reconstruct_nucdyn

    df = read_pairs(str(PAIRS))
    c = load_contacts(df, genome_ranges="chr19")
    assert set(c["chrom_a"]) == {"chr19"} and len(c["pos_a"]) > 100
    with pytest.raises(ValueError):
        load_contacts(df, genome_ranges="chrNOPE")
    with pytest.raises(ValueError):
        reconstruct_nucdyn(df, device="tpu")


@pytest.mark.gpu
def test_gpu_matches_cpu_ensemble_statistics():
    if not un.gpu_available():
        pytest.skip("no GPU adapter")
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    kw = dict(n_models=6, seed=4, genome_ranges=["chr19"], particle_sizes=[1e6, 5e5], temp_steps=[100],
              dynamics_steps=[100])
    g = reconstruct_nucdyn(str(PAIRS), device="gpu", **kw)
    c = reconstruct_nucdyn(str(PAIRS), device="cpu", **kw)

    def stats(cd):
        X = np.stack([cd.layers[k] for k in sorted(cd.layers)])
        bb = np.median([np.median(np.linalg.norm(np.diff(x, axis=0), axis=1)) for x in X])
        rg = np.median([np.sqrt(((x - x.mean(0)) ** 2).sum(1).mean()) for x in X])
        return bb, rg

    (bg, rg_g), (bc, rg_c) = stats(g), stats(c)
    assert abs(bg - bc) < 0.1
    assert abs(rg_g - rg_c) / rg_c < 0.15


ROBUST_QUICK = dict(genome_ranges=["chr19"], particle_sizes=[2e6, 4e5, 2e5], temp_steps=[60], dynamics_steps=[50])


def test_robust_protocol_downweights_injected_noise(tmp_path):
    """protocol="robust": random (false) contacts added to chr19 get lower weights than the real ones."""
    import pandas as pd

    from uchrom import ChromData
    from uchrom.io import read_pairs
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    df = read_pairs(str(PAIRS))
    df = df[(df["chr1"] == "chr19") & (df["chr2"] == "chr19")].reset_index(drop=True)
    rng = np.random.default_rng(0)
    lo, hi = int(df[["pos1", "pos2"]].min().min()), int(df[["pos1", "pos2"]].max().max())
    n_noise = len(df) // 5
    noise = df.iloc[:n_noise].copy()
    noise["pos1"] = rng.integers(lo, hi, n_noise)
    noise["pos2"] = rng.integers(lo, hi, n_noise)
    both = pd.concat([df, noise], ignore_index=True)
    cd = reconstruct_nucdyn(both, n_models=4, device="cpu", seed=1, protocol="robust",
                            robust_segments=2, **ROBUST_QUICK)
    w = cd.results["nucdyn.contact_weights"]
    assert w.shape == (len(both),)
    is_noise = np.arange(len(both)) >= len(df)
    ok = np.isfinite(w)
    assert np.nanmean(w[~is_noise & ok]) > np.nanmean(w[is_noise & ok]) + 0.05
    em = cd.results["nucdyn.em"]
    assert {"eps", "s", "mean_w"} <= set(em.columns) and (em["eps"] > 0).all()
    assert cd.uns["nucdyn"]["particle_position"] == "end"
    out = tmp_path / "rb.chromdata.zarr"
    cd.write(out)
    back = ChromData.read(out)
    np.testing.assert_array_equal(back.results["nucdyn.contact_weights"], w)


@pytest.mark.gpu
def test_robust_gpu_matches_cpu_statistics():
    """protocol="robust" (weights, support evidence, no-contact term) on GPU vs CPU: same ensemble statistics
    and contact weights."""
    if not un.gpu_available():
        pytest.skip("no GPU adapter")
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    kw = dict(n_models=6, seed=4, protocol="robust", robust_segments=2, robust_kernel="exp", robust_support_rel=4,
              robust_nc_scale=5, robust_nc_qmax=1, genome_ranges=["chr19"], particle_sizes=[2e6, 4e5, 2e5],
              temp_steps=[100], dynamics_steps=[100])
    g = reconstruct_nucdyn(str(PAIRS), device="gpu", **kw)
    c = reconstruct_nucdyn(str(PAIRS), device="cpu", **kw)

    def stats(cd):
        X = np.stack([cd.layers[k] for k in sorted(cd.layers)])
        bb = np.median([np.median(np.linalg.norm(np.diff(x, axis=0), axis=1)) for x in X])
        rg = np.median([np.sqrt(((x - x.mean(0)) ** 2).sum(1).mean()) for x in X])
        return bb, rg

    (bg, rg_g), (bc, rg_c) = stats(g), stats(c)
    assert abs(bg - bc) < 0.1
    assert abs(rg_g - rg_c) / rg_c < 0.15
    wg, wc = g.results["nucdyn.contact_weights"], c.results["nucdyn.contact_weights"]
    ok = np.isfinite(wg) & np.isfinite(wc)
    assert abs(np.mean(wg[ok]) - np.mean(wc[ok])) < 0.05


def test_robust_without_reweighting_equals_2017():
    """With re-weighting disabled (start stage beyond the schedule) robust is the 2017 protocol, bit for bit."""
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    a = reconstruct_nucdyn(str(PAIRS), n_models=2, device="cpu", seed=3, **ROBUST_QUICK)
    b = reconstruct_nucdyn(str(PAIRS), n_models=2, device="cpu", seed=3, protocol="robust",
                           robust_start_stage=99, robust_refine=0, robust_temp_steps=[], robust_dynamics_steps=[],
                           robust_sample_temp=0.0, robust_merge_below=0.0, **ROBUST_QUICK)
    for k in a.layers:
        np.testing.assert_array_equal(a.layers[k], b.layers[k])


def test_robust_sampling_and_adaptive_resolution():
    """Snapshots multiply the models; merged runs come back on the full particle grid."""
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    kw = dict(n_models=2, device="cpu", seed=2, protocol="robust", genome_ranges=["chr19"],
              particle_sizes=[2e6, 4e5, 1e5], temp_steps=[30], dynamics_steps=[20])
    a = reconstruct_nucdyn(str(PAIRS), **kw)
    b = reconstruct_nucdyn(str(PAIRS), robust_merge_below=2.1e6, robust_sample_temp=1000.0, robust_sample_steps=10,
                           robust_sample_snapshots=3, **kw)
    assert len(b.layers) == 6
    np.testing.assert_array_equal(a.bins[["chrom", "start", "end"]].to_numpy(), b.bins[["chrom", "start", "end"]].to_numpy())
    st = b.results["nucdyn.stages"]
    assert st["n_particles"].iloc[-1] < len(b.bins)  # fewer simulated particles than output loci
    assert np.isfinite(np.stack([b.layers[k] for k in b.layers])).all()
