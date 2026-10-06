# License

U-Chrom is released under the MIT license.  See
[`LICENSE`](https://github.com/Nanguage/U-Chrom/blob/main/LICENSE) in
the repo for the full text.

## Third-party code

- `uchrom.strc.loop`, `uchrom.fea.arc`, `uchrom.utils.stats`
  implement algorithms described in Yu *et al.* 2025 (*ArcFISH*,
  bioRxiv 2025.11.26.690837).  The implementation is independent of
  the upstream ArcFISH source (GPL-3.0).
- The native NucDynamics engine (`packages/uchrom-recon`, package
  `uchrom-recon`, used by `uchrom.recon.sc.nucdyn`) is a clean Rust
  re-implementation of NucDynamics (Stevens *et al.* 2017, *Nature*
  544:59; tjs23/nuc_dynamics, LGPL-3.0) and is itself distributed under
  the LGPL-3.0-or-later as a separate package; `uchrom` only imports it.
- The deprecated Taichi code in `uchrom.recon.sc.nucdyn.nucdyn` and
  `uchrom.recon.sc.gem` are Taichi reimplementations of the Nuc
  Dynamics and GEM algorithms published by the original authors.
