# License

U-Chrom is released under the MIT license — the packages `chromdata`, `u-chrom`, `uchrom-browser`,
`uchrom-discovery` and `uchrom-maps`.  See
[`LICENSE`](https://github.com/u-science-lab/U-Chrom/blob/main/LICENSE) in
the repo for the full text.

## Third-party code

- The Hi-C map callers (`uchrom.strc.comp.call_compartments_eig`, `uchrom.strc.tad.call_tads_insulation`,
  `uchrom.strc.loop.call_loops_hiccups` / `call_loops_mustache`, `uchrom.fea.pileup`) and their native
  kernels (`packages/uchrom-maps`) are independent implementations of the published methods (Crane
  *et al.* 2015; Rao *et al.* 2014; Roayaei Ardakany *et al.* 2020; Open2C 2024), checked against cooltools
  and mustache-hic (both MIT), which U-Chrom neither includes nor imports.

- `uchrom.strc.loop`, `uchrom.fea.arc`, `uchrom.utils.stats`
  implement algorithms described in Yu *et al.* 2025 (*ArcFISH*,
  bioRxiv 2025.11.26.690837).  The implementation is independent of
  the upstream ArcFISH source (GPL-3.0).
- The native NucDynamics engine (`packages/uchrom-recon`, package
  `uchrom-recon`, used by `uchrom.recon.sc.nucdyn`) is a clean Rust
  re-implementation of NucDynamics (Stevens *et al.* 2017, *Nature*
  544:59; tjs23/nuc_dynamics, LGPL-3.0) and is itself distributed under
  the LGPL-3.0-or-later as a separate package; `uchrom` only imports it.
