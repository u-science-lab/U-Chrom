"""uchrom.fea.contact_features: short / long ratio (Guo et al. 2026's bins), bands, P(s) slope, cis fraction and
trans shares from the stored contact-distance histograms, checked against the pairs of one real mESC cell."""

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.fea import ContactFeatureParams, chromosome_dosage, contact_features
from uchrom.io.pairs_stats import ContactStats, distance_edges

from .. import FIXTURES
from ..io.test_pairs_stats import MM10


@pytest.fixture(scope="module")
def pairs():
    return pd.read_csv(FIXTURES / "cell1.pairs.gz", sep="\t", header=None,
                       names=["read", "chrom1", "pos1", "chrom2", "pos2", "strand1", "strand2"])


def _cd(pairs):
    names = list(MM10)
    code = {c: i for i, c in enumerate(names)}
    st = ContactStats(["cell1", "empty"], names, distance_edges(MM10))
    c1 = pairs["chrom1"].map(code).fillna(-1).astype(int)
    c2 = pairs["chrom2"].map(code).fillna(-1).astype(int)
    st.add(np.zeros(len(pairs), int), c1, pairs["pos1"], c2, pairs["pos2"], pairs["strand1"], pairs["strand2"])
    cd = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                "end": [], "trace_id": []}),
                   cells=pd.DataFrame({"cell_id": ["cell1", "empty"]}))
    st.write(cd, key="contacts")
    return cd


def test_guo2026_ratio_matches_their_computation(pairs):
    cd = _cd(pairs)
    f = contact_features(cd, params=ContactFeatureParams.guo2026())
    # Guo et al.: scHiCluster histogram of cis |pos2 - pos1|, bins 0-7 zeroed, proportions of the rest
    cis = pairs[(pairs["chrom1"] == pairs["chrom2"]) & pairs["chrom1"].isin(list(MM10))]
    edges = distance_edges(MM10)
    decay = np.histogram((cis["pos2"] - cis["pos1"]).abs(), edges)[0].astype(float)
    decay[:8] = 0
    props = decay / decay.sum()
    short, long = props[51:77].sum(), props[103:115].sum()
    assert f.loc["cell1", "frac_short"] == pytest.approx(short, rel=1e-12)
    assert f.loc["cell1", "frac_long"] == pytest.approx(long, rel=1e-12)
    assert f.loc["cell1", "short_long_ratio"] == pytest.approx(short / long, rel=1e-12)
    assert np.isnan(f.loc["empty", "short_long_ratio"])
    # stored on the cells and as a result table
    assert cd.cells["contacts.short_long_ratio"].iloc[0] == pytest.approx(short / long)
    assert "contacts.features" in cd.results


def test_default_ranges_bands_slopes_trans(pairs):
    cd = _cd(pairs)
    f = contact_features(cd, key_added=None)
    assert "contacts.short_long_ratio" not in cd.cells.columns
    cis = pairs[(pairs["chrom1"] == pairs["chrom2"]) & pairs["chrom1"].isin(list(MM10))]
    d = (cis["pos2"] - cis["pos1"]).abs().to_numpy()
    known = pairs["chrom1"].isin(list(MM10)) & pairs["chrom2"].isin(list(MM10))
    n_trans = int(known.sum()) - len(cis)
    assert f.loc["cell1", "n_cis"] == len(cis) and f.loc["cell1", "n_trans"] == n_trans
    assert f.loc["cell1", "cis_fraction"] == pytest.approx(len(cis) / known.sum())
    # by bin centres the default ranges are bins 51-76 and 104-114: close to Guo's
    assert f.loc["cell1", "n_used"] == (d >= 5000).sum() - (d > distance_edges(MM10)[-1]).sum()
    band = f.loc["cell1", "frac_2M_12M"]
    assert 0.0 < band < 1.0
    assert -2.0 < f.loc["cell1", "ps_slope_100k_1M"] < -0.3 and -2.5 < f.loc["cell1", "ps_slope_1M_10M"] < -0.5
    tr = pairs[known & (pairs["chrom1"] != pairs["chrom2"])]
    legs = ((tr["chrom1"] == "chr7").sum() + (tr["chrom2"] == "chr7").sum())
    cis7 = (cis["chrom1"] == "chr7").sum()
    assert f.loc["cell1", "trans_share.chr7"] == pytest.approx(legs / (legs + 2 * cis7))
    with pytest.raises(KeyError):
        contact_features(cd, key="other")


def test_genome_wide_histograms_give_the_same_features(pairs):
    cd = _cd(pairs)
    a = contact_features(cd, key_added=None)
    names = list(MM10)
    code = {c: i for i, c in enumerate(names)}
    st = ContactStats(["cell1", "empty"], names, distance_edges(MM10))
    c1 = pairs["chrom1"].map(code).fillna(-1).astype(int)
    c2 = pairs["chrom2"].map(code).fillna(-1).astype(int)
    st.add(np.zeros(len(pairs), int), c1, pairs["pos1"], c2, pairs["pos2"], pairs["strand1"], pairs["strand2"])
    st.write(cd, key="gw", per_chromosome=False, dtype=np.int32)
    assert cd.cellm["gw.distance"].shape == (2, len(st.edges) + 1) and cd.cellm["gw.distance"].dtype == np.int32
    b = contact_features(cd, key="gw", key_added=None)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
    with pytest.raises(ValueError):
        contact_features(cd, key="gw", params=ContactFeatureParams(chroms=["chr1"]), key_added=None)


def test_per_chromosome_features_ignore_chromosome_gains(pairs):
    """A cell with an extra copy of chr19 (its chr19 contacts doubled) shifts the pooled features, not the
    per-chromosome ones: the same folding on every chromosome."""
    names = list(MM10)
    code = {c: i for i, c in enumerate(names)}
    cis = pairs[(pairs["chrom1"] == pairs["chrom2"]) & pairs["chrom1"].isin(names)]
    gain = pd.concat([cis, cis[cis["chrom1"] == "chr19"]], ignore_index=True)
    st = ContactStats(["cell1", "gain"], names, distance_edges(MM10))
    for row, p in enumerate((cis, gain)):
        c = p["chrom1"].map(code).astype(int)
        st.add(np.full(len(p), row), c, p["pos1"], c, p["pos2"], p["strand1"], p["strand2"])
    cd = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                "end": [], "trace_id": []}),
                   cells=pd.DataFrame({"cell_id": ["cell1", "gain"]}))
    st.write(cd, key="contacts")
    cols = ["frac_short", "frac_long", "short_long_ratio", "frac_2M_12M", "ps_slope_1M_10M"]
    pooled = contact_features(cd, params=ContactFeatureParams.guo2026(), key_added=None)
    assert not np.allclose(pooled.loc["cell1", cols].to_numpy(float), pooled.loc["gain", cols].to_numpy(float))
    per = contact_features(cd, params=ContactFeatureParams.guo2026(per_chromosome=True), key_added=None)
    np.testing.assert_allclose(per.loc["cell1", cols].to_numpy(float), per.loc["gain", cols].to_numpy(float),
                               rtol=1e-12)
    dropped = [c for c in names if c not in per.attrs["chroms"]]    # too short for 20-50 Mb contacts to count
    assert "chr1" in per.attrs["chroms"] and dropped and all(MM10[c] < MM10["chr1"] / 2 for c in dropped)
    one = contact_features(cd, params=ContactFeatureParams.guo2026(chroms=["chr2"], per_chromosome=True),
                           key_added=None)
    sub = contact_features(cd, params=ContactFeatureParams.guo2026(chroms=["chr2"]), key_added=None)
    np.testing.assert_allclose(one[cols].to_numpy(float), sub[cols].to_numpy(float))


def _thinned_cells(pairs, n: int = 8, gains=(0, 1), seed: int = 0):
    """``n`` cells, each 60 % of the real cell's contacts drawn at random; the cells in ``gains`` with their chr19
    contacts (cis and trans) counted twice: an extra copy of chr19."""
    names = list(MM10)
    code = {c: i for i, c in enumerate(names)}
    known = pairs[pairs["chrom1"].isin(names) & pairs["chrom2"].isin(names)]
    rng = np.random.default_rng(seed)
    st = ContactStats([f"c{i}" for i in range(n)] + ["empty"], names, distance_edges(MM10))
    for i in range(n):
        p = known[rng.random(len(known)) < 0.6]
        if i in gains:
            p = pd.concat([p, p[(p["chrom1"] == "chr19") | (p["chrom2"] == "chr19")]], ignore_index=True)
        st.add(np.full(len(p), i), p["chrom1"].map(code), p["pos1"], p["chrom2"].map(code), p["pos2"],
               p["strand1"], p["strand2"])
    cd = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                "end": [], "trace_id": []}),
                   cells=pd.DataFrame({"cell_id": list(st.cells), "section": ["a"] * (n // 2) + ["b"] * (n - n // 2)
                                       + [None]}))
    st.write(cd, key="contacts")
    return cd, st


def test_chromosome_dosage_is_the_log2_share_of_the_legs(pairs):
    cd, st = _thinned_cells(pairs)
    ids = [f"c{i}" for i in range(8)]
    t = chromosome_dosage(cd, cells=ids, key_added=None)
    assert list(t.index) == ids and list(t.columns) == list(MM10)
    legs = (2 * st.distance.sum(axis=2) + st.trans)[:8].astype(float)
    share = legs / legs.sum(axis=1, keepdims=True)
    np.testing.assert_allclose(t.to_numpy(), np.log2(share / np.median(share, axis=0)), rtol=0, atol=1e-12)
    # the extra chr19: about +log2(2) on chr19 in the two cells (its trans contacts with a partner leg elsewhere
    # count once more, not twice), the other chromosomes a little lower, nothing in the rest
    gain, rest = t.loc[["c0", "c1"]], t.loc[ids[2:]]
    assert (gain["chr19"] > 0.75).all() and (rest["chr19"].abs() < 0.1).all()
    assert (gain.drop(columns="chr19").median(axis=1) < -0.02).all()
    # the empty cell, the excluded chromosome, the median per group
    assert t.shape[0] == 8 and chromosome_dosage(cd, key_added=None).loc["empty"].isna().all()
    noX = chromosome_dosage(cd, cells=ids, exclude=("chrX",), key_added=None)
    assert "chrX" not in noX.columns and np.isfinite(noX.to_numpy()).all()
    by = chromosome_dosage(cd, groupby="section", key_added=None)
    for sec, rows in (("a", ids[:4]), ("b", ids[4:])):
        s = share[[ids.index(c) for c in rows]]
        np.testing.assert_allclose(by.loc[rows].to_numpy(), np.log2(s / np.median(s, axis=0)), atol=1e-12)
    assert by.loc["empty"].isna().all()                         # no group
    with pytest.raises(KeyError):
        chromosome_dosage(cd, key="other")


def test_chromosome_dosage_components_find_the_gain(pairs):
    cd, _ = _thinned_cells(pairs)
    ids = [f"c{i}" for i in range(8)]
    t = chromosome_dosage(cd, cells=ids, n_pcs=3)
    prof = t[list(MM10)].to_numpy()
    Z = (prof - prof.mean(0)) / prof.std(0, ddof=1)
    u, sv, _ = np.linalg.svd(Z, full_matrices=False)
    np.testing.assert_allclose(np.abs(t[["PC1", "PC2", "PC3"]].to_numpy()), np.abs(u[:, :3] * sv[:3]), atol=1e-9)
    assert t.attrs["pc_variance"][0] == pytest.approx(sv[0] ** 2 / (sv ** 2).sum())
    pc1 = t["PC1"].to_numpy()                                   # the two cells with the gain at one end
    assert set(np.argsort(pc1 * np.sign(pc1[0]))[-2:]) == {0, 1}
    # stored: the profile and components on the cells (NaN for the cell left out), the table as a result
    assert cd.cellm["contacts.dosage"].shape == (9, len(MM10)) and np.isnan(cd.cellm["contacts.dosage"][8]).all()
    np.testing.assert_allclose(cd.cellm["contacts.dosage.pcs"][:8], t[["PC1", "PC2", "PC3"]].to_numpy())
    assert cd.results.record("contacts.dosage").params["n_pcs"] == 3
    from uchrom.spatial import covariate_matrix

    cov = covariate_matrix(cd, ["contacts.dosage.pcs"], ids)
    assert cov.shape == (8, 3)
