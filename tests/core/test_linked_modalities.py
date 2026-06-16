import numpy as np
import pandas as pd


def _make_cd(coords=None):
    from uchrom import ChromData

    if coords is None:
        coords = np.zeros((4, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr1"],
        "start": [0, 1_000_000, 0, 1_000_000],
        "end": [1_000_000, 2_000_000, 1_000_000, 2_000_000],
        "trace_id": ["t1", "t1", "t2", "t2"],
        "cell_id": ["cell_a", "cell_a", "cell_b", "cell_b"],
    })
    cells = pd.DataFrame(
        {"cell_type": ["L2/3 IT", "L5 IT"]},
        index=pd.Index(["cell_a", "cell_b"], name="cell_id"),
    )
    return ChromData(coords, spots, cells=cells)


def test_linked_mudata_and_scool_metadata_roundtrip(tmp_path):
    from uchrom import ChromData

    cd = _make_cd()
    h5mu = tmp_path / "schicar.h5mu"
    scool = tmp_path / "schicar.scool"
    h5mu.write_text("placeholder")
    scool.write_text("placeholder")

    cd.link_mudata(
        h5mu,
        key="schicar",
        modalities=["rna", "atac", "hic_features", "spatial"],
        cell_axis="RNAbarcode",
        spatial_source="Tangram-inferred MERFISH coordinate",
        not_measured_spatial=True,
    )
    cd.link_scool(
        scool,
        key="contacts",
        cell_name="RNAbarcode",
        barcode_source="DNAbarcode",
        genome_assembly="mm10",
        bin_size=1_000_000,
    )

    path = tmp_path / "linked.h5cd"
    cd.write(path)
    out = ChromData.read(path)

    links = out.describe_links()
    assert links["linked_mudata"]["schicar"]["path"] == str(h5mu)
    assert links["linked_mudata"]["schicar"]["not_measured_spatial"] is True
    assert links["linked_scool"]["contacts"]["bin_size"] == 1_000_000
    assert links["linked_scool"]["contacts"]["coordinate_status"] == "contacts, not xyz coordinates"


def test_validate_links_reports_all_nan_coords_without_declared_status():
    cd = _make_cd(coords=np.full((4, 3), np.nan))

    issues = cd.validate_links(check_files=False)

    assert any("coords are all NaN" in issue for issue in issues)


def test_validate_links_accepts_declared_all_nan_projection(tmp_path):
    cd = _make_cd(coords=np.full((4, 3), np.nan))
    cd.uns["coordinate_status"] = "projection_container_no_xyz_coordinates"
    cd.link_mudata(tmp_path / "missing.h5mu", key="m", modalities=["rna"])

    issues = cd.validate_links(check_files=False)

    assert not any("coords are all NaN" in issue for issue in issues)
    assert issues == []


def test_uchrom_project_delegates_linking_and_validation(tmp_path):
    from uchrom import UChromProject

    cd = _make_cd()
    project = UChromProject.from_chromdata(cd)
    project.link_mudata(tmp_path / "schicar.h5mu", key="schicar", modalities=["rna"])
    project.link_scool(tmp_path / "contacts.scool", key="contacts", cell_name="RNAbarcode")

    desc = project.describe()

    assert desc["summary"]["n_cells"] == 2
    assert "schicar" in desc["links"]["linked_mudata"]
    assert "contacts" in desc["links"]["linked_scool"]
    assert project.validate(check_files=False) == []


def test_discovery_schema_reports_linked_mudata_and_scool(tmp_path):
    from uchrom.auto_discovery.schema import build_discovery_schema

    cd = _make_cd()
    cd.link_mudata(tmp_path / "schicar.h5mu", key="schicar", modalities=["rna", "spatial"])
    cd.link_scool(tmp_path / "contacts.scool", key="contacts", cell_name="RNAbarcode")

    schema = build_discovery_schema(cd)

    assert schema["linked_mudata"]["present"] is True
    assert "schicar" in schema["linked_mudata"]["records"]
    assert schema["linked_scool"]["present"] is True
    assert "contacts" in schema["linked_scool"]["records"]
    assert schema["modalities"]["mudata_multiomics"]["present"] is True
    assert schema["modalities"]["single_cell_hic_contacts"]["present"] is True


def test_cell_spatial_coordinates_align_by_cell_id_and_roundtrip(tmp_path):
    from uchrom import ChromData
    from uchrom.auto_discovery.schema import build_discovery_schema

    cd = _make_cd()
    cd.set_cell_spatial_coordinates(
        np.array([[20.0, 30.0], [10.0, 15.0]]),
        key="tangram_merfish",
        cell_ids=["cell_b", "cell_a"],
        source="MERFISH centroid",
        method="Tangram map_cells_to_space",
        coordinate_system="micron",
        inferred=True,
    )

    path = tmp_path / "spatial_cells.h5cd"
    cd.write(path)
    out = ChromData.read(path)

    assert out.cells.loc["cell_a", "tangram_merfish_spatial_x"] == 10.0
    assert out.cells.loc["cell_a", "tangram_merfish_spatial_y"] == 15.0
    assert out.cells.loc["cell_b", "tangram_merfish_spatial_x"] == 20.0
    assert out.describe_links()["cell_spatial"]["tangram_merfish"]["inferred"] is True

    schema = build_discovery_schema(out)
    assert schema["cell_spatial"]["present"] is True
    assert "tangram_merfish" in schema["cell_spatial"]["records"]
    assert schema["modalities"]["cell_spatial_coordinates"]["present"] is True
