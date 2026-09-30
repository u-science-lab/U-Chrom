import fire


def read_and_show(*paths, style='qdarkgraystyle', web=False, host='127.0.0.1',
                  port=8765, open_browser=True):
    """Open structure files in the browser.

    Desktop (PyVista + Qt) by default; ``--web`` serves the web browser on
    ``host:port`` instead (``--noopen_browser`` to skip opening a tab).
    """
    # fire reads `--web out.cdz` as web='out.cdz': that value is a path too
    if isinstance(web, str) and web.lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
        paths, web = (web, *paths), True
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
