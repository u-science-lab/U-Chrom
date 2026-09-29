import gzip
import stat

import numpy as np

from contacts import Grid, ParticleIndex, bin_contacts, contact_pairs, read_contacts, write_contacts, write_pairs
from models_io import nucdyn_chain_map, read_3dg, read_sic_pdb, resample_3dg, save_npz


def test_geo_roundtrip_subset(tmp_path):
    src = tmp_path / "cell.txt.gz"
    lines = ["#chr_A\tpos_A\tchr_B\tpos_B"] + [f"chr{i % 3 + 1}\t{1000 * i + 7}\tchrX\t{5000 * i}" for i in range(50)]
    with gzip.open(src, "wt") as fh:
        fh.write("\n".join(lines) + "\n")
    c = read_contacts(src)
    assert c.fmt == "geo" and len(c) == 50 and c.pos_a[3] == 3007 and c.chrom_b[0] == "chrX"
    keep = np.arange(50) % 4 != 0
    write_contacts(tmp_path / "train.txt.gz", c, keep)
    got = gzip.open(tmp_path / "train.txt.gz", "rt").read().splitlines()
    assert got == [lines[0]] + [l for k, l in enumerate(lines[1:]) if keep[k]]
    assert c.chroms == ["chr1", "chr2", "chr3", "chrX"]


def test_pairs_roundtrip(tmp_path):
    src = tmp_path / "x.pairs"
    txt = "## pairs format v1.0\n#columns: readID chr1 pos1 chr2 pos2 strand1 strand2\n" \
          "r1\tchr2\t100\tchr10\t200\t+\t-\nr2\tchr1\t5\tchr1\t900\t-\t-\n"
    src.write_text(txt)
    c = read_contacts(src)
    assert c.fmt == "pairs" and list(c.chrom_a) == ["chr2", "chr1"] and list(c.pos_b) == [200, 900]
    write_contacts(tmp_path / "y.pairs", c)
    assert (tmp_path / "y.pairs").read_text() == txt
    write_pairs(tmp_path / "z.pairs", c, {"chr1": 1000, "chr2": 1000, "chr10": 1000})
    assert "#chromosome: chr10 1000" in (tmp_path / "z.pairs").read_text()


def test_particle_convention():
    chrom = np.array(["chr1"] * 3 + ["chr2"] * 2)
    pos = np.array([100, 200, 300, 100, 200])            # particle covers (pos - 100, pos]
    p = ParticleIndex(chrom, pos)
    got = p(["chr1", "chr1", "chr1", "chr1", "chr2", "chr3", "chr1"], [1, 100, 101, 300, 150, 50, 301])
    assert got.tolist() == [0, 0, 1, 2, 4, -1, -1]


def test_grid_and_pairs():
    g = Grid({"chr1": (150, 999), "chr2": (0, 250)}, 100)
    assert g.n == 9 + 3 and g.index(["chr1", "chr2", "chr1"], [150, 250, 50]).tolist() == [0, 11, -1]
    assert Grid.from_dict(g.to_dict()).n == g.n
    chrom = np.array(["a"] * 5 + ["b"] * 5)
    pairs, counts = contact_pairs([0, 0, 1, 2, 4, -1], [1, 3, 3, 3, 5, 2], chrom)
    assert pairs.tolist() == [[0, 3], [1, 3], [4, 5]] and counts.tolist() == [1, 1, 1]


def test_bin_contacts(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("chr1 150 chr1 250\nchr1 99999 chr2 1\n")
    c = read_contacts(f)
    i, j = bin_contacts(c, ["chr1", "chr1", "chr2"], [200, 300, 100], 100)
    assert i.tolist() == [0, -1] and j.tolist() == [1, 2]


def test_sic_pdb(tmp_path):
    # the exact printf of cavity2pdb_chain.c
    rows = [("a", 1, 1.0, -2.5, 3.25), ("a", 2, 10.0, 0.0, -1234.5), ("b", 1, 0.5, 0.5, 0.5)]
    with open(tmp_path / "genome.pdb", "w") as fh:
        for k, (ch, rid, x, y, z) in enumerate(rows):
            fh.write("ATOM %6d  C     %c%6d    %8.3lf%8.3lf%8.3lf\n".replace("%8.3lf", "%8.3f") % (k + 1, ch, rid, x, y, z))
    chrom, pos, X = read_sic_pdb(tmp_path / "genome.pdb", ["chr1", "chrX"], 100_000)
    assert chrom.tolist() == ["chr1", "chr1", "chrX"] and pos.tolist() == [100_000, 200_000, 100_000]
    assert np.allclose(X[1], [10.0, 0.0, -1234.5])


def test_nucdyn_chain_map():
    m = nucdyn_chain_map(["chrX", "chr10", "chr2", "chr1"])
    assert m == {"a": "chr1", "b": "chr2", "c": "chr10", "d": "chrX"}


def test_3dg_resample(tmp_path):
    (tmp_path / "x.3dg").write_text("#unit: 1\nchr1\t0\t0\t0\t0\nchr1\t300\t1\t0\t0\nchr1\t400\t2\t0\t0\n")
    ch, st, xyz = read_3dg(tmp_path / "x.3dg")
    c, p, X = resample_3dg(ch, st, xyz, 100, spans={"chr1": (100, 499)})
    assert p.tolist() == [200, 300, 400, 500] and X[:, 0].tolist() == [0, 0, 1, 2]


def test_n3d(tmp_path):
    from run_nucdyn_original import read_n3d
    (tmp_path / "a.n3d").write_text("chr2\t2\t2\n10\t0 0 0\t1 1 1\n20\t1 0 0\t2 1 1\n"
                                     "chr1\t1\t2\n5\t9 9 9\t8 8 8\n")
    chrom, pos, X = read_n3d(tmp_path / "a.n3d")
    assert chrom.tolist() == ["chr1", "chr2", "chr2"] and pos.tolist() == [5, 10, 20]
    assert X.shape == (2, 3, 3) and X[1, 2].tolist() == [2, 1, 1] and X[0, 0].tolist() == [9, 9, 9]


def test_sic_prepare_mock(tmp_path):
    """contact/1kb_prepare replacement with a stand-in for the shipped binary (copies its input)."""
    from run_sic import check_res, prepare_1kb
    import pytest
    d = tmp_path / "1kb"
    d.mkdir()
    mock = d / "gettargetcontact.o"
    mock.write_text("#!/bin/sh\nread a\nread b\ncp \"$a\" \"$b\"\n")
    mock.chmod(mock.stat().st_mode | stat.S_IXUSR)
    f = tmp_path / "c.txt"
    f.write_text("chr1 10 chr1 20\nchrX 5 chr1 7\nchr1 30 chrX 40\nchr2 1 chr2 2\n")
    c = read_contacts(f)
    out = prepare_1kb(c, c.chroms, d, jobs=2)
    assert out["n_kept_after_isolation_filter"] == 4
    # chrom numbering 1..n natural order: chr1=1, chr2=2, chrX=3; inter rows oriented (i, j)
    assert (d / "1_3.dat").read_text().split() == ["30", "40", "7", "5"]   # (i, j) rows first, as do.sh
    assert (d / "1_1.dat").read_text().split() == ["10", "20"]
    with pytest.raises(ValueError):
        check_res(1000)
    check_res(500)


def test_save_npz(tmp_path):
    save_npz(tmp_path / "m.npz", ["chr1"], [100], np.zeros((1, 3)))
    z = np.load(tmp_path / "m.npz")
    assert z["coords"].shape == (1, 1, 3)
