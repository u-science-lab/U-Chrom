import fire
from vispy import app
import PyQt5

from .main_window import MainWindow
from nucbox.io import read_particles


def read_and_show(*paths):
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    win = MainWindow()
    for i, path in enumerate(paths):
        if i > 0:
            win.add_canvas('h')
        df = read_particles(path)
        win.load_model(df)
        win.init_draw()
        win.update_view()
    win.show()
    app.run()


if __name__ == '__main__':
    fire.Fire(read_and_show)
