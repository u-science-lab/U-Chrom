"""PyVista-based 3-D rendering of reconstructed chromatin structures.

Draws a :class:`~chromdata.ChromData` (or raw coordinate arrays) as
smooth tubes along the genomic chain — matching the look of the
interactive web browser (`uchrom-browser`).

Works in notebooks (inline screenshot or interactive if ``pythreejs`` /
`trame` backends are installed) and in scripts (save to PNG, or show
an OS window).  PyVista is imported lazily so importing ``uchrom.pl``
keeps its zero-cost path when the user only needs matplotlib helpers.

Colour options
--------------
``colour`` accepts:

- A matplotlib-style colour name or ``(r, g, b)`` tuple → whole chain
  painted uniformly.
- ``'bin'`` → gradient along bin index using ``cmap``.
- ``'chrom'`` → one colour per chromosome (requires ``spots`` to carry
  ``chrom`` — automatically true for a :class:`ChromData`).
- ``'trace'`` → one colour per trace (distinct alleles).
- An ``(N,)`` numpy array of scalar values (e.g. epigenetic signal) →
  mapped through ``cmap``.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple, Union

import numpy as np


_DEFAULT_CMAP = "viridis"


# ----------------------------------------------------------------------
# Coordinate extraction
# ----------------------------------------------------------------------

def _coords_and_groups(
    cd_or_coords: Any,
    chrom: Optional[str] = None,
    trace_id: Optional[Union[int, str]] = None,
) -> Tuple[list, np.ndarray, Optional[Any]]:
    """Return ``(coord_segments, scalar_per_bin_fallback, spots_df)``.

    ``coord_segments`` is a list of ``(coords, label)`` tuples so that
    each contiguous stretch can be rendered as a separate tube (chain
    jumps between chromosomes / traces become gaps rather than fake
    connecting edges).
    """
    try:
        from chromdata import ChromData  # local import
    except Exception:
        ChromData = None  # type: ignore

    if ChromData is not None and isinstance(cd_or_coords, ChromData):
        cd = cd_or_coords
        spots = cd.spots.copy()
        coords = np.asarray(cd.coords)
        if chrom is not None:
            keep = spots["chrom"].astype(str) == str(chrom)
            spots = spots[keep].reset_index(drop=True)
            coords = coords[keep.to_numpy()]
        if trace_id is not None and "trace_id" in spots.columns:
            keep = spots["trace_id"].astype(str) == str(trace_id)
            spots = spots[keep].reset_index(drop=True)
            coords = coords[keep.to_numpy()]

        # Sort by (chrom, trace_id, start) so tubes follow the chain
        order_cols = [c for c in ("chrom", "trace_id", "start")
                       if c in spots.columns]
        if order_cols:
            spots = spots.assign(_o=np.arange(len(spots)))
            spots = spots.sort_values(order_cols, kind="mergesort")
            coords = coords[spots["_o"].to_numpy()]
            spots = spots.drop(columns="_o").reset_index(drop=True)

        # Build segments — split whenever chrom / trace_id changes.
        segments = []
        if spots.empty:
            return segments, np.empty(0), spots
        if "trace_id" in spots.columns and "chrom" in spots.columns:
            key = list(zip(
                spots["chrom"].astype(str).tolist(),
                spots["trace_id"].astype(str).tolist(),
            ))
            start = 0
            for i in range(1, len(key) + 1):
                if i == len(key) or key[i] != key[i - 1]:
                    segments.append(
                        (coords[start:i], {
                            "chrom": key[start][0],
                            "trace_id": key[start][1],
                        })
                    )
                    start = i
        else:
            segments.append((coords, {}))
        return segments, np.arange(len(coords)), spots
    else:
        coords = np.asarray(cd_or_coords, dtype=np.float64)
        if coords.ndim != 2 or coords.shape[1] != 3:
            raise ValueError(
                "Expected a ChromData or a (n_bins, 3) coordinate array"
            )
        return [(coords, {})], np.arange(coords.shape[0]), None


# ----------------------------------------------------------------------
# Colour resolution
# ----------------------------------------------------------------------

def _resolve_color(
    mode: Union[str, Sequence, np.ndarray],
    segment_coords: np.ndarray,
    segment_meta: dict,
    all_bin_idx: np.ndarray,
    spots_df,
    cmap: str,
):
    """Return ``(color_array, per_vertex, label)`` for one chain segment.

    ``color_array`` is either a single RGB triple or a (N, 3) float
    array in [0, 1].  ``per_vertex=True`` when the tube should be
    coloured along its length.
    """
    import matplotlib.colors as mpl_colors
    from matplotlib import colormaps as mpl_colormaps

    N = segment_coords.shape[0]
    palette = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
               "#a65628", "#f781bf", "#999999", "#66c2a5", "#fc8d62"]

    if isinstance(mode, str):
        m = mode.lower()
        if m == "bin":
            t = np.linspace(0, 1, N) if N > 0 else np.empty(0)
            cm = mpl_colormaps.get_cmap(cmap)
            return cm(t)[:, :3], True, "bin"
        if m == "chrom":
            chrom = segment_meta.get("chrom", "chr?")
            h = (hash(chrom) % len(palette))
            return mpl_colors.to_rgb(palette[h]), False, f"chrom={chrom}"
        if m == "trace":
            tid = segment_meta.get("trace_id", "")
            h = (hash(str(tid)) % len(palette))
            return (
                mpl_colors.to_rgb(palette[h]), False,
                f"trace={tid}",
            )
        # Named colour
        return mpl_colors.to_rgb(m), False, None

    if isinstance(mode, np.ndarray) and mode.ndim == 1:
        # Index into the full scalar array by segment position
        seg_vals = mode[all_bin_idx[:N]] if len(mode) >= N else mode
        norm = (seg_vals - np.nanmin(mode)) / (
            max(np.nanmax(mode) - np.nanmin(mode), 1e-12)
        )
        cm = mpl_colormaps.get_cmap(cmap)
        return cm(norm)[:, :3], True, "scalar"

    # (r, g, b) tuple
    return tuple(mode[:3]), False, None


# ----------------------------------------------------------------------
# Public entry
# ----------------------------------------------------------------------

def plot_structure_3d(
    cd_or_coords: Any,
    chrom: Optional[str] = None,
    trace_id: Optional[Union[int, str]] = None,
    colour: Union[str, Sequence, np.ndarray] = "bin",
    cmap: str = _DEFAULT_CMAP,
    tube_radius: Optional[float] = None,
    spline_smoothing: bool = True,
    background: str = "white",
    show_scalar_bar: Optional[bool] = None,
    save_png: Optional[str] = None,
    window_size: Tuple[int, int] = (900, 700),
    show: bool = True,
    plotter: Any = None,
    notebook: Optional[bool] = None,
    jupyter_backend: str = "static",
    bond_outlier_factor: Optional[float] = None,
):
    """Render a ``ChromData`` (or ``(n_bins, 3)`` coords) as a 3-D tube.

    Parameters
    ----------
    cd_or_coords : ChromData or ndarray (n_bins, 3)
        The structure to plot.  A ``ChromData`` is sorted by
        ``(chrom, trace_id, start)`` and broken into contiguous
        sub-chains, each drawn as one tube so discontinuities are not
        bridged by fake edges.
    chrom : str, optional
        Restrict to one chromosome.
    trace_id : int or str, optional
        Restrict to one trace / allele.
    colour : 'bin' | 'chrom' | 'trace' | named colour | ndarray
        See the module docstring for the full colour contract.
    cmap : str
        Matplotlib colour-map name used when ``colour`` is a gradient
        or a scalar array.
    tube_radius : float, optional
        Radius of the rendered tube.  If ``None``, auto-picks 1.5 % of
        the bounding-box diagonal.
    spline_smoothing : bool
        If True, interpolate each sub-chain with a Catmull-Rom-style
        spline before piping (nicer curvature at sharp bends).
    background : str
        Colour of the plotter background.
    show_scalar_bar : bool, optional
        Whether to render a colour-bar (default: auto based on colour
        mode).
    save_png : str, optional
        If given, write a PNG to this path.
    window_size : (int, int)
        Renderer resolution in pixels.
    show : bool
        If True, call ``plotter.show()`` at the end (pops a window or
        renders inline in a notebook).
    plotter : pyvista.Plotter, optional
        Add to an existing plotter instead of creating one.
    notebook : bool, optional
        If None, auto-detect.
    jupyter_backend : str
        Passed to ``plotter.show(jupyter_backend=...)`` — ``'static'``
        renders an inline image (safest for nbconvert / CI), ``'trame'``
        gives an interactive widget.
    bond_outlier_factor : float, optional
        If set, any consecutive-bin bond longer than
        ``factor * median_bond`` is treated as a discontinuity and
        the chain is split at that point (rendered as two separate
        tubes with a visible gap).  Default ``None`` keeps the chain
        continuous — use this when the algorithm produces a legitimate
        chain that just happens to have a scale mismatch between
        intra-TAD bonds and inter-TAD boundary bonds (the typical
        two-stage reconstruction case).  Set to e.g. ``50`` to catch
        only pathologically long "bridges".

    Returns
    -------
    plotter : pyvista.Plotter
        The plotter object (useful for adding annotations before
        calling ``show()``).  ``None`` if PyVista is not installed.
    """
    try:
        import pyvista as pv
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pyvista is required for plot_structure_3d — "
            "install it or use the browser module instead"
        ) from exc

    segments, all_bin_idx, spots_df = _coords_and_groups(
        cd_or_coords, chrom=chrom, trace_id=trace_id,
    )
    if not segments:
        raise ValueError("No coordinates to render — empty filter?")

    # Split each contiguous segment further at pathologically long bonds
    # so we don't draw fake bridges across algorithm-induced discontinuities.
    if bond_outlier_factor is not None and bond_outlier_factor > 0:
        all_bonds = []
        for seg, _ in segments:
            if seg.shape[0] >= 2:
                all_bonds.extend(
                    np.linalg.norm(seg[1:] - seg[:-1], axis=1).tolist()
                )
        if all_bonds:
            thr = float(bond_outlier_factor * np.median(all_bonds))
            refined = []
            for seg, meta in segments:
                if seg.shape[0] < 2:
                    refined.append((seg, meta))
                    continue
                d = np.linalg.norm(seg[1:] - seg[:-1], axis=1)
                cuts = np.where(d > thr)[0] + 1
                if cuts.size == 0:
                    refined.append((seg, meta))
                else:
                    pts = [0, *cuts.tolist(), seg.shape[0]]
                    for a, b in zip(pts[:-1], pts[1:]):
                        if b - a >= 2:
                            refined.append((seg[a:b], meta))
            segments = refined

    # Auto tube radius from global extent
    all_xyz = np.vstack([s for s, _ in segments])
    extent = float(np.linalg.norm(all_xyz.max(0) - all_xyz.min(0)))
    if tube_radius is None:
        tube_radius = max(extent * 0.010, 0.01)

    if notebook is None:
        try:
            from IPython import get_ipython
            notebook = get_ipython() is not None
        except Exception:
            notebook = False

    if plotter is None:
        plotter = pv.Plotter(
            notebook=notebook, off_screen=save_png is not None and not show,
            window_size=list(window_size),
        )
    plotter.set_background(background)

    any_scalar = False
    for segment_coords, meta in segments:
        if segment_coords.shape[0] < 2:
            continue
        col, per_vertex, label = _resolve_color(
            colour, segment_coords, meta, all_bin_idx,
            spots_df, cmap,
        )

        if spline_smoothing:
            n_pts = min(segment_coords.shape[0] * 3, 1500)
            try:
                spline = pv.Spline(segment_coords, n_points=n_pts)
                tube = spline.tube(radius=tube_radius, n_sides=12)
            except Exception:
                poly = pv.PolyData()
                poly.points = segment_coords
                n_pts = segment_coords.shape[0]
                cells = np.zeros(n_pts + 1, dtype=np.int_)
                cells[0] = n_pts
                cells[1:] = np.arange(n_pts)
                poly.lines = cells
                tube = poly.tube(radius=tube_radius, n_sides=12)
        else:
            poly = pv.PolyData()
            poly.points = segment_coords
            n_pts = segment_coords.shape[0]
            cells = np.zeros(n_pts + 1, dtype=np.int_)
            cells[0] = n_pts
            cells[1:] = np.arange(n_pts)
            poly.lines = cells
            tube = poly.tube(radius=tube_radius, n_sides=12)

        kw = dict(smooth_shading=True, specular=0.3, specular_power=15)
        if per_vertex:
            # Map colours onto the tube by bin index along the spline.
            n_out_pts = tube.points.shape[0]
            scalar_idx = np.linspace(0, segment_coords.shape[0] - 1, n_out_pts)
            scalar_idx = np.clip(scalar_idx.astype(int), 0,
                                 segment_coords.shape[0] - 1)
            col_arr = np.asarray(col)
            if col_arr.ndim == 2 and col_arr.shape[0] == segment_coords.shape[0]:
                tube["rgb"] = (col_arr[scalar_idx] * 255).astype(np.uint8)
                plotter.add_mesh(tube, scalars="rgb", rgb=True, **kw)
            else:
                plotter.add_mesh(tube, color=tuple(col), **kw)
        else:
            plotter.add_mesh(tube, color=tuple(col), **kw)

    plotter.add_axes()
    plotter.show_bounds(
        grid="back", location="outer", ticks="outside",
        xtitle="x", ytitle="y", ztitle="z",
    )

    if save_png:
        plotter.screenshot(save_png)
    if show:
        if notebook:
            return plotter.show(jupyter_backend=jupyter_backend)
        plotter.show()
    return plotter


__all__ = ["plot_structure_3d"]
