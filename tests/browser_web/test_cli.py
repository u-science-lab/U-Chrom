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
    monkeypatch.setattr(web, "serve", lambda p, host, port, open_browser: got.update(paths=p, open=open_browser))
    fire.Fire(cli.read_and_show, command=argv)
    assert got == {"paths": paths, "open": opened}


def test_unknown_option_is_an_error():
    with pytest.raises(SystemExit):
        fire.Fire(cli.read_and_show, command=["--web", "--bogus", "x"])
