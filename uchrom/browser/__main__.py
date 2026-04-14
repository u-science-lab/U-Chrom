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

    # Sync camera viewing angle after PyVista finishes deferred initialization
    all_canvases = list(win.get_all_canvas())
    if len(all_canvases) > 1:
        def sync_camera_angles():
            import numpy as np
            ref_cam = all_canvases[0].backend.plotter.camera
            ref_pos = np.array(ref_cam.position)
            ref_focal = np.array(ref_cam.focal_point)
            ref_dir = ref_pos - ref_focal
            ref_dir = ref_dir / (np.linalg.norm(ref_dir) + 1e-12)
            ref_up = np.array(ref_cam.up)

            for canvas in all_canvases[1:]:
                cam = canvas.backend.plotter.camera
                focal = np.array(cam.focal_point)
                pos = np.array(cam.position)
                dist = np.linalg.norm(pos - focal)
                # Keep own focal point and distance, match viewing direction
                cam.position = tuple(focal + ref_dir * dist)
                cam.up = tuple(ref_up)
                canvas.backend.plotter.reset_camera_clipping_range()
                canvas.backend.render()
        QTimer.singleShot(300, sync_camera_angles)

    qapp.exec_()


if __name__ == '__main__':
    fire.Fire(read_and_show)
