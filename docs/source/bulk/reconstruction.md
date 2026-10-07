# Structures from a bulk map: MDS and IGM

A bulk map is an average over millions of nuclei.  MDS turns it into one consensus structure; IGM into a
population of structures whose contacts together reproduce it.  Both return a `ChromData` (IGM: one cell
per structure, one trace per chromosome copy), measured and compared with imaging like any traced data.

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/bulk_reconstruction
```

## MDS: one consensus structure

```python
import uchrom as uc
from uchrom.fea import rebin_map

rebin_map(hic, "bulk", resolution=100_000)                   # a 100 kb copy of the map, linked as "bulk_100kb"
model = uc.tl.reconstruct_bulk(hic, contacts="bulk_100kb")   # = uchrom.recon.bulk.mds.reconstruct_mds
```

The command line does the same from a file:

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
import uchrom.datasets as ds
from uchrom.recon.bulk.deconv import deconvolve
from uchrom.recon.bulk.deconv.preprocess import preprocess_hic

hic = ds.load("rao2014_imr90_chr21")                         # IMR90 chr21, 5 kb; the map linked as "bulk"
prob = preprocess_hic(hic, contacts="bulk")                  # Hi-C -> contact probabilities
pop = deconvolve(prob, method="igm", n_structures=50, seed=1)
```

The result is one cell per structure and one trace per chromosome copy; `out="pop.chromdata.zarr"`
streams a large population to disk.  The [tutorial](../tutorials/bulk_reconstruction) checks it against
the input map and against chromatin tracing of the same cell line.
