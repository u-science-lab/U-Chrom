from PyQt5.QtWidgets import (QHBoxLayout, QLineEdit, QPushButton, QTextBrowser, QWidget, QLabel, 
                             QVBoxLayout, QCheckBox)

from .utils import pyqtsignal


class GenomeRange(object):
    SUPER_MAX = 100000000000000000000

    def __init__(self, chr, start=0, end=SUPER_MAX):
        self.chr = chr
        if (start is not None) and (end is not None):
            self.start = int(start)
            self.end = int(end)
            assert self.end > self.start >= 0

    @staticmethod
    def parse_text(text, valid_chr_names=None):
        if ":" in text:
            assert "-" in text
            tp1 = text.split(":")
            chr = tp1[0]
            start, end = tp1[1].split("-")
            gr = GenomeRange(chr, start, end)
        else:
            gr = GenomeRange(text)
        if valid_chr_names is not None:
            assert gr.chr in valid_chr_names
        return gr

    def __str__(self):
        if (self.start == 0) and (self.end == self.SUPER_MAX):
            return self.chr
        else:
            return f"{self.chr}:{self.start}-{self.end}"

    def __repr__(self):
        return f"GenomeRange({str(self)})"

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __gt__(self, other):
        return (self.start > other.start) and (self.end > other.end)

    def __lt__(self, other):
        return (self.start < other.start) and (self.end < other.end)


class RangeList(QWidget):

    signal_item_changed = pyqtsignal(name="item_changed")

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
        vbox = QVBoxLayout()
        vbox.addWidget(l, 0)
        vbox.addLayout(add_hbox, 1)
        vbox.addWidget(self.tb, 2)
        vbox.addLayout(reverse_hbox, 3)
        vbox.addWidget(self.clear_btn, 4)
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