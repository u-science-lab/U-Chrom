"""uchrom.strc.comp.single_cell: single-cell compartment values (scA/B) from per-cell maps."""

import warnings

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from chromdata import ChromData  # noqa: E402

from uchrom.io.pairs_maps import genome_bins  # noqa: E402
from uchrom.strc.comp import single_cell as sc  # noqa: E402
from uchrom.strc.comp.single_cell import (  # noqa: E402
    ScABParams,
    normalize_scab,
    scab_sums,
    single_cell_compartments,
)

RES = 1000
SIZES = {"chrA": 40_500, "chrB": 23_000, "chrC": 9_000}


def _brute(cells, b1, b2, cnt, track, chrom, n_cells, mode="all", min_sep=1, min_contacts=1):
    """Dip-C ``color2`` written out contact by contact: every contact between two different bins appends the
    partner's track value to each leg (when the partner has one); the value is the mean of the list."""
    nb = len(track)
    lists = [[[] for _ in range(nb)] for _ in range(n_cells)]
    for r, i, j, n in zip(cells, b1, b2, cnt):
        cis = chrom[i] == chrom[j]
        if i == j or (mode == "cis" and not cis) or (mode == "trans" and cis):
            continue
        if cis and abs(i - j) < min_sep:
            continue
        for _ in range(int(n)):
            if np.isfinite(track[j]):
                lists[r][i].append(track[j])
            if np.isfinite(track[i]):
                lists[r][j].append(track[i])
    out = np.full((n_cells, nb), np.nan)
    for r in range(n_cells):
        for i in range(nb):
            if len(lists[r][i]) >= min_contacts:
                out[r, i] = np.mean(lists[r][i])
    return out


def _random_pixels(rng, n_cells, nb, chrom, n=300):
    rows, i, j, c = [], [], [], []
    for r in range(n_cells):
        a = rng.integers(0, nb, n)
        b = np.clip(a + rng.geometric(0.15, n) - 1, 0, nb - 1)
        t = rng.random(n) < 0.2
        b[t] = rng.integers(0, nb, int(t.sum()))
        rows.append(np.full(n, r))
        i.append(np.minimum(a, b))
        j.append(np.maximum(a, b))
        c.append(rng.integers(1, 4, n))
    return np.concatenate(rows), np.concatenate(i), np.concatenate(j), np.concatenate(c)


@pytest.mark.parametrize("mode,min_sep,min_contacts", [("all", 1, 1), ("cis", 1, 1), ("trans", 1, 1),
                                                       ("all", 3, 2)])
def test_kernel_is_the_mean_of_the_partners_track(mode, min_sep, min_contacts):
    rng = np.random.default_rng(1)
    chrom = np.repeat([0, 1, 2], [20, 12, 8])
    nb = len(chrom)
    track = rng.random(nb)
    track[[3, 25]] = np.nan                                       # bins without a value are no partners
    rows, i, j, c = _random_pixels(rng, 5, nb, chrom)
    params = ScABParams(contacts=mode, min_separation=min_sep, min_contacts=min_contacts)
    got, den, n_contacts = scab_sums(rows, i, j, c, track, n_rows=5, chrom_of_bin=chrom, params=params)
    want = _brute(rows, i, j, c, track, chrom, 5, mode, min_sep, min_contacts)
    np.testing.assert_allclose(got, want, rtol=1e-12, equal_nan=True)
    assert np.isnan(got).sum() == np.isnan(want).sum()
    # contacts counted: after the cis / trans and separation filters, each once
    cis = chrom[i] == chrom[j]
    keep = (i != j) & ((mode == "all") | ((mode == "cis") & cis) | ((mode == "trans") & ~cis))
    keep &= ~cis | (np.abs(i - j) >= min_sep)
    np.testing.assert_array_equal(n_contacts, np.bincount(rows[keep], weights=c[keep], minlength=5))


def test_normalize_rank_is_dipc_color_to_rank():
    from scipy.stats import rankdata

    x = np.array([[0.3, np.nan, 0.1, 0.3, 0.9], [np.nan, 0.5, np.nan, np.nan, np.nan],
                  [2.0, 1.0, 4.0, 3.0, 0.0]])
    r = normalize_scab(x, "rank")
    ok = np.isfinite(x[0])
    want = (rankdata(x[0][ok]) - 1) / (ok.sum() - 1)                 # ties averaged, 0..1
    np.testing.assert_allclose(r[0][ok], want)
    assert np.isnan(r[0][~ok]).all()
    assert np.isnan(r[1]).all()                                       # one value: no rank
    np.testing.assert_allclose(r[2], [0.5, 0.25, 1.0, 0.75, 0.0])
    z = normalize_scab(x, "zscore")
    np.testing.assert_allclose(z[2], (x[2] - x[2].mean()) / x[2].std())
    np.testing.assert_array_equal(normalize_scab(x, "none"), x)
    # many rows, many ties, missing values: as rankdata row by row
    rng = np.random.default_rng(5)
    x = rng.integers(0, 6, (40, 30)).astype(float)
    x[rng.random(x.shape) < 0.2] = np.nan
    r = normalize_scab(x, "rank")
    for row, got in zip(x, r):
        ok = np.isfinite(row)
        np.testing.assert_allclose(got[ok], (rankdata(row[ok]) - 1) / (ok.sum() - 1))
        assert np.isnan(got[~ok]).all()


def _dataset(tmp_path, n_cells=9, seed=0):
    rng = np.random.default_rng(seed)
    bins = genome_bins(SIZES, RES)
    chrom = pd.factorize(bins["chrom"])[0]
    names = [f"c{k:02d}" for k in range(n_cells)]
    maps = {}
    rows, i, j, c = _random_pixels(rng, n_cells, len(bins), chrom, n=400)
    for r, name in enumerate(names):
        sel = rows == r
        px = (pd.DataFrame({"bin1_id": i[sel], "bin2_id": j[sel], "count": c[sel]})
              .groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum())
        maps[name] = px
    scool = tmp_path / "cells.scool"
    cooler.create_scool(str(scool), bins, maps, ordered=True, assembly="toy1")
    cells = pd.DataFrame({"cell_type": np.array(["T1", "T2", "T3"])[np.arange(n_cells) % 3]},
                         index=pd.Index(names, name="cell_id"))
    no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                             "cell_id": pd.Series(dtype=str)})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells, uns={"genome_assembly": "toy1"})
    cd.link_scool(scool.name, key="per_cell", cell_name="cell_id", genome_assembly="toy1", bin_size=RES)
    store = tmp_path / "toy.chromdata.zarr"
    cd.write(store)
    track = pd.DataFrame({"chrom": bins["chrom"], "start": bins["start"], "end": bins["end"],
                          "value": rng.random(len(bins))})
    track.loc[[5, 50], "value"] = np.nan
    return store, bins, maps, names, track


def _expected(bins, maps, names, track, res=RES, params=ScABParams(), chroms=None):
    """The scA/B matrix from the maps directly: pixels to coarse bins, the brute-force kernel, the norm."""
    coarse = genome_bins(SIZES, res)
    first = coarse.reset_index().groupby("chrom", sort=False)["index"].min()
    to_coarse = first[bins["chrom"]].to_numpy() + bins["start"].to_numpy() // res
    # the track on the coarse bins: mean of the fine values whose midpoint they hold
    t = pd.Series(track["value"].to_numpy()).groupby(to_coarse).mean().to_numpy()
    chrom = pd.factorize(coarse["chrom"])[0]
    rows, i, j, c = [], [], [], []
    for r, n in enumerate(names):
        px = maps[n]
        rows.append(np.full(len(px), r))
        i.append(to_coarse[px["bin1_id"].to_numpy()])
        j.append(to_coarse[px["bin2_id"].to_numpy()])
        c.append(px["count"].to_numpy())
    raw = _brute(np.concatenate(rows), np.concatenate(i), np.concatenate(j), np.concatenate(c), t, chrom,
                 len(names), params.contacts, params.min_separation, params.min_contacts)
    cols = np.arange(len(coarse)) if chroms is None else np.flatnonzero(coarse["chrom"].isin(chroms))
    return normalize_scab(raw[:, cols], params.normalize), coarse.iloc[cols].reset_index(drop=True), t[cols]


@pytest.mark.parametrize("res", [RES, 3 * RES])
@pytest.mark.parametrize("params", [ScABParams(), ScABParams(contacts="cis", normalize="none")])
def test_from_a_scool_matches_the_definition(tmp_path, res, params):
    store, bins, maps, names, track = _dataset(tmp_path)
    cd = ChromData.read(store)
    frame = single_cell_compartments(cd, track=track, resolution=res, params=params)
    want, wbins, wtrack = _expected(bins, maps, names, track, res, params)
    np.testing.assert_allclose(frame.to_numpy(np.float64), want, rtol=1e-6, atol=1e-7, equal_nan=True)
    assert list(frame.index) == names
    assert frame.columns[0] == f"chrA:0-{res}"
    # stored: the matrix on the cells axis, the bins with provenance, per-cell counts
    np.testing.assert_array_equal(cd.cellm["compartments.scab"], frame.to_numpy())
    table = cd.results["compartments.scab"]
    assert list(table.columns) == ["chrom", "start", "end", "track", "n_cells", "mean", "sd"]
    pd.testing.assert_frame_equal(table[["chrom", "start", "end"]].astype({"chrom": str}),
                                  wbins[["chrom", "start", "end"]].astype({"chrom": str}), check_dtype=False)
    np.testing.assert_allclose(table["track"], wtrack, equal_nan=True)
    np.testing.assert_array_equal(table["n_cells"], np.isfinite(want).sum(axis=0))
    rec = cd.results.record("compartments.scab")
    assert rec.function == "uchrom.strc.comp.single_cell_compartments"
    assert rec.params["contacts"] == params.contacts and rec.inputs["resolution"] == res
    assert (cd.cells["compartments.scab.n_bins"].to_numpy() == np.isfinite(want).sum(axis=1)).all()
    assert (cd.cells["compartments.scab.n_contacts"] > 0).all()


def test_cells_and_chromosomes_subset(tmp_path):
    store, bins, maps, names, track = _dataset(tmp_path)
    cd = ChromData.read(store)
    pick = ["c07", "c02", "c04"]
    frame = single_cell_compartments(cd, track=track, cells=pick, chrom=["chrA", "chrC"])
    order = sorted(pick)                                   # the computed cells, in the maps' order
    want, wbins, _ = _expected(bins, {n: maps[n] for n in order}, order, track, chroms=["chrA", "chrC"])
    assert list(frame.index) == order
    np.testing.assert_allclose(frame.to_numpy(np.float64), want, rtol=1e-6, atol=1e-7, equal_nan=True)
    assert frame.shape[1] == len(wbins) and not any(c.startswith("chrB") for c in frame.columns)
    m = cd.cellm["compartments.scab"]
    assert m.shape == (len(names), len(wbins))
    assert np.isnan(m[[names.index(c) for c in names if c not in pick]]).all()
    assert np.isnan(cd.cells.loc["c00", "compartments.scab.n_contacts"])


def test_embedded_maps_give_the_same_values_in_several_blocks(tmp_path, monkeypatch):
    from chromdata.embedded import embed_links

    store, bins, maps, names, track = _dataset(tmp_path)
    ref = single_cell_compartments(ChromData.read(store), track=track, key_added=None)
    embed_links(str(store), verbose=False)
    (tmp_path / "cells.scool").rename(tmp_path / "moved.scool")      # only the embedded copy is left
    monkeypatch.setattr(sc, "BLOCK_BYTES", 16 * len(bins) * 2)      # two cells per block
    cd = ChromData.read(store, backed=True)
    got = single_cell_compartments(cd, track=track, max_pixels=150, workers=2)  # several reads per partition
    pd.testing.assert_frame_equal(got, ref)
    assert cd.cellm["compartments.scab"].shape == ref.shape
    for p in (ScABParams(contacts="cis"), ScABParams(contacts="trans", normalize="none"),
              ScABParams(min_separation=3, min_contacts=2)):
        got = single_cell_compartments(cd, track=track, params=p, resolution=2 * RES, key_added=None)
        want, _, _ = _expected(bins, maps, names, track, res=2 * RES, params=p)
        np.testing.assert_allclose(got.to_numpy(np.float64), want, rtol=1e-6, atol=1e-7, equal_nan=True)


def test_track_from_a_fasta_is_the_cpg_frequency(tmp_path):
    from uchrom.fea.sequence import compute_sequence_features

    rng = np.random.default_rng(3)
    store, bins, maps, names, _ = _dataset(tmp_path)
    fasta = tmp_path / "toy.fa"
    seqs = {}
    with open(fasta, "w") as fh:
        for c, n in SIZES.items():
            s = "".join(rng.choice(list("ACGTacgN"), n, p=[.2, .25, .25, .2, .03, .03, .02, .02]))
            seqs[c] = s.upper()
            fh.write(f">{c}\n" + "\n".join(s[k:k + 60] for k in range(0, n, 60)) + "\n")
    cd = ChromData.read(store)
    frame = single_cell_compartments(cd, track=str(fasta), resolution=5 * RES)
    table = cd.results["compartments.scab"]
    for row in table.sample(5, random_state=0).itertuples():
        s = seqs[row.chrom][row.start:row.end]
        pairs = sum(1 for a, b in zip(s, s[1:]) if a in "ACGT" and b in "ACGT")
        assert row.track == pytest.approx(s.count("CG") / pairs)
    feats = compute_sequence_features(table[["chrom", "start", "end"]], fasta, features=["cpg_frequency"])
    np.testing.assert_allclose(feats["cpg_frequency"], table["track"])
    assert "cpg_frequency" in cd.results.record("compartments.scab").inputs["track"]
    assert frame.notna().to_numpy().any()


def test_copy_and_errors(tmp_path):
    store, bins, maps, names, track = _dataset(tmp_path)
    cd = ChromData.read(store)
    out = single_cell_compartments(cd, track=track, copy=True, key_added="scab")
    assert "scab" in out.cellm and "scab" not in cd.cellm
    with pytest.raises(ValueError, match="needs a track"):
        single_cell_compartments(cd)
    with pytest.raises(ValueError, match="contacts"):
        single_cell_compartments(cd, track=track, params=ScABParams(contacts="near"))
    with pytest.raises(ValueError, match="not in the per-cell maps"):
        single_cell_compartments(cd, track=track, chrom="chrZ")
    with pytest.raises(KeyError):
        single_cell_compartments(cd, track=track, cells=["nope"])
    with pytest.raises(ValueError, match="multiple"):
        single_cell_compartments(cd, track=track, resolution=1500)
    cells = cd.cells.copy()
    cd.cells = pd.concat([cells, cells.iloc[:1].rename(index={"c00": "ghost"})])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        frame = single_cell_compartments(cd, track=track, key_added="s")
    assert any("no per-cell map" in str(x.message) for x in w)
    assert "ghost" not in frame.index and np.isnan(cd.cellm["s"][-1]).all()
