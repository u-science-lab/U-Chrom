"""
Optimized PyVista renderer with advanced features for high-performance 3D visualization.
"""

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel
from matplotlib import cm


class OptimizedPyVistaRenderer(QWidget):
    """High-performance PyVista renderer with optimizations"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_plotter()
        self.setup_performance_features()
        
    def setup_ui(self):
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
    def setup_plotter(self):
        """Initialize PyVista plotter with optimizations"""
        self.plotter = QtInteractor(self)
        self.layout.addWidget(self.plotter.interactor)
        
        # Performance optimizations
        self.plotter.set_background('black')
        self.plotter.enable_depth_peeling(10, 0.001)  # Better transparency
        self.plotter.enable_anti_aliasing()  # Smooth edges
        self.plotter.enable_shadows()  # Better depth perception
        
        # Setup camera
        self.plotter.camera_position = 'xy'
        self.plotter.camera.zoom(1.2)
        
        # Enable parallel projection for better visualization
        self.plotter.enable_parallel_projection()
        
        # Add ambient light for better visibility
        light = pv.Light(position=(1, 1, 1), light_type='scene light')
        self.plotter.add_light(light)
        
    def setup_performance_features(self):
        """Setup advanced performance features"""
        # Level of Detail (LOD) for large datasets
        self.use_lod = True
        self.lod_threshold = 10000  # Switch to simplified rendering above this point count
        
        # Occlusion culling
        self.use_occlusion_culling = True
        
        # Frustum culling
        self.use_frustum_culling = True
        
        # Mesh decimation for large datasets
        self.decimation_factor = 0.5
        
        # GPU acceleration settings
        self.plotter.ren_win.SetMultiSamples(4)  # Anti-aliasing samples
        
    def render_chromatin_optimized(self, positions, colors, style='tube', width=2.0):
        """Render chromatin with performance optimizations"""
        n_points = positions.shape[0]
        
        # Apply LOD if dataset is large
        if self.use_lod and n_points > self.lod_threshold:
            positions, colors = self._apply_lod(positions, colors)
            
        if style == 'tube':
            return self._render_tube_optimized(positions, colors, width)
        elif style == 'line':
            return self._render_line_optimized(positions, colors, width)
        elif style == 'points':
            return self._render_points_optimized(positions, colors, width)
        elif style == 'ribbon':
            return self._render_ribbon(positions, colors, width)
        elif style == 'surface':
            return self._render_surface(positions, colors, width)
            
    def _apply_lod(self, positions, colors):
        """Apply Level of Detail decimation"""
        # Simple decimation - take every nth point
        step = max(1, positions.shape[0] // self.lod_threshold)
        positions = positions[::step]
        if len(colors.shape) > 1:
            colors = colors[::step]
        return positions, colors
        
    def _render_tube_optimized(self, positions, colors, width):
        """Optimized tube rendering with GPU acceleration"""
        # Create spline with adaptive resolution
        n_points = min(1000, positions.shape[0] * 10)
        spline = pv.Spline(positions, n_points)
        
        # Create tube with optimized parameters
        tube = spline.tube(radius=width/2, n_sides=12)  # Reduced sides for performance
        
        # Apply vertex colors if gradient
        if len(colors.shape) > 1:
            # Interpolate colors for tube vertices
            tube_colors = self._interpolate_colors_fast(colors, tube.n_points)
            tube["colors"] = tube_colors
            actor = self.plotter.add_mesh(
                tube,
                scalars="colors",
                rgb=True,
                smooth_shading=True,
                opacity=1.0,
                pbr=True,  # Physically based rendering
                metallic=0.3,
                roughness=0.5
            )
        else:
            actor = self.plotter.add_mesh(
                tube,
                color=colors,
                smooth_shading=True,
                opacity=1.0,
                pbr=True,
                metallic=0.3,
                roughness=0.5
            )
        return actor
        
    def _render_line_optimized(self, positions, colors, width):
        """Optimized line rendering"""
        # Create polyline
        lines = self._create_polyline(positions)
        
        # Apply colors
        if len(colors.shape) > 1:
            lines["colors"] = colors
            actor = self.plotter.add_mesh(
                lines,
                scalars="colors",
                rgb=True,
                line_width=width,
                render_lines_as_tubes=True  # GPU-accelerated tube rendering
            )
        else:
            actor = self.plotter.add_mesh(
                lines,
                color=colors,
                line_width=width,
                render_lines_as_tubes=True
            )
        return actor
        
    def _render_points_optimized(self, positions, colors, width):
        """Optimized point cloud rendering"""
        point_cloud = pv.PolyData(positions)
        
        # Use GPU point sprites for better performance
        if len(colors.shape) > 1:
            point_cloud["colors"] = colors
            actor = self.plotter.add_mesh(
                point_cloud,
                scalars="colors",
                rgb=True,
                point_size=width * 2,
                render_points_as_spheres=True,
                lighting=True
            )
        else:
            actor = self.plotter.add_mesh(
                point_cloud,
                color=colors,
                point_size=width * 2,
                render_points_as_spheres=True,
                lighting=True
            )
        return actor
        
    def _render_ribbon(self, positions, colors, width):
        """Render as ribbon for better visualization of DNA structure"""
        # Create ribbon mesh
        spline = pv.Spline(positions, 1000)
        ribbon = spline.ribbon(width=width, normal=(0, 0, 1))
        
        if len(colors.shape) > 1:
            ribbon_colors = self._interpolate_colors_fast(colors, ribbon.n_points)
            ribbon["colors"] = ribbon_colors
            actor = self.plotter.add_mesh(
                ribbon,
                scalars="colors",
                rgb=True,
                smooth_shading=True,
                opacity=0.9
            )
        else:
            actor = self.plotter.add_mesh(
                ribbon,
                color=colors,
                smooth_shading=True,
                opacity=0.9
            )
        return actor
        
    def _render_surface(self, positions, colors, width):
        """Render as surface mesh for volume visualization"""
        # Create surface from point cloud
        point_cloud = pv.PolyData(positions)
        
        # Delaunay 3D to create volume
        volume = point_cloud.delaunay_3d(alpha=width*5)
        
        # Extract surface
        surface = volume.extract_geometry()
        
        if len(colors.shape) > 1:
            # Map colors to surface vertices
            surface["colors"] = self._map_colors_to_surface(positions, colors, surface)
            actor = self.plotter.add_mesh(
                surface,
                scalars="colors",
                rgb=True,
                smooth_shading=True,
                opacity=0.7
            )
        else:
            actor = self.plotter.add_mesh(
                surface,
                color=colors,
                smooth_shading=True,
                opacity=0.7
            )
        return actor
        
    def _create_polyline(self, points):
        """Create efficient polyline from points"""
        n_points = points.shape[0]
        cells = np.full((n_points - 1, 3), 2, dtype=np.int32)
        cells[:, 1] = np.arange(0, n_points - 1, dtype=np.int32)
        cells[:, 2] = np.arange(1, n_points, dtype=np.int32)
        return pv.PolyData(points, lines=cells)
        
    def _interpolate_colors_fast(self, colors, n_target):
        """Fast color interpolation using NumPy"""
        n_source = colors.shape[0]
        
        if n_source == n_target:
            return colors
            
        # Create interpolation indices
        indices = np.linspace(0, n_source - 1, n_target)
        indices_floor = np.floor(indices).astype(int)
        indices_ceil = np.minimum(indices_floor + 1, n_source - 1)
        
        # Interpolation weights
        weights = indices - indices_floor
        weights = weights.reshape(-1, 1)
        
        # Interpolate colors
        colors_floor = colors[indices_floor]
        colors_ceil = colors[indices_ceil]
        interpolated = colors_floor * (1 - weights) + colors_ceil * weights
        
        return interpolated
        
    def _map_colors_to_surface(self, orig_points, orig_colors, surface):
        """Map colors from original points to surface vertices"""
        # For each surface vertex, find nearest original point
        surface_points = surface.points
        n_surface = surface_points.shape[0]
        
        if len(orig_colors.shape) == 1:
            return np.tile(orig_colors, (n_surface, 1))
            
        # Use KDTree for efficient nearest neighbor search
        from scipy.spatial import cKDTree
        tree = cKDTree(orig_points)
        
        _, indices = tree.query(surface_points)
        return orig_colors[indices]
        
    def enable_animation(self, rotation_speed=1.0):
        """Enable smooth rotation animation"""
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(lambda: self._rotate_camera(rotation_speed))
        self.animation_timer.start(50)  # 20 FPS
        
    def _rotate_camera(self, speed):
        """Rotate camera for animation"""
        self.plotter.camera.azimuth += speed
        self.plotter.render()
        
    def set_quality_preset(self, preset):
        """Set rendering quality preset"""
        presets = {
            'low': {'samples': 0, 'shadows': False, 'depth_peeling': False},
            'medium': {'samples': 2, 'shadows': False, 'depth_peeling': True},
            'high': {'samples': 4, 'shadows': True, 'depth_peeling': True},
            'ultra': {'samples': 8, 'shadows': True, 'depth_peeling': True}
        }
        
        settings = presets.get(preset, presets['medium'])
        
        self.plotter.ren_win.SetMultiSamples(settings['samples'])
        if settings['shadows']:
            self.plotter.enable_shadows()
        else:
            self.plotter.disable_shadows()
        if settings['depth_peeling']:
            self.plotter.enable_depth_peeling()
        else:
            self.plotter.disable_depth_peeling()
            
    def export_scene(self, filename, format='gltf'):
        """Export scene to various 3D formats"""
        if format == 'gltf':
            self.plotter.export_gltf(filename)
        elif format == 'obj':
            self.plotter.export_obj(filename)
        elif format == 'html':
            self.plotter.export_html(filename)
        elif format == 'vtkjs':
            self.plotter.export_vtkjs(filename)