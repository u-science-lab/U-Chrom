"""Shared steps of the single-cell Hi-C builds of the atlas (HiRES, dscHi-C, GAGE-seq, Droplet Hi-C).

* :func:`stream_pairs` reads a (gzipped) ``.pairs`` / pairs-like table in blocks (``gzip -dc | grep -v '^#'`` into
  pyarrow's CSV reader): the files are 1–25 GB, never loaded whole.
* :class:`ContactBinner` bins contacts once into a per-cell map (default 1 Mb; written as ``.scool``) and an
  all-cells bulk map (default 50 kb; ``.mcool`` with coarser zooms).  Contacts go to bucket files on disk (cell
  buckets / bin1 buckets), so memory stays bounded by one bucket however many cells.
* :func:`rna_h5ad` / :func:`hvg_zscores` write the RNA counts as the store's linked AnnData and pick the genes
  of the RNA embedding.

The builds then put cells, embeddings and the links into a ``.chromdata.zarr`` and embed the linked files
(``python -m chromdata.embedded STORE``) before the store goes to the atlas.
"""

from __future__ import annotations

import gzip
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

import numpy as np
import pandas as pd

MM10 = [f"chr{i}" for i in range(1, 20)] + ["chrX", "chrY"]
HG38 = [f"chr{i}" for i in range(1, 23)] + ["chrX", "chrY"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def chromsizes(path: Optional[Path] = None, assembly: str = "mm10", keep: Optional[Sequence[str]] = None) -> Dict[str, int]:
    """Chromosome sizes from a pairs header (``#chromosome:`` / ``#chromsize:`` / ``#samheader: @SQ``), a cooler (URI)
    or, without one, UCSC's table for ``assembly``; only the ``keep`` chromosomes (default: autosomes, X, Y), in that order."""
    sizes: Dict[str, int] = {}
    if path is not None and ("::" in str(path) or str(path).endswith((".cool", ".mcool"))):
        import cooler
        sizes = {str(k): int(v) for k, v in cooler.Cooler(str(path)).chromsizes.items()}
    elif path is not None:
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt") as fh:
            for line in fh:
                if not line.startswith("#"):
                    break
                parts = line.split()
                if parts[0] in ("#chromosome:", "#chromsize:") and len(parts) >= 3:
                    sizes[parts[1]] = int(parts[2])
                elif parts[0] == "#samheader:" and parts[1] == "@SQ":
                    f = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
                    if "SN" in f and "LN" in f:
                        sizes[f["SN"]] = int(f["LN"])
    if not sizes:
        import cooler.util
        sizes = {str(k): int(v) for k, v in cooler.util.fetch_chromsizes(assembly).items()}
    keep = list(keep or (HG38 if assembly.startswith("hg") else MM10))
    return {c: sizes[c] for c in keep if c in sizes}


def stream_pairs(path: Path, columns: Dict[str, int], *, block_mb: int = 256,
                 types: Optional[Dict[str, str]] = None) -> Iterator[pd.DataFrame]:
    """Blocks of a tab-separated pairs table as DataFrames with the named ``columns`` (name -> 0-based column).
    Header / comment lines (``#``) are skipped.  ``types``: name -> "int" | "str" (default: chrom/barcode-like
    names str, the rest int)."""
    import pyarrow as pa
    import pyarrow.csv as pacsv

    cmd = f"gzip -dc '{path}' | LC_ALL=C grep -v '^#'" if str(path).endswith(".gz") else f"LC_ALL=C grep -v '^#' '{path}'"
    first = subprocess.run(["/bin/sh", "-c", cmd + " | head -n 1"], capture_output=True).stdout
    if not first.strip():
        return
    n_cols = len(first.rstrip(b"\n").split(b"\t"))       # the table's width: every column must be named
    if max(columns.values()) >= n_cols:
        raise ValueError(f"{path}: {n_cols} columns, asked for column {max(columns.values())}")
    skipped = [0]

    def bad_row(row):
        skipped[0] += 1
        return "skip"

    proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE, bufsize=1 << 24)
    names = [f"c{i}" for i in range(n_cols)]
    want = {f"c{i}": name for name, i in columns.items()}
    types = dict(types or {})
    col_types = {}
    for name, i in columns.items():
        kind = types.get(name) or ("int" if name.startswith("pos") else "str")
        col_types[f"c{i}"] = pa.int64() if kind == "int" else pa.dictionary(pa.int32(), pa.string())
    try:
        reader = pacsv.open_csv(
            proc.stdout,
            read_options=pacsv.ReadOptions(column_names=names, block_size=block_mb << 20),
            parse_options=pacsv.ParseOptions(delimiter="\t", invalid_row_handler=bad_row),
            convert_options=pacsv.ConvertOptions(include_columns=list(want), column_types=col_types))
        for batch in reader:
            df = batch.to_pandas()
            yield df.rename(columns=want)
    except pa.ArrowInvalid as exc:      # an empty file
        if "Empty CSV file" not in str(exc):
            raise
    finally:
        proc.stdout.close()
        proc.wait()
        if skipped[0]:
            log(f"  {path}: skipped {skipped[0]:,} malformed rows")


def cool_contacts(uri: str) -> pd.DataFrame:
    """The contacts of a single-cell map (a ``.cool`` or ``.mcool::/resolutions/N`` URI): each pixel repeated
    ``count`` times at the midpoints of its bins; columns chrom1, pos1, chrom2, pos2."""
    import cooler

    clr = cooler.Cooler(str(uri))
    bins, px = clr.bins()[["chrom", "start", "end"]][:], clr.pixels()[:]
    mid = ((bins["start"] + bins["end"]) // 2).to_numpy()
    b1, b2 = (np.repeat(px[c].to_numpy(), px["count"].to_numpy().astype(np.int64)) for c in ("bin1_id", "bin2_id"))
    chrom = bins["chrom"].astype(str).to_numpy()
    return pd.DataFrame({"chrom1": chrom[b1], "pos1": mid[b1], "chrom2": chrom[b2], "pos2": mid[b2]})


def extract_members(tars: Iterable[Path], names: Iterable[str], out: Path) -> None:
    """Write the members of ``tars`` whose file name is in ``names`` to ``out/<name>`` (those not there yet)."""
    import tarfile

    out.mkdir(parents=True, exist_ok=True)
    want = {n for n in names if not (out / n).exists()}
    for tar in tars if want else []:
        with tarfile.open(tar, "r|gz") as t:
            for mem in t:
                base = Path(mem.name).name
                if mem.isfile() and base in want:
                    tmp = out / f"{base}.part"
                    tmp.write_bytes(t.extractfile(mem).read())
                    tmp.replace(out / base)


def lu2025_map_name(cell: str) -> str:
    """Lu 2025 (scNanoHi-C2): the file of a cell's map in the library tarballs ('EGC_E11.5_0513.P37B1' ->
    'FGC_E11.5_0513.P37B1_mm10_MGP_chronly_sort.mcool')."""
    return cell.replace("EGC_", "FGC_", 1) + "_mm10_MGP_chronly_sort.mcool"


def bin_table(sizes: Dict[str, int], res: int) -> pd.DataFrame:
    rows = []
    for c, n in sizes.items():
        starts = np.arange(0, n, res, dtype=np.int64)
        rows.append(pd.DataFrame({"chrom": c, "start": starts, "end": np.minimum(starts + res, n)}))
    return pd.concat(rows, ignore_index=True)


class _Buckets:
    """Append-only int64 key files, one per bucket."""

    def __init__(self, folder: Path, n: int, tag: str):
        self.folder, self.n, self.tag = folder, n, tag
        self.files = [open(folder / f"{tag}_{b:04d}.i64", "ab") for b in range(n)]

    def add(self, bucket: np.ndarray, keys: np.ndarray) -> None:
        order = np.argsort(bucket, kind="stable")
        bucket, keys = bucket[order], keys[order]
        bounds = np.searchsorted(bucket, np.arange(self.n + 1))
        for b in np.flatnonzero(np.diff(bounds)):
            self.files[b].write(keys[bounds[b]:bounds[b + 1]].astype(np.int64).tobytes())

    def close(self) -> None:
        for f in self.files:
            f.close()

    def counts(self, b: int):
        """(unique keys sorted, counts) of bucket ``b``."""
        keys = np.fromfile(self.folder / f"{self.tag}_{b:04d}.i64", dtype=np.int64)
        return np.unique(keys, return_counts=True)


class KeyMaker:
    """Bin keys of contacts (picklable: worker processes bin their files, the binner only stores the keys)."""

    def __init__(self, sizes: Dict[str, int], cell_res: int, bulk_res: int):
        self.sizes = dict(sizes)
        self.chroms = list(sizes)
        self.index = {c: i for i, c in enumerate(self.chroms)}
        self.cell_res, self.bulk_res = cell_res, bulk_res

        def offsets(res):
            n = np.array([-(-self.sizes[c] // res) for c in self.chroms], dtype=np.int64)
            return np.r_[0, np.cumsum(n)[:-1]], int(n.sum())

        self.cell_off, self.cell_nb = offsets(cell_res)
        self.bulk_off, self.bulk_nb = offsets(bulk_res)

    def chrom_codes(self, names: Iterable[str]) -> np.ndarray:
        return np.array([self.index.get(str(n), -1) for n in names], dtype=np.int64)

    def keys(self, c1, p1, c2, p2):
        """(within-cell keys at cell_res, bulk keys at bulk_res) of contacts with kept chromosomes (c >= 0)."""
        ok = (c1 >= 0) & (c2 >= 0)
        c1, p1, c2, p2 = c1[ok], np.asarray(p1)[ok].astype(np.int64), c2[ok], np.asarray(p2)[ok].astype(np.int64)
        out = []
        for off, nb, res in ((self.cell_off, self.cell_nb, self.cell_res), (self.bulk_off, self.bulk_nb, self.bulk_res)):
            g1, g2 = off[c1] + p1 // res, off[c2] + p2 // res
            out.append(np.minimum(g1, g2) * nb + np.maximum(g1, g2))
        return out[0], out[1]


class ContactBinner:
    """Bin contacts of many cells into per-cell maps (``cell_res``) and one bulk map (``bulk_res``).

    ``cells``: the cell names (scool names; order does not matter).  Call :meth:`add` with blocks of contacts,
    then :meth:`write_scool` / :meth:`write_mcool`."""

    def __init__(self, sizes: Dict[str, int], cells: Sequence[str], workdir: Path, *, cell_res: int = 1_000_000,
                 bulk_res: int = 50_000, n_cell_buckets: int = 64, n_bulk_buckets: int = 64, bulk: bool = True,
                 min_cis: int = 0):
        self.sizes = dict(sizes)
        self.chroms = list(sizes)
        self.min_cis = int(min_cis)
        self.cells = sorted(str(c) for c in cells)        # scool order: bucket b holds a run of sorted names
        self.cell_index = pd.Index(self.cells)
        self.cell_res, self.bulk_res = cell_res, bulk_res
        self.workdir = Path(workdir)
        if self.workdir.exists():
            shutil.rmtree(self.workdir)
        self.workdir.mkdir(parents=True)

        def offsets(res):
            n = np.array([-(-self.sizes[c] // res) for c in self.chroms], dtype=np.int64)
            return np.r_[0, np.cumsum(n)[:-1]], int(n.sum())

        self.cell_off, self.cell_nb = offsets(cell_res)
        self.bulk_off, self.bulk_nb = offsets(bulk_res)
        self.n_cell_buckets = max(1, min(n_cell_buckets, len(self.cells)))
        self.cellb = _Buckets(self.workdir, self.n_cell_buckets, "cell")
        self.bulkb = _Buckets(self.workdir, n_bulk_buckets, "bulk") if bulk else None
        self.n_in = self.n_kept = 0
        self.per_cell = np.zeros(len(self.cells), np.int64)

    def chrom_codes(self, names: Iterable[str]) -> np.ndarray:
        """Chromosome index of each name (-1: not kept)."""
        idx = {c: i for i, c in enumerate(self.chroms)}
        return np.array([idx.get(str(n), -1) for n in names], dtype=np.int64)

    def cell_codes(self, names: Iterable[str]) -> np.ndarray:
        """Cell index of each name in the binner's (sorted) order (-1: not a cell)."""
        return self.cell_index.get_indexer(pd.Index([str(n) for n in names]))

    def add(self, cell: np.ndarray, c1: np.ndarray, p1: np.ndarray, c2: np.ndarray, p2: np.ndarray) -> None:
        """One block: ``cell`` = cell index (from :meth:`cell_codes`), ``c1`` / ``c2`` = chromosome index (from
        :meth:`chrom_codes`), ``p1`` / ``p2`` = positions.  Rows with -1 are dropped, and cis pairs closer than
        ``min_cis`` bp (ligation products of one fragment) when the binner was made with one."""
        self.n_in += len(cell)
        ok = (cell >= 0) & (c1 >= 0) & (c2 >= 0)
        if self.min_cis:
            ok &= (c1 != c2) | (np.abs(np.asarray(p2, np.int64) - np.asarray(p1, np.int64)) >= self.min_cis)
        cell, c1, p1, c2, p2 = cell[ok], c1[ok], p1[ok].astype(np.int64), c2[ok], p2[ok].astype(np.int64)
        self.n_kept += len(cell)
        self.per_cell += np.bincount(cell, minlength=len(self.cells))
        g1 = self.cell_off[c1] + p1 // self.cell_res
        g2 = self.cell_off[c2] + p2 // self.cell_res
        lo, hi = np.minimum(g1, g2), np.maximum(g1, g2)
        nb = self.cell_nb
        self.cellb.add(cell * self.n_cell_buckets // len(self.cells), cell * nb * nb + lo * nb + hi)
        if self.bulkb is not None:
            g1 = self.bulk_off[c1] + p1 // self.bulk_res
            g2 = self.bulk_off[c2] + p2 // self.bulk_res
            lo, hi = np.minimum(g1, g2), np.maximum(g1, g2)
            nb = self.bulk_nb
            self.bulkb.add(lo * self.bulkb.n // nb, lo * nb + hi)

    def add_frame(self, df: pd.DataFrame, *, cell="cell", chr1="chr1", pos1="pos1", chr2="chr2", pos2="pos2",
                  cell_index: Optional[np.ndarray] = None) -> None:
        """One block from :func:`stream_pairs` (categorical chromosome / barcode columns).  ``cell_index``: the
        cell index of every row instead of a ``cell`` column (a per-cell file)."""
        def codes(col, lookup):
            v = df[col]
            if isinstance(v.dtype, pd.CategoricalDtype):
                table = lookup(v.cat.categories)
                c = v.cat.codes.to_numpy()
                return np.where(c >= 0, table[np.maximum(c, 0)], -1)
            return lookup(v.astype(str).to_numpy())

        cells = cell_index if cell_index is not None else codes(cell, self.cell_codes)
        self.add(np.asarray(cells, np.int64), codes(chr1, self.chrom_codes), df[pos1].to_numpy(),
                 codes(chr2, self.chrom_codes), df[pos2].to_numpy())

    def add_keys(self, cell: int, cell_keys: np.ndarray, bulk_keys: np.ndarray, n_in: int = 0) -> None:
        """One cell's contacts as keys from :meth:`KeyMaker.keys` (a worker process binned them)."""
        nb = self.cell_nb
        self.n_in += n_in or len(cell_keys)
        self.n_kept += len(cell_keys)
        self.per_cell[cell] += len(cell_keys)
        self.cellb.add(np.full(len(cell_keys), cell * self.n_cell_buckets // len(self.cells)), cell * nb * nb + cell_keys)
        if self.bulkb is not None:
            self.bulkb.add((bulk_keys // self.bulk_nb) * self.bulkb.n // self.bulk_nb, bulk_keys)

    def keymaker(self) -> KeyMaker:
        return KeyMaker(self.sizes, self.cell_res, self.bulk_res)

    def close(self) -> None:
        self.cellb.close()
        if self.bulkb is not None:
            self.bulkb.close()

    # -- writers ---------------------------------------------------------------------------------------------

    def write_scool(self, path: Path, *, min_contacts: int = 1) -> List[str]:
        """The per-cell maps as a ``.scool`` (cells with at least ``min_contacts`` contacts); returns the names."""
        import cooler

        binner = self
        nb = self.cell_nb
        names = [c for i, c in enumerate(self.cells) if self.per_cell[i] >= min_contacts]

        class Lazy(dict):        # create_scool asks for the cells in sorted order: one bucket at a time
            cache = {"b": None}

            def __getitem__(self, name):
                ci = binner.cell_index.get_loc(name)
                b = ci * binner.n_cell_buckets // len(binner.cells)
                if self.cache["b"] != b:
                    keys, counts = binner.cellb.counts(b)
                    cell = keys // (nb * nb)
                    self.cache.update(b=b, keys=keys, counts=counts, cell=cell)
                c = self.cache
                lo, hi = np.searchsorted(c["cell"], [ci, ci + 1])
                k = c["keys"][lo:hi] % (nb * nb)
                return pd.DataFrame({"bin1_id": k // nb, "bin2_id": k % nb, "count": c["counts"][lo:hi]})

        cells = Lazy({n: None for n in names})
        path = Path(path)
        if path.exists():
            path.unlink()
        cooler.create_scool(str(path), bin_table(self.sizes, self.cell_res), cells, ordered=True)
        return names

    def write_mcool(self, path: Path, resolutions: Sequence[int] = (50_000, 100_000, 250_000, 500_000, 1_000_000),
                    *, balance: bool = True) -> Path:
        """The bulk map as a multi-resolution ``.mcool`` (base ``bulk_res``); the resolutions from
        :data:`BALANCE_MIN_RES` up are ICE-balanced unless ``balance=False`` (at 50 kb ICE over 1e9 pixels takes
        hours; the browser shows counts where a resolution has no weights)."""
        import cooler

        nb = self.bulk_nb

        def chunks():
            for b in range(self.bulkb.n):
                keys, counts = self.bulkb.counts(b)
                if len(keys):
                    yield pd.DataFrame({"bin1_id": keys // nb, "bin2_id": keys % nb, "count": counts})

        path = Path(path)
        base = path.with_suffix(".base.cool")
        cooler.create_cooler(str(base), bin_table(self.sizes, self.bulk_res), chunks(), ordered=True)
        res = sorted({int(r) for r in resolutions if r >= self.bulk_res and r % self.bulk_res == 0})
        if path.exists():
            path.unlink()
        cooler.zoomify_cooler(str(base), str(path), res, chunksize=10_000_000)
        base.unlink()
        if balance:
            balance_mcool(path)
        return path

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


BALANCE_MIN_RES = 250_000


def balance_mcool(path: Path, min_res: int = BALANCE_MIN_RES) -> List[int]:
    """ICE weights for the resolutions of an ``.mcool`` from ``min_res`` up (missing ones only)."""
    import cooler

    done = []
    for uri in cooler.fileops.list_coolers(str(path)):
        r = int(uri.rstrip("/").rsplit("/", 1)[-1])
        c = cooler.Cooler(f"{path}::{uri}")
        if r >= min_res and "weight" not in c.bins().columns:
            cooler.balance_cooler(c, store=True, ignore_diags=2, min_nnz=10, mad_max=5, max_iters=500)
            done.append(r)
    return done


# -- RNA -----------------------------------------------------------------------------------------------------

def rna_h5ad(counts, cells: pd.Index, genes: pd.DataFrame, path: Path, *, modality: str = "RNA",
             description: str = "raw UMI counts (X) of every gene, one row per cell of cells") -> Dict[str, str]:
    """Write cells × genes counts (sparse) as the store's linked AnnData; returns the ``uns['linked_anndata']``
    record (path relative to the store's folder)."""
    import anndata as ad
    import scipy.sparse as sp

    x = sp.csr_matrix(counts, dtype=np.float32)
    var = genes.copy()
    var.index = pd.Index(var.index.astype(str), name="gene")
    if not var.index.is_unique:
        var.index = pd.Index(_dedupe(var.index), name="gene")
    obs = pd.DataFrame(index=pd.Index(cells.astype(str), name="cell_id"))
    adata = ad.AnnData(X=x, obs=obs, var=var)
    adata.write_h5ad(path, compression="gzip")
    return {"path": Path(path).name, "format": "h5ad", "modality": modality, "description": description,
            "cell_axis": "obs index = cells index", "var_axis": "var index = gene"}


def _dedupe(names: Sequence[str]) -> List[str]:
    seen: Dict[str, int] = {}
    out = []
    for n in names:
        k = seen.get(n, 0)
        out.append(n if k == 0 else f"{n}-{k}")
        seen[n] = k + 1
    return out


def hvg_zscores(counts, n_hvg: int = 2000, min_frac: float = 0.01) -> tuple:
    """(cells × n_hvg z-scored log1p CP10k matrix, chosen gene indices): the input of the RNA PCA / UMAP."""
    import scipy.sparse as sp

    x = sp.csr_matrix(counts, dtype=np.float64)
    tot = np.asarray(x.sum(1)).ravel()
    xn = sp.diags(1e4 / np.maximum(tot, 1)) @ x
    xn.data = np.log1p(xn.data)
    frac = np.asarray((x > 0).mean(0)).ravel()
    mean = np.asarray(xn.mean(0)).ravel()
    var = np.asarray(xn.multiply(xn).mean(0)).ravel() - mean ** 2
    disp = np.where(frac >= min_frac, var / np.maximum(mean, 1e-9), -np.inf)
    hvg = np.argsort(-disp)[:n_hvg]
    hvg = hvg[np.isfinite(disp[hvg])]
    z = xn[:, hvg].toarray()
    z = (z - z.mean(0)) / np.where(z.std(0) > 0, z.std(0), 1)
    return np.clip(z, -10, 10).astype(np.float32), hvg


def empty_spots() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                         [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
