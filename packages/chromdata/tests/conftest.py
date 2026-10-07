"""Markers: ``slow`` (> ~10 s or large downloaded data)."""


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long-running or large-data test")
