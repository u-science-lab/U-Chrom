"""uchrom.io.read_snapfish: SnapFISH / SnapFISH-IMPUTE coordinate + annotation tables."""

import numpy as np
import pandas as pd
import pytest

from uchrom.io import read_snapfish

STARTS = [34_601_078, 34_606_078, 34_611_078, 34_616_078]


def _tables():
    ann = pd.DataFrame({"region": ["129"] * 4 + ["CAST"] * 4, "pos": [1, 2, 3, 4] * 2,
                        "start": STARTS * 2, "end": [s + 5000 for s in STARTS] * 2})
    rows = []
    for region in ("129", "CAST"):
        for h in ("cell_id.7", "cell_id.3"):                      # not sorted: file order must be kept
            for pos in (1, 2, 3, 4):
                v = 100.0 * pos + (0 if region == "129" else 10) + (1 if h.endswith("3") else 0)
                missing = (pos == 2 and h.endswith("7")) or (pos == 4 and region == "129")
                rows.append((region, h, pos, *([np.nan] * 3 if missing else [v, v + 1, v + 2])))
    coor = pd.DataFrame(rows, columns=["region", "haploid", "pos", "x", "y", "z"])
    return coor, ann


def test_regions_as_chromosomes_by_default(tmp_path):
    coor, ann = _tables()
    coor.to_csv(tmp_path / "coor.txt", sep="\t", index=False)
    ann.to_csv(tmp_path / "ann.txt", sep="\t", index=False)
    cd = read_snapfish(tmp_path / "coor.txt", tmp_path / "ann.txt")
    assert cd.n_spots == 16 and cd.n_traces == 4 and cd.n_bins == 8
    assert sorted(cd.chroms) == ["129", "CAST"]
    assert cd.spots["trace_id"].astype(str).tolist()[:5] == ["cell_id.7_129"] * 4 + ["cell_id.3_129"]
    np.testing.assert_array_equal(cd.coords, coor[["x", "y", "z"]].to_numpy())      # file order, NaN rows kept
    assert cd.spots["pos"].tolist() == coor["pos"].tolist()
    assert "cell_id" not in cd.spots.columns
    assert cd.traces.loc["cell_id.7_129", "n_detected"] == 2 and cd.traces.loc["cell_id.7_129", "n_loci"] == 4
    assert cd.uns["xyz_unit"] == "nm" and "genome_assembly" not in cd.uns


def test_alleles_of_one_chromosome_with_cells():
    coor, ann = _tables()
    coor["haploid"] = coor["haploid"].str.removeprefix("cell_id.")
    cd = read_snapfish(coor, ann, chrom="chr3", region_name="allele", cell_id=True, genome_assembly="mm10")
    assert cd.n_bins == 4 and cd.chroms == ["chr3"]                  # both alleles share the locus axis
    assert cd.bins["start"].tolist() == STARTS
    assert cd.cells.index.tolist() == ["7", "3"]                     # in the table's order
    assert set(cd.spots["allele"]) == {"129", "CAST"}
    assert cd.traces.loc["3_CAST", "cell_id"] == "3" and cd.traces.loc["3_CAST", "allele"] == "CAST"
    one = cd.get_trace("3_CAST").to_dataframe()
    assert one["x"].tolist() == [111.0, 211.0, 311.0, 411.0]
    assert cd.uns["genome_assembly"] == "mm10"


def test_drop_missing_keeps_the_whole_panel_and_snapfish_column_names():
    coor, ann = _tables()
    coor = coor.rename(columns={"region": "chr", "haploid": "cell_id"})      # SnapFISH's own names
    ann = ann.rename(columns={"region": "chr"})
    cd = read_snapfish(coor, ann, keep_missing=False, cell_id=lambda h: h.split(".")[1])
    assert not np.isnan(cd.coords).any()
    assert cd.n_spots == int(coor["x"].notna().sum())
    assert cd.n_bins == 8                                              # chr 129, pos 4: never detected, still a bin
    assert set(cd.spots["cell_id"].astype(str)) == {"7", "3"}


def test_mismatched_tables_raise():
    coor, ann = _tables()
    with pytest.raises(ValueError, match="annotation"):
        read_snapfish(coor, ann[ann["pos"] != 3])
    with pytest.raises(ValueError, match="does not map"):
        read_snapfish(coor, ann, chrom={"129": "chr3"})
    with pytest.raises(ValueError, match="misses"):
        read_snapfish(coor.drop(columns="pos"), ann)
