# Bulk Hi-C: methods

## MDS: one consensus structure

Input: `.hic` / `.mcool` / `.cool`.
Output: `.chromdata.zarr` (or per-chromosome for inter mode).

```bash
# Single chromosome
python -m uchrom.recon.bulk.mds data.mcool out.chromdata.zarr \
    --resolution=100000 --chrom=chr1 --device=auto

# Whole genome with inter-chromosomal contacts
python -m uchrom.recon.bulk.mds data.mcool ./outdir/ \
    --resolution=100000 --resolution-inter=1000000 \
    --inter=True --device=auto
```

The solver is **SMACOF** with CMDS initialisation, implemented in
PyTorch so it runs on CUDA / MPS / CPU.  Inter-chromosomal mode runs a
low-resolution whole-genome scaffold MDS then Procrustes-aligns each
chromosome's high-resolution structure to its scaffold position.

Additional flags:

| Flag | Default | Meaning |
|------|---------|---------|
| `--alpha` | 4.0 | Contact → distance exponent |
| `--weight` | 0.05 | Distance-decay prior weight |
| `--n_iter` | 1000 | SMACOF iterations |
| `--partitioned` | False | Split by TAD for better parallelism |
| `--tad_bed` | None | TAD regions BED when `--partitioned` |

## IGM: a population of structures

IGM (Integrative Genome Modeling; Boninsegna et al. 2022, *Nat Methods* 19:938; alberlab/igm) fits a population of structures
so that, together, they reproduce the contact probabilities of the map: each pair of loci in contact
with probability *p* is placed in contact in a fraction *p* of the structures (assignment), the
structures are relaxed under those restraints (modelling), and the two steps alternate over decreasing
probability thresholds.  U-Chrom runs the modelling on the native engine (protocol `"igm"`); the
defaults follow the IGM 1.0 protocol, with options from IGM-Plus / IGM 2.0 as fields of `IgmParams`.

```python
from uchrom.recon.bulk.deconv import deconvolve
from uchrom.recon.bulk.deconv.preprocess import preprocess_hic

prob = preprocess_hic("map.mcool", chroms=["chr21"])          # Hi-C -> contact probabilities
pop = deconvolve(prob.probabilities, bins=prob.bins, method="igm", n_structures=50, seed=1)
```

The result is one cell per structure and one trace per chromosome copy; `out="pop.chromdata.zarr"`
streams a large population to disk.  The [tutorial](../tutorials/bulk_reconstruction) checks it against
the input map and against chromatin tracing of the same cell line.

## GEM-FISH: Hi-C and chromatin tracing together

GEM-FISH (Abbas et al. 2019, *Nat Commun* 10:2049) builds one model of a chromosome from its Hi-C map and
the distances measured by chromatin tracing in the same cell type: first the TADs as beads, placed by
Hi-C contacts and the FISH distances between TAD centres, then each TAD at bin resolution with its FISH
radius of gyration.  U-Chrom's re-implementation runs on PyTorch.

```python
from uchrom.recon.fish import reconstruct_gem_fish, GEMFISHParams

model = reconstruct_gem_fish("map.mcool", "chr21", resolution=30_000, fish_cd=tracing)
```

Without `fish_cd` the FISH terms are dropped and the result is a Hi-C-only model — the comparison the
[tutorial](../tutorials/gem_fish_reconstruction) makes.  Hi-C and imaging must come from the same cell
type (and the same genome assembly).
