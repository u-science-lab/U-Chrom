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
