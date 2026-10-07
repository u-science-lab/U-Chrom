"""Tests for uchrom.emb.higashi: the FastHigashi/Higashi wrapper and helpers.

Design:

- FastHigashi itself is a heavy optional dep (torch + pinned scipy).  The
  wrapper is built for *dependency injection*: the caller (or our lazy
  default) supplies a factory that produces something with the same
  surface as ``fasthigashi.FastHigashi_Wrapper.FastHigashi``.  This lets
  us TDD the orchestration/alignment logic without the real package.

- We only test the behaviour that is ours: row-order alignment into
  ``cd.cells``, ChromData mutation (``cellm`` + ``uns``), pre-flight
  validation, and error messages.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _make_cd(cell_names):
    """Minimal ChromData: 1 spot per cell, with cells.cell_name."""
    from chromdata.cdata import ChromData

    n = len(cell_names)
    coords = np.zeros((n, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * n,
        "start": np.arange(n) * 1_000_000,
        "end":   np.arange(n) * 1_000_000 + 1_000_000,
        "trace_id": [f"t{i}" for i in range(n)],
        "cell_id": list(cell_names),
    })
    cells = pd.DataFrame({"cell_name": list(cell_names)})
    return ChromData(coords=coords, spots=spots, cells=cells, validate=True)


# ---------------------------------------------------------------------------
# align_embedding
# ---------------------------------------------------------------------------

def test_align_embedding_reorders_to_cd_cells():
    from uchrom.emb.higashi import align_embedding

    emb = np.array([[1.0, 1.1],
                    [2.0, 2.1],
                    [3.0, 3.1]])
    emb_order = ["c2", "c3", "c1"]          # FastHigashi internal order
    cd_cells = pd.DataFrame({"cell_name": ["c1", "c2", "c3"]})

    out = align_embedding(emb, emb_order, cd_cells, cell_id_col="cell_name")

    assert out.shape == (3, 2)
    np.testing.assert_allclose(out[0], [3.0, 3.1])   # c1
    np.testing.assert_allclose(out[1], [1.0, 1.1])   # c2
    np.testing.assert_allclose(out[2], [2.0, 2.1])   # c3


def test_align_embedding_missing_cell_raises():
    from uchrom.emb.higashi import align_embedding

    emb = np.zeros((2, 4))
    emb_order = ["c1", "c2"]
    cd_cells = pd.DataFrame({"cell_name": ["c1", "c3"]})   # c3 wasn't trained

    with pytest.raises(ValueError, match="c3"):
        align_embedding(emb, emb_order, cd_cells, cell_id_col="cell_name")


def test_align_embedding_extra_emb_rows_raises():
    from uchrom.emb.higashi import align_embedding

    emb = np.zeros((3, 4))
    emb_order = ["c1", "c2", "EXTRA"]
    cd_cells = pd.DataFrame({"cell_name": ["c1", "c2"]})

    with pytest.raises(ValueError, match="EXTRA"):
        align_embedding(emb, emb_order, cd_cells, cell_id_col="cell_name")


# ---------------------------------------------------------------------------
# run() pre-flight
# ---------------------------------------------------------------------------

def test_run_requires_cell_name_column(tmp_path):
    from chromdata.cdata import ChromData
    from uchrom.emb.higashi import run

    coords = np.zeros((2, 3))
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1"], "start": [0, 1_000_000],
        "end": [1_000_000, 2_000_000],
        "trace_id": ["t0", "t1"], "cell_id": ["c1", "c2"],
    })
    # cells present but lacks cell_name
    cd = ChromData(coords=coords, spots=spots,
                   cells=pd.DataFrame({"other": ["x", "y"]}))

    with pytest.raises(ValueError, match="cell_name"):
        run(cd, contacts_dir=tmp_path, wrapper_factory=lambda **_: None)


# ---------------------------------------------------------------------------
# run() happy path with an injected fake FastHigashi
# ---------------------------------------------------------------------------

class _FakeFastHigashi:
    """Mimics the real FastHigashi surface enough to drive ``run()``.

    Real contract (FastHigashi 0.1.1a0):
    - ``__init__(config_path, path2input_cache, path2result_dir, off_diag,
       filter, do_conv, do_rwr, do_col, no_col)`` — positional.
    - ``fast_process_data()``
    - ``prep_dataset(meta_only=False, batch_norm=True)``
    - ``run_model(dim1=0.6, rank=256, n_iter_parafac=1, ...)``
    - ``fetch_cell_embedding(final_dim, restore_order)`` →
      dict with keys ``embed_l2_norm`` etc.  When ``restore_order=True``
      rows align with the ``label_info`` order on disk.
    """

    def __init__(self, config_path, path2input_cache, path2result_dir,
                 off_diag, filter, do_conv, do_rwr, do_col, no_col):
        self.init_args = dict(
            config_path=config_path,
            path2input_cache=path2input_cache,
            path2result_dir=path2result_dir,
        )
        self.calls: list[str] = []
        # When restore_order=True, rows align to label_info (= cd.cells).
        self._n = 3
        self._d = 2
        self._emb_restored = np.array([[1.0, 1.5],
                                        [2.0, 2.5],
                                        [3.0, 3.5]])

    def fast_process_data(self):    self.calls.append("fast_process_data")
    def prep_dataset(self, meta_only=False, batch_norm=True):
        self.calls.append(f"prep_dataset:{batch_norm}")
    def run_model(self, dim1=0.6, rank=256, n_iter_parafac=1, **_):
        self.calls.append(f"run_model:rank={rank},dim1={dim1}")
    def fetch_cell_embedding(self, final_dim=None, restore_order=False):
        self.calls.append(f"fetch:final_dim={final_dim},restore={restore_order}")
        # Real FastHigashi returns a dict with embed_l2_norm etc.
        return {
            "embed_all":     self._emb_restored * 10,
            "embed_raw":     self._emb_restored,
            "embed_l2_norm": self._emb_restored / 5,
            "restore_order": restore_order,
        }


def test_run_writes_aligned_cellm_and_uns(tmp_path):
    from uchrom.emb.higashi import run
    from uchrom.io.contacts import write_label_info

    cd = _make_cd(["c1", "c2", "c3"])
    contacts_dir = tmp_path / "higashi_in"
    contacts_dir.mkdir()
    (contacts_dir / "config.JSON").write_text("{}")
    # label_info row order = cd.cells row order; restore_order=True
    # makes the embedding match this on output.
    write_label_info(cd.cells, contacts_dir / "label_info.pickle")

    instances: list[_FakeFastHigashi] = []
    def factory(*args, **kwargs):
        inst = _FakeFastHigashi(*args, **kwargs)
        instances.append(inst)
        return inst

    out = run(
        cd,
        contacts_dir=contacts_dir,
        which="fast",
        rank=8,
        embed_key="higashi",
        wrapper_factory=factory,
    )

    # returns the same ChromData, mutated in place
    assert out is cd

    # cellm populated and row-aligned to cd.cells order
    assert "higashi" in cd.cellm
    emb = cd.cellm["higashi"]
    assert emb.shape == (3, 2)
    np.testing.assert_allclose(emb[0], [1.0 / 5, 1.5 / 5])   # c1 (l2_norm picked)
    np.testing.assert_allclose(emb[1], [2.0 / 5, 2.5 / 5])   # c2
    np.testing.assert_allclose(emb[2], [3.0 / 5, 3.5 / 5])   # c3

    # uns carries provenance
    assert "higashi" in cd.uns
    provenance = cd.uns["higashi"]
    assert provenance["method"] == "fast"
    assert provenance["rank"] == 8
    assert Path(provenance["config_path"]) == contacts_dir / "config.JSON"

    # pipeline sequence was invoked
    assert len(instances) == 1
    inst = instances[0]
    assert inst.calls[0] == "fast_process_data"
    assert inst.calls[1].startswith("prep_dataset")
    assert inst.calls[2].startswith("run_model")
    assert inst.calls[3].startswith("fetch")
    # we explicitly request restore_order=True so the rows align to label_info
    assert "restore=True" in inst.calls[3]


def test_run_passes_rank_to_run_model(tmp_path):
    from uchrom.emb.higashi import run
    from uchrom.io.contacts import write_label_info

    cd = _make_cd(["c1", "c2", "c3"])
    contacts_dir = tmp_path / "higashi_in"
    contacts_dir.mkdir()
    (contacts_dir / "config.JSON").write_text("{}")
    write_label_info(cd.cells, contacts_dir / "label_info.pickle")

    captured: list[_FakeFastHigashi] = []
    def factory(*a, **kw):
        inst = _FakeFastHigashi(*a, **kw); captured.append(inst); return inst

    run(cd, contacts_dir=contacts_dir, rank=64, wrapper_factory=factory)
    rm = [c for c in captured[0].calls if c.startswith("run_model")][0]
    assert "rank=64" in rm


def test_run_raises_import_error_when_fasthigashi_missing(tmp_path):
    """With no wrapper_factory and no fasthigashi installed, error is actionable."""
    from uchrom.emb.higashi import run

    cd = _make_cd(["c1", "c2"])
    contacts_dir = tmp_path / "higashi_in"
    contacts_dir.mkdir()
    (contacts_dir / "config.JSON").write_text("{}")
    from uchrom.io.contacts import write_label_info
    write_label_info(cd.cells, contacts_dir / "label_info.pickle")

    # if fasthigashi happens to be importable we skip — we only care
    # about the guard firing when it's absent
    try:
        import fasthigashi   # noqa: F401
        pytest.skip("fasthigashi is installed; cannot test the ImportError guard")
    except ImportError:
        pass

    with pytest.raises(ImportError, match="u-chrom\\[emb\\]"):
        run(cd, contacts_dir=contacts_dir)


def test_run_rejects_missing_config(tmp_path):
    from uchrom.emb.higashi import run

    cd = _make_cd(["c1"])
    with pytest.raises(FileNotFoundError, match="config.JSON"):
        run(cd, contacts_dir=tmp_path, wrapper_factory=lambda **_: None)
