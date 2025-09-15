import os
import fire
from vispy import app

# Check if we should use the new backend-aware implementation
use_new_backend = os.environ.get('NUCBROWSER_BACKEND', 'pyvista').lower() in ['pyvista']

if use_new_backend:
    from .main_window_new import MainWindow
else:
    from .main_window import MainWindow

from nucbox.utils.io import read_particles
from .utils import get_qapp


def read_and_show(*paths, style='qdarkgraystyle', backend=None):
    qapp = get_qapp(style=style)
    
    # Use backend from parameter or environment variable
    if backend is None:
        backend = os.environ.get('NUCBROWSER_BACKEND', 'pyvista').lower()
    
    # Create window with appropriate backend support
    if use_new_backend:
        win = MainWindow(backend=backend)
    else:
        win = MainWindow()
    
    for i, path in enumerate(paths):
        if i > 0:
            win.add_canvas('h')
        df = read_particles(path)
        win.load_model(df, path)
        win.init_draw()
    win.show()
    app.run()


if __name__ == '__main__':
    fire.Fire(read_and_show)
