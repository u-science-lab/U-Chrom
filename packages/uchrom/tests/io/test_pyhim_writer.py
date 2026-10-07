"""uchrom.io.write_pyhim_trace (PyHiM ECSV) and read_bintu_tracing(keep_missing=)."""

import numpy as np
import pandas as pd
import pytest

from uchrom.io import read_bintu_tracing, write_pyhim_trace

pytest.importorskip("astropy")


def _bintu_csv(path):
    rows = ["Chromosome index,Segment index,Z,X,Y"]
    for chrom_idx in (1, 2):
        for seg in (1, 2, 3):
            if chrom_idx == 2 and seg == 2:
                rows.append(f"{chrom_idx},{seg},,,")                       # not detected
            else:
                rows.append(f"{chrom_idx},{seg},{10.0 * seg},{1000.0 * chrom_idx + seg},{2000.0 + seg}")
    path.write_text("IMR90 chr21 toy, coordinates in nm\n" + "\n".join(rows) + "\n")
    return path


def test_read_bintu_keeps_or_drops_undetected_segments(tmp_path):
    csv = _bintu_csv(tmp_path / "toy.csv")
    dropped = read_bintu_tracing(csv, chrom="chr21", start_bp=1000, resolution_bp=100)
    kept = read_bintu_tracing(csv, chrom="chr21", start_bp=1000, resolution_bp=100, keep_missing=True)
    assert dropped.n_spots == 5 and kept.n_spots == 6
    assert np.isnan(kept.coords).any(axis=1).sum() == 1
    assert kept.n_bins == 3 and kept.bins["start"].tolist() == [1000, 1100, 1200]


def test_round_trip_through_from_pyhim_trace(tmp_path):
    from chromdata import ChromData

    cd = read_bintu_tracing(_bintu_csv(tmp_path / "toy.csv"), chrom="chr21", start_bp=1000, resolution_bp=100,
                            keep_missing=True)
    path = write_pyhim_trace(cd, tmp_path / "toy.ecsv", comments={"source": "toy"})
    assert path == tmp_path / "toy.ecsv"
    back = ChromData.from_pyhim_trace(path)
    assert back.uns["xyz_unit"] == "micron" and back.uns["genome_assembly"] == "hg38"
    assert back.uns["pyhim"]["ecsv_comments"] == ["xyz_unit=micron", "genome_assembly=hg38", "source=toy"]
    np.testing.assert_array_equal(back.coords, cd.coords / 1000)          # nm -> um, NaN rows kept
    sp = back.spots
    assert sp["spot_id"].astype(str).tolist() == ["1_1", "1_2", "1_3", "2_1", "2_2", "2_3"]
    assert sp["barcode"].tolist() == [1, 2, 3, 1, 2, 3]                     # locus number on the chromosome
    assert sp["cell_id"].astype(str).tolist() == ["1", "1", "1", "2", "2", "2"]
    assert (sp["roi_id"] == 0).all() and (sp["label"] == "None").all()
    a, b = cd.to_dataframe(), back.to_dataframe()
    assert a["start"].tolist() == b["start"].tolist() and a["trace_id"].astype(str).tolist() == b["trace_id"].astype(str).tolist()


def test_without_loci_needs_a_barcode_dict(tmp_path):
    from chromdata import ChromData

    cd = read_bintu_tracing(_bintu_csv(tmp_path / "toy.csv"), chrom="chr21", start_bp=1000, resolution_bp=100)
    path = write_pyhim_trace(cd, tmp_path / "noloci.ecsv", loci=False)
    with pytest.raises(ValueError, match="barcode_dict"):
        ChromData.from_pyhim_trace(path)
    panel = pd.DataFrame({"barcode": [1, 2, 3], "chrom": "chr21", "start": [1000, 1100, 1200], "end": [1100, 1200, 1300]})
    back = ChromData.from_pyhim_trace(path, barcode_dict=panel)
    assert back.to_dataframe()["start"].tolist() == cd.to_dataframe()["start"].tolist()


def test_spot_columns_and_units_are_honoured(tmp_path):
    from chromdata import ChromData

    spots = pd.DataFrame({"chrom": "chr2", "start": [0, 50, 0], "end": [50, 100, 50], "trace_id": ["a", "a", "b"],
                          "cell_id": ["c1", "c1", "c2"], "spot_id": ["s1", "s2", "s3"], "barcode": [7, 8, 7],
                          "roi_id": [3, 3, 4], "label": ["x", "y", "z"]})
    cd = ChromData(np.arange(9, dtype=float).reshape(3, 3), spots, uns={"xyz_unit": "um"})
    back = ChromData.from_pyhim_trace(write_pyhim_trace(cd, tmp_path / "t.ecsv"))
    np.testing.assert_array_equal(back.coords, cd.coords)
    for c in ("spot_id", "barcode", "roi_id", "label"):
        assert back.spots[c].astype(str).tolist() == spots[c].astype(str).tolist()
    assert back.spots["cell_id"].astype(str).tolist() == ["c1", "c1", "c2"]
    cd.uns["xyz_unit"] = "parsec"
    with pytest.raises(ValueError, match="xyz_unit"):
        write_pyhim_trace(cd, tmp_path / "bad.ecsv")
