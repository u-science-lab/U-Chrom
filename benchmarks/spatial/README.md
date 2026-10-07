# spatial — cell-type deconvolution of spatial Hi-C contact maps (PREREG §14)

A spatial Hi-C spot is a mixture of a few cells or partial nuclei.  Instead of splitting a spot into cells
(PREREG §12: per-contact cell identity is too weak), each spot's contact map is written as a
composition-weighted sum of **cell-type contact profiles**, the compositions coming from RNA (as RCTD /
cell2location do for expression), and the profiles are estimated jointly over all spots.  The design, the
split, the endpoints and the decision rule are pre-registered in `benchmarks/screcon/PREREG.md` §14;
development numbers go to `typedecon_devlog.md`.

The code is standalone (numpy / scipy / pandas) so it runs in the Sherlock `venv-main` without U-Chrom.

| file | what |
| --- | --- |
| `typedecon.py` | the method (`fit_td`: multinomial mixture with known compositions, EM; optional Dirichlet shrinkage, learned per-type contact yield, composition refinement; `fit_td_groups`: spatially varying profiles) and the baselines (`dominant_pool`, `nnls_profiles`, `oracle_pool`) |
| `tissue.py` | `Layout` (cis bin pairs of chr1-19), Tan 2021 cell reader (`cell_bins`, 50 kb), the registered split (`split_cells`), in-silico tissues (`build_tissue`: cortical layer pattern, 1-5 partial cells per spot, disjoint contacts), RNA-like compositions (`observed_composition`) |
| `scoring.py` | O/E features and type contrasts, distance-centred compartment scores, insulation, P(s), type identification, bootstrap |
| `run_typedecon.py` | stages `split`, `cells`, `truth`, `tissue`, `fit`, `aggregate` |
| `variants_dev.json` | the registered development variants of TD |
| `sherlock/td_*.sbatch` | the jobs (`_env.sh` holds the paths) |
| `tests/` | `pytest benchmarks/spatial/tests` (~10 s; synthetic toys check the code only) |

## Model

Spot s with N_s cis contacts on the bin pairs p: y_s ~ Multinomial(N_s, π_s), π_sp = Σ_t a_st P_tp, Σ_p P_tp = 1.
a_s = the spot's contact share per type (given composition; optionally × a learned per-type yield c_t, or
refined per spot under a Dirichlet prior centred on the given composition); P_t = the type's contact profile
(distance decay included).  EM: r_stp = a_st P_tp / π_sp; P_t ∝ Σ_s y_sp r_stp + κ_t m_t.  Equivalent to
KL-NMF with the spot factor W = N_s a_s known; each iteration is two sparse-dense products over the
non-zeros.  Cost: 1 Mb, ~10 M contacts in 150-600 spots, 6 types: ~0.2 s per iteration; 250 kb ~0.6 s
(laptop, fake contacts of the real size).

## Run (Sherlock)

```bash
rsync -a --exclude .git ./ sherlock:$SCRATCH/uchrom-nd/repo-spatial/
sbatch benchmarks/spatial/sherlock/td_prepare.sbatch                 # split, cells, truth, dev tissues
sbatch --array=1-48 benchmarks/spatial/sherlock/td_fit.sbatch        # dev: 4 reps x 2 regimes x 2 res x 3 noise
sbatch benchmarks/spatial/sherlock/td_aggregate.sbatch               # -> runs/spatial/typedecon/tables/dev/
```

The held-back tissues are built only with `SET=test APPROVED=1` after the freeze (PREREG §14.6).

## Data

Tan et al. 2021 Dip-C adult cortex cells (fetch `tan2021_cortex`; cell list
`benchmarks/screcon/data/tan2021_adult_cortex_cells.tsv`), both documented in `apps/atlas/recipes/README.md`.
Validation 2 adds Takei et al. 2021 *Science* imaging (fetch `takei2021_brain`), validation 3 the Spatial
Hi-C-RNA stores (`spatial_hicrna`), both already catalogued.
