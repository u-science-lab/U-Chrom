"""Structure callers on synthetic data with a planted answer."""
import numpy as np
import pytest
import torch

from tests._synth import RES, block_contact_matrix, chain_traces, domain_traces


def _near(found, expected, tol=1):
    return all(any(abs(f - e) <= tol for f in found) for e in expected)


# ---------------------------------------------------------------- TADs

def test_directionality_index_recovers_block_boundaries():
    from uchrom.strc.tad import get_domains

    mat = torch.as_tensor(block_contact_matrix((30, 30, 30)))
    domains = get_domains(mat, window=10, smoothing_param=0.03, device="cpu")
    starts = [s for s, _ in domains]
    assert _near(starts, [30, 60], tol=3), domains


def test_call_tads_by_pval_recovers_planted_boundaries():
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval
    from uchrom.strc.tad.arc_pval import arcfish_boundary_stats

    cd = domain_traces(n_traces=150, bounds=(0, 15, 30, 45))
    params = TADCallerParams(window_bp=1.5e5)
    tads = call_tads_by_pval(cd, "chr1", params=params, device="cpu")
    assert cd.results["tads"] is tads
    assert {"chrom", "start", "end", "level", "start1", "end1", "start2", "end2", "stat1", "stat2"} <= set(tads.columns)
    top = tads[tads["level"] == 0]                               # the finest partition
    boundary_bins = sorted(set(top["start"] // RES) - {0})
    assert _near(boundary_bins, [15, 30], tol=1), top
    assert (top["end"].to_numpy()[:-1] == top["start"].to_numpy()[1:]).all()      # level 0 tiles the loci
    st = arcfish_boundary_stats(cd, chrom="chr1", params=params, device="cpu")
    assert sorted(st.loc[st["peak"], "start"] // RES) == boundary_bins
    assert (st.loc[st["peak"], "fdr"] < 0.1).all()
    # hierarchy: removing the interior boundaries one at a time adds one merged domain each, up to the whole region
    assert len(tads) == 2 * len(top) - 1
    last = tads[tads["level"] == tads["level"].max()].iloc[0]
    assert (last["start"], last["end"]) == (top["start"].min(), top["end"].max())


def test_call_tads_by_pval_store_false_leaves_results_untouched():
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval

    cd = domain_traces(n_traces=60)
    call_tads_by_pval(
        cd, "chr1", params=TADCallerParams(window_bp=1.5e5), device="cpu",
        store=False,
    )
    assert "tads" not in cd.results


def test_fishnet_recovers_per_trace_domains():
    from uchrom.strc.tad import FISHnetParams, call_domains_fishnet

    cd = domain_traces(n_traces=3, bounds=(0, 15, 30, 45))
    params = FISHnetParams(n_louvain_runs=3, max_thresholds=20)
    doms = call_domains_fishnet(cd, "chr1", params=params)
    assert "fishnet_domains" in cd.results
    assert set(doms["trace_id"].astype(int)) == {0, 1, 2}
    # at least 2 of the 3 traces find both planted boundaries
    hits = 0
    for _, g in doms.groupby("trace_id", observed=True):
        hits += _near(sorted(set(g["start_bin"]) - {0}), [15, 30], tol=2)
    assert hits >= 2, doms


# ---------------------------------------------------------------- loops

def test_axiswise_f_recovers_planted_loop():
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.loop.axiswise_f import arcfish_loop_matrices

    cd = chain_traces(n_traces=200, n_bins=40, loop=(8, 30))
    loops = call_loops_axiswise_f(cd, "chr1", device="cpu")
    assert cd.results["loops"] is loops
    assert len(loops) >= 1
    # the planted pair's neighbourhood belongs to a called loop's cluster (the summit is the cluster's smallest p;
    # with p-values saturated at 0, the first in row-major order, as the authors' code picks it)
    m = arcfish_loop_matrices(cd, chrom="chr1", device="cpu")
    called = {m["label"][i, j] for i, j in zip(loops["summit_i"], loops["summit_j"])}
    near = m["label"][7:10, 29:32]
    assert any(v in called for v in near[np.isfinite(near)])
    assert all(abs(i - 8) <= 4 and abs(j - 30) <= 4 for i, j in zip(loops["summit_i"], loops["summit_j"]))


def test_axiswise_f_no_loop_on_plain_chain():
    from uchrom.strc.loop import call_loops_axiswise_f

    cd = chain_traces(n_traces=200, n_bins=40, seed=1)
    loops = call_loops_axiswise_f(cd, "chr1", device="cpu")
    assert len(loops) == 0


# ---------------------------------------------------------- compartments

def test_axes_pc_separates_planted_compartments():
    from uchrom.strc.comp import call_compartments_axes_pc

    mask = np.zeros(40, bool)
    mask[np.r_[0:10, 20:30]] = True
    cd = chain_traces(n_traces=200, n_bins=40, a_mask=mask)
    comp = call_compartments_axes_pc(cd, "chr1", device="cpu")
    assert "compartments" in cd.results
    assert len(comp) == 40
    assert set(comp["compartment"]) <= {"A", "B"}
    called = comp["compartment"].to_numpy() == "A"
    agreement = max((called == mask).mean(), (called != mask).mean())
    assert agreement >= 0.75, agreement
