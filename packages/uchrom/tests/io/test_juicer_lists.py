"""uchrom.io.read_juicer_loops / read_juicer_domains: Juicer HiCCUPS / Arrowhead lists (GSE63525 layout and
Juicer's .bedpe layout)."""

import gzip

import pandas as pd

from uchrom.io import read_juicer_domains, read_juicer_loops

LOOPS = """chr1\tx1\tx2\tchr2\ty1\ty2\tcolor\to\te_bl\tfdr_bl
10\t100225000\t100230000\t10\t100420000\t100425000\t0,255,255\t95\t27.49\t1.2e-15
21\t30000000\t30005000\t21\t30200000\t30205000\t0,255,255\t40\t10.1\t3.0e-8
21\t20000000\t20005000\t21\t20100000\t20105000\t0,255,255\t50\t12.5\t2.0e-9
"""

DOMAINS = """chr1\tx1\tx2\tchr2\ty1\ty2\tcolor\tf1\tf2\tf3\tf4\tf5
21\t15620000\t15790000\t21\t15620000\t15790000\t255,255,0\t0.7\t0.02\t0.03\t0.53\t0.53
21\t10380000\t11180000\t21\t10380000\t11180000\t255,255,0\t1.06\t0.27\t0.18\t0.40\t0.78
X\t5000000\t5600000\tX\t5000000\t5600000\t255,255,0\t0.5\t0.3\t0.2\t0.4\t0.5
"""


def test_geo_lists(tmp_path):
    p = tmp_path / "loops.txt.gz"
    with gzip.open(p, "wt") as fh:
        fh.write(LOOPS)
    loops = read_juicer_loops(p)
    assert list(loops.columns[:6]) == ["chrom1", "start1", "end1", "chrom2", "start2", "end2"]
    assert loops["chrom1"].tolist() == ["chr10", "chr21", "chr21"]
    assert loops.loc[1, "start1"] == 20_000_000 and loops["o"].tolist() == [95, 50, 40]
    assert len(read_juicer_loops(p, chrom="21")) == 2 and len(read_juicer_loops(p, chrom=["chr21"])) == 2
    assert read_juicer_loops(p, chrom="21", chrom_prefix=None)["chrom1"].tolist() == ["21", "21"]

    d = tmp_path / "domains.txt"
    d.write_text(DOMAINS)
    doms = read_juicer_domains(d, chrom="chr21")
    assert doms.columns[:3].tolist() == ["chrom", "start", "end"] and "y1" not in doms.columns
    assert doms["start"].tolist() == [10_380_000, 15_620_000] and doms.loc[0, "f1"] == 1.06
    assert read_juicer_domains(d)["chrom"].tolist() == ["chr21", "chr21", "chrX"]


def test_bedpe_layout(tmp_path):
    p = tmp_path / "merged_loops.bedpe"
    p.write_text("#chr1\tx1\tx2\tchr2\ty1\ty2\tname\tscore\n# juicer_tools version 1.22.01\n"
                 "chr1\t1000\t2000\tchr1\t50000\t51000\t.\t.\n")
    loops = read_juicer_loops(p)
    assert len(loops) == 1 and loops.loc[0, "chrom1"] == "chr1" and loops.loc[0, "end2"] == 51_000
    assert isinstance(loops, pd.DataFrame)
