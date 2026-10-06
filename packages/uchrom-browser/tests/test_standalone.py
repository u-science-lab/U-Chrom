"""uchrom-browser on its own: the server opens a store and streams its geometry with the data model (chromdata) and
no analysis library (uchrom) — what the hosted image installs."""

import subprocess
import sys

_SCRIPT = """
import sys
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
from chromdata import ChromData
import uchrom_browser
from uchrom_browser import DatasetStore, create_app, decode_geometry

rng = np.random.default_rng(0)
spots = pd.DataFrame([{"chrom": c, "start": k * 1000, "end": (k + 1) * 1000, "trace_id": f"c{i}_{c}", "cell_id": f"c{i}"}
                      for i in range(2) for c in ("chr1", "chr2") for k in range(10)])
ChromData(rng.normal(size=(len(spots), 3)), spots).write(sys.argv[1])

client = TestClient(create_app(DatasetStore(), atlas=""))
assert client.get("/api/health").json()["status"] == "ok"
ds = client.post("/api/datasets", json={"path": sys.argv[1]}).json()
assert ds["n_spots"] == 40 and ds["n_cells"] == 2, ds
r = client.post(f"/api/datasets/{ds['id']}/geometry", json={"cell_ids": ["c0"]})
assert r.status_code == 200
assert decode_geometry(r.content)["header"]["n_points"] == 20
print("uchrom imported:", any(m == "uchrom" or m.startswith("uchrom.") for m in sys.modules))
"""


def test_serves_a_store_without_uchrom(tmp_path):
    out = subprocess.run([sys.executable, "-c", _SCRIPT, str(tmp_path / "toy.chromdata.zarr")],
                         capture_output=True, text=True, check=True).stdout
    assert "uchrom imported: False" in out
