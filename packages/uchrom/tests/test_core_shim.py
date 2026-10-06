"""uchrom.core is the former name of the chromdata package: old imports keep working, with a DeprecationWarning."""

import importlib
import sys
import warnings

import pytest


def test_uchrom_core_is_chromdata():
    for name in [m for m in sys.modules if m == "uchrom.core" or m.startswith("uchrom.core.")]:
        del sys.modules[name]
    with pytest.warns(DeprecationWarning, match="chromdata"):
        core = importlib.import_module("uchrom.core")
    import chromdata
    import chromdata.catalog
    import chromdata.zarrcd
    import uchrom.convention

    assert core.ChromData is chromdata.ChromData
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from uchrom.core.zarrcd import ZARR_FORMAT_VERSION, container_kind  # noqa: F401  (private names too)
        import uchrom.core.atlas as atlas
        import uchrom.core.convention as convention
    assert importlib.import_module("uchrom.core.zarrcd") is chromdata.zarrcd
    assert core.cdata.ChromData is chromdata.ChromData
    assert atlas is chromdata.catalog and convention is uchrom.convention


def test_settings_are_shared():
    import chromdata
    import uchrom

    assert uchrom.settings is chromdata.settings
    old = chromdata.settings._memory_budget
    try:
        uchrom.settings.memory_budget = "1GB"
        assert chromdata.settings.memory_budget == 1 << 30
    finally:
        chromdata.settings._memory_budget = old
