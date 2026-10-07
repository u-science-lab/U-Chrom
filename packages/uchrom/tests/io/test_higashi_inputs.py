"""Tests for Higashi input format writers (uchrom.io.contacts).

Higashi v2 expects:
- Per-cell contact files with columns: chrom1, pos1, chrom2, pos2, count
- A filelist.txt pointing at those files (with cell_name + path)
- label_info.pickle — dict of per-cell metadata arrays
- config.JSON — genome/resolution/chrom_list + paths
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def test_pairs_df_to_higashi_converts_columns_and_dedups():
    """read_pairs-style DataFrame -> higashi (chrom1, pos1, chrom2, pos2, count)."""
    from uchrom.io.contacts import pairs_df_to_higashi

    pairs = pd.DataFrame({
        "read": ["r1", "r2", "r3", "r4"],
        "chr1": ["chr1", "chr1", "chr1", "chr2"],
        "pos1": [3_165_000, 3_165_000, 100, 500],
        "chr2": ["chr1", "chr1", "chr1", "chr2"],
        "pos2": [10_790_000, 10_790_000, 200, 800],
        "strand1": ["+", "-", "+", "+"],
        "strand2": ["+", "-", "+", "+"],
    })

    out = pairs_df_to_higashi(pairs, resolution=1_000_000)

    assert list(out.columns) == ["chrom1", "pos1", "chrom2", "pos2", "count"]
    # rows 1 and 2 land in the same 1 Mb bin-pair → collapsed with count=2
    assert len(out) == 3
    dup = out[(out.chrom1 == "chr1") & (out.pos1 == 3_000_000)
              & (out.pos2 == 10_000_000)]
    assert len(dup) == 1
    assert int(dup["count"].iloc[0]) == 2


def test_pairs_df_to_higashi_orders_endpoints():
    """For intra-chrom contacts, (pos1, pos2) is sorted so pos1 <= pos2."""
    from uchrom.io.contacts import pairs_df_to_higashi

    pairs = pd.DataFrame({
        "read": ["r1"],
        "chr1": ["chr1"], "pos1": [10_000_000],
        "chr2": ["chr1"], "pos2": [3_000_000],
        "strand1": ["+"], "strand2": ["+"],
    })
    out = pairs_df_to_higashi(pairs, resolution=1_000_000)
    assert int(out["pos1"].iloc[0]) <= int(out["pos2"].iloc[0])


def test_make_higashi_config_has_required_fields(tmp_path):
    """config.JSON must carry genome / resolution / chrom_list / data_dir."""
    from uchrom.io.contacts import make_higashi_config

    cfg = make_higashi_config(
        data_dir=str(tmp_path),
        genome_reference="mm10",
        resolution=1_000_000,
        chrom_list=["chr1", "chr2", "chr3"],
        temp_dir=str(tmp_path / "tmp"),
    )

    assert cfg["genome_reference"] == "mm10"
    assert cfg["resolution"] == 1_000_000
    assert cfg["chrom_list"] == ["chr1", "chr2", "chr3"]
    assert cfg["data_dir"] == str(tmp_path)
    assert cfg["temp_dir"] == str(tmp_path / "tmp")
    assert cfg["input_format"] == "higashi_v2"
    # cell_feats required by label_info contract; default empty list ok
    assert "cell_feats" in cfg


def test_make_higashi_config_merges_overrides(tmp_path):
    """Extra kwargs override defaults without clobbering required fields."""
    from uchrom.io.contacts import make_higashi_config

    cfg = make_higashi_config(
        data_dir=str(tmp_path),
        genome_reference="hg38",
        resolution=500_000,
        chrom_list=["chr1"],
        overrides={"coassay": True, "resolution": 250_000},
    )
    # override wins over default
    assert cfg["resolution"] == 250_000
    assert cfg["coassay"] is True
    assert cfg["genome_reference"] == "hg38"


def test_write_label_info_roundtrips_columns(tmp_path):
    """cells DataFrame -> label_info.pickle as dict[col] -> ndarray, order preserved."""
    from uchrom.io.contacts import write_label_info

    cells = pd.DataFrame({
        "cell_name": ["c1", "c2", "c3"],
        "cell_type": ["GM", "GM", "K562"],
        "batch": [0, 0, 1],
    })

    out_path = write_label_info(cells, tmp_path / "label_info.pickle")

    assert out_path.exists()
    with open(out_path, "rb") as f:
        obj = pickle.load(f)
    assert set(obj.keys()) == {"cell_name", "cell_type", "batch"}
    assert list(obj["cell_name"]) == ["c1", "c2", "c3"]
    assert list(obj["cell_type"]) == ["GM", "GM", "K562"]
    assert list(obj["batch"]) == [0, 0, 1]
    # each value is an ndarray (Higashi's expectation)
    for v in obj.values():
        assert isinstance(v, np.ndarray)


def _make_pairs_file(path, rows):
    """Write a minimal .pairs file (tab-separated, no header, comment-friendly)."""
    cols = ["read", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(path, sep="\t", index=False, header=False)


def test_write_higashi_inputs_produces_expected_files(tmp_path):
    """End-to-end: dict of .pairs → filelist.txt + per-cell txt + label_info + config."""
    from uchrom.io.contacts import write_higashi_inputs

    # two tiny synthetic cells
    p1 = tmp_path / "cell1.pairs"
    p2 = tmp_path / "cell2.pairs"
    _make_pairs_file(p1, [
        ["r1", "chr1", 3_000_100, "chr1", 10_500_000, "+", "+"],
        ["r2", "chr1", 3_000_200, "chr1", 10_500_500, "+", "-"],  # same 1Mb bin
        ["r3", "chr1", 5_000_000, "chr2", 2_000_000, "+", "+"],
    ])
    _make_pairs_file(p2, [
        ["r4", "chr1", 7_000_000, "chr1", 8_000_000, "+", "+"],
    ])

    cells = pd.DataFrame({
        "cell_name": ["c1", "c2"],
        "cell_type": ["A", "B"],
    })

    out_dir = tmp_path / "higashi"
    result = write_higashi_inputs(
        pairs_files={"c1": p1, "c2": p2},
        out_dir=out_dir,
        label_info=cells,
        resolution=1_000_000,
        genome_reference="mm10",
        chrom_list=["chr1", "chr2"],
    )

    assert (out_dir / "filelist.txt").exists()
    assert (out_dir / "label_info.pickle").exists()
    assert (out_dir / "config.JSON").exists()

    # FastHigashi v2 contract: filelist.txt is ONE path per line, in
    # label_info row order (no cell_name prefix).
    filelist = (out_dir / "filelist.txt").read_text().strip().splitlines()
    assert len(filelist) == 2
    for line in filelist:
        assert "\t" not in line
        assert Path(line).exists()

    # per-cell file is higashi-formatted (no header — header_included=False)
    c1_path = filelist[0]
    c1_df = pd.read_csv(c1_path, sep="\t", header=None,
                        names=["chrom1", "pos1", "chrom2", "pos2", "count"])
    # r1+r2 collapsed to count=2 at chr1:3Mb-10Mb
    collapsed = c1_df[(c1_df.chrom1 == "chr1") & (c1_df.pos1 == 3_000_000)]
    assert int(collapsed["count"].iloc[0]) == 2

    # config.JSON points at out_dir and has the FastHigashi-required fields
    cfg = json.loads((out_dir / "config.JSON").read_text())
    assert cfg["resolution"] == 1_000_000
    assert cfg["chrom_list"] == ["chr1", "chr2"]
    assert Path(cfg["data_dir"]) == out_dir
    assert cfg["input_format"] == "higashi_v2"
    assert cfg["header_included"] is False
    assert cfg["contact_header"] == ["chrom1", "pos1", "chrom2", "pos2", "count"]

    # return value is the out_dir
    assert Path(result) == out_dir


def test_write_higashi_inputs_rejects_mismatched_labels(tmp_path):
    """If label_info rows don't match pairs_files keys we fail loudly."""
    from uchrom.io.contacts import write_higashi_inputs

    p1 = tmp_path / "cell1.pairs"
    _make_pairs_file(p1, [["r1", "chr1", 0, "chr1", 1_000_000, "+", "+"]])
    cells = pd.DataFrame({"cell_name": ["c1", "MISSING"]})

    with pytest.raises(ValueError, match="cell_name"):
        write_higashi_inputs(
            pairs_files={"c1": p1},
            out_dir=tmp_path / "higashi",
            label_info=cells,
            resolution=1_000_000,
            genome_reference="mm10",
            chrom_list=["chr1"],
        )


def test_write_higashi_inputs_emits_chromsizes_when_dict_given(tmp_path):
    """A {chrom: size} mapping is materialised to chromsizes.tsv and config
    points at it. FastHigashi reads this at ``fast_process_data`` time."""
    from uchrom.io.contacts import write_higashi_inputs

    p1 = tmp_path / "cell1.pairs"
    _make_pairs_file(p1, [["r1", "chr1", 0, "chr1", 1_000_000, "+", "+"]])

    out_dir = write_higashi_inputs(
        pairs_files={"c1": p1},
        out_dir=tmp_path / "higashi",
        label_info=pd.DataFrame({"cell_name": ["c1"]}),
        resolution=1_000_000,
        genome_reference="mm10",
        chrom_list=["chr1"],
        chromsizes={"chr1": 195_000_000, "chr2": 182_000_000},
    )

    sizes_path = out_dir / "chromsizes.tsv"
    assert sizes_path.exists()
    content = sizes_path.read_text().strip().splitlines()
    assert content == ["chr1\t195000000", "chr2\t182000000"]

    cfg = json.loads((out_dir / "config.JSON").read_text())
    assert Path(cfg["genome_reference_path"]) == sizes_path
