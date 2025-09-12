"""
Layer implementations that work with the abstract rendering backend.
These layers maintain the same interface as the original but use the backend abstraction.
"""

import numpy as np
from PyQt5.QtWidgets import QWidget
from matplotlib import cm
from matplotlib import colors as mpl_colors


class Layer(object):
    """Base layer class that works with abstract backend."""
    LABEL = "Layer"

    def __init__(self, canvas):
        self.name = None
        self.vis_handles = []  # Store backend handles instead of visual objects
        self.vis_objs = []  # Compatibility wrapper objects
        self.canvas = canvas
        self.control_panel = self.init_props_panel()
        self.locked = False
        self.is_visible = True
    
    def _create_vis_obj_wrapper(self, handle):
        """Create a wrapper object for compatibility with vis_objs interface."""
        class VisObjWrapper:
            def __init__(self, handle, layer):
                self.handle = handle
                self.layer = layer
            
            def set_data(self, **kwargs):
                # For now, trigger a redraw
                # In a full implementation, this would update specific properties
                pass
            
            @property
            def opacity(self):
                return 1.0
            
            @opacity.setter
            def opacity(self, value):
                # Would set opacity on the backend object
                pass
        
        return VisObjWrapper(handle, self)

    def remove(self):
        """Remove all visual objects from the scene."""
        # Remove all handles
        for handle in list(self.vis_handles):  # Use list() to avoid modification during iteration
            try:
                self.canvas.backend.remove_object(handle)
            except:
                pass
        
        # Clear the lists
        self.vis_handles.clear()
        self.vis_objs.clear()
        
        # Always force a final render after all removals
        if hasattr(self.canvas.backend, 'render'):
            self.canvas.backend.render()

    def set_props(self, key, val):
        """Set properties on visual objects."""
        # This would need backend-specific implementation
        pass

    def set_visible(self, visible: bool):
        """Set layer visibility."""
        self.is_visible = visible
        if visible:
            # Re-draw the layer when making it visible
            self.draw()
        else:
            # Remove all visual objects when hiding
            self.remove()
        
        # Force render to show changes immediately
        if hasattr(self.canvas.backend, 'render'):
            self.canvas.backend.render()

    def set_locked(self, locked: bool):
        """Set layer locked state."""
        self.locked = locked

    def __str__(self):
        if self.name is None:
            return f"{self.LABEL} <{id(self)}>"
        else:
            return self.name

    def __repr__(self):
        return str(self)

    def init_props_panel(self) -> QWidget:
        """Initialize properties panel."""
        from .obj_panel import LayerPropsPanel
        w = LayerPropsPanel()
        w.connect_with(self)
        return w


class ChrLabelLayer(Layer):
    """Chromosome label layer using abstract backend."""
    LABEL = "ChrLabel"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.labels = []
        self.label_ori_pos = []

    def draw(self, df, shift_factor=0.05, color="#ff0000", font_size=400, bold=True):
        """Draw chromosome labels."""
        # Clear existing handles
        self.remove()
        
        for chrom in df['chrom'].unique():
            sdf = df[df['chrom'] == chrom]
            pos = sdf[['x', 'y', 'z']].values
            center = pos.mean(axis=0)
            norm = np.sqrt(sum([(pos[:, i]-center[i])**2 for i in range(3)]))
            max_norm_ix = np.argmax(norm)
            max_norm_pos = pos[max_norm_ix]
            self.label_ori_pos.append(max_norm_pos)
            label_pos = max_norm_pos * (1 + shift_factor)
            
            # Handle color
            if isinstance(color, dict):
                c = color.get(chrom, color.get(str(chrom).lower().replace('chr',''), "#FFFFFF"))
            else:
                c = color
            
            # Show numeric part only
            chrom_text = str(chrom).lower().replace('chr', '')
            
            # Add text using backend
            handle = self.canvas.backend.add_text(
                chrom_text, 
                tuple(label_pos),
                color=c,
                font_size=font_size,
                bold=bold
            )
            self.vis_handles.append(handle)

    def init_props_panel(self) -> QWidget:
        """Initialize properties panel."""
        from .obj_panel import ChrLabelProps
        w = ChrLabelProps()
        w.connect_with(self)
        return w


class ChromatinLayer(Layer):
    """Chromatin layer using abstract backend."""
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
        """Draw chromatin structure."""
        if len(props) != 0:
            self.cache_props.update(props)
        props = self.cache_props
        
        try:
            df = props['df']
            chr_colormap = props['chr_colormap']
            width = props['width']
            style = props['style']
        except Exception:
            return
        
        # Clear existing visuals
        self.remove()
        
        if not self.is_visible:
            return
        
        color_mode = props.get('color_mode', 'rainbow')
        single_color = props.get('single_color', '#FFFFFF')
        num_chrom = int(df['chrom'].nunique())
        
        # Iterate over chromosomes in the actual data, not just the colormap
        for chrom in df['chrom'].unique():
            sdf = df[df['chrom'] == chrom]
            if sdf.shape[0] <= 1:
                continue
            
            pos = sdf[['x', 'y', 'z']].values
            
            # Prepare colors
            if color_mode == 'single':
                color = single_color
                colors_rgba = mpl_colors.to_rgba(color)
            else:
                if num_chrom > 1:
                    # Multiple chromosomes: one color per chromosome
                    color = chr_colormap.get(chrom, "#888888")
                    colors_rgba = mpl_colors.to_rgba(color)
                else:
                    # Single chromosome: rainbow gradient
                    t = np.linspace(0.0, 1.0, pos.shape[0])
                    cmap = cm.get_cmap('rainbow')
                    colors_rgba = cmap(t)
            
            # Draw based on style
            if style == 'points':
                handle = self.canvas.backend.add_points(
                    pos,
                    color=colors_rgba,
                    size=width
                )
                if handle is not None:
                    self.vis_handles.append(handle)
                    self.vis_objs.append(self._create_vis_obj_wrapper(handle))
                    
            elif style == 'tube':
                if isinstance(colors_rgba, np.ndarray) and colors_rgba.ndim == 2:
                    # Gradient tube - need to create segments
                    self._draw_gradient_tube(pos, colors_rgba, width/2, props)
                else:
                    # Single color tube
                    handle = self.canvas.backend.add_tube(
                        pos,
                        color=colors_rgba,
                        radius=width/2
                    )
                    if handle is not None:
                        self.vis_handles.append(handle)
                        self.vis_objs.append(self._create_vis_obj_wrapper(handle))
                        
            else:  # line
                handle = self.canvas.backend.add_line(
                    pos,
                    color=colors_rgba,
                    width=width
                )
                if handle is not None:
                    self.vis_handles.append(handle)
                    self.vis_objs.append(self._create_vis_obj_wrapper(handle))
            
            # Handle breaks if specified
            if props.get('breaks', False):
                self._handle_breaks(sdf, pos, colors_rgba, width, style)
        
        # Don't auto-render here - let the caller decide when to render
    
    def _draw_gradient_tube(self, pos, colors_rgba, radius, props):
        """Draw a gradient-colored tube by segments."""
        max_segments = int(props.get('tube_gradient_segments', 50))
        total_points = pos.shape[0]
        
        if total_points <= max_segments * 2:
            # Small dataset: fewer segments
            step = max(2, total_points // max_segments)
            for i in range(0, total_points - step, step):
                j = min(total_points - 1, i + step * 2)
                seg = pos[i:j+1]
                if seg.shape[0] >= 2:
                    c = tuple(colors_rgba[i])
                    handle = self.canvas.backend.add_tube(
                        seg,
                        color=c,
                        radius=radius
                    )
                    if handle is not None:
                        self.vis_handles.append(handle)
                        self.vis_objs.append(self._create_vis_obj_wrapper(handle))
        else:
            # Large dataset: adaptive decimation
            indices = np.linspace(0, total_points-1, max_segments, dtype=int)
            for i in range(len(indices)-1):
                start_idx = indices[i]
                end_idx = indices[i+1]
                seg = pos[start_idx:end_idx+1]
                if seg.shape[0] >= 2:
                    c = tuple(colors_rgba[start_idx])
                    handle = self.canvas.backend.add_tube(
                        seg,
                        color=c,
                        radius=radius
                    )
                    if handle is not None:
                        self.vis_handles.append(handle)
                        self.vis_objs.append(self._create_vis_obj_wrapper(handle))
    
    def _handle_breaks(self, sdf, pos, colors_rgba, width, style):
        """Handle breaks in the chromatin structure."""
        first_row = sdf.iloc[0, :]
        starts = sdf['start'].values
        diff = starts[1:] - starts[:-1]
        bin_size = first_row['end'] - first_row['start']
        median_gap = np.median(diff)
        gap_thresh = median_gap * 2
        breaks_ix = np.where(diff > gap_thresh)[0]
        
        if len(breaks_ix) > 0:
            # Clear and redraw with breaks
            for handle in self.vis_handles:
                self.canvas.backend.remove_object(handle)
            self.vis_handles.clear()
            
            # Draw segments
            breaks_ix = np.concatenate([[0], breaks_ix + 1, [len(pos)]])
            for i in range(len(breaks_ix) - 1):
                start = breaks_ix[i]
                end = breaks_ix[i + 1]
                seg_pos = pos[start:end]
                
                if seg_pos.shape[0] < 2:
                    continue
                
                # Get colors for segment
                if isinstance(colors_rgba, np.ndarray) and colors_rgba.ndim == 2:
                    seg_color = colors_rgba[start:end]
                else:
                    seg_color = colors_rgba
                
                # Draw segment based on style
                if style == 'points':
                    handle = self.canvas.backend.add_points(seg_pos, color=seg_color, size=width)
                elif style == 'tube':
                    if isinstance(seg_color, np.ndarray) and seg_color.ndim == 2:
                        # Need to handle gradient for segment
                        for j in range(seg_pos.shape[0] - 1):
                            sub_seg = seg_pos[j:j+2]
                            c = tuple(seg_color[j])
                            handle = self.canvas.backend.add_tube(sub_seg, color=c, radius=width/2)
                            if handle is not None:
                                self.vis_handles.append(handle)
                        continue
                    else:
                        handle = self.canvas.backend.add_tube(seg_pos, color=seg_color, radius=width/2)
                else:
                    handle = self.canvas.backend.add_line(seg_pos, color=seg_color, width=width)
                
                if handle is not None:
                    self.vis_handles.append(handle)

    def init_props_panel(self) -> QWidget:
        """Initialize properties panel."""
        from .obj_panel import ChromatinProps
        w = ChromatinProps()
        w.connect_with(self)
        return w
    
    def re_render(self, parent=False):
        """Re-render the layer."""
        self.remove()
        self.draw()
        if hasattr(self.control_panel, 'update_params'):
            self.control_panel.update_params()
        if parent:
            if self.parent is None:
                return
            if hasattr(self.parent, 're_render'):
                self.parent.re_render(parent=True)