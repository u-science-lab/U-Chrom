"""``python -m uchrom_browser [PATH ...] [--host 127.0.0.1] [--port 8765] [--noopen_browser] [--atlas URL] [--hosted]``
or subcommands ``python -m uchrom_browser ctl ...`` / ``python -m uchrom_browser mcp ...``."""


_BOOL = ("true", "false", "1", "0", "yes", "no")


def _is_path(v):
    return isinstance(v, str) and v.lower() not in _BOOL


def main(*paths, host="127.0.0.1", port=8765, open_browser=True, atlas=None, hosted=False, **flags):
    """Serve the web browser on ``host:port`` with the given stores (``.chromdata.zarr`` / ``.cdz``, paths or URLs)
    and open a tab (``--noopen_browser`` to skip).  ``--atlas URL`` is the atlas the Open dialog lists (default: the
    public U-Chrom atlas; ``--atlas=`` for none).  ``--hosted`` is the mode of a public server (one session per
    visitor, only atlas datasets, no folder listing; see ``hosted.py``)."""
    # fire hands the token after a boolean flag to the flag: `--open_browser out.cdz` is open_browser='out.cdz',
    # `--noopen_browser out.cdz` is noopen_browser='out.cdz' (and open_browser stays True): either way it is a path
    if _is_path(open_browser):
        paths, open_browser = (open_browser, *paths), True
    if _is_path(hosted):
        paths, hosted = (hosted, *paths), True
    for name in ("noopen_browser", "no_open_browser"):
        if name in flags:
            v = flags.pop(name)
            if _is_path(v):
                paths = (v, *paths)
            open_browser = False
    if flags:
        raise SystemExit(f"unknown option(s): {', '.join('--' + k for k in flags)}")
    from . import serve

    serve(paths, host=host, port=port, open_browser=open_browser, atlas=atlas, hosted=bool(hosted))


def _cli(argv=None):
    """The ``uchrom-browser`` command (serves stores, or dispatches ``ctl`` / ``mcp`` subcommands)."""
    eff_argv = __import__("sys").argv[1:] if argv is None else list(argv)
    if eff_argv and eff_argv[0] == "mcp":
        from .mcp import _cli as mcp_cli

        mcp_cli(eff_argv[1:], prog="uchrom-browser mcp")
        return
    if eff_argv and eff_argv[0] == "ctl":
        from .cli import main as ctl_main

        raise SystemExit(ctl_main(eff_argv[1:], prog="uchrom-browser ctl"))
    import fire

    if argv is None:
        fire.Fire(main)
    else:
        fire.Fire(main, command=argv)


if __name__ == "__main__":
    _cli()
