# Calling structures from a map

A contact map shows chromatin structure at three scales: A/B **compartments** (the megabase checkerboard),
**domains** (TADs, squares on the diagonal) and **loops** (dots).  `uchrom.strc` calls all three on a map
linked to a `ChromData` — a bulk Hi-C map, or a [pseudo-bulk map](../schic/pseudobulk) of single cells —
with U-Chrom's own implementations of the standard methods (no cooltools / Mustache dependency).  Every
caller reads the map as a sparse band near the diagonal (`uchrom.fea.read_band`), never as a dense matrix,
so a 5 kb map of human chr1 (49,851 bins) runs on a laptop; the results go to `cd.results` /
`cd.intervals` with their provenance, like every other call.

```python
import uchrom as uc
import uchrom.datasets as ds
from uchrom.fea import rebin_map
from uchrom.io import read_juicer_loops

hic = ds.load("rao2014_imr90_chr21")                  # IMR90 chr21, 5 kb raw counts, linked as "bulk"
rebin_map(hic, "bulk", resolution=10_000)             # balanced (ICE) 10 kb copy, linked as "bulk_10kb"
rebin_map(hic, "bulk", resolution=100_000)            # ... and "bulk_100kb"

uc.tl.call_compartments(hic, method="eig", contacts="bulk_100kb", phasing=ds.fetch("hg19_chr21"))  # GC: E1 > 0 is A
uc.tl.compartment_strength(hic, contacts="bulk_100kb")                      # saddle (AA + BB) / (AB + BA)
uc.tl.call_tads(hic, method="insulation", contacts="bulk_10kb")             # insulation-score boundaries
uc.tl.call_loops(hic, method="hiccups", contacts="bulk_10kb")               # or ["bulk_5kb", "bulk_10kb"]: merged
uc.tl.call_loops(hic, method="mustache", contacts="bulk_10kb")
known = read_juicer_loops(published_list, chrom="21")                       # e.g. the Rao 2014 HiCCUPS list
uc.tl.pileup(hic, known, contacts="bulk_10kb", shifts=(-500_000, 500_000))  # APA, and of the loops shifted
```

The callers need a **balanced** map (a cooler `weight` column): `rebin_map` sums a linked map into coarser
bins and balances it (`cooler balance` defaults).

| Structure | Method | API | Stored as | Resolution |
|-----------|--------|-----|-----------|------------|
| A/B compartments | cis eigenvector of observed / expected, oriented by a phasing track (GC content, gene density, an active mark); Lieberman-Aiden et al. 2009, cooltools `eigs_cis` | `uc.tl.call_compartments(cd, method="eig", contacts=)`, `uchrom.strc.comp.call_compartments_eig` | `compartments.eig` (+ `.eigvals`; A / B runs in `cd.intervals`) | 100 kb – 1 Mb |
| compartment strength | saddle plot, `(AA + BB) / (AB + BA)`; Nora et al. 2017, Flyamer et al. 2017 | `uc.tl.compartment_strength`, `uchrom.strc.comp.compartment_strength` | `compartment_strength.saddle` | as the compartments |
| domains | diamond insulation score, minima above Li's threshold; Crane et al. 2015, cooltools `insulation` | `uc.tl.call_tads(cd, method="insulation", contacts=)`, `call_tads_insulation`, `insulation_score` | `tads.insulation` (+ `.boundaries`, `.score`) | 10 – 25 kb |
| domains | directionality index; Dixon et al. 2012 | `uc.tl.call_tads(cd, method="di", contacts=)` | `tads.di` | 25 – 50 kb |
| loops | HiCCUPS: local enrichment against four backgrounds, FDR per λ-chunk; Rao et al. 2014, cooltools `dots` | `uc.tl.call_loops(cd, method="hiccups", contacts=)`, `call_loops_hiccups` | `loops.hiccups` | 5 – 25 kb, several merged |
| loops | Mustache: blobs in a Gaussian scale space; Roayaei Ardakany et al. 2020 | `uc.tl.call_loops(cd, method="mustache", contacts=)`, `call_loops_mustache` | `loops.mustache` | 5 – 10 kb |
| known loops / boundaries | pileup (aggregate peak analysis, APA), with the same features shifted as a control (`shifts=`); Rao et al. 2014 | `uc.tl.pileup(cd, features, contacts=)`, `uchrom.fea.pileup` | `pileup` | 5 – 25 kb |
| against a reference | loops with both anchors within a tolerance; boundaries within a number of loci (`contacts=`: the bins of a linked map), with the chance level; published Juicer lists read as tables | `uchrom.strc.loop.match_loops`, `uchrom.strc.tad.compare_boundaries`, `uchrom.io.read_juicer_loops` / `read_juicer_domains` | — | — |
| a shallower map | binomial thinning of the raw counts, written, balanced and linked | `uchrom.fea.thin_map(cd, contacts, fraction=)` | — | any |

## Which method, and when

- **Calling needs depth.**  Loops are the first to go: on the IMR90 chr21 map thinned (`thin_map`) to a
  fifth of its 10.3 M contacts HiCCUPS finds a third of the published loops, at 5 % one, at 2 % none.  The
  pileup of the same loops stays at APA 3.8–4.7 down to 2 % (the loops shifted by ±0.5–1 Mb: at or below 1).  On a shallow map — a cell-type pseudo-bulk, a few
  deep single cells — **score known loops by pileup instead of calling them**, or, with ~100 cells or more
  of a type, **call them across the cells without pooling** (SnapHiC: 0.60 of the published mES loops from
  742 cells, where HiCCUPS on their pooled map finds 0.06; [calling structures from single
  cells](../schic/structures.md)).  Domains and compartments need fewer contacts (88 % of the insulation
  boundaries are still found at 2 %).
- **Compare strengths at matched depth.**  The saddle strength of a shallow map is inflated (+16 % at 2 %
  of this map), so groups with different numbers of contacts are compared on random subsets of equal depth
  (`uc.tl.pseudobulk(cd, groupby=<Series>)`; the [pseudo-bulk tutorial](../tutorials/pseudobulk)).
- **HiCCUPS or Mustache.**  HiCCUPS is the conservative caller (most of its calls are in the published
  list), Mustache the sensitive one (more calls, nearly all published loops at 5 kb, half of its calls
  unconfirmed).  HiCCUPS on several resolutions merges them as Juicer does.
- **Phasing.**  An eigenvector's sign is arbitrary: give `phasing=` a FASTA (GC content), a `cd.bin_tracks`
  column or a table; to compare several maps, orient them all by one reference (e.g. the E1 of all cells) with
  `EigCompartmentParams(sort_by_phasing=True)`.
- **Speed.**  Everything runs on a laptop: a 5 kb map of chr1 (50,000 bins) takes seconds per caller.  With
  the native kernels installed (`pip install ./packages/uchrom-maps`, the extra `u-chrom[maps]`; Rust,
  multi-core) HiCCUPS and Mustache run 3–6× faster on such a map, with the same calls; without them the
  numpy code runs.

## Validation, in brief

On the same balanced maps the implementations reproduce the reference tools (`benchmarks/hic_structures/`):
compartments = cooltools `eigs_cis` / `saddle` to 1e-14; insulation boundaries identical to cooltools
`insulation` in 20 of 20 map × window cases; HiCCUPS' enriched pixels identical to cooltools `dots` on 6 maps;
Mustache calls within 2 bins of mustache-hic for 89–96 %.  Against the published Rao 2014 calls on IMR90
chr21 (92 HiCCUPS loops, 86 Arrowhead domains):

| Caller | Map | Recall | Precision |
|--------|-----|--------|-----------|
| HiCCUPS | 10 kb (5 + 10 kb merged) | 0.76 (0.79) | 0.74 (0.74) |
| Mustache | 5 kb / 10 kb | 0.95 / 0.72 | 0.41 / 0.42 |
| insulation (boundaries vs Arrowhead edges, ±2 bins) | 10 kb / 25 kb | 0.66 / 0.67 | 0.84 / 0.94 (chance 0.13 / 0.28) |

The compartments of the same map agree with chromatin tracing of IMR90 chr21 (Su et al. 2020) on 94 % of
the imaged loci.  The full tables, the depth series and run times (IMR90 chr1 at 5 kb: insulation 1.5 s,
compartments 8 s, HiCCUPS 6–16 s, Mustache 16–19 s) are in `benchmarks/hic_structures/README.md`.

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/hic_structures
```

API: [compartments](../reference/api/strc_comp), [TADs](../reference/api/strc_tad),
[loops](../reference/api/strc_loop), [maps, pileups, pseudo-bulk](../reference/api/fea).
