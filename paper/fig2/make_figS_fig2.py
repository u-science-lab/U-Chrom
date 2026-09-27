"""Supplementary Figure S1 — all Fig. 2 supplementary panels on one page.

Stacks the three supplementary figures of Fig. 2 as matplotlib subfigures, each drawn by its
own script in its own mm frame, and letters the panels consecutively:

  1  one trace / one chromosome, across formats                    (make_figS_access.py)
  2  cross-modal query: RNA groups -> pseudo-bulk Hi-C               (make_figS_crossmodal.py)
  3  linked vs copied contacts                                       (make_figS_contacts.py)

    python paper/fig2/make_figS_fig2.py      # -> figS_fig2.pdf / .png
"""

from __future__ import annotations

import string
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.text import Text

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_figS_contacts as SC  # noqa: E402
import make_figS_crossmodal as SX  # noqa: E402
import make_figS_access as SA  # noqa: E402

MM = 1 / 25.4
W = 170.0
GAP = 8.0                                    # mm between sections
SECTIONS = [(SA, SA.H), (SX, SX.H), (SC, SC.H)]
SEP_TITLES = [None, "Linked vs copied contacts"]   # section 2 carries its own title; section 3 does not
LEGENDS = ["figS_access_legend.md", "figS_crossmodal_legend.md", "figS_contacts_legend.md"]


def _panel_letters(fig):
    """Panel-letter texts (10 pt bold, one lowercase letter), in drawing order."""
    return [t for t in fig.findobj(Text)
            if len(t.get_text()) == 1 and t.get_text() in string.ascii_lowercase
            and t.get_fontsize() == 10 and t.get_fontweight() in ("bold", 700)]


def write_legend(offsets) -> Path:
    """One legend: the three section legends with their panel letters shifted."""
    import re
    parts = ["**Supplementary Figure S1 — Fig. 2 supplement: access by format (a, b); cross-modal query (c–f); "
             "linked vs copied contacts (g–i).**"]
    for name, off in zip(LEGENDS, offsets):
        txt = (HERE / name).read_text().strip()
        txt = re.sub(r"^\*\*Supplementary Figure S\d+[a-z,–-]*\s*[—-]\s*", "**", txt, count=1)   # keep the section title
        txt = re.sub(r"\*\*([a-z])\*\*", lambda m: f"**{string.ascii_lowercase[off + ord(m.group(1)) - 97]}**", txt)
        parts.append(txt)
    out = HERE / "figS_fig2_legend.md"
    out.write_text(" ".join(parts) + "\n")
    return out


def main() -> None:
    heights = [h for _, h in SECTIONS]
    H = sum(heights) + GAP * (len(SECTIONS) - 1)
    fig = plt.figure(figsize=(W * MM, H * MM))
    ratios = []
    for i, h in enumerate(heights):
        ratios.append(h)
        if i < len(heights) - 1:
            ratios.append(GAP)
    subs = fig.subfigures(len(ratios), 1, height_ratios=ratios, hspace=0)
    nxt, offsets = 0, []
    for (mod, h), sub in zip(SECTIONS, subs[::2]):
        offsets.append(nxt)
        # helpers size things via fig.get_figwidth/height: give each subfigure its own size in inches
        sub.get_figwidth = lambda: W * MM
        sub.get_figheight = (lambda hh: (lambda: hh * MM))(h)
        mod.main(fig=sub)
        letters = sorted(_panel_letters(sub), key=lambda t: t.get_text())
        for t in letters:                     # a, b, ... of this section -> the next free letters
            t.set_text(string.ascii_lowercase[nxt + string.ascii_lowercase.index(t.get_text())])
        nxt += len({t.get_text() for t in letters})
    for k, sep in enumerate(subs[1::2]):      # thin rule between sections (+ a title where the section has none)
        title = SEP_TITLES[k]
        y_rule = 0.85 if title else 0.5
        sep.add_artist(plt.Line2D([0.01, 0.99], [y_rule, y_rule], color="#d9dce1", lw=0.5,
                                  transform=sep.transSubfigure))
        if title:
            sep.text(1 / W, 0.62, title, fontsize=8.5, fontweight="bold", va="top", transform=sep.transSubfigure)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig2.{ext}", dpi=300)
    print(write_legend(offsets))
    print(HERE / "figS_fig2.pdf", f"{W:.0f} x {H:.0f} mm, panels a-{string.ascii_lowercase[nxt - 1]}")


if __name__ == "__main__":
    main()
