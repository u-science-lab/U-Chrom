"""Fig 6d — a real agent session: the researcher's selection → Claude Code + skills → views in the browser.

1. Start the browser on Takei 2025 FOV 0 and open the page (Playwright, Chromium).
2. The "researcher" selects the 8 Bergmann cells.  This uses the page's own selection action
   (`select_cells`, the same store call as a lasso in the Embedding view).
3. Run Claude Code non-interactively (`claude -p`) in an empty directory whose only context is the two
   skills (`skills/compare-groups`, `skills/show-in-browser`), allowed tools Bash/Read/Glob/Grep.
4. Save everything to this folder: the transcript (stream-json), the answer, the page screenshot, a
   PNG of each view the agent opened, and run metadata.

    .venv/bin/python paper/fig6/agent_run/run_d.py [--data example-data/takei2025_fov0/takei2025_fov0.h5cd]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "benchmarks/fig6"))

from bench_frontend import LAUNCH, free_port, start_server  # noqa: E402

QUESTION = "What is different about the cells I just selected in the browser? Show me."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO / "example-data/takei2025_fov0/takei2025_fov0.h5cd"))
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=int, default=1200)
    a = ap.parse_args()

    import requests
    from playwright.sync_api import sync_playwright

    import uchrom.browser as ub
    from uchrom.core import ChromData

    port = free_port()
    proc = start_server(port)
    base = f"http://127.0.0.1:{port}"
    requests.post(base + "/api/datasets", json={"path": str(Path(a.data).resolve())}, timeout=600).raise_for_status()
    work = Path(tempfile.mkdtemp(prefix="uchrom_agent_d_"))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**LAUNCH)
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
            page.goto(base + "/")
            page.wait_for_function("performance.getEntriesByName('uchrom:geometry-drawn').length > 0", timeout=120_000)
            ws = ub.connect(base)
            cd = ChromData.read(a.data)
            berg = [str(c) for c in cd.cells.index[cd.cells["cell_type"].astype(str) == "Bergmann"]]
            sel = ws.select_cells(cells=berg)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(HERE / "before.png"))
            views_before = {v["pane"] for v in ws.describe()["views"]}

            # the agent's working directory: nothing but the skills
            (work / ".claude/skills").mkdir(parents=True)
            for s in ("compare-groups", "show-in-browser"):
                shutil.copytree(REPO / "skills" / s, work / ".claude/skills" / s)
            env = {**os.environ, "UCHROM_BROWSER_URL": base,
                   "PATH": f"{REPO / '.venv/bin'}{os.pathsep}{os.environ['PATH']}"}
            cmd = ["claude", "-p", QUESTION, "--output-format", "stream-json", "--verbose",
                   "--allowedTools", "Bash", "Read", "Glob", "Grep", "Skill"]
            if a.model:
                cmd += ["--model", a.model]
            t0 = time.time()
            # run the agent while the page stays open (the browser serves its actions)
            agent = subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # drain both pipes continuously: a large tool result must never block the agent
            out, err = [], []
            readers = [threading.Thread(target=lambda f, buf: buf.extend(iter(f.readline, b"")), args=(agent.stdout, out), daemon=True),
                       threading.Thread(target=lambda f, buf: buf.extend(iter(f.readline, b"")), args=(agent.stderr, err), daemon=True)]
            for r in readers:
                r.start()
            while agent.poll() is None and time.time() - t0 < a.timeout:
                page.wait_for_timeout(500)          # keep the page's event loop running
            if agent.poll() is None:
                agent.kill()
            for r in readers:
                r.join(10)
            lines = [l.decode("utf-8", "replace").rstrip("\n") for l in out if l.strip()]
            err = b"".join(err).decode("utf-8", "replace")
            (HERE / "transcript.jsonl").write_text("\n".join(lines) + "\n")
            elapsed = time.time() - t0

            page.wait_for_timeout(2500)
            page.screenshot(path=str(HERE / "after.png"))
            new_views = [v for v in ws.describe()["views"] if v["pane"] not in views_before]
            for v in new_views:   # as the researcher saw them
                ws.capture(pane=v["pane"], path=str(HERE / f"view_{v['pane']}_{v['type']}.png"))
            # for the figure: each new view alone (tabs layout) at a fixed size — layout only, content unchanged
            page.set_viewport_size({"width": 1180, "height": 860})
            ws.arrange(layout="tabs")
            for v in new_views:
                ws.show_view(pane=v["pane"])
                page.wait_for_timeout(1200)
                ws.capture(pane=v["pane"], path=str(HERE / f"fig_{v['pane']}_{v['type']}.png"))
            final = {}
            for l in reversed(lines):
                try:
                    d = json.loads(l)
                except ValueError:
                    continue
                if d.get("type") == "result":
                    final = d
                    break
            (HERE / "answer.md").write_text(final.get("result", "") + "\n")
            meta = {"question": QUESTION, "selection": sel, "n_selected": len(berg), "elapsed_s": elapsed,
                    "returncode": agent.returncode, "stderr_tail": err[-2000:], "new_views": new_views,
                    "model": final.get("model") or a.model, "cost_usd": final.get("total_cost_usd"),
                    "num_turns": final.get("num_turns"), "claude_version": subprocess.run(
                        ["claude", "--version"], capture_output=True, text=True).stdout.strip(),
                    "data": str(Path(a.data).name), "workdir": str(work),
                    "figure_captures": "after the session: tabs layout, 1180x860 viewport, one view at a time"}
            (HERE / "run.json").write_text(json.dumps(meta, indent=1))
            print(json.dumps({k: meta[k] for k in ("elapsed_s", "returncode", "new_views", "cost_usd", "num_turns")}, indent=1))
            browser.close()
    finally:
        proc.terminate()
        proc.wait(10)


if __name__ == "__main__":
    main()
