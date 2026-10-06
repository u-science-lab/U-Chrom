"""The native engine is ``uchrom_recon``; a build from before the rename (``uchrom_nucdyn``) still loads."""

import sys
import types

import pytest

from uchrom.recon.sc.nucdyn.native import _engine


def test_former_name_is_used_when_the_engine_is_missing(monkeypatch):
    old = types.ModuleType("uchrom_nucdyn")
    monkeypatch.setitem(sys.modules, "uchrom_recon", None)      # import raises ImportError
    monkeypatch.setitem(sys.modules, "uchrom_nucdyn", old)
    assert _engine() is old


def test_neither_name_raises_with_the_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "uchrom_recon", None)
    monkeypatch.setitem(sys.modules, "uchrom_nucdyn", None)
    with pytest.raises(ImportError, match="uchrom-recon"):
        _engine()
