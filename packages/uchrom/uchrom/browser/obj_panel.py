from PyQt5.QtWidgets import (QComboBox, QDoubleSpinBox, QSpinBox, QWidget, QLabel,
                             QGridLayout, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLineEdit, QGroupBox,
                             QColorDialog, QMessageBox, QScrollArea, QSizePolicy, QTabWidget)
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from .range_list import RangeList


class LayerPropsPanel(QWidget):
    def __init__(self, parent=None, grid_table=[], operation_widgets=[], title="Properties"):
        super().__init__(parent)
        self.top_layout = QVBoxLayout()
        self.title = QLabel(f"<h2>{title}</h2>")
        self.top_layout.addWidget(self.title)
        self.grid_layout = QGridLayout()
        for i, row in enumerate(grid_table):
            for j, _obj in enumerate(row):
                self.grid_layout.addWidget(_obj, i, j)
        self.top_layout.addLayout(self.grid_layout)
        self.top_layout.addStretch()
        self.setLayout(self.top_layout)
        self.layers = []
        self.operation_widgets = []
        self.operation_widgets += operation_widgets
        self.operations_panel = QWidget()
        vbox = QVBoxLayout()
        for op in self.operation_widgets:
            vbox.addWidget(op)
        vbox.addStretch()
        self.operations_panel.setLayout(vbox)

    def connect_with(self, layer):
        self.layers.append(layer)

    def update_params(self):
        pass


class ChromatinProps(LayerPropsPanel):
    def __init__(self):
        # Create grouped controls
        self.create_grouped_controls()



        self.subset_window = RangeList("Take sub-set")
        self.subset_window.signal_ok.connect(self.on_take_subset)

        # Move entire Chromosome Management group to the Layers panel's right side
        # Consolidate the three "management" groups into a QTabWidget so only
        # one is shown at a time.  Tabs are added/removed based on the data
        # in ``_update_style_availability``.  The QTabWidget's pane supplies
        # the outer frame; the inner QGroupBoxes drop their own title (the
        # tab label already names each section) but keep their default frame
        # so the content visually matches the layer list.
        self.ops_tabs = QTabWidget()
        for g in (self.chrom_group, self.region_group, self.trace_group):
            try:
                g.setTitle("")
            except Exception:
                pass
        self.ops_tabs.addTab(self.chrom_group, "Chromosome")
        self.ops_tabs.addTab(self.region_group, "Region")
        self.ops_tabs.addTab(self.trace_group, "Trace")
        super().__init__(grid_table=[], operation_widgets=[self.ops_tabs])
        
        # Add grouped controls to layout after parent initialization
        self.add_grouped_layout()

    def create_grouped_controls(self):
        # Model Properties Group
        self.model_group = QGroupBox("Model Properties")
        model_layout = QGridLayout()
        
        l_style = QLabel("Style")
        self.model_style_select = QComboBox()
        self.model_style_select.addItem("line")
        self.model_style_select.addItem("tube")
        self.model_style_select.addItem("points")
        self.model_style_select.currentIndexChanged.connect(self.on_model_style_change)

        l_width = QLabel("Width/Radius")
        self.width_control = QDoubleSpinBox()
        self.width_control.setMaximum(20.0)
        self.width_control.setMinimum(0.0)
        self.width_control.setSingleStep(1.0)
        self.width_control.setValue(1.0)
        self.width_control.valueChanged.connect(self.on_width_changed)

        l_opacity = QLabel("Opacity")
        self.opacity_control = QDoubleSpinBox()
        self.opacity_control.setMaximum(1.0)
        self.opacity_control.setMinimum(0.0)
        self.opacity_control.setSingleStep(0.05)
        self.opacity_control.setValue(1.0)
        self.opacity_control.valueChanged.connect(self.on_opacity_changed)

        # High quality mode checkbox (for tube mode)
        self.high_quality_checkbox = QCheckBox("High Quality (slow)")
        self.high_quality_checkbox.setChecked(False)
        self.high_quality_checkbox.setToolTip("Use more interpolation points for smoother curves. Better quality but slower rendering.")
        self.high_quality_checkbox.stateChanged.connect(self.on_high_quality_changed)
        self.high_quality_checkbox.setVisible(False)  # Only visible in tube mode
 
        l_color_mode = QLabel("Color")
        # Mode: Rainbow or Custom HEX
        self.model_color_mode = QComboBox()
        self.model_color_mode.addItems(["Rainbow", "Custom", "Per Trace"])
        self.model_color_mode.setCurrentText("Rainbow")
        self.model_color_mode.currentIndexChanged.connect(self.on_model_color_mode_change)
        # Custom color controls
        self.single_color_btn = QPushButton()
        self.single_color_btn.setFixedSize(50, 25)
        self.single_color_btn.clicked.connect(self.on_pick_single_color)
        self.single_color_hex = QLineEdit("#FFFFFF")
        self.single_color_hex.setPlaceholderText("#FFFFFF")
        self.single_color_hex.textChanged.connect(self.on_single_color_hex_changed)
        # Hidden unless Custom mode
        self.single_color_btn.setVisible(False)
        self.single_color_hex.setVisible(False)
        

        # Chromosome management section
        self.chrom_group = QGroupBox("Chromosome Management")
        chrom_layout = QVBoxLayout()
        
        # Chromosome selector
        chrom_selector_layout = QHBoxLayout()
        chrom_selector_layout.addWidget(QLabel("Select Chromosome:"))
        self.chrom_select = QComboBox()
        self.chrom_select.currentTextChanged.connect(self.on_chromosome_selected)
        chrom_selector_layout.addWidget(self.chrom_select)
        chrom_layout.addLayout(chrom_selector_layout)
        
        # Color controls for selected chromosome
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        self.chrom_color_btn = QPushButton()
        self.chrom_color_btn.setFixedSize(50, 25)
        self.chrom_color_btn.clicked.connect(self.on_change_chrom_color)
        color_layout.addWidget(self.chrom_color_btn)
        
        self.chrom_hex_input = QLineEdit()
        self.chrom_hex_input.setPlaceholderText("#CD18FC")
        self.chrom_hex_input.textChanged.connect(self.on_chrom_hex_changed)
        color_layout.addWidget(self.chrom_hex_input)
        chrom_layout.addLayout(color_layout)
        
        # Subset creation button
        self.create_subset_btn = QPushButton("Create Subset of Selected Chromosome")
        self.create_subset_btn.clicked.connect(self.on_create_chrom_subset)
        chrom_layout.addWidget(self.create_subset_btn)
        
        self.chrom_group.setLayout(chrom_layout)

        # Region Management Group
        self.region_group = QGroupBox("Region Management")
        region_layout = QGridLayout()
        
        # Add chromosome selector for region
        l_region_chr = QLabel("Chromosome:")
        self.region_chr_select = QComboBox()
        self.region_chr_select.currentTextChanged.connect(self.on_region_chr_changed)
        
        # Add range display label
        self.region_range_label = QLabel("Valid range: ")
        self.region_range_label.setStyleSheet("color: #888888; font-size: 11px;")
        
        l_region = QLabel("Start-End:")
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText("100000-200000")
        self.region_input.setToolTip("Enter the start and end coordinates within the valid range")
        
        l_region_color = QLabel("Color:")
        self.region_color_btn = QPushButton()
        self.region_color_btn.setFixedSize(50, 20)
        self.region_color_btn.setStyleSheet("background-color:#CD18FC")
        self.region_color_btn.clicked.connect(self.on_pick_region_color)
        self.region_color_hex = QLineEdit("#CD18FC")
        self.region_color_hex.textChanged.connect(self.on_region_hex_changed)
        
        self.region_subset_btn = QPushButton("Create Region Subset")
        self.region_subset_btn.clicked.connect(self.on_create_region_subset)
        
        # Layout: chromosome selector and range display
        region_layout.addWidget(l_region_chr, 0, 0)
        region_layout.addWidget(self.region_chr_select, 0, 1, 1, 2)
        region_layout.addWidget(self.region_range_label, 1, 0, 1, 3)
        region_layout.addWidget(l_region, 2, 0)
        region_layout.addWidget(self.region_input, 2, 1, 1, 2)
        region_layout.addWidget(l_region_color, 3, 0)
        region_layout.addWidget(self.region_color_btn, 3, 1)
        region_layout.addWidget(self.region_color_hex, 3, 2)
        region_layout.addWidget(self.region_subset_btn, 4, 0, 1, 3)
        self.region_group.setLayout(region_layout)

        # Trace Management Group (visible only when a chromosome has multiple traces)
        self.trace_group = QGroupBox("Trace Management")
        trace_layout = QGridLayout()

        l_trace_mode = QLabel("Mode:")
        self.trace_mode_select = QComboBox()
        self.trace_mode_select.addItems(["Single", "Range", "Multiple"])
        self.trace_mode_select.setCurrentText("Single")
        self.trace_mode_select.currentTextChanged.connect(self.on_trace_mode_changed)

        self.trace_info_label = QLabel("")
        self.trace_info_label.setStyleSheet("color: #888888; font-size: 11px;")

        l_trace_id = QLabel("Trace ID:")
        self.trace_id_input = QLineEdit()
        self.trace_id_input.setPlaceholderText("1")
        self.trace_id_input.setToolTip(
            "Single: one trace_id (e.g. '1').  "
            "Range: two IDs joined by '-' (e.g. '1-50').  "
            "Multiple: comma-separated IDs (e.g. '1,5,20')."
        )

        l_trace_color = QLabel("Color:")
        self.trace_color_btn = QPushButton()
        self.trace_color_btn.setFixedSize(50, 20)
        self.trace_color_btn.setStyleSheet("background-color:#FF6A00")
        self.trace_color_btn.clicked.connect(self.on_pick_trace_color)
        self.trace_color_hex = QLineEdit("#FF6A00")
        self.trace_color_hex.textChanged.connect(self.on_trace_hex_changed)

        self.trace_subset_btn = QPushButton("Create Trace Subset")
        self.trace_subset_btn.clicked.connect(self.on_create_trace_subset)

        trace_layout.addWidget(l_trace_mode, 0, 0)
        trace_layout.addWidget(self.trace_mode_select, 0, 1, 1, 2)
        trace_layout.addWidget(self.trace_info_label, 1, 0, 1, 3)
        trace_layout.addWidget(l_trace_id, 2, 0)
        trace_layout.addWidget(self.trace_id_input, 2, 1, 1, 2)
        trace_layout.addWidget(l_trace_color, 3, 0)
        trace_layout.addWidget(self.trace_color_btn, 3, 1)
        trace_layout.addWidget(self.trace_color_hex, 3, 2)
        trace_layout.addWidget(self.trace_subset_btn, 4, 0, 1, 3)
        self.trace_group.setLayout(trace_layout)

        # Trace Statistics group: population-level aggregate plots (E)
        self.stats_group = QGroupBox("Trace Statistics")
        stats_layout = QGridLayout()

        self.stats_dist_btn = QPushButton("Distance Matrix")
        self.stats_dist_btn.setToolTip("Population-median pairwise distance matrix")
        self.stats_dist_btn.clicked.connect(self.on_show_distance_matrix)

        self.stats_contact_btn = QPushButton("Contact Map")
        self.stats_contact_btn.setToolTip("Contact frequency under a distance threshold")
        self.stats_contact_btn.clicked.connect(self.on_show_contact_map)

        self.stats_rg_btn = QPushButton("Rg Histogram")
        self.stats_rg_btn.setToolTip("Distribution of per-trace radius of gyration")
        self.stats_rg_btn.clicked.connect(self.on_show_rg_histogram)

        self.stats_threshold = QDoubleSpinBox()
        self.stats_threshold.setRange(0.0, 1e6)
        self.stats_threshold.setDecimals(3)
        self.stats_threshold.setSingleStep(10.0)
        self.stats_threshold.setValue(200.0)
        self.stats_threshold.setToolTip("Contact threshold (same units as coords)")

        self.stats_split_spin = QSpinBox()
        self.stats_split_spin.setRange(1, 64)
        self.stats_split_spin.setValue(4)
        self.stats_split_spin.setToolTip("Number of traces to show side by side")

        self.stats_split_btn = QPushButton("Split by Trace")
        self.stats_split_btn.setToolTip("Open N canvases each showing one trace")
        self.stats_split_btn.clicked.connect(self.on_split_by_trace)

        # Compact 3-column grid so the group doesn't dominate the panel
        stats_layout.addWidget(self.stats_dist_btn,    0, 0, 1, 3)
        stats_layout.addWidget(QLabel("Threshold:"),   1, 0)
        stats_layout.addWidget(self.stats_threshold,   1, 1, 1, 2)
        stats_layout.addWidget(self.stats_contact_btn, 2, 0, 1, 3)
        stats_layout.addWidget(self.stats_rg_btn,      3, 0, 1, 3)
        stats_layout.addWidget(QLabel("Split N:"),     4, 0)
        stats_layout.addWidget(self.stats_split_spin,  4, 1)
        stats_layout.addWidget(self.stats_split_btn,   4, 2)

        self.stats_group.setLayout(stats_layout)
        self.stats_group.setVisible(False)
        # Keep references to open figure windows so they are not GC'd
        self._figure_dialogs = []

        # Labels overlay color mode
        self.labels_group = QGroupBox("Chromosome Labels")
        labels_layout = QGridLayout()
        self.labels_enable = QCheckBox("Enable")
        self.labels_enable.setChecked(True)
        self.labels_enable.stateChanged.connect(self.on_labels_enable_change)
        labels_layout.addWidget(self.labels_enable, 0, 0, 1, 2)
        
        l_mode = QLabel("Color mode:")
        self.labels_mode = QComboBox()
        self.labels_mode.addItems(["Follow chromosome", "White", "Black"])
        self.labels_mode.currentIndexChanged.connect(self.on_labels_mode_change)
        labels_layout.addWidget(l_mode, 1, 0)
        labels_layout.addWidget(self.labels_mode, 1, 1)
        
        l_font_size = QLabel("Font size:")
        self.labels_font_size = QSpinBox()
        self.labels_font_size.setMinimum(50)
        self.labels_font_size.setMaximum(2000)
        self.labels_font_size.setSingleStep(50)
        self.labels_font_size.setValue(150)
        self.labels_font_size.valueChanged.connect(self.on_labels_font_size_change)
        labels_layout.addWidget(l_font_size, 2, 0)
        labels_layout.addWidget(self.labels_font_size, 2, 1)
        
        self.labels_group.setLayout(labels_layout)
        self.labels_group.setVisible(False)


        model_layout.addWidget(l_style, 0, 0)
        model_layout.addWidget(self.model_style_select, 0, 1)
        model_layout.addWidget(l_width, 1, 0)
        model_layout.addWidget(self.width_control, 1, 1)
        model_layout.addWidget(l_opacity, 2, 0)
        model_layout.addWidget(self.opacity_control, 2, 1)
        model_layout.addWidget(self.high_quality_checkbox, 3, 0, 1, 2)  # Span 2 columns
        model_layout.addWidget(l_color_mode, 4, 0)
        model_layout.addWidget(self.model_color_mode, 4, 1)
        model_layout.addWidget(self.single_color_btn, 5, 0)
        model_layout.addWidget(self.single_color_hex, 5, 1)
        self.model_group.setLayout(model_layout)

        # Layer Label Group
        self.label_group = QGroupBox("Layer Label")
        label_layout = QGridLayout()

        l_label_font = QLabel("Font size")
        self.label_font_control = QDoubleSpinBox()
        self.label_font_control.setMaximum(100.0)
        self.label_font_control.setMinimum(0.5)
        self.label_font_control.setSingleStep(0.5)
        self.label_font_control.setValue(20.0)
        self.label_font_control.valueChanged.connect(self.on_label_font_changed)

        l_label_pos = QLabel("Position")
        self.label_position_control = QComboBox()
        self.label_position_control.addItems([
            "Top Left", "Top Center", "Top Right",
            "Bottom Left", "Bottom Center", "Bottom Right"
        ])
        self.label_position_control.setCurrentText("Top Left")
        self.label_position_control.currentTextChanged.connect(self.on_label_position_changed)

        l_label_color = QLabel("Color")
        self.label_color_control = QComboBox()
        self.label_color_control.addItems([
            "Purple", "Custom"
        ])
        self.label_color_control.setCurrentText("Purple")
        self.label_color_control.currentTextChanged.connect(self.on_label_color_changed)

        # Custom label color controls (similar to single color mode)
        self.label_color_btn = QPushButton()
        self.label_color_btn.setFixedSize(50, 25)
        self.label_color_btn.clicked.connect(self.on_pick_label_color)
        self.label_color_hex = QLineEdit("#CD18FC")  # Default purple color
        self.label_color_hex.setPlaceholderText("#CD18FC")
        self.label_color_hex.textChanged.connect(self.on_label_color_hex_changed)
        # Hidden unless Custom mode
        self.label_color_btn.setVisible(False)
        self.label_color_hex.setVisible(False)

        # Add to label group layout
        label_layout.addWidget(l_label_font, 0, 0)
        label_layout.addWidget(self.label_font_control, 0, 1)
        label_layout.addWidget(l_label_pos, 1, 0)
        label_layout.addWidget(self.label_position_control, 1, 1)
        label_layout.addWidget(l_label_color, 2, 0)
        label_layout.addWidget(self.label_color_control, 2, 1)
        label_layout.addWidget(self.label_color_btn, 3, 0)
        label_layout.addWidget(self.label_color_hex, 3, 1)
        self.label_group.setLayout(label_layout)

        # Canvas Properties Group
        self.canvas_group = QGroupBox("Canvas Properties")
        canvas_layout = QGridLayout()

        l_bg_color = QLabel("Background")
        self.bg_color_control = QComboBox()
        self.bg_color_control.addItems([
            "Black", "White", "Light Gray"
        ])
        self.bg_color_control.setCurrentText("Black")
        self.bg_color_control.currentTextChanged.connect(self.on_bg_color_changed)

        # Add to canvas group layout
        canvas_layout.addWidget(l_bg_color, 0, 0)
        canvas_layout.addWidget(self.bg_color_control, 0, 1)
        self.canvas_group.setLayout(canvas_layout)

    def add_grouped_layout(self):
        # Create a scroll area for the properties
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Use automatic scrollbar policy - Qt will handle it intelligently
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create a container widget for all group boxes
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(5)
        container_layout.setContentsMargins(5, 5, 5, 5)  # Add some margins
        
        # Add all group boxes to the container
        container_layout.addWidget(self.model_group)
        container_layout.addWidget(self.stats_group)
        container_layout.addWidget(self.labels_group)
        container_layout.addWidget(self.label_group)
        container_layout.addWidget(self.canvas_group)
        # Remove addStretch() to prevent unnecessary space that might cause scrolling
        # container_layout.addStretch()
        
        # Set the container as the scroll area's widget
        scroll_area.setWidget(container)
        
        # Set minimum size for the scroll area to prevent it from being too small
        scroll_area.setMinimumHeight(200)  # Minimum height to show some content
        
        # Make the scroll area expand to fill available space
        # This allows the Properties panel to grow with the window
        self.top_layout.insertWidget(1, scroll_area, 1)  # stretch factor = 1
        
        # Ensure the Properties panel itself can expand
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        # Store reference for potential future use
        self.scroll_area = scroll_area
        self.scroll_container = container
        
        # Ensure the scroll area can expand to fill available space
        scroll_area.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def _update_style_availability(self):
        # Rebuild the style combo based on current conditions
        current_style = self.model_style_select.currentText()
        # Maintain backward-compat variable for legacy reads
        try:
            current_color = self.model_color_mode.currentText()
        except Exception:
            current_color = "Rainbow"
        
        # Check chromosome count and color mode constraints
        # Tube mode is always supported for all configurations
        disable_tube = False
        is_multi_chrom = False
        if len(self.layers) > 0:
            for layer in self.layers:
                try:
                    df = layer.df
                    num_chrom = int(df['chrom'].nunique())
                    if num_chrom > 1:
                        is_multi_chrom = True
                        break
                except Exception:
                    pass
        
        # Rebuild the combo with appropriate options
        self.model_style_select.blockSignals(True)  # Prevent triggering events during rebuild
        self.model_style_select.clear()
        
        # Always add basic styles
        self.model_style_select.addItem("line")
        
        # Always add tube and points options
        self.model_style_select.addItem('tube')
        self.model_style_select.addItem('points')
        has_tube_option = True
        
        
        # Update color controls and chromosome management based on chromosome count
        self.model_color_mode.blockSignals(True)
        if is_multi_chrom:
            # Multi-chromosome: only rainbow mode
            self.model_color_mode.setCurrentText("Rainbow")
            self.single_color_btn.setVisible(False)
            self.single_color_hex.setVisible(False)
            self._update_chromosome_list()
        else:
            # Single chromosome: allow all color modes
            if current_color not in ["Rainbow", "Rainbow (Multi-chromosome)"]:
                self.model_color_mode.setCurrentText("Custom")
                self.single_color_btn.setVisible(True)
                self.single_color_hex.setVisible(True)
            else:
                self.model_color_mode.setCurrentText("Rainbow")
                self.single_color_btn.setVisible(False)
                self.single_color_hex.setVisible(False)
        self.model_color_mode.blockSignals(False)

        # Trace Management tab: show only when the data has more traces than
        # chromosomes (i.e. multiple polymers per chromosome, typical of
        # imaging data).
        show_trace = False
        try:
            for layer in self.layers:
                if not hasattr(layer, 'df'):
                    continue
                ldf = layer.df
                if 'trace_id' not in ldf.columns:
                    continue
                n_tr = int(ldf['trace_id'].nunique())
                n_ch = int(ldf['chrom'].nunique())
                if n_tr > n_ch:
                    show_trace = True
                    self.trace_info_label.setText(
                        f"{n_tr} traces across {n_ch} chromosome(s)"
                    )
                    break
        except Exception:
            pass

        self._set_tab_visible(self.chrom_group, is_multi_chrom)
        self._set_tab_visible(self.region_group, True)
        self._set_tab_visible(self.trace_group, show_trace)
        self.stats_group.setVisible(show_trace)
        # Pick a sensible default tab
        self._select_default_ops_tab()

        # Restore selection or fallback to line
        if current_style == 'tube' and disable_tube:
            current_style = 'line'

        # Set the current style
        for i in range(self.model_style_select.count()):
            if self.model_style_select.itemText(i) == current_style:
                self.model_style_select.setCurrentIndex(i)
                break

        self.model_style_select.blockSignals(False)

    def _set_tab_visible(self, widget, visible: bool):
        """Show/hide a tab in ``self.ops_tabs`` by its inner widget."""
        idx = self.ops_tabs.indexOf(widget)
        if idx < 0:
            return
        # Qt ≥ 5.15 exposes setTabVisible; older versions: no-op but tab stays
        setter = getattr(self.ops_tabs, "setTabVisible", None)
        if callable(setter):
            setter(idx, visible)

    def _select_default_ops_tab(self):
        """Pick the first visible tab as the current one if needed."""
        current = self.ops_tabs.currentIndex()
        is_current_visible = True
        try:
            w = self.ops_tabs.widget(current)
            if w is not None and not w.isVisible():
                is_current_visible = False
        except Exception:
            pass
        if is_current_visible:
            return
        for i in range(self.ops_tabs.count()):
            w = self.ops_tabs.widget(i)
            if w is not None and w.isVisible():
                self.ops_tabs.setCurrentIndex(i)
                return

    def connect_with(self, layer):
        super().connect_with(layer)
        # Update style availability after connecting with layer
        self._update_style_availability()
        # Update region placeholder with actual data range
        self._update_region_placeholder()
        # Update chromosome numbers checkbox state based on layer visibility
        self._update_chr_labels_checkbox()
        # Show labels section only for multi-chromosome layers
        try:
            if hasattr(layer, 'df'):
                num = int(layer.df['chrom'].nunique())
                self.labels_group.setVisible(num > 1)
        except Exception:
            self.labels_group.setVisible(False)

    def update_params(self):
        self.on_opacity_changed()
        self.on_width_changed()
        # Sync color combo with current layer color settings
        try:
            if len(self.layers) > 0:
                props = getattr(self.layers[0], 'cache_props', {})
                mode = props.get('color_mode', 'rainbow')
                if mode == 'single':
                    self._set_model_color_ui_to_hex(props.get('single_color', '#FFFFFF'))
                else:
                    text = 'Rainbow (Multi-chromosome)' if self.chrom_group.isVisible() else 'Rainbow'
                    idx = self.model_color_mode.findText(text)
                    if idx >= 0:
                        self.model_color_mode.setCurrentIndex(idx)
        except Exception:
            pass


    def on_take_subset(self):
        for layer in self.layers:
            df = layer.cache_props.get('df')
            if df is None:
                continue
            chr_colormap = layer.cache_props.get('chr_colormap')
            sub_df = self.subset_window.subset_dataframe(df)
            if sub_df.shape[0] == 0:
                continue
            name = 'subset: ' + ' '.join(sorted([str(r) for r in self.subset_window.ranges]))
            new_layer = layer.canvas.control_panel.add_chromatin_layer(sub_df, chr_colormap, parent=layer, name=name)
            # re-render for transparency
            new_layer.parent.re_render(parent=True)

    def sync_ui_from_cache(self):
        """Update UI controls to reflect actual layer cache_props values."""
        if not self.layers:
            return
        layer = self.layers[0]
        props = layer.cache_props

        self.model_style_select.blockSignals(True)
        style = props.get('style', 'line')
        idx = self.model_style_select.findText(style)
        if idx >= 0:
            self.model_style_select.setCurrentIndex(idx)
        self.high_quality_checkbox.setVisible(style == 'tube')
        self.model_style_select.blockSignals(False)

        self.width_control.blockSignals(True)
        self.width_control.setValue(props.get('width', 1.0))
        self.width_control.blockSignals(False)

        self.opacity_control.blockSignals(True)
        self.opacity_control.setValue(props.get('opacity', 1.0))
        self.opacity_control.blockSignals(False)

        color_mode = props.get('color_mode', 'rainbow')
        self.model_color_mode.blockSignals(True)
        if color_mode == 'single':
            self.model_color_mode.setCurrentText('Custom')
        elif color_mode == 'per_trace':
            self.model_color_mode.setCurrentText('Per Trace')
        else:
            self.model_color_mode.setCurrentText('Rainbow')
        self.model_color_mode.blockSignals(False)
        is_single = (color_mode == 'single')
        self.single_color_btn.setVisible(is_single)
        self.single_color_hex.setVisible(is_single)
        if is_single:
            hex_color = props.get('single_color', '#FFFFFF')
            self.single_color_hex.setText(hex_color)
            self.single_color_btn.setStyleSheet(f"background-color:{hex_color}")

        self.high_quality_checkbox.blockSignals(True)
        self.high_quality_checkbox.setChecked(props.get('high_quality', False))
        self.high_quality_checkbox.blockSignals(False)

        # Sync layer label and background from canvas state
        canvas = layer.canvas
        self.label_font_control.blockSignals(True)
        self.label_font_control.setValue(getattr(canvas.layer_title, 'font_size', 20.0))
        self.label_font_control.blockSignals(False)

        self.label_position_control.blockSignals(True)
        pos = getattr(canvas, '_label_position', 'Top Left')
        idx = self.label_position_control.findText(pos)
        if idx >= 0:
            self.label_position_control.setCurrentIndex(idx)
        self.label_position_control.blockSignals(False)

        bg_hex = getattr(canvas.view, 'bgcolor', '#000000')
        bg_map = {'#000000': 'Black', '#FFFFFF': 'White', '#C0C0C0': 'Light Gray'}
        bg_name = bg_map.get(bg_hex, 'Black')
        self.bg_color_control.blockSignals(True)
        idx = self.bg_color_control.findText(bg_name)
        if idx >= 0:
            self.bg_color_control.setCurrentIndex(idx)
        self.bg_color_control.blockSignals(False)

    def _get_main_window(self):
        """Get main window reference for link_canvas check."""
        from PyQt5.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'link_canvas') and hasattr(widget, 'get_all_canvas'):
                return widget
        return None

    def _get_linked_layers_and_canvases(self):
        """Get all layers and canvases when linked, else current only."""
        main = self._get_main_window()
        if main and main.link_canvas:
            layers = []
            canvases = []
            for canvas in main.get_all_canvas():
                layers.extend(canvas.control_panel.layers)
                canvases.append(canvas)
            return layers, canvases
        return self.layers, [self.layers[0].canvas] if self.layers else []

    def _render_canvases(self, canvases):
        """Render all given canvases."""
        for canvas in canvases:
            if hasattr(canvas.backend, 'render'):
                canvas.backend.render()

    def on_width_changed(self):
        style = self.model_style_select.currentText()
        width = self.width_control.value()
        layers, canvases = self._get_linked_layers_and_canvases()
        for layer in layers:
            layer.cache_props['width'] = width
            if style != "line":
                layer.remove()
                layer.draw(width=width)
        self._render_canvases(canvases)

    def on_opacity_changed(self):
        val = self.opacity_control.value()
        layers, canvases = self._get_linked_layers_and_canvases()
        for layer in layers:
            layer.set_props('opacity', val)
            layer.cache_props['opacity'] = val
        self._render_canvases(canvases)

    def on_model_style_change(self):
        style = self.model_style_select.currentText()
        self.high_quality_checkbox.setVisible(style == 'tube')

        layers, canvases = self._get_linked_layers_and_canvases()
        for layer in layers:
            layer.remove()
            layer.draw(style=style)

        if style == 'line':
            self.width_control.setMaximum(20.0)
            self.width_control.setMinimum(1.0)
            self.width_control.setSingleStep(1.0)
            self.width_control.setValue(1.0)
        elif style == 'points':
            self.width_control.setMaximum(2.0)
            self.width_control.setMinimum(0)
            self.width_control.setSingleStep(0.1)
            self.width_control.setValue(0.5)
        elif style == 'tube':
            self.width_control.setMaximum(5.0)
            self.width_control.setMinimum(0)
            self.width_control.setSingleStep(0.1)
            self.width_control.setValue(0.5)

        self._render_canvases(canvases)

    def on_high_quality_changed(self):
        """Handle high quality checkbox state change."""
        high_quality = self.high_quality_checkbox.isChecked()
        layers, canvases = self._get_linked_layers_and_canvases()
        for layer in layers:
            layer.cache_props['high_quality'] = high_quality
            layer.remove()
            layer.draw()
        self._render_canvases(canvases)

    def on_model_color_mode_change(self):
        mode = self.model_color_mode.currentText()
        is_single = (mode == 'Custom')
        self.single_color_btn.setVisible(is_single)
        self.single_color_hex.setVisible(is_single)
        if mode == 'Custom':
            mode_key = 'single'
        elif mode == 'Per Trace':
            mode_key = 'per_trace'
        else:
            mode_key = 'rainbow'
        layers, canvases = self._get_linked_layers_and_canvases()
        for layer in layers:
            layer.cache_props['color_mode'] = mode_key
            layer.remove()
            layer.draw()
        self._render_canvases(canvases)

    def on_pick_single_color(self):
        current = QColor(self.single_color_hex.text() or "#FFFFFF")
        color = QColorDialog.getColor(current, self)
        if color.isValid():
            hex_color = color.name()
            self.single_color_hex.setText(hex_color)
            self.single_color_btn.setStyleSheet(f"background-color:{hex_color}")
            self._apply_single_color(hex_color)

    def on_single_color_hex_changed(self):
        text = self.single_color_hex.text()
        try:
            if text.startswith('#') and len(text) == 7 and QColor(text).isValid():
                self.single_color_btn.setStyleSheet(f"background-color:{text}")
                self._apply_single_color(text)
        except Exception:
            pass

    def _apply_single_color(self, hex_color: str):
        layers, canvases = self._get_linked_layers_and_canvases()
        for layer in layers:
            layer.cache_props['color_mode'] = 'single'
            layer.cache_props['single_color'] = hex_color
            layer.remove()
            layer.draw()
        self._render_canvases(canvases)
        self._update_style_availability()
    

    def _set_model_color_ui_to_hex(self, hex_color: str):
        """Set the color combo to reflect a specific hex color.
        If the hex matches a named color, select that; otherwise add/select a custom hex item."""
        try:
            color_map = {
                "White": "#FFFFFF", "Black": "#000000", "Red": "#FF0000", "Green": "#008000",
                "Blue": "#0000FF", "Yellow": "#FFFF00", "Cyan": "#00FFFF", "Magenta": "#FF00FF",
                "Orange": "#FFA500", "Purple": "#800080", "Brown": "#A52A2A", "Pink": "#FFC0CB",
                "Gray": "#808080", "Olive": "#808000", "Navy": "#000080", "Lime": "#00FF00",
                "Maroon": "#800000", "Teal": "#008080", "Silver": "#C0C0C0", "Gold": "#FFD700"
            }
            # Try to find named color
            for name, val in color_map.items():
                if val.lower() == (hex_color or '').lower():
                    idx = self.model_color_mode.findText(name)
                    if idx >= 0:
                        self.model_color_mode.setCurrentIndex(idx)
                        return
            # Add or select a custom entry
            # Switch to Custom mode and show controls
            self.model_color_mode.setCurrentText("Custom")
            self.single_color_hex.setText(hex_color.upper())
            self.single_color_btn.setStyleSheet(f"background-color:{hex_color}")
            self.single_color_btn.setVisible(True)
            self.single_color_hex.setVisible(True)
        except Exception:
            pass

    def on_labels_mode_change(self):
        mode_text = self.labels_mode.currentText()
        if mode_text.startswith('Follow'):
            mode_key = 'follow'
        elif mode_text == 'White':
            mode_key = 'white'
        else:
            mode_key = 'black'
        # apply to the current canvas control
        if len(self.layers) > 0:
            canvas_control = self.layers[0].canvas.control_panel
            canvas_control.set_chr_label_color_mode(mode_key)

    def on_labels_enable_change(self):
        enabled = self.labels_enable.isChecked()
        if len(self.layers) > 0:
            canvas_control = self.layers[0].canvas.control_panel
            canvas_control.set_chr_labels_enabled(enabled)
    
    def on_labels_font_size_change(self):
        font_size = self.labels_font_size.value()
        # Update the chromosome numbers with new font size
        if len(self.layers) > 0:
            canvas_control = self.layers[0].canvas.control_panel
            canvas_control.set_chr_label_font_size(font_size)

    def on_pick_region_color(self):
        current = QColor(self.region_color_hex.text() or "#FF6A00")
        color = QColorDialog.getColor(current, self)
        if color.isValid():
            self.region_color_hex.setText(color.name())
            self.region_color_btn.setStyleSheet(f"background-color:{color.name()}")

    def on_region_hex_changed(self):
        text = self.region_color_hex.text()
        try:
            if text.startswith('#') and len(text) == 7 and QColor(text).isValid():
                self.region_color_btn.setStyleSheet(f"background-color:{text}")
        except Exception:
            pass
    
    def on_region_chr_changed(self):
        """Update the valid range display when chromosome selection changes."""
        if len(self.layers) == 0 or not hasattr(self.layers[0], 'df'):
            return
        
        selected_chr = self.region_chr_select.currentText()
        if not selected_chr:
            return
        
        try:
            df = self.layers[0].df
            chr_data = df[df['chrom'] == selected_chr]
            
            if len(chr_data) > 0:
                min_start = int(chr_data['start'].min())
                max_end = int(chr_data['end'].max())
                
                # Update range label
                self.region_range_label.setText(f"Valid range: {min_start:,} - {max_end:,}")
                
                # Update placeholder with example
                region_size = min(1000000, int((max_end - min_start) * 0.1))
                example_start = min_start
                example_end = min_start + region_size
                self.region_input.setPlaceholderText(f"{example_start}-{example_end}")
                
                # Update tooltip
                self.region_input.setToolTip(
                    f"Enter coordinates within the range: {min_start:,} - {max_end:,}\n"
                    f"Example: {example_start}-{example_end}"
                )
        except:
            pass

    def on_create_region_subset(self):
        # Get selected chromosome from dropdown
        chrom = self.region_chr_select.currentText()
        if not chrom:
            QMessageBox.warning(self, "Invalid input", "Please select a chromosome.")
            return
        
        # Get region coordinates
        region = self.region_input.text().strip()
        if len(self.layers) == 0:
            QMessageBox.warning(self, "Invalid input", "No layer is available to create a region subset.")
            return
        if region == "":
            QMessageBox.warning(self, "Invalid input", "Please enter start and end coordinates (e.g., 100000-200000).")
            return
        
        # Parse coordinates (now just start-end, not chr:start-end)
        try:
            pos = region.replace(',', '')
            if '-' in pos:
                start, end = pos.split('-')
            else:
                QMessageBox.warning(self, "Invalid input", "Please use format: start-end (e.g., 100000-200000)")
                return
            start = int(start)
            end = int(end)
        except Exception:
            QMessageBox.warning(self, "Invalid input", "Coordinate format error. Expected 'start-end', e.g. '100000-200000'.")
            return
        
        # Use the layer currently selected in the canvas control
        layer = self.layers[0].canvas.control_panel.current_layer or self.layers[0]
        if not hasattr(layer, 'df'):
            QMessageBox.warning(self, "Invalid state", "Current layer has no dataframe to subset from.")
            return
        df = layer.df
        chr_colormap = layer.cache_props.get('chr_colormap', {})
        
        # Get available chromosomes
        available_chroms = df['chrom'].unique()
        
        # More flexible chromosome matching
        chrom_str = df['chrom'].astype(str)
        
        # Try different matching strategies
        # 1. Exact match
        mask_chr = chrom_str == chrom
        
        # 2. Case-insensitive match
        if mask_chr.sum() == 0:
            mask_chr = chrom_str.str.lower() == chrom.lower()
        
        # 3. Try without 'chr' prefix
        if mask_chr.sum() == 0:
            chrom_norm = chrom.lower().replace('chr', '')
            mask_chr = chrom_str.str.lower().str.replace('chr', '') == chrom_norm
        
        # 4. Try adding 'chr' prefix if not present
        if mask_chr.sum() == 0 and not chrom.lower().startswith('chr'):
            chrom_with_chr = 'chr' + chrom
            mask_chr = chrom_str.str.lower() == chrom_with_chr.lower()
        
        # Check if chromosome exists
        if mask_chr.sum() == 0:
            QMessageBox.warning(self, "Chromosome not found", 
                f"Chromosome '{chrom}' not found in data.\n\n"
                f"Available chromosomes:\n{', '.join(map(str, sorted(available_chroms)))}")
            return
        
        s0, s1 = (start, end) if start <= end else (end, start)
        # Use overlap selection to be robust to bin edges
        try:
            starts = df['start'].astype(int)
            ends = df['end'].astype(int)
        except Exception:
            starts = df['start']
            ends = df['end']
        
        # Get the actual data range for this chromosome
        chr_starts = starts[mask_chr]
        chr_ends = ends[mask_chr]
        chr_min = chr_starts.min()
        chr_max = chr_ends.max()
        
        pos_overlap = (starts <= s1) & (ends >= s0)
        sub_df = df[mask_chr & pos_overlap].copy()
        
        if sub_df.shape[0] <= 0:
            # Provide helpful information about the actual data range
            QMessageBox.warning(self, "No data in region", 
                f"No data found in region {chrom}:{s0:,}-{s1:,}\n\n"
                f"The actual data range for {chrom} is:\n"
                f"{chr_min:,} - {chr_max:,}\n\n"
                f"Example valid regions:\n"
                f"  {chrom}:{chr_min:,}-{chr_min + 1000000:,}\n"
                f"  {chrom}:{chr_max - 1000000:,}-{chr_max:,}")
            return
        name = f"region: {chrom}:{s0}-{s1}"
        # Ensure a valid color map for the new subset layer
        # Always use the region color for region subsets to make them visually distinct
        region_color = self.region_color_hex.text() or "#CD18FC"
        # Create a new colormap with just the region's chromosome
        chr_colormap = {chrom: region_color}
        # Also handle normalized chromosome names
        chrom_norm = chrom.lower().replace('chr', '')
        if chrom_norm != chrom:
            chr_colormap[chrom_norm] = region_color
        
        # add_chromatin_layer will inherit width and style; force subset to use the region color
        new_layer = layer.canvas.control_panel.add_chromatin_layer(sub_df, chr_colormap, parent=layer, name=name)
        try:
            new_layer.cache_props['color_mode'] = 'single'
            new_layer.cache_props['single_color'] = region_color
            new_layer.remove()
            new_layer.draw()
            # Update its UI selection to this color
            if hasattr(new_layer, 'control_panel') and hasattr(new_layer.control_panel, '_set_model_color_ui_to_hex'):
                new_layer.control_panel._set_model_color_ui_to_hex(region_color)
        except Exception:
            pass
        if new_layer.parent:
            new_layer.parent.re_render(parent=True)

    # ── Trace Management ────────────────────────────────────────────────────
    def on_trace_mode_changed(self, mode: str):
        placeholders = {
            "Single":   "1",
            "Range":    "1-50",
            "Multiple": "1,5,20",
        }
        self.trace_id_input.setPlaceholderText(placeholders.get(mode, "1"))
        self.trace_id_input.clear()

    def on_pick_trace_color(self):
        current = QColor(self.trace_color_hex.text() or "#FF6A00")
        color = QColorDialog.getColor(current, self)
        if color.isValid():
            self.trace_color_hex.setText(color.name())
            self.trace_color_btn.setStyleSheet(f"background-color:{color.name()}")

    def on_trace_hex_changed(self):
        text = self.trace_color_hex.text()
        if text.startswith('#') and len(text) == 7 and QColor(text).isValid():
            self.trace_color_btn.setStyleSheet(f"background-color:{text}")

    def _parse_trace_selection(self, mode: str, text: str, available):
        """Return list of trace_ids from user input, or (None, error_msg)."""
        text = text.strip()
        if not text:
            return None, "Please enter a trace ID."
        avail_set = set(map(str, available))
        selected = []
        try:
            if mode == "Single":
                selected = [text]
            elif mode == "Range":
                if '-' not in text:
                    return None, "Range format: 'start-end' (e.g. '1-50')."
                a, b = text.split('-', 1)
                a, b = int(a.strip()), int(b.strip())
                lo, hi = min(a, b), max(a, b)
                # Only include IDs that actually exist in the data, preserving numeric order
                numeric_avail = sorted(int(x) for x in available if str(x).lstrip('-').isdigit())
                selected = [str(i) for i in numeric_avail if lo <= i <= hi]
            elif mode == "Multiple":
                selected = [t.strip() for t in text.split(',') if t.strip()]
            else:
                return None, f"Unknown mode: {mode}"
        except ValueError:
            return None, "Could not parse trace IDs. Check the format."
        missing = [s for s in selected if s not in avail_set]
        if missing:
            return None, f"Trace IDs not found: {', '.join(missing[:5])}" + (" ..." if len(missing) > 5 else "")
        return selected, None

    def on_create_trace_subset(self):
        if len(self.layers) == 0:
            QMessageBox.warning(self, "Invalid state", "No layer available to subset.")
            return
        layer = self.layers[0].canvas.control_panel.current_layer or self.layers[0]
        if not hasattr(layer, 'df') or 'trace_id' not in layer.df.columns:
            QMessageBox.warning(self, "Invalid state", "Current layer has no trace_id column.")
            return
        df = layer.df
        available = df['trace_id'].unique()

        mode = self.trace_mode_select.currentText()
        selected, err = self._parse_trace_selection(mode, self.trace_id_input.text(), available)
        if err:
            QMessageBox.warning(self, "Invalid trace selection", err)
            return

        # Compare as strings to sidestep categorical/int/str dtype differences
        sub_df = df[df['trace_id'].astype(str).isin(selected)].copy()
        if sub_df.shape[0] == 0:
            QMessageBox.warning(self, "No data", "Selected traces produced an empty subset.")
            return

        if mode == "Single":
            name = f"trace_{selected[0]}"
        elif mode == "Range":
            name = f"traces_{selected[0]}-{selected[-1]}"
        else:
            preview = ",".join(selected[:3])
            if len(selected) > 3:
                preview += ",..."
            name = f"traces_{preview}"

        trace_color = self.trace_color_hex.text() or "#FF6A00"
        chr_colormap = dict(layer.cache_props.get('chr_colormap', {}))

        new_layer = layer.canvas.control_panel.add_chromatin_layer(
            sub_df, chr_colormap, parent=layer, name=name
        )
        try:
            new_layer.cache_props['color_mode'] = 'single'
            new_layer.cache_props['single_color'] = trace_color
            new_layer.remove()
            new_layer.draw()
            if hasattr(new_layer, 'control_panel') and hasattr(new_layer.control_panel, '_set_model_color_ui_to_hex'):
                new_layer.control_panel._set_model_color_ui_to_hex(trace_color)
        except Exception:
            pass
        if new_layer.parent:
            new_layer.parent.re_render(parent=True)

    # ── Trace Statistics (E) ────────────────────────────────────────────────
    def _current_layer_df(self):
        """Return the DataFrame of the canvas's current layer, or None."""
        if not self.layers:
            return None, None
        layer = self.layers[0].canvas.control_panel.current_layer or self.layers[0]
        if not hasattr(layer, 'df'):
            return None, None
        return layer, layer.df

    def _show_figure(self, fig, title: str):
        """Display a matplotlib Figure inside a dockable Qt dialog."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        from matplotlib.backends.backend_qt5agg import (
            FigureCanvasQTAgg as _Canvas,
            NavigationToolbar2QT as _Toolbar,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(720, 620)
        layout = QVBoxLayout(dlg)
        canvas = _Canvas(fig)
        toolbar = _Toolbar(canvas, dlg)
        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        dlg.show()
        # Avoid GC
        self._figure_dialogs.append(dlg)

    def on_show_distance_matrix(self):
        layer, df = self._current_layer_df()
        if df is None:
            QMessageBox.warning(self, "Invalid state", "No layer available.")
            return
        from uchrom.fea import mean_distance_matrix
        from uchrom.pl import plot_distance_matrix
        try:
            chrom = df['chrom'].iloc[0] if df['chrom'].nunique() == 1 else None
            dm, bin_ids, n = mean_distance_matrix(df, chrom=chrom)
            unit = self._coord_unit(layer)
            title = f"Median pairwise distance ({n} traces"
            if chrom is not None:
                title += f", {chrom}"
            title += ")"
            fig = plot_distance_matrix(dm, bin_ids=bin_ids, title=title)
            if unit:
                fig.axes[-1].set_ylabel(f"Distance ({unit})")
            self._show_figure(fig, title)
        except Exception as e:
            QMessageBox.warning(self, "Compute failed", str(e))

    def on_show_contact_map(self):
        layer, df = self._current_layer_df()
        if df is None:
            QMessageBox.warning(self, "Invalid state", "No layer available.")
            return
        from uchrom.fea import contact_frequency
        from uchrom.pl import plot_contact_map
        try:
            threshold = float(self.stats_threshold.value())
            chrom = df['chrom'].iloc[0] if df['chrom'].nunique() == 1 else None
            cm, bin_ids, n = contact_frequency(df, threshold=threshold, chrom=chrom)
            unit = self._coord_unit(layer)
            thr_str = f"{threshold:g} {unit}" if unit else f"{threshold:g}"
            title = f"Contact freq (threshold={thr_str}, {n} traces)"
            fig = plot_contact_map(cm, bin_ids=bin_ids, title=title)
            self._show_figure(fig, title)
        except Exception as e:
            QMessageBox.warning(self, "Compute failed", str(e))

    def on_show_rg_histogram(self):
        layer, df = self._current_layer_df()
        if df is None:
            QMessageBox.warning(self, "Invalid state", "No layer available.")
            return
        from uchrom.fea import radius_of_gyration
        from uchrom.pl import plot_rg_histogram
        try:
            chrom = df['chrom'].iloc[0] if df['chrom'].nunique() == 1 else None
            rg = radius_of_gyration(df, chrom=chrom)
            unit = self._coord_unit(layer)
            title = f"Radius of gyration ({rg.size} traces)"
            fig = plot_rg_histogram(rg, title=title)
            if unit:
                fig.axes[0].set_xlabel(f"Radius of gyration ({unit})")
            self._show_figure(fig, title)
        except Exception as e:
            QMessageBox.warning(self, "Compute failed", str(e))

    def _coord_unit(self, layer):
        """Best-effort coordinate unit discovery (µm / nm) for axis labels."""
        try:
            uns = getattr(layer, 'uns', None) or {}
            return uns.get('xyz_unit')
        except Exception:
            return None

    # ── Small multiples (F) ─────────────────────────────────────────────────
    def on_split_by_trace(self):
        import math

        layer, df = self._current_layer_df()
        if df is None or 'trace_id' not in df.columns:
            QMessageBox.warning(self, "Invalid state", "Current layer has no trace_id.")
            return
        n = int(self.stats_split_spin.value())
        available = list(df['trace_id'].unique())
        if n > len(available):
            n = len(available)
        selected = available[:n]
        # Work through the owning canvas's main window
        canvas = layer.canvas
        main_window = getattr(canvas, 'main_window', None)
        if main_window is None:
            QMessageBox.warning(self, "Invalid state", "Cannot locate main window.")
            return
        chr_colormap = dict(layer.cache_props.get('chr_colormap', {}))

        # Lay out as a ~square grid: ceil(sqrt(N)) columns, ceil(N/cols) rows.
        cols = max(1, int(math.ceil(math.sqrt(n))))
        rows = max(1, int(math.ceil(n / cols)))

        for i, tid in enumerate(selected):
            sub = df[df['trace_id'].astype(str) == str(tid)].copy()
            row_idx = i % rows
            # First canvas of each column: 'h' (new column).  Subsequent
            # canvases in the column: 'v' (new row within the current column).
            main_window.add_canvas('h' if row_idx == 0 else 'v')
            cur_canvas = main_window.canvas
            new_layer = cur_canvas.control_panel.add_chromatin_layer(
                sub, chr_colormap, name=f"trace_{tid}"
            )
            try:
                new_layer.cache_props['color_mode'] = 'rainbow'
                new_layer.remove()
                new_layer.draw()
            except Exception:
                pass

    def on_label_font_changed(self):
        val = self.label_font_control.value()
        if len(self.layers) == 0:
            return
        _, canvases = self._get_linked_layers_and_canvases()
        for canvas in canvases:
            canvas.set_layer_title_font_size(val)

    def on_label_position_changed(self):
        position = self.label_position_control.currentText()
        if len(self.layers) == 0:
            return
        _, canvases = self._get_linked_layers_and_canvases()
        for canvas in canvases:
            canvas.set_layer_title_position(position)

    def on_label_color_changed(self):
        color_name = self.label_color_control.currentText()
        is_custom = (color_name == 'Custom')

        self.label_color_btn.setVisible(is_custom)
        self.label_color_hex.setVisible(is_custom)

        if len(self.layers) == 0:
            return

        _, canvases = self._get_linked_layers_and_canvases()
        if is_custom:
            hex_color = self.label_color_hex.text()
            from PyQt5.QtGui import QColor
            if hex_color and QColor(hex_color).isValid():
                for canvas in canvases:
                    canvas.set_layer_title_color_hex(hex_color)
        else:
            for canvas in canvases:
                canvas.set_layer_title_color(color_name)
    
    def on_pick_label_color(self):
        """Open color picker for label color."""
        from PyQt5.QtWidgets import QColorDialog
        from PyQt5.QtGui import QColor
        
        current = QColor(self.label_color_hex.text() or "#CD18FC")
        color = QColorDialog.getColor(current, self)
        if color.isValid():
            hex_color = color.name()
            self.label_color_hex.setText(hex_color)
            self.label_color_btn.setStyleSheet(f"background-color:{hex_color}")
            self._apply_label_custom_color(hex_color)

    def on_label_color_hex_changed(self):
        """Handle manual hex color input for label."""
        text = self.label_color_hex.text()
        try:
            from PyQt5.QtGui import QColor
            if text.startswith('#') and len(text) == 7 and QColor(text).isValid():
                self.label_color_btn.setStyleSheet(f"background-color:{text}")
                self._apply_label_custom_color(text)
        except Exception:
            pass

    def _apply_label_custom_color(self, hex_color: str):
        """Apply custom hex color to label."""
        if len(self.layers) == 0:
            return
        _, canvases = self._get_linked_layers_and_canvases()
        for canvas in canvases:
            canvas.set_layer_title_color_hex(hex_color)

    def on_bg_color_changed(self):
        color_name = self.bg_color_control.currentText()
        if len(self.layers) == 0:
            return
        main = self._get_main_window()
        if main and main.link_canvas:
            canvases = list(main.get_all_canvas())
        else:
            canvases = [self.layers[0].canvas]
        for canvas in canvases:
            canvas.set_background_color(color_name)
            canvas.update_layer_title()

    def _update_chromosome_list(self):
        # Update the chromosome dropdown list
        self.chrom_select.blockSignals(True)
        self.chrom_select.clear()
        
        if len(self.layers) > 0:
            layer = self.layers[0]
            if hasattr(layer, 'df'):
                chromosomes = sorted(layer.df['chrom'].unique())
                self.chrom_select.addItems([str(c) for c in chromosomes])
                if len(chromosomes) > 0:
                    self.chrom_select.setCurrentIndex(0)
                    self._update_selected_chromosome_display()
        
        self.chrom_select.blockSignals(False)
    
    def _update_region_placeholder(self):
        """Update region chromosome dropdown and placeholder."""
        if len(self.layers) == 0 or not hasattr(self.layers[0], 'df'):
            return
        
        try:
            df = self.layers[0].df
            chromosomes = sorted(df['chrom'].unique())
            
            # Populate chromosome dropdown for region selection
            self.region_chr_select.blockSignals(True)
            self.region_chr_select.clear()
            self.region_chr_select.addItems([str(c) for c in chromosomes])
            self.region_chr_select.blockSignals(False)
            
            # Set first chromosome and update range display
            if len(chromosomes) > 0:
                self.region_chr_select.setCurrentIndex(0)
                self.on_region_chr_changed()
        except:
            pass

    def _update_chr_labels_checkbox(self):
        """Update chromosome numbers checkbox based on layer visibility."""
        try:
            if len(self.layers) > 0:
                layer = self.layers[0]
                # Enable checkbox only if layer is visible
                if hasattr(layer, 'is_visible'):
                    self.labels_enable.blockSignals(True)
                    # If layer is not visible, uncheck the checkbox
                    if not layer.is_visible:
                        self.labels_enable.setChecked(False)
                    self.labels_enable.blockSignals(False)
                # Also toggle the whole labels group by chromosome count
                if hasattr(layer, 'df'):
                    self.labels_group.setVisible(int(layer.df['chrom'].nunique()) > 1)
        except:
            pass
    
    def _update_selected_chromosome_display(self):
        # Update color display for selected chromosome
        selected_chrom = self.chrom_select.currentText()
        if selected_chrom and len(self.layers) > 0:
            layer = self.layers[0]
            chr_colormap = layer.cache_props.get('chr_colormap', {})
            current_color = chr_colormap.get(selected_chrom, "#CD18FC")
            
            self.chrom_color_btn.setStyleSheet(f"background-color: {current_color}")
            self.chrom_hex_input.blockSignals(True)
            self.chrom_hex_input.setText(current_color)
            self.chrom_hex_input.blockSignals(False)

    def on_chromosome_selected(self):
        # Handle chromosome selection change
        self._update_selected_chromosome_display()

    def on_change_chrom_color(self):
        # Open color picker for selected chromosome
        selected_chrom = self.chrom_select.currentText()
        if not selected_chrom:
            return
            
        current_color = self.chrom_hex_input.text() or "#CD18FC"
        color = QColorDialog.getColor(QColor(current_color), self)
        if color.isValid():
            hex_color = color.name()
            self._apply_chromosome_color(selected_chrom, hex_color)

    def on_chrom_hex_changed(self):
        # Handle hex input change
        selected_chrom = self.chrom_select.currentText()
        hex_text = self.chrom_hex_input.text()
        
        if selected_chrom and hex_text.startswith('#') and len(hex_text) == 7:
            try:
                color = QColor(hex_text)
                if color.isValid():
                    self._apply_chromosome_color(selected_chrom, hex_text)
            except:
                pass

    def _apply_chromosome_color(self, chromosome, hex_color):
        # Apply color to specific chromosome
        self.chrom_color_btn.setStyleSheet(f"background-color: {hex_color}")
        self.chrom_hex_input.blockSignals(True)
        self.chrom_hex_input.setText(hex_color)
        self.chrom_hex_input.blockSignals(False)
        
        # Update all layers
        for layer in self.layers:
            if hasattr(layer, 'cache_props'):
                if 'chr_colormap' not in layer.cache_props:
                    layer.cache_props['chr_colormap'] = {}
                layer.cache_props['chr_colormap'][chromosome] = hex_color
                layer.remove()
                layer.draw()
                if hasattr(layer, 'parent') and layer.parent:
                    layer.parent.re_render(parent=True)

    def on_create_chrom_subset(self):
        # Create subset for selected chromosome
        selected_chrom = self.chrom_select.currentText()
        if not selected_chrom or len(self.layers) == 0:
            return
            
        current_layer = self.layers[0]
        if hasattr(current_layer, 'df'):
            df = current_layer.df
            chr_colormap = current_layer.cache_props.get('chr_colormap', {})
            
            # Filter data for selected chromosome
            subset_df = df[df['chrom'] == selected_chrom].copy()
            if subset_df.shape[0] > 0:
                # Name the new layer exactly as the chromosome identifier
                name = str(selected_chrom)
                new_layer = current_layer.canvas.control_panel.add_chromatin_layer(
                    subset_df, chr_colormap, parent=current_layer, name=name
                )
                # Apply the chromosome's current color to this new single-chrom layer
                try:
                    chrom_color = chr_colormap.get(selected_chrom)
                    if chrom_color:
                        new_layer.cache_props['color_mode'] = 'single'
                        new_layer.cache_props['single_color'] = chrom_color
                        new_layer.remove()
                        new_layer.draw()
                        if hasattr(new_layer, 'control_panel') and hasattr(new_layer.control_panel, '_set_model_color_ui_to_hex'):
                            new_layer.control_panel._set_model_color_ui_to_hex(chrom_color)
                except Exception:
                    pass
                # Re-render for transparency
                if new_layer.parent:
                    new_layer.parent.re_render(parent=True)


class ChrLabelProps(LayerPropsPanel):
    def __init__(self):
        l_show_label = QLabel("Show label")
        self.show_label_ckbox = QCheckBox()
        self.show_label_ckbox.toggled.connect(self.on_toggle_show_label)

        l_label_size = QLabel("Label size")
        self.label_size_control = QSpinBox()
        self.label_size_control.setMaximum(10000)
        self.label_size_control.setMinimum(1)
        self.label_size_control.setSingleStep(100)
        self.label_size_control.setValue(1000)
        self.label_size_control.valueChanged.connect(self.on_label_size_changed)

        l_label_shift = QLabel("Label shift")
        self.label_shift_control = QDoubleSpinBox()
        self.label_shift_control.setMaximum(1.0)
        self.label_shift_control.setMinimum(-1.0)
        self.label_shift_control.setSingleStep(0.01)
        self.label_shift_control.setValue(0.05)
        self.label_shift_control.valueChanged.connect(self.on_label_shift_changed)

        layout_table = [
            [l_show_label, self.show_label_ckbox],
            [l_label_size, self.label_size_control],
            [l_label_shift, self.label_shift_control],
        ]

        super().__init__(grid_table=layout_table)

    def on_toggle_show_label(self):
        val = self.show_label_ckbox.isChecked()
        for layer in self.layers:
            layer.set_props('visible', val)

    def on_label_size_changed(self):
        val = self.label_size_control.value()
        for layer in self.layers:
            layer.set_label_props('font_size', val)

    def on_label_shift_changed(self):
        val = self.label_shift_control.value()
        for layer in self.layers:
            for i, l in enumerate(layer.vis_objs):
                ori = layer.label_ori_pos[i]
                l.pos = ori * (1+val)





