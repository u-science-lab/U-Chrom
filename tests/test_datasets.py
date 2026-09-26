"""uchrom.datasets: example-data root discovery and path joining."""

from pathlib import Path

import pytest

import uchrom
from uchrom import datasets
from uchrom.datasets import DATASETS, example_data_dir, example_path

REPO = Path(__file__).resolve().parents[1]


def test_env_var_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("UCHROM_EXAMPLE_DATA", str(tmp_path))
    assert example_data_dir() == tmp_path
    assert example_path("imr90_hic", "x.cool") == tmp_path / "imr90_hic" / "x.cool"


def test_repo_discovery_from_package(monkeypatch):
    monkeypatch.delenv("UCHROM_EXAMPLE_DATA", raising=False)
    pkg = Path(uchrom.__file__).resolve().parent
    if not (pkg.parent / "example-data").is_dir():
        pytest.skip("uchrom not imported from a source checkout")
    assert example_data_dir() == pkg.parent / "example-data"


def test_fallback_is_cwd_relative(monkeypatch):
    monkeypatch.delenv("UCHROM_EXAMPLE_DATA", raising=False)
    monkeypatch.setattr(datasets, "_checkout_example_data", lambda: None)
    assert example_data_dir() == Path("example-data")


def test_path_joining(monkeypatch, tmp_path):
    monkeypatch.setenv("UCHROM_EXAMPLE_DATA", str(tmp_path))
    assert example_path("takei2021_mesc") == tmp_path / "takei2021_mesc"
    p = example_path("takei2021_mesc", "DNAseqFISH+", "a.csv")
    assert p == tmp_path / "takei2021_mesc" / "DNAseqFISH+" / "a.csv"
    assert not p.exists()  # no existence check


def test_unknown_dataset_lists_catalog():
    with pytest.raises(ValueError, match="stevens2017_mesc"):
        example_path("no_such_dataset")


def test_catalog_folders_match_disk(monkeypatch):
    """Every tracked dataset folder is in DATASETS and in the catalog README."""
    monkeypatch.delenv("UCHROM_EXAMPLE_DATA", raising=False)
    root = REPO / "example-data"
    if not root.is_dir():
        pytest.skip("no example-data/ in this checkout")
    readme = (root / "README.md").read_text()
    on_disk = {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))}
    assert on_disk <= set(DATASETS), on_disk - set(DATASETS)
    for name in DATASETS:
        assert f"{name}/" in readme, f"{name}/ missing from example-data/README.md"
    # in-repo files resolve through the helper
    monkeypatch.setenv("UCHROM_EXAMPLE_DATA", str(root))
    assert example_path("stevens2017_mesc", "cell1.pairs").is_file()
    assert example_path("imr90_hic", "IMR90_chr21_30kb.cool").is_file()
