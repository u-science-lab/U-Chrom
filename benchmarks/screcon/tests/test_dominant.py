"""dominant.py (PREREG §13): nested sampling, mixture tables, designs, graph QC metrics, structure comparison."""

import json

import numpy as np
import pandas as pd

import dominant as dm
from contacts import Contacts, read_contacts, write_geo


def _cell(n, seed, chroms=("chr1", "chr2", "chr3"), span=60_000_000):
    rng = np.random.default_rng(seed)
    ca = rng.choice(chroms, n)
    cb = np.where(rng.random(n) < 0.8, ca, rng.choice(chroms, n))
    pa = rng.integers(1, span, n)
    pb = np.where(ca == cb, np.clip(pa + rng.integers(-5_000_000, 5_000_000, n), 1, span), rng.integers(1, span, n))
    return Contacts(ca.astype(str), pa.astype(np.int64), cb.astype(str), pb.astype(np.int64))


def test_sampler_is_nested_and_keeps_trans_ratio():
    c = _cell(5000, 0)
    s = dm.Sampler(c, 1)
    a, b = s.take(500), s.take(1000)
    assert set(a) <= set(b)
    cis = dm.cis_mask(c)
    assert cis[a].sum() == 500
    r_all = (~cis).sum() / cis.sum()
    assert abs((~cis[b]).sum() / 1000 - r_all) < 0.01


def test_design_n_lowers_for_small_minors():
    assert dm.design_n("full", 80_000, [100_000], 1) == 80_000
    assert dm.design_n(30_000, 80_000, [100_000], 1) == 30_000
    assert dm.design_n("full", 80_000, [20_000], 1) == 40_000        # f = 0.5 needs 0.5 N from the minor
    assert dm.design_n("full", 80_000, [12_000, 30_000], 2) == 48_000


def test_build_haploid_mixtures(tmp_path):
    tabs = {}
    for k, n in enumerate((9_000, 9_000, 8_000)):
        f = tmp_path / f"c{k}.txt.gz"
        c = _cell(n, k)
        write_geo(f, c.chrom_a, c.pos_a, c.chrom_b, c.pos_b)
        tabs[f"c{k}"] = (str(f), int(dm.cis_mask(c).sum()))
    d = tmp_path / "set"
    d.mkdir()
    pd.DataFrame([{"cell": k, "table": v[0], "type": "", "n_rows": 0, "n_cis": v[1], "n_other": 0} for k, v in tabs.items()]
                 ).to_csv(d / "cells.tsv", sep="\t", index=False)
    (d / "set.json").write_text(json.dumps({"dataset": "stevens", "set": "dev"}))
    des = {"dataset": "stevens", "set": "dev", "dominants": ["c0"],
           "designs": [{"dominant": "c0", "m": 1, "minors": ["c1"], "design": 0},
                       {"dominant": "c0", "m": 2, "minors": ["c1", "c2"], "design": 1}]}
    (d / "designs.json").write_text(json.dumps(des))
    dm.main(["build", "--dir", str(d)])
    man = pd.read_csv(d / "c0" / "manifest.tsv", sep="\t")
    # n_cis(c0) < 10k -> only "full"; full: pure + 2 designs x 5 f + 5 D-only
    assert set(man.level) == {"full"}
    assert (man.kind == "pure").sum() == 1 and (man.kind == "mix").sum() == 10 and (man.kind == "donly").sum() == 5
    name = man[(man.kind == "mix") & np.isclose(man.f, 0.6) & (man.design == 1)].name.iloc[0]
    info = json.loads((d / "c0" / "tables" / f"{name}.json").read_text())
    assert abs(info["f_realised"] - 0.6) < 0.002
    assert abs(info["cis"][1] - info["cis"][2]) <= 1
    org = np.load(d / "c0" / "tables" / f"{name}.origin.npz")
    t = read_contacts(d / "c0" / "tables" / f"{name}.txt.gz")
    assert len(t) == len(org["cell"]) == sum(info["rows"])
    # the D-only table holds exactly the dominant rows of the mixture
    don = read_contacts(d / "c0" / "tables" / f"donly_N{info['N']}_f0.6.txt.gz")
    key = lambda c: sorted(zip(c.chrom_a, c.pos_a, c.chrom_b, c.pos_b))  # noqa: E731
    dom_rows = t.subset(org["cell"] == 0)
    assert key(don) == key(dom_rows)
    # run list: 4 references (dominant EMber + NucDynamics, 2 minors) + 11 tables x 3 + 5 D-only
    assert len(dm.run_list(d / "c0", "stevens")) == 4 + 11 * 3 + 5


def test_graph_metrics_drop_with_mixing():
    # a "cell": a few dense trans / long-range cliques; mixing in a second cell's cliques lowers closure
    rng = np.random.default_rng(0)

    def cliques(seed):
        r = np.random.default_rng(seed)
        rows = []
        for _ in range(40):
            loci = [(f"chr{r.integers(1, 6)}", int(r.integers(1, 100)) * 1_000_000 + 500_000) for _ in range(5)]
            for i in range(5):
                for j in range(i + 1, 5):
                    if loci[i][0] != loci[j][0] or abs(loci[i][1] - loci[j][1]) >= 2_000_000:
                        rows.append((*loci[i], *loci[j]))
        a = np.array(rows, dtype=object)
        return Contacts(a[:, 0].astype(str), a[:, 1].astype(np.int64), a[:, 2].astype(str), a[:, 3].astype(np.int64))

    one = cliques(1)
    q1 = dm.graph_metrics(one)
    # random rewiring of the same number of edges: closure collapses
    rnd = Contacts(one.chrom_a, one.pos_a, one.chrom_b, rng.permutation(one.pos_b))
    rnd.chrom_b = rng.permutation(one.chrom_b)
    q0 = dm.graph_metrics(rnd)
    assert q1["q5_trans_lr"] > q0["q5_trans_lr"]
    assert q1["q6_tri"] > q0["q6_tri"]


def test_comparer_identity_and_noise():
    rng = np.random.default_rng(0)
    n = 120
    chrom = np.repeat(["chr1", "chr2"], n)
    pos = np.concatenate([np.arange(1, n + 1), np.arange(1, n + 1)]) * 200_000
    X = np.cumsum(rng.normal(size=(2, 2 * n, 3)), 1)
    c = dm.Comparer(chrom, pos, X)
    r = c.compare(chrom, pos, X)
    assert abs(r["per_copy_r"] - 1) < 1e-12 and abs(r["whole_r"] - 1) < 1e-12
    # a model on a subset of particles is matched by (chain, position)
    sub = np.arange(10, 2 * n)
    r2 = c.compare(chrom[sub], pos[sub], X[:, sub] + rng.normal(scale=3.0, size=X[:, sub].shape))
    assert r2["n_matched"] == len(sub) and r2["per_copy_r"] < 0.99


def test_youden_and_auc_direction():
    single = np.array([0.1, 0.2, 0.15, 0.12])
    mixed = np.array([0.4, 0.5, 0.35])
    assert dm.auc_dir(single, mixed, +1) == 1.0
    assert dm.auc_dir(single, mixed, -1) == 0.0
    y = dm.youden(single, mixed, +1)
    assert y["sens"] == 1.0 and y["spec"] == 1.0 and 0.2 < y["threshold"] <= 0.35


def _phased(n, seed):
    from diploid import Phased
    c = _cell(n, seed)
    rng = np.random.default_rng(seed + 10)
    ha = np.where(rng.random(n) < 0.3, rng.integers(0, 2, n), -1)
    hb = np.where(rng.random(n) < 0.3, rng.integers(0, 2, n), -1)
    return Phased(c.chrom_a, c.pos_a, ha, c.chrom_b, c.pos_b, hb)


def test_build_diploid_mixtures_keep_phases(tmp_path):
    from diploid import read_phased, write_phased
    d = tmp_path / "set"
    d.mkdir()
    rows = []
    for k, n in enumerate((9_000, 9_000)):
        f = tmp_path / f"c{k}.pairs.gz"
        p = _phased(n, k)
        write_phased(f, p)
        rows.append({"cell": f"c{k}", "table": str(f), "type": "P:GSM1", "n_rows": n,
                     "n_cis": int(dm.cis_mask(p).sum()), "n_other": 0})
    pd.DataFrame(rows).to_csv(d / "cells.tsv", sep="\t", index=False)
    (d / "set.json").write_text(json.dumps({"dataset": "tan", "set": "dev"}))
    (d / "designs.json").write_text(json.dumps({"dataset": "tan", "set": "dev", "dominants": ["c0"],
                                                "designs": [{"dominant": "c0", "m": 1, "minors": ["c1"], "design": 0}]}))
    dm.main(["build", "--dir", str(d)])
    man = pd.read_csv(d / "c0" / "manifest.tsv", sep="\t")
    name = man[(man.kind == "mix") & np.isclose(man.f, 0.5)].name.iloc[0]
    t = read_phased(d / "c0" / "tables" / f"{name}.pairs.gz")
    src = [read_phased(tmp_path / f"c{k}.pairs.gz") for k in (0, 1)]
    keys = {tuple(r) for s in src for r in zip(s.chrom_a, s.pos_a, s.hap_a, s.chrom_b, s.pos_b, s.hap_b)}
    assert len(t) > 0 and all(tuple(r) in keys for r in zip(t.chrom_a, t.pos_a, t.hap_a, t.chrom_b, t.pos_b, t.hap_b))


def test_violation_rate_diploid_uses_phased_copy():
    from diploid import Phased
    # two copy chains of chr1, 10 particles of 200 kb each; contacts between particle 0 and particle 9
    pos = np.arange(1, 11) * 200_000
    chrom = np.array(["chr1(0)"] * 10 + ["chr1(1)"] * 10)
    X0 = np.stack([np.arange(10.0), np.zeros(10), np.zeros(10)], 1)
    c = Phased(["chr1", "chr1"], [150_000, 150_000], [0, -1], ["chr1", "chr1"], [1_850_000, 1_850_000], [1, -1])
    # copies 100 units apart: the phased (0, 1) contact spans the copies, the unphased one is 9 units at best
    X = np.concatenate([X0, X0 + [0, 100.0, 0]])[None]
    assert dm.violation_rate(c, chrom, np.concatenate([pos, pos]), X, diploid=True) == 1.0
    # copy-1 particle 9 next to copy-0 particle 0: both satisfied (the unphased one through that copy pair)
    X2 = np.concatenate([X0, X0 + [0, 100.0, 0]])[None]
    X2[0, 19] = X2[0, 0] + [0, 0.5, 0]
    assert dm.violation_rate(c, chrom, np.concatenate([pos, pos]), X2, diploid=True) == 0.0
    # haploid reading of the same chain ignores phases
    hap = Phased(["chr1"], [150_000], [-1], ["chr1"], [1_850_000], [-1])
    assert dm.violation_rate(hap, np.array(["chr1"] * 10), pos, X0[None], diploid=False) == 1.0
