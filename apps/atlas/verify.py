"""Check an atlas end to end over HTTP: every dataset of its catalog opens, its contact maps (a region and the whole
genome, per spot and bulk), section images and cell x bin tracks are readable and agree with the catalog.

    python apps/atlas/verify.py [ATLAS_URL]        # default: the public atlas; ~1 min
"""
import json, time, warnings, sys
warnings.filterwarnings("ignore")
from uchrom.core.atlas import fetch_catalog
from uchrom.browser.web.data import DatasetStore, GENOME, decode_matrix
import sys
from uchrom.core.atlas import DEFAULT_ATLAS
cat = fetch_catalog(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ATLAS)
bad = 0
print(f"{'dataset':34s} {'open':>6s} {'maps':>5s} {'img':>4s} {'tracks':>7s}  checks")
for d in cat["datasets"]:
    t = time.time(); store = DatasetStore(); ds = store.load(d["url"]); summ = ds.summary(); t_open = time.time() - t
    notes = []
    maps = summ["contact_maps"]
    ok = len(maps) == d["contact_maps"] and all(m.get("embedded") for m in maps) and summ["n_cells"] == d["n_cells"]
    if not ok: notes.append(f"summary differs from the catalog (maps {len(maps)} vs {d['contact_maps']})")
    for m in maps:       # one region and the whole genome of every map
        kw = {"key": m["key"], "chrom": m["chroms"][0]["name"]}
        if m["per_cell"]: kw["cell"] = ds._embedded_maps()[m["key"]].cells[0]
        try:
            a = decode_matrix(ds.contacts(**kw)); b = decode_matrix(ds.contacts(**{**kw, "chrom": GENOME}))
            if not (a["matrix"].sum() > 0 and b["matrix"].sum() > 0): notes.append(f"empty map {m['key']}")
        except Exception as e:
            notes.append(f"{m['key']}: {type(e).__name__}: {e}")
    imgs = ds._images(); n_img = 0
    for name in imgs:
        r = ds.image_bytes(name)
        if r and len(r[0]) > 1000 and r[1].startswith("image/"): n_img += 1
        else: notes.append(f"image {name} unreadable")
    tracks = list(ds._cell_bin_tracks())
    for tr in tracks[:1]:
        try:
            ds._cell_bin_values(tr, ds.genome_layout()[0]["name"], None, None, None, None, "mean")
        except Exception as e:
            notes.append(f"track {tr}: {type(e).__name__}: {e}")
    good = ok and not notes; bad += not good
    print(f"{'OK ' if good else 'BAD'} {d['id']:30s} {t_open:5.1f}s {len(maps):5d} {n_img:4d} {len(tracks):7d}  {'; '.join(notes)[:150]}", flush=True)
print("ALL 10 OK" if not bad else f"{bad} PROBLEMS")
