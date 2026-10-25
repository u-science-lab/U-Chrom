"""Add the per-spot contact statistics of the spatial Hi-C-RNA samples (GEO GSE311199) to the hicrna_* stores.

The statistics come from one more pass over each sample's ``.nodups.pairs.gz`` on a compute cluster
(``spatial_hicrna/slurm/contact_stats.sbatch`` -> ``spatial_pairs_stats.py``, ``uchrom.io.ContactStats``):
per spot, the cis contact-distance histogram in scHiCluster's log2 bins (2.5 kb x 2^(k/8), the bins of Guo et al.
2026's short / long-range ratio), per read orientation, and the cis and trans contacts per chromosome; MAPQ >= 30
on both legs, in-tissue spots, main chromosomes — the contacts of the per-spot maps.  Copy
``<sample>.contact_stats_q30.npz`` from the archive (``$UCHROM_ARCHIVE/spatial_3dgenome/<sample>/``) into
``$UCHROM_DATA/spatial_hicrna/contacts/`` over the DTN, then::

    python apps/atlas/recipes/link_spatial_hicrna_contact_stats.py [SAMPLE ...]

Per store this writes (``ContactStats.write(per_chromosome=False)``, int32)

  * ``cellm["contacts.distance"]`` (spots x distance bins — 132 mm10, 134 hg38 — summed over the chromosomes),
    ``cellm["contacts.orientation"]`` (spots x 4 x 133), ``cellm["contacts.cis"]`` / ``["contacts.trans"]``
    (spots x chromosomes),
  * ``cells["contacts.n_cis"]`` / ``["contacts.n_trans"]``,
  * ``uns["contact_stats"]["contacts"]`` (edges, chromosomes, filter, source),

after checking spot by spot that cis + trans equal the store's ``hic_contacts`` (the per-spot maps' counts).
``uchrom.fea.contact_features(cd)`` then gives the short / long ratio, distance bands, decay slopes and cis
fraction of every spot.
"""

from __future__ import annotations

import sys

import numpy as np

from uchrom import ChromData
from uchrom.datasets import data_dir
from uchrom.io import ContactStats

ROOT = data_dir() / "spatial_hicrna"
CONTACTS = ROOT / "contacts"
STORE_OF = {"mouse_brain_r1": "mouse_brain", "mouse_brain_r2": "mouse_brain",
            "mouse_embryo_E11.5": "mouse_embryo", "mouse_embryo_E13.5_r1": "mouse_embryo",
            "mouse_embryo_E13.5_r2": "mouse_embryo",
            "human_melanoma_r1": "human_melanoma", "human_melanoma_r2": "human_melanoma"}


def main(samples: list) -> None:
    by_store: dict = {}
    for s in samples:
        by_store.setdefault(STORE_OF[s], []).append(s)
    for store, secs in by_store.items():
        path = ROOT / f"hicrna_{store}.chromdata.zarr"
        cd = ChromData.read(path)
        merged = None
        for sample in secs:
            f = CONTACTS / f"{sample}.contact_stats_q30.npz"
            if not f.exists():
                sys.exit(f"{sample}: {f} missing (copy it from the archive first)")
            st = ContactStats.load(f)
            st.cells = np.asarray([f"{sample}:{b}" for b in st.cells], dtype=object)
            if merged is None:
                merged = st
            else:
                if st.chroms != merged.chroms or not np.array_equal(st.edges, merged.edges):
                    sys.exit(f"{sample}: chromosomes / edges differ from {secs[0]}")
                both = ContactStats(list(merged.cells) + list(st.cells), merged.chroms, merged.edges)
                both.distance = np.concatenate([merged.distance, st.distance])
                both.trans = np.concatenate([merged.trans, st.trans])
                both.orientation = np.concatenate([merged.orientation, st.orientation])
                both.meta = merged.meta
                merged = both
        merged.write(cd, key="contacts", per_chromosome=False, dtype=np.int32,
                     source="GSE311199 .nodups.pairs.gz, apps/atlas/recipes/spatial_hicrna/slurm/"
                            "spatial_pairs_stats.py (MAPQ >= 30, in-tissue spots, main chromosomes)")
        c = cd.cells
        have = c["section"].isin(secs).to_numpy()
        total = (c["contacts.n_cis"] + c["contacts.n_trans"]).to_numpy()[have]
        ref = c["hic_contacts"].to_numpy()[have]
        bad = int((total != ref).sum())
        if bad:
            sys.exit(f"{store}: {bad} spots whose cis + trans differ from hic_contacts — not written")
        print(f"{store}: {int(have.sum()):,} spots of {secs}; cis + trans equal hic_contacts for every spot; "
              f"{int(total.sum()):,} contacts")
        cd.write(path)
        print("wrote", path.name)


if __name__ == "__main__":
    main(sys.argv[1:] or list(STORE_OF))
