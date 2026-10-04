"""`python -m uchrom.browser`: fire gives the token after a boolean flag to the flag; it is a path."""

import fire
import pytest

from uchrom.browser import __main__ as cli


@pytest.mark.parametrize("argv, paths, opened", [
    (["--web", "--port", "1", "--noopen_browser", "a.zarr"], ("a.zarr",), False),
    (["--open_browser", "a.zarr", "--web"], ("a.zarr",), True),
    (["--web", "a.zarr", "--open_browser=False"], ("a.zarr",), False),
    (["a.zarr", "--web"], ("a.zarr",), True),
])
def test_paths_next_to_boolean_flags(monkeypatch, argv, paths, opened):
    import uchrom.browser.web as web

    got = {}
    monkeypatch.setattr(web, "serve", lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(paths=p, open=open_browser, atlas=atlas))
    fire.Fire(cli.read_and_show, command=argv)
    assert got == {"paths": paths, "open": opened, "atlas": None}


def test_unknown_option_is_an_error():
    with pytest.raises(SystemExit):
        fire.Fire(cli.read_and_show, command=["--web", "--bogus", "x"])


def test_atlas_option(monkeypatch):
    import uchrom.browser.web as web

    got = {}
    monkeypatch.setattr(web, "serve", lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(paths=p, atlas=atlas, hosted=hosted))
    fire.Fire(cli.read_and_show, command=["a.zarr", "--web", "--atlas", "https://x.example/atlas"])
    assert got["paths"] == ("a.zarr",) and got["atlas"] == "https://x.example/atlas"
    fire.Fire(cli.read_and_show, command=["--web", "--atlas="])
    assert got["atlas"] == ""


def test_hosted_flag(monkeypatch):
    import uchrom.browser.web as web

    got = {}
    monkeypatch.setattr(web, "serve", lambda p, host, port, open_browser, atlas=None, hosted=False: got.update(
        paths=p, host=host, port=port, hosted=hosted))
    fire.Fire(cli.read_and_show, command=["--web", "--hosted", "--host=0.0.0.0", "--port=8000", "--open_browser=False"])
    assert got == {"paths": (), "host": "0.0.0.0", "port": 8000, "hosted": True}
