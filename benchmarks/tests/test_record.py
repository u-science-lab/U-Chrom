"""benchmarks/_record.py: results with provenance, and comparing two runs."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _record  # noqa: E402


def test_save_load_compare(tmp_path):
    p = _record.save(tmp_path / "a.json", {"recall": np.float64(0.76), "n": np.int64(94), "seconds": 1.5,
                                           "per_chrom": {"chr21": [0.7, float("nan")]}},
                     script=__file__, datasets=["rao2014_imr90_chr21"], params={"window": 100_000})
    doc = _record.load(p)
    prov = doc["provenance"]
    assert doc["results"]["recall"] == 0.76 and doc["results"]["per_chrom"]["chr21"][1] is None
    assert prov["revision"] and prov["datasets"] == ["rao2014_imr90_chr21"] and prov["params"]["window"] == 100_000
    assert prov["script"].startswith("benchmarks/") and "numpy" in prov["versions"] and prov["cpus"] >= 1
    q = _record.save(tmp_path / "b.json", {"recall": 0.70, "n": 94, "seconds": 9.0, "per_chrom": {"chr21": [0.7, None]}})
    diffs = _record.compare(p, q)
    assert diffs == ["recall: 0.76 -> 0.7"]                   # timings left out
    assert _record.compare(p, q, rtol=0.1) == []
    bare = tmp_path / "old.json"
    bare.write_text(json.dumps({"recall": 0.76}))             # a file written before _record: no provenance
    assert _record.load(bare)["provenance"] is None and _record.compare(bare, p, keys=["recall"]) == []
