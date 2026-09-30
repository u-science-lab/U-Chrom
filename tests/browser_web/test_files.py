"""Directory listing of the "Open dataset" dialog (uchrom.browser.web.files, GET /api/files)."""

import pytest

from uchrom.browser.web.files import dataset_format, list_dir, places


def test_dataset_formats():
    assert dataset_format("a.chromdata.zarr", True) == "chromdata.zarr"
    assert dataset_format("a.chromdata.zarr", False) is None          # a file of that name: not a store
    assert dataset_format("x.cdz", False) == "cdz"
    assert dataset_format("x.H5CD", False) == "h5cd"
    assert dataset_format("t.csv.gz", False) == "csv"
    assert dataset_format("notes.txt", False) is None
    assert dataset_format("folder", True) is None


def test_list_dir_orders_and_classifies(tmp_path):
    (tmp_path / "b_dir").mkdir()
    store = tmp_path / "s.chromdata.zarr"
    store.mkdir()
    (store / "zarr.json").write_text("{}")
    (tmp_path / "a.cdz").write_bytes(b"x" * 10)
    (tmp_path / "readme.txt").write_text("hi")
    (tmp_path / ".hidden").mkdir()
    d = list_dir(str(tmp_path))
    assert d["path"] == str(tmp_path.resolve()) and d["parent"] == str(tmp_path.resolve().parent)
    assert [(e["name"], e["kind"], e["format"]) for e in d["entries"]] == [
        ("b_dir", "dir", None), ("a.cdz", "dataset", "cdz"),
        ("s.chromdata.zarr", "dataset", "chromdata.zarr"), ("readme.txt", "file", None)]
    sizes = {e["name"]: e["size"] for e in d["entries"]}
    assert sizes["a.cdz"] == 10 and sizes["s.chromdata.zarr"] == 2 and sizes["b_dir"] is None
    assert ".hidden" in [e["name"] for e in list_dir(str(tmp_path), show_hidden=True)["entries"]]
    with pytest.raises(FileNotFoundError):
        list_dir(str(tmp_path / "nope"))
    with pytest.raises(NotADirectoryError):
        list_dir(str(tmp_path / "readme.txt"))


def test_places_dedup(tmp_path):
    p = places([str(tmp_path / "x.cdz"), str(tmp_path / "y.cdz")])
    labels = [x["label"] for x in p]
    assert labels[:2] == ["Server folder", "Home"]
    assert sum(1 for x in p if x["path"] == str(tmp_path.resolve())) == 1


def test_files_endpoint(tmp_path):
    from fastapi.testclient import TestClient

    from uchrom.browser.web import DatasetStore, create_app

    (tmp_path / "a.cdz").write_bytes(b"x")
    c = TestClient(create_app(DatasetStore()))
    r = c.get("/api/files", params={"path": str(tmp_path)})
    assert r.status_code == 200 and r.json()["entries"][0]["name"] == "a.cdz"
    assert c.get("/api/files", params={"path": str(tmp_path / "nope")}).status_code == 404
    assert c.get("/api/files/places").json()[0]["label"] == "Server folder"
