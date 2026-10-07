"""uchrom.io.read_seqfish_detections: raw DNA seqFISH+ detections (Takei et al. 2021 Zenodo layouts)."""

import zipfile

import numpy as np
import pandas as pd
import pytest

from uchrom.io import read_seqfish_detections

LOCI_25KB = pd.DataFrame({"chrom": ["chr1", "chr1", "chrX"], "region": [1, 2, 1],
                          "start": [1000, 2000, 5000], "end": [2000, 3000, 6000]})


def _table_25kb():
    return pd.DataFrame({
        "fov": [0, 0, 0, 1, 1], "channel": [3, 3, 3, 1, 1], "cellID": [1, 1, 1, 1, 1],
        "regionID (hyb1-60)": [1, 2, 2, 1, 1], "x": [10.0, 11.0, 30.0, 5.0, 6.0], "y": [1.0, 2.0, 3.0, 4.0, 5.0],
        "z": [2.0, 2.5, 3.0, 1.0, 1.0], "dot_intensity": [600, 700, 200, 300, 400],
        "chr1_intensity": [10, 20, 30, 40, 50], "chromID": [1, 1, 1, 20, 20], "labelID": [0, 0, 1, -1, 0]})


def test_25kb_layout_from_a_zip(tmp_path):
    raw = _table_25kb()
    zpath = tmp_path / "DNAseqFISH+.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("DNAseqFISH+/toy-25kb.csv", raw.to_csv(index=False))
    cd = read_seqfish_detections(zpath, member="toy-25kb.csv", loci=LOCI_25KB)       # basename is enough
    assert cd.n_spots == 5 and cd.n_bins == 3 and cd.n_cells == 2
    np.testing.assert_array_equal(cd.coords, raw[["x", "y", "z"]].to_numpy() * [103.0, 103.0, 250.0])
    sp = cd.spots_with_loci()
    assert sp["cell_id"].astype(str).tolist() == ["0_1", "0_1", "0_1", "1_1", "1_1"]
    assert sp["trace_id"].astype(str).tolist() == ["0_1_chr1"] * 3 + ["1_1_chrX"] * 2   # untraced candidate sets
    assert sp["start"].tolist() == [1000, 2000, 2000, 5000, 5000]
    assert sp["spot_id"].tolist() == [0, 1, 2, 3, 4]
    assert sp["label"].tolist() == [0, 0, 1, -1, 0] and sp["region"].tolist() == [1, 2, 2, 1, 1]
    assert cd.spot_tracks.columns.tolist() == ["dot_intensity", "chr1_intensity"]
    assert cd.uns["xyz_unit"] == "nm" and cd.cells.loc["1_1", "fov"] == 1


def test_csv_path_named_loci_and_errors(tmp_path):
    raw = pd.DataFrame({"fov": [0, 0], "cellID": [4, 4], "channel": [1, 1], "geneID": ["chr1-#1", "Satb2"],
                        "x": [1.0, 2.0], "y": [1.0, 2.0], "z": [1.0, 2.0], "seeds": [5, 4], "intensity": [9, 8]})
    path = tmp_path / "toy-1mb.csv"
    raw.to_csv(path, index=False)
    loci = pd.DataFrame({"name": ["chr1-#1", "Satb2"], "chrom": ["chr1", "chr1"], "start": [0, 1_000_000],
                         "end": [1_000_000, 2_000_000]})
    cd = read_seqfish_detections(path, loci=loci, voxel_nm=(100, 100, 200), cell_prefix="rep1_")
    assert cd.spots["name"].tolist() == ["chr1-#1", "Satb2"]
    assert cd.spots["cell_id"].astype(str).tolist() == ["rep1_0_4"] * 2
    np.testing.assert_array_equal(cd.coords[1], [200.0, 200.0, 400.0])
    assert "label" not in cd.spots.columns and cd.spot_tracks.columns.tolist() == ["seeds", "intensity"]
    with pytest.raises(ValueError, match="missing from loci"):
        read_seqfish_detections(path, loci=loci.iloc[:1])
    with pytest.raises(ValueError, match="member"):
        zp = tmp_path / "x.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("a.csv", raw.to_csv(index=False))
        read_seqfish_detections(zp, loci=loci)
