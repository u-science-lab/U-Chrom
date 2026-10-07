"""Shared pytest configuration.

Markers
-------
slow     : > ~10 s or needs large downloaded data.  CI runs ``-m "not slow and not gpu"``.
gpu      : needs CUDA / MPS.
"""
import os

# Headless matplotlib.
os.environ.setdefault("MPLBACKEND", "Agg")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long-running or large-data test")
    config.addinivalue_line("markers", "gpu: requires a CUDA or MPS device")
