import os.path as osp
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel)
from PyQt5 import QtSvg


HERE = osp.dirname(osp.abspath(__file__))


class About(QWidget):

    def __init__(self):
        super().__init__()
        self.title = "About"
        self.init_UI()

    def init_UI(self):
        import uchrom
        vbox = QVBoxLayout()
        svg = QtSvg.QSvgWidget(osp.join(HERE, "../uc.svg"))
        svg.setGeometry(200, 200, 200, 200)
        vbox.addWidget(svg)
        vbox.addWidget(QLabel(f"U-Chrom version: {uchrom.__version__}"))
        l = QLabel('Project page: <a href="https://github.com/Nanguage/U-Chrom">github.com/Nanguage/U-Chrom</a>')
        l.setOpenExternalLinks(True)
        vbox.addWidget(l)
        self.setLayout(vbox)
        self.setWindowTitle(self.title)
        self.setGeometry(300, 300, 300, 300)
