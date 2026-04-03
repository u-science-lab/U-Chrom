import fire

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
    qapp.exec_()


if __name__ == '__main__':
    fire.Fire(read_and_show)
