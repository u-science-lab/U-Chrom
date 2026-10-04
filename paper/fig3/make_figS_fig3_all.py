"""Build Fig. 3 and its supplementary figures as one numbered set.

Supplementary Fig. S1 belongs to Fig. 2; Fig. 3's set is S2-S7 (S4 is the number the
manuscript already cites for the overflow figure):

  S2  published vs U-Chrom, four viewpoints           make_figS_fig3_views.py
  S3  100 kb / 10 kb / 1 kb on one GPU                  make_figS_fig3_resolution.py
  S4  the original's repulsion-list overflow            make_figS_fig3_overflow.py
  S5  the single-cell benchmark in detail               make_figS_fig3_benchmark.py
  S6  imaged distances -> contacts (with DIMES)         make_figS_fig3.py
  S7  population and Hi-C + FISH reconstruction         make_figS_fig3_population.py

Writes every figure, then ``figS_fig3_set.pdf`` (S2-S7 in order) and, with ``--manuscript``,
copies ``fig3.pdf`` and ``figS<k>.pdf`` into ``paper/manuscript/figures/``.

    python paper/fig3/make_figS_fig3_all.py [--manuscript]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET = [("S2", "make_figS_fig3_views.py", "figS_fig3_views.pdf"),
       ("S3", "make_figS_fig3_resolution.py", "figS_fig3_resolution.pdf"),
       ("S4", "make_figS_fig3_overflow.py", "figS_fig3_overflow.pdf"),
       ("S5", "make_figS_fig3_benchmark.py", "figS_fig3_benchmark.pdf"),
       ("S6", "make_figS_fig3.py", "figS_fig3.pdf"),
       ("S7", "make_figS_fig3_population.py", "figS_fig3_population.pdf")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manuscript", action="store_true", help="copy the PDFs into paper/manuscript/figures/")
    a = ap.parse_args()
    for script in ["make_fig3.py"] + [s for _, s, _ in SET]:
        subprocess.run([sys.executable, str(HERE / script)], check=True, cwd=HERE)
    from pypdf import PdfWriter
    w = PdfWriter()
    for _, _, pdf in SET:
        w.append(str(HERE / pdf))
    w.write(str(HERE / "figS_fig3_set.pdf"))
    print(HERE / "figS_fig3_set.pdf")
    if a.manuscript:
        dst = HERE.parent / "manuscript" / "figures"
        shutil.copy(HERE / "fig3.pdf", dst / "fig3.pdf")
        for num, _, pdf in SET:
            shutil.copy(HERE / pdf, dst / f"fig{num}.pdf")
        print("copied to", dst)


if __name__ == "__main__":
    main()
