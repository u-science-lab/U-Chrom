"""uchrom.fea.contact_features: short / long ratio (Guo et al. 2026's bins), bands, P(s) slope, cis fraction and
trans shares from the stored contact-distance histograms, checked against the pairs of one real mESC cell."""

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.fea import ContactFeatureParams, contact_features
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
