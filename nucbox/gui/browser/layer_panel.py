from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QPushButton, QWidget, QLabel, QHBoxLayout, QVBoxLayout)


class LayerPanel(QWidget):

    def __init__(self, parent=None):
        super(LayerPanel, self).__init__(parent)

        self.list = QListWidget()

        self.subset_btn = QPushButton("Subset")
        self.del_btn = QPushButton("Delete")

        title_layout = QVBoxLayout()
        title_layout.addWidget(QLabel("<h2>Layers</h2>"))

        vbox_btns = QVBoxLayout()
        vbox_btns.addWidget(self.subset_btn)
        vbox_btns.addWidget(self.del_btn)
        vbox_btns.addStretch()

        hbox = QHBoxLayout()
        hbox.addWidget(self.list)
        hbox.addLayout(vbox_btns)

        vbox = QVBoxLayout()
        vbox.addLayout(title_layout)
        vbox.addLayout(hbox)

        self.setLayout(vbox)

