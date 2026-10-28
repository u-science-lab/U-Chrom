"""Cell embeddings for an atlas store: the view the web browser opens a dataset of many cells with.

A single-cell dataset without an embedding opens on its 3-D view alone, where the cells of a Dip-C or tracing
experiment pile up.  This adds ``cd.cellm`` embeddings (PCA, t-SNE, UMAP) from what the store holds:

* ``--hic KEY``: the per-cell contact maps linked under ``KEY``, summed into ``--hic-resolution`` bins
  (:func:`uchrom.fea.rebin_scool`, a ``.scool`` next to the store linked as ``KEY_<res>``) and embedded by
  scHiCluster (:func:`uchrom.emb.embed_contacts`, outputs ``hic_*``);
* ``--rna-regex RE`` / ``--rna-after COLUMN``: the RNA counts per cell — the numeric ``cells`` columns matching
  ``RE``, or every numeric column after ``COLUMN`` — embedded by :func:`uchrom.emb.embed_cells` (``rna_*``);
* ``--leiden``: Leiden clusters of the cells on the PCA of the store (``rna_pca``, else ``hic_pca``), as
  ``cells["leiden_rna"]`` / ``["leiden_hic"]`` (:func:`uchrom.emb.cluster_cells`) — what the browser colours a
  dataset without cell types by.  Embeddings already in the store are kept when only ``--leiden`` is given.

The store is read whole and written back (embedded copies kept); run it before ``python -m chromdata.embedded``.

Usage::

    python apps/atlas/recipes/derive_embeddings.py STORE.chromdata.zarr --hic per_cell [--hic-resolution 1000000]
    python apps/atlas/recipes/derive_embeddings.py STORE.chromdata.zarr --rna-after neuron_identity
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path


def rna_fields(cells, regex=None, after=None) -> list:
    numeric = [c for c in cells.columns if str(cells[c].dtype) not in ("category", "object", "str", "string", "bool")]
    if regex:
        return [c for c in numeric if re.fullmatch(regex, str(c))]
    cols = list(cells.columns)
    if after not in cols:
        raise SystemExit(f"--rna-after {after!r}: no such column")
    tail = set(cols[cols.index(after) + 1:])
    return [c for c in numeric if c in tail]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("store", type=Path)
    ap.add_argument("--hic", help="key of the linked per-cell contact maps")
    ap.add_argument("--hic-resolution", type=int, default=1_000_000)
    ap.add_argument("--rna-regex")
    ap.add_argument("--rna-after")
    ap.add_argument("--leiden", action="store_true")
    ap.add_argument("--leiden-resolution", type=float, default=1.0)
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()

    from chromdata import ChromData
    from uchrom.emb import cluster_cells, embed_cells, embed_contacts
    from uchrom.fea import rebin_scool

    t0 = time.time()
    store = a.store.resolve()
    cd = ChromData.read(store)
    print(f"read {store.name}: {cd.n_cells:,} cells, {cd.n_spots:,} spots ({time.time() - t0:.0f} s)", flush=True)
    if a.hic:
        label = f"{a.hic_resolution // 1_000_000}mb" if a.hic_resolution % 1_000_000 == 0 else f"{a.hic_resolution // 1000}kb"
        out = store.parent / f"{store.name.removesuffix('.chromdata.zarr')}_{label}.scool"
        key = f"{a.hic}_{label}"
        rebin_scool(cd, a.hic, resolution=a.hic_resolution, out=out, key_added=key)
        print(f"rebinned {a.hic} -> {out.name} ({key}) ({time.time() - t0:.0f} s)", flush=True)
        embed_contacts(cd, contacts=key, key_added="hic", n_threads=a.threads)
        print(f"hic embeddings: {[k for k in cd.cellm if k.startswith('hic_')]} ({time.time() - t0:.0f} s)", flush=True)
    if a.rna_regex or a.rna_after:
        fields = rna_fields(cd.cells, a.rna_regex, a.rna_after)
        if not fields:
            raise SystemExit("no RNA columns selected")
        embed_cells(cd, source="rna", fields=fields, features=f"{len(fields)} RNA counts per cell")
        print(f"rna embeddings from {len(fields)} genes: {[k for k in cd.cellm if k.startswith('rna_')]}", flush=True)
    if a.leiden:
        use = next((k for k in ("rna_pca", "hic_pca") if k in cd.cellm), None)
        if use is None:
            raise SystemExit("--leiden: no rna_pca / hic_pca in the store")
        key = f"leiden_{use.split('_')[0]}"
        labels = cluster_cells(cd, use=use, resolution=a.leiden_resolution, key_added=key)
        print(f"{key}: {labels.nunique()} clusters on {use}", flush=True)
    cd.write(store)
    print(f"wrote {store.name} ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
