#!/usr/bin/env python
"""
NucBox 3D Genome Browser with multiple rendering backends.
Enhanced with PyVista for improved performance and rendering quality.
"""

import sys
import argparse
import os
from vispy import app
import fire

from .main_window import MainWindow
from nucbox.utils.io import read_particles
from .utils import get_qapp


def read_and_show_legacy(*paths, style='qdarkgraystyle'):
    """Legacy VisPy-based viewer (kept for compatibility)"""
    qapp = get_qapp(style=style)
    win = MainWindow()
    for i, path in enumerate(paths):
        if i > 0:
            win.add_canvas('h')
        df = read_particles(path)
        win.load_model(df, path)
        win.init_draw()
    win.show()
    app.run()


def main():
    """Enhanced main function with renderer selection"""
    parser = argparse.ArgumentParser(
        description='NucBox 3D Genome Browser - Visualize chromosome structures',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View with PyVista renderer (recommended for performance)
  python -m nucbox.gui.browser data.csv --renderer pyvista
  
  # View with VisPy renderer (legacy)
  python -m nucbox.gui.browser data.csv --renderer vispy
  
  # Use tube style with custom width
  python -m nucbox.gui.browser data.csv --style tube --width 3.0
        """
    )
    
    parser.add_argument('csv_files', nargs='*', 
                        help='CSV file(s) with particle positions')
    parser.add_argument('--renderer', choices=['vispy', 'pyvista'], 
                        default='pyvista',
                        help='Choose rendering backend (default: pyvista)')
    parser.add_argument('--style', choices=['line', 'tube', 'points'], 
                        default='tube',
                        help='Rendering style (default: tube)')
    parser.add_argument('--width', type=float, default=2.0,
                        help='Line/tube width (default: 2.0)')
    parser.add_argument('--legacy', action='store_true',
                        help='Use legacy fire interface')
    
    args = parser.parse_args()
    
    ## Handle legacy fire interface
    #if args.legacy or (len(sys.argv) > 1 and not sys.argv[1].startswith('-')):
    #    # Fall back to legacy behavior for backward compatibility
    #    fire.Fire(read_and_show_legacy)
    #    return
    
    # Use new enhanced interface
    if args.renderer == 'pyvista':
        print("Using PyVista renderer (optimized for performance)")
        try:
            from .main_window_pyvista import MainWindowPyVista
            from PyQt5.QtWidgets import QApplication
            import qdarkgraystyle
            
            app = QApplication(sys.argv)
            app.setStyleSheet(qdarkgraystyle.load_stylesheet())
            
            window = MainWindowPyVista()
            window.show()
            
            # Load files if provided
            for csv_file in args.csv_files:
                if os.path.exists(csv_file):
                    print(f"Loading {csv_file}...")
                    window.load_particles(csv_file)
                    window.set_render_style(args.style)
                    window.set_render_width(args.width)
                else:
                    print(f"Warning: File '{csv_file}' not found")
            
            sys.exit(app.exec_())
            
        except ImportError:
            print("PyVista not installed, falling back to VisPy renderer")
            print("Install with: pip install pyvista pyvistaqt")
            args.renderer = 'vispy'
    
    if args.renderer == 'vispy':
        print("Using VisPy renderer")
        # Use the legacy function with the provided files
        if args.csv_files:
            read_and_show_legacy(*args.csv_files)
        else:
            read_and_show_legacy()


if __name__ == '__main__':
    # Check if being called with fire-style arguments
    main()
