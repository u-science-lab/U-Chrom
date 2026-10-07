"""uchrom.im.trace: align_spots on a ChromData of detections, and score_alignment."""

import numpy as np
import pandas as pd
import pytest

from uchrom.im.trace import SpotAlignerParams, align_spots, score_alignment

PARAMS = SpotAlignerParams(max_skip=4, min_spots_per_fiber=5, max_fibers_per_chrom=3, detect_sisters=False)


def _detections(n_cells=4, n_loci=20, seed=0):
    """Two well separated Gaussian-chain homologs per (cell, chromosome), a few loci dropped (nm)."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_cells):
        for chrom in ("chr1", "chr2"):
            for h in (0, 1):
                walk = np.cumsum(rng.normal(0, 60, (n_loci, 3)), axis=0) + rng.normal(0, 4000, 3)
                for i in np.flatnonzero(rng.random(n_loci) > 0.1):
                    rows.append({"cell_id": f"0_{c}", "chrom": chrom, "start": 25_000 * i, "end": 25_000 * (i + 1),
                                 "x": walk[i, 0], "y": walk[i, 1], "z": walk[i, 2], "label": h})
    df = pd.DataFrame(rows)
    df["label"] = df["label"].where(rng.random(len(df)) > 0.05, -1)          # some rejected upstream
    df.insert(0, "spot_id", np.arange(len(df)))
    return df


def _as_chromdata(df, unit="nm"):
    from chromdata import ChromData

    spots = df[["chrom", "start", "end", "cell_id", "spot_id", "label"]].copy()
    spots["trace_id"] = df["cell_id"] + "_" + df["chrom"]                       # untraced candidate sets
    scale = 1000.0 if unit == "micron" else 1.0
    return ChromData(df[["x", "y", "z"]].to_numpy() / scale, spots,
                     spot_tracks=pd.DataFrame({"intensity": np.arange(len(df), dtype=float)}),
                     uns={"xyz_unit": unit, "source": "toy"})


def test_chromdata_input_matches_the_table_and_keeps_the_object():
    df = _detections()
    cd = _as_chromdata(df)
    a = align_spots(df[["spot_id", "cell_id", "chrom", "start", "end", "x", "y", "z"]], params=PARAMS)
    b = align_spots(cd, params=PARAMS)
    order = np.argsort(b.spots["spot_id"].to_numpy())
    oa = np.argsort(a.spots["spot_id"].to_numpy())
    np.testing.assert_array_equal(a.spots["spot_id"].to_numpy()[oa], b.spots["spot_id"].to_numpy()[order])
    np.testing.assert_array_equal(a.coords[oa], b.coords[order])
    assert a.spots["trace_id"].astype(str).to_numpy()[oa].tolist() == b.spots["trace_id"].astype(str).to_numpy()[order].tolist()
    # the result keeps the input's locus axis, spot columns, spot tracks and uns
    assert b.bins.equals(cd.bins)
    ids = b.spots["spot_id"].to_numpy()
    assert (b.spots["label"].to_numpy() == df.set_index("spot_id").loc[ids, "label"].to_numpy()).all()
    np.testing.assert_array_equal(b.spot_tracks["intensity"].to_numpy(), ids.astype(float))
    assert b.uns["source"] == "toy" and "jie_polymer" in b.uns and "ploidy" in b.results


def test_micron_input_is_aligned_in_nm_and_returned_in_micron():
    df = _detections()
    nm = align_spots(_as_chromdata(df), params=PARAMS)
    um = align_spots(_as_chromdata(df, unit="micron"), params=PARAMS)
    assert um.uns["xyz_unit"] == "micron"
    np.testing.assert_allclose(um.coords * 1000, nm.coords)
    assert um.spots["trace_id"].tolist() == nm.spots["trace_id"].tolist()


def test_chrom_and_cells_restrict_the_alignment():
    cd = _as_chromdata(_detections())
    res = align_spots(cd, chrom="chr2", cells=["0_1", "0_2"], params=PARAMS)
    assert set(res.spots["chrom"].astype(str)) == {"chr2"}
    assert set(res.spots["cell_id"].astype(str)) <= {"0_1", "0_2"}
    assert len(res.results["ploidy"]) == 2


def test_score_alignment_against_the_labels():
    df = _detections()
    cd = _as_chromdata(df)
    res = align_spots(cd, params=PARAMS)
    s = score_alignment(res, cd, label="label")
    assert s["purity"] > 0.95 and s["assigned"] > 0.8 and s["median ARI"] > 0.8
    assert s["n_spots"] == (df["label"] >= 0).sum()
    per = score_alignment(res, cd, label="label", per="chrom")
    assert sorted(per.index) == ["chr1", "chr2"] and {"assigned", "purity", "median ARI"} <= set(per.columns)
    # a reference with more chromosomes than were aligned: only the aligned (cell, chromosome) groups count
    one = align_spots(cd, chrom="chr1", params=PARAMS)
    s1 = score_alignment(one, cd, label="label")
    assert s1["n_spots"] == ((df["label"] >= 0) & (df["chrom"] == "chr1")).sum()
    # a perfect alignment: the labels themselves as fibres
    perfect = cd[(cd.spots["label"] >= 0).to_numpy()]
    perfect.spots["trace_id"] = (perfect.spots["cell_id"].astype(str) + "_" + perfect.spots["chrom"].astype(str)
                                 + "_" + perfect.spots["label"].astype(str))
    p = score_alignment(perfect, df, label="label")
    assert p["assigned"] == 1.0 and p["purity"] == 1.0 and p["median ARI"] == 1.0
    with pytest.raises(ValueError, match="per"):
        score_alignment(res, cd, label="label", per="cell")
