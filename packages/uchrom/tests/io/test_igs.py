"""uchrom.io.read_igs on the IGS tables of Payne et al. 2021 (tests/fixtures/igs: one PGP1 fibroblast and one cell of
a 4-cell embryo, rows as published), checked against the files read with the csv module."""

import csv

import numpy as np
import pytest

from chromdata import ChromData
from uchrom.io import read_igs

from tests import FIXTURES

PGP1 = FIXTURES / "igs" / "Table_S1_pgp1_data_table.csv"
EMBRYO = FIXTURES / "igs" / "Table_S2_embryo_data_table.csv"


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def test_pgp1_reads():
    rows = _rows(PGP1)
    cd = read_igs(PGP1)
    on = [r for r in rows if int(r["hg38_chr"]) <= 24]
    off = [r for r in rows if int(r["hg38_chr"]) > 24]
    assert cd.n_spots == len(on) and len(cd.points["other_reads"]) == len(off) > 0
    assert cd.uns["trace_kind"] == "set" and cd.uns["genome_assembly"] == "hg38" and cd.uns["xyz_unit"] == "um"

    s = cd.spots_with_loci().sort_values("spot_id").reset_index()
    xyz = cd.coords[s["index"].to_numpy()]
    name = {**{str(i): f"chr{i}" for i in range(1, 23)}, "23": "chrX", "24": "chrY"}
    tag = {"0": "none", "1": "h1", "2": "h2"}
    for i, r in enumerate(on):
        assert np.allclose(xyz[i], [float(r["x_um"]), float(r["y_um"]), float(r["z_um"])])
        chrom, pos = name[r["hg38_chr"]], int(r["hg38_pos"])
        assert s.loc[i, "chrom"] == chrom and s.loc[i, "pos"] == pos
        assert s.loc[i, "start"] == pos // 1_000_000 * 1_000_000 and s.loc[i, "end"] - s.loc[i, "start"] == 1_000_000
        assert s.loc[i, "trace_id"] == f"{r['cell_id']}_{chrom}_{tag.get(r['cluster'], 'c' + r['cluster'])}"
    assert set(cd.traces["homolog"]) >= {"h1", "h2", "none"}
    assert cd.traces["n_reads"].sum() == cd.n_spots
    cell = rows[0]["cell_id"]
    assert cd.cells.loc[cell, "n_reads"] == len(rows) and cd.cells.loc[cell, "n_reads_primary"] == len(on)
    assert sorted(cd.points["other_reads"]["chrom_label"]) == sorted(r["hg38_chr"] for r in off)
    assert "purity_score" in cd.spot_tracks.columns and "mle_cluster" in cd.spots.columns
    assert {"umi_rol", "umi_cs"} <= set(cd.spots.columns) and "umi_rol" not in cd.spot_tracks.columns


def test_embryo_territories_by_parent():
    rows = _rows(EMBRYO)
    cd = read_igs(EMBRYO)
    assert cd.uns["genome_assembly"] == "mm10"
    cell = f"e{rows[0]['embryo_id']}.{rows[0]['cell_id']}"
    assert list(cd.cells.index) == [cell]
    assert cd.cells.loc[cell, "stage"] == rows[0]["stage"] and cd.cells.loc[cell, "embryo"] == int(rows[0]["embryo_id"])

    def homolog(r):
        c, p = int(r["cluster"]), int(r["cluster_hap_imputed"])
        if c in (1, 2) and p in (0, 1):
            return "mat" if p == 0 else "pat"
        return {1: "h1", 2: "h2", 0: "none", -1: "overlap"}.get(c, f"c{c}")

    primary = [r for r in rows if r["chr_name"] in {f"chr{i}" for i in range(1, 20)} | {"chrX", "chrY"}]
    want = sorted(f"{cell}_{r['chr_name']}_{homolog(r)}" for r in primary)
    assert sorted(cd.spots["trace_id"].astype(str)) == want
    assert set(cd.traces["homolog"]) >= {"mat", "pat", "h1", "h2", "overlap"}
    other = [r for r in rows if r not in primary]
    assert sorted(cd.points["other_reads"]["chrom_label"]) == sorted(r["chr_name"] for r in other)
    assert {"dist_to_lamin", "gc"} <= set(cd.spot_tracks.columns)
    assert {"cluster_hap_imputed", "umi_seq"} <= set(cd.spots.columns)


def test_resolution_and_round_trip(tmp_path):
    fine = read_igs(EMBRYO, resolution=100_000).spots_with_loci()
    assert (fine["start"] == fine["pos"] // 100_000 * 100_000).all()
    cd = read_igs(EMBRYO)
    s = cd.spots_with_loci()
    assert (cd.bins["resolution"] == 1_000_000).all()
    assert s.duplicated(["trace_id", "bin_id"]).any()          # a set: several reads of one bin in a territory
    cd.write(tmp_path / "igs.chromdata.zarr")
    back = ChromData.read(tmp_path / "igs.chromdata.zarr", original_order=True)
    assert np.array_equal(back.coords, cd.coords)
    assert back.uns["trace_kind"] == "set" and len(back.points["other_reads"]) == len(cd.points["other_reads"])
    cols = ["chrom", "start", "trace_id", "cell_id", "pos"]
    assert back.spots_with_loci()[cols].astype(str).equals(s[cols].astype(str))


def test_not_an_igs_table(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="not an IGS data table"):
        read_igs(p)
