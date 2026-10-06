"""Readers / writers for the sequencing-side formats."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from tests import REPO

DATA = REPO / "example-data"


def _particles(n=12):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "chrom": ["chr1"] * (n // 2) + ["chr2"] * (n - n // 2),
        "start": np.r_[np.arange(n // 2), np.arange(n - n // 2)] * 1000,
    })
    df["end"] = df["start"] + 1000
    df[["x", "y", "z"]] = rng.normal(size=(n, 3))
    return df


def test_read_pairs_cell1():
    from uchrom.io import read_pairs

    path = DATA / "cell1.pairs"
    if not path.exists():
        pytest.skip("cell1.pairs missing")
    df = read_pairs(str(path))
    assert list(df.columns) == ["read", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    assert len(df) == 105_700
    assert pd.api.types.is_string_dtype(df["chr1"])      # object (pandas 2) or str (pandas 3)


def test_read_pairs_gz_with_header(tmp_path):
    import gzip
    from uchrom.io import read_pairs

    p = tmp_path / "x.pairs.gz"
    with gzip.open(p, "wt") as f:
        f.write("## pairs format v1.0\n#columns: readID chr1 pos1 chr2 pos2 strand1 strand2\n")
        f.write("r1\tchr1\t100\tchr1\t500\t+\t-\n")
        f.write("r2\t1\t200\t2\t900\t-\t+\n")
    df = read_pairs(str(p))
    assert len(df) == 2
    assert list(df["chr2"]) == ["chr1", "2"]      # ints coerced to str


def test_load_cool_pixels():
    from uchrom.io import load_cool

    path = DATA / "K562_chr21_30kb.cool"
    if not path.exists():
        pytest.skip("K562 cool missing")
    px = load_cool(str(path))
    assert {"chr1", "start1", "chr2", "start2", "count", "pos1", "pos2"} <= set(px.columns)
    assert (px["chr1"] == "chr21").all()
    assert (px["pos1"] == (px["start1"] + px["end1"]) / 2).all()
    assert (px["count"] > 0).all()


def test_read_3dg(tmp_path):
    from uchrom.io import read_3dg

    p = tmp_path / "x.3dg"
    p.write_text("# comment\nchr1(pat)\t0\t1.0\t2.0\t3.0\nchr1(pat)\t20000\t1.5\t2.5\t3.5\n")
    df = read_3dg(str(p))
    assert list(df.columns) == ["chrom", "start", "x", "y", "z"]
    assert df.shape == (2, 5)
    assert df.loc[1, "z"] == 3.5


@pytest.mark.parametrize("ext", [".csv", ".chromdata.zarr", ".cdz"])
def test_particles_roundtrip(tmp_path, ext):
    from uchrom.io import read_particles, save_particles

    df = _particles()
    p = tmp_path / f"p{ext}"
    save_particles(df, p)
    back = read_particles(p)
    assert np.allclose(back[["x", "y", "z"]].to_numpy(), df[["x", "y", "z"]].to_numpy())
    assert list(back["chrom"]) == list(df["chrom"])


def test_particles_refuse_h5cd(tmp_path):
    from uchrom.io import read_particles, save_particles

    with pytest.raises(ValueError, match="no longer supported"):
        save_particles(_particles(), tmp_path / "p.h5cd")
    (tmp_path / "q.h5cd").write_bytes(b"\x89HDF\r\n\x1a\n")
    with pytest.raises(ValueError, match="uchrom.io.upgrade"):
        read_particles(tmp_path / "q.h5cd")


def test_particles_to_pdb_split_by_chrom(tmp_path):
    from uchrom.io import particles_to_pdb, save_particles

    src = tmp_path / "p.csv"
    save_particles(_particles(), src)
    particles_to_pdb(str(src), str(tmp_path / "out.pdb"))
    lines = (tmp_path / "out.pdb").read_text().splitlines()
    assert sum(l.startswith("HETATM") for l in lines) == 12

    particles_to_pdb(str(src), str(tmp_path / "s.pdb"), split_by_chrom=True)
    for c in ("chr1", "chr2"):
        txt = (tmp_path / f"s.{c}.pdb").read_text()
        assert sum(l.startswith("HETATM") for l in txt.splitlines()) == 6
