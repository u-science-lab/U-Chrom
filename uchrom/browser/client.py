"""``uchrom.browser.client`` is :mod:`uchrom_browser.client` (``connect()``: drive an open web browser from Python)."""

import sys

try:
    import uchrom_browser.client as _client
except ModuleNotFoundError as exc:          # pragma: no cover - depends on the installation
    raise ImportError('connect() is part of the web browser, the uchrom-browser package: pip install "u-chrom[web]"') from exc

sys.modules[__name__] = _client
