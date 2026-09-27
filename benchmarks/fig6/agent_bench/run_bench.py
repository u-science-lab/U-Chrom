"""Run the Fig 6e agent benchmark: each question × condition in a fresh directory with `claude -p`.

Conditions (the only difference is the skills folder):
  docs    ./docs = U-Chrom documentation (README, concepts, guides)
  skills  ./docs + ./.claude/skills/<every skill in skills/>

    python benchmarks/fig6/agent_bench/run_bench.py --data-root <example-data> --ids A1,C1 \
        --conditions docs,skills --reps 1 --jobs 4 --run pilot1

Writes runs/<run>/<id>__<condition>__r<k>/{transcript.jsonl, answer.md, meta.json}.

Isolation: the agent sees no path into this repository.  The dataset is cloned (APFS `cp -c`, no extra space)
into ./data of a neutrally named temp dir, and `uchrom` comes from a venv with a non-editable wheel built from a
clean `git archive` of a fixed commit, so `uchrom.__file__` is in site-packages.  Build that venv once:

    SHA=$(git rev-parse --short HEAD); B=~/.cache/uchrom-bench/$SHA; mkdir -p $B/src
    git archive HEAD | tar -x -C $B/src && (cd $B/src && uv build --wheel -o $B/dist) && rm -rf $B/src
    uv pip freeze --python .venv/bin/python | grep -v '^-e ' > $B/requirements.txt
    uv venv --python .venv/bin/python $B/venv && uv pip install --python $B/venv/bin/python -r $B/requirements.txt $B/dist/*.whl

The agent runs under `sandbox-exec` with reads and writes denied below the U-Chrom checkouts (the parent of this
repo plus every `--deny` path) and below ~/.claude/projects/*U-Chrom* (Claude Code memories of those projects):
in main2, a `find /` located another checkout and read its build scripts.

Each run's meta.json records `repo_refs` (tool calls naming this repo or the data root — should be 0) and
`pkg_source_refs` (tool calls reading the installed uchrom source, which a real user could also do).
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
# sim: the in-repo h5cd — the .cdz under --data-root is ChromData 2.0, which the uchrom under test cannot read
# (same spots and coordinates; checked against ground_truth._read_cdz).
DATA = {"takei": "takei2025_fov0/takei2025_fov0.h5cd", "schicar": "schicar_mop/schicar_mop.h5cd",
        "sim": REPO / "example-data/sim_cell1/sim_cell1.h5cd"}
# Files of a dataset folder that are not given to the agent: raw source tables and backups.
DATA_EXCLUDE = ("*.csv", "*.bak.*")
PROMPT = """You are analysing 3-D genome data with U-Chrom: the Python package `uchrom` is installed \
(run it with `python`), and its documentation is in ./docs.

Data: {data}

Question: {question}

Work it out with code, then give a concise final answer: the key numbers with units, how you computed them, \
and anything that limits the conclusion."""


def clone_data(src: Path, w: Path) -> str:
    """Clone the dataset's folder (top-level files, minus DATA_EXCLUDE) into w/data; return the relative path.

    Linked files (.mcool / .scool next to the .h5cd) come along, since links are stored relative to the h5cd.
    """
    dst = w / "data" / src.parent.name
    dst.mkdir(parents=True)
    for f in src.parent.iterdir():
        if f.is_file() and not any(f.match(x) for x in DATA_EXCLUDE):
            subprocess.run(["cp", "-c", str(f), str(dst / f.name)], check=True)   # APFS clone
    return f"./data/{src.parent.name}/{src.name}"


def audit(lines: list[str], data_root: Path) -> dict:
    """Count tool calls whose input names this repo / the data root, or the installed uchrom source."""
    repo_marks = {str(REPO.parent), str(data_root.resolve())}
    repo = pkg = 0
    for l in lines:
        try:
            j = json.loads(l)
        except ValueError:
            continue
        if j.get("type") != "assistant":
            continue
        for c in j["message"].get("content", []):
            if c.get("type") != "tool_use":
                continue
            inp = json.dumps(c.get("input", {}))
            repo += any(m in inp for m in repo_marks)
            pkg += "site-packages/uchrom" in inp or "uchrom.__file__" in inp or "inspect.getsource" in inp
    return {"repo_refs": repo, "pkg_source_refs": pkg}


def sandbox_profile(deny: list[Path]) -> str:
    """macOS sandbox-exec profile: allow everything except reading/writing the given trees and U-Chrom memories."""
    paths = "\n".join(f'  (subpath "{d}")' for d in deny)
    return f"""(version 1)
(allow default)
(deny file-read* file-write*
{paths}
  (regex #"^{Path.home()}/\\.claude/projects/[^/]*U-Chrom"))
"""


def workdir(condition: str, agent: str = "claude") -> Path:
    # neutral name: the agent should not learn it is in a benchmark, or which condition
    w = Path(tempfile.mkdtemp(prefix="analysis_"))
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
            agent: str = "claude", venv: Path | None = None, deny: list[Path] | None = None):
    d = out / f"{q['id']}__{condition}__r{rep}"
    if (d / "meta.json").exists():
        return json.loads((d / "meta.json").read_text())
    d.mkdir(parents=True, exist_ok=True)
    w = workdir(condition, agent)
    data = clone_data((data_root / DATA[q["data"]]).resolve(), w)
    prompt = PROMPT.format(data=data, question=q["prompt"])
    if agent == "claude":
        # Project settings only, no MCP servers: the user's own skills, plugins and claude.ai connectors
        # would otherwise be listed next to the benchmark skills (36 extra in main2).  Built-in skills remain.
        mcp = w.parent / f"{w.name}.mcp.json"          # outside the workdir, like the sandbox profile
        mcp.write_text('{"mcpServers": {}}')
        cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
               "--allowedTools", "Bash", "Read", "Glob", "Grep", "Skill",
               "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", str(mcp)]
        if model:
            cmd += ["--model", model]
    else:  # codex (read-only data, writes only in its workdir)
        cmd = ["codex", "exec", "--skip-git-repo-check", "-C", str(w), "-s", "workspace-write", "--json",
               "-o", str(d / "answer_codex.md"), prompt]
        if model:
            cmd += ["-m", model]
    # uchrom from the isolated venv only: drop PATH entries inside the repo and any activated venv
    path = [x for x in os.environ["PATH"].split(os.pathsep) if not x.startswith(str(REPO.parent))]
    env = {**os.environ, "PATH": os.pathsep.join([str(venv / "bin"), *path])}
    for k in ("UCHROM_BROWSER_URL", "VIRTUAL_ENV", "PYTHONPATH", "CONDA_PREFIX"):
        env.pop(k, None)
    # A Bash call past Claude Code's 120 s default is moved to the background, and under `claude -p` the agent
    # then ends its turn without the result (TAD calls in B7/B8/C3).  Let such calls run in the foreground.
    env["BASH_DEFAULT_TIMEOUT_MS"] = env["BASH_MAX_TIMEOUT_MS"] = "600000"
    if deny:
        prof = w / ".." / f"{w.name}.sb"             # outside the workdir, so the agent never sees it
        prof.write_text(sandbox_profile(deny))
        cmd = ["sandbox-exec", "-f", str(prof), *cmd]
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
            "model": init.get("model"), "skills_used": skills_used, "workdir": str(w), "venv": str(venv),
            "claude_code_version": init.get("claude_code_version"),
            "sandbox_deny": [str(x) for x in deny or []], "skills_listed": init.get("skills"),
            **audit(lines, data_root)}
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    shutil.rmtree(w, ignore_errors=True)
    if agent == "claude":
        mcp.unlink(missing_ok=True)
    if deny:
        prof.unlink(missing_ok=True)
    print(f"{q['id']:4s} {condition:6s} r{rep}  {meta['elapsed_s']:5.0f} s  ${meta['cost_usd'] or 0:.2f}  "
          f"turns {meta['num_turns']}  skills {skills_used}  repo_refs {meta['repo_refs']}", flush=True)
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
    ap.add_argument("--deny", type=Path, action="append", default=[],
                    help="extra U-Chrom checkout to hide from the agent (repeatable); the parent of this repo is "
                         "always hidden")
    ap.add_argument("--no-sandbox", action="store_true")
    ap.add_argument("--venv", type=Path, default=None,
                    help="isolated venv (default ~/.cache/uchrom-bench/<HEAD short sha>/venv; see module docstring)")
    a = ap.parse_args()
    if a.venv is None:
        sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
        a.venv = Path.home() / ".cache/uchrom-bench" / sha / "venv"
    if not (a.venv / "bin/python").exists():
        raise SystemExit(f"no benchmark venv at {a.venv}; build it as described in the module docstring")
    a.venv = a.venv.resolve()
    deny = [] if a.no_sandbox else sorted({REPO.parent.resolve(), *(d.resolve() for d in a.deny)})
    for d in deny:
        if a.venv.is_relative_to(d):   # data are cloned before the sandbox starts, so --data-root may be inside
            raise SystemExit(f"venv {a.venv} is inside a hidden tree {d}")
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
        list(ex.map(lambda t: run_one(t[0], t[1], t[2], a.data_root, t[3], t[4], a.timeout, a.agent, a.venv, deny), tasks))
    print("->", HERE / "runs" / a.run)


if __name__ == "__main__":
    main()
