"""Convert paper/fig2/tableS_capabilities.md into LaTeX bodies for the supplement.

Usage: python make_tableS1.py ../fig2/tableS_capabilities.md supp   (or `make tables`)

Writes <out>/tableS1_matrix.tex, tableS1_changes.tex and tableS1_evidence.tex;
supplement.tex holds the header text (columns, marks, rules, versions) by hand.
Repository-internal references (file paths, script names, PR numbers, format
version numbers) are rewritten into reader-facing wording.
"""
import re
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2])

MARKS = {"●": r"\mNative{}", "◎": r"\mLinked{}", "○": r"\mConv{}", "–": r"\mNone{}"}


def clean(s: str) -> str:
    # --- reader-facing rewrites (before escaping) ---
    s = s.replace("spec.md 'Cell spatial position' (format 2.3): ",
                  "the cell spatial position schema of the format specification: ")
    s = s.replace(" (spec.md 'Cell spatial position', format 2.3)", " (format specification, cell spatial position)")
    s = s.replace("; format 2.3, PR #77)", ")")
    s = re.sub(r",? ?\(?format 2\.\d\)?", "", s)
    s = re.sub(r",? ?PR #\d+", "", s)
    s = s.replace("load_linked_scool / Dataset.contacts(group=) read them",
                  "load_linked_scool and the group pseudo-bulk query read them")
    # parentheses holding only repository paths
    def paths(m):
        inner = m.group(1)
        return " (ChromData format specification)" if "spec.md" in inner else ""
    s = re.sub(r"\s*\(((?:`[^`]*(?:/|\.py|\.md)[^`]*`(?:, )?)+)\)", paths, s)
    s = s.replace("`tests/core/test_cell_spatial.py`", "")
    # --- markdown -> LaTeX ---
    links = []

    def keep_link(m):
        links.append(m.group(2))
        return f"\x00{len(links) - 1}\x00"
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", keep_link, s)
    codes = []

    def keep_code(m):
        codes.append(m.group(1))
        return f"\x01{len(codes) - 1}\x01"
    s = re.sub(r"`([^`]+)`", keep_code, s)
    s = esc(s)
    s = re.sub(r"\*([^*]+)\*", r"\\emph{\1}", s)
    s = re.sub("\x01(\\d+)\x01", lambda m: r"\texttt{" + esc(codes[int(m.group(1))]) + "}", s)
    s = re.sub("\x00(\\d+)\x00", lambda m: r"\url{" + links[int(m.group(1))].replace("%", r"\%").replace("#", r"\#") + "}", s)
    for k, v in MARKS.items():
        s = s.replace(k, v)
    return s.strip()


def esc(s: str) -> str:
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
           "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(c, c) for c in s)


def test_cell(s: str) -> str:
    s = s.strip()
    if s.startswith("— (specification)"):
        return "specification only"
    s = s.replace("✓ (dedicated slot) ", "dedicated slot: ")
    s = s.replace("✓ (generic slot) ", "general-purpose slot: ")
    s = s.replace("✓ (external slot) ", "external file: ")
    s = s.replace("✓ not counted: ", "not counted: ")
    return clean(s)


def rows(block: str):
    lines = [l for l in block.strip().splitlines() if l.startswith("|")]
    return [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines[2:]]


# ---- summary matrix
m = re.search(r"\| Container \| spot coordinates.*?\n((?:\|.*\n)+)", src)
mat = rows(m.group(0))
lines = []
for r in mat:
    lines.append(esc(r[0]) + " & " + " & ".join(MARKS[c] for c in r[1:]) + r" \\")
(out / "tableS1_matrix.tex").write_text("\n".join(lines) + "\n")

# ---- changes after audits
chg = []
for sec in re.finditer(r"## (Changes after the audit of [0-9-]+)\n\n((?:\|[^\n]*\n)+)\n?(.*?)(?=\n## |\Z)", src, re.S):
    chg.append(r"\multicolumn{5}{@{}l}{\textit{" + esc(sec.group(1)) + r"}}\\[2pt]")
    for r in rows(sec.group(2)):
        chg.append(" & ".join(clean(c) for c in r) + r" \\")
    tail = sec.group(3).strip()
    if tail:
        chg.append(r"\multicolumn{5}{@{}p{\linewidth}@{}}{\footnotesize " + clean(tail) + r"}\\[3pt]")
(out / "tableS1_changes.tex").write_text("\n".join(chg) + "\n")

# ---- evidence per container
ev = []
body = src.split("## Evidence per cell", 1)[1]
for sec in re.finditer(r"### (.+?)\n\n((?:\|.*\n?)+)", body):
    ev.append(r"\multicolumn{4}{@{}l}{\textbf{" + esc(sec.group(1)) + r"}}\\*[2pt]")
    for r in rows(sec.group(2)):
        el, mark, evid, test = r
        mark_tex = clean(mark) if mark != "—" else "---"
        el_tex = clean(el).replace(r"(extra test: cells\_table\_json)", "(extra test: cell table as JSON)")
        el_tex = el_tex.replace(r"(extra test: cell\_emb\_matrix\_json)", "(extra test: embedding as JSON)")
        ev.append(f"{el_tex} & {mark_tex} & {clean(evid) if evid != '—' else '---'} & {test_cell(test)} \\\\")
    ev.append(r"\midrule")
if ev and ev[-1] == r"\midrule":
    ev.pop()
(out / "tableS1_evidence.tex").write_text("\n".join(ev) + "\n")
print("ok", len(mat), len(chg), len(ev))
