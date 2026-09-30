"""uchrom.recon.bulk.deconv (method "igm") on the native engine.

Synthetic data only (correctness of the pipeline); real-data validation is
in benchmarks/bulk/.  Skipped when the native engine with the igm protocol
is not installed.
"""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("scipy")
import scipy.sparse as sp  # noqa: E402

from uchrom.recon.bulk.deconv import IgmParams, deconvolve  # noqa: E402
from uchrom.recon.bulk.deconv.igm import contact_probabilities, native_available  # noqa: E402

pytestmark = pytest.mark.skipif(not native_available(), reason="uchrom_nucdyn with the igm protocol not installed")

N_PER = 50


def _bins(n=N_PER):
    b = pd.DataFrame({"chrom": ["chr1"] * n + ["chr2"] * n,
                      "start": np.r_[np.arange(n), np.arange(n)] * 1_000_000})
    b["end"] = b["start"] + 1_000_000
    return b


def _designed_matrix(bins):
    """Neighbours 1, 10-bead domains at 0.3, one inter-chromosomal block at 0.1."""
    n = len(bins)
    half = n // 2
    D = np.zeros((n, n))
    chrom = bins["chrom"].to_numpy()
    for i in range(n - 1):
        if chrom[i] == chrom[i + 1]:
            D[i, i + 1] = 1.0
    for c in (0, half):
        for a in range(0, half, 10):
            for i in range(c + a, c + a + 10):
                for j in range(i + 2, c + a + 10):
                    D[i, j] = 0.3
    D[10:15, half + 30:half + 35] = 0.1
    return D


def _params(s, scale=0.1, **kw):
    stages = [dict(st, mdsteps=max(1, int(st["mdsteps"] * scale))) for st in IgmParams().stages]
    base = dict(n_structures=s, nucleus_radius=2000.0, stages=stages,
                relax=dict(mdsteps=int(500 * scale), temperature=1.0, max_velocity=10.0),
                intra_sigma_list=[1.0, 0.2, 0.1, 0.05], inter_sigma_list=[1.0, 0.2, 0.1, 0.05],
                max_iterations=3)
    base.update(kw)
    return IgmParams(**base)


def test_output_layout():
    bins = _bins(20)
    D = _designed_matrix(bins)
    cd = deconvolve(sp.csr_matrix(D), bins=bins, params=_params(6, scale=0.02, intra_sigma_list=[1.0],
                                                                   inter_sigma_list=[1.0]),
                    device="cpu", seed=3, keep_intermediate=True)
    assert len(cd.cells) == 6
    assert len(cd.traces) == 6 * 4                      # 2 chromosomes x 2 copies
    assert len(cd.spots) == 6 * 2 * len(bins)
    assert set(cd.traces["copy"]) == {0, 1}
    one = cd.get_cell("s00000")
    assert len(one.spots) == 2 * len(bins)
    assert (cd.bin_tracks["radius_nm"] > 0).all()
    u = cd.uns["deconv"]
    assert u["method"] == "igm" and u["n_structures"] == 6
    assert [r["round"] for r in u["rounds"]] == [1]
    # relaxed start (round 0) and round 1 kept as layers
    assert set(cd.layers) == {"round_00", "round_01"}
    assert np.allclose(cd.layers["round_01"], cd.coords, atol=1e-3)
    act = cd.results["deconv.igm"]
    assert {"bin_i", "bin_j", "p", "d_act_nm"} <= set(act.columns)
    # all structures inside the (reduced) nucleus up to the envelope tolerance
    r = np.linalg.norm(cd.coords, axis=1)
    assert r.max() < 2000.0 * 1.1


def test_streamed_output(tmp_path):
    bins = _bins(20)
    D = _designed_matrix(bins)
    out = tmp_path / "pop.chromdata.zarr"
    cd = deconvolve(sp.csr_matrix(D), bins=bins, params=_params(5, scale=0.02, intra_sigma_list=[1.0],
                                                                   inter_sigma_list=[1.0]),
                    device="cpu", seed=3, out=out)
    assert cd.backed
    assert len(cd.cells) == 5
    mem = deconvolve(sp.csr_matrix(D), bins=bins, params=_params(5, scale=0.02, intra_sigma_list=[1.0],
                                                                    inter_sigma_list=[1.0]),
                     device="cpu", seed=3)
    a = cd.get_cell("s00003")
    b = mem.get_cell("s00003")
    ka = a.spots_with_loci().assign(x=a.coords[:, 0], t=lambda d: d["trace_id"].astype(str)).sort_values(["t", "start"])
    kb = b.spots_with_loci().assign(x=b.coords[:, 0], t=lambda d: d["trace_id"].astype(str)).sort_values(["t", "start"])
    assert np.allclose(ka["x"].to_numpy(), kb["x"].to_numpy())


def test_synthetic_end_to_end_reproduces_input():
    """Truth population from a designed matrix; its contact probabilities
    are the input of a second run (other seed); the second population must
    reproduce them.  2 chromosomes x 50 bins, diploid, 200 structures."""
    bins = _bins()
    D = _designed_matrix(bins)
    truth = deconvolve(sp.csr_matrix(D), bins=bins, params=_params(200), device="cpu", seed=1)
    F = contact_probabilities(truth)
    iu = np.triu_indices(len(bins), 1)
    F_in = np.where(F >= 0.01, F, 0.0)
    rec = deconvolve(sp.csr_matrix(np.triu(F_in, 1)), bins=bins, params=_params(200), device="auto", seed=2)
    R = contact_probabilities(rec)
    f, r = F[iu], R[iu]
    sel = f >= 0.05                                           # restrained at the last sigma
    pear = np.corrcoef(f[sel], r[sel])[0, 1]
    mae = np.abs(f[sel] - r[sel]).mean()
    print(f"pairs >= 0.05: {sel.sum()}, Pearson {pear:.3f}, MAE {mae:.3f}; "
          f"all pairs Pearson {np.corrcoef(f, r)[0, 1]:.3f}")
    assert sel.sum() > 300
    assert pear > 0.95
    assert mae < 0.05
    # final violation score of the fit
    assert rec.uns["deconv"]["rounds"][-1]["violation_score"] < 0.05


def test_python_defaults_match_native():
    import uchrom_nucdyn

    native = uchrom_nucdyn.default_igm_params()
    ours = IgmParams().to_native()
    for k, v in native.items():
        if k in ("seed", "device"):
            continue
        assert ours[k] == v, k


def test_unknown_method_and_inputs():
    bins = _bins(5)
    with pytest.raises(ValueError):
        deconvolve(np.eye(10), bins=bins, method="nope")
    with pytest.raises(ValueError):
        deconvolve(np.eye(10))                       # no bins
    with pytest.raises(TypeError):
        deconvolve(np.eye(10), bins=bins, not_a_param=1)
