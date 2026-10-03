# `robust` results for Fig. 3

Built by `benchmarks/screcon/robust_fig3_tables.py`; method = protocol `"robust"` frozen at tag
`robust-frozen` (PREREG.md §6, `benchmarks/screcon/TEST_RESULTS.md`).

| file | content | provenance |
|---|---|---|
| `heldout.csv` | held-out ROC / PR-AUC, columns of `../screcon/heldout.csv` + `set` | cells 1-4 (`dev`): development runs of the frozen parameter set ("c2"); cells 5-8 (`test`): frozen-build test runs; 10 models, 100 kb, seed 1, CPU f64 |
| `sim.csv` | imaging-truth simulations, columns of `../screcon/sim.csv` + `set` | truth 1-2 `dev` (c2 runs), truth 3-5 `test` (frozen build); 5 models, seed 1 |
| `score_all.json` | ED Table 2 metrics on the full Stevens 2017 tables, cells 1-8 (`rmsd_to_mean_mirror_mean`, `rmsd_pair_mirror_mean`, %V>3 / %V>4, vs published GEO models), format of `../a_nucdyn_score_all.json` | frozen build, 10 models, 100 kb, seed 1 (`sherlock/robust_fig3_score.sbatch`) |
| `speed_one_model.json` | one-model wall-time records (`speed_one_model.py` format; `robust_cpu` 1 / 16 threads, `robust_gpu`) + medians | CPU: AMD EPYC 9754, parameter set c2 on engine build e8 (same algorithm and parameter values as the frozen defaults); GPU: one H100, frozen build |
