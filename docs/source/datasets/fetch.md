# Fetching files

`ds.fetch(name)` puts files on your disk — once: a second call returns the path without downloading.  It
returns the file (or the folder of a dataset with several files) in the data directory.

## An atlas store, for offline work

```python
import uchrom.datasets as ds

path = ds.fetch("stevens2017_mesc")       # <data directory>/atlas/stevens2017_mesc.cdz (26 MB)
cd = ds.load("stevens2017_mesc")          # now reads the local copy
```

The `.cdz` is the store in one uncompressed zip: everything the remote store holds, contact maps and RNA
included, read the same way (backed).  Its size is `ds.list_atlas()["download_mb"]` — from 26 MB to several
GB; the download is checked against it.  Delete the file to go back to the remote store.

## Original files

The registry (`ds.list_datasets()`: name, size, whether a loader exists, description) names every file
U-Chrom uses, where it comes from and its md5 sum:

```python
ds.list_datasets().query("size_mb < 100")
path = ds.fetch("takei")                  # Takei 2021 FOF-CT core table (4DN), md5-checked
fasta = ds.fetch("hg19_chr21")            # a reference sequence (UCSC), e.g. GC phasing of compartments
ds.path("takei")                          # where it is (or will be), without downloading
```

Use them to read a raw format yourself (the [import tutorials](../tracing/reading) do), as reference files
(genome sequences, gene annotations, published loop lists), or as the inputs of the benchmarks.  A few entries
are built rather than downloaded whole: slices of large Hi-C files read over HTTP range requests
(`rao2014_imr90_chr21`, `rao2014_imr90_chr1`, ...), the head of a large archive (`takei2025_fov0`).

## From the command line

```bash
python -m uchrom.datasets list                      # the registry
python -m uchrom.datasets atlas                     # the atlas (with what is downloaded)
python -m uchrom.datasets fetch takei hg19_chr21    # original files
python -m uchrom.datasets fetch stevens2017_mesc    # an atlas store (.cdz)
python -m uchrom.datasets fetch --default           # every file the tutorials use (~0.9 GB)
python -m uchrom.datasets path takei
```

`--root DIR` (or `UCHROM_DATA`) puts the files elsewhere, e.g. on a cluster's scratch space.

## Adding a dataset

A new dataset is registered in `packages/uchrom/uchrom/datasets/_sources.py` (files, URLs, md5 sums,
size, description; a loader in `_load_*.py` when it should come as a `ChromData`) and documented in
`apps/atlas/recipes/README.md` ([data sources](../reference/data_sources)) in the same change — no silent
downloads.
