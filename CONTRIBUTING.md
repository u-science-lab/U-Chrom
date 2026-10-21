# Contributing to U-Chrom

Thank you for helping.  U-Chrom gathers the analysis of chromatin tracing, imaging multi-omics, single-cell, spatial
and bulk Hi-C on one data model, `ChromData`; a method added once runs on every dataset it applies to and shows in
the web browser.  Methods, readers for new formats, datasets, tutorials, browser views, agent skills and bug reports
are all welcome.

The full guide — the methods that exist and those that are wanted, where code goes, the calling convention, tests
and pull requests — is [Contributing](docs/source/reference/development.md) in the documentation
([online](https://u-chrom-docs.u-science.org/reference/development)).  In short:

1. **Bugs and questions**: open an [issue](https://github.com/u-science-lab/U-Chrom/issues) with a minimal example,
   ideally on a dataset of `uchrom.datasets` so that anyone can run it.
2. **A new method**: open a [method proposal](https://github.com/u-science-lab/U-Chrom/issues/new?template=method.md)
   first (the paper, its benchmark data, the authors' code and its licence); we agree on where it goes and how it
   will be checked before you write the code.
3. **The method takes a `ChromData`** and stores its result there with provenance (`cd.results`), following the
   calling convention of `packages/uchrom/uchrom/convention.py`.
4. **A re-implementation gives the authors' results** on the data of their paper; the pull request reports the
   comparison (identical calls, largest difference, run time), also when it disappoints.
5. **Real data, registered**: every dataset is registered in `uchrom.datasets` or `apps/atlas/recipes/` and
   documented in the same pull request; only small test fixtures are committed.
6. **Tests** go to the package whose code they test (`cd packages/<package> && pytest tests`): known answers on
   small inputs, the authors' output on a small real fixture, and the calling convention.
7. **Licences**: the core is MIT; implement from the paper instead of copying GPL or unlicensed code, and wrap
   external tools as optional extras.

Small fixes (typos, docs, a failing edge case) can go straight to a pull request.
