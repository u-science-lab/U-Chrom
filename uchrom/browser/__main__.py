import fire
from PyQt5.QtCore import QTimer

from uchrom.io import read_particles
from .utils import get_qapp
from .main_window import MainWindow


def read_and_show(*paths, style='qdarkgraystyle'):
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
