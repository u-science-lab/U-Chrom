"""FastHigashi / Higashi wrapper for ``uchrom.emb``.

Design notes
------------
The expensive dependency (``fasthigashi`` / ``higashi``) is imported
lazily and can also be *injected* via ``wrapper_factory`` for testing.

FastHigashi's row order
~~~~~~~~~~~~~~~~~~~~~~~
``FastHigashi.fetch_cell_embedding(restore_order=True)`` returns rows in
the same order as ``label_info.pickle``.  We always pass
``restore_order=True`` and read that order from the pickle next to
``config.JSON`` — that's the canonical row anchor and avoids relying on
internal attributes that may change between FastHigashi versions.

Why we don't store imputed maps in ChromData
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Per-cell imputed contact maps are O(n²) per cell.  ChromData is
deliberately O(n) (no global ``spotp``).  When the user wants imputed
maps, they live on disk under ``path2result_dir`` and we only record the
path in ``cd.uns[embed_key]['result_dir']``.

Apple Silicon shim
~~~~~~~~~~~~~~~~~~
FastHigashi 0.1.1a0 calls ``tensor.pin_memory()`` unconditionally during
``prep_dataset``, which crashes on PyTorch ≥2.x on Apple Silicon when
MPS is the only non-CPU device available (PyTorch tries to pin against
MPS, which is not a real pinned-memory backend).  When CUDA isn't
available we no-op ``pin_memory`` for the duration of ``run()`` —
pinned memory only matters for CUDA host→device transfers anyway.
"""
from __future__ import annotations

import contextlib
import pickle
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

import numpy as np
import pandas as pd


# Default FastHigashi __init__ args.  Mirrors the constructor in
# fasthigashi 0.1.1a0; users override via wrapper_kwargs.
_FAST_HIGASHI_INIT_DEFAULTS: dict[str, Any] = {
    "off_diag": 100,
    "filter": False,
    "do_conv": False,
    "do_rwr": False,
    "do_col": False,
    "no_col": False,
}


@contextlib.contextmanager
def _no_pin_memory_without_cuda() -> Iterator[None]:
    """Make ``tensor.pin_memory()`` a no-op when CUDA is unavailable.

    On Apple Silicon (mps available, no cuda), PyTorch ≥2.x raises when
    a CPU tensor's storage is pinned because it tries to pin against MPS.
    Pinned memory only helps CUDA host→device transfers, so we can safely
    skip it.  Restored on exit so other code in the process is unaffected.
    """
    try:
        import torch
    except ImportError:
        yield
        return

    if torch.cuda.is_available():
        yield
        return

    original = torch.Tensor.pin_memory

    def _noop(self, *args, **kwargs):
        return self

    torch.Tensor.pin_memory = _noop      # type: ignore[assignment]
    try:
        yield
    finally:
        torch.Tensor.pin_memory = original  # type: ignore[assignment]


def align_embedding(
    emb: np.ndarray,
    emb_order: list[str],
    cd_cells: pd.DataFrame,
    *,
    cell_id_col: str = "cell_name",
) -> np.ndarray:
    """Reorder ``emb`` rows to match ``cd_cells[cell_id_col]`` exactly.

    Misaligning silently poisons every downstream analysis, so we fail
    loudly on missing / extra names rather than pad with NaNs.
    """
    if emb.shape[0] != len(emb_order):
        raise ValueError(
            f"emb has {emb.shape[0]} rows but emb_order has {len(emb_order)} names"
        )
    want = [str(n) for n in cd_cells[cell_id_col].tolist()]
    have = [str(n) for n in emb_order]

    missing = [n for n in want if n not in have]
    extra = [n for n in have if n not in want]
    if missing:
        raise ValueError(
            f"cell(s) in ChromData.cells missing from embedding: {missing}"
        )
    if extra:
        raise ValueError(
            f"cell(s) in embedding not present in ChromData.cells: {extra}"
        )

    idx = {n: i for i, n in enumerate(have)}
    return emb[[idx[n] for n in want]]


def run(
    cd,
    contacts_dir: str | Path,
    *,
    which: Literal["fast", "full"] = "fast",
    config_path: str | Path | None = None,
    rank: int = 256,
    embed_key: str = "higashi",
    cell_id_col: str = "cell_name",
    embed_variant: str = "embed_l2_norm",
    result_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    wrapper_factory: Callable[..., Any] | None = None,
    wrapper_kwargs: dict[str, Any] | None = None,
    run_model_kwargs: dict[str, Any] | None = None,
):
    """Run FastHigashi (or Higashi) and stash the cell embedding on ``cd``.

    Parameters
    ----------
    cd : ChromData
        Must have a ``cells`` frame containing ``cell_id_col``.
    contacts_dir : path
        Directory produced by :func:`uchrom.io.write_higashi_inputs`.
        Must contain ``config.JSON`` and ``label_info.pickle``.
    which : {"fast", "full"}
        FastHigashi (default) or full Higashi.
    rank : int
        Tucker rank passed to FastHigashi's ``run_model`` and used as
        ``final_dim`` in ``fetch_cell_embedding``.
    embed_variant : str
        Which key from FastHigashi's embedding dict to use.  Default is
        ``embed_l2_norm`` (L2-normalised, what the official tutorial uses).
    result_dir, cache_dir : path, optional
        Where FastHigashi caches per-cell tensors and writes results.
        Default to ``contacts_dir`` (lets ``write_higashi_inputs`` and
        FastHigashi share one directory tree).
    wrapper_factory : callable, optional
        For tests / alt backends.  Called as
        ``factory(config_path, path2input_cache, path2result_dir,
                  off_diag, filter, do_conv, do_rwr, do_col, no_col)``
        — the real FastHigashi constructor takes positional args.
    wrapper_kwargs : dict, optional
        Override the FastHigashi ``__init__`` defaults
        (``off_diag``, ``filter``, ``do_conv`` etc.).
    run_model_kwargs : dict, optional
        Forwarded to ``run_model``.  ``rank`` from the top-level kwarg
        wins unless explicitly overridden here.

    Returns
    -------
    ChromData
        The same ``cd`` object, mutated in place.
    """
    if cd.cells is None or cell_id_col not in cd.cells.columns:
        raise ValueError(
            f"ChromData.cells must have a '{cell_id_col}' column to run higashi"
        )

    contacts_dir = Path(contacts_dir)
    if config_path is None:
        config_path = contacts_dir / "config.JSON"
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Higashi config not found: {config_path}")

    label_info_path = contacts_dir / "label_info.pickle"
    if not label_info_path.exists():
        raise FileNotFoundError(
            f"label_info.pickle not found at {label_info_path}; "
            "produce it via uchrom.io.write_higashi_inputs."
        )
    with open(label_info_path, "rb") as f:
        label_info = pickle.load(f)
    if cell_id_col not in label_info:
        # also accept 'cell_name' even if cd uses a different col name
        if "cell_name" in label_info:
            order_key = "cell_name"
        else:
            raise KeyError(
                f"label_info.pickle has no '{cell_id_col}' or 'cell_name' key; "
                f"keys present: {list(label_info)}"
            )
    else:
        order_key = cell_id_col
    emb_order = [str(x) for x in label_info[order_key]]

    cache_dir = Path(cache_dir) if cache_dir else contacts_dir
    result_dir = Path(result_dir) if result_dir else contacts_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    if wrapper_factory is None:
        wrapper_factory = _default_factory(which)

    init_overrides = dict(_FAST_HIGASHI_INIT_DEFAULTS)
    init_overrides.update(wrapper_kwargs or {})
    wrapper = wrapper_factory(
        str(config_path),
        str(cache_dir),
        str(result_dir),
        init_overrides["off_diag"],
        init_overrides["filter"],
        init_overrides["do_conv"],
        init_overrides["do_rwr"],
        init_overrides["do_col"],
        init_overrides["no_col"],
    )

    with _no_pin_memory_without_cuda():
        wrapper.fast_process_data()
        wrapper.prep_dataset()

        rm_kwargs = {"rank": rank}
        rm_kwargs.update(run_model_kwargs or {})
        wrapper.run_model(**rm_kwargs)

        fetched = wrapper.fetch_cell_embedding(final_dim=rank, restore_order=True)
    emb = _select_variant(fetched, embed_variant)
    aligned = align_embedding(emb, emb_order, cd.cells, cell_id_col=cell_id_col)

    cd.cellm[embed_key] = aligned
    cd.uns[embed_key] = {
        "method": which,
        "rank": int(rank),
        "embed_variant": embed_variant,
        "config_path": str(config_path),
        "result_dir": str(result_dir),
    }
    return cd


def _select_variant(fetched: Any, variant: str) -> np.ndarray:
    """Pick one matrix out of FastHigashi's embedding dict (or accept ndarray)."""
    if isinstance(fetched, dict):
        if variant in fetched:
            return np.asarray(fetched[variant])
        # fall back: any ndarray-shaped value
        for k, v in fetched.items():
            arr = np.asarray(v)
            if arr.ndim == 2:
                return arr
        raise KeyError(
            f"variant {variant!r} not in fetched keys {list(fetched)}"
        )
    return np.asarray(fetched)


def _default_factory(which: str) -> Callable[..., Any]:
    if which == "fast":
        try:
            from fasthigashi.FastHigashi_Wrapper import FastHigashi as _W
        except ImportError as e:
            raise ImportError(
                "fasthigashi is not installed.  Install it with "
                "`pip install 'fast-higashi @ git+https://github.com/ma-compbio/Fast-Higashi' 'numpy<2'` "
                "(u-chrom[emb]) or pass wrapper_factory=..."
            ) from e
        return _W
    if which == "full":
        try:
            from higashi.Higashi_wrapper import Higashi as _W
        except ImportError as e:
            raise ImportError(
                "higashi is not installed.  Install with "
                "`pip install u-chrom[emb-full]` or pass wrapper_factory=..."
            ) from e
        return _W
    raise ValueError(f"which must be 'fast' or 'full', got {which!r}")
