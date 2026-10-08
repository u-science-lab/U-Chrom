"""``uchrom.tl`` — flat, scanpy-style aliases for analysis *tools*.

Tools add annotations (structures, features, embeddings) to a
``ChromData``.  The implementations live in the domain modules
(``uchrom.strc``, ``uchrom.fea``, …); these aliases only dispatch on
``method=`` and forward every other keyword unchanged, so they follow the
same calling convention (``chrom=None``, ``params=``, ``key_added=``,
``copy=``)::

    import uchrom as uc
    uc.tl.call_tads(cd, method="arcfish")        # strc.tad.call_tads_by_pval
    uc.tl.call_loops(cd)                         # strc.loop.call_loops_axiswise_f
    uc.tl.call_compartments(cd)                  # strc.comp.call_compartments_axes_pc
    uc.tl.call_compartments(cd, method="eig", contacts="bulk")   # a linked Hi-C map: cis eigenvector
    uc.tl.call_tads(cd, method="insulation", contacts="bulk")    # insulation-score boundaries
    uc.tl.call_loops(cd, method="hiccups", contacts="bulk")      # local-enrichment loops (HiCCUPS)
    uc.tl.call_loops(cd, method="mustache", contacts="bulk")     # scale-space loops
    uc.tl.pileup(cd, "loops.hiccups", contacts="bulk")           # APA of known loops (too shallow to call)
    uc.tl.pseudobulk(cd, "cell_type")            # fea.pseudobulk: per-cell maps summed per group, linked
    uc.tl.single_cell_compartments(cd, track=fasta)  # scA/B per cell (Tan 2021), from the per-cell maps
    uc.tl.call_loops(cd, method="snaphic")       # loops across single cells (SnapHiC), imputed per cell
    uc.tl.single_cell_boundaries(cd)             # boundaries per cell + consensus, imputed per cell
    uc.tl.reconstruct_sc("cell.pairs")           # recon.sc.reconstruct_ember (EMber)
    uc.tl.reconstruct_bulk(cd, contacts="bulk")  # recon.bulk.mds.reconstruct_mds (a linked bulk map)
    uc.tl.embed_cells(cd, source="rna")          # emb.embed_cells
    uc.tl.embed_higashi(cd)                      # emb.embed_higashi (FastHigashi on linked contact maps)
    uc.tl.embed_contacts(cd)                     # emb.embed_contacts (scHiCluster on linked contact maps)
    uc.tl.cluster_cells(cd, use="rna_pca")       # emb.cluster_cells
"""

from __future__ import annotations

from typing import Callable, Dict


def _tad_methods() -> Dict[str, Callable]:
    from uchrom.strc.tad import call_domains_fishnet, call_tads_by_pval, call_tads_di, call_tads_insulation

    return {
        "arcfish": call_tads_by_pval,
        "pval": call_tads_by_pval,
        "fishnet": call_domains_fishnet,
        "di": call_tads_di,
        "insulation": call_tads_insulation,
    }


def _dispatch(kind: str, methods: Dict[str, Callable], method: str):
    try:
        return methods[method]
    except KeyError:
        raise ValueError(f"unknown {kind} method {method!r}; choose from {sorted(methods)}") from None


def call_tads(cd, *, method: str = "arcfish", **kwargs):
    """Call TADs / domains.

    ``method``: ``"arcfish"`` (alias ``"pval"``) →
    :func:`uchrom.strc.tad.call_tads_by_pval`; ``"fishnet"`` →
    :func:`uchrom.strc.tad.call_domains_fishnet`; on linked Hi-C maps ``"insulation"`` →
    :func:`uchrom.strc.tad.call_tads_insulation` and ``"di"`` → :func:`uchrom.strc.tad.call_tads_di`.
    """
    return _dispatch("TAD", _tad_methods(), method)(cd, **kwargs)


def _loop_methods() -> Dict[str, Callable]:
    from uchrom.strc.loop import call_loops_axiswise_f, call_loops_hiccups, call_loops_mustache, call_loops_snaphic

    return {"axiswise_f": call_loops_axiswise_f, "hiccups": call_loops_hiccups, "mustache": call_loops_mustache,
            "snaphic": call_loops_snaphic}


def call_loops(cd, *, method: str = "axiswise_f", **kwargs):
    """Call loops.  ``method``: ``"axiswise_f"`` (3-D distances) →
    :func:`uchrom.strc.loop.call_loops_axiswise_f`; on a linked Hi-C map ``"hiccups"`` (local enrichment) →
    :func:`uchrom.strc.loop.call_loops_hiccups` and ``"mustache"`` (scale space) →
    :func:`uchrom.strc.loop.call_loops_mustache`; from linked per-cell maps, across cells ``"snaphic"`` →
    :func:`uchrom.strc.loop.call_loops_snaphic`."""
    return _dispatch("loop", _loop_methods(), method)(cd, **kwargs)


def call_compartments(cd, *, method: str = "axes_pc", **kwargs):
    """Call A/B compartments.  ``method``: ``"axes_pc"`` (3-D distances) →
    :func:`uchrom.strc.comp.call_compartments_axes_pc`; on a linked Hi-C map ``"eig"`` (the cis
    eigenvector) → :func:`uchrom.strc.comp.call_compartments_eig` and ``"hic_pc1"`` (PC1 of the O/E
    correlation on uneven loci) → :func:`uchrom.strc.comp.call_compartments_hic`."""
    from uchrom.strc.comp import call_compartments_axes_pc, call_compartments_eig, call_compartments_hic

    return _dispatch("compartment", {"axes_pc": call_compartments_axes_pc, "eig": call_compartments_eig,
                                     "hic_pc1": call_compartments_hic}, method)(cd, **kwargs)


def single_cell_boundaries(cd, **kwargs):
    """Domain boundaries of single cells (insulation of each cell's imputed map) and their consensus ->
    :func:`uchrom.strc.tad.single_cell_boundaries`."""
    from uchrom.strc.tad import single_cell_boundaries as _f

    return _f(cd, **kwargs)


def single_cell_compartments(cd, **kwargs):
    """Per-cell compartment values (scA/B: the mean CpG of each bin's contact partners) from the linked per-cell
    maps -> :func:`uchrom.strc.comp.single_cell_compartments`."""
    from uchrom.strc.comp import single_cell_compartments as _f

    return _f(cd, **kwargs)


def compartment_strength(cd, **kwargs):
    """Compartment strength from a saddle plot of a linked Hi-C map -> :func:`uchrom.strc.comp.compartment_strength`."""
    from uchrom.strc.comp import compartment_strength as _f

    return _f(cd, **kwargs)


def pseudobulk(cd, groupby=None, **kwargs):
    """Sum the linked per-cell contact maps per cell group into linked pseudo-bulk maps ->
    :func:`uchrom.fea.pseudobulk`."""
    from uchrom.fea import pseudobulk as _f

    return _f(cd, groupby, **kwargs)


def pileup(cd, features, **kwargs):
    """Aggregate a linked Hi-C map around known loops / boundaries (APA) -> :func:`uchrom.fea.pileup`."""
    from uchrom.fea import pileup as _f

    return _f(cd, features, **kwargs)


def reconstruct_sc(contacts, *, method: str = "ember", **kwargs):
    """Single-cell Hi-C 3-D reconstruction -> new ``ChromData``.  ``method``:
    ``"ember"`` -> :func:`uchrom.recon.sc.reconstruct_ember`; ``"nucdyn"`` ->
    :func:`uchrom.recon.sc.reconstruct_nucdyn`."""
    from uchrom.recon.sc import reconstruct_ember, reconstruct_nucdyn

    return _dispatch("single-cell reconstruction", {"ember": reconstruct_ember, "nucdyn": reconstruct_nucdyn}, method)(
        contacts, **kwargs)


def reconstruct_bulk(cd, *, method: str = "mds", **kwargs):
    """3-D structure of a bulk Hi-C map linked to ``cd`` (``contacts=<key>``) -> new ``ChromData``.
    ``method``: ``"mds"`` -> :func:`uchrom.recon.bulk.mds.reconstruct_mds`; ``"gem_fish"`` (with
    ``fish=<tracing ChromData>``, ``chrom=``) -> :func:`uchrom.recon.fish.reconstruct_gem_fish`.  A population of
    structures (IGM): :func:`uchrom.recon.bulk.deconv.deconvolve`."""
    from uchrom.recon.bulk.mds import reconstruct_mds
    from uchrom.recon.fish import reconstruct_gem_fish

    return _dispatch("bulk reconstruction", {"mds": reconstruct_mds, "gem_fish": reconstruct_gem_fish}, method)(
        cd, **kwargs)


def embed_cells(cd, **kwargs):
    """Embed cells from a per-cell matrix (RNA, IF, ATAC, ...) -> :func:`uchrom.emb.embed_cells`."""
    from uchrom.emb import embed_cells as _f

    return _f(cd, **kwargs)


def embed_higashi(cd, **kwargs):
    """Embed cells by their linked single-cell Hi-C maps with FastHigashi -> :func:`uchrom.emb.embed_higashi`."""
    from uchrom.emb import embed_higashi as _f

    return _f(cd, **kwargs)


def embed_contacts(cd, **kwargs):
    """Embed cells by their linked single-cell Hi-C maps (scHiCluster) -> :func:`uchrom.emb.embed_contacts`."""
    from uchrom.emb import embed_contacts as _f

    return _f(cd, **kwargs)


def cluster_cells(cd, **kwargs):
    """Leiden clusters of an embedding -> :func:`uchrom.emb.cluster_cells`."""
    from uchrom.emb import cluster_cells as _f

    return _f(cd, **kwargs)


__all__ = ["call_compartments", "single_cell_compartments", "single_cell_boundaries", "compartment_strength", "call_loops", "call_tads", "pileup", "pseudobulk", "reconstruct_sc", "reconstruct_bulk", "embed_cells", "embed_higashi",
           "embed_contacts", "cluster_cells"]
