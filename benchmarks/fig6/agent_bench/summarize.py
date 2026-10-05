"""Summarise graded Fig 6e runs into u-chrom-paper/manuscripts/full/figures/fig6/results/agent_bench.json.

    python benchmarks/fig6/agent_bench/summarize.py --run main2

Reads runs/<run>/<agent-model>/grades.json (from grade.py) and writes, per model and condition: mean score
overall, by category and by split, the number of tasks where a skill was loaded, cost and median time, plus a
paired Wilcoxon test of skills vs docs over tasks.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import yaml
from scipy.stats import wilcoxon

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from _paper import results_dir  # noqa: E402

OUT = results_dir("fig6") / "agent_bench.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--judge", default="claude-sonnet-5", help="recorded in the output")
    a = ap.parse_args()
    qs = {q["id"]: q for q in yaml.safe_load((HERE / "questions.yaml").read_text())["questions"]}
    cats = sorted({q["category"] for q in qs.values()})
    models = {}
    for gfile in sorted((HERE / "runs" / a.run).glob("*/grades.json")):
        g = json.loads(gfile.read_text())
        rows = list(g.values())
        m = {"model": rows[0]["model"], "conditions": {}}
        for c in ("docs", "skills"):
            R = [r for r in rows if r["condition"] == c]
            m["conditions"][c] = {
                "n_tasks": len({r["id"] for r in R}),
                "n_runs": len(R),
                "score": st.mean(r["score"] for r in R),
                "by_category": {k: st.mean(r["score"] for r in R if qs[r["id"]]["category"] == k) for k in cats},
                "by_split": {s: st.mean(r["score"] for r in R if qs[r["id"]]["split"] == s) for s in ("dev", "test")},
                "n_perfect": sum(r["score"] == 1 for r in R),
                "n_zero": sum(r["score"] == 0 for r in R),
                "n_skill_loaded": sum(bool(r["skills_used"]) for r in R),
                "n_failed_runs": sum(r["returncode"] != 0 for r in R),
                "cost_usd": sum(r["cost_usd"] or 0 for r in R),
                "median_time_s": st.median(r["elapsed_s"] for r in R),
                # each task's score averaged over its repeats (error bars across tasks)
                "per_task": {i: st.mean(r["score"] for r in R if r["id"] == i) for i in sorted({r["id"] for r in R})},
            }
        ids = sorted({r["id"] for r in rows})
        # paired over tasks, each task's score averaged over its repeats
        tm = {(i, c): st.mean(r["score"] for r in rows if r["id"] == i and r["condition"] == c)
              for i in ids for c in ("docs", "skills")}
        d = [tm[(i, "skills")] - tm[(i, "docs")] for i in ids]
        nz = [x for x in d if x]
        m["paired"] = {"mean_diff": st.mean(d), "better": sum(x > 0 for x in d), "worse": sum(x < 0 for x in d),
                       "same": sum(x == 0 for x in d), "wilcoxon_p": wilcoxon(nz).pvalue if nz else None}
        models[gfile.parent.name.removeprefix("claude-")] = m
    reps = sorted({len({r["rep"] for r in json.loads(f.read_text()).values() if r["id"] == i and r["condition"] == c})
                   for f in (HERE / "runs" / a.run).glob("*/grades.json")
                   for i in qs for c in ("docs", "skills")})
    task_meta = {i: {"category": q["category"], "split": q["split"]} for i, q in qs.items()}
    out = {"run": a.run, "judge": a.judge, "tasks": task_meta, "reps": reps[0] if len(reps) == 1 else reps, "n_tasks": len(qs), "categories": cats,
           "category_sizes": {k: sum(q["category"] == k for q in qs.values()) for k in cats}, "models": models}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print("->", OUT)


if __name__ == "__main__":
    main()
