# From detections to traces

`uchrom.im.trace.align_spots` links decoded DNA FISH detections into chromatin fibres (traces) — a
re-implementation of the *jie* method (Jia et al.) for data where each locus of a cell may have several
candidate spots and the number of fibres per chromosome is not known in advance.

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/jie_aligner
```

```python
import uchrom.datasets as ds
from uchrom.im.trace import align_spots, score_alignment

detections = ds.load("takei2021_mesc_detections")      # raw DNA seqFISH+ detections, not yet traced
traced = align_spots(detections, chrom="chr19")         # also: uc.pp.align_spots; a spot table works too
score_alignment(traced, detections, label="label")      # against the authors' homolog call: purity, ARI
```

## When to use `uchrom.im.trace.align_spots`

Use it when your input is **raw, decoded FISH detections** with
multiple candidate spots per genomic locus per cell.  If you instead
already have a 4DN FOF-CT file (every spot carries a `trace_id`), you
can skip tracing entirely and go straight to
`ChromData.from_fofct` ([reading tracing data](reading)).

## The jie algorithm in one paragraph

For every (cell, chromosome), the aligner builds a directed acyclic
graph over the candidate spots ordered by genomic position.  Edge
weight is the Mahalanobis cost `R²_ij / (2·S²_ij)` of the observed 3-D
distance under a Gaussian-chain bond whose expected axis variance is
`S²_ij = σ_i² + σ_j² + (2/3)·l_p·τ·L_ij`.  A shortest path
(Dijkstra) picks the most polymer-plausible one-spot-per-locus fiber;
iterating with already-used spots masked recovers all fibers
(*ploidy-agnostic karyotyping*).  Post-hoc pairing detects sister
chromatids by mean co-locus distance.

```python
from uchrom.im.trace import align_spots, SpotAlignerParams

cd = align_spots(
    spots_df,
    params=SpotAlignerParams(
        persistence_length_bp=150.0,
        max_skip=3,
        gap_penalty=3.0,
        min_spots_per_fiber=30,
        max_fibers_per_chrom=4,
        detect_sisters=True,
        sister_pair_radius_nm=400.0,
    ),
    tau_by_chrom={"chr19": 0.012},   # nm/bp; ~0.01-0.02 is typical
)
```

Output is a normal `ChromData`:
- `cd.spots` — kept detections with `trace_id` populated
- `cd.traces` — one row per fiber with `mean_edge` and `sister_group`
- `cd.results["ploidy"]` — per `(cell, chrom)` fiber count
- `cd.uns["jie_polymer"]` — the τ fit used per chromosome

## Known limitations

- **Structural variants** (inversions, translocations) break the DAG
  monotonicity assumption.  Mask or exclude known-SV regions.
- **Tight sister chromatids** (< ~150 nm) often merge into one called
  fiber.
- **τ auto-fit** is sensitive to decoy contamination; pass
  `tau_by_chrom={chrom: value}` explicitly for noisy data.
- **GPL-3 upstream**: the reference implementation at github.com/b2jia/jie is GPL-3.0.  This port is
  independent, rewritten from the paper's method section.

The tutorial [spot-to-trace alignment](../tutorials/jie_aligner) runs it on the raw DNA seqFISH+
detections of Takei et al. 2021 (Zenodo 3735329) and scores it against their published traces
(4DN `4DNFIHF3JCBY`).
