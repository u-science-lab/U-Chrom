#!/usr/bin/env python
"""
Test script for PyVista renderer with sample data.
"""

import sys
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import QApplication
import qdarkgraystyle

from nucbox.gui.browser.main_window_pyvista import MainWindowPyVista
from nucbox.gui.browser.renderer_pyvista_optimized import OptimizedPyVistaRenderer


def generate_sample_data(n_chromosomes=2, points_per_chr=100):
    """Generate sample chromosome data for testing"""
    data = []
    
    for chr_idx in range(n_chromosomes):
        # Generate helix-like structure for each chromosome
        t = np.linspace(0, 4*np.pi, points_per_chr)
        radius = 10
        
        x = radius * np.cos(t) + chr_idx * 30
        y = radius * np.sin(t)
        z = t * 3
        
        for i in range(points_per_chr):
            data.append({
                'chrom': f'chr{chr_idx+1}',
                'start': i * 1000,
                'end': (i+1) * 1000,
                'x': x[i],
                'y': y[i],
                'z': z[i]
            })
    
    return pd.DataFrame(data)


def test_basic_renderer():
    """Test basic PyVista renderer"""
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkgraystyle.load_stylesheet_pyqt5())
    
    # Create main window
    window = MainWindowPyVista()
    
    # Generate and load sample data
    df = generate_sample_data(n_chromosomes=3, points_per_chr=200)
    
    # Save sample data for testing (with index as expected by read_particles)
    df.to_csv('test_chromatin_data.csv', index=True)
    
    # Load the data
    window.load_particles('test_chromatin_data.csv')
    
    # Show window
    window.show()
    
    return app.exec_()


def test_optimized_renderer():
    """Test optimized PyVista renderer with advanced features"""
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkgraystyle.load_stylesheet_pyqt5())
    
    from PyQt5.QtWidgets import QMainWindow, QComboBox, QPushButton, QVBoxLayout, QWidget, QHBoxLayout
    
    class TestWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Optimized PyVista Renderer Test")
            self.resize(1200, 800)
            
            # Central widget
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            
            # Control panel
            controls = QHBoxLayout()
            
            # Style selector
            self.style_combo = QComboBox()
            self.style_combo.addItems(['tube', 'line', 'points', 'ribbon', 'surface'])
            self.style_combo.currentTextChanged.connect(self.update_rendering)
            controls.addWidget(self.style_combo)
            
            # Quality preset
            self.quality_combo = QComboBox()
            self.quality_combo.addItems(['low', 'medium', 'high', 'ultra'])
            self.quality_combo.setCurrentText('high')
            self.quality_combo.currentTextChanged.connect(self.set_quality)
            controls.addWidget(self.quality_combo)
            
            # Animation toggle
            self.anim_button = QPushButton("Toggle Animation")
            self.anim_button.clicked.connect(self.toggle_animation)
            controls.addWidget(self.anim_button)
            
            layout.addLayout(controls)
            
            # Renderer
            self.renderer = OptimizedPyVistaRenderer()
            layout.addWidget(self.renderer)
            
            # Load sample data
            self.load_sample_data()
            
            self.animation_enabled = False
            
        def load_sample_data(self):
            # Generate sample data
            n_points = 500
            t = np.linspace(0, 8*np.pi, n_points)
            
            # Create double helix
            radius1 = 10
            radius2 = 10
            
            x1 = radius1 * np.cos(t)
            y1 = radius1 * np.sin(t)
            z1 = t * 2
            
            x2 = radius2 * np.cos(t + np.pi)
            y2 = radius2 * np.sin(t + np.pi)
            z2 = t * 2
            
            # Combine into positions
            self.positions1 = np.column_stack([x1, y1, z1])
            self.positions2 = np.column_stack([x2, y2, z2])
            
            # Generate gradient colors
            from matplotlib import cm
            cmap = cm.get_cmap('rainbow')
            t_norm = t / t.max()
            self.colors1 = cmap(t_norm)[:, :3]
            self.colors2 = cmap(1 - t_norm)[:, :3]
            
            # Initial rendering
            self.update_rendering()
            
        def update_rendering(self):
            # Clear existing actors
            self.renderer.plotter.clear()
            
            style = self.style_combo.currentText()
            
            # Render both helices
            self.renderer.render_chromatin_optimized(
                self.positions1, self.colors1, style=style, width=2.0
            )
            self.renderer.render_chromatin_optimized(
                self.positions2, self.colors2, style=style, width=2.0
            )
            
            # Add labels
            self.renderer.plotter.add_text("DNA Double Helix - PyVista Optimized", 
                                          position='upper_left', font_size=12)
            self.renderer.plotter.add_text(f"Style: {style}", 
                                          position='lower_left', font_size=10)
            
            self.renderer.plotter.reset_camera()
            
        def set_quality(self):
            quality = self.quality_combo.currentText()
            self.renderer.set_quality_preset(quality)
            self.renderer.plotter.render()
            
        def toggle_animation(self):
            if not self.animation_enabled:
                self.renderer.enable_animation(rotation_speed=2.0)
                self.animation_enabled = True
                self.anim_button.setText("Stop Animation")
            else:
                if hasattr(self.renderer, 'animation_timer'):
                    self.renderer.animation_timer.stop()
                self.animation_enabled = False
                self.anim_button.setText("Toggle Animation")
    
    window = TestWindow()
    window.show()
    
    return app.exec_()


def benchmark_comparison():
    """Compare rendering performance between VisPy and PyVista"""
    import time
    
    print("Rendering Performance Benchmark")
    print("=" * 50)
    
    # Generate large dataset
    sizes = [100, 500, 1000, 5000, 10000]
    
    for size in sizes:
        print(f"\nDataset size: {size} points")
        
        # Generate data
        t = np.linspace(0, 8*np.pi, size)
        x = 10 * np.cos(t)
        y = 10 * np.sin(t)
        z = t * 2
        positions = np.column_stack([x, y, z])
        
        # Benchmark PyVista rendering
        app = QApplication(sys.argv)
        renderer = OptimizedPyVistaRenderer()
        
        start_time = time.time()
        renderer.render_chromatin_optimized(positions, 'red', style='tube', width=2.0)
        renderer.plotter.show(auto_close=False, interactive=False)
        pyvista_time = time.time() - start_time
        
        print(f"  PyVista render time: {pyvista_time:.3f}s")
        
        renderer.plotter.close()
        app.quit()
        
        # Calculate FPS estimate
        estimated_fps = 1.0 / pyvista_time if pyvista_time > 0 else float('inf')
        print(f"  Estimated FPS: {estimated_fps:.1f}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test PyVista renderer')
    parser.add_argument('--mode', choices=['basic', 'optimized', 'benchmark'], 
                        default='optimized',
                        help='Test mode to run')
    
    args = parser.parse_args()
    
    if args.mode == 'basic':
        sys.exit(test_basic_renderer())
    elif args.mode == 'optimized':
        sys.exit(test_optimized_renderer())
    elif args.mode == 'benchmark':
        benchmark_comparison()