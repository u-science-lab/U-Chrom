# Hi-C with imaging: GEM-FISH

GEM-FISH (Abbas et al. 2019, *Nat Commun* 10:2049) builds one model of a chromosome from its Hi-C map and
the distances measured by chromatin tracing in the same cell type: first the TADs as beads, placed by
Hi-C contacts and the FISH distances between TAD centres, then each TAD at bin resolution with its FISH
radius of gyration.  U-Chrom's re-implementation runs on PyTorch.

```python
import uchrom.datasets as ds
from uchrom.fea import rebin_map, compare_distances
from uchrom.recon.fish import reconstruct_gem_fish

hic = ds.load("rao2014_imr90_chr21")                         # Rao 2014 IMR90 Hi-C, hg19
fish = ds.load("bintu_imr90_hg19")                           # Bintu 2018 IMR90 tracing, hg19
rebin_map(hic, "bulk", resolution=30_000, anchor=fish.bins["start"].min())   # on the 30 kb segments
model = reconstruct_gem_fish(hic, contacts="bulk_30kb", chrom="chr21", fish=fish)
compare_distances(model, fish).scores                        # correlation with the imaged distances
```

Without `fish` the FISH terms are dropped and the result is a Hi-C-only model — the comparison the
[tutorial](../tutorials/gem_fish_reconstruction) makes.  Hi-C and imaging must come from the same cell
type (and the same genome assembly).

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/gem_fish_reconstruction
```

API: [GEM-FISH](../reference/api/recon_fish).
