"""Structure calls against references: loops, boundaries, compartments (incl. Hi-C PC1 on a linked cool),
and the ChromData form of single-allele FISHnet."""
import numpy as np
import pandas as pd
import pytest

from tests._synth import RES, chain_traces, domain_traces


# ---------------------------------------------------------------- loops

def test_match_loops_within_tolerance_and_chromosome():
    from uchrom.strc.loop import match_loops

    ref = pd.DataFrame({"chrom1": ["chr1", "chr1", "chr2"], "start1": [100, 1000, 100], "start2": [500, 2000, 500]},
                       index=[7, 8, 9])
    calls = pd.DataFrame({"chrom1": ["chr1", "chr1"], "start1": [120, 1000], "start2": [480, 2100]})
    out = match_loops(ref, calls, tol=25)
    assert out.index.tolist() == [7, 8, 9]
    assert out.tolist() == [True, False, False]           # 2nd: anchor 100 bp off; 3rd: other chromosome
    no_chrom = ref.drop(columns="chrom1")
    assert match_loops(no_chrom, calls, tol=25).tolist() == [True, False, True]
    assert match_loops(ref, calls, tol=100).tolist() == [True, True, False]


def test_score_loops_planted_loop_is_closer_than_background():
    from uchrom.strc.loop import score_loops

    cd = chain_traces(n_traces=120, n_bins=40, loop=(8, 30))
    loops = pd.DataFrame({"chrom1": ["chr1", "chr1"], "start1": [8 * RES, 2 * RES], "start2": [30 * RES, 24 * RES]})
    s = score_loops(cd, loops)
    assert s["n_traces"].tolist() == [120, 120]
    assert s["n_background"].tolist() == [120 * (40 - 22 - 1)] * 2      # 18 pairs 22 bins apart, minus itself
    assert s["ratio"].iloc[0] < 0.6                       # the planted loop
    assert 0.6 < s["ratio"].iloc[1] < 1.6                 # an ordinary pair
    cd.results.set("loops.test", loops, kind="table", function="test")
    by_key = score_loops(cd, "loops.test", trace_ids=[str(t) for t in range(60)])
    assert by_key["n_traces"].tolist() == [60, 60]
    with pytest.raises(KeyError, match="locus start"):
        score_loops(cd, loops.assign(start1=[8 * RES + 1, 2 * RES]))


# ------------------------------------------------------------ boundaries

def _gapped_cd(n_traces=2):
    """Six 50-bp loci with gaps between them: starts 0, 100, 250, 300, 500, 600."""
    from uchrom import ChromData

    starts = np.array([0, 100, 250, 300, 500, 600])
    spots = pd.DataFrame({"chrom": "chr1", "start": np.tile(starts, n_traces), "end": np.tile(starts + 50, n_traces),
                          "trace_id": np.repeat(np.arange(n_traces), len(starts))})
    return ChromData(np.random.default_rng(0).normal(size=(len(spots), 3)), spots)


def test_tad_boundaries_on_gapped_loci_and_levels():
    from uchrom.strc.tad import tad_boundaries

    cd = _gapped_cd()
    tads = pd.DataFrame({"chrom": "chr1", "start": [0, 250, 500, 0, 500], "end": [150, 350, 650, 350, 650],
                         "level": [1, 1, 1, 2, 2]})
    b = tad_boundaries(cd, tads)                           # level 1: ends and next starts on the same loci
    assert b["bin_index"].tolist() == [2, 4]
    assert b["start"].tolist() == [250, 500]
    assert tad_boundaries(cd, tads, level=2)["bin_index"].tolist() == [4]
    # a gap between two domains (a one-locus segment left out) gives both of its edges
    gap = pd.DataFrame({"chrom": "chr1", "start": [0, 300], "end": [150, 650]})
    assert tad_boundaries(cd, gap)["bin_index"].tolist() == [2, 3]
    cd.results.set("tads.test", tads, kind="table", function="test")
    assert tad_boundaries(cd, "tads.test")["bin_index"].tolist() == [2, 4]


def test_compare_boundaries_and_boundary_frequency():
    from uchrom.strc.tad import boundary_frequency, compare_boundaries, tad_boundaries

    cd = _gapped_cd()
    query = pd.DataFrame({"chrom": "chr1", "start": [0, 250, 500], "end": [150, 350, 650]})        # 2, 4
    ref = pd.DataFrame({"chrom": "chr1", "start": [0, 300], "end": [300, 650]})                    # 3
    out = compare_boundaries(cd, query, ref, tol=1)
    assert out["n_query"] == 2 and out["n_reference"] == 1
    assert out["fraction_near"] == 1.0
    assert out["chance"] == pytest.approx(3 / 6)                   # loci 2, 3, 4 of 6
    assert out["enrichment"] == pytest.approx(2.0)
    assert compare_boundaries(cd, query, ref, tol=0)["fraction_near"] == 0.0

    per_trace = pd.DataFrame({"chrom": "chr1", "trace_id": ["a", "a", "a", "b", "b"],
                              "start": [0, 250, 500, 0, 250], "end": [150, 350, 650, 150, 650]})
    b = tad_boundaries(cd, per_trace)
    assert list(b.columns) == ["chrom", "trace_id", "bin_index", "bin_id", "start"]
    assert b.groupby("trace_id")["bin_index"].apply(list).to_dict() == {"a": [2, 4], "b": [2]}
    f = boundary_frequency(cd, per_trace)
    assert f["frequency"].tolist() == [0, 0, 1.0, 0, 0.5, 0]
    assert (f["n_traces"] == 2).all()
    with pytest.raises(KeyError, match="trace_id"):
        boundary_frequency(cd, query)


# --------------------------------------------------------------- FISHnet

def test_fishnet_trace_on_chromdata_equals_matrix_and_population_rows():
    from uchrom.strc.tad import FISHnetParams, call_domains_fishnet, call_domains_fishnet_trace, trace_seed

    cd = domain_traces(n_traces=3, bounds=(0, 15, 30, 45))
    params = FISHnetParams(n_louvain_runs=3, max_thresholds=20)
    one = call_domains_fishnet_trace(cd, params=params, trace_id="1")
    assert one["distances"].shape == (45, 45) and len(one["loci"]) == 45 and one["trace_id"] == "1"
    xyz = cd.get_trace(1).coords
    assert np.allclose(one["distances"], np.linalg.norm(xyz[:, None] - xyz[None], axis=-1))
    same = call_domains_fishnet_trace(one["distances"], params=params, seed_base=trace_seed("1"))
    assert same["domains"] == one["domains"]

    assert trace_seed("1") == trace_seed(1) and trace_seed("1") != trace_seed("2")
    alone = call_domains_fishnet(cd, chrom="chr1", trace_ids=["1"], params=params, key_added=None)
    together = call_domains_fishnet(cd, chrom="chr1", params=params, key_added=None)
    cols = ["start", "end", "start_bin", "end_bin"]
    picked = together[together["trace_id"].astype(str) == "1"][cols].reset_index(drop=True)
    assert alone[cols].reset_index(drop=True).equals(picked)           # independent of the other traces
    assert [tuple(r) for r in alone[["start_bin", "end_bin"]].to_numpy()] == [tuple(d) for d in one["domains"]]
    with pytest.raises(TypeError, match="trace_id"):
        call_domains_fishnet_trace(cd, params=params)


# ------------------------------------------------------------ compartments

def test_axes_pc_names_a_by_a_bin_track():
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc

    mask = np.zeros(40, bool)
    mask[np.r_[0:10, 20:30]] = True
    cd = chain_traces(n_traces=200, n_bins=40, a_mask=mask)
    cd.bin_tracks = pd.DataFrame({"active": mask.astype(float)}, index=cd.bins.index)
    for track, want in (("active", mask), ):
        comp = call_compartments_axes_pc(cd, params=CompartmentCallerParams(a_track=track), device="cpu")
        called = comp.sort_values("start")["compartment"].to_numpy() == "A"
        assert (called == want).mean() >= 0.75
        a = comp[comp.compartment == "A"]["pc2"].mean()
        assert a > comp[comp.compartment == "B"]["pc2"].mean()
    with pytest.raises(KeyError, match="a_track"):
        call_compartments_axes_pc(cd, params=CompartmentCallerParams(a_track="nope"), device="cpu", key_added=None)


def _checkerboard_cd(tmp_path):
    """24 uneven loci (A/B in blocks of 4), a Hi-C map of them written as a cooler whose bins run from one
    locus to the next after an empty leading bin, linked to a ChromData with a gene track higher in A."""
    import cooler
    from uchrom import ChromData

    rng = np.random.default_rng(0)
    n = 24
    starts = np.cumsum(rng.integers(50, 120, n)) * 1000
    truth = np.repeat([1, 0] * 3, 4).astype(bool)                      # A = True
    sep = np.abs(starts[:, None] - starts[None, :]) / 1e5 + 1
    same = truth[:, None] == truth[None, :]
    counts = np.round(1000 * sep ** -1.0 * np.where(same, 3.0, 1.0) * rng.uniform(0.9, 1.1, (n, n)))
    counts = np.triu(counts) + np.triu(counts, 1).T
    bins = pd.DataFrame({"chrom": "chr1", "start": np.r_[0, starts], "end": np.r_[starts, starts[-1] + 50_000]})
    i, j = np.triu_indices(n)
    pixels = pd.DataFrame({"bin1_id": i + 1, "bin2_id": j + 1, "count": counts[i, j].astype(np.int64)})
    path = tmp_path / "toy.cool"
    cooler.create_cooler(str(path), bins, pixels)
    spots = pd.DataFrame({"chrom": "chr1", "start": np.tile(starts, 2), "end": np.tile(starts + 50_000, 2),
                          "trace_id": np.repeat([0, 1], n)})
    cd = ChromData(rng.normal(size=(2 * n, 3)), spots)
    cd.bin_tracks = pd.DataFrame({"genes": np.where(truth, 2.0, 0.0)}, index=cd.bins.index)
    cd.link_cool(path, key="hic")
    return cd, truth, counts, starts


def test_call_compartments_hic_recovers_a_checkerboard(tmp_path):
    from uchrom.strc.comp import call_compartments_hic, compare_compartments, hic_compartment_pc1

    cd, truth, counts, starts = _checkerboard_cd(tmp_path)
    table = call_compartments_hic(cd, contacts="hic", orient_by="genes")
    assert len(table) == 24 and table["bin_index"].tolist() == list(range(1, 25))      # empty bin 0 left out
    assert ((table["compartment"] == "A").to_numpy() == truth).all()
    assert np.allclose(table["pc1"], hic_compartment_pc1(counts, starts, marker=truth.astype(float)))
    assert len(cd.intervals["compartments.hic_pc1"]) == 6
    track = cd.bin_tracks["compartments.hic_pc1.pc1"].to_numpy()
    assert np.allclose(track, table["pc1"].to_numpy())                 # one locus per Hi-C bin
    flipped = call_compartments_hic(cd, contacts="hic", key_added=None)
    assert abs(np.corrcoef(flipped["pc1"], table["pc1"])[0, 1]) == pytest.approx(1.0)

    query = table.assign(compartment=np.where(np.arange(24) < 2, "B", table["compartment"]), pc2=table["pc1"])
    query = query.drop(columns="pc1")
    out = compare_compartments(cd, query, "compartments.hic_pc1")
    assert out["n_bins"] == 24
    assert out["agreement"] == pytest.approx(22 / 24)
    assert out["pearson_r"] == pytest.approx(1.0)
    new = call_compartments_hic(cd, contacts="hic", orient_by="genes", key_added="c.copy", copy=True)
    assert "c.copy" in new.results and "c.copy" not in cd.results
    assert "c.copy.pc1" in new.bin_tracks.columns
    with pytest.raises(KeyError, match="orient_by"):
        call_compartments_hic(cd, contacts="hic", orient_by="nope")
