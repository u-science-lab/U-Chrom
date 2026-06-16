"""Shared pytest configuration for the test suite.

Guarantees the repository root is on ``sys.path`` so tests can import both the
application package (``webapp.backend...``) and sibling test helpers
(``from tests._agent_loop_harness import ...``) regardless of how pytest is
invoked (``pytest`` console script vs ``python -m pytest``) or from which
working directory. conftest.py is auto-loaded by pytest before any test module
is imported, so the path is in place before collection.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Unit tests should not leave debug JSONL traces in the repository by default.
# Conversation logger tests opt back in explicitly.
os.environ.setdefault("UCHROM_CONVERSATION_LOG", "0")


def _ensure_rich_multicell_fixture():
    """Auto-create the gitignored ``rich_multicell.h5cd`` fixture if missing.

    Several webapp tests need a multi-cell / multi-chrom dataset that the
    single-cell ``synthetic_chr1_tiny.h5cd`` cannot provide (per-cell UMAP,
    cell-coloured 3D, /api/cells, /api/dataset_info). The fixture is generated
    deterministically by ``example-data/make_rich_multicell.py`` and gitignored
    like the other generated ``.h5cd`` files, so we (re)build it on demand here
    — mirroring how ``synthetic_chr1_tiny.h5cd`` is auto-created. Best-effort:
    the dependent tests also ``skipif`` the file is absent, so a build failure
    (e.g. a missing optional dep) skips rather than errors the whole suite.
    """
    target = os.path.join(_REPO_ROOT, "example-data", "rich_multicell.h5cd")
    if os.path.exists(target):
        return
    try:
        import importlib.util
        gen = os.path.join(_REPO_ROOT, "example-data", "make_rich_multicell.py")
        spec = importlib.util.spec_from_file_location("_make_rich_multicell", gen)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        mod.build_rich_multicell(target)
    except Exception:
        pass  # dependent tests skipif-guard on the file's absence


_ensure_rich_multicell_fixture()
