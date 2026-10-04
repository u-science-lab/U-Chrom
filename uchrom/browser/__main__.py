import fire


_BOOL = ('true', 'false', '1', '0', 'yes', 'no')


def _is_path(v):
    return isinstance(v, str) and v.lower() not in _BOOL


def read_and_show(*paths, style='qdarkgraystyle', web=False, host='127.0.0.1',
                  port=8765, open_browser=True, **flags):
    """Open structure files in the browser.

    Desktop (PyVista + Qt) by default; ``--web`` serves the web browser on
    ``host:port`` instead (``--noopen_browser`` to skip opening a tab).
    """
    # fire hands the token after a boolean flag to the flag: `--web out.cdz` is web='out.cdz',
    # `--open_browser out.cdz` is open_browser='out.cdz', `--noopen_browser out.cdz` is
    # noopen_browser='out.cdz' (and open_browser stays True): in every case the value is a path
    if _is_path(web):
        paths, web = (web, *paths), True
    if _is_path(open_browser):
        paths, open_browser = (open_browser, *paths), True
    for name in ('noopen_browser', 'no_open_browser'):
        if name in flags:
            v = flags.pop(name)
            if _is_path(v):
                paths = (v, *paths)
            open_browser = False
    if flags:
        raise SystemExit(f"unknown option(s): {', '.join('--' + k for k in flags)}")
    if web:
        from .web import serve
        serve(paths, host=host, port=port, open_browser=open_browser)
        return

    from PyQt5.QtCore import QTimer

    from uchrom.io import read_particles
    from .utils import get_qapp
    from .main_window import MainWindow

    qapp = get_qapp(style=style)

    win = MainWindow()
    for i, path in enumerate(paths):
        if i > 0:
            win.add_canvas('h')
        df = read_particles(path)
        win.load_model(df, path)
        win.init_draw()

    win.show()

    # Sync camera across all canvases after PyVista finishes initialization
    all_canvases = list(win.get_all_canvas())
    if len(all_canvases) > 1:
        def sync_cameras():
            ref = all_canvases[0].backend.plotter
            ref.reset_camera()
            state = all_canvases[0].backend.get_camera_state()
            for canvas in all_canvases[1:]:
                canvas.backend.plotter.reset_camera()
                canvas.backend.set_camera_state(state)
                canvas.backend.render()
        QTimer.singleShot(500, sync_cameras)

    qapp.exec_()


if __name__ == '__main__':
    fire.Fire(read_and_show)
