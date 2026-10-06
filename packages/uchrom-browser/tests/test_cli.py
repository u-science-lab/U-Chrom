"""`python -m uchrom_browser` / `uchrom-browser`: fire gives the token after a boolean flag to the flag; it is a path."""

import fire
import pytest

import uchrom_browser
from uchrom_browser import __main__ as cli


@pytest.mark.parametrize("argv, paths, opened", [
    (["--port", "1", "--noopen_browser", "a.zarr"], ("a.zarr",), False),
    (["--open_browser", "a.zarr"], ("a.zarr",), True),
    (["a.zarr", "--open_browser=False"], ("a.zarr",), False),
    (["a.zarr", "b.cdz"], ("a.zarr", "b.cdz"), True),
])
def test_paths_next_to_boolean_flags(monkeypatch, argv, paths, opened):
    got = {}
    monkeypatch.setattr(uchrom_browser, "serve",
                        lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(paths=p, open=open_browser))
    fire.Fire(cli.main, command=argv)
    assert got == {"paths": paths, "open": opened}


def test_hosted_and_atlas(monkeypatch):
    got = {}
    monkeypatch.setattr(uchrom_browser, "serve",
                        lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(atlas=atlas, hosted=hosted))
    fire.Fire(cli.main, command=["--hosted", "--atlas", "https://x.test", "--noopen_browser"])
    assert got == {"atlas": "https://x.test", "hosted": True}


def test_unknown_option_is_an_error():
    with pytest.raises(SystemExit):
        fire.Fire(cli.main, command=["--bogus", "x"])
