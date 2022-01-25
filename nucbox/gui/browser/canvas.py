from vispy import scene

from .canvas_control import CanvasControl


class Canvas(scene.SceneCanvas):

    def __init__(self):
        scene.SceneCanvas.__init__(self, keys=None)
        self.size = 800, 600
        self.unfreeze()

        self.view = self.central_widget.add_view()
        self.view.bgcolor = "#000000"
        self.view.camera = 'turntable'
        self.view.camera.distance = 50

        # Add a 3D axis to keep us oriented
        self.axis = scene.visuals.XYZAxis(parent=self.view.scene)
        self.axis.visible = False

        self.control_panel = CanvasControl(self)

        self.freeze()

