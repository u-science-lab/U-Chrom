"""EMber: noise-aware single-cell Hi-C 3-D genome reconstruction.

EMber (EM + annealing / sampling) is the native engine's protocol ``"robust"``
(``uchrom_recon``; ``packages/uchrom-recon/src/robust.rs``): the NucDynamics 2017
hierarchical annealing with a mixture observation model — every contact is a
true proximity or a false contact (rate ε), contact restraints are re-weighted
by their posterior probability of being true (EM; ε and the contact-kernel
width learned from the data, plus structure-free local-support evidence) — a
short schedule (2,500 MD steps per stage), a sampling stage at finite
temperature (calibrated ensembles) and adaptive resolution below 25 kb.

It was pre-registered, developed on a development set, frozen (tag
``robust-frozen``) and tested once against NucDynamics
(an unpublished design note, ``TEST_RESULTS.md``).  The defaults below are
the frozen method.

    from uchrom.recon.sc import reconstruct_ember
    cd = reconstruct_ember("cell1.pairs", n_models=10, device="auto")
    cd.layers["model_0"]                        # one model per layer
    cd.results["ember.contact_weights"]         # posterior weight of every input contact

Phased (homolog-resolved) contacts — hickit ``.pairs`` with ``phase0`` / ``phase1``, Dip-C
``.con`` — give a diploid reconstruction: one particle chain per chromosome copy, the copy pair
of every contact with an unphased end inferred by EM from the structure (the copy pair is a
latent variable of the same mixture model)::

    cd = reconstruct_ember("cell.contacts.pairs.gz", ploidy="auto")   # traces chr1(pat), chr1(mat), ...
    cd.results["ember.imputed_phase"]           # most probable (hap_a, hap_b) of every contact

The diploid extension is new (not part of the frozen, pre-registered test); its haploid
behaviour is unchanged.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence, Union

import pandas as pd

from .nucdyn.native import DEFAULT_PARTICLE_SIZES, reconstruct_nucdyn

__all__ = ["reconstruct_ember", "EMBER_PROTOCOL"]

#: engine protocol implementing EMber
EMBER_PROTOCOL = "robust"


def reconstruct_ember(
    contacts: Union[str, os.PathLike, pd.DataFrame],
    *,
    chrom: Union[None, str, Sequence[str]] = None,
    n_models: int = 10,
    params: Optional[Mapping[str, Any]] = None,
    device: str = "auto",
    n_threads: int = 0,
    seed: int = 0,
    particle_sizes: Sequence[float] = DEFAULT_PARTICLE_SIZES,
    cell_id: Optional[str] = None,
    key_added: Optional[str] = "ember",
    copy: bool = False,
    verbose: bool = False,
    ploidy: Any = None,
    hap_names: Sequence[str] = ("pat", "mat"),
    phase_prior: bool = False,
    **engine_params: Any,
):
    """Single-cell Hi-C genome structure ensemble with EMber.

    Parameters
    ----------
    contacts
        Path (``.ncc``, ``.pairs[.gz]``, GEO ``chr_A pos_A chr_B pos_B`` table)
        or DataFrame of contacts (see :func:`uchrom.recon.sc.nucdyn.load_contacts`).
    chrom
        ``None`` (default): the whole genome.  A chromosome name / range
        (``"chr19"``, ``"chr1:1000000-5000000"``) or a list of them restricts
        the contacts to those regions (calling convention: ``chrom=None`` runs
        everything).
    n_models
        Models (structures) in the ensemble.
    params
        Engine parameters overriding the frozen defaults (see
        ``uchrom_recon.default_params()``; the ``robust_*`` fields are EMber's);
        keyword arguments are merged into it.
    device
        ``"auto"`` (GPU when available), ``"cpu"`` (f64, multi-core) or
        ``"gpu"`` (f32, wgpu).
    n_threads, seed, particle_sizes, cell_id, verbose
        As :func:`uchrom.recon.sc.nucdyn.reconstruct_nucdyn`.
    key_added
        Key of ``cd.uns[key_added]`` (method, engine, protocol, parameters)
        and of the results ``<key>.stages`` / ``<key>.em`` (EM log) /
        ``<key>.contact_weights``; ``None`` stores neither.
    copy
        Reconstruction always creates a new ``ChromData`` from the contacts;
        accepted for the calling convention (no effect).
    ploidy, hap_names, phase_prior
        Phased (diploid) input, see :func:`uchrom.recon.sc.nucdyn.reconstruct_nucdyn`:
        copies per chromosome (``None`` = ``"auto"``: male when chrY is present;
        ``"haploid"`` ignores the phases), haplotype names in the trace ids, and whether
        hickit's imputed phase probabilities (when present) are used as an extra prior of the
        copy pairs (default ``False``: the frozen configuration, EMber's own neighbourhood prior
        only; an unpublished design note §6).
        Adds the results ``<key>.phase_probs`` / ``<key>.imputed_phase`` and
        ``uns[key]["diploid"]`` (phasing statistics).

    Returns
    -------
    ChromData
        One spot per particle; ``coords`` = model 0, ``layers['model_<k>']`` =
        every model; units: particle radii.  Same layout as
        :func:`uchrom.recon.sc.nucdyn.reconstruct_nucdyn` with
        ``protocol="robust"`` (identical coordinates for the same seed).
    """
    del copy
    return reconstruct_nucdyn(
        contacts, n_models=n_models, device=device, n_threads=n_threads, seed=seed, protocol=EMBER_PROTOCOL,
        particle_sizes=particle_sizes, genome_ranges=chrom, cell_id=cell_id, key_added=key_added, params=params,
        verbose=verbose, ploidy=ploidy, hap_names=hap_names, phase_prior=phase_prior, _method="ember",
        **engine_params)
