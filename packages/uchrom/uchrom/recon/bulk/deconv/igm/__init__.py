"""IGM population modelling (A/M deconvolution of bulk Hi-C) on the native engine.

A population of S diploid structures is fitted jointly to a haploid
contact-probability matrix by alternating the A-step (activation distances
from the population decide which structure carries which contact restraint)
and the M-step (every structure annealed and minimised independently under
its restraints) over a decreasing probability threshold σ — the algorithm of
IGM (Boninsegna et al. 2022, *Nat Methods* 19:938,
doi:10.1038/s41592-022-01527-x; its predecessor PGS: Tjong et al. 2016
*PNAS* 113:E1663, Hua et al. 2018 *Nat Protoc* 13:915).

The computation runs in the native engine (``uchrom_recon``, protocol
``igm``, Rust; multi-core CPU f64 or wgpu GPU f32), a clean
re-implementation from an unpublished design note (the original
GPL-licensed IGM / alabtools / lammpgen code was not copied); where it
deviates from the original is listed in ``packages/uchrom-recon/README.md``.
Please cite the papers above when using it.
"""

from ._contacts import contact_probabilities, population_array
from ._params import IgmParams
from ._run import CITATIONS, deconvolve_igm, native_available

__all__ = ["IgmParams", "deconvolve_igm", "native_available", "contact_probabilities", "population_array", "CITATIONS"]
