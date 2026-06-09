import pytest
from pipeline.catalog import load_catalog, CatalogError


def test_load_valid_catalog():
    from pathlib import Path
    yaml_path = Path(__file__).resolve().parents[2] / "pipeline" / "catalog" / "mesc_sox2_test.yaml"
    entry = load_catalog(str(yaml_path))
    assert entry.id == "mesc_sox2_test"
    assert entry.organism == "Mus musculus"
    assert entry.files[0]["format"] == "h5cd"
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
