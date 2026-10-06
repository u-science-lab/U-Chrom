"""Link the reprocessed spatial ATAC-Hi-C contact maps (GSE307620) into mouse_brain.chromdata.zarr.

The contacts come from our Sherlock pipeline (example-data/spatial_atac_hic/sherlock/: SRA reads
-> bwa -> pairtools -> pairs_to_cool.py), one folder per section on Oak.  Copy the outputs
here first (they are not public; see example-data/README.md, "spatial_atac_hic")::

    for s in MouseBrainR6 MouseBrainR8; do for f in pixels_1Mb.scool bulk.mcool barcode_stats.tsv log.json; do
      rsync -a sherlock-dtn:$OAK/uchrom/spatial_atac_hic/$s/$s.$f example-data/spatial_atac_hic/contacts/; done; done

then::

    python example-data/link_spatial_atac_hic_contacts.py

Per section it writes ``mouse_brain_<section>.spots_1Mb.scool`` — the pipeline's .scool with every
cell renamed from its 16-base spot barcode (barcode A + barcode B, read order) to the store's
cell id ``<section>:<barcode>``, keeping the store's spots only — and links it as
``per_spot.<section>`` (cells follow the focus / groups in the browser) next to the merged map
``bulk.<section>`` (``contacts/<section>.bulk.mcool`` as copied).  ``uns['contacts_stats'][<section>]`` records the
pipeline counts and the agreement with the authors' per-spot Hi-C fragment counts
(``cells.n_fragments_hic``).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from uchrom import ChromData

HERE = Path(__file__).resolve().parent / "spatial_atac_hic"
STORE = HERE / "mouse_brain.chromdata.zarr"
SECTIONS = ["MouseBrainR6", "MouseBrainR8"]


def rename_scool(src: Path, dst: Path, rename: dict) -> int:
    """Copy ``src`` to ``dst`` with cells renamed (``rename``: old -> new); others dropped."""
    tmp = dst.with_suffix(".tmp")
    shutil.copyfile(src, tmp)
    with h5py.File(tmp, "r+") as f:
        cells = f["cells"]
        for name in list(cells.keys()):
            new = rename.get(name)
            if new is None:
                del cells[name]
            elif new != name:
                cells.move(name, new)
        n = len(cells)
    tmp.replace(dst)
    return n


def main() -> None:
    cd = ChromData.read(STORE)
    cells = cd.cells
    stats = dict(cd.uns.get("contacts_stats") or {})
    for sec in SECTIONS:
        src = HERE / "contacts"
        scool, mcool = src / f"{sec}.pixels_1Mb.scool", src / f"{sec}.bulk.mcool"
        if not scool.exists() or not mcool.exists():
            raise SystemExit(f"{scool.name} / {mcool.name} missing: copy them from Oak first (see the docstring)")
        c = cells[cells["section"] == sec]
        rename = dict(zip(c["barcode"].astype(str), c.index.astype(str)))
        out = HERE / f"mouse_brain_{sec}.spots_1Mb.scool"
        n = rename_scool(scool, out, rename)
        cd.link_scool(f"{out.name}", key=f"per_spot.{sec}", cell_name="cell id (<section>:<barcode A><barcode B>)",
                      genome_assembly="mm10", bin_size=1_000_000, label=f"{sec}, per spot",
                      source="reprocessed from SRA (example-data/spatial_atac_hic/sherlock)")
        cd.link_cool(f"contacts/{mcool.name}", key=f"bulk.{sec}", label=f"{sec}, all spots (merged)", genome_assembly="mm10")

        # agreement with the authors' per-spot Hi-C fragment counts
        bc = pd.read_csv(src / f"{sec}.barcode_stats.tsv", sep="\t").set_index("barcode_pair")
        ours = bc.reindex(c["barcode"].astype(str))["pairs"].to_numpy(float)
        auth = c["n_fragments_hic"].to_numpy(float)
        ok = np.isfinite(ours) & (auth > 0)
        log_r = float(np.corrcoef(np.log1p(ours[ok]), np.log1p(auth[ok]))[0, 1])
        swapped = bc.reindex([b[8:] + b[:8] for b in c["barcode"].astype(str)])["pairs"].to_numpy(float)
        ok2 = np.isfinite(swapped) & (auth > 0)
        log_r_swapped = float(np.corrcoef(np.log1p(swapped[ok2]), np.log1p(auth[ok2]))[0, 1])
        pipe = json.loads((src / f"{sec}.log.json").read_text())
        stats[sec] = {
            **{k: pipe[k] for k in ("lines", "kept", "duplicates", "low_mapq", "short_cis", "bad_barcode", "min_mapq", "min_cis_dist")},
            "spots_with_map": n,
            "spots_in_store": int(len(c)),
            "authors_vs_ours_log_pearson": round(log_r, 4),
            "authors_vs_ours_spearman": round(float(spearmanr(ours[ok], auth[ok]).statistic), 4),
            "barcode_order_check_log_pearson_swapped": round(log_r_swapped, 4),
            "ours_over_authors_total": round(float(ours[ok].sum() / auth[ok].sum()), 4),
        }
        print(sec, json.dumps(stats[sec]))
    cd.uns["contacts_stats"] = stats
    cd.write(STORE)
    print("wrote", STORE)


if __name__ == "__main__":
    main()
