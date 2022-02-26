from PyQt5.QtWidgets import (QHBoxLayout, QLineEdit, QPushButton, QTextBrowser, QWidget, QLabel, 
                             QVBoxLayout, QCheckBox)
import pandas as pd

from .utils import pyqtsignal
from ...utils.genome import GenomeRange


class RangeList(QWidget):

    signal_item_changed = pyqtsignal(name="item_changed")
    signal_ok = pyqtsignal(name="ok")

    def __init__(self, title, chr_names=None):
        super().__init__()
        self.title = title
        self.init_UI()
        self.ranges = set()
        self.chr_names = chr_names

    def init_UI(self):
        l_reverse = QLabel("Reverse mode: not show the selected regions")
        self.reverse_ck = QCheckBox()
        reverse_hbox = QHBoxLayout()
        reverse_hbox.addWidget(l_reverse)
        reverse_hbox.addWidget(self.reverse_ck)
        l = QLabel("Input genome range, like: chr1:10000-200000")
        self.le = QLineEdit()
        self.le.returnPressed.connect(self.append)
        self.add_btn = QPushButton("Add")
        self.add_btn.pressed.connect(self.append)
        add_hbox = QHBoxLayout()
        add_hbox.addWidget(self.le, stretch=2)
        add_hbox.addWidget(self.add_btn, stretch=1)
        self.tb = QTextBrowser()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.pressed.connect(self.clear)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.pressed.connect(self.signal_ok)
        self.ok_btn.pressed.connect(self.close)
        hbox_btns = QHBoxLayout()
        hbox_btns.addWidget(self.clear_btn)
        hbox_btns.addWidget(self.ok_btn)
        vbox = QVBoxLayout()
        vbox.addWidget(l, 0)
        vbox.addLayout(add_hbox, 1)
        vbox.addWidget(self.tb, 2)
        vbox.addLayout(reverse_hbox, 3)
        vbox.addLayout(hbox_btns, 4)
        self.setLayout(vbox)
        self.setWindowTitle(self.title)
        self.setGeometry(300, 300, 300, 300)
        self._connect_change()

    def _connect_change(self):
        self.reverse_ck.toggled.connect(self.signal_item_changed)
        self.tb.textChanged.connect(self.signal_item_changed)

    def _disconnect_change(self):
        self.reverse_ck.toggled.disconnect()
        self.tb.textChanged.disconnect()

    def append(self, text=None):
        if text is None:
            text = self.le.text()
        try:
            gr = GenomeRange.parse_text(text, self.chr_names)
            if gr not in self.ranges:
                self.ranges.add(gr)
                self.tb.append(str(gr))
                self.le.setStyleSheet("")
        except Exception as e:
            print(f"{text} is not a valid genome range")
            print(str(e))
            self.le.setStyleSheet("border: 1px solid red;")

    def clear(self):
        self.ranges.clear()
        self.tb.clear()

    def setRanges(self, ranges, block_signal=False):
        if block_signal:
            self._disconnect_change()
        self.clear()
        for r in ranges:
            self.append(str(r))
        if block_signal:
            self._connect_change()

    def subset_dataframe(self, df: pd.DataFrame):
        res = []
        for range in list(self.ranges):
            sub_df = df[(df['chrom'] == range.chr) & (df['start'] >= range.start) & (df['end'] <= range.end)]
            res.append(sub_df)
        if res:
            res = pd.concat(res).drop_duplicates()
        else:
            res = pd.DataFrame(columns=df.columns)
        return res
