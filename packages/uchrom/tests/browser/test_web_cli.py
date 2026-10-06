"""`python -m uchrom.browser --web` (u-chrom's entry to the uchrom-browser package): fire gives the token
after a boolean flag to the flag; it is a path.  The deprecated aliases uchrom.browser.web / .client."""

import numpy as np
import pandas as pd
import fire
import pytest

pytest.importorskip("uchrom_browser")

from chromdata import ChromData  # noqa: E402

from uchrom.browser import __main__ as cli  # noqa: E402


@pytest.mark.parametrize("argv, paths, opened", [
    (["--web", "--port", "1", "--noopen_browser", "a.zarr"], ("a.zarr",), False),
    (["--open_browser", "a.zarr", "--web"], ("a.zarr",), True),
    (["--web", "a.zarr", "--open_browser=False"], ("a.zarr",), False),
    (["a.zarr", "--web"], ("a.zarr",), True),
])
def test_paths_next_to_boolean_flags(monkeypatch, argv, paths, opened):
    import uchrom_browser as web

    got = {}
    monkeypatch.setattr(web, "serve", lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(paths=p, open=open_browser, atlas=atlas))
    fire.Fire(cli.read_and_show, command=argv)
    assert got == {"paths": paths, "open": opened, "atlas": None}


def test_unknown_option_is_an_error():
    with pytest.raises(SystemExit):
        fire.Fire(cli.read_and_show, command=["--web", "--bogus", "x"])


def test_atlas_option(monkeypatch):
    import uchrom_browser as web

    got = {}
    monkeypatch.setattr(web, "serve", lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(paths=p, atlas=atlas, hosted=hosted))
    fire.Fire(cli.read_and_show, command=["a.zarr", "--web", "--atlas", "https://x.example/atlas"])
    assert got["paths"] == ("a.zarr",) and got["atlas"] == "https://x.example/atlas"
    fire.Fire(cli.read_and_show, command=["--web", "--atlas="])
    assert got["atlas"] == ""


def test_hosted_flag(monkeypatch):
    import uchrom_browser as web

    got = {}
    monkeypatch.setattr(web, "serve", lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(
        paths=p, host=host, port=port, hosted=hosted))
    fire.Fire(cli.read_and_show, command=["--web", "--hosted", "--host=0.0.0.0", "--port=8000", "--open_browser=False"])
    assert got == {"paths": (), "host": "0.0.0.0", "port": 8000, "hosted": True}


def test_deprecated_aliases_are_the_package():
    import warnings

    import uchrom_browser
    import uchrom_browser.client
    import uchrom.browser as ub
    from uchrom.browser import client

    assert client is uchrom_browser.client and ub.connect is uchrom_browser.client.connect
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import importlib

        import uchrom.browser.web as web
        importlib.reload(web)
    assert web.server is uchrom_browser.server and any("deprecated" in str(x.message) for x in w)


def test_cli_serves_over_http(tmp_path):
    """`python -m uchrom.browser --web file` starts a working server."""
    import json
    import socket
    import subprocess
    import sys
    import time
    import urllib.request

    pytest.importorskip("uvicorn")
    path = tmp_path / "cli.chromdata.zarr"
    spots = pd.DataFrame({"chrom": ["chr1"] * 3, "start": [0, 10, 20],
                          "end": [10, 20, 30], "trace_id": ["a"] * 3})
    ChromData(np.zeros((3, 3)), spots).write(path)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uchrom.browser", str(path), "--web",
         f"--port={port}", "--noopen_browser"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        url = f"http://127.0.0.1:{port}/api/datasets"
        for _ in range(100):
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    datasets = json.load(r)
                break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail(proc.stdout.read().decode())
                time.sleep(0.1)
        else:
            pytest.fail("server did not come up")
        assert datasets[0]["name"] == "cli" and datasets[0]["n_spots"] == 3
    finally:
        proc.terminate()
        proc.wait(timeout=10)

