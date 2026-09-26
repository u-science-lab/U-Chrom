"""Run the Fig 6e agent benchmark: each question × condition in a fresh directory with `claude -p`.

Conditions (the only difference is the skills folder):
  docs    ./docs = U-Chrom documentation (README, concepts, guides)
  skills  ./docs + ./.claude/skills/<every skill in skills/>

    python benchmarks/fig6/agent_bench/run_bench.py --data-root <example-data> --ids A1,C1 \
        --conditions docs,skills --reps 1 --jobs 4 --run pilot1

Writes runs/<run>/<id>__<condition>__r<k>/{transcript.jsonl, answer.md, meta.json}.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DATA = {"takei": "takei2025_fov0/takei2025_fov0.h5cd", "schicar": "schicar_mop/schicar_mop.h5cd",
        "sim": "sim_cell1/sim_cell1.cdz"}
PROMPT = """You are analysing 3-D genome data with U-Chrom: the Python package `uchrom` is installed \
(run it with `python`), and its documentation is in ./docs.

Data: {data}

Question: {question}

Work it out with code, then give a concise final answer: the key numbers with units, how you computed them, \
and anything that limits the conclusion."""


def workdir(condition: str, agent: str = "claude") -> Path:
    w = Path(tempfile.mkdtemp(prefix=f"uchrom_bench_{condition}_"))
    docs = w / "docs"
    docs.mkdir()
    shutil.copy(REPO / "README.md", docs / "README.md")
    for p in (REPO / "docs/source").glob("*.md"):
        shutil.copy(p, docs / p.name)
    shutil.copytree(REPO / "docs/source/guide", docs / "guide")
    if condition == "skills":
        # Claude Code reads project skills from .claude/skills; Codex from .agents/skills (unverified: Codex
        # was over its usage limit when this was written)
        target = ".claude/skills" if agent == "claude" else ".agents/skills"
        for s in (REPO / "skills").iterdir():
            if (s / "SKILL.md").exists():
                shutil.copytree(s, w / target / s.name, ignore=shutil.ignore_patterns("__pycache__"))
    return w


def run_one(q: dict, condition: str, rep: int, data_root: Path, out: Path, model: str | None, timeout: int,
            agent: str = "claude"):
    d = out / f"{q['id']}__{condition}__r{rep}"
    if (d / "meta.json").exists():
        return json.loads((d / "meta.json").read_text())
    d.mkdir(parents=True, exist_ok=True)
    w = workdir(condition, agent)
    prompt = PROMPT.format(data=(data_root / DATA[q["data"]]).resolve(), question=q["prompt"])
    if agent == "claude":
        cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
               "--allowedTools", "Bash", "Read", "Glob", "Grep", "Skill"]
        if model:
            cmd += ["--model", model]
    else:  # codex (read-only data, writes only in its workdir)
        cmd = ["codex", "exec", "--skip-git-repo-check", "-C", str(w), "-s", "workspace-write", "--json",
               "-o", str(d / "answer_codex.md"), prompt]
        if model:
            cmd += ["-m", model]
    env = {**os.environ, "PATH": f"{REPO / '.venv/bin'}{os.pathsep}{os.environ['PATH']}"}
    env.pop("UCHROM_BROWSER_URL", None)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=w, env=env, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
        out_b, rc = p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        out_b, rc = e.stdout or b"", "timeout"
    lines = [l for l in out_b.decode("utf-8", "replace").splitlines() if l.strip()]
    (d / "transcript.jsonl").write_text("\n".join(lines) + "\n")
    final, init = {}, {}
    for l in lines:
        try:
            j = json.loads(l)
        except ValueError:
            continue
        if j.get("type") == "result":
            final = j
        if j.get("type") == "system" and j.get("subtype") == "init":
            init = j
    if agent == "codex":
        a_file = d / "answer_codex.md"
        final = {"result": a_file.read_text() if a_file.exists() else ""}
    (d / "answer.md").write_text(final.get("result", "") + "\n")
    skills_used = sorted({json.loads(l)["message"]["content"][0]["input"].get("skill", "")
                          for l in lines if '"name":"Skill"' in l.replace(" ", "")
                          and json.loads(l).get("type") == "assistant"} - {""})
    meta = {"id": q["id"], "condition": condition, "rep": rep, "agent": agent, "model_requested": model,
            "returncode": rc, "elapsed_s": time.time() - t0,
            "cost_usd": final.get("total_cost_usd"), "num_turns": final.get("num_turns"),
            "model": init.get("model"), "skills_used": skills_used, "workdir": str(w)}
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    shutil.rmtree(w, ignore_errors=True)
    print(f"{q['id']:4s} {condition:6s} r{rep}  {meta['elapsed_s']:5.0f} s  ${meta['cost_usd'] or 0:.2f}  "
          f"turns {meta['num_turns']}  skills {skills_used}", flush=True)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--conditions", default="docs,skills")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--models", default="", help="comma-separated; claude: opus,sonnet,haiku")
    ap.add_argument("--agent", default="claude", choices=["claude", "codex"])
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--run", default=time.strftime("run_%Y%m%d_%H%M"))
    a = ap.parse_args()
    qs = yaml.safe_load((HERE / "questions.yaml").read_text())["questions"]
    ids = set(filter(None, a.ids.split(",")))
    qs = [q for q in qs if not ids or q["id"] in ids]
    models = [m for m in a.models.split(",") if m] or [None]
    tasks = []
    for m in models:
        out = HERE / "runs" / a.run / f"{a.agent}-{m or 'default'}"
        out.mkdir(parents=True, exist_ok=True)
        tasks += [(q, c, r, out, m) for r in range(a.reps) for q in qs for c in a.conditions.split(",")]
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda t: run_one(t[0], t[1], t[2], a.data_root, t[3], t[4], a.timeout, a.agent), tasks))
    print("->", HERE / "runs" / a.run)


if __name__ == "__main__":
    main()
