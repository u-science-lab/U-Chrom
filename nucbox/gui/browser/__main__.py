import fire
from vispy import app

from .main_window import MainWindow
from nucbox.utils.io import read_particles
from .utils import get_qapp


def read_and_show(*paths, style='qdarkgraystyle'):
    qapp = get_qapp(style=style)
    win = MainWindow()
    for i, path in enumerate(paths):
        if i > 0:
            win.add_canvas('h')
        df = read_particles(path)
        win.load_model(df)
        win.init_draw()
    win.show()
    app.run()


if __name__ == '__main__':
    fire.Fire(read_and_show)
