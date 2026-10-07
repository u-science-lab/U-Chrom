"""EMber-pop: population deconvolution of bulk Hi-C without a nuclear envelope (development).

IGM's A/M population modelling on the native engine (``uchrom_recon``, protocol ``igm``) with the
EMber-pop options of ``benchmarks/bulk/PREREG_POP.md``:

* **no envelope**: no sphere / ellipsoid wall;
* **gyration-shape prior**: each structure is held, softly and in its own orientation, to the
  standard deviations σ1 ≥ σ2 ≥ σ3 of an imaged nucleus along its principal axes (one imaged cell per
  structure when the imaging is given cell by cell, so the population keeps the cells' size and shape
  variation);
* **two-sided assignment** at the last σ: bead pairs within the contact distance that carry no
  assigned contact are pushed apart, so over-represented contacts are corrected as well as missing
  ones.

The configuration is under development (``benchmarks/bulk/POP_DEVLOG.md``); it is frozen with tag
``ember-pop-frozen`` before the pre-registered test.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..igm import IgmParams, deconvolve_igm

__all__ = ["EMBER_POP_OPTIONS", "ember_pop_params", "gyration_sds", "deconvolve_ember_pop"]

#: Engine options of EMber-pop on top of IGM's (development candidate)
EMBER_POP_OPTIONS = dict(
    nucleus_shape="none",
    gyration_kspring=1.0,
    noncontact_kspring=1.0,
    advance_on_max_iterations=True,
)


def gyration_sds(nucleus: Any) -> np.ndarray:
    """Gyration standard deviations (nm) of imaged nuclei, (n_cells, 3) sorted σ1 ≥ σ2 ≥ σ3.

    ``nucleus``: a ChromData of imaged cells (all spots of a cell; coordinates in nm), an array
    (n_cells, 3) of standard deviations, or one triple."""
    if hasattr(nucleus, "coords") and hasattr(nucleus, "spots"):
        xyz = np.asarray(nucleus.coords, dtype=np.float64)
        if "cell_id" not in nucleus.spots:
            raise ValueError("the imaging ChromData needs spots['cell_id'] (one nucleus per cell)")
        cell = np.asarray(nucleus.spots["cell_id"].astype(str))
        out = []
        for c in dict.fromkeys(cell.tolist()):
            Y = xyz[cell == c]
            Y = Y[np.isfinite(Y).all(1)]
            if len(Y) > 3:
                lam = np.sort(np.linalg.eigvalsh(np.cov((Y - Y.mean(0)).T, bias=True)))[::-1]
                out.append(np.sqrt(np.maximum(lam, 1.0)))
        if not out:
            raise ValueError("no imaged cell with more than three positions")
        return np.array(out)
    a = np.atleast_2d(np.asarray(nucleus, dtype=np.float64))
    if a.shape[1] != 3 or not np.isfinite(a).all() or (a <= 0).any():
        raise ValueError("nucleus must be a ChromData or positive standard deviations of shape (3,) or (n, 3)")
    return -np.sort(-a, axis=1)


def ember_pop_params(nucleus: Any, n_structures: int, seed: int = 0, params: Optional[IgmParams] = None,
                     per_cell: bool = True) -> IgmParams:
    """IgmParams with the EMber-pop options and the imaging calibration.

    The bead volumes follow IGM (occupancy of the sphere of radius sqrt(5/3) Rg, Rg the median
    imaged radius of gyration); the gyration prior is the median shape, and with ``per_cell`` every
    structure gets the shape of one imaged cell (drawn with ``seed``)."""
    sd = gyration_sds(nucleus)
    med = np.median(sd, axis=0)
    rg = float(np.median(np.sqrt((sd ** 2).sum(1))))
    base = params if params is not None else IgmParams()
    kw = dict(EMBER_POP_OPTIONS, n_structures=int(n_structures), nucleus_radius=float(np.sqrt(5.0 / 3.0) * rg),
              gyration_prior=[float(x) for x in med],
              noncontact_from_sigma=len(base.intra_sigma_list) - 1)
    if per_cell and len(sd) > 1:
        pick = np.random.default_rng([int(seed), 0x6779]).choice(len(sd), int(n_structures), replace=len(sd) < n_structures)
        kw["gyration_targets"] = sd[pick].tolist()
    return base.replace(**kw)


def deconvolve_ember_pop(data: Any = None, *, nucleus: Any, params: Optional[IgmParams] = None,
                         n_structures: Optional[int] = None, seed: int = 0, per_cell: bool = True,
                         key_added: Optional[str] = "deconv.ember_pop", **kwargs: Any):
    """EMber-pop on a contact-probability matrix (same input / output as
    :func:`uchrom.recon.bulk.deconv.igm.deconvolve_igm`; ``uns["deconv"]["method"] = "ember_pop"``).

    ``nucleus``: the imaging calibration — a ChromData of imaged nuclei of the cell type (cells with
    their spots), per-cell gyration standard deviations (n, 3) or one triple (nm)."""
    base = params if params is not None else IgmParams()
    S = int(n_structures if n_structures is not None else base.n_structures)
    p = ember_pop_params(nucleus, S, seed=seed, params=base, per_cell=per_cell)
    return deconvolve_igm(data, params=p, seed=seed, key_added=key_added, _method="ember_pop", **kwargs)
