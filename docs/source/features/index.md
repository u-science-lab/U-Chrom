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
| annotation (GTF) and sequence (FASTA) features | `add_annotation_features`, `add_sequence_features` |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/features
```

API: [uchrom.fea](../reference/api/fea).
