"""chen_spots.py (PREREG §13.3): per-spot split, secondary mixtures, scoring and report without a GPU."""

import gzip
import json

import numpy as np
import pandas as pd

import chen_spots as cs


def _pairs(path, spots, rng):
    with gzip.open(path, "wt") as fh:
        fh.write("## pairs format v1.0.0\n#columns: readID chrom1 pos1 chrom2 pos2 strand1 strand2 mapq1 mapq2\n")
        for bc, n in spots:
            ca = rng.choice(["chr1", "chr2", "chrX"], n)
            cb = np.where(rng.random(n) < 0.8, ca, rng.choice(["chr1", "chr2", "chrX"], n))
            pa = rng.integers(1, 60_000_000, n)
            pb = np.where(ca == cb, np.clip(pa + rng.integers(2_000, 8_000_000, n), 1, 61_000_000), rng.integers(1, 60_000_000, n))
            for r in zip(ca, pa, cb, pb):
                fh.write(f"{bc}\t{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t+\t-\t60\t60\n")
            fh.write(f"{bc}\tchrM\t5\tchr1\t100\t+\t-\t60\t60\n")      # dropped (chromosome)
        fh.write("UNLINKED_X\tchr1\t5\tchr1\t50000\t+\t-\t60\t60\n")  # dropped (barcode)


def test_split_mixtures_score_report(tmp_path):
    rng = np.random.default_rng(0)
    spots = [("AAA_CCC", 14_000), ("AAA_GGG", 13_000), ("TTT_CCC", 3_000)]
    _pairs(tmp_path / "p.pairs.gz", spots, rng)
    pd.DataFrame({"run": "R1", "barcode_pair": [s for s, _ in spots], "spot": ["S:1x1", "S:1x2", "S:2x1"], "section": "S",
                  "grid_col": [1, 1, 2], "grid_row": [1, 2, 1], "Region": ["L1", "L1", "L2"]}
                 ).to_csv(tmp_path / "spots.tsv.gz", sep="\t", index=False)
    d = tmp_path / "R1"
    cs.main(["split", "--pairs", str(tmp_path / "p.pairs.gz"), "--spots", str(tmp_path / "spots.tsv.gz"), "--out", str(d)])
    st = pd.read_csv(d / "spots.tsv", sep="\t")
    assert list(st.level) == ["10k", "10k", "na"]
    assert (st.n_cis + st.n_trans + st.n_short).tolist() == [n for _, n in spots]
    man = pd.read_csv(d / "manifest.tsv", sep="\t")
    assert len(man) == 2
    cs.N_SECONDARY = 3
    cs.SECONDARY_N = 4_000
    cs.main(["mixtures", "--dir", str(d)])
    man = pd.read_csv(d / "manifest.tsv", sep="\t")
    assert (man.kind == "single").sum() == 2 and (man.kind == "mix2").sum() == 3
    cs.main(["score", "--dir", str(d), "--task", "1", "--ntasks", "1"])
    sc = pd.read_csv(d / "scores" / "001.tsv", sep="\t")
    assert len(sc) == len(man) and sc.q7_conflict.notna().all()
    # report with fake Q3 values (no GPU runs here)
    sc["q3_viol"] = [0.1, 0.9] + [0.5] * (len(sc) - 2)
    for k in ("rg_genome", "rg_chrom_median", "intermingling"):
        sc[k] = 1.0
    sc.to_csv(d / "scores" / "001.tsv", sep="\t", index=False)
    thr = {"thresholds": {"10k": 0.4, "30k": 0.4, "100k": 0.4}, "q7_thresholds": {"10k": 0.8, "30k": 0.8, "100k": 0.8}}
    (tmp_path / "thr.json").write_text(json.dumps(thr))
    cs.main(["report", "--dirs", str(d), "--thresholds", str(tmp_path / "thr.json"), "--out", str(tmp_path / "rep")])
    s = json.loads((tmp_path / "rep" / "summary.json").read_text())["R1"]
    assert s["levels"]["10k"]["pass"] == 1 and s["levels"]["na"]["n"] == 1
    assert (tmp_path / "rep" / "R1_maps.png").exists()


def test_structure_features_shapes():
    rng = np.random.default_rng(1)
    chrom = np.repeat(["chr1", "chr2"], 50)
    X = np.cumsum(rng.normal(size=(2, 100, 3)), 1)
    f = cs.structure_features(chrom, X)
    assert f["rg_genome"] > 0 and 0 <= f["intermingling"] <= 1
