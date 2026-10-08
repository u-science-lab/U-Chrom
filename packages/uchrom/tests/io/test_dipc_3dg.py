"""Single-cell structures in the .3dg layouts of Dip-C and hickit (uchrom.io.dipc_3dg)."""

import gzip

import numpy as np
import pytest

from uchrom.io.dipc_3dg import read_3dg_cells, read_3dg_structure, replicate_deviation


def _write(path, lines, header=()):
    text = "".join(f"{h}\n" for h in header) + "".join("\t".join(map(str, row)) + "\n" for row in lines)
    if str(path).endswith(".gz"):
        with gzip.open(path, "wt") as fh:
            fh.write(text)
    else:
        path.write_text(text)
    return path


def _dipc_rows(rng, chroms=("1", "2", "10", "X"), n=6, size=20_000, shift=0.0):
    rows = []
    for c in chroms:
        for hap in ("mat", "pat"):
            for k in range(n):
                x, y, z = rng.normal(size=3) + shift
                rows.append((f"{c}({hap})", (k + 3) * size, x, y, z))
    return rows


def test_dipc_layout(tmp_path):
    rng = np.random.default_rng(0)
    rows = _dipc_rows(rng) + [("2(pat)", 0, 0.1, 0.2, 0.3)]          # a chain start at 0: holds nothing
    t = read_3dg_structure(_write(tmp_path / "c.3dg.txt.gz", rows))
    assert t.attrs["format"] == "dipc" and t.attrs["particle_size"] == 20_000
    assert t.attrs["particle_position"] == "end" and t.attrs["n_dropped_before_start"] == 1
    assert set(t["chrom"]) == {"chr1", "chr2", "chr10", "chrX"} and set(t["homolog"]) == {"pat", "mat"}
    first = t.iloc[0]
    assert (first["position"], first["start"], first["end"]) == (60_000, 40_000, 60_000)   # (p - size, p]
    assert len(t) == len(rows) - 1
    np.testing.assert_allclose(t[["x", "y", "z"]].to_numpy()[0], rows[0][2:])
    s = read_3dg_structure(tmp_path / "c.3dg.txt.gz", particle_position="start", chr_prefix=False)
    assert s["start"].iloc[0] == 60_000 and s["chrom"].iloc[0] == "1"


def test_hickit_layout(tmp_path):
    header = ["#chromosome: 1a 300000", "#chromosome: 1b 300000", "#chromosome: Xa 200000",
              "#chromosome: Xb 200000"]
    rows = [("1a", 0, 0, 0, 0, 0.01), ("1a", 100_000, 1, 0, 0, 0.01), ("1a", 120_000, 2, 0, 0, 0.01),
            ("1b", 140_000, 0, 1, 0, 0.01), ("1b", 160_000, 0, 2, 0, 0.01), ("Xa", 40_000, 0, 0, 1, 0.02),
            ("Xb", 60_000, 0, 0, 2, 0.02)]
    t = read_3dg_structure(_write(tmp_path / "h.3dg", rows, header))
    assert t.attrs["format"] == "hickit" and t.attrs["particle_position"] == "start"
    assert t.attrs["particle_size"] == 20_000
    assert list(t["homolog"]) == ["pat", "pat", "pat", "mat", "mat", "pat", "mat"]
    assert list(t["chrom"]) == ["chr1"] * 5 + ["chrX"] * 2
    assert (t["start"].iloc[1], t["end"].iloc[1]) == (100_000, 120_000)                    # [p, p + size)
    assert t["start"].iloc[0] == 0                                                          # kept as [0, size)
    u = read_3dg_structure(tmp_path / "h.3dg", hap_names=("a", "b"))
    assert list(u["homolog"][:4]) == ["a", "a", "a", "b"]


def test_plain_haploid_layout(tmp_path):
    rows = [("chr1", 100_000, 0, 0, 0), ("chr1", 200_000, 1, 0, 0), ("chr2", 100_000, 0, 1, 0)]
    t = read_3dg_structure(_write(tmp_path / "p.3dg", rows))
    assert t.attrs["format"] == "plain" and t["homolog"].isna().all()
    cd = read_3dg_cells({"cellA": tmp_path / "p.3dg"})
    assert sorted(cd.traces.index) == ["cellA_chr1", "cellA_chr2"]
    assert cd.traces.loc["cellA_chr1", "n_particles"] == 2


def test_cells_layers_and_order(tmp_path):
    rng = np.random.default_rng(1)
    rows_a = _dipc_rows(rng)
    rows_b = _dipc_rows(rng, chroms=("1", "10"))
    rep_a = [r for r in rows_a if r[:2] != ("10(pat)", 80_000)] + [("1(mat)", 400_000, 9, 9, 9)]
    files = {"a": _write(tmp_path / "a.3dg", rows_a), "b": _write(tmp_path / "b.3dg", rows_b)}
    cd = read_3dg_cells(files, layers={"rep1": {"a": _write(tmp_path / "ra.3dg", rep_a)}})
    assert cd.n_spots == len(rows_a) + len(rows_b) and cd.n_traces == 8 + 4
    # genome order of the chromosomes, cells in the given order
    assert list(cd.bins["chrom"].cat.categories) == ["chr1", "chr2", "chr10", "chrX"]
    assert list(cd.cells.index) == ["a", "b"] and cd.cells.loc["b", "n_traces"] == 4
    assert cd.traces.loc["a_chr10_pat", "homolog"] == "pat"
    rep = cd.layers["rep1"]
    info = cd.uns["structures"]["layers"]["rep1"]
    assert info["particles_not_in_main_run"] == 1
    assert info["main_particles_missing"] == 1 + len(rows_b)              # the dropped particle + cell b
    loci = cd.spots_with_loci()
    gone = ((loci["trace_id"] == "a_chr10_pat") & (loci["end"] == 80_000)).to_numpy()
    assert np.isnan(rep[gone]).all() and np.isfinite(rep[(loci["cell_id"] == "a").to_numpy() & ~gone]).all()
    same = (loci["cell_id"] == "a").to_numpy() & ~gone
    np.testing.assert_allclose(rep[same], np.asarray(cd.coords)[same])
    assert cd.uns["xyz_unit"] == "particle radius" and cd.uns["structures"]["particle_size"] == 20_000


def test_replicate_deviation_superposes_and_mirrors(tmp_path):
    rng = np.random.default_rng(2)
    rows = _dipc_rows(rng, n=15)
    xyz = np.array([r[2:] for r in rows])
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(q) > 0:
        q[:, 0] *= -1                                              # an improper rotation: a mirror image
    moved = xyz @ q + np.array([5.0, -2.0, 1.0])
    noisy = moved + rng.normal(scale=0.05, size=moved.shape)
    main = _write(tmp_path / "m.3dg", rows)
    r1 = _write(tmp_path / "r1.3dg", [(r[0], r[1], *m) for r, m in zip(rows, moved)])
    r2 = _write(tmp_path / "r2.3dg", [(r[0], r[1], *m) for r, m in zip(rows, noisy)])
    cd = read_3dg_cells({"c": main}, layers={"rep1": {"c": r1}, "rep2": {"c": r2}})
    per_cell, per_spot = replicate_deviation(cd, ("rep1", "rep2"))
    assert per_cell.loc["c", "rmsd_rep1"] < 1e-9 and bool(per_cell.loc["c", "mirrored_rep1"])
    assert 0.02 < per_cell.loc["c", "rmsd_rep2"] < 0.15
    assert per_spot.shape == (cd.n_spots,) and np.isfinite(per_spot).all()
    proper, _ = replicate_deviation(cd, ("rep1",), reflection=False)
    assert proper.loc["c", "rmsd_rep1"] > 0.5


def test_mixed_particle_sizes_raise(tmp_path):
    a = _write(tmp_path / "a.3dg", [("1(pat)", 40_000, 0, 0, 0), ("1(pat)", 60_000, 1, 0, 0)])
    b = _write(tmp_path / "b.3dg", [("1(pat)", 100_000, 0, 0, 0), ("1(pat)", 200_000, 1, 0, 0)])
    with pytest.raises(ValueError, match="particles of"):
        read_3dg_cells({"a": a, "b": b})
