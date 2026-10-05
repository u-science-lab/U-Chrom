"""unic_qc.py: read-footprint conventions, stats on a small pairs file, projection."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unic_qc  # noqa: E402


def test_footprint_conventions():
    hets = {"1": np.array([1000, 5000])}
    chrom = np.array(["1", "1", "1", "1", "2"])
    pos = np.array([900, 1100, 5000, 3000, 1000])
    strand = np.array(["+", "+", "-", "+", "+"])
    hit = unic_qc._footprint_hit(hets, chrom, pos, strand, 150)
    # + at 900: [900, 1049] covers 1000 (down); [751, 900] does not (up)
    # + at 1100: down [1100, 1249] no; up [951, 1100] yes
    # - at 5000: down [4851, 5000] yes; up [5000, 5149] yes (het exactly at pos)
    assert hit["down"].tolist() == [True, False, True, False, False]
    assert hit["up"].tolist() == [False, True, True, False, False]
    assert hit["both"].tolist() == [True, True, True, False, False]


def test_stats_and_project(tmp_path):
    lines = ["## pairs format v1.0", "#chromsize: 1 1000000", "#chromsize: 2 500000",
             "#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1"]
    rows = [("r1", "1", 1000, "1", 50000, "+", "-", "0", "."),
            ("r2", "1", 1010, "1", 200000, "+", "+", ".", "."),
            ("r3", "1", 300000, "2", 1000, "-", "+", "1", "0"),
            ("r4", "chrM", 10, "1", 400000, "+", "+", ".", ".")]
    p = tmp_path / "x.pairs"
    p.write_text("\n".join(lines + ["\t".join(map(str, r)) for r in rows]) + "\n")
    hets = {"1": np.array([1050, 299_950]), "2": np.array([1100])}
    s = unic_qc.stats(str(p), hets, 150, "ref")
    assert s["rows"] == 4 and s["contacts"] == 3
    assert abs(s["frac_trans"] - 1 / 3) < 1e-9
    assert s["actual"]["frac_legs_phased"] == 3 / 6
    # legs: (1,1000,+) down yes; (1,1010,+) down yes; (1,300000,-) down yes; (1,50000,-) no; (1,200000,+) no;
    # (2,1000,+) down yes
    assert abs(s["footprint"]["frac_legs_down"] - 4 / 6) < 1e-9
    assert s["footprint"]["phased_legs_with_het"]["down"] == 1.0
    assert s["legs_per_1kb_bin"]["max"] == 2
    assert s["contacts_per_particle"]["100000"]["particles"] == 2 * (10 + 5)
    a = tmp_path / "ref.json"
    a.write_text(json.dumps(s))
    u = dict(s, label="unic")
    b = tmp_path / "u.json"
    b.write_text(json.dumps(u))
    out = tmp_path / "p.json"
    unic_qc.main(["project", "--unic", str(b), "--ref", str(a), "--convention", "down", "--out", str(out)])
    P = json.loads(out.read_text())
    assert P["calibration"]["ref"]["convention"] == "down"
    q = P["unic"][0]["proj_legs_min"]
    assert abs(q - 0.5) < 1e-9          # footprint 4/6 x calibration (3/6)/(4/6)
    unic_qc.main(["project", "--unic", str(b), "--ref", str(a), "--out", str(out)])
    P = json.loads(out.read_text())
    assert abs(P["unic"][0]["proj_legs_min"] - 0.5) < 1e-9   # same file: projection = actual, any convention
