"""``deconvolve_igm``: probability matrix → population ChromData."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from ._params import IgmParams

CITATIONS = [
    "Boninsegna L. et al. (2022) Integrative genome modeling platform reveals essentiality of rare "
    "contact events in 3D genome organizations. Nat Methods 19:938-949. doi:10.1038/s41592-022-01527-x",
    "Tjong H. et al. (2016) Population-based 3D genome structure analysis reveals driving forces in "
    "spatial genome organization. PNAS 113:E1663-E1672. doi:10.1073/pnas.1512577113",
    "Hua N. et al. (2018) Producing genome structure populations with the dynamic and automated PGS "
    "software. Nat Protoc 13:915-926. doi:10.1038/nprot.2018.008",
]

#: spots per chunk handed to the streaming writer
_WRITE_CHUNK_SPOTS = 2_000_000


def _engine():
    from uchrom.recon.sc.nucdyn.native import _engine as _native

    uchrom_recon = _native()
    if not hasattr(uchrom_recon, "calc_population"):
        raise ImportError("the installed uchrom_recon has no 'igm' protocol; rebuild packages/uchrom-recon")
    return uchrom_recon


def native_available() -> bool:
    """True when the native engine with the ``igm`` protocol is importable."""
    try:
        _engine()
    except ImportError:
        return False
    return True


def _resolve_device(device: str) -> str:
    if device in ("cpu", "gpu"):
        return device
    if device != "auto":
        raise ValueError(f"device must be 'auto', 'cpu' or 'gpu', got {device!r}")
    return "gpu" if _engine().gpu_available() else "cpu"


def _is_chromdata(x: Any) -> bool:
    return hasattr(x, "bins") and hasattr(x, "coords") and hasattr(x, "spots")


def _upper_coo(P: Any, n: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Strict upper triangle (i < j, value > 0) of a square matrix as COO.
    A matrix with entries in both triangles is read from its upper triangle;
    a lower-triangular one from its lower triangle."""
    import scipy.sparse as sp

    M = sp.coo_matrix(P) if not sp.issparse(P) else P.tocoo()
    if M.shape != (n, n):
        raise ValueError(f"probability matrix shape {M.shape} does not match {n} bins")
    r, c, v = np.asarray(M.row), np.asarray(M.col), np.asarray(M.data, dtype=np.float64)
    keep = (v > 0) & (r != c)
    r, c, v = r[keep], c[keep], v[keep]
    up = r < c
    if up.any():
        r, c, v = r[up], c[up], v[up]
    else:
        r, c = c, r
    if np.any(v > 1.0 + 1e-9) or np.any(~np.isfinite(v)):
        raise ValueError("probabilities must be finite and in [0, 1]")
    return r.astype(np.uint32), c.astype(np.uint32), v


def _normalise_bins(bins: pd.DataFrame) -> pd.DataFrame:
    missing = {"chrom", "start", "end"} - set(bins.columns)
    if missing:
        raise ValueError(f"bins lack columns {sorted(missing)}")
    b = pd.DataFrame({"chrom": bins["chrom"].astype(str).to_numpy(),
                      "start": pd.to_numeric(bins["start"]).to_numpy(np.int64),
                      "end": pd.to_numeric(bins["end"]).to_numpy(np.int64)})
    codes = pd.factorize(b["chrom"])[0]
    if np.any(np.diff(codes) < 0):
        raise ValueError("bins must be grouped by chromosome (each chromosome contiguous, genome order)")
    return b


def _inputs(data: Any, probabilities: Any, bins: Optional[pd.DataFrame]):
    """(bins DataFrame, probability matrix) from the accepted call forms."""
    if hasattr(data, "probabilities") and hasattr(data, "bins") and not _is_chromdata(data):
        if probabilities is not None:                     # a ProbabilityMatrix (preprocess_hic / _igm)
            raise ValueError("pass a ProbabilityMatrix or probabilities=, not both")
        return _normalise_bins(data.bins if bins is None else bins), data.probabilities
    if _is_chromdata(data):
        if bins is None:
            bins = data.bins[["chrom", "start", "end"]]
        if probabilities is None:
            raise ValueError("deconvolve(cd, ...) needs probabilities= (a bins x bins contact-probability "
                             "matrix, e.g. from uchrom.recon.bulk.deconv.preprocess)")
        P = probabilities
    else:
        if data is not None and probabilities is not None:
            raise ValueError("pass the matrix as the first argument or as probabilities=, not both")
        P = data if data is not None else probabilities
        if P is None:
            raise ValueError("no probability matrix given")
        if bins is None:
            raise ValueError("a probability matrix needs bins= (DataFrame with chrom, start, end)")
    return _normalise_bins(bins), P


def _occupancy_total_bp(p: IgmParams, bins_all: pd.DataFrame, un) -> float:
    """Genome size (bp, all copies) the occupancy refers to; 0 = the modelled beads."""
    sc = p.occupancy_scope
    if sc == "model" or p.bead_radius is not None:
        return 0.0
    if sc == "genome":
        size = (bins_all["end"] - bins_all["start"]).groupby(bins_all["chrom"], sort=False).sum()
        copies = un.resolve_copies(list(size.index), p.ploidy)
        return float(np.dot(size.to_numpy(np.float64), np.asarray(copies, dtype=np.float64)))
    return float(sc)


def _init_pins(init_positions: Any, bins: pd.DataFrame, s: int) -> Optional[Dict[str, np.ndarray]]:
    """``init_positions`` table -> engine pins (structure, model bin, copy, xyz).

    Columns: ``structure`` (index 0..S-1 or cell id ``"s00012"``), ``chrom``,
    ``start`` (any position inside the bin, bp), ``copy`` (default 0),
    ``x``, ``y``, ``z`` (nm, the nucleus frame: centre at the origin)."""
    if init_positions is None:
        return None
    df = pd.DataFrame(init_positions)
    need = {"structure", "chrom", "start", "x", "y", "z"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"init_positions lacks columns {sorted(missing)}")
    if len(df) == 0:
        return None
    st = df["structure"]
    if st.dtype == object or isinstance(st.dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(st):
        ids = {c: k for k, c in enumerate(_structure_ids(s))}
        try:
            struct = np.array([ids[x] if isinstance(x, str) else int(x) for x in st], dtype=np.int64)
        except KeyError as e:
            raise ValueError(f"init_positions: unknown structure {e.args[0]!r}") from None
    else:
        struct = st.to_numpy(np.int64)
    if struct.min() < 0 or struct.max() >= s:
        raise ValueError(f"init_positions: structure index outside 0..{s - 1}")
    copy = df["copy"].to_numpy(np.int64) if "copy" in df.columns else np.zeros(len(df), dtype=np.int64)
    if copy.min() < 0:
        raise ValueError("init_positions: negative copy")
    chrom = df["chrom"].astype(str).to_numpy()
    pos = pd.to_numeric(df["start"]).to_numpy(np.int64)
    bin_idx = np.full(len(df), -1, dtype=np.int64)
    bchrom = bins["chrom"].to_numpy()
    for c in np.unique(chrom):
        rows = np.flatnonzero(chrom == c)
        cb = np.flatnonzero(bchrom == c)
        if len(cb) == 0:
            raise ValueError(f"init_positions: chromosome {c!r} is not modelled")
        st_c = bins["start"].to_numpy()[cb]
        en_c = bins["end"].to_numpy()[cb]
        k = np.searchsorted(st_c, pos[rows], side="right") - 1
        ok = (k >= 0) & (pos[rows] < en_c[np.clip(k, 0, None)])
        if not ok.all():
            raise ValueError(f"init_positions: {int((~ok).sum())} positions on {c} fall outside the bins")
        bin_idx[rows] = cb[k]
    xyz = df[["x", "y", "z"]].to_numpy(np.float64)
    if not np.isfinite(xyz).all():
        raise ValueError("init_positions: non-finite coordinates")
    return {"structure": struct, "bin": bin_idx, "copy": copy, "xyz": xyz}


def _structure_ids(s: int) -> List[str]:
    w = max(5, len(str(max(s - 1, 0))))
    return [f"s{k:0{w}d}" for k in range(s)]


class _Layout:
    """Spot layout of one structure (beads in engine order) and id tables."""

    def __init__(self, res: Mapping[str, Any], bins: pd.DataFrame, s: int):
        self.bead_bin = np.asarray(res["bead_bin"], dtype=np.int64)
        self.bead_chain = np.asarray(res["bead_chain"], dtype=np.int64)
        self.bead_copy = np.asarray(res["bead_copy"], dtype=np.int64)
        self.n = len(self.bead_bin)
        # chains: (chrom, copy) in engine order
        first = np.r_[0, np.flatnonzero(np.diff(self.bead_chain)) + 1]
        self.chain_chrom = bins["chrom"].to_numpy()[self.bead_bin[first]]
        self.chain_copy = self.bead_copy[first]
        self.n_chains = len(first)
        self.cell_ids = _structure_ids(s)
        self.trace_ids = [f"{c}:{ch}:{cp}" for c in self.cell_ids
                          for ch, cp in zip(self.chain_chrom, self.chain_copy)]
        self.bins = bins

    def spots(self, s0: int, s1: int) -> pd.DataFrame:
        k = s1 - s0
        bb = np.tile(self.bead_bin, k)
        trace_codes = (np.repeat(np.arange(s0, s1), self.n) * self.n_chains + np.tile(self.bead_chain, k))
        cell_codes = np.repeat(np.arange(s0, s1), self.n)
        tr = self.trace_ids[s0 * self.n_chains:s1 * self.n_chains]
        return pd.DataFrame({
            "chrom": pd.Categorical(self.bins["chrom"].to_numpy()[bb]),
            "start": self.bins["start"].to_numpy()[bb],
            "end": self.bins["end"].to_numpy()[bb],
            "trace_id": pd.Categorical.from_codes(trace_codes - s0 * self.n_chains, categories=tr),
            "cell_id": pd.Categorical.from_codes(cell_codes - s0, categories=self.cell_ids[s0:s1]),
        })

    def traces(self) -> pd.DataFrame:
        s = len(self.cell_ids)
        df = pd.DataFrame({
            "cell_id": np.repeat(self.cell_ids, self.n_chains),
            "chrom": np.tile(self.chain_chrom, s),
            "copy": np.tile(self.chain_copy, s).astype(np.int64),
        }, index=pd.Index(self.trace_ids, name="trace_id"))
        return df


def _cells_table(stats: Sequence[Mapping[str, Any]], cell_ids: List[str]) -> pd.DataFrame:
    rows = []
    for st in stats:
        v = st["viol"]
        imp = v["hic_imposed"] + v["poly_imposed"] + v["env_imposed"]
        vio = v["hic_violated"] + v["poly_violated"] + v["env_violated"]
        rows.append({
            "violation_score": vio / imp if imp else 0.0,
            "n_hic_restraints": int(st["n_hic"]),
            **{k: int(x) for k, x in v.items()},
            "energy": float(st["energy"]),
            "cg_iterations": int(st["cg_iterations"]),
        })
    return pd.DataFrame(rows, index=pd.Index(cell_ids, name="cell_id"))


def deconvolve_igm(
    data: Any = None,
    *,
    probabilities: Any = None,
    bins: Optional[pd.DataFrame] = None,
    chrom: Optional[Union[str, Sequence[str]]] = None,
    params: Optional[IgmParams] = None,
    device: str = "auto",
    seed: int = 0,
    out: Optional[Union[str, os.PathLike]] = None,
    keep_intermediate: bool = False,
    key_added: Optional[str] = "deconv.igm",
    progress: Optional[Any] = None,
    init_positions: Optional[pd.DataFrame] = None,
    **overrides: Any,
):
    """IGM population modelling of a contact-probability matrix.

    The defaults run the faithful IGM 1.0 protocol.  Opt-in options from
    IGM-Plus (alberlab/IGM-Plus v2.0.2) and IGM_2.0 (fields of
    :class:`IgmParams`, also accepted as keyword overrides): ``chrom=`` with
    ``occupancy_scope`` (chromosome-subset models), ``bead_radius``
    (radii set directly, exclusive with ``occupancy``),
    ``iterative_correction=False``, ``assignment_pooling="gp"``,
    ``init_positions`` + ``init_noise`` (expanded initialisation).  The
    per-round logs always carry the violation breakdown by restraint kind
    (Hi-C intra / inter, polymer, envelope) with the most violating
    structure; ``uns["deconv"]["relax_init"]`` holds that of the initial
    relaxation.

    Parameters
    ----------
    data, probabilities, bins
        The haploid contact-probability matrix (``scipy.sparse`` or dense,
        entries = probability that the two loci are in contact, neighbours 1)
        and its bins (``chrom``, ``start``, ``end``; each chromosome
        contiguous): ``deconvolve_igm(P, bins=bins)``, the
        :class:`~uchrom.recon.bulk.deconv.preprocess.ProbabilityMatrix` of
        ``preprocess_hic`` (``deconvolve_igm(prob)``: its matrix and bins),
        or ``deconvolve_igm(cd, probabilities=P)`` with the bins of ``cd``.
    chrom
        Restrict the model to these chromosomes (default: all bins), e.g.
        one chromosome: its copies follow ``ploidy`` (``"haploid"``,
        ``"diploid"`` or ``{chrom: copies}``); the nuclear envelope stays the
        full nucleus.  The bead radii follow ``params.occupancy_scope``:
        ``"model"`` (default, as IGM-Plus: the modelled chromosomes alone
        fill ``occupancy`` of the nucleus, so beads grow as fewer
        chromosomes are modelled), ``"genome"`` (radii of the whole-genome
        model of the input bins) — or set ``bead_radius``.
    params
        :class:`IgmParams`; keyword ``overrides`` replace single fields
        (``n_structures=1000``, ``occupancy=0.4``, ...).
    device
        ``"auto"`` (GPU if available), ``"cpu"`` or ``"gpu"``.
    seed
        Master seed (initial structures, velocities).
    out
        ``*.chromdata.zarr`` path: the population is streamed to it with
        :meth:`ChromData.writer` and returned backed (large populations).
        ``None``: an in-memory ChromData.
    keep_intermediate
        Keep the population after every M-step (round) as
        ``layers["round_<k>"]`` (spot-aligned coordinates; round 0 = the
        relaxed random start).  Off by default.
    key_added
        ``cd.results`` key of the last activation-distance table.
    progress
        Callback ``progress(round_log: dict)`` after every M-step (round 0:
        the initial relaxation).
    init_positions
        Optional table of loci placed at given initial positions (IGM-Plus
        expanded initialisation): columns ``structure`` (0..S-1 or
        ``"s00012"``), ``chrom``, ``start`` (a position inside the bin),
        ``copy`` (default 0), ``x``, ``y``, ``z`` (nm, nucleus centred at the
        origin).  Beads between two pinned beads of one chain are linearly
        interpolated; the rest keep the random-territory start.  Only the
        start is set — no positional restraint is added (see the stage-2
        design in an unpublished design note).

    Returns
    -------
    ChromData: ``bins`` = the (haploid) model bins; one **cell** per structure
    (``s00000`` …, per-structure violation statistics in ``cells``), one
    **trace** per chromosome copy (``s00000:chr1:0``; ``traces`` has
    ``chrom`` / ``copy``), one spot per bead pointing to its bin; coordinates
    in nm.  ``bin_tracks["radius_nm"]``, ``bin_tracks["input_prob_rowsum"]``;
    ``uns["deconv"]``: method, parameters, per-round log (with
    ``breakdown``), ``relax_init``, engine, timing.  ``cells`` also has
    ``hic_inter_imposed`` / ``hic_inter_violated`` (the inter-chromosomal
    subset of ``hic_*``).
    """
    from chromdata import ChromData
    from chromdata.results import ResultsStore

    un = _engine()
    p = params if params is not None else IgmParams()
    if overrides:
        unknown = set(overrides) - {f.name for f in __import__("dataclasses").fields(IgmParams)}
        if unknown:
            raise TypeError(f"unknown IGM parameters: {sorted(unknown)}")
        p = p.replace(**overrides)
    bins_df, P = _inputs(data, probabilities, bins)
    occ_total_bp = _occupancy_total_bp(p, bins_df, un)
    n_bins_all = len(bins_df)
    ii, jj, vv = _upper_coo(P, n_bins_all)
    if chrom is not None:
        keep_chroms = [chrom] if isinstance(chrom, str) else list(chrom)
        keep = bins_df["chrom"].isin(keep_chroms).to_numpy()
        if not keep.any():
            raise ValueError(f"no bins on {keep_chroms}")
        new = np.full(n_bins_all, -1, dtype=np.int64)
        new[keep] = np.arange(int(keep.sum()))
        m = keep[ii] & keep[jj]
        ii, jj, vv = new[ii[m]].astype(np.uint32), new[jj[m]].astype(np.uint32), vv[m]
        bins_df = bins_df[keep].reset_index(drop=True)
    pins = _init_pins(init_positions, bins_df, int(p.n_structures))
    dev = _resolve_device(device)
    native = p.to_native()
    native["occupancy_total_bp"] = occ_total_bp
    for st in native["stages"]:
        st["mdsteps"] = int(st["mdsteps"])
    if native.get("relax"):
        native["relax"] = {**native["relax"], "mdsteps": int(native["relax"]["mdsteps"])}
    native.update(device=dev, seed=int(seed))

    tmpdir = None
    round_files: List[Tuple[int, Path]] = []
    if keep_intermediate:
        tmpdir = Path(tempfile.mkdtemp(prefix="igm_rounds_", dir=(Path(out).parent if out else None)))

    def on_round(log: Dict[str, Any], coords) -> None:
        if keep_intermediate and coords is not None:
            f = tmpdir / f"round_{int(log['round']):03d}.npy"
            np.save(f, np.asarray(coords, dtype=np.float32))
            round_files.append((int(log["round"]), f))
        if progress is not None:
            progress(log)

    t0 = time.time()
    try:
        res = un.calc_population(
            bins_df["chrom"].to_numpy(), bins_df["start"].to_numpy(), bins_df["end"].to_numpy(),
            ii, jj, vv, ploidy=p.ploidy, on_round=on_round,
            round_coords=bool(keep_intermediate), init_pins=pins, **native)
        S = int(res["coords"].shape[0])
        lay = _Layout(res, bins_df, S)
        # per-bin tracks
        radius = np.full(len(bins_df), np.nan)
        first_copy = res["bead_copy"] == 0
        radius[lay.bead_bin[first_copy]] = np.asarray(res["radii"])[first_copy]
        rowsum = np.zeros(len(bins_df))
        np.add.at(rowsum, ii.astype(np.int64), vv)
        np.add.at(rowsum, jj.astype(np.int64), vv)
        bin_tracks = pd.DataFrame({"radius_nm": radius, "input_prob_rowsum": rowsum})
        cells = _cells_table(res["final_stats"], lay.cell_ids)
        traces = lay.traces()
        a = res["actdist"]
        act = pd.DataFrame({"bin_i": a["i"].astype(np.int64), "bin_j": a["j"].astype(np.int64),
                            "f": a["f"], "p": a["p"], "p_now": a["p_now"], "d_act_nm": a["d"]})
        prov = {k: v for k, v in native.items()}
        prov["ploidy"] = p.ploidy
        prov["occupancy_scope"] = p.occupancy_scope
        if pins is not None:
            prov["init_positions"] = {"n_loci": int(len(pins["structure"])),
                                      "n_structures": int(len(np.unique(pins["structure"])))}
        uns = {"deconv": {
            "method": "igm",
            "protocol": "igm (native uchrom_recon)",
            "engine": res["engine"],
            "engine_version": un.__version__,
            "params": prov,
            "copies": res["copies"],
            "n_structures": S,
            "n_beads": lay.n,
            "input": {"n_bins": int(len(bins_df)), "n_pairs": int(len(vv)), "chrom": chrom},
            "rounds": res["rounds"],
            "relax_init": res.get("relax_init"),
            "stopped_at_max_iterations": res["stopped_at_max_iterations"],
            "seconds_engine": res["seconds_total"],
            "seconds_total": time.time() - t0,
            "intermediate_rounds": [r for r, _ in round_files],
            "citations": CITATIONS,
        }, "xyz_unit": "nm"}
        results = ResultsStore()
        if key_added is not None:
            results.set(key_added, act, kind="table", function="uchrom.recon.bulk.deconv.igm.deconvolve_igm",
                        params=prov, inputs={"n_bins": int(len(bins_df)), "n_pairs": int(len(vv))})
        coords = res["coords"]

        def layers_for(s0: int, s1: int) -> Dict[str, np.ndarray]:
            out_l = {}
            for r, f in round_files:
                arr = np.load(f, mmap_mode="r")
                out_l[f"round_{r:02d}"] = np.asarray(arr[s0:s1], dtype=np.float64).reshape(-1, 3)
            return out_l

        if out is None:
            spots = lay.spots(0, S)
            cd = ChromData(np.asarray(coords, dtype=np.float64).reshape(-1, 3), spots,
                           bins=bins_df, cells=cells, traces=traces, layers=layers_for(0, S) or None, uns=uns)
            cd.bin_tracks = bin_tracks
            cd.results = results
            return cd
        per = max(1, _WRITE_CHUNK_SPOTS // max(lay.n, 1))
        with ChromData.writer(out, bins=bins_df) as w:
            for s0 in range(0, S, per):
                s1 = min(S, s0 + per)
                lyr = layers_for(s0, s1)
                w.append(coords=np.asarray(coords[s0:s1], dtype=np.float64).reshape(-1, 3),
                         spots=lay.spots(s0, s1), layers=lyr or None)
            w.finish(cells=cells, traces=traces, bin_tracks=bin_tracks, results=results, uns=uns)
        return ChromData.read(out, backed=True)
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
