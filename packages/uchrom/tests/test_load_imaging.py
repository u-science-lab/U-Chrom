"""Imaging loaders of ``uchrom.datasets`` (``_load_imaging``): Huang 2021 Sox2 (SnapFISH-IMPUTE tables) and
the Takei 2021 raw seqFISH+ detections, built offline from miniatures of their original files, and checked
on the real files when they are in the data directory."""

import zipfile

import numpy as np
import pandas as pd
import pytest

import uchrom.datasets as ds

from tests import DATA_DIR


def _mini_sox2(folder):
    folder.mkdir(parents=True)
    starts = [34_601_078, 34_606_078, 34_611_078]
    ann = pd.DataFrame({"region": ["129"] * 3 + ["CAST"] * 3, "pos": [1, 2, 3] * 2, "start": starts * 2,
                        "end": [s + 5000 for s in starts] * 2})
    rows = [(r, f"cell_id.{c}", p, *([np.nan] * 3 if (c == 26 and p == 2) else [float(p), float(c), 1.0]))
            for r in ("129", "CAST") for c in (11, 26) for p in (1, 2, 3)]
    coor = pd.DataFrame(rows, columns=["region", "haploid", "pos", "x", "y", "z"])
    coor.to_csv(folder / "mESC_Sox2_coor_wnan.txt", sep="\t", index=False, na_rep="")
    ann.to_csv(folder / "mESC_Sox2_ann.txt", sep="\t", index=False)


def test_huang2021_sox2_on_a_miniature(monkeypatch, tmp_path):
    from uchrom.datasets import _load_imaging

    folder = tmp_path / "data" / "huang2021_sox2"
    _mini_sox2(folder)
    monkeypatch.setattr(ds, "fetch", lambda name, root=None, **kw: folder)
    cd = _load_imaging.build_huang2021_sox2(tmp_path / "data", folder / "huang2021_sox2.chromdata.zarr")
    assert cd.n_spots == 12 and cd.n_traces == 4 and cd.n_bins == 3 and cd.chroms == ["chr3"]
    assert cd.cells.index.tolist() == ["11", "26"]
    assert sorted(cd.traces.index) == ["11_129", "11_CAST", "26_129", "26_CAST"]
    assert set(cd.spots["allele"]) == {"129", "CAST"}
    assert int(np.isnan(cd.coords[:, 0]).sum()) == 2                 # undetected loci stay NaN rows
    assert cd.uns["genome_assembly"] == "mm10" and cd.uns["xyz_unit"] == "nm"


def _mini_takei(tmp_path):
    """A detection CSV in a zip (the Zenodo layout) and the FOF-CT table that traces the same spots."""
    from chromdata import ChromData

    raw = pd.DataFrame({"fov": [0, 0, 0, 0, 1], "channel": 3, "cellID": [1, 1, 1, 1, 2],
                        "regionID (hyb1-60)": [1, 2, 2, 1, 1], "x": [100.0, 101.0, 140.0, 200.0, 50.0],
                        "y": [10.0, 11.0, 12.0, 13.0, 14.0], "z": [4.0, 5.0, 6.0, 7.0, 8.0],
                        "dot_intensity": [1, 2, 3, 4, 5], "chromID": [1, 1, 1, 20, 1], "labelID": [0, 0, 1, 0, -1]})
    zpath = tmp_path / "DNAseqFISH+.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("DNAseqFISH+/DNAseqFISH+25kbloci-E14-replicate1.csv", raw.to_csv(index=False))
    locus = {(1, 1): (1000, 2000), (1, 2): (2000, 3000), (20, 1): (7000, 8000)}
    chrom = raw["chromID"].map(lambda c: "chrX" if c == 20 else f"chr{c}")
    cell = raw["fov"].astype(str) + "_" + raw["cellID"].astype(str)
    spots = pd.DataFrame({
        "chrom": chrom, "start": [locus[k][0] for k in zip(raw["chromID"], raw["regionID (hyb1-60)"])],
        "end": [locus[k][1] for k in zip(raw["chromID"], raw["regionID (hyb1-60)"])],
        "trace_id": cell + "_" + raw["chromID"].astype(str) + "_" + raw["labelID"].astype(str),
        "cell_id": cell, "spot_id": np.arange(len(raw)) + 100})
    xyz = np.round(raw[["x", "y", "z"]].to_numpy() * [0.103, 0.103, 0.25], 3)
    core = tmp_path / "core.csv"
    ChromData(xyz, spots, uns={"xyz_unit": "micron", "genome_assembly": "mm10"}).to_fofct(core)
    return raw, zpath, core


def test_takei2021_detections_on_a_miniature(monkeypatch, tmp_path):
    from uchrom.datasets import _load_imaging

    raw, zpath, core = _mini_takei(tmp_path)
    monkeypatch.setattr(ds, "fetch", lambda name, root=None, **kw: {"seqfish": zpath, "takei": core}[name])
    cd = _load_imaging.build_takei2021_mesc_detections(tmp_path, tmp_path / "out.chromdata.zarr")
    assert cd.n_spots == 5 and cd.n_bins == 3
    assert cd.uns["locus_map"]["same_cell"] == 1.0 and cd.uns["locus_map"]["label_equals_fofct_homolog"] == 1.0
    sp = cd.spots_with_loci()
    assert sp["start"].tolist() == [1000, 2000, 2000, 7000, 1000]
    assert sp["trace_id"].astype(str).tolist() == ["0_1_chr1"] * 3 + ["0_1_chrX", "1_2_chr1"]
    assert sp["label"].tolist() == [0, 0, 1, 0, -1]
    np.testing.assert_array_equal(cd.coords, raw[["x", "y", "z"]].to_numpy() * [103.0, 103.0, 250.0])


def test_takei2021_locus_map_refuses_a_mismatch(tmp_path):
    from chromdata import ChromData
    from uchrom.datasets._load_imaging import takei2021_locus_map

    raw, _, core = _mini_takei(tmp_path)
    fofct = ChromData.from_fofct(core).to_dataframe()
    moved = raw.assign(x=raw["x"] + 1)
    with pytest.raises(ValueError, match="no FOF-CT spot"):
        takei2021_locus_map(moved, fofct)


def test_the_loaders_are_registered():
    from uchrom.datasets._loaders import loaders

    known = loaders()
    assert {"huang2021_sox2", "takei2021_mesc_detections"} <= set(known)
    assert known["takei2021_mesc_detections"].sources == ("seqfish", "takei")


@pytest.mark.skipif(not (DATA_DIR / "huang2021_sox2" / "mESC_Sox2_coor_wnan.txt").exists(),
                    reason="huang2021_sox2 not in the data directory")
def test_huang2021_sox2_real(tmp_path):
    from uchrom.datasets import _load_imaging

    cd = _load_imaging.build_huang2021_sox2(DATA_DIR, tmp_path / "x.chromdata.zarr")
    assert (cd.n_spots, cd.n_cells, cd.n_traces, cd.n_bins) == (116_112, 1416, 2832, 41)
    assert cd.bins["start"].iloc[0] == 34_601_078 and cd.bins["end"].iloc[-1] == 34_806_078
    # SnapFISH-IMPUTE's preprocessing left locus 26 of the 129 allele empty in every cell
    sp = cd.spots_with_loci()
    blank = (sp["allele"] == "129").to_numpy() & (sp["pos"] == 26).to_numpy()
    assert np.isnan(cd.coords[blank]).all() and blank.sum() == 1416
