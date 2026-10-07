"""``reconstruct_mds``: a consensus structure from a contact map linked to a ``ChromData``."""

from __future__ import annotations

import contextlib
import io
import time
from typing import Any, Optional, Sequence, Union

import numpy as np
import pandas as pd

MODES = ("intra", "partitioned", "inter")


def reconstruct_mds(
    cd: Any,
    *,
    contacts: Optional[str] = None,
    chrom: Union[None, str, Sequence[str]] = None,
    resolution: Optional[int] = None,
    balance: bool = True,
    mode: str = "intra",
    alpha: float = 4.0,
    weight: float = 0.05,
    method: str = "smacof",
    n_iter: int = 1000,
    lr: float = 0.01,
    tol: float = 1e-6,
    device: str = "auto",
    cell_id: Optional[str] = None,
    key_added: Optional[str] = "mds",
    verbose: bool = False,
    **mode_kw: Any,
):
    """A consensus 3-D structure of a bulk Hi-C map by multidimensional scaling.

    Every chromosome is reconstructed from its balanced intra-chromosomal matrix: bins without contacts are
    dropped, the map is smoothed with a distance-decay prior (``weight``), contacts become distances
    ``d = c^(-1/alpha)`` (mean 1), and the stress is minimised by SMACOF from a classical-MDS start
    (``method="adam"``: autograd + Adam on the same stress) — :func:`run_mds`, PyTorch on the CPU, CUDA or
    Apple MPS.  ::

        hic = ds.load("rao2014_imr90_chr21")                  # the 5 kb map, linked as "bulk"
        rebin_map(hic, "bulk", resolution=100_000)             # -> "bulk_100kb" (ICE-balanced)
        mds = reconstruct_mds(hic, contacts="bulk_100kb")

    Parameters
    ----------
    cd
        A ``ChromData`` with the map linked (``cd.link_cool``), or the path of a ``.cool`` / ``.mcool``.
    contacts
        Key of the linked map (``None``: the only one).
    chrom
        Chromosome(s) (default: every chromosome of the map); each becomes one trace.
    resolution
        The level of an ``.mcool`` (a ``.cool`` must be at it; :func:`uchrom.fea.rebin_map` makes coarser
        maps).
    balance
        Use the balanced matrix (``weight`` column).
    mode
        ``"intra"`` (default; chromosomes independently), ``"partitioned"`` (TAD-wise divide and conquer at
        high resolution, :func:`partitioned_mds`; ``mode_kw``: ``res_ratio``, ``alpha2``, ``n_workers``,
        ``tad_regions``) or ``"inter"`` (whole genome placed by the inter-chromosomal contacts,
        :func:`inter_mds`; ``mode_kw``: ``resolution_inter``; a ``.hic`` or ``.mcool``).
    alpha, weight, method, n_iter, lr, tol
        Contact-to-distance exponent, distance-decay prior weight and the solver (see :func:`run_mds`).
    device
        ``"auto"`` (CUDA / MPS when available, float32 there), ``"cpu"``, ``"cuda"``, ``"mps"``.
    cell_id
        ``spots["cell_id"]`` of the structure (e.g. the sample).
    key_added
        ``uns`` key of the settings and ``results["<key_added>.chroms"]`` (bins kept and time per
        chromosome); ``None`` stores neither.
    verbose
        Print the solver's progress.

    Returns
    -------
    ChromData
        One spot per kept bin, one trace per chromosome; coordinates in arbitrary units (mean target
        distance 1); ``uns["xyz_unit"] = "arbitrary (MDS)"``.
    """
    import torch
    from chromdata import ChromData

    from uchrom.fea.maps import _is_chromdata, _map_record, _open, contact_matrix, map_path

    from .torch_mds import get_device, run_mds

    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    path = map_path(cd, contacts)
    record = _map_record(cd, contacts)
    assembly = record.get("genome_assembly") or (cd.uns.get("genome_assembly") if _is_chromdata(cd) else None)
    quiet = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
    t0 = time.time()
    rows, frames = [], []
    used = int(resolution) if resolution else (100_000 if mode == "inter" else None)
    if mode == "inter":
        from .inter import inter_mds

        chroms = None if chrom is None else ([chrom] if isinstance(chrom, str) else list(chrom))
        with quiet:
            df = inter_mds(path, resolution_intra=used, chroms=chroms, alpha=alpha,
                           weight=weight, n_iter=n_iter, device=device, output_dir=None, verbose=verbose,
                           **mode_kw)
        df = df[np.isfinite(df[["x", "y", "z"]].to_numpy()).all(1)]
        frames.append(df[["chrom", "start", "end", "x", "y", "z"]])
        rows = [{"chrom": c, "n_bins": None, "n_kept": int((df["chrom"] == c).sum()), "seconds": None}
                for c in pd.unique(df["chrom"])]
    else:
        clr = _open(path, resolution)
        used = int(clr.binsize) if clr.binsize else used
        chroms = list(clr.chromnames) if chrom is None else ([chrom] if isinstance(chrom, str) else list(chrom))
        for c in chroms:
            t1 = time.time()
            bins, M = contact_matrix(path, chrom=c, resolution=resolution, balance=balance)
            with quiet:
                if mode == "intra":
                    X, keep = run_mds(torch.from_numpy(M), alpha=alpha, device=device, weight=weight,
                                      n_iter=n_iter, lr=lr, tol=tol, method=method, verbose=verbose)
                else:
                    from .partitioned import partitioned_mds

                    X = partitioned_mds(torch.from_numpy(M), device=device, alpha=alpha, weight=weight,
                                        n_iter=n_iter, verbose=verbose, **mode_kw)
                    keep = np.isfinite(X).all(1) & (M.sum(1) > 0)
                    X = X[keep]
            kept = bins[keep].reset_index(drop=True)
            frames.append(kept.assign(x=X[:, 0], y=X[:, 1], z=X[:, 2]))
            rows.append({"chrom": c, "n_bins": int(len(bins)), "n_kept": int(keep.sum()),
                         "seconds": time.time() - t1})
    df = pd.concat(frames, ignore_index=True)
    out = ChromData.from_dataframe(df, cell_id=cell_id, uns={"xyz_unit": "arbitrary (MDS)",
                                                            "genome_assembly": assembly})
    if key_added is not None:
        settings = {"method": "mds", "mode": mode, "solver": method, "alpha": float(alpha), "weight": float(weight),
                    "n_iter": int(n_iter), "device": str(get_device(device)), "balance": bool(balance),
                    "resolution": used,
                    "contacts": record.get("key", str(path)), "n_bins": int(out.n_spots),
                    "seconds": time.time() - t0,
                    "citation": "MDS / SMACOF as in miniMDS (Rieber & Mahony 2017, Bioinformatics 33:i261)"}
        out.uns[key_added] = settings
        out.results.set(f"{key_added}.chroms", pd.DataFrame(rows), kind="table",
                        function="uchrom.recon.bulk.mds.reconstruct_mds",
                        params={k: v for k, v in settings.items() if k not in ("seconds", "n_bins", "citation")},
                        inputs={"contacts": settings["contacts"], "chroms": [r["chrom"] for r in rows]})
    return out


__all__ = ["reconstruct_mds", "MODES"]
