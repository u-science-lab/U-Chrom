"""uchrom.strc.comp.eig: cis eigenvector compartments (cooltools eigs_cis formulation) and saddle strength,
on synthetic maps with planted A/B compartments, against dense re-implementations of the published
procedure."""

import gzip

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

RES = 10_000


def _labels(n, block=12, seed=1):
    """A/B truth in blocks of uneven size (True = A)."""
    rng = np.random.default_rng(seed)
    sizes = rng.integers(block // 2, block * 2, n)
    lab = np.repeat(np.arange(len(sizes)) % 2 == 0, sizes)[:n]
    return lab


def _planted(n=160, *, chroms=("chr1",), fold=2.0, scale=300.0, masked=(), seed=0, labels=None):
    """Pixels of maps with compartments: contacts ~ scale / (1 + d) times ``fold`` between bins of the same
    compartment (``1 / fold`` between A and B); ``masked`` bins empty.  Returns bins, pixels, truth."""
    rng = np.random.default_rng(seed)
    truth = _labels(n) if labels is None else np.asarray(labels, bool)
    i, j = np.triu_indices(n)
    same = truth[i] == truth[j]
    lam = scale / (1.0 + (j - i)) * np.where(same, fold, 1.0 / fold)
    bins, pix = [], []
    for k, c in enumerate(chroms):
        cnt = rng.poisson(lam)
        cnt[np.isin(i, masked) | np.isin(j, masked)] = 0
        keep = cnt > 0
        bins.append(pd.DataFrame({"chrom": c, "start": np.arange(n) * RES, "end": np.arange(1, n + 1) * RES}))
        pix.append(pd.DataFrame({"bin1_id": i[keep] + k * n, "bin2_id": j[keep] + k * n, "count": cnt[keep]}))
    return pd.concat(bins, ignore_index=True), pd.concat(pix, ignore_index=True), truth


def _cool(tmp_path, bins, pix, name="m.cool", balance=True):
    path = tmp_path / name
    cooler.create_cooler(str(path), bins, pix, ordered=True)
    if balance:
        cooler.balance_cooler(cooler.Cooler(str(path)), store=True, cis_only=True)
    return path


def _chromdata(path, key="hic"):
    from uchrom import ChromData

    spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str)]})
    cd = ChromData(np.zeros((0, 3)), spots)
    cd.link_cool(str(path), key=key)
    return cd


# ---------------------------------------------------------------- dense references (the published steps)


def _dense_cis_eig(A, n_eigs=3, ignore_diags=2, clip_percentile=99.9, ratio=1.03):  # ratio None: per diagonal
    """cooltools ``cis_eig`` written out densely: ignored diagonals set to 1, log-binned O/E over the
    valid pixels, clipping, eigenvectors of O/E - 1 (largest |eigenvalue|), scaled by sqrt(|eigenvalue|)."""
    A = np.array(A, dtype=float)
    A[~np.isfinite(A)] = 0
    mask = A.sum(axis=0) > 0
    N = len(A)
    for d in range(-ignore_diags + 1, ignore_diags):
        idx = np.arange(N - abs(d))
        A[idx + max(-d, 0), idx + max(d, 0)] = 1.0
    if ratio is None:
        edges = np.arange(N + 1)
    else:
        num = int(np.log(N) / np.log(ratio))
        edges = np.r_[0, np.unique(np.rint(10 ** np.linspace(0, np.log10(N), num))).astype(int)]
    OE = A.copy()
    sep = np.abs(np.subtract.outer(np.arange(N), np.arange(N)))
    good = np.outer(mask, mask)
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (sep >= lo) & (sep < hi) & good
        upper = sel & (np.subtract.outer(np.arange(N), np.arange(N)) <= 0)
        if upper.sum() and A[upper].mean() != 0:
            OE[sel] = A[sel] / A[upper].mean()
    thr = np.percentile(OE[mask][:, mask], clip_percentile)
    OE = np.clip(OE, 0, thr) - 1.0
    M = OE[mask][:, mask]
    w, V = np.linalg.eigh(M)
    order = np.argsort(-np.abs(w))[:n_eigs]
    vecs = np.full((n_eigs, N), np.nan)
    vecs[:, mask] = (V[:, order] / np.linalg.norm(V[:, order], axis=0) * np.sqrt(np.abs(w[order]))).T
    return w[order], vecs


def _dense_saddle(A, track, n_groups, qrange=(0.025, 0.975), min_diag=3):
    """cooltools ``saddle`` (cis) written out densely on one chromosome."""
    A = np.array(A, dtype=float)
    N = len(A)
    valid = np.isfinite(A).sum(axis=0) > 0
    exp = np.array([np.nanmean(np.diagonal(A, d)[valid[: N - d] & valid[d:]]) if (valid[: N - d] & valid[d:]).any()
                    else np.nan for d in range(N)])
    sep = np.abs(np.subtract.outer(np.arange(N), np.arange(N)))
    with np.errstate(invalid="ignore", divide="ignore"):
        OE = A / exp[sep]
    OE[sep < min_diag] = np.nan
    t = np.where(valid, track, np.nan)
    edges = np.nanpercentile(t, np.linspace(qrange[0], qrange[1], n_groups + 1) * 100)
    g = np.where(np.isfinite(t), np.digitize(np.nan_to_num(t), edges), -1)
    G = n_groups + 2
    S, C = np.zeros((G, G)), np.zeros((G, G))
    for a in range(G):
        for b in range(G):
            block = OE[g == a][:, g == b]
            S[a, b] = np.nansum(block)
            C[a, b] = np.isfinite(block).sum()
    return S + S.T, C + C.T


# ---------------------------------------------------------------- the eigen core


@pytest.mark.parametrize("n, masked", [(160, (5, 6, 77)), (300, (0, 150, 151))])
def test_cis_eigs_equals_the_dense_procedure(tmp_path, n, masked):
    """n = 160: dense eigensolver; n = 300 (> 256 valid bins): sparse Lanczos on O/E - 1."""
    from uchrom.fea.band import read_band
    from uchrom.strc.comp.eig import cis_eigs

    bins, pix, _ = _planted(n, masked=masked, scale=60.0)
    clr = cooler.Cooler(str(_cool(tmp_path, bins, pix)))
    A = clr.matrix(balance=True).fetch("chr1")
    band = read_band(clr, chrom="chr1")
    for ig, clip, ratio in ((2, 99.9, 1.03), (0, 99.0, 1.03), (3, 0, 1.0)):
        w, V = cis_eigs(band, n_eigs=3, ignore_diags=ig, clip_percentile=clip, dist_bin_ratio=ratio)
        ref_w, ref_V = _dense_cis_eig(A, 3, ig, clip or 100, None if ratio == 1.0 else ratio)
        np.testing.assert_allclose(w, ref_w, rtol=1e-8)
        assert np.array_equal(np.isfinite(V), np.isfinite(ref_V))
        for k in range(3):
            ok = np.isfinite(V[k])
            sign = np.sign(V[k][ok] @ ref_V[k][ok])
            np.testing.assert_allclose(V[k][ok] * sign, ref_V[k][ok], atol=1e-8)
    # a region: the same as decomposing the sub-matrix
    w, V = cis_eigs(band, lo=40, hi=130, n_eigs=2)
    ref_w, _ = _dense_cis_eig(A[40:130, 40:130], 2)
    np.testing.assert_allclose(w, ref_w, rtol=1e-8)
    assert V.shape == (2, 90)


def test_cis_eigs_small_region_is_nan(tmp_path):
    from uchrom.fea.band import read_band
    from uchrom.strc.comp.eig import cis_eigs

    bins, pix, _ = _planted(40)
    band = read_band(cooler.Cooler(str(_cool(tmp_path, bins, pix))), chrom="chr1")
    w, V = cis_eigs(band, lo=0, hi=5, n_eigs=2)
    assert np.isnan(w).all() and V.shape == (2, 5) and np.isnan(V).all()


def test_logbin_edges_follow_cooltools():
    from uchrom.strc.comp.eig import _logbin_edges

    e = _logbin_edges(481, 1.03)
    assert e[0] == 0 and e[1] == 1 and e[-1] == 481
    assert (np.diff(e) >= 1).all() and (np.diff(e)[:20] == 1).all()       # one diagonal per class near 0
    assert (_logbin_edges(10, 1.0) == np.arange(11)).all()


def test_weighted_percentile_is_numpy_percentile():
    from uchrom.strc.comp.eig import _weighted_percentile

    rng = np.random.default_rng(0)
    values = rng.random(50)
    counts = rng.integers(1, 5, 50)
    full = np.repeat(values, counts)
    for q in (0.0, 12.5, 50.0, 99.9, 100.0):
        assert _weighted_percentile(values, counts.astype(float), q) == pytest.approx(np.percentile(full, q))


def test_clip_threshold_is_the_dense_percentile():
    from uchrom.strc.comp.eig import _clip_threshold

    rng = np.random.default_rng(1)
    pairs = rng.gamma(2.0, size=500)
    singles = np.r_[1.0, 0.7, rng.random(5)]
    scount = np.r_[40, 78, np.ones(5, int)]
    for n_zero in (0, 30, 5000):
        full = np.r_[pairs, pairs, np.repeat(singles, scount), np.zeros(n_zero)]
        for q in (1.0, 50.0, 90.0, 99.0, 99.9):                   # low q: the sorting fallback
            assert _clip_threshold(pairs, singles, scount, n_zero, q) == pytest.approx(np.percentile(full, q))


# ---------------------------------------------------------------- the caller


def _gc_fasta(path, truth, chrom="chr1"):
    """A FASTA whose A bins are GC-rich (60 %) and B bins GC-poor (35 %)."""
    rng = np.random.default_rng(3)
    seq = []
    for a in truth:
        p = 0.6 if a else 0.35
        gc = rng.random(RES) < p
        seq.append(np.where(gc, np.where(rng.random(RES) < 0.5, "G", "C"), np.where(rng.random(RES) < 0.5, "A", "T")))
    seq = "".join("".join(s) for s in seq)
    with gzip.open(path, "wt") as fh:
        fh.write(f">{chrom}\n")
        for k in range(0, len(seq), 80):
            fh.write(seq[k:k + 80] + "\n")
    return path


def test_call_compartments_eig_recovers_planted_compartments(tmp_path):
    from uchrom.strc.comp import compare_compartments
    from uchrom.strc.comp.eig import call_compartments_eig

    bins, pix, truth = _planted(160, masked=(50, 51, 52))
    path = _cool(tmp_path, bins, pix)
    cd = _chromdata(path)
    gc = bins.assign(value=np.where(truth, 0.55, 0.40))
    table = call_compartments_eig(cd, contacts="hic", phasing=gc)
    assert list(table.columns) == ["chrom", "start", "end", "bin_index", "region", "compartment", "E1", "E2", "E3"]
    assert not table["bin_index"].isin([50, 51, 52]).any()               # masked bins dropped
    called = table["compartment"].to_numpy() == "A"
    assert (called == truth[table["bin_index"]]).mean() > 0.97
    assert table["E1"][called].min() > 0 > table["E1"][~called].max()
    ev = cd.results["compartments.eig.eigvals"]
    assert list(ev["region"]) == ["chr1"] and ev["phasing_r1"].iloc[0] > 0.8
    assert abs(ev["eigval1"].iloc[0]) >= abs(ev["eigval2"].iloc[0]) >= abs(ev["eigval3"].iloc[0])
    rec = cd.results.record("compartments.eig")
    assert rec.function == "uchrom.strc.comp.call_compartments_eig" and rec.inputs["contacts"] == "hic"
    segs = cd.intervals["compartments.eig"]
    assert segs["n_bins"].sum() == len(table)
    assert not ((segs["start"] < 52 * RES) & (segs["end"] > 50 * RES)).any()     # broken at the masked bins

    # the same orientation from a FASTA (GC content) and from a bin track
    fasta = _gc_fasta(tmp_path / "toy.fa.gz", truth)
    by_gc = call_compartments_eig(cd, contacts="hic", phasing=str(fasta), key_added=None)
    np.testing.assert_allclose(by_gc["E1"], table["E1"])
    assert cd.results.record("compartments.eig").inputs["phasing"].startswith("DataFrame")
    unsigned = call_compartments_eig(str(path), key_added="ignored")              # a path: nothing stored
    assert abs(np.corrcoef(unsigned["E1"], table["E1"])[0, 1]) == pytest.approx(1.0)

    # loci of a tracing-like ChromData get E1 of the map bin holding their midpoint
    from uchrom import ChromData

    starts = np.arange(0, 160, 4) * RES + 2_500
    spots = pd.DataFrame({"chrom": "chr1", "start": starts, "end": starts + 5_000, "trace_id": "0"})
    loci = ChromData(np.random.default_rng(0).normal(size=(len(spots), 3)), spots)
    loci.link_cool(str(path), key="hic")
    loci.bin_tracks = pd.DataFrame({"gc": np.where(truth[starts // RES], 1.0, 0.0)}, index=loci.bins.index)
    new = call_compartments_eig(loci, contacts="hic", phasing="gc", copy=True)
    assert "compartments.eig" in new.results and "compartments.eig" not in loci.results
    e1 = new.bin_tracks["compartments.eig.E1"].to_numpy()
    want = table.set_index("bin_index")["E1"].reindex(starts // RES).to_numpy()
    np.testing.assert_allclose(e1, want, rtol=1e-8)                              # NaN on masked bins
    out = compare_compartments(new, "compartments.eig", table)
    assert out["agreement"] == 1.0 and out["pearson_r"] == pytest.approx(1.0)


def test_call_compartments_eig_by_arm(tmp_path):
    from uchrom.fea.band import read_band
    from uchrom.strc.comp.eig import call_compartments_eig, cis_eigs

    bins, pix, truth = _planted(200, chroms=("chr1", "chr2"))
    path = _cool(tmp_path, bins, pix)
    cd = _chromdata(path)
    gc = bins.assign(value=np.tile(np.where(truth, 0.55, 0.40), 2))
    table = call_compartments_eig(cd, phasing=gc, centromeres={"chr1": 80 * RES + 3_000}, n_eigs=2)
    assert list(pd.unique(table["region"])) == ["chr1_p", "chr1_q", "chr2"]
    assert table.loc[table.region == "chr1_p", "bin_index"].max() == 80          # the bin holding the centromere
    band = read_band(cooler.Cooler(str(path)), chrom="chr1")
    _, V = cis_eigs(band, lo=81, hi=200, n_eigs=2)
    q = table[table.region == "chr1_q"]
    np.testing.assert_allclose(np.abs(q["E1"].to_numpy()), np.abs(V[0][q["bin_index"].to_numpy() - 81]))
    ev = cd.results["compartments.eig.eigvals"]
    assert list(ev["region"]) == ["chr1_p", "chr1_q", "chr2"] and list(ev["end"])[:2] == [80 * RES + 3_000, 200 * RES]
    called = table["compartment"].to_numpy() == "A"
    assert (called == truth[table["bin_index"]]).mean() > 0.95


def test_track_on_bins_finer_and_coarser_tracks():
    from uchrom.strc.comp.eig import _track_on_bins

    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(8) * RES, "end": np.arange(1, 9) * RES})
    fine = pd.DataFrame({"chrom": "chr1", "start": np.arange(16) * RES // 2, "end": np.arange(1, 17) * RES // 2})
    got = _track_on_bins(fine, np.arange(16.0), bins)                      # the mean of the two halves
    np.testing.assert_allclose(got, np.arange(8) * 2 + 0.5)
    coarse = pd.DataFrame({"chrom": "chr1", "start": [0, 4 * RES], "end": [4 * RES, 8 * RES]})
    got = _track_on_bins(coarse, np.array([1.0, 2.0]), bins)               # the coarse bin holding the midpoint
    np.testing.assert_allclose(got, [1.0] * 4 + [2.0] * 4)
    other = pd.DataFrame({"chrom": "chr2", "start": [0], "end": [8 * RES]})
    assert np.isnan(_track_on_bins(other, np.array([1.0]), bins)).all()


def test_call_compartments_eig_input_errors(tmp_path):
    from uchrom.strc.comp.eig import call_compartments_eig

    bins, pix, _ = _planted(60)
    raw = _cool(tmp_path, bins, pix, name="raw.cool", balance=False)
    with pytest.raises(ValueError, match="not balanced"):
        call_compartments_eig(_chromdata(raw))
    cd = _chromdata(_cool(tmp_path, bins, pix))
    with pytest.raises(KeyError, match="phasing"):
        call_compartments_eig(cd, phasing="nope")
    with pytest.raises(ValueError, match="not in the map"):
        call_compartments_eig(cd, chrom="chrX")


# ---------------------------------------------------------------- saddle


def test_compartment_strength_equals_the_dense_saddle(tmp_path):
    from uchrom.strc.comp.eig import SaddleParams, call_compartments_eig, compartment_strength, saddle_strength

    bins, pix, truth = _planted(160, masked=(10, 90))
    path = _cool(tmp_path, bins, pix)
    cd = _chromdata(path)
    call_compartments_eig(cd, phasing=bins.assign(value=truth.astype(float)))
    out = compartment_strength(cd, n_bins=10)
    e1 = cd.results["compartments.eig"].set_index("bin_index")["E1"].reindex(np.arange(160)).to_numpy()
    S, C = _dense_saddle(cooler.Cooler(str(path)).matrix(balance=True).fetch("chr1"), e1, 10)
    np.testing.assert_allclose(out["sum"], S, rtol=1e-10, atol=1e-10)
    np.testing.assert_array_equal(out["count"], C)
    np.testing.assert_allclose(out["strength_curve"][1:], saddle_strength(S, C)[1:])
    assert out["saddle"].shape == (12, 12) and out["group_size"].sum() == 158
    k = out["corner_groups"]
    assert out["strength"] == pytest.approx(out["strength_curve"][k])
    assert out["AA"] > 1 and out["BB"] > 1 and out["AB"] < 1 and out["strength"] > 3
    rec = cd.results.record("compartment_strength.saddle")
    assert rec.kind == "mapping" and rec.inputs["compartments"] == "compartments.eig"

    # no compartments: strength near 1
    flat, fpix, _ = _planted(160, fold=1.0, seed=5)
    fcd = _chromdata(_cool(tmp_path, flat, fpix, name="flat.cool"))
    call_compartments_eig(fcd, phasing=flat.assign(value=truth.astype(float)))
    assert 0.8 < compartment_strength(fcd, key_added=None, n_bins=10)["strength"] < 1.25

    # a band limit and a DataFrame track on a path
    lim = compartment_strength(str(path), compartments=cd.results["compartments.eig"], n_bins=10,
                               params=SaddleParams(max_diag=40))
    assert lim["count"].sum() < out["count"].sum() and lim["strength"] > 2


def test_compartment_strength_errors(tmp_path):
    from uchrom.strc.comp.eig import SaddleParams, compartment_strength

    bins, pix, _ = _planted(60)
    cd = _chromdata(_cool(tmp_path, bins, pix))
    with pytest.raises(KeyError, match="compartments"):
        compartment_strength(cd)
    with pytest.raises(ValueError, match="qrange"):
        compartment_strength(cd, compartments=bins.assign(E1=0.0), params=SaddleParams(qrange=None))
