#!/usr/bin/env python
"""
Test PyVista renderer with real data files
"""

import sys
from PyQt5.QtWidgets import QApplication
import qdarkgraystyle

from nucbox.gui.browser.main_window_pyvista import MainWindowPyVista


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkgraystyle.load_stylesheet())
    
    # Create main window with PyVista renderer
    window = MainWindowPyVista()
    window.setWindowTitle('NucBrowser - PyVista Renderer')
    
    # Load real data file
    import os
    if os.path.exists('wt.csv'):
        print("Loading wt.csv with PyVista renderer...")
        window.load_particles('wt.csv')
    elif os.path.exists('pi.csv'):
        print("Loading pi.csv with PyVista renderer...")
        window.load_particles('pi.csv')
    else:
        print("No data files found. Please provide wt.csv or pi.csv")
    
    window.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())