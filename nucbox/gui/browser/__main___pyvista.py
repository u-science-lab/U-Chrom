#!/usr/bin/env python
"""
Enhanced NucBox browser with PyVista rendering option.
Usage:
    python -m nucbox.gui.browser [--renderer=pyvista|vispy] <csv_file>
"""

import sys
import argparse
from PyQt5.QtWidgets import QApplication
import qdarkgraystyle

from .main_window import MainWindow
from .main_window_pyvista import MainWindowPyVista


def main():
    parser = argparse.ArgumentParser(description='NucBox 3D Genome Browser')
    parser.add_argument('csv_file', nargs='?', help='CSV file with particle positions')
    parser.add_argument('--renderer', choices=['vispy', 'pyvista'], default='pyvista',
                        help='Choose rendering backend (default: pyvista for better performance)')
    parser.add_argument('--style', choices=['line', 'tube', 'points'], default='tube',
                        help='Rendering style (default: tube)')
    parser.add_argument('--width', type=float, default=2.0,
                        help='Line/tube width (default: 2.0)')
    
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkgraystyle.load_stylesheet_pyqt5())
    
    # Choose renderer based on argument
    if args.renderer == 'pyvista':
        print("Using PyVista renderer (optimized for performance and quality)")
        window = MainWindowPyVista()
    else:
        print("Using VisPy renderer")
        window = MainWindow()
    
    window.show()
    
    # Load file if provided
    if args.csv_file:
        try:
            if args.renderer == 'pyvista':
                window.load_particles(args.csv_file)
                # Set initial style if using PyVista
                if hasattr(window, 'set_render_style'):
                    window.set_render_style(args.style)
                    window.set_render_width(args.width)
        except Exception as e:
            print(f"Error loading file: {e}")
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()