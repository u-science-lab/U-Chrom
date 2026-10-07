"""uchrom.recon.bulk.deconv (method "ember_pop") on the native engine.

Synthetic data only (the pipeline and the options reach the engine); the real-data development
and the pre-registered test are in benchmarks/bulk/ (PREREG_POP.md, POP_DEVLOG.md).  Skipped when
the native engine with the igm protocol is not installed.
"""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("scipy")

from uchrom.recon.bulk.deconv import IgmParams, deconvolve  # noqa: E402
from uchrom.recon.bulk.deconv.ember_pop import ember_pop_params, gyration_sds  # noqa: E402
from uchrom.recon.bulk.deconv.igm import native_available  # noqa: E402

pytestmark = pytest.mark.skipif(not native_available(), reason="uchrom_recon with the igm protocol not installed")


def _bins(n=20):
    b = pd.DataFrame({"chrom": ["chr1"] * n + ["chr2"] * n, "start": np.r_[np.arange(n), np.arange(n)] * 1_000_000})
    b["end"] = b["start"] + 1_000_000
    return b


def _matrix(bins):
    n = len(bins)
    D = np.zeros((n, n))
    chrom = bins["chrom"].to_numpy()
    for i in range(n - 1):
        if chrom[i] == chrom[i + 1]:
            D[i, i + 1] = 1.0
        for j in range(i + 2, min(n, i + 5)):
            if chrom[i] == chrom[j]:
                D[i, j] = 0.3
    D[2:5, n // 2 + 3:n // 2 + 6] = 0.1
    return D


def _imaged_nuclei(n_cells=6, seed=0):
    """A ChromData of flat 'nuclei' (random points in ellipsoids of different sizes)."""
    from chromdata import ChromData
    rng = np.random.default_rng(seed)
    rows, xyz = [], []
    for c in range(n_cells):
        ax = np.array([3000.0, 1500.0, 400.0]) * (1 + 0.2 * rng.normal())
        u = rng.normal(size=(200, 3))
        u /= np.linalg.norm(u, axis=1)[:, None]
        xyz.append(u * (rng.random(200) ** (1 / 3))[:, None] * ax)
        rows += [("chr1", k * 100_000, k * 100_000 + 50_000, f"c{c}", f"c{c}") for k in range(200)]
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    return ChromData(np.concatenate(xyz), spots)


def _short(p: IgmParams) -> IgmParams:
    stages = [dict(st, mdsteps=max(1, int(st["mdsteps"] * 0.02))) for st in p.stages]
    return p.replace(stages=stages, relax=dict(mdsteps=10, temperature=1.0, max_velocity=10.0),
                     intra_sigma_list=[1.0, 0.2, 0.1], inter_sigma_list=[1.0, 0.2, 0.1], max_iterations=2)


def test_gyration_sds_and_params():
    nuc = _imaged_nuclei()
    sd = gyration_sds(nuc)
    assert sd.shape == (6, 3) and (np.diff(sd, axis=1) <= 0).all()
    assert np.allclose(np.median(sd[:, 0] / sd[:, 2]), 7.5, rtol=0.25)      # flat
    assert np.allclose(gyration_sds([100.0, 300.0, 200.0]), [[300.0, 200.0, 100.0]])
    p = ember_pop_params(nuc, n_structures=10, seed=3)
    assert p.nucleus_shape == "none" and p.noncontact_kspring > 0
    assert p.noncontact_from_sigma == len(p.intra_sigma_list) - 1
    assert p.gyration_targets == [] and p.max_iterations == 5
    pc = ember_pop_params(nuc, n_structures=10, seed=3, per_cell=True)
    assert len(pc.gyration_targets) == 10 and all(t in sd.tolist() for t in pc.gyration_targets)
    assert np.allclose(p.gyration_prior, np.median(sd, axis=0))
    assert ember_pop_params(nuc, 10, seed=3, per_cell=True).gyration_targets == pc.gyration_targets
    with pytest.raises(ValueError):
        gyration_sds([[1.0, 2.0]])


def test_ember_pop_runs_without_envelope():
    bins = _bins()
    D = _matrix(bins)
    nuc = _imaged_nuclei()
    cd = deconvolve(D, bins=bins, method="ember_pop", nucleus=nuc, n_structures=6, device="cpu",
                    params=_short(IgmParams(n_threads=2)), seed=1)
    d = cd.uns["deconv"]
    assert d["method"] == "ember_pop" and d["params"]["nucleus_shape"] == "none"
    assert d["params"]["gyration_targets"] == [] and d["params"]["gyration_kspring"] == 0.1
    assert cd.cells.shape[0] == 6 and int(cd.cells["env_imposed"].sum()) == 0
    X = np.asarray(cd.coords).reshape(6, -1, 3)
    assert np.isfinite(X).all()
    # the gyration prior pulls the structures towards the imaged (flat) shape
    sd = np.array([np.sqrt(np.sort(np.linalg.eigvalsh(np.cov(x.T, bias=True)))[::-1]) for x in X])
    assert np.median(sd[:, 0] / sd[:, 2]) > 2.0
    assert "deconv.ember_pop" in cd.results
