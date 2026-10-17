"""Interactivity of the hosted browser on the atlas stores, over HTTP (Brief Communication Fig. 2b, Supp. Fig. 5).

For every dataset of the atlas catalogue, through the hosted browser (``--hosted``) reading the stores from the
atlas' object storage (``--data``), in one session:

* **open**: ``POST /api/datasets`` with the store URL (the summary the page shows first);
* **first view**: the overview the page draws first -- the 3-D geometry when the store has coordinates, else the
  tissue positions of its first spatial set, else its first embedding;
* **bulk map**: the first merged contact map (``.cool`` / ``.mcool``), ``chr2``;
* **one cell**: one cell's or spot's map from the per-cell ``.scool``, ``chr2``;
* **all cells**: the pseudo-bulk of every cell from the per-cell maps (the server sums at most 20,000), ``chr2``.

Each request is timed end to end from this client (wall clock, ``time.perf_counter``); ``--reps`` passes are made,
the first one is the store's first open in the session.  The dataset is closed after each pass
(``DELETE /api/datasets/{id}``).  The container is woken first (``/api/health``) and that wait is not counted.

Writes ``<uchrom-reproducibility>/manuscripts/nmeth-bc/figures/results/hosted.json``.

    python apps/atlas/benchmarks/hosted.py [--reps 2] [--only ID ...]
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "benchmarks"))   # _paper.py
from _paper import paper_root  # noqa: E402

HOSTED = "https://uchrom-browser.u-science.org"
DATA = "https://uchrom-atlas-r2.u-science.org"


def timed(fn):
    t = time.perf_counter()
    r = fn()
    return r, round(time.perf_counter() - t, 3)


def wake(s: requests.Session, base: str) -> float:
    t = time.perf_counter()
    for _ in range(30):
        try:
            if s.get(f"{base}/api/health", timeout=150).status_code == 200:
                return round(time.perf_counter() - t, 1)
        except requests.RequestException:
            pass
        time.sleep(5)
    raise SystemExit("the hosted browser did not answer")


def one_pass(s: requests.Session, base: str, url: str) -> dict:
    out: dict = {}
    r, out["open"] = timed(lambda: s.post(f"{base}/api/datasets", json={"path": url}, timeout=600))
    r.raise_for_status()
    d = r.json()
    i = d["id"]
    out["n_cells"], out["n_spots"] = d.get("n_cells"), d.get("n_spots")
    maps = d.get("contact_maps") or []
    try:
        if d.get("n_spots"):
            r, out["first_view"] = timed(lambda: s.post(f"{base}/api/datasets/{i}/geometry", json={}, timeout=600))
            out["first_view_kind"] = "geometry"
        elif d.get("spatial"):
            key = d["spatial"][0]["key"]
            r, out["first_view"] = timed(lambda: s.get(f"{base}/api/datasets/{i}/spatial/{key}", timeout=600))
            out["first_view_kind"] = "spatial"
        elif d.get("embeddings"):
            key = d["embeddings"][0]["key"]
            r, out["first_view"] = timed(lambda: s.get(f"{base}/api/datasets/{i}/embedding/{key}", timeout=600))
            out["first_view_kind"] = "embedding"
        out["first_view_status"] = r.status_code
        bulk = next((m["key"] for m in maps if m.get("kind") in ("cool", "mcool")), None)
        per = next((m["key"] for m in maps if m.get("kind") == "scool"), None)
        if bulk:
            r, out["bulk_map"] = timed(lambda: s.get(f"{base}/api/datasets/{i}/contacts/{bulk}", params={"chrom": "chr2"}, timeout=600))
            out["bulk_map_status"] = r.status_code
        if per:
            cells = [c["cell_id"] for c in s.get(f"{base}/api/datasets/{i}/cells", params={"limit": 20000},
                                                    timeout=600).json()["cells"]]
            step = max(1, len(cells) // 50)
            for k, cell in enumerate(cells[::step]):    # the first cell with a map (RNA sections have none)
                r, t = timed(lambda: s.get(f"{base}/api/datasets/{i}/contacts/{per}",
                                           params={"chrom": "chr2", "cell": cell}, timeout=600))
                if r.status_code != 404:
                    break
            out["one_cell"], out["one_cell_status"], out["one_cell_tries"] = t, r.status_code, k + 1
            r, out["all_cells"] = timed(lambda: s.get(f"{base}/api/datasets/{i}/contacts/{per}",
                                                      params={"chrom": "chr2", "group": "all"}, timeout=900))
            out["all_cells_status"] = r.status_code
    finally:
        s.delete(f"{base}/api/datasets/{i}", timeout=120)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hosted", default=HOSTED)
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    s = requests.Session()
    cat = s.get(f"{args.data}/catalog.json", timeout=120).json()
    woke = wake(s, args.hosted)
    rows = []
    for d in cat["datasets"]:
        if args.only and d["id"] not in args.only:
            continue
        url = d.get("url") or f"{args.data}/{d['path']}"
        passes = []
        for rep in range(args.reps):
            try:
                passes.append(one_pass(s, args.hosted, url))
            except Exception as exc:                         # record and go on
                passes.append({"error": f"{type(exc).__name__}: {exc}"[:300]})
        rows.append({"id": d["id"], "size_mb": d.get("size_mb"), "passes": passes})
        print(d["id"], json.dumps(passes[0])[:200], flush=True)
    root = paper_root()
    if root is None:
        raise SystemExit("uchrom-reproducibility not found (set UCHROM_REPRO)")
    out = root / "manuscripts" / "nmeth-bc" / "figures" / "results" / "hosted.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.only and out.exists():                        # a partial run replaces only its datasets
        old = {r["id"]: r for r in json.loads(out.read_text())["datasets"]}
        old.update({r["id"]: r for r in rows})
        rows = [old[d["id"]] for d in cat["datasets"] if d["id"] in old]
    out.write_text(json.dumps({"generated": time.strftime("%Y-%m-%d %H:%M %Z"), "hosted": args.hosted,
                               "data": args.data, "client": {"host": socket.gethostname(), "python": platform.python_version()},
                               "wake_s": woke, "reps": args.reps, "datasets": rows}, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
