# Per-locus features

`uchrom.fea` computes what describes a locus across many cells: distance maps and contact
frequencies, the variance of positions along each axis (what the callers test), signals summed over
intervals, peaks of a signal, annotation and sequence content — and projects interval features onto
the locus axis (`bin_tracks`) so that they sit next to imaging or sequencing signals.  Every feature
is recorded in `cd.uns["feature_registry"]`.

| Feature | API |
|---------|-----|
| distance maps (exact, streaming), mean distances, contact frequency, radius of gyration | `distance_map`, `DistanceMap`, `mean_distance_matrix`, `contact_frequency`, `radius_of_gyration` |
| axis-wise variance (the callers' statistic) | `axis_variance_cube`, `axis_weight`, `filter_normalize` |
| signals over intervals; intervals onto bins | `aggregate_tracks_by_interval`, `project_interval_features_to_bins` |
| peaks of a signal (MACS-style) | `call_peaks_from_track`, `call_macs_bdgpeaks_from_signal`, `add_peak_features` |
| annotation (GTF) and sequence (FASTA) features, CpG frequency | `add_annotation_features`, `add_sequence_features` (`features=["cpg_frequency"]`) |
| contact maps linked to the data: matrices, coarser bins, banded reads of large maps, the cis expected, thinning | `contact_matrix`, `rebin_map`, `read_band`, `expected_cis`, `thin_map` ([bulk Hi-C](../bulk/structures.md)) |
| maps of cell groups, cells drawn at matched depth, pileups of known features | `pseudobulk`, `sample_cells_by_depth`, `pileup` ([pseudo-bulk maps](../schic/pseudobulk.md)) |
| single-cell maps imputed by a random walk with restart (scHiCluster / SnapHiC; native kernels in `uchrom-maps`) | `impute_maps`, `rwr_band`, `zscore_band`, `ImputeParams` ([single cells](../schic/structures.md)) |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/features
```

API: [uchrom.fea](../reference/api/fea).
