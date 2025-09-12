import numpy as np
import pyvista as pv
from PyQt5.QtWidgets import QWidget
from matplotlib import cm
from matplotlib import colors as mpl_colors


class LayerPyVista(object):
    LABEL = "Layer"
    
    def __init__(self, canvas):
        self.name = None
        self.vis_objs = []  # Store PyVista actors
        self.canvas = canvas
        self.control_panel = self.init_props_panel()
        self.locked = False
        self.is_visible = True
        
    def remove(self):
        """Remove all visual objects from the scene"""
        for actor in self.vis_objs:
            self.canvas.plotter.remove_actor(actor)
        self.vis_objs.clear()
        
    def set_props(self, key, val):
        """Set properties on all visual objects"""
        for obj in self.vis_objs:
            if hasattr(obj, key):
                setattr(obj, key, val)
                
    def set_visible(self, visible: bool):
        self.is_visible = visible
        if visible:
            # Re-draw the layer when making it visible
            self.draw()
        else:
            # Remove all visual objects when hiding
            self.remove()
            
    def set_locked(self, locked: bool):
        self.locked = locked
        
    def __str__(self):
        if self.name is None:
            return f"{self.LABEL} <{id(self)}>"
        else:
            return self.name
            
    def __repr__(self):
        return str(self)
        
    def init_props_panel(self) -> QWidget:
        try:
            from .obj_panel_pyvista import LayerPropsPanelPyVista
            w = LayerPropsPanelPyVista()
        except ImportError:
            from .obj_panel import LayerPropsPanel
            w = LayerPropsPanel()
        w.connect_with(self)
        return w


class ChrLabelLayerPyVista(LayerPyVista):
    LABEL = "ChrLabel"
    
    def __init__(self, canvas):
        super().__init__(canvas)
        self.labels = []
        self.label_ori_pos = []
        
    def draw(self, df, shift_factor=0.05, color="#ff0000", font_size=400, bold=True):
        """Draw chromosome labels in 3D space"""
        self.remove()  # Clear existing labels
        
        for chrom in df['chrom'].unique():
            sdf = df[df['chrom'] == chrom]
            pos = sdf[['x', 'y', 'z']].values
            center = pos.mean(axis=0)
            norm = np.sqrt(sum([(pos[:, i]-center[i])**2 for i in range(3)]))
            max_norm_ix = np.argmax(norm)
            max_norm_pos = pos[max_norm_ix]
            self.label_ori_pos.append(max_norm_pos)
            label_pos = max_norm_pos * (1 + shift_factor)
            
            # Handle color mapping
            if isinstance(color, dict):
                c = color.get(chrom, color.get(str(chrom).lower().replace('chr',''), "#FFFFFF"))
            else:
                c = color
                
            # Show numeric part only (e.g., chr1 -> 1)
            chrom_text = str(chrom).lower().replace('chr', '')
            
            # Create 3D text actor
            text_mesh = pv.Text3D(chrom_text, depth=0.1)
            text_mesh.translate(label_pos)
            
            # Scale the text appropriately
            scale_factor = font_size / 1000.0  # Adjust scale based on font_size
            text_mesh.scale([scale_factor, scale_factor, scale_factor])
            
            # Add to plotter with color
            actor = self.canvas.plotter.add_mesh(
                text_mesh, 
                color=c,
                opacity=1.0,
                lighting=True
            )
            self.vis_objs.append(actor)
            self.canvas.add_actor(actor)
            
    def init_props_panel(self) -> QWidget:
        from .obj_panel import ChrLabelProps
        w = ChrLabelProps()
        w.connect_with(self)
        return w


class ChromatinLayerPyVista(LayerPyVista):
    LABEL = "Chromatin"
    
    def __init__(self, canvas, df, chr_colormap, width=1.0, style='line'):
        self.parent = None
        self.df = df
        self.cache_props = {
            'color_mode': 'rainbow',
            'single_color': '#FFFFFF',
            'df': df,
            'chr_colormap': chr_colormap,
            'width': width,
            'style': style,
        }
        super().__init__(canvas)
        self.draw(df=df, chr_colormap=chr_colormap, width=width, style=style)
        
    def draw(self, **props):
        if len(props) != 0:
            self.cache_props.update(props)
        props = self.cache_props
        
        try:
            df = props['df']
            chr_colormap = props['chr_colormap']
            width = props['width']
            style = props['style']
        except Exception as e:
            print(repr(e))
            return
            
        # Clear existing actors
        self.remove()
        
        # If layer is not visible, don't draw anything
        if not self.is_visible:
            return
            
        color_mode = props.get('color_mode', 'rainbow')
        single_color = props.get('single_color', '#FFFFFF')
        num_chrom = int(df['chrom'].nunique())
        
        for chrom in chr_colormap.keys():
            sdf = df[df['chrom'] == chrom]
            if sdf.shape[0] <= 1:
                continue
            pos = sdf[['x', 'y', 'z']].values
            
            # Determine colors
            if color_mode == 'single':
                color_rgba = mpl_colors.to_rgba(single_color)
                colors = np.tile(color_rgba[:3], (pos.shape[0], 1))  # RGB only for PyVista
            else:
                if num_chrom > 1:
                    # Multiple chromosomes -> one color per chromosome
                    color = chr_colormap.get(chrom, "#888888")
                    color_rgba = mpl_colors.to_rgba(color)
                    colors = np.array(color_rgba[:3])  # Convert to numpy array for consistency
                else:
                    # Single chromosome -> rainbow gradient along polymer
                    t = np.linspace(0.0, 1.0, pos.shape[0])
                    cmap = cm.get_cmap('rainbow')
                    colors_rgba = cmap(t)
                    colors = colors_rgba[:, :3]  # Remove alpha channel for PyVista
                    
            # Draw based on style
            self._draw_chromatin(pos, colors, width, style, props)
            
    def _draw_chromatin(self, pos, colors, width, style, props):
        """Draw chromatin with specified style using PyVista"""
        
        if style == 'points':
            # Create point cloud
            point_cloud = pv.PolyData(pos)
            
            # Add colors if per-vertex coloring
            if isinstance(colors, np.ndarray) and len(colors.shape) > 1 and colors.shape[0] == pos.shape[0]:
                point_cloud["colors"] = colors
                actor = self.canvas.plotter.add_mesh(
                    point_cloud,
                    scalars="colors",
                    rgb=True,
                    point_size=width * 2,
                    render_points_as_spheres=True
                )
            else:
                actor = self.canvas.plotter.add_mesh(
                    point_cloud,
                    color=colors,
                    point_size=width * 2,
                    render_points_as_spheres=True
                )
            self.vis_objs.append(actor)
            self.canvas.add_actor(actor)
            
        elif style == 'tube':
            # Create tube/spline representation
            radius = width / 2
            
            # Check for breaks in the chromatin
            if props.get('breaks', False):
                segments = self._get_segments_with_breaks(pos, props)
            else:
                segments = [pos]
                
            for seg_pos in segments:
                if seg_pos.shape[0] < 2:
                    continue
                    
                # Create spline through points
                spline = pv.Spline(seg_pos, 1000)
                
                # Create tube
                tube = spline.tube(radius=radius, n_sides=16)
                
                # Add colors
                if isinstance(colors, np.ndarray) and len(colors.shape) > 1 and colors.shape[0] == seg_pos.shape[0]:
                    # Interpolate colors for the tube
                    # This is a simplified approach - for gradient tubes
                    tube_colors = self._interpolate_colors_for_tube(colors, seg_pos.shape[0], 1000)
                    tube["colors"] = tube_colors
                    actor = self.canvas.plotter.add_mesh(
                        tube,
                        scalars="colors",
                        rgb=True,
                        smooth_shading=True,
                        opacity=1.0
                    )
                else:
                    actor = self.canvas.plotter.add_mesh(
                        tube,
                        color=colors,
                        smooth_shading=True,
                        opacity=1.0
                    )
                self.vis_objs.append(actor)
                self.canvas.add_actor(actor)
                
        else:  # line style
            # Check for breaks in the chromatin
            if props.get('breaks', False):
                segments = self._get_segments_with_breaks(pos, props)
            else:
                segments = [pos]
                
            for seg_pos in segments:
                if seg_pos.shape[0] < 2:
                    continue
                    
                # Create lines
                lines = self._create_lines_from_points(seg_pos)
                
                # Add colors
                if isinstance(colors, np.ndarray) and len(colors.shape) > 1 and colors.shape[0] == pos.shape[0]:
                    lines["colors"] = colors[:seg_pos.shape[0]]
                    actor = self.canvas.plotter.add_mesh(
                        lines,
                        scalars="colors",
                        rgb=True,
                        line_width=width,
                        render_lines_as_tubes=True
                    )
                else:
                    actor = self.canvas.plotter.add_mesh(
                        lines,
                        color=colors,
                        line_width=width,
                        render_lines_as_tubes=True
                    )
                self.vis_objs.append(actor)
                self.canvas.add_actor(actor)
                
    def _create_lines_from_points(self, points):
        """Create a PolyData line from points"""
        n_points = points.shape[0]
        cells = np.full((n_points - 1, 3), 2, dtype=np.int_)
        cells[:, 1] = np.arange(0, n_points - 1, dtype=np.int_)
        cells[:, 2] = np.arange(1, n_points, dtype=np.int_)
        lines = pv.PolyData(points, lines=cells)
        return lines
        
    def _get_segments_with_breaks(self, pos, props):
        """Calculate segments with breaks"""
        sdf = props['df']
        first_row = sdf.iloc[0, :]
        starts = sdf['start'].values
        diff = starts[1:] - starts[:-1]
        bin_size = first_row['end'] - first_row['start']
        breaks = np.where(diff > (bin_size + 10))[0] + 1
        
        segments = []
        if breaks.shape[0] <= 0:
            segments.append(pos)
        else:
            ob = 0
            for b in list(breaks) + [pos.shape[0]]:
                segments.append(pos[ob:b])
                ob = b
        return segments
        
    def _interpolate_colors_for_tube(self, colors, n_original, n_interpolated):
        """Interpolate colors for tube vertices"""
        if not isinstance(colors, np.ndarray):
            # Convert single color to array
            colors = np.array(colors)
        
        if len(colors.shape) == 1:
            # Single color
            return np.tile(colors, (n_interpolated, 1))
        else:
            # Multiple colors - interpolate
            t_orig = np.linspace(0, 1, n_original)
            t_interp = np.linspace(0, 1, n_interpolated)
            
            interp_colors = np.zeros((n_interpolated, 3))
            for i in range(3):
                interp_colors[:, i] = np.interp(t_interp, t_orig, colors[:, i])
            return interp_colors
            
    def init_props_panel(self) -> QWidget:
        try:
            from .obj_panel_pyvista import ChromatinPropsPyVista
            w = ChromatinPropsPyVista()
        except ImportError:
            from .obj_panel import ChromatinProps
            w = ChromatinProps()
        w.connect_with(self)
        return w
        
    def re_render(self, parent=False):
        self.remove()
        self.draw()
        # Only update params if control panel exists and has the method
        if hasattr(self, 'control_panel') and hasattr(self.control_panel, 'update_params'):
            try:
                # Temporarily disable updates to avoid recursion
                if not getattr(self, '_updating', False):
                    self._updating = True
                    self.control_panel.update_params()
                    self._updating = False
            except AttributeError:
                # Ignore attribute errors from incompatible control panels
                self._updating = False
                pass
        if parent:
            if self.parent is None:
                return
            self.parent.re_render(parent=True)