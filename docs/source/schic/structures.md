# Calling structures from single cells

A single cell's contact map holds 10⁴–10⁶ contacts — far too few for the callers of bulk Hi-C on that cell
alone.  Structures are still within reach, by four routes; which one works depends on the structure and on
how many cells of a kind there are:

| Route | What it calls | When | API |
|-------|---------------|------|-----|
| **pool the cells, call the map** | compartments, domains, loops, pileups | cell groups (types, clusters) with enough contacts: compartments and domains from ~2 % of bulk depth, loops near bulk depth | `uc.tl.pseudobulk` → `uc.tl.call_compartments(method="eig")`, `call_tads(method="insulation")`, `call_loops(method="hiccups")`, `uc.tl.pileup` ([pseudo-bulk maps](pseudobulk.md), [calling structures from a map](../bulk/structures.md)) |
| **across cells, without pooling** | loops (SnapHiC); domain boundaries per cell and their consensus | ≥ ~100 cells of a type at 10 kb: SnapHiC finds loops where the pooled map gives almost none | `uc.tl.call_loops(cd, method="snaphic")`, `uc.tl.single_cell_boundaries(cd)` |
| **per cell** | compartment values (scA/B) of every cell | always; they separate cell types even at 10⁴–10⁵ contacts | `uc.tl.single_cell_compartments(cd, track=<genome FASTA>)` |
| **on reconstructed 3-D structures** | the tracing callers (compartments, TADs, loops on distances) | compartments: yes; TADs and loops: not at tens of cells | `uc.tl.reconstruct_sc` / published structures → `uc.tl.call_compartments(method="axes_pc")` |

```python
import uchrom as uc
import uchrom.datasets as ds

cd = ds.load("nagano2017_dip_serum")                    # 1,175 diploid mES cells, 10 kb maps per cell (linked)
top = cd.cells.index[cd.cells["snaphic_top742"]]         # SnapHiC's selection: the 742 deepest cells
loops = uc.tl.call_loops(cd, method="snaphic", cells=top)          # loops across the cells
bounds = uc.tl.single_cell_boundaries(cd, cells=top)               # boundaries per cell + consensus
scab = uc.tl.single_cell_compartments(cd, track=ds.fetch("mm10_genome"))   # cells x bins
```

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/sc_structures
```

## Loops across cells: SnapHiC

Each cell's map is imputed by a random walk with restart on its binary contact graph (whole chromosomes; or
SnapHiC2's sliding windows, `ImputeParams(window="auto")`), turned into per-diagonal z-scores, and every
candidate pixel is tested against its local background **over the cells** (paired t-test, FDR per distance,
the five filters and the clustering of Yu et al. 2021).  The imputation, z-scores and per-cell sums run in
Rust (`uchrom-maps`); without it the numpy code runs, which cannot hold whole chromosomes in memory — use
`window="auto"` then.

Checked on the paper's data (Nagano 2017 mES cells, `benchmarks/sc_structures/snaphic_*.py`):
- **the authors' code**: on the same 100 cells and contacts U-Chrom calls exactly their 479 loops (with their
  sliding-window quirk switched on; z-scores within 1.4e-13) — in 5 s instead of 21 min;
- **742 cells, genome-wide, vs the paper's reference loops** (HiCCUPS on bulk Hi-C + MAPS): recall 0.60
  (paper 0.60), precision 0.60 (paper 0.66), 19,324 loops (paper 15,896); 73 % of the paper's loops within
  20 kb of ours.  HiCCUPS on the pooled map of the same cells: 396 loops, recall 0.06.

## Domain boundaries of single cells

The insulation score of each cell's imputed map gives that cell's boundaries; the cells' mean insulation gives
consensus boundaries.  742 mES cells vs bulk insulation: 60 % of the consensus boundaries within 2 bins of a
bulk boundary (chance 16 %), 58 % of the bulk boundaries recovered; a single cell's boundaries are rarely at
the bulk ones (frequency 0.058 vs 0.040 elsewhere) — domains vary from cell to cell.

## Compartments of single cells: scA/B

Per cell and bin, the mean CpG frequency of the bin's contact partners (Tan et al. 2021, Dip-C; ranked per
cell; `ScABParams(contacts="cis", normalize="none")` gives scHiCluster's score).  Identical to Dip-C's and
scHiCluster's own code on the same contacts; 32,777 dscHi-C cells in 70 s.  It separates cell types — Tan 2021
cortex structure types kNN 0.875 (scHiCluster embedding 0.68), dscHi-C cell types 0.91 — and follows bulk E1
(GM12878 cells vs Rao 2014: r 0.82 per cell).  **Much of it is the CpG track itself** (its mean correlates
0.84–0.89 with CpG): the cell-type-specific part is real but modest (partial r given CpG 0.3–0.67).

## The tracing callers on reconstructed structures

A reconstruction is a `ChromData` with coordinates — the tracing callers run on it unchanged (`io.read_3dg_cells`
reads Dip-C / hickit structures; `ds.load("tan2018_gm12878")` holds the authors' Dip-C structures).  On 14
GM12878 cells (28 chr21 homologs, 20 kb) against Rao 2014:

| Structure | Structures (tracing callers) | Same cells pooled (map callers) |
|-----------|------------------------------|----------------------------------|
| compartments | r 0.77 with E1, agreement 0.86 | r 0.93, agreement 0.95 |
| domain boundaries | ArcFISH at chance; FISHnet frequency peaks 0.34 (chance 0.12) | insulation: precision 0.38, recall 0.70 |
| loops | none called (axis-wise F), although published loop anchors sit at 0.69× the background distance | HiCCUPS: 4 |

Compartments are limited by the number of cells (the same as imaging at equal numbers of traces); domains and
loops by the structures — a reconstruction is smoother than an imaged trace and the tracing callers' tests
treat it as data.  For domains and loops pool the cells or call across them (above).

The numbers, datasets and Sherlock jobs are in `benchmarks/sc_structures/README.md`.
