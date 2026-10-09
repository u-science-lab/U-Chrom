# spatial_variable — committed results

The numbers behind the docs page *Spatial variation across a tissue* (`docs/source/schic/spatial.md`) and the
figure data of nmeth-bc Fig. 2, as the scripts wrote them with `benchmarks/_record.py` (each file carries its
`provenance`: revision, host, job, package versions, datasets, parameters).  Data: the spatial Hi-C-RNA spots of
Guo et al. 2026 (GEO GSE311199; atlas stores `hicrna_mouse_brain`, `hicrna_human_melanoma`), per-spot contact
statistics and window counts from the samples' `.nodups.pairs.gz` (`apps/atlas/recipes/spatial_hicrna/sherlock/`).
Compare a new run with `python benchmarks/_record.py OLD NEW --rtol ...`.

| File | What | Script (stage) | Produced |
| --- | --- | --- | --- |
| `validate_stats.json` | SPARK-X vs `SPARK::sparkx` (R, xzhoulab/SPARK @a8b4bf2), Moran's I / Geary's C vs PySAL `esda` 2.10, on the spot RNA of mouse brain r1 | `validate_stats.py` | 2026-10-09, Sherlock job 47069625, revision 958f978 |
| `contact_stats_check_brain.json`, `_melanoma.json` | per-spot cis / trans contacts of the statistics vs the atlas spot maps, spot for spot | `spatial_variable.py` (check) | 2026-10-09, jobs 47089493 / 47089504, revision ba50047 |
| `global_features_brain.json`, `_melanoma.json` | Guo et al.'s short / long contrast; per feature and section the smooth spatial variance at each adjustment (destriped, depth, + 30 RNA PCs); calibration with held-out genes; copy-number covariates; per-spot boundary / loop strength (log ratios and against each spot's expected); per-structure smooth shares and their replication between sections; scA/B SPARK-X | `spatial_variable.py` | 2026-10-09, written by stage summary (jobs 47133508 brain, 47133509 melanoma, revision 23c0780, with stage calibrate); stages local in jobs 47096195 (brain) and 47093852 (melanoma), revision 75e8ceb; stages check, features, sv, cnv, compartments in jobs 47089493 (brain) and 47089504 (melanoma), revision ba50047 — no change to their code since |

The per-spot contact statistics themselves (`<sample>.contact_stats_{q30,all}.npz`, `.window_counts.npz`) are on
Oak, `$OAK/uchrom/spatial_3dgenome/<sample>/`.  They were computed by jobs 47059381-47059390 (contact statistics,
revisions 2f1f105 and 93850ca, which differ only by the added `pairs_windows.py`) and 47074062 / 47074067 / 47077387
/ 47077388 (window counts, revisions 63d5d93 and d6494bc, no change to `uchrom.io` between them).  The revision is
the `code` field in the first line of each job's log (archived with the run, below); the `.revision` files written
next to the contact statistics may name a later sync and are not authoritative.

Figure data (nmeth-bc Fig. 2) go to the paper repository, `manuscripts/nmeth-bc/figures/results/spatial_variable_<tissue>{.json,.npz,_spots.parquet,_calibration.parquet,_local.parquet}`, from the same summary jobs.
