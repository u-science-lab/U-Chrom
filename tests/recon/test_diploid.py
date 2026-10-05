"""Diploid (homolog-resolved, partially phased) reconstruction: phased readers, NucDynamics
(2017 ambiguous restraints) and EMber (copy pair inferred by EM) on the native engine.

Synthetic toys only (two homologs of three random-walk chromosomes, a third of the contact
ends phased): they check the plumbing, the trace layout and that the homologs come out
separated with the right phases.  The validation on imaging truths and on Dip-C GM12878 is in
``benchmarks/screcon`` (``diploid_*.py``).
"""

import gzip

import numpy as np
import pandas as pd
import pytest

un = pytest.importorskip("uchrom_nucdyn")

QUICK = dict(particle_sizes=[4e6, 1e6, 4e5], n_models=2, seed=3, device="cpu", n_threads=2,
             temp_steps=[60], dynamics_steps=[50], robust_temp_steps=[60], robust_dynamics_steps=[50])


def toy(seed=1, chroms=("chr1", "chr2", "chrX"), male=False, n_try=60_000, phased=0.35):
    """Contacts from two random-walk homologs per chromosome (one copy of chrX / chrY when
    ``male``).  Returns (DataFrame chrom1 pos1 hap1 chrom2 pos2 hap2, true haps (n, 2), walks)."""
    rng = np.random.default_rng(seed)
    nloc, step = 120, 100_000
    walks = {}
    for k, c in enumerate(chroms):
        for h in range(1 if (male and c in ("chrX", "chrY")) else 2):
            w = np.cumsum(rng.normal(scale=0.35, size=(nloc, 3)), axis=0) + [k * 6.0, h * 9.0, 0]
            walks[(c, h)] = w
    keys = list(walks)
    rows, truth = [], []
    for _ in range(n_try):
        a = keys[rng.integers(len(keys))]
        if rng.random() < 0.9:
            b = a if rng.random() < 0.9 else (a[0], 1 - a[1]) if (a[0], 1 - a[1]) in walks else a
        else:
            b = keys[rng.integers(len(keys))]
        i, j = rng.integers(nloc, size=2)
        if np.sum((walks[a][i] - walks[b][j]) ** 2) < 0.8:
            single = lambda c: male and c in ("chrX", "chrY")  # noqa: E731
            ha = a[1] if (rng.random() < phased and not single(a[0])) else -1
            hb = b[1] if (rng.random() < phased and not single(b[0])) else -1
            rows.append((a[0], i * step + 1 + rng.integers(step - 1), ha, b[0], j * step + 1 + rng.integers(step - 1), hb))
            truth.append((a[1], b[1]))
    df = pd.DataFrame(rows, columns=["chrom1", "pos1", "hap1", "chrom2", "pos2", "hap2"])
    return df, np.array(truth), walks


def write_pairs(df, path, probs=None):
    h = lambda x: np.where(x >= 0, x.astype(str), ".")  # noqa: E731
    cols = "readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1"
    if probs is not None:
        cols += " phase_prob00 phase_prob01 phase_prob10 phase_prob11"
    with gzip.open(path, "wt") as fh:
        fh.write("## pairs format v1.0\n#columns: " + cols + "\n")
        for k, r in enumerate(df.itertuples()):
            extra = "" if probs is None else "\t" + "\t".join(f"{x:.4f}" for x in probs[k])
            fh.write(f"r{k}\t{r.chrom1}\t{r.pos1}\t{r.chrom2}\t{r.pos2}\t+\t-\t{h(np.int8(r.hap1))}\t{h(np.int8(r.hap2))}{extra}\n")


def write_con(df, path):
    h = lambda x: "." if x < 0 else str(x)  # noqa: E731
    with gzip.open(path, "wt") as fh:
        for r in df.itertuples():
            fh.write(f"{r.chrom1},{r.pos1},{h(r.hap1)}\t{r.chrom2},{r.pos2},{h(r.hap2)}\n")


def test_phased_readers_agree(tmp_path):
    from uchrom.io import read_phased_pairs

    df, _, _ = toy(n_try=3000)
    probs = np.random.default_rng(0).dirichlet(np.ones(4), len(df))
    write_pairs(df, tmp_path / "c.pairs.gz", probs)
    write_con(df, tmp_path / "c.con.gz")
    for f in ("c.pairs.gz", "c.con.gz"):
        t = read_phased_pairs(tmp_path / f)
        e = un.read_phased_contacts(str(tmp_path / f))
        for col, key in (("chrom1", "chrom_a"), ("pos1", "pos_a"), ("hap1", "hap_a"),
                         ("chrom2", "chrom_b"), ("pos2", "pos_b"), ("hap2", "hap_b")):
            np.testing.assert_array_equal(t[col].to_numpy(), df[col].to_numpy())
            np.testing.assert_array_equal(np.asarray(e[key]), df[col].to_numpy())
        if f.endswith("pairs.gz"):
            np.testing.assert_allclose(e["phase_prob"], probs, atol=1e-4)
            np.testing.assert_allclose(t[["phase_prob00", "phase_prob01", "phase_prob10", "phase_prob11"]], probs, atol=1e-4)
    from uchrom.recon.sc.nucdyn.native import is_phased_file

    assert is_phased_file(tmp_path / "c.pairs.gz") and is_phased_file(tmp_path / "c.con.gz")


def _copy_r(cd, walks, layer="model_0"):
    """Distance-matrix r of every copy chain vs its truth walk (particle -> locus)."""
    X = cd.layers[layer]
    sp = cd.spots_with_loci()
    out = {}
    for t, idx in sp.groupby("trace_id", observed=True).indices.items():
        c = str(sp["chrom"].iloc[idx[0]])
        h = int(sp["haplotype"].iloc[idx[0]])
        loc = ((sp["end"].to_numpy()[idx] - 1) // 100_000).astype(int)
        ok = loc < len(walks[(c, h)])
        idx, loc = idx[ok], loc[ok]
        iu = np.triu_indices(len(idx), 2)
        dm = np.linalg.norm(X[idx][:, None] - X[idx][None], axis=2)[iu]
        dt = np.linalg.norm(walks[(c, h)][loc][:, None] - walks[(c, h)][loc][None], axis=2)[iu]
        out[t] = np.corrcoef(dm, dt)[0, 1]
    return out


@pytest.mark.parametrize("method", ["ember", "nucdyn"])
def test_diploid_reconstruction_separates_homologs(tmp_path, method):
    from uchrom.recon.sc import reconstruct_ember, reconstruct_nucdyn

    df, truth, walks = toy()
    write_pairs(df, tmp_path / "c.pairs.gz")
    if method == "ember":
        cd = reconstruct_ember(str(tmp_path / "c.pairs.gz"), cell_id="toy", **QUICK)
    else:
        cd = reconstruct_nucdyn(str(tmp_path / "c.pairs.gz"), cell_id="toy", **QUICK)
    key = method
    traces = sorted(cd.spots["trace_id"].astype(str).unique())
    assert traces == ["chr1(mat)", "chr1(pat)", "chr2(mat)", "chr2(pat)", "chrX(mat)", "chrX(pat)"]
    # both copies share the bins
    assert len(cd.bins) * 2 == len(cd.spots)
    r = _copy_r(cd, walks)
    assert np.mean(list(r.values())) > 0.6, r
    info = cd.uns[key]["diploid"]
    assert info["ploidy"] == {"chr1": 2, "chr2": 2, "chrX": 2}
    assert 0.2 < info["frac_ends_phased"] < 0.5
    pp = cd.results[f"{key}.phase_probs"]
    assert pp.shape == (len(df), 4)
    ok = np.isfinite(pp).all(1)
    np.testing.assert_allclose(pp[ok].sum(1), 1.0, atol=1e-9)
    imp = cd.results[f"{key}.imputed_phase"]
    # input phases are kept; the imputed phase of unphased ends of informative contacts is right
    ph = ok & (df.hap1.to_numpy() >= 0)
    assert (imp.imputed_a.to_numpy()[ph] == df.hap1.to_numpy()[ph]).mean() > 0.97
    # informative: the other copy of end a is >= 3 units from end b in the truth (and, for an
    # unphased end b, from both copies of b)
    sel = np.zeros(len(df), bool)
    for k, r in enumerate(df.itertuples()):
        if not ok[k] or r.hap1 >= 0:
            continue
        la, lb = (r.pos1 - 1) // 100_000, (r.pos2 - 1) // 100_000
        hbs = [r.hap2] if r.hap2 >= 0 else [0, 1]
        alt = 1 - truth[k, 0]
        sel[k] = all(np.linalg.norm(walks[(r.chrom1, alt)][la] - walks[(r.chrom2, h)][lb]) >= 3.0
                     for h in hbs if (r.chrom2, h) in walks)
    acc = (imp.imputed_a.to_numpy()[sel] == truth[sel, 0]).mean()
    assert sel.sum() > 200 and acc > 0.9, (sel.sum(), acc)
    if method == "ember":
        w = cd.results["ember.contact_weights"]
        assert np.isfinite(w).sum() > len(df) // 2
        em = cd.results["ember.em"]
        assert "n_ambiguous" in em and em["n_ambiguous"].max() > 0


def test_male_auto_ploidy_and_haploid_override(tmp_path):
    from uchrom.recon.sc import reconstruct_ember

    df, _, _ = toy(chroms=("chr1", "chrX", "chrY"), male=True)
    write_pairs(df, tmp_path / "m.pairs.gz")
    cd = reconstruct_ember(str(tmp_path / "m.pairs.gz"), **QUICK)
    assert sorted(cd.spots["trace_id"].astype(str).unique()) == ["chr1(mat)", "chr1(pat)", "chrX", "chrY"]
    assert cd.uns["ember"]["diploid"]["ploidy"] == {"chr1": 2, "chrX": 1, "chrY": 1}
    # ploidy="haploid": phases ignored -> the haploid result, bit for bit
    h = reconstruct_ember(str(tmp_path / "m.pairs.gz"), ploidy="haploid", **QUICK)
    plain = df[["chrom1", "pos1", "chrom2", "pos2"]]
    g = reconstruct_ember(plain, **QUICK)
    for k in g.layers:
        np.testing.assert_array_equal(h.layers[k], g.layers[k])
    assert "diploid" not in h.uns["ember"]


def test_diploid_rejects_release13(tmp_path):
    from uchrom.recon.sc import reconstruct_nucdyn

    df, _, _ = toy(n_try=5000)
    with pytest.raises(ValueError):
        reconstruct_nucdyn(df, protocol="release_1.3", **QUICK)


def test_ember_default_matches_frozen_config(tmp_path):
    """reconstruct_ember's default is the frozen diploid configuration: EMber's own neighbourhood
    prior on, hickit's imputed phase_prob not used (PREREG §6); phase_prior=True opts in."""
    import inspect

    from uchrom.recon.sc import reconstruct_ember

    assert inspect.signature(reconstruct_ember).parameters["phase_prior"].default is False
    df, _, _ = toy(n_try=8_000)
    probs = np.full((len(df), 4), 0.25)
    write_pairs(df, tmp_path / "c.pairs.gz", probs=probs)
    q = dict(QUICK, particle_sizes=[4e6, 1e6])
    cd = reconstruct_ember(str(tmp_path / "c.pairs.gz"), cell_id="toy", **q)
    assert cd.uns["ember"]["diploid"]["phase_prior"] is False
    assert cd.uns["ember"]["diploid"] and cd.results.record("ember.stages").params["robust_dip_nbr_prior"] is True
    cd = reconstruct_ember(str(tmp_path / "c.pairs.gz"), cell_id="toy", phase_prior=True, **q)
    assert cd.uns["ember"]["diploid"]["phase_prior"] is True
