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


# ---------------------------------------------------------------- IGM-Plus / IGM_2.0 options

def _regression_case():
    """Small fixed-seed case; its reference outputs were recorded before the
    IGM-Plus options were added (macOS arm64, CPU f64)."""
    n = 20
    bins = pd.DataFrame({"chrom": ["chr1"] * n + ["chr2"] * n,
                         "start": np.r_[np.arange(n), np.arange(n)] * 1_000_000})
    bins["end"] = bins["start"] + 1_000_000
    D = np.zeros((2 * n, 2 * n))
    for i in range(2 * n - 1):
        if i != n - 1:
            D[i, i + 1] = 1.0
    for c in (0, n):
        for a in range(0, n, 10):
            for i in range(c + a, c + a + 10):
                for j in range(i + 2, c + a + 10):
                    D[i, j] = 0.3
    D[3:6, n + 10:n + 13] = 0.1
    stages = [dict(st, mdsteps=max(1, int(st["mdsteps"] * 0.02))) for st in IgmParams().stages]
    p = IgmParams(n_structures=8, nucleus_radius=2000.0, stages=stages,
                  relax=dict(mdsteps=10, temperature=1.0, max_velocity=10.0),
                  intra_sigma_list=[1.0, 0.1], inter_sigma_list=[1.0, 0.1], max_iterations=2)
    return bins, sp.csr_matrix(D), p


def test_default_run_unchanged_by_the_options():
    """The faithful IGM 1.0 defaults stay bit-identical on the CPU (hashes of
    the population, the last A-step and the per-structure statistics)."""
    import hashlib
    import platform

    bins, P, p = _regression_case()
    cd = deconvolve(P, bins=bins, params=p, device="cpu", seed=5)
    h = lambda a: hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()  # noqa: E731
    got = (h(np.asarray(cd.coords)), h(cd.results["deconv.igm"][["p", "d_act_nm"]].to_numpy()),
           h(cd.cells[["violation_score", "n_hic_restraints", "energy"]].to_numpy()))
    assert [r["violation_score"] for r in cd.uns["deconv"]["rounds"]] == [0.0, 0.0]
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        pytest.skip("reference hashes recorded on macOS arm64 (libm rounding may differ elsewhere)")
    assert got == ("a343172af3e02560ad215901e016a44c63f9f4522282fbd8f91f967312dded30",
                   "58f294080a62c037b74af3a75a8fbdb090bbcac5df645324986143e6291a7e00",
                   "93487c6d0d04babe303f1118785ae8310121edfd0f75a0528d84654d4b6796dc")


def test_explicit_defaults_equal_implicit():
    """Setting every new option to its default value changes nothing."""
    bins, P, p = _regression_case()
    a = deconvolve(P, bins=bins, params=p, device="cpu", seed=5)
    q = p.replace(occupancy=0.2, occupancy_scope="model", iterative_correction=True,
                  assignment_pooling="igm", init_noise=0.0)
    b = deconvolve(P, bins=bins, params=q, device="cpu", seed=5, init_positions=None)
    assert np.array_equal(np.asarray(a.coords), np.asarray(b.coords))


def test_bead_radius_exclusive_with_occupancy():
    assert IgmParams().effective_occupancy == 0.2
    with pytest.raises(ValueError, match="mutually exclusive"):
        IgmParams(bead_radius=150.0, occupancy=0.3)
    q = IgmParams(occupancy=0.3).replace(bead_radius=150.0)        # replace drops the occupancy
    assert q.occupancy is None and q.to_native()["occupancy"] == 0.0 and q.to_native()["bead_radius"] == 150.0
    assert IgmParams.boninsegna2022(bead_radius=100.0).bead_radius == 100.0
    bins, P, p = _regression_case()
    cd = deconvolve(P, bins=bins, params=p, device="cpu", seed=5, bead_radius=90.0)
    assert np.allclose(cd.bin_tracks["radius_nm"], 90.0)
    assert cd.uns["deconv"]["params"]["bead_radius"] == 90.0
    assert cd.uns["deconv"]["params"]["occupancy"] == 0.0


def test_single_chromosome_models_and_occupancy_scope():
    bins, P, p = _regression_case()
    whole = deconvolve(P, bins=bins, params=p.replace(n_structures=2, intra_sigma_list=[1.0],
                                                      inter_sigma_list=[1.0]), device="cpu", seed=1)
    r_whole = whole.bin_tracks["radius_nm"].to_numpy()[:20]
    q = p.replace(n_structures=3, intra_sigma_list=[1.0], inter_sigma_list=[1.0])
    # IGM-Plus: the modelled chromosome alone fills the occupancy -> larger beads
    one = deconvolve(P, bins=bins, chrom="chr1", params=q, device="cpu", seed=1)
    assert len(one.bins) == 20 and set(one.traces["chrom"]) == {"chr1"}
    assert len(one.traces) == 3 * 2                                   # diploid by default
    assert np.allclose(one.bin_tracks["radius_nm"], r_whole * 2 ** (1 / 3))
    # whole-genome bead sizes
    g = deconvolve(P, bins=bins, chrom="chr1", params=q.replace(occupancy_scope="genome"), device="cpu", seed=1)
    assert np.allclose(g.bin_tracks["radius_nm"], r_whole)
    assert g.uns["deconv"]["params"]["occupancy_total_bp"] == 2 * 40 * 1_000_000
    # haploid single chromosome
    h = deconvolve(P, bins=bins, chrom="chr1", params=q.replace(ploidy="haploid"), device="cpu", seed=1)
    assert len(h.traces) == 3 and set(h.traces["copy"]) == {0}
    assert (np.linalg.norm(h.coords, axis=1) < 2000.0 * 1.1).all()   # the full nucleus envelope
    with pytest.raises(ValueError):
        IgmParams(occupancy_scope="cell")


def test_astep_options_iterative_correction_and_gp_pooling():
    bins, P, p = _regression_case()
    q = p.replace(intra_sigma_list=[0.1], inter_sigma_list=[0.1], max_iterations=2)
    base = deconvolve(P, bins=bins, params=q, device="cpu", seed=5)
    noic = deconvolve(P, bins=bins, params=q.replace(iterative_correction=False), device="cpu", seed=5)
    act = noic.results["deconv.igm"]
    assert np.array_equal(act["p"].to_numpy(), act["f"].to_numpy())      # p = f without the correction
    gp = deconvolve(P, bins=bins, params=q.replace(assignment_pooling="gp"), device="cpu", seed=5)
    a0, a1 = base.results["deconv.igm"], gp.results["deconv.igm"]
    assert len(a0) == len(a1)
    assert not np.array_equal(a0["p_now"].to_numpy(), a1["p_now"].to_numpy())
    assert gp.uns["deconv"]["params"]["assignment_pooling"] == "gp"
    with pytest.raises(ValueError):
        IgmParams(assignment_pooling="pgs")


def test_init_positions_pin_and_interpolate():
    bins, P, _ = _regression_case()
    # (almost) no dynamics: one MD step at T = 1, one CG step, so round 0 ~ the start
    q = IgmParams(n_structures=3, nucleus_radius=2000.0, relax=None,
                  stages=[dict(mdsteps=1, tstart=1.0, tstop=1.0, evfactor=1.0, envelope_factor=1.0)],
                  cg_max_iter=1, cg_max_eval=1, intra_sigma_list=[1.0], inter_sigma_list=[1.0], max_iterations=1)
    pins = pd.DataFrame({"structure": ["s00001", "s00001", 1], "chrom": ["chr1", "chr1", "chr2"],
                         "start": [2_000_000, 6_500_000, 0], "copy": [0, 0, 1],
                         "x": [0.0, 800.0, -500.0], "y": [0.0, 0.0, 300.0], "z": [0.0, 0.0, 0.0]})
    cd = deconvolve(P, bins=bins, params=q, device="cpu", seed=2, keep_intermediate=True,
                    init_positions=pins)
    assert "round_00" in cd.layers
    s1 = cd.get_cell("s00001")
    loc = s1.spots_with_loci()
    start = np.asarray(s1.layers["round_00"])
    tr = loc["trace_id"].astype(str).to_numpy()

    def at(chrom, bin_start, copy):
        k = np.flatnonzero((loc["chrom"].astype(str).to_numpy() == chrom) & (loc["start"].to_numpy() == bin_start)
                           & (np.char.endswith(tr.astype(str), f":{copy}")))
        assert len(k) == 1
        return start[k[0]]

    assert np.linalg.norm(at("chr1", 2_000_000, 0) - [0, 0, 0]) < 60
    assert np.linalg.norm(at("chr1", 6_000_000, 0) - [800, 0, 0]) < 60
    assert np.linalg.norm(at("chr1", 4_000_000, 0) - [400, 0, 0]) < 60   # interpolated
    assert np.linalg.norm(at("chr2", 0, 1) - [-500, 300, 0]) < 60
    assert cd.uns["deconv"]["params"]["init_positions"] == {"n_loci": 3, "n_structures": 1}
    with pytest.raises(ValueError, match="outside the bins"):
        deconvolve(P, bins=bins, params=q, device="cpu", init_positions=pins.assign(start=[99_000_000, 0, 0]))
    with pytest.raises(ValueError, match="structure"):
        deconvolve(P, bins=bins, params=q, device="cpu", init_positions=pins.assign(structure=[7, 7, 7]))


def test_violation_reports():
    bins, P, p = _regression_case()
    cd = deconvolve(P, bins=bins, params=p, device="cpu", seed=5)
    u = cd.uns["deconv"]
    ri = u["relax_init"]
    assert ri["round"] == 0 and [b["kind"] for b in ri["breakdown"]] == ["hic_intra", "hic_inter", "polymer", "envelope"]
    last = u["rounds"][-1]
    assert sum(b["imposed"] for b in last["breakdown"]) == sum(
        last["violations"][k] for k in ("hic_imposed", "poly_imposed", "env_imposed"))
    inter = next(b for b in last["breakdown"] if b["kind"] == "hic_inter")
    assert inter["imposed"] == int(cd.cells["hic_inter_imposed"].sum()) > 0
    assert (cd.cells["hic_inter_imposed"] <= cd.cells["hic_imposed"]).all()
