"""Project-level wrapper for linked U-Chrom modality files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from .cdata import ChromData, PathLike


@dataclass
class UChromProject:
    """Coordinate a ``ChromData`` object with linked MuData and scool files.

    This wrapper is intentionally lightweight.  The data remain in their
    native files; the project object centralizes links, validation, and
    descriptive metadata.
    """

    chromdata: Optional[ChromData] = None
    chromdata_path: Optional[Path] = None
    links: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_chromdata(cls, cdata_or_path: Union[ChromData, PathLike]) -> "UChromProject":
        if isinstance(cdata_or_path, ChromData):
            project = cls(chromdata=cdata_or_path)
        else:
            path = Path(cdata_or_path)
            project = cls(chromdata=ChromData.read(path), chromdata_path=path)
        project.links = project.chromdata.describe_links() if project.chromdata is not None else {}
        return project

    def link_mudata(self, path: PathLike, *, key: str = "default", **metadata: Any) -> dict:
        self._require_chromdata()
        record = self.chromdata.link_mudata(path, key=key, **metadata)
        self.links = self.chromdata.describe_links()
        return record

    def link_scool(self, path: PathLike, *, key: str = "default", **metadata: Any) -> dict:
        self._require_chromdata()
        record = self.chromdata.link_scool(path, key=key, **metadata)
        self.links = self.chromdata.describe_links()
        return record

    def set_cell_spatial_coordinates(self, xy, *, key: str = "default", **metadata: Any) -> dict:
        self._require_chromdata()
        record = self.chromdata.set_cell_spatial_coordinates(xy, key=key, **metadata)
        self.links = self.chromdata.describe_links()
        return record

    def load_mudata(self, *, key: str = "default"):
        self._require_chromdata()
        return self.chromdata.load_linked_mudata(key=key)

    def load_scool(self, *, key: str = "default", cell: Optional[str] = None):
        self._require_chromdata()
        return self.chromdata.load_linked_scool(key=key, cell=cell)

    def validate(self, *, check_files: bool = True) -> list[str]:
        self._require_chromdata()
        return self.chromdata.validate_links(check_files=check_files)

    def describe(self) -> dict:
        self._require_chromdata()
        return {
            "chromdata_path": None if self.chromdata_path is None else str(self.chromdata_path),
            "summary": {
                "n_spots": int(self.chromdata.n_spots),
                "n_traces": int(self.chromdata.n_traces),
                "n_cells": int(self.chromdata.n_cells),
            },
            "links": self.chromdata.describe_links(),
        }

    def _require_chromdata(self) -> None:
        if self.chromdata is None:
            raise ValueError("UChromProject has no ChromData object.")
