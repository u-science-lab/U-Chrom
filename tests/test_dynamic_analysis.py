"""Unit tests for the dynamic_analysis sandbox.

Focus: malicious code is rejected at validation time, legitimate code compiles
and runs, timeouts and bad return types are caught.
"""
import numpy as np
import pandas as pd
import pytest

from webapp.backend.dynamic_analysis import (
    AnalysisValidationError,
    SAFE_BUILTINS,
    compile_analysis,
    run_with_timeout,
    validate_source,
)


GOOD_CODE = '''
def analyze(cd, chrom, **params):
    n = cd.coords.shape[0]
    starts = cd.spots["start"].to_numpy()
    rg = np.sqrt((cd.coords ** 2).sum(axis=1))
    return pd.DataFrame({
        "chrom": [chrom] * n,
        "start": starts,
        "end": starts + 1,
        "rg": rg,
    })
'''


# ---------------------------------------------------------------------------
# Malicious / invalid source is rejected
# ---------------------------------------------------------------------------

MALICIOUS = {
    "import_os": "import os\ndef analyze(cd, chrom, **p):\n    return pd.DataFrame()",
    "from_import": "from os import system\ndef analyze(cd, chrom, **p):\n    return pd.DataFrame()",
    "open_file": "def analyze(cd, chrom, **p):\n    open('/etc/passwd')\n    return pd.DataFrame()",
    "dunder_class": "def analyze(cd, chrom, **p):\n    return ().__class__.__bases__",
    "subclasses_chain": (
        "def analyze(cd, chrom, **p):\n"
        "    return ().__class__.__bases__[0].__subclasses__()"
    ),
    "eval": "def analyze(cd, chrom, **p):\n    return eval('1+1')",
    "exec": "def analyze(cd, chrom, **p):\n    exec('x=1')\n    return pd.DataFrame()",
    "getattr": "def analyze(cd, chrom, **p):\n    return getattr(cd, 'coords')",
    "compile": "def analyze(cd, chrom, **p):\n    return compile('1', '<s>', 'eval')",
    "import_builtin": "def analyze(cd, chrom, **p):\n    return __import__('os')",
    "globals": "def analyze(cd, chrom, **p):\n    return globals()",
    "lambda": "analyze = lambda cd, chrom, **p: pd.DataFrame()",
    "with_open": "def analyze(cd, chrom, **p):\n    with open('x') as f:\n        return pd.DataFrame()",
    "global_stmt": "def analyze(cd, chrom, **p):\n    global x\n    return pd.DataFrame()",
    "dunder_globals": "def analyze(cd, chrom, **p):\n    return analyze.__globals__",
    "no_analyze": "def helper(cd, chrom, **p):\n    return pd.DataFrame()",
    "empty": "",
    "syntax_error": "def analyze(cd, chrom, **p)\n    return pd",
}


@pytest.mark.parametrize("src", list(MALICIOUS.values()), ids=list(MALICIOUS))
def test_malicious_rejected(src):
    with pytest.raises(AnalysisValidationError):
        validate_source(src)


@pytest.mark.parametrize("src", list(MALICIOUS.values()), ids=list(MALICIOUS))
def test_malicious_rejected_at_compile(src):
    with pytest.raises(AnalysisValidationError):
        compile_analysis("evil", src)


def test_safe_builtins_excludes_dangerous():
    for forbidden in ("__import__", "open", "eval", "exec", "getattr", "compile", "globals"):
        assert forbidden not in SAFE_BUILTINS
    for ok in ("len", "range", "sum", "sorted", "min", "max"):
        assert ok in SAFE_BUILTINS


# ---------------------------------------------------------------------------
# Legitimate source compiles + runs
# ---------------------------------------------------------------------------

class _FakeCD:
    def __init__(self, n=20):
        self.coords = np.random.randn(n, 3).astype(np.float32)
        self.spots = pd.DataFrame({
            "chrom": ["chr1"] * n,
            "start": np.arange(n) * 100_000,
            "end": (np.arange(n) + 1) * 100_000,
        })


def test_good_compiles():
    compiled = compile_analysis(
        "rg", GOOD_CODE,
        chromosome_field="chrom", genomic_fields=["start", "end"],
        suggested_mark="line",
    )
    assert compiled.name == "rg"
    assert compiled.chromosome_field == "chrom"
    assert compiled.genomic_fields == ("start", "end")
    assert compiled.suggested_mark == "line"
    assert callable(compiled.fn)


def test_good_runs_returns_dataframe():
    compiled = compile_analysis("rg", GOOD_CODE)
    cd = _FakeCD(n=20)
    df = run_with_timeout(compiled, cd, "chr1", params={}, timeout_s=5.0)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 20
    assert list(df["chrom"].unique()) == ["chr1"]
    assert "rg" in df.columns


def test_np_pd_prebound_no_import_needed():
    src = (
        "def analyze(cd, chrom, **params):\n"
        "    arr = np.arange(3)\n"
        "    return pd.DataFrame({'chrom': [chrom]*3, 'start': arr, 'end': arr+1})\n"
    )
    compiled = compile_analysis("np_pd", src)
    df = run_with_timeout(compiled, _FakeCD(), "chr1", timeout_s=5.0)
    assert len(df) == 3


# ---------------------------------------------------------------------------
# Timeout + bad return type
# ---------------------------------------------------------------------------

def test_timeout_raises():
    src = (
        "def analyze(cd, chrom, **params):\n"
        "    total = 0\n"
        "    while True:\n"
        "        total = total + 1\n"
    )
    compiled = compile_analysis("infinite", src)
    with pytest.raises(TimeoutError):
        run_with_timeout(compiled, _FakeCD(), "chr1", timeout_s=0.5)


def test_non_dataframe_return_rejected():
    src = (
        "def analyze(cd, chrom, **params):\n"
        "    return [1, 2, 3]\n"
    )
    compiled = compile_analysis("badret", src)
    with pytest.raises(TypeError):
        run_with_timeout(compiled, _FakeCD(), "chr1", timeout_s=5.0)


def test_runtime_error_propagates():
    src = (
        "def analyze(cd, chrom, **params):\n"
        "    return pd.DataFrame({'x': [1]})[0]['missing']\n"
    )
    compiled = compile_analysis("boom", src)
    with pytest.raises(Exception):
        run_with_timeout(compiled, _FakeCD(), "chr1", timeout_s=5.0)
