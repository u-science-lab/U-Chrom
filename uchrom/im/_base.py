from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np


def ensure_2d_array(array, source="input"):
    array = np.asarray(array)
    if array.ndim != 2:
        raise ValueError(
            f"Expected a 2D array from {source}, got shape {array.shape}."
        )
    return array


def ensure_3d_array(array, source="input"):
    array = np.asarray(array)
    if array.ndim != 3:
        raise ValueError(
            f"Expected a 3D stack with shape (z, y, x) from {source}, got shape {array.shape}."
        )
    if min(array.shape) < 1:
        raise ValueError(f"Invalid empty stack from {source}: shape={array.shape}")
    return array


@dataclass
class Image2D:
    data: np.ndarray
    name: Optional[str] = None
    path: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.data = ensure_2d_array(self.data, source=self.name or self.path or "Image2D")


@dataclass
class Image3D:
    data: np.ndarray
    name: Optional[str] = None
    path: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.data = ensure_3d_array(self.data, source=self.name or self.path or "Image3D")


@dataclass
class RoundBundle:
    fiducial: Image2D
    images: Dict[str, Image2D] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectionResult:
    data: np.ndarray
    method: str
    zmin: int
    zmax: int
    source_path: Optional[str] = None
    saved_npy_path: Optional[str] = None
    saved_png_path: Optional[str] = None


@dataclass
class Registration2DImageResult:
    input_image: Image2D
    registered: np.ndarray
    registered_path: Optional[str] = None


@dataclass
class Registration2DRoundResult:
    shift: np.ndarray
    fiducial: Image2D
    registered_fiducial: np.ndarray
    images: Dict[str, Registration2DImageResult] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    error: Optional[float] = None
    diffphase: Optional[float] = None
    reference_preprocessed: Optional[np.ndarray] = None
    moving_preprocessed: Optional[np.ndarray] = None
    moving_preprocessed_shifted: Optional[np.ndarray] = None
    registered_path: Optional[str] = None
    overlay_corrected_path: Optional[str] = None
    reference_difference_path: Optional[str] = None


@dataclass
class Registration2DResult:
    reference: str
    rounds: Dict[str, Registration2DRoundResult]
    sample_id: Optional[str] = None
    roi: Optional[str] = None
    out_dir: Optional[str] = None
    shift_json_path: Optional[str] = None
    shift_table_path: Optional[str] = None

    def to_dict(self):
        return {
            "reference": self.reference,
            "sample_id": self.sample_id,
            "roi": self.roi,
            "out_dir": self.out_dir,
            "shift_json": self.shift_json_path,
            "shift_table": self.shift_table_path,
            "rounds": {
                round_name: {
                    "shift": [
                        float(round_result.shift[0]),
                        float(round_result.shift[1]),
                    ],
                    "error": round_result.error,
                    "diffphase": round_result.diffphase,
                    "fiducial": {
                        "input_path": round_result.fiducial.path,
                        "registered_path": round_result.registered_path,
                        "overlay_corrected_path": round_result.overlay_corrected_path,
                        "reference_difference_path": round_result.reference_difference_path,
                    },
                    "images": [
                        {
                            "name": image_name,
                            "input_path": image_result.input_image.path,
                            "registered_path": image_result.registered_path,
                        }
                        for image_name, image_result in round_result.images.items()
                    ],
                    "meta": round_result.fiducial.meta,
                    "round_meta": round_result.meta,
                }
                for round_name, round_result in self.rounds.items()
            },
        }


@dataclass
class LocalRegistrationRoundResult:
    shift_zyx: np.ndarray
    registered_fiducial: np.ndarray
    block_table: Any = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.shift_zyx = np.asarray(self.shift_zyx, dtype=np.float64)


@dataclass
class LocalRegistrationResult:
    reference: str
    rounds: Dict[str, LocalRegistrationRoundResult]
    table: Any = None
    method: str = "block3d"
    out_dir: Optional[str] = None
    table_path: Optional[str] = None


@dataclass
class MaskResult:
    labels: np.ndarray
    properties: Any = None
    method: str = "threshold"
    source_name: Optional[str] = None
    saved_path: Optional[str] = None


@dataclass
class LocalizationResult:
    table: Any
    method: str = "pyhim_3d"
    saved_path: Optional[str] = None

    def __getitem__(self, key):
        return self.table.__getitem__(key)

    def __len__(self):
        return len(self.table)

    @property
    def columns(self):
        return self.table.columns

    def head(self, *args, **kwargs):
        return self.table.head(*args, **kwargs)


@dataclass
class TraceResult:
    table: Any
    method: str = "KDtree"
    saved_path: Optional[str] = None

    def __getitem__(self, key):
        return self.table.__getitem__(key)

    def __len__(self):
        return len(self.table)

    @property
    def columns(self):
        return self.table.columns

    def head(self, *args, **kwargs):
        return self.table.head(*args, **kwargs)


@dataclass
class MatrixResult:
    matrices: Dict[str, np.ndarray]
    saved_paths: Dict[str, str] = field(default_factory=dict)

    def keys(self):
        return self.matrices.keys()

    def __getitem__(self, key):
        return self.matrices[key]
