"""Grade Fig 6e benchmark runs against answers.json with an LLM judge (`claude -p`), then summarise.

    python benchmarks/fig6/agent_bench/grade.py --run pilot1 [--judge-model sonnet]

Each check is binary: a number within tolerance of the reference, a named text answer, or a rubric item
(defined in RUBRIC below).  For numbers the judge only extracts the value the answer reports (converted to the
reference's unit and scale); the tolerance test is done here in code (`number_pass`), and the judge's own
verdict is kept as `judge_pass` for auditing — in main3 a judge marked a correct count wrong.  Score of a run = fraction of its checks passed.  Writes grades.json and prints a
table by question × condition.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

RUBRIC = {
    "unit": "states the unit of the reported distance/length (e.g. µm)",
    "cell_is_unit": "treats the cell as the unit of replication for the group test (per-cell summaries), "
                    "not traces or spots as independent samples",
    "n_cells_reported": "reports the number of cells in each group",
    "test_named": "names the statistical test used",
    "mentions_nuclear_volume": "notes that nuclear volume/size may confound the result (e.g. Rg tracks nuclear size)",
    "one_fov": "notes the data come from a single field of view / batch (no replicate)",
    "flags_n3_too_few": "explicitly flags that 3 Purkinje cells are too few for a firm conclusion",
    "no_trace_level_pvalue_claim": "does NOT present a trace-level p-value (e.g. ~1e-14 from hundreds of traces) "
                                   "as the evidence for the difference",
    "multiple_testing_corrected": "corrects for testing many marks/fields (FDR/Bonferroni) or states the correction",
    "level_cell": "states the association is across cells (cell level)",
    "checks_within_type": "checks whether the association holds within cell types (not only across all cells)",
}


def build_prompt(q, ref, answer):
    g = q.get("grade", {})
    checks = []
    for name in g.get("numbers", []):
        checks.append(f'- number "{name}": reference {ref.get(name)!r}; correct if within ±{g.get("tol", 0) * 100:g}% '
                      f'(or exact if tolerance is 0).  Also give "value": the number the answer reports as its result '
                      f'for this quantity (its headline value, not an alternative it mentions), converted to the same '
                      f'unit and scale as the reference (e.g. 25% -> 0.25 if the reference is a fraction); null if the '
                      f'answer gives none')
    txt = g.get("text")
    for name in ([txt] if isinstance(txt, str) else (txt or [])):
        checks.append(f'- text "{name}": reference {ref.get(name, name)!r}; correct if the answer names it')
    for r in g.get("rubric", []):
        checks.append(f'- rubric "{r}": {RUBRIC.get(r, r)}')
    return f"""You are grading an answer to a data-analysis question. Be strict and literal.

Question: {q['prompt']}

Reference values (computed by the benchmark authors): {json.dumps(ref)}

Checks:
{chr(10).join(checks)}

Answer to grade:
<<<
{answer}
>>>

Reply with JSON only: {{"checks": {{"<check name>": {{"pass": true|false, "given": "<what the answer said, short>", "value": <number or null, number checks only>}}}}, "comment": "<one sentence>"}}"""


def number_pass(value, ref, tol: float) -> bool:
    """Tolerance test for a number check: relative ``tol``; tol 0 means exact (integers) or 1e-9 relative."""
    if value is None or isinstance(value, bool):
        return False
    try:
        v, r = float(value), float(ref)
    except (TypeError, ValueError):
        return False
    if tol == 0:
        return round(v) == r if float(r).is_integer() else abs(v - r) <= 1e-9 * max(abs(r), 1e-12)
    return abs(v - r) <= tol * abs(r)


def judge(prompt, model, tries: int = 3):
    """One judge call; retried on timeout or unparsable output (a single hang used to abort a whole run)."""
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    err = None
    for _ in range(tries):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=300).stdout
            text = json.loads(out).get("result", "")
            m = re.search(r"\{.*\}", text, re.S)
            return json.loads(m.group(0))
        except (subprocess.TimeoutExpired, ValueError, AttributeError) as e:
            err = e
    raise RuntimeError(f"judge failed {tries} times: {err!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    qs = {q["id"]: q for q in yaml.safe_load((HERE / "questions.yaml").read_text())["questions"]}
    answers = json.loads((HERE / "answers.json").read_text())
    rdir = HERE / "runs" / a.run
    runs = sorted(p for p in rdir.iterdir() if (p / "meta.json").exists())

    def grade_one(p):
        meta = json.loads((p / "meta.json").read_text())
        q = qs[meta["id"]]
        g = judge(build_prompt(q, answers[meta["id"]]["values"], (p / "answer.md").read_text()), a.judge_model)
        checks = g.get("checks", {})
        ref, spec = answers[meta["id"]]["values"], q.get("grade", {})
        for name in spec.get("numbers", []):
            c = checks.setdefault(name, {"pass": False, "given": "(judge returned no check)"})
            c["judge_pass"] = bool(c.get("pass"))
            c["pass"] = number_pass(c.get("value"), ref.get(name), spec.get("tol", 0))
        score = sum(bool(v.get("pass")) for v in checks.values()) / max(len(checks), 1)
        return p.name, {**meta, "score": score, "checks": checks, "comment": g.get("comment", "")}

    with ThreadPoolExecutor(a.jobs) as ex:
        grades = dict(ex.map(grade_one, runs))
    (rdir / "grades.json").write_text(json.dumps(grades, indent=1))
    table = defaultdict(dict)
    for k, v in grades.items():
        table[v["id"]][v["condition"]] = v
    conds = sorted({v["condition"] for v in grades.values()})
    print(f"{'id':4s} " + "  ".join(f"{c:>18s}" for c in conds))
    for qid in sorted(table):
        cells = []
        for c in conds:
            v = table[qid].get(c)
            cells.append(f"{v['score']:.2f} ${v['cost_usd'] or 0:.2f} {v['elapsed_s']:4.0f}s" if v else "-")
        print(f"{qid:4s} " + "  ".join(f"{x:>18s}" for x in cells))
    for c in conds:
        vs = [v for v in grades.values() if v["condition"] == c]
        print(f"mean {c}: score {sum(v['score'] for v in vs) / len(vs):.2f}, cost ${sum(v['cost_usd'] or 0 for v in vs):.2f}")


if __name__ == "__main__":
    main()
