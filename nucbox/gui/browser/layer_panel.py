from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QWidget, QLabel, QGridLayout, QVBoxLayout)


class LayerPanel(QWidget):

    def __init__(self, parent=None):
        super(LayerPanel, self).__init__(parent)

        self.list = QListWidget()
        QListWidgetItem("first", self.list)
        QListWidgetItem("second", self.list)

        title_layout = QVBoxLayout()
        title_layout.addWidget(QLabel("<h2>Layers</h2>"))

        vbox = QVBoxLayout()
        vbox.addLayout(title_layout)
        vbox.addWidget(self.list)
        vbox.addStretch(1)
        self.setLayout(vbox)
