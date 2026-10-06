# mESC Sox2 tracing with missing loci (`mESC_Sox2_5cells_wnan.chromdata.zarr`)

Five traces of the Sox2 locus in mouse ES cells, with the loci that were not detected left as NaN — a
small real input for the imputation tests (`tests/im/test_impute.py`, `test_impute_parallel.py`; a copy is
in `packages/uchrom-browser/tests/fixtures/` for the browser's tests).

- **Source**: Huang et al. 2021, "CTCF mediates dosage- and sequence-context-dependent transcriptional
  insulation by forming local chromatin domains", *Nature Genetics* 53:1064–1074,
  [doi:10.1038/s41588-021-00863-6](https://doi.org/10.1038/s41588-021-00863-6); the coordinates as
  distributed with SnapFISH-IMPUTE (github.com/hyuyu104/SnapFISH-IMPUTE, MIT):
  `python -m uchrom.datasets fetch huang2021_sox2` (`mESC_Sox2_coor_wnan.txt`, `mESC_Sox2_ann.txt`;
  1,416 cells × 2 alleles × 41 loci at 5 kb, 29 % missing).
- **Content**: the first 5 traces of the 129 allele (`cell_id` 11, 14, 16, 26, 27): 5 × 41 = 205 spots,
  49 (24 %) with NaN coordinates; chromosome `129` (the allele), positions 34,601,078–34,806,078 (205 kb
  around Sox2 on chromosome 3; the locus table names no assembly).
- **Format**: a `.chromdata.zarr` store (format 2.3; converted from the former 1.1 `.h5cd` with
  `python -m uchrom.io.upgrade`).  `tutorials/fish_imputation.ipynb` builds the same object from the
  fetched files (identical loci, bins and coordinates).

Imputation method: Yu H., SnapFISH-IMPUTE (github.com/hyuyu104/SnapFISH-IMPUTE), vendored in
`uchrom.im.impute`.
