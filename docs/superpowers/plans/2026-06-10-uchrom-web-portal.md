# U-Chrom Web Portal v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个染色质 3D "分析就绪" 数据集门户：离线 pipeline 从 `.h5cd` 提取元数据并预渲染 notebook，FastAPI 只读后端提供 REST，Next.js SSR 前端展示列表页 + 详情页。

**Architecture:** Monorepo 三件套（`data-portal/{backend,pipeline,frontend}`）。Pipeline 离线把 `.h5cd` + notebook 嚼成 SQLite 行 + 静态 HTML；后端无状态只读这些产物；前端 SSR 渲染。数据文件外部托管（Zenodo），后端运行时不碰 `.h5cd`。

**Tech Stack:** Python 3.11 (FastAPI + SQLAlchemy + SQLite + nbconvert + PyYAML), `uchrom` 包 (ChromData), pytest；Next.js 15 (App Router, SSR) + TypeScript + Tailwind + shadcn/ui。

**关键环境事实（实现者必读）:**
- Python 解释器固定用仓库根的 venv：`/Volumes/sandisk/Coding/U-Chrom/.venv/bin/python`（下文记为 `$PY`）。该 venv 已有 fastapi/pyyaml/pytest/numpy/uchrom，**缺** sqlalchemy/nbconvert/uvicorn（Task 0 安装）。
- 所有命令在 worktree 根 `/Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal` 下执行。
- `ChromData` 真实 API（已核对）：`ChromData.read(path)` → 实例；属性 `.n_cells/.n_traces/.n_spots`（int）、`.spots`（DataFrame，列含 `chrom,start,end,trace_id`，可能有 `cell_id`）、`.cells`（DataFrame，可能含 `cell_type`，可能为空）、`.tracks`（DataFrame 或 `None`）、`.uns`（dict，可能含 `genome_assembly`/`xyz_unit`/`description`）、`.chroms`（list[str]）。
- 提取逻辑**必须优雅降级**：`tracks` 为 None → `n_markers=0`；`cells` 空或无 `cell_type` → `cell_types={}`；`uns` 缺键 → 用默认值。

---

## File Structure

```
data-portal/
├── backend/
│   ├── __init__.py
│   ├── db.py              SQLite 引擎 + Session + Base
│   ├── models.py          SQLAlchemy Dataset 表
│   ├── schemas.py         Pydantic DatasetSummary / DatasetDetail / FileEntry
│   ├── main.py            FastAPI app + CORS + StaticFiles + 路由注册
│   └── api/
│       ├── __init__.py
│       └── datasets.py    GET /api/datasets, /{id}, /{id}/notebook, /facets, /health
├── pipeline/
│   ├── __init__.py
│   ├── extract.py         extract_stats(ChromData) -> dict（核心 uchrom 逻辑）
│   ├── catalog.py         load_catalog(yaml_path) -> CatalogEntry + QC
│   ├── render_nb.py       render_notebook(nb_path, out_html) -> bool
│   ├── ingest.py          CLI: ingest(yaml_path) UPSERT 一行 + 产物
│   └── catalog/
│       └── mesc_sox2_test.yaml   首个数据集声明（用 in-repo fixture）
├── frontend/
│   ├── package.json, tsconfig.json, next.config.js, tailwind.config.ts
│   └── src/
│       ├── lib/api.ts     fetch 封装 + 类型
│       ├── app/layout.tsx          全局壳
│       ├── app/page.tsx            列表页
│       └── app/datasets/[id]/page.tsx  详情页（3 tab）
├── data/                  生成物（gitignore）：portal.db, notebooks/, thumbnails/
├── tests/
│   ├── __init__.py
│   ├── conftest.py        共享 fixture（临时 db、样本 ChromData 路径）
│   ├── pipeline/
│   │   ├── test_extract.py
│   │   ├── test_catalog.py
│   │   ├── test_render_nb.py
│   │   └── test_ingest.py
│   └── backend/
│       ├── test_api_datasets.py
│       └── test_security.py
├── requirements.txt       portal 专属依赖
└── README.md
```

## Task 0: Scaffold + dependencies + test fixture

**Files:**
- Create: `data-portal/requirements.txt`
- Create: `data-portal/.gitignore`
- Create: `data-portal/backend/__init__.py`, `data-portal/pipeline/__init__.py`, `data-portal/tests/__init__.py`, `data-portal/backend/api/__init__.py`, `data-portal/tests/pipeline/__init__.py`, `data-portal/tests/backend/__init__.py` (all empty)
- Create: `data-portal/tests/conftest.py`
- Copy: `test_20cells_chr21.h5cd` fixture into worktree

- [ ] **Step 1: Create directory tree + empty package files**

```bash
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal
mkdir -p data-portal/backend/api data-portal/pipeline/catalog \
         data-portal/tests/pipeline data-portal/tests/backend \
         data-portal/data/notebooks data-portal/data/thumbnails
touch data-portal/backend/__init__.py data-portal/backend/api/__init__.py \
      data-portal/pipeline/__init__.py data-portal/tests/__init__.py \
      data-portal/tests/pipeline/__init__.py data-portal/tests/backend/__init__.py
```

- [ ] **Step 2: Write `data-portal/requirements.txt`**

```
fastapi>=0.110
uvicorn[standard]>=0.27
sqlalchemy>=2.0
pydantic>=2.0
pyyaml>=6.0
nbconvert>=7.0
```

- [ ] **Step 3: Write `data-portal/.gitignore`**

```
data/portal.db
data/notebooks/
data/thumbnails/
frontend/node_modules/
frontend/.next/
__pycache__/
*.pyc
```

- [ ] **Step 4: Install missing Python deps into the repo venv**

Run:
```bash
/Volumes/sandisk/Coding/U-Chrom/.venv/bin/pip install sqlalchemy "uvicorn[standard]" nbconvert
```
Expected: installs successfully (fastapi/pyyaml/pytest already present).

- [ ] **Step 5: Copy the rich test fixture into this worktree's example-data**

The 66KB `test_20cells_chr21.h5cd` has `cell_type` + `uns` (assembly/unit) — ideal for exercising extraction. It currently lives only in the other working dir.

Run:
```bash
cp /Users/bakezq/Coding/U-Chrom/example-data/test_20cells_chr21.h5cd \
   /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal/example-data/test_20cells_chr21.h5cd
ls -la example-data/test_20cells_chr21.h5cd
```
Expected: file present, ~66KB.

- [ ] **Step 6: Write `data-portal/tests/conftest.py`**

```python
import sys
from pathlib import Path
import pytest

# Make `backend` and `pipeline` importable as top-level packages.
DATA_PORTAL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DATA_PORTAL))

# Repo root (worktree) — for locating example-data fixtures.
REPO_ROOT = DATA_PORTAL.parent


@pytest.fixture
def rich_h5cd() -> str:
    """A ChromData fixture with cells (cell_type) and uns metadata."""
    p = REPO_ROOT / "example-data" / "test_20cells_chr21.h5cd"
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return str(p)


@pytest.fixture
def minimal_h5cd() -> str:
    """A minimal ChromData fixture: no cells, no tracks, no uns."""
    p = REPO_ROOT / "example-data" / "mESC_Sox2_5cells_wnan.h5cd"
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return str(p)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """A temporary SQLite DB path, isolated per test."""
    db_path = tmp_path / "portal.db"
    monkeypatch.setenv("PORTAL_DB_PATH", str(db_path))
    return str(db_path)
```

- [ ] **Step 7: Verify pytest collects (no tests yet, but imports work)**

Run:
```bash
cd data-portal && /Volumes/sandisk/Coding/U-Chrom/.venv/bin/python -m pytest tests/ -v
```
Expected: "no tests ran" (collection succeeds, conftest imports cleanly).

- [ ] **Step 8: Commit**

```bash
git add data-portal/ example-data/test_20cells_chr21.h5cd
git commit -m "chore(portal): scaffold data-portal monorepo + test fixture"
```

---

## Task 1: Pipeline — stats extraction from ChromData

**Files:**
- Create: `data-portal/pipeline/extract.py`
- Test: `data-portal/tests/pipeline/test_extract.py`

This is the core uchrom-touching logic. It must degrade gracefully on minimal data.

- [ ] **Step 1: Write the failing test**

`data-portal/tests/pipeline/test_extract.py`:
```python
from uchrom.core.cdata import ChromData
from pipeline.extract import extract_stats


def test_extract_rich(rich_h5cd):
    cd = ChromData.read(rich_h5cd)
    stats = extract_stats(cd)
    assert stats["n_cells"] == 20
    assert stats["n_traces"] == 20
    assert stats["n_spots"] == 1000
    # tracks is None in this fixture -> 0 markers
    assert stats["n_markers"] == 0
    # cells has cell_type column -> non-empty mapping summing to n_cells
    assert isinstance(stats["cell_types"], dict)
    assert sum(stats["cell_types"].values()) == 20
    assert stats["assembly"] == "hg38"
    assert stats["xyz_unit"] == "nm"
    assert stats["genome_coverage"] == "chr21"


def test_extract_minimal(minimal_h5cd):
    cd = ChromData.read(minimal_h5cd)
    stats = extract_stats(cd)
    assert stats["n_cells"] == 0
    assert stats["n_traces"] == 5
    assert stats["n_markers"] == 0
    assert stats["cell_types"] == {}
    # missing uns -> safe defaults (not crash)
    assert stats["assembly"] in ("", None) or isinstance(stats["assembly"], str)
    assert stats["xyz_unit"] in ("", None) or isinstance(stats["xyz_unit"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-portal && $PY -m pytest tests/pipeline/test_extract.py -v` (where `$PY=/Volumes/sandisk/Coding/U-Chrom/.venv/bin/python`)
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.extract'`.

- [ ] **Step 3: Write `data-portal/pipeline/extract.py`**

```python
"""Extract portal display statistics from a ChromData object.

Pure function over an already-loaded ChromData. Degrades gracefully when
optional layers (cells, tracks, uns) are absent — minimal fixtures have
none of them, full datasets (Takei 2025) have all.
"""
from __future__ import annotations

from typing import Any


def extract_stats(cd: Any) -> dict:
    # Marker count = number of epigenomic track columns (tracks may be None).
    n_markers = 0 if cd.tracks is None else int(cd.tracks.shape[1])

    # Cell-type distribution, if a cell_type column exists.
    cell_types: dict[str, int] = {}
    cells = cd.cells
    if cells is not None and "cell_type" in getattr(cells, "columns", []):
        counts = cells["cell_type"].value_counts()
        cell_types = {str(k): int(v) for k, v in counts.items()}

    # Genome coverage: list of chromosomes joined, or "genome-wide" if many.
    chroms = list(cd.chroms)
    if len(chroms) == 0:
        genome_coverage = ""
    elif len(chroms) >= 20:
        genome_coverage = "genome-wide"
    else:
        genome_coverage = ",".join(chroms)

    uns = cd.uns or {}
    return {
        "n_cells": int(cd.n_cells),
        "n_traces": int(cd.n_traces),
        "n_spots": int(cd.n_spots),
        "n_markers": n_markers,
        "cell_types": cell_types,
        "genome_coverage": genome_coverage,
        "assembly": str(uns.get("genome_assembly", "")),
        "xyz_unit": str(uns.get("xyz_unit", "")),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-portal && $PY -m pytest tests/pipeline/test_extract.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add data-portal/pipeline/extract.py data-portal/tests/pipeline/test_extract.py
git commit -m "feat(portal): extract display stats from ChromData"
```

## Task 2: Pipeline — catalog YAML loading + QC

**Files:**
- Create: `data-portal/pipeline/catalog.py`
- Create: `data-portal/pipeline/catalog/mesc_sox2_test.yaml`
- Test: `data-portal/tests/pipeline/test_catalog.py`

`load_catalog` parses a YAML declaration, validates required fields, and resolves `~`/relative paths. Bad catalogs raise `CatalogError` so `ingest` aborts before writing the DB.

- [ ] **Step 1: Write the first dataset's catalog YAML**

`data-portal/pipeline/catalog/mesc_sox2_test.yaml`:
```yaml
id: mesc_sox2_test
title: "mESC Sox2 locus DNA FISH (test fixture)"
description: "A 5-cell test slice of mouse ESC Sox2-locus chromatin tracing, used to exercise the portal pipeline end-to-end."
organism: "Mus musculus"
assembly: "mm10"
technology: "DNA FISH"
doi: ""
citation: "U-Chrom example data"
source_h5cd: "../example-data/mESC_Sox2_5cells_wnan.h5cd"
notebook: "../tutorials/takei2025_walkthrough.ipynb"
files:
  - label: "5-cell slice (.h5cd)"
    url: "https://example.org/placeholder/mESC_Sox2_5cells_wnan.h5cd"
    size_mb: 1
    format: h5cd
analyzer_url: null
```

Note: `source_h5cd` / `notebook` are relative to the catalog YAML's directory's grandparent (the worktree root). `load_catalog` resolves them; see Step 3.

- [ ] **Step 2: Write the failing test**

`data-portal/tests/pipeline/test_catalog.py`:
```python
import pytest
from pipeline.catalog import load_catalog, CatalogError


def test_load_valid_catalog():
    # Resolve the real catalog shipped with the repo.
    from pathlib import Path
    yaml_path = Path(__file__).resolve().parents[2] / "pipeline" / "catalog" / "mesc_sox2_test.yaml"
    entry = load_catalog(str(yaml_path))
    assert entry.id == "mesc_sox2_test"
    assert entry.organism == "Mus musculus"
    assert entry.files[0]["format"] == "h5cd"
    # source_h5cd resolved to an existing absolute path
    assert entry.source_h5cd_path.exists()
    assert entry.analyzer_url is None


def test_missing_required_field_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("title: no id here\n")
    with pytest.raises(CatalogError):
        load_catalog(str(bad))


def test_bad_slug_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: 'Has Spaces!'\ntitle: x\nsource_h5cd: y\n")
    with pytest.raises(CatalogError):
        load_catalog(str(bad))
```

- [ ] **Step 3: Write `data-portal/pipeline/catalog.py`**

```python
"""Load + validate a dataset catalog YAML declaration."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

SLUG_RE = re.compile(r"^[a-z0-9_]+$")
REQUIRED = ("id", "title", "source_h5cd")


class CatalogError(Exception):
    """Raised when a catalog YAML is invalid."""


@dataclass
class CatalogEntry:
    id: str
    title: str
    source_h5cd_path: Path
    description: str = ""
    organism: str = ""
    assembly: str = ""
    technology: str = ""
    doi: str = ""
    citation: str = ""
    notebook_path: Optional[Path] = None
    files: list[dict] = field(default_factory=list)
    analyzer_url: Optional[str] = None


def load_catalog(yaml_path: str) -> CatalogEntry:
    path = Path(yaml_path).expanduser().resolve()
    if not path.exists():
        raise CatalogError(f"catalog not found: {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}

    for k in REQUIRED:
        if not raw.get(k):
            raise CatalogError(f"missing required field '{k}' in {path.name}")

    slug = str(raw["id"])
    if not SLUG_RE.match(slug):
        raise CatalogError(f"id must match [a-z0-9_]+, got {slug!r}")

    # Paths in the YAML are relative to the YAML file's own directory.
    base = path.parent

    def resolve(rel: str) -> Path:
        p = Path(rel).expanduser()
        return p if p.is_absolute() else (base / p).resolve()

    source = resolve(str(raw["source_h5cd"]))
    notebook = resolve(str(raw["notebook"])) if raw.get("notebook") else None

    return CatalogEntry(
        id=slug,
        title=str(raw["title"]),
        source_h5cd_path=source,
        description=str(raw.get("description", "")),
        organism=str(raw.get("organism", "")),
        assembly=str(raw.get("assembly", "")),
        technology=str(raw.get("technology", "")),
        doi=str(raw.get("doi", "")),
        citation=str(raw.get("citation", "")),
        notebook_path=notebook,
        files=list(raw.get("files") or []),
        analyzer_url=raw.get("analyzer_url"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-portal && $PY -m pytest tests/pipeline/test_catalog.py -v`
Expected: PASS (3 passed). Note the catalog's `source_h5cd: "../example-data/..."` resolves relative to `pipeline/catalog/`, i.e. `pipeline/example-data/` — **this will fail** unless the path is correct. Fix: the YAML path must be `../../example-data/mESC_Sox2_5cells_wnan.h5cd` (catalog dir is `pipeline/catalog/`, worktree root is two levels up). Update the YAML in Step 1 accordingly and re-run.

- [ ] **Step 5: Correct the relative paths in the YAML**

Edit `data-portal/pipeline/catalog/mesc_sox2_test.yaml`:
```yaml
source_h5cd: "../../../example-data/mESC_Sox2_5cells_wnan.h5cd"
notebook: "../../../tutorials/takei2025_walkthrough.ipynb"
```
Reasoning: catalog YAML is at `data-portal/pipeline/catalog/`. To reach worktree-root `example-data/`, go up 3 levels (`catalog` → `pipeline` → `data-portal` → worktree root). Re-run Step 4 until `entry.source_h5cd_path.exists()` passes.

- [ ] **Step 6: Commit**

```bash
git add data-portal/pipeline/catalog.py data-portal/pipeline/catalog/mesc_sox2_test.yaml data-portal/tests/pipeline/test_catalog.py
git commit -m "feat(portal): load + validate catalog YAML declarations"
```

---

## Task 3: Pipeline — render notebook to HTML

**Files:**
- Create: `data-portal/pipeline/render_nb.py`
- Test: `data-portal/tests/pipeline/test_render_nb.py`

`render_notebook` uses nbconvert programmatically. Returns `True` on success, `False` (logged) on failure — never raises, so a bad notebook degrades gracefully.

- [ ] **Step 1: Write the failing test**

`data-portal/tests/pipeline/test_render_nb.py`:
```python
from pathlib import Path
from pipeline.render_nb import render_notebook


def test_render_real_notebook(tmp_path):
    nb = Path(__file__).resolve().parents[3] / "tutorials" / "takei2025_walkthrough.ipynb"
    if not nb.exists():
        import pytest
        pytest.skip("notebook fixture missing")
    out = tmp_path / "out.html"
    ok = render_notebook(str(nb), str(out))
    assert ok is True
    assert out.exists()
    assert out.stat().st_size > 1000
    assert "<html" in out.read_text(errors="ignore").lower()


def test_render_missing_notebook_returns_false(tmp_path):
    out = tmp_path / "out.html"
    ok = render_notebook(str(tmp_path / "nope.ipynb"), str(out))
    assert ok is False
    assert not out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-portal && $PY -m pytest tests/pipeline/test_render_nb.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.render_nb'`.

- [ ] **Step 3: Write `data-portal/pipeline/render_nb.py`**

```python
"""Render a Jupyter notebook to standalone HTML via nbconvert.

Never raises: returns True on success, False on any failure (caller logs
a warning and continues — a failed notebook must not abort ingest).
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def render_notebook(nb_path: str, out_html: str) -> bool:
    src = Path(nb_path)
    if not src.exists():
        logger.warning("notebook not found: %s", src)
        return False
    try:
        import nbformat
        from nbconvert import HTMLExporter

        nb = nbformat.read(str(src), as_version=4)
        exporter = HTMLExporter()
        exporter.exclude_input_prompt = True
        body, _ = exporter.from_notebook_node(nb)
        out = Path(out_html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("nbconvert failed for %s: %s", src, exc)
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-portal && $PY -m pytest tests/pipeline/test_render_nb.py -v`
Expected: PASS (2 passed). The real Takei notebook renders to >1KB HTML.

- [ ] **Step 5: Commit**

```bash
git add data-portal/pipeline/render_nb.py data-portal/tests/pipeline/test_render_nb.py
git commit -m "feat(portal): render notebook to HTML via nbconvert"
```

## Task 4: Backend — DB engine + Dataset model

**Files:**
- Create: `data-portal/backend/db.py`
- Create: `data-portal/backend/models.py`
- Test: `data-portal/tests/backend/test_models.py`

SQLAlchemy 2.0 declarative. DB path comes from `PORTAL_DB_PATH` env (default `data/portal.db`), so tests use a tmp DB.

- [ ] **Step 1: Write the failing test**

`data-portal/tests/backend/test_models.py`:
```python
from backend.db import make_engine, make_session, Base
from backend.models import Dataset


def test_create_and_query_dataset(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    Base.metadata.create_all(engine)
    Session = make_session(engine)
    with Session() as s:
        s.add(Dataset(
            id="ds1", title="Test DS", organism="Mus musculus",
            technology="DNA FISH", n_cells=20, n_traces=20, n_spots=1000,
            n_markers=0, cell_types={"A": 12, "B": 8},
            files=[{"label": "x", "url": "http://e/x", "size_mb": 1, "format": "h5cd"}],
            status="published",
        ))
        s.commit()
    with Session() as s:
        got = s.get(Dataset, "ds1")
        assert got.title == "Test DS"
        assert got.cell_types == {"A": 12, "B": 8}
        assert got.files[0]["url"] == "http://e/x"
        assert got.analyzer_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-portal && $PY -m pytest tests/backend/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.db'`.

- [ ] **Step 3: Write `data-portal/backend/db.py`**

```python
"""SQLite engine + session factory. DB path from PORTAL_DB_PATH env."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def default_db_path() -> str:
    env = os.getenv("PORTAL_DB_PATH")
    if env:
        return env
    # data/portal.db relative to the data-portal package root.
    root = Path(__file__).resolve().parent.parent
    return str(root / "data" / "portal.db")


def make_engine(db_path: str | None = None):
    path = db_path or default_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", future=True)


def make_session(engine):
    return sessionmaker(bind=engine, future=True)
```

- [ ] **Step 4: Write `data-portal/backend/models.py`**

```python
"""SQLAlchemy model for the datasets table."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    # identity / search
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(String, default="")
    organism: Mapped[str] = mapped_column(String, default="", index=True)
    assembly: Mapped[str] = mapped_column(String, default="")
    technology: Mapped[str] = mapped_column(String, default="", index=True)
    doi: Mapped[str] = mapped_column(String, default="")
    citation: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # stats
    n_cells: Mapped[int] = mapped_column(Integer, default=0)
    n_traces: Mapped[int] = mapped_column(Integer, default=0)
    n_spots: Mapped[int] = mapped_column(Integer, default=0)
    n_markers: Mapped[int] = mapped_column(Integer, default=0)
    cell_types: Mapped[dict] = mapped_column(JSON, default=dict)
    genome_coverage: Mapped[str] = mapped_column(String, default="")
    xyz_unit: Mapped[str] = mapped_column(String, default="")
    resolution: Mapped[dict] = mapped_column(JSON, default=dict)

    # external hosting + artifacts
    files: Mapped[list] = mapped_column(JSON, default=list)
    notebook_html_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    analyzer_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="published", index=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd data-portal && $PY -m pytest tests/backend/test_models.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add data-portal/backend/db.py data-portal/backend/models.py data-portal/tests/backend/test_models.py
git commit -m "feat(portal): SQLAlchemy Dataset model + engine"
```

---

## Task 5: Pipeline — ingest CLI (ties it together)

**Files:**
- Create: `data-portal/pipeline/ingest.py`
- Test: `data-portal/tests/pipeline/test_ingest.py`

`ingest(yaml_path, db_path, data_dir)` = load catalog → read ChromData → extract stats → render notebook → UPSERT row. Idempotent. Aborts (raises) if the `.h5cd` can't be read; notebook failure only nulls `notebook_html_path`.

- [ ] **Step 1: Write the failing test**

`data-portal/tests/pipeline/test_ingest.py`:
```python
from pathlib import Path
import pytest

from pipeline.ingest import ingest
from pipeline.catalog import CatalogError
from backend.db import make_engine, make_session, Base
from backend.models import Dataset

CATALOG = Path(__file__).resolve().parents[2] / "pipeline" / "catalog" / "mesc_sox2_test.yaml"


def _session(db_path):
    engine = make_engine(db_path)
    Base.metadata.create_all(engine)
    return make_session(engine)


def test_ingest_writes_row(tmp_path):
    db = str(tmp_path / "p.db")
    ingest(str(CATALOG), db_path=db, data_dir=str(tmp_path / "data"))
    Session = _session(db)
    with Session() as s:
        ds = s.get(Dataset, "mesc_sox2_test")
        assert ds is not None
        assert ds.n_traces == 5
        assert ds.organism == "Mus musculus"
        assert ds.files[0]["format"] == "h5cd"


def test_ingest_idempotent(tmp_path):
    db = str(tmp_path / "p.db")
    data = str(tmp_path / "data")
    ingest(str(CATALOG), db_path=db, data_dir=data)
    ingest(str(CATALOG), db_path=db, data_dir=data)  # second run
    Session = _session(db)
    with Session() as s:
        rows = s.query(Dataset).all()
        assert len(rows) == 1  # no duplicate


def test_ingest_bad_h5cd_aborts(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "id: bad_ds\ntitle: Bad\n"
        f"source_h5cd: {tmp_path / 'nonexistent.h5cd'}\n"
    )
    db = str(tmp_path / "p.db")
    with pytest.raises((CatalogError, FileNotFoundError, Exception)):
        ingest(str(bad), db_path=db, data_dir=str(tmp_path / "data"))
    # DB must not contain the bad row
    if Path(db).exists():
        Session = _session(db)
        with Session() as s:
            assert s.get(Dataset, "bad_ds") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-portal && $PY -m pytest tests/pipeline/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.ingest'`.

- [ ] **Step 3: Write `data-portal/pipeline/ingest.py`**

```python
"""Ingest CLI: catalog YAML + .h5cd + notebook -> one DB row + artifacts.

Idempotent UPSERT. Reading the .h5cd is mandatory (abort on failure);
notebook rendering is best-effort (null the path on failure).

Usage:
    python -m pipeline.ingest pipeline/catalog/mesc_sox2_test.yaml
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from uchrom.core.cdata import ChromData

from backend.db import Base, default_db_path, make_engine, make_session
from backend.models import Dataset
from pipeline.catalog import load_catalog
from pipeline.extract import extract_stats
from pipeline.render_nb import render_notebook

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest")


def ingest(yaml_path: str, db_path: str | None = None, data_dir: str | None = None) -> None:
    entry = load_catalog(yaml_path)

    # Mandatory: read ChromData (raises if unreadable -> abort, no DB write).
    cd = ChromData.read(str(entry.source_h5cd_path))
    stats = extract_stats(cd)

    data_root = Path(data_dir) if data_dir else Path(default_db_path()).parent
    nb_dir = data_root / "notebooks"
    notebook_rel = None
    if entry.notebook_path is not None:
        out_html = nb_dir / f"{entry.id}.html"
        if render_notebook(str(entry.notebook_path), str(out_html)):
            notebook_rel = f"notebooks/{entry.id}.html"
        else:
            logger.warning("notebook unavailable for %s", entry.id)

    engine = make_engine(db_path)
    Base.metadata.create_all(engine)
    Session = make_session(engine)
    with Session() as s:
        row = s.get(Dataset, entry.id)
        if row is None:
            row = Dataset(id=entry.id)
            s.add(row)
        row.title = entry.title
        row.description = entry.description
        row.organism = entry.organism
        row.assembly = entry.assembly or stats["assembly"]
        row.technology = entry.technology
        row.doi = entry.doi
        row.citation = entry.citation
        row.n_cells = stats["n_cells"]
        row.n_traces = stats["n_traces"]
        row.n_spots = stats["n_spots"]
        row.n_markers = stats["n_markers"]
        row.cell_types = stats["cell_types"]
        row.genome_coverage = stats["genome_coverage"]
        row.xyz_unit = stats["xyz_unit"]
        row.files = entry.files
        row.notebook_html_path = notebook_rel
        row.analyzer_url = entry.analyzer_url
        row.status = "published"
        s.commit()
    logger.info(
        "ingested %s: %d cells, %d traces, %d markers",
        entry.id, stats["n_cells"], stats["n_traces"], stats["n_markers"],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest a dataset catalog YAML")
    ap.add_argument("catalog", help="path to catalog YAML")
    ap.add_argument("--db", default=None, help="SQLite path (default data/portal.db)")
    ap.add_argument("--data-dir", default=None, help="artifact output dir")
    args = ap.parse_args()
    ingest(args.catalog, db_path=args.db, data_dir=args.data_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-portal && $PY -m pytest tests/pipeline/test_ingest.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full pipeline suite**

Run: `cd data-portal && $PY -m pytest tests/pipeline/ -v`
Expected: all pipeline tests PASS.

- [ ] **Step 6: Commit**

```bash
git add data-portal/pipeline/ingest.py data-portal/tests/pipeline/test_ingest.py
git commit -m "feat(portal): ingest CLI wiring catalog+extract+render+UPSERT"
```

## Task 6: Backend — Pydantic schemas + REST API

**Files:**
- Create: `data-portal/backend/schemas.py`
- Create: `data-portal/backend/api/datasets.py`
- Create: `data-portal/backend/main.py`
- Test: `data-portal/tests/backend/test_api_datasets.py`

Two-layer schema (`DatasetSummary` for list, `DatasetDetail` for detail). API is read-only. `notebook` endpoint serves the rendered HTML file.

- [ ] **Step 1: Write the failing test**

`data-portal/tests/backend/test_api_datasets.py`:
```python
import pytest
from fastapi.testclient import TestClient

from backend.db import make_engine, make_session, Base
from backend.models import Dataset


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "p.db")
    monkeypatch.setenv("PORTAL_DB_PATH", db)
    # seed
    engine = make_engine(db)
    Base.metadata.create_all(engine)
    Session = make_session(engine)
    with Session() as s:
        s.add(Dataset(
            id="ds1", title="DS One", organism="Mus musculus",
            technology="DNA FISH", n_cells=20, n_traces=20, n_spots=1000,
            n_markers=0, cell_types={"A": 20},
            files=[{"label": "x", "url": "http://e/x", "size_mb": 1, "format": "h5cd"}],
            status="published",
        ))
        s.commit()
    # import app AFTER env is set so it binds the tmp DB
    from backend.main import app
    return TestClient(app)


def test_list_datasets(client):
    r = client.get("/api/datasets")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "ds1"
    assert data[0]["n_cells"] == 20
    # summary must NOT include heavy fields
    assert "files" not in data[0]


def test_get_detail(client):
    r = client.get("/api/datasets/ds1")
    assert r.status_code == 200
    d = r.json()
    assert d["files"][0]["url"] == "http://e/x"
    assert d["cell_types"] == {"A": 20}


def test_get_missing_404(client):
    assert client.get("/api/datasets/nope").status_code == 404


def test_facets(client):
    r = client.get("/api/facets")
    assert r.status_code == 200
    assert "Mus musculus" in r.json()["organism"]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["n_datasets"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-portal && $PY -m pytest tests/backend/test_api_datasets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.main'`.

- [ ] **Step 3: Write `data-portal/backend/schemas.py`**

```python
"""Pydantic response schemas — the API/SDK contract."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class FileEntry(BaseModel):
    label: str
    url: str
    size_mb: float | int | None = None
    format: str = ""


class DatasetSummary(BaseModel):
    id: str
    title: str
    organism: str
    technology: str
    n_cells: int
    n_markers: int
    thumbnail_url: Optional[str] = None

    model_config = {"from_attributes": True}


class DatasetDetail(BaseModel):
    id: str
    title: str
    description: str
    organism: str
    assembly: str
    technology: str
    doi: str
    citation: str
    n_cells: int
    n_traces: int
    n_spots: int
    n_markers: int
    cell_types: dict
    genome_coverage: str
    xyz_unit: str
    files: list[FileEntry]
    notebook_available: bool
    analyzer_url: Optional[str] = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Write `data-portal/backend/api/datasets.py`**

```python
"""Read-only REST endpoints for datasets."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.db import Base, default_db_path, make_engine, make_session
from backend.models import Dataset
from backend.schemas import DatasetDetail, DatasetSummary

router = APIRouter(prefix="/api")

SLUG_RE = re.compile(r"^[a-z0-9_]+$")

_engine = make_engine()
Base.metadata.create_all(_engine)
_Session = make_session(_engine)


def _data_root() -> Path:
    return Path(default_db_path()).parent


@router.get("/datasets", response_model=list[DatasetSummary])
def list_datasets(
    organism: str | None = Query(None),
    technology: str | None = Query(None),
    q: str | None = Query(None),
):
    with _Session() as s:
        stmt = select(Dataset).where(Dataset.status == "published")
        if organism:
            stmt = stmt.where(Dataset.organism == organism)
        if technology:
            stmt = stmt.where(Dataset.technology == technology)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(Dataset.title.like(like) | Dataset.description.like(like))
        rows = s.scalars(stmt).all()
        return [
            DatasetSummary(
                id=r.id, title=r.title, organism=r.organism,
                technology=r.technology, n_cells=r.n_cells, n_markers=r.n_markers,
                thumbnail_url=(f"/api/datasets/{r.id}/thumbnail" if r.thumbnail_path else None),
            )
            for r in rows
        ]


@router.get("/facets")
def facets():
    with _Session() as s:
        rows = s.scalars(select(Dataset).where(Dataset.status == "published")).all()
        return {
            "organism": sorted({r.organism for r in rows if r.organism}),
            "technology": sorted({r.technology for r in rows if r.technology}),
        }


@router.get("/health")
def health():
    with _Session() as s:
        n = len(s.scalars(select(Dataset)).all())
    return {"status": "ok", "n_datasets": n}


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str):
    if not SLUG_RE.match(dataset_id):
        raise HTTPException(status_code=404, detail="not found")
    with _Session() as s:
        r = s.get(Dataset, dataset_id)
        if r is None or r.status != "published":
            raise HTTPException(status_code=404, detail="not found")
        return DatasetDetail(
            id=r.id, title=r.title, description=r.description, organism=r.organism,
            assembly=r.assembly, technology=r.technology, doi=r.doi, citation=r.citation,
            n_cells=r.n_cells, n_traces=r.n_traces, n_spots=r.n_spots, n_markers=r.n_markers,
            cell_types=r.cell_types or {}, genome_coverage=r.genome_coverage,
            xyz_unit=r.xyz_unit, files=r.files or [],
            notebook_available=bool(r.notebook_html_path), analyzer_url=r.analyzer_url,
        )


@router.get("/datasets/{dataset_id}/notebook")
def get_notebook(dataset_id: str):
    if not SLUG_RE.match(dataset_id):
        raise HTTPException(status_code=404, detail="not found")
    with _Session() as s:
        r = s.get(Dataset, dataset_id)
        if r is None or not r.notebook_html_path:
            raise HTTPException(status_code=404, detail="notebook unavailable")
        # Resolve + confirm the path stays inside data/notebooks (anti path-traversal).
        nb_dir = (_data_root() / "notebooks").resolve()
        target = (_data_root() / r.notebook_html_path).resolve()
        if not str(target).startswith(str(nb_dir)) or not target.exists():
            raise HTTPException(status_code=404, detail="notebook unavailable")
        return FileResponse(str(target), media_type="text/html")
```

- [ ] **Step 5: Write `data-portal/backend/main.py`**

```python
"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.datasets import router as datasets_router

app = FastAPI(title="U-Chrom Data Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(datasets_router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd data-portal && $PY -m pytest tests/backend/test_api_datasets.py -v`
Expected: PASS (5 passed).

Note: `backend/api/datasets.py` binds `_engine` at import time from `PORTAL_DB_PATH`. The test fixture sets the env var **before** importing `backend.main`, so the binding picks up the tmp DB. Keep that import-after-env order in any new test.

- [ ] **Step 7: Commit**

```bash
git add data-portal/backend/schemas.py data-portal/backend/api/datasets.py data-portal/backend/main.py data-portal/tests/backend/test_api_datasets.py
git commit -m "feat(portal): read-only REST API (datasets/facets/health/notebook)"
```

---

## Task 7: Backend — path-traversal security test

**Files:**
- Test: `data-portal/tests/backend/test_security.py`

Confirm the slug whitelist + path-resolution defense rejects traversal attempts. No new implementation — this hardens Task 6.

- [ ] **Step 1: Write the failing/guarding test**

`data-portal/tests/backend/test_security.py`:
```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "p.db"))
    from backend.db import make_engine, Base
    Base.metadata.create_all(make_engine(str(tmp_path / "p.db")))
    from backend.main import app
    return TestClient(app)


@pytest.mark.parametrize("attack", [
    "../../../etc/passwd",
    "..%2f..%2fsecret",
    "foo/bar",
    "Foo_Bar",      # uppercase not in slug whitelist
    "foo bar",
])
def test_notebook_rejects_bad_ids(client, attack):
    r = client.get(f"/api/datasets/{attack}/notebook")
    assert r.status_code == 404


@pytest.mark.parametrize("attack", ["../../etc", "Foo", "a b"])
def test_detail_rejects_bad_ids(client, attack):
    r = client.get(f"/api/datasets/{attack}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd data-portal && $PY -m pytest tests/backend/test_security.py -v`
Expected: PASS (all parametrized cases). If any case returns 200/500 instead of 404, the slug guard in Task 6 needs tightening — fix `SLUG_RE` usage before continuing.

- [ ] **Step 3: Run the full backend + pipeline suite**

Run: `cd data-portal && $PY -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add data-portal/tests/backend/test_security.py
git commit -m "test(portal): path-traversal + slug-whitelist guards"
```

## Task 8: Frontend — scaffold Next.js + Tailwind + API client

**Files:**
- Create: `data-portal/frontend/` (Next.js project)
- Create: `data-portal/frontend/src/lib/api.ts`

Frontend is SSR UI — verified by build + runtime check rather than unit tests (E2E deferred to v1 per spec §10).

- [ ] **Step 1: Scaffold Next.js with TypeScript + Tailwind + App Router**

Run:
```bash
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal/data-portal
npx --yes create-next-app@latest frontend \
  --typescript --tailwind --app --src-dir --eslint \
  --import-alias "@/*" --no-turbopack --use-npm
```
Expected: scaffolds `frontend/` with `src/app/`, `package.json`, `tailwind.config.ts`. If prompted, accept defaults.

- [ ] **Step 2: Add backend base URL config**

Create `data-portal/frontend/.env.local`:
```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

- [ ] **Step 3: Write `data-portal/frontend/src/lib/api.ts`**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface DatasetSummary {
  id: string;
  title: string;
  organism: string;
  technology: string;
  n_cells: number;
  n_markers: number;
  thumbnail_url: string | null;
}

export interface FileEntry {
  label: string;
  url: string;
  size_mb: number | null;
  format: string;
}

export interface DatasetDetail {
  id: string;
  title: string;
  description: string;
  organism: string;
  assembly: string;
  technology: string;
  doi: string;
  citation: string;
  n_cells: number;
  n_traces: number;
  n_spots: number;
  n_markers: number;
  cell_types: Record<string, number>;
  genome_coverage: string;
  xyz_unit: string;
  files: FileEntry[];
  notebook_available: boolean;
  analyzer_url: string | null;
}

export const apiBase = API_BASE;

export async function listDatasets(params: Record<string, string> = {}): Promise<DatasetSummary[]> {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/api/datasets${qs ? `?${qs}` : ""}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`list failed: ${res.status}`);
  return res.json();
}

export async function getDataset(id: string): Promise<DatasetDetail | null> {
  const res = await fetch(`${API_BASE}/api/datasets/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`detail failed: ${res.status}`);
  return res.json();
}

export async function getFacets(): Promise<{ organism: string[]; technology: string[] }> {
  const res = await fetch(`${API_BASE}/api/facets`, { cache: "no-store" });
  if (!res.ok) return { organism: [], technology: [] };
  return res.json();
}
```

- [ ] **Step 4: Verify the scaffold builds**

Run:
```bash
cd data-portal/frontend && npm run build
```
Expected: build succeeds (default scaffold compiles).

- [ ] **Step 5: Commit**

```bash
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal
git add data-portal/frontend/package.json data-portal/frontend/src/lib/api.ts \
        data-portal/frontend/.env.local data-portal/frontend/tsconfig.json \
        data-portal/frontend/next.config.* data-portal/frontend/tailwind.config.* \
        data-portal/frontend/postcss.config.* data-portal/frontend/.eslintrc.* \
        data-portal/frontend/src/app/globals.css
git commit -m "chore(portal): scaffold Next.js frontend + typed API client"
```
Note: `frontend/node_modules/` and `frontend/.next/` are gitignored (Task 0). If `create-next-app` wrote its own `.gitignore` inside `frontend/`, keep it.

---

## Task 9: Frontend — list page (`/`)

**Files:**
- Modify: `data-portal/frontend/src/app/page.tsx`
- Modify: `data-portal/frontend/src/app/layout.tsx`

- [ ] **Step 1: Write the global shell `layout.tsx`**

Replace `data-portal/frontend/src/app/layout.tsx`:
```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "U-Chrom Data Portal",
  description: "Analysis-ready chromatin 3D structure datasets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="border-b bg-white">
          <div className="mx-auto max-w-6xl px-4 py-4 flex items-center justify-between">
            <a href="/" className="text-lg font-semibold">U-Chrom Data Portal</a>
            <a
              href="https://github.com/Nanguage/U-Chrom"
              className="text-sm text-gray-500 hover:text-gray-900"
            >
              GitHub
            </a>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: Write the list page `page.tsx`**

Replace `data-portal/frontend/src/app/page.tsx`:
```tsx
import { listDatasets } from "@/lib/api";

export default async function HomePage() {
  let datasets;
  try {
    datasets = await listDatasets();
  } catch {
    return (
      <p className="text-gray-500">暂无法加载数据集，请确认后端服务已启动。</p>
    );
  }

  if (datasets.length === 0) {
    return <p className="text-gray-500">暂无数据集。</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {datasets.map((d) => (
        <a
          key={d.id}
          href={`/datasets/${d.id}`}
          className="rounded-lg border bg-white p-4 hover:shadow-md transition"
        >
          <h2 className="font-semibold">{d.title}</h2>
          <p className="mt-1 text-sm text-gray-500">
            {d.organism} · {d.technology}
          </p>
          <p className="mt-2 text-sm">
            {d.n_cells.toLocaleString()} cells · {d.n_markers} markers
          </p>
        </a>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `cd data-portal/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal
git add data-portal/frontend/src/app/layout.tsx data-portal/frontend/src/app/page.tsx
git commit -m "feat(portal): dataset list page + global shell"
```

---

## Task 10: Frontend — detail page (`/datasets/[id]`) with 3 tabs

**Files:**
- Create: `data-portal/frontend/src/app/datasets/[id]/page.tsx`
- Create: `data-portal/frontend/src/app/datasets/[id]/DetailTabs.tsx`

Tabs need client-side state, so a small client component wraps the SSR-fetched data.

- [ ] **Step 1: Write the SSR page `page.tsx`**

`data-portal/frontend/src/app/datasets/[id]/page.tsx`:
```tsx
import { notFound } from "next/navigation";
import { getDataset } from "@/lib/api";
import { DetailTabs } from "./DetailTabs";

export default async function DatasetPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const ds = await getDataset(id);
  if (!ds) notFound();

  return (
    <div>
      <a href="/" className="text-sm text-gray-500 hover:text-gray-900">← Back</a>
      <h1 className="mt-2 text-2xl font-semibold">{ds.title}</h1>
      <p className="mt-1 text-sm text-gray-500">
        {ds.organism} · {ds.assembly} · {ds.technology}
        {ds.doi ? ` · DOI:${ds.doi}` : ""}
      </p>
      <div className="mt-6">
        <DetailTabs ds={ds} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write the client tabs component `DetailTabs.tsx`**

`data-portal/frontend/src/app/datasets/[id]/DetailTabs.tsx`:
```tsx
"use client";

import { useState } from "react";
import { apiBase, type DatasetDetail } from "@/lib/api";

const TABS = ["Overview", "Notebook", "Download"] as const;
type Tab = (typeof TABS)[number];

export function DetailTabs({ ds }: { ds: DatasetDetail }) {
  const [tab, setTab] = useState<Tab>("Overview");

  return (
    <div>
      <div className="flex gap-2 border-b">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm ${
              tab === t ? "border-b-2 border-gray-900 font-medium" : "text-gray-500"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === "Overview" && <Overview ds={ds} />}
        {tab === "Notebook" && <Notebook ds={ds} />}
        {tab === "Download" && <Download ds={ds} />}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border bg-white p-4 text-center">
      <div className="text-xl font-semibold">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}

function Overview({ ds }: { ds: DatasetDetail }) {
  const code = `from uchrom.datasets import load_dataset\n\ncd = load_dataset("${ds.id}")  # SDK coming soon`;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="cells" value={ds.n_cells} />
        <Stat label="traces" value={ds.n_traces} />
        <Stat label="spots" value={ds.n_spots} />
        <Stat label="markers" value={ds.n_markers} />
      </div>
      {ds.description && <p className="text-sm">{ds.description}</p>}
      {Object.keys(ds.cell_types).length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium">Cell types</h3>
          <ul className="text-sm text-gray-600">
            {Object.entries(ds.cell_types).map(([k, v]) => (
              <li key={k}>{k}: {v.toLocaleString()}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <h3 className="mb-2 text-sm font-medium">Load in Python</h3>
        <pre className="overflow-x-auto rounded-lg bg-gray-900 p-4 text-xs text-gray-100">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}

function Notebook({ ds }: { ds: DatasetDetail }) {
  if (!ds.notebook_available) {
    return <p className="text-gray-500">该数据集的 notebook 暂不可用。</p>;
  }
  return (
    <iframe
      src={`${apiBase}/api/datasets/${ds.id}/notebook`}
      className="h-[70vh] w-full rounded-lg border"
      title="notebook"
      loading="lazy"
    />
  );
}

function Download({ ds }: { ds: DatasetDetail }) {
  return (
    <div className="space-y-3">
      {ds.files.map((f) => (
        <a
          key={f.url}
          href={f.url}
          className="flex items-center justify-between rounded-lg border bg-white p-4 hover:shadow-sm"
        >
          <span className="text-sm font-medium">{f.label}</span>
          <span className="text-xs text-gray-500">
            {f.format}{f.size_mb ? ` · ${f.size_mb} MB` : ""}
          </span>
        </a>
      ))}
      {ds.analyzer_url && (
        <a
          href={ds.analyzer_url}
          className="block rounded-lg bg-gray-900 p-4 text-center text-sm text-white"
        >
          在 Analyzer 中打开
        </a>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `cd data-portal/frontend && npm run build`
Expected: build succeeds (no type errors).

- [ ] **Step 4: Commit**

```bash
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal
git add data-portal/frontend/src/app/datasets/
git commit -m "feat(portal): dataset detail page with Overview/Notebook/Download tabs"
```

## Task 11: End-to-end validation + README

**Files:**
- Create: `data-portal/README.md`

Per spec §10 validation discipline: actually run the whole stack on real data, not just "tests passed".

- [ ] **Step 1: Run the real ingest into the real data dir**

Run:
```bash
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal/data-portal
$PY -m pipeline.ingest pipeline/catalog/mesc_sox2_test.yaml
```
(where `$PY=/Volumes/sandisk/Coding/U-Chrom/.venv/bin/python`)
Expected: log line `INFO ingested mesc_sox2_test: 0 cells, 5 traces, 0 markers` and `data/portal.db` + `data/notebooks/mesc_sox2_test.html` created.

- [ ] **Step 2: Start the backend and probe endpoints**

Run (background, then curl):
```bash
cd data-portal
$PY -m uvicorn backend.main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/api/health
curl -s http://localhost:8000/api/datasets
curl -s http://localhost:8000/api/datasets/mesc_sox2_test | head -c 400
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/datasets/mesc_sox2_test/notebook
```
Expected: health shows `n_datasets: 1`; list returns one summary; detail returns full JSON; notebook returns `200`. Then kill the server: `kill %1`.

- [ ] **Step 3: Start the frontend dev server and verify pages render**

Run:
```bash
# terminal A: backend
cd data-portal && $PY -m uvicorn backend.main:app --port 8000 &
# terminal B: frontend
cd data-portal/frontend && npm run dev &
sleep 5
curl -s http://localhost:3000/ | grep -o "U-Chrom Data Portal" | head -1
curl -s http://localhost:3000/datasets/mesc_sox2_test | grep -o "mESC Sox2" | head -1
```
Expected: both `grep` find their strings (SSR rendered the title + detail). Kill both servers afterward.

- [ ] **Step 4: Manual browser check (human-in-loop)**

Open `http://localhost:3000` in a browser. Confirm:
- List page shows the `mesc_sox2_test` card.
- Clicking it opens the detail page.
- Overview tab shows stat cards (5 traces) + the `load_dataset` code snippet.
- Notebook tab loads the embedded notebook HTML in an iframe.
- Download tab shows the file entry (placeholder URL is fine); no "Analyzer" button (analyzer_url is null).

- [ ] **Step 5: Write `data-portal/README.md`**

```markdown
# U-Chrom Data Portal

Analysis-ready chromatin 3D structure dataset portal. Distributes ChromData
(`.h5cd`) datasets with embedded reproduction notebooks. See the design spec at
`docs/superpowers/specs/2026-06-10-uchrom-web-portal-design.md`.

## Architecture

- `pipeline/` — offline CLI: `.h5cd` + notebook → SQLite row + static HTML
- `backend/` — read-only FastAPI REST over the SQLite DB (no `.h5cd` at runtime)
- `frontend/` — Next.js SSR list + detail pages

Data files are externally hosted (Zenodo); the portal stores only metadata and
pre-rendered notebooks.

## Setup

Python (uses the repo venv at `../.venv`):
\`\`\`bash
/Volumes/sandisk/Coding/U-Chrom/.venv/bin/pip install -r requirements.txt
\`\`\`

## Ingest a dataset

\`\`\`bash
python -m pipeline.ingest pipeline/catalog/<dataset>.yaml
\`\`\`

## Run

\`\`\`bash
# backend
python -m uvicorn backend.main:app --port 8000
# frontend (separate shell)
cd frontend && npm install && npm run dev
\`\`\`

Visit http://localhost:3000.

## Tests

\`\`\`bash
python -m pytest tests/ -v
\`\`\`

## Adding a dataset

1. Write a catalog YAML in `pipeline/catalog/` (see `mesc_sox2_test.yaml`).
2. Fill `files[].url` with the external (Zenodo) download links.
3. Run `python -m pipeline.ingest pipeline/catalog/<id>.yaml`.
\`\`\`
```

- [ ] **Step 6: Final full-suite run + commit**

Run: `cd data-portal && $PY -m pytest tests/ -v`
Expected: all PASS.

```bash
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/web-portal
git add data-portal/README.md
git commit -m "docs(portal): add README + end-to-end validation"
```

---

## Validation Summary (report in PR/commit)

After Task 11, report the real-data result, not just "tests passed":
- Ingested dataset: `mesc_sox2_test` (5 traces, 205 spots, 0 markers — minimal fixture).
- Endpoints verified live: `/api/health`, `/api/datasets`, `/api/datasets/{id}`, `/api/datasets/{id}/notebook`.
- Frontend SSR verified: list card + detail page + notebook iframe.
- **Known limitation:** the in-repo fixture has no cells/tracks/uns, so cell-type
  distribution and marker count are empty. The full Takei 2025 dataset (external
  SSD / Zenodo) exercises those fields — add its catalog YAML when the `.h5cd`
  is hosted, then re-ingest. This is the v1 follow-up.
- **Deliberately deferred:** thumbnail generation. The `Dataset.thumbnail_path`
  column and the summary's `thumbnail_url` exist for the future, but v0 does not
  generate a representative image from the notebook and the list card does not
  display one (it shows title/organism/stats only). Internally consistent: never
  populated, never rendered. Add notebook-cell image extraction in v1 alongside
  the interactive Plotly figures.
