# u-chrom-nucdyn

Native NucDynamics engine for [U-Chrom](../../README.md): single-cell Hi-C
genome structure calculation by simulated annealing of a particle model,
written in Rust (PyO3 bindings), on a multi-core CPU (f64, rayon) or on a GPU
through wgpu (f32; Metal on macOS, Vulkan on Linux, DX12 on Windows).  Every
model of an ensemble is computed at once: models run in parallel on the CPU
and in one batched dispatch on the GPU.

Import name `uchrom_nucdyn`, pip name `u-chrom-nucdyn`; U-Chrom uses it from
`uchrom.recon.sc.nucdyn` when it is installed (`pip install u-chrom[nucdyn]`
or `pip install ./native/nucdyn`).

## Attribution

This is a clean re-implementation of the algorithm of **NucDynamics**:

> Stevens, T. J., Lando, D., Basu, S., Atkinson, L. P., Cao, Y., Lee, S. F.,
> Leeb, M., Wohlfahrt, K. J., Boucher, W., O'Shaughnessy-Kirwan, A., Cramard,
> J., Faure, A. J., Ralser, M., Blanco, E., Morey, L., Sansó, M., Palayret,
> M. G. S., Lehner, B., Di Croce, L., Wutz, A., Hendrich, B., Klenerman, D. &
> Laue, E. D. (2017). 3D structures of individual mammalian genomes studied
> by single-cell Hi-C. *Nature* 544, 59–64. doi:10.1038/nature21429

Original implementation: <https://github.com/tjs23/nuc_dynamics> (Tim J.
Stevens, Python + Cython), licensed under the GNU Lesser General Public
License v3.0.  The reference for this port is its master branch (commit
`00eaf0b`, 2022; the physics and protocol are unchanged since the 2017
"parallel model computation" rewrite apart from the items listed below).  No
code was copied; the behaviour of each original function was re-implemented
from the algorithm, and the Rust functions keep the original names so the
two can be compared side by side.  This crate is distributed under the
LGPL-3.0-or-later as well.

Please cite Stevens et al. 2017 when you use structures computed with this
engine.
