"""uchrom.fea.separation_profile: per-cell proximity by genomic separation, from per-cell maps (.scool, embedded)
and from traced coordinates (in memory, backed), against direct counts and brute-force pairs."""

import warnings

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData

from uchrom.fea import SeparationParams, separation_profile

RES = 1000
SIZES = {"chrA": 40_500, "chrB": 23_000, "chrX": 9_000}


# ------------------------------------------------------------------------------------------------- contacts

def _cell_pixels(rng, nb, chrom, n=400):
    i = rng.integers(0, nb, n)
    j = np.clip(i + rng.geometric(0.15, n) - 1, 0, nb - 1)
    t = rng.random(n) < 0.15
    j[t] = rng.integers(0, nb, int(t.sum()))
    same = chrom[i] == chrom[j]
    j[~same & ~t] = i[~same & ~t]
    a, b = np.minimum(i, j), np.maximum(i, j)
    return (pd.DataFrame({"bin1_id": a, "bin2_id": b, "count": rng.integers(1, 3, n)})
            .groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum())


def _map_dataset(tmp_path, n_cells=12, seed=0):
    cooler = pytest.importorskip("cooler")
    from uchrom.io.pairs_maps import genome_bins

    rng = np.random.default_rng(seed)
    bins = genome_bins(SIZES, RES)
    chrom = bins["chrom"].to_numpy()
    names = [f"c{k:02d}" for k in range(n_cells)]
    maps = {c: _cell_pixels(rng, len(bins), chrom) for c in names}
    cooler.create_scool(str(tmp_path / "cells.scool"), bins, maps, ordered=True, assembly="toy1")
    ids = names + ["no_map"]                                         # a cell without a map
    cells = pd.DataFrame({"cell_type": np.array(["T1", "T2"])[np.arange(len(ids)) % 2]},
                         index=pd.Index(ids, name="cell_id"))
    no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                             "cell_id": pd.Series(dtype=str)})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells)
    cd.link_scool("cells.scool", key="per_cell", cell_name="cell_id", genome_assembly="toy1", bin_size=RES)
    store = tmp_path / "toy.chromdata.zarr"
    cd.write(store)
    return store, bins, maps


def _expected_contacts(bins, maps, p: SeparationParams, chroms=("chrA", "chrB")):
    chrom = bins["chrom"].to_numpy()
    rows, prof = {}, {}
    e = np.asarray(p.edges, float) if p.edges is not None else None
    for c, px in maps.items():
        same = (chrom[px.bin1_id] == chrom[px.bin2_id]) & np.isin(chrom[px.bin1_id], chroms)
        px = px[same]
        sep = (px.bin2_id - px.bin1_id).to_numpy() * RES
        cnt = px["count"].to_numpy()
        n_s = cnt[(sep >= p.short[0]) & (sep < p.short[1])].sum()
        n_l = cnt[(sep >= p.long[0]) & (sep < p.long[1])].sum()
        rows[c] = {"n_cis": cnt.sum(), "n_apart": cnt[sep > 0].sum(), "n_short": n_s, "n_long": n_l,
                   "log2_short_long": np.log2((n_s + p.pseudocount) / (n_l + p.pseudocount))}
        if e is not None:
            prof[c] = [cnt[(sep >= a) & (sep < b)].sum() for a, b in zip(e[:-1], e[1:])]
    return pd.DataFrame(rows).T.astype(float), (pd.DataFrame(prof).T.astype(float) if prof else None)


P_MAP = SeparationParams(short=(1000, 2000), long=(3000, 7000), edges=np.r_[0, np.arange(0.5, 12.5)] * RES)


def test_contacts_from_a_scool_match_direct_counts(tmp_path):
    store, bins, maps = _map_dataset(tmp_path)
    cd = ChromData.read(store)
    out = separation_profile(cd, params=P_MAP)
    want, prof = _expected_contacts(bins, maps, P_MAP)
    assert list(out.index) == list(cd.cells.index.astype(str))
    assert out.loc["no_map"].isna().all()                           # no map: NaN, not zero
    got = out.drop(index="no_map")[want.columns]
    np.testing.assert_allclose(got.to_numpy(), want.loc[got.index].to_numpy())
    # stored: cells columns, the table, the profile (cells axis) with its bins in the parameters
    np.testing.assert_allclose(cd.cells["separation.n_short"].drop(index="no_map").to_numpy(),
                               want.loc[got.index, "n_short"].to_numpy())
    np.testing.assert_allclose(cd.cellm["separation.profile"][:-1], prof.loc[got.index].to_numpy())
    assert np.isnan(cd.cellm["separation.profile"][-1]).all()
    rec = cd.results.record("separation")
    assert rec.function == "uchrom.fea.separation_profile" and rec.inputs["source"] == "contacts"
    assert rec.params["edges"] == [float(v) for v in P_MAP.edges]
    assert rec.inputs["per_cell_maps"][0]["chroms"] == ["chrA", "chrB"]   # chrX left out by default


def test_contacts_from_embedded_maps_match_the_scool(tmp_path):
    from chromdata.embedded import embed_links

    store, bins, maps = _map_dataset(tmp_path)
    embed_links(str(store), verbose=False)
    (tmp_path / "cells.scool").rename(tmp_path / "moved.scool")       # only the embedded copy is left
    cd = ChromData.read(store, backed=True)
    out = separation_profile(cd, params=P_MAP, max_pixels=150, workers=2, key_added=None)
    want, prof = _expected_contacts(bins, maps, P_MAP)
    got = out.drop(index="no_map")
    np.testing.assert_allclose(got[want.columns].to_numpy(), want.loc[got.index].to_numpy())
    np.testing.assert_allclose(out.attrs["profile"].drop(index="no_map").to_numpy(), prof.loc[got.index].to_numpy())
    # chromosomes chosen, cells chosen
    p = SeparationParams(short=P_MAP.short, long=P_MAP.long, chroms=["chrA", "chrX"])
    sub = separation_profile(cd, params=p, cells=["c03", "c00"], key_added=None)
    want2, _ = _expected_contacts(bins, {c: maps[c] for c in ("c00", "c03")}, p, chroms=("chrA", "chrX"))
    assert list(sub.index) == ["c00", "c03"]                          # in the cells' order
    np.testing.assert_allclose(sub[want2.columns].to_numpy(), want2.loc[sub.index].to_numpy())


# ------------------------------------------------------------------------------------------------- coordinates

LOCI = {"chr1": np.array([0, 1.0, 2.2, 3.1, 4.0, 6.5, 9.0, 20.0, 30.0]) * 1e6,
        "chr2": np.array([0, 1.4, 2.0, 25.0]) * 1e6,
        "chrX": np.array([0, 1.5, 30.0]) * 1e6}


def _traced(n_cells=7, seed=3, nan_frac=0.15, with_cells=True):
    """Two copies of every chromosome per cell, loci 100 kb wide at LOCI (start), some spots missing / NaN; a cell
    without spots in the cells table (``with_cells=False``: no cells at all, traces only)."""
    rng = np.random.default_rng(seed)
    rows, xyz = [], []
    for c in range(n_cells):
        for chrom, starts in LOCI.items():
            for h in range(2):
                walk = np.cumsum(rng.normal(size=(len(starts), 3)), axis=0) * (1 + c % 3)
                for k, s in enumerate(starts):
                    if rng.random() < 0.1:
                        continue                                       # not detected
                    rows.append((chrom, int(s), int(s) + 100_000, f"t{c}_{chrom}_{h}", f"cell{c}"))
                    xyz.append(walk[k] if rng.random() > nan_frac else [np.nan] * 3)
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    if not with_cells:
        return ChromData(np.asarray(xyz, float), spots.drop(columns="cell_id"), uns={"xyz_unit": "um"})
    cells = pd.DataFrame({"cell_type": [f"T{c % 2}" for c in range(n_cells + 1)]},
                         index=pd.Index([f"cell{c}" for c in range(n_cells + 1)], name="cell_id"))
    return ChromData(np.asarray(xyz, float), spots, cells=cells, uns={"xyz_unit": "um"})


def _expected_coords(cd, p: SeparationParams, unit="cell_id", chroms=("chr1", "chr2")):
    df = cd.to_dataframe()
    df = df[df["chrom"].isin(chroms)].dropna(subset=["x", "y", "z"])
    df["mid"] = (df["start"] + df["end"]) / 2
    ranges = {"short": [p.short], "long": [p.long]}
    if p.edges is not None:
        ranges["profile"] = list(zip(p.edges[:-1], p.edges[1:]))
    out = {}
    for u, sub in df.groupby(unit, observed=True):
        vals = {k: [[] for _ in r] for k, r in ranges.items()}
        for _, t in sub.groupby("trace_id", observed=True):
            X, m = t[["x", "y", "z"]].to_numpy(), t["mid"].to_numpy()
            i, j = np.triu_indices(len(t), 1)
            sep, d = np.abs(m[j] - m[i]), np.linalg.norm(X[j] - X[i], axis=1)
            for k, r in ranges.items():
                for q, (a, b) in enumerate(r):
                    vals[k][q] += list(d[(sep >= a) & (sep < b)])
        stat = np.median if p.stat == "median" else np.mean
        row = {"n_traces": sub["trace_id"].nunique(), "n_spots": len(sub)}
        for k in ("short", "long"):
            v = np.asarray(vals[k][0])
            row[f"d_{k}"] = stat(v) if len(v) else np.nan
            row[f"n_pairs_{k}"] = len(v)
            if p.threshold is not None:
                row[f"f_{k}"] = (v < p.threshold).mean() if len(v) else np.nan
        row["log2_short_long"] = np.log2(row["d_long"] / row["d_short"])
        if "profile" in vals:
            row["profile"] = [stat(v) if len(v) else np.nan for v in vals["profile"]]
            row["n_pairs"] = [len(v) for v in vals["profile"]]
        out[str(u)] = row
    return out


P_XYZ = SeparationParams(short=(0.9e6, 2.1e6), long=(5e6, 31e6), edges=[0.5e6, 1.2e6, 3e6, 10e6, 40e6],
                         threshold=4.0)


@pytest.mark.parametrize("stat", ["median", "mean"])
def test_coordinates_match_brute_force_pairs(stat):
    cd = _traced()
    p = SeparationParams(**{**P_XYZ.__dict__, "stat": stat})
    out = separation_profile(cd, params=p, batch=2)                 # several chunks of cells
    want = _expected_coords(cd, p)
    assert list(out.index) == [f"cell{c}" for c in range(8)]
    assert out.loc["cell7"].drop(["n_traces", "n_spots", "n_pairs_short", "n_pairs_long"]).isna().all()
    for c, row in want.items():
        for k, v in row.items():
            if k in ("profile", "n_pairs"):
                continue
            np.testing.assert_allclose(out.loc[c, k], v, rtol=1e-12, err_msg=f"{c} {k}")
        np.testing.assert_allclose(cd.cellm["separation.profile"][int(c[4:])], row["profile"], rtol=1e-12)
        np.testing.assert_array_equal(cd.cellm["separation.n_pairs"][int(c[4:])], row["n_pairs"])
    assert cd.results.record("separation").inputs["chroms"] == ["chr1", "chr2"]


def test_coordinates_backed_match_in_memory(tmp_path):
    cd = _traced()
    path = tmp_path / "traced.chromdata.zarr"
    cd.write(path)
    mem = separation_profile(ChromData.read(path), params=P_XYZ, key_added=None)
    backed = separation_profile(ChromData.read(path, backed=True), params=P_XYZ, batch=3, key_added=None)
    pd.testing.assert_frame_equal(mem, backed, check_exact=True)
    pd.testing.assert_frame_equal(mem.attrs["profile"], backed.attrs["profile"], check_exact=True)
    sub = separation_profile(ChromData.read(path, backed=True), params=P_XYZ, cells=["cell4", "cell1"],
                             key_added=None)
    pd.testing.assert_frame_equal(sub, mem.loc[["cell1", "cell4"]], check_exact=True)


def test_traces_without_cells_are_the_units():
    cd = _traced(n_cells=2, with_cells=False)
    out = separation_profile(cd, params=P_XYZ, key_added=None)
    want = _expected_coords(cd, P_XYZ, unit="trace_id")
    assert out.index.name == "trace_id"
    for t, row in want.items():
        assert out.loc[t, "n_pairs_long"] == row["n_pairs_long"]
        np.testing.assert_allclose(out.loc[t, "d_short"], row["d_short"], rtol=1e-12)


def test_duplicate_spots_as_merged_first():
    from uchrom.im import merge_duplicate_spots

    cd = _traced(nan_frac=0.0)
    extra = cd[np.arange(0, cd.n_spots, 5)]                          # a second spot at some loci
    dup = ChromData(np.r_[cd.coords, extra.coords + 0.3],
                    pd.concat([cd.spots_with_loci()[["chrom", "start", "end", "trace_id", "cell_id"]],
                               extra.spots_with_loci()[["chrom", "start", "end", "trace_id", "cell_id"]]],
                              ignore_index=True), cells=cd.cells)
    p = SeparationParams(**{**P_XYZ.__dict__, "duplicates": "mean"})
    a = separation_profile(dup, params=p, key_added=None)
    b = separation_profile(merge_duplicate_spots(dup, how="mean"), params=P_XYZ, key_added=None)
    autosomes = cd.spots_with_loci()["chrom"].isin(["chr1", "chr2"]).sum()
    assert a["n_spots"].sum() == autosomes                           # one spot per (trace, bin) after merging
    pd.testing.assert_frame_equal(a.loc[b.index], b, rtol=1e-12)    # b: the cells with spots


def test_source_must_be_chosen_when_both_are_present(tmp_path):
    store, _, _ = _map_dataset(tmp_path)
    maps = ChromData.read(store)
    cd = _traced()
    cd.uns["linked_scool"] = maps.uns["linked_scool"]
    with pytest.raises(ValueError, match="both"):
        separation_profile(cd)
    with pytest.raises(ValueError, match="lo < hi"):
        separation_profile(cd, source="coords", params=SeparationParams(short=(2e6, 1e6)))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        separation_profile(cd, source="coords", key_added=None)
