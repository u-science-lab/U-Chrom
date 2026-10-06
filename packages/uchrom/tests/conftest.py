"""Shared pytest configuration.

Markers
-------
slow     : > ~10 s or needs large downloaded data.  CI runs ``-m "not slow and not gpu"``.
gpu      : needs CUDA / MPS.
browser  : needs PyQt5 + PyVista and a GL-capable display (CI uses xvfb).
"""
import os

# Headless matplotlib.  Qt / VTK are *not* forced off-screen here: VTK's
# QtInteractor needs a real GL surface (Qt's "offscreen" platform segfaults
# it), so browser tests run in a subprocess under the native / xvfb display.
os.environ.setdefault("MPLBACKEND", "Agg")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long-running or large-data test")
    config.addinivalue_line("markers", "gpu: requires a CUDA or MPS device")
    config.addinivalue_line("markers", "browser: requires PyQt5 + PyVista")
