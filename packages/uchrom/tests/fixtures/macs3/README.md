# MACS3 reference results

Two files of MACS3's own regression tests (github.com/macs3-project/MACS, `test/`, the default branch at
commit ee5def7fdf, downloaded 2026-10-06; BSD 3-Clause, see LICENSE), gzipped:

- `run_bdgcmp_FE.bdg.gz` — `test/standard_results_bdgcmp/run_bdgcmp_FE.bdg` (fold-enrichment bedGraph)
- `run_bdgpeakcall_w_prefix_c2.0_l200_g30_peaks.narrowPeak.gz` —
  `test/standard_results_bdgpeakcall/run_bdgpeakcall_w_prefix_c2.0_l200_g30_peaks.narrowPeak`
  (`macs3 bdgpeakcall -c 2.0 -l 200 -g 30` on it)

`tests/fea/test_peak_features.py` checks that `uchrom.fea.peaks` (the bdgpeakcall port) writes the
same narrowPeak file byte for byte.
