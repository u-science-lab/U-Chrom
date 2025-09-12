from PyQt5.QtWidgets import (QComboBox, QDoubleSpinBox, QSpinBox, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLineEdit, QGroupBox, 
                             QColorDialog, QMessageBox)
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
        super().__init__(grid_table=[], operation_widgets=[self.chrom_group, self.region_group])
        
        # Add grouped controls to layout after parent initialization
        self.add_grouped_layout()

    def create_grouped_controls(self):
        # Model Properties Group
        self.model_group = QGroupBox("Model Properties")
        model_layout = QGridLayout()
        
        l_style = QLabel("Style")
        self.model_style_select = QComboBox()
        self.model_style_select.addItem("line")
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
 
        l_color_mode = QLabel("Color")
        self.model_color_select = QComboBox()
        single_color_options = [
            "White", "Black", "Red", "Green", "Blue", "Yellow", "Cyan", "Magenta",
            "Orange", "Purple", "Brown", "Pink", "Gray", "Olive", "Navy", "Lime",
            "Maroon", "Teal", "Silver", "Gold"
        ]
        items = ["Rainbow"] + [f"Single - {c}" for c in single_color_options]
        self.model_color_select.addItems(items)
        self.model_color_select.setCurrentText("Rainbow")
        self.model_color_select.currentIndexChanged.connect(self.on_model_color_change)
        

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
        self.chrom_hex_input.setPlaceholderText("#FF0000")
        self.chrom_hex_input.textChanged.connect(self.on_chrom_hex_changed)
        color_layout.addWidget(self.chrom_hex_input)
        chrom_layout.addLayout(color_layout)
        
        # Subset creation button
        self.create_subset_btn = QPushButton("Create Subset of Selected Chromosome")
        self.create_subset_btn.clicked.connect(self.on_create_chrom_subset)
        chrom_layout.addWidget(self.create_subset_btn)
        
        self.chrom_group.setLayout(chrom_layout)
        # Hidden by default; will be shown for multi-chromosome datasets
        self.chrom_group.setVisible(False)

        # Region Management Group
        self.region_group = QGroupBox("Region Management")
        region_layout = QGridLayout()
        
        l_region = QLabel("Region (chr:start-end):")
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText("chr1:100000-200000")
        
        l_region_color = QLabel("Color:")
        self.region_color_btn = QPushButton()
        self.region_color_btn.setFixedSize(50, 20)
        self.region_color_btn.setStyleSheet("background-color:#FF6A00")
        self.region_color_btn.clicked.connect(self.on_pick_region_color)
        self.region_color_hex = QLineEdit("#FF6A00")
        self.region_color_hex.textChanged.connect(self.on_region_hex_changed)
        
        self.region_subset_btn = QPushButton("Create Region Subset")
        self.region_subset_btn.clicked.connect(self.on_create_region_subset)
        
        region_layout.addWidget(l_region, 0, 0)
        region_layout.addWidget(self.region_input, 0, 1)
        region_layout.addWidget(l_region_color, 1, 0)
        region_layout.addWidget(self.region_color_btn, 1, 1)
        region_layout.addWidget(self.region_color_hex, 1, 2)
        region_layout.addWidget(self.region_subset_btn, 2, 0, 1, 3)
        self.region_group.setLayout(region_layout)
        self.region_group.setVisible(True)

        # Numbers overlay color mode
        self.numbers_group = QGroupBox("Chromosome Numbers")
        numbers_layout = QGridLayout()
        self.numbers_enable = QCheckBox("Enable")
        self.numbers_enable.setChecked(True)
        self.numbers_enable.stateChanged.connect(self.on_numbers_enable_change)
        numbers_layout.addWidget(self.numbers_enable, 0, 0, 1, 2)
        l_mode = QLabel("Color mode:")
        self.numbers_mode = QComboBox()
        self.numbers_mode.addItems(["Follow chromosome", "White", "Black"])
        self.numbers_mode.currentIndexChanged.connect(self.on_numbers_mode_change)
        numbers_layout.addWidget(l_mode, 1, 0)
        numbers_layout.addWidget(self.numbers_mode, 1, 1)
        self.numbers_group.setLayout(numbers_layout)
        self.numbers_group.setVisible(True)

        self.l_perf_mode = QLabel("Tube performance")
        self.perf_mode_control = QComboBox()
        self.perf_mode_control.addItems([
            "Fast (50 segments)", "Balanced (100 segments)", "Quality (200 segments)"
        ])
        self.perf_mode_control.setCurrentText("Fast (50 segments)")
        self.perf_mode_control.currentTextChanged.connect(self.on_perf_mode_changed)

        # Add to model group layout
        model_layout.addWidget(l_style, 0, 0)
        model_layout.addWidget(self.model_style_select, 0, 1)
        model_layout.addWidget(l_width, 1, 0)
        model_layout.addWidget(self.width_control, 1, 1)
        model_layout.addWidget(l_opacity, 2, 0)
        model_layout.addWidget(self.opacity_control, 2, 1)
        model_layout.addWidget(l_color_mode, 3, 0)
        model_layout.addWidget(self.model_color_select, 3, 1)
        model_layout.addWidget(self.l_perf_mode, 4, 0)
        model_layout.addWidget(self.perf_mode_control, 4, 1)
        
        # Initially hide tube performance controls
        self.l_perf_mode.setVisible(False)
        self.perf_mode_control.setVisible(False)
        self.model_group.setLayout(model_layout)

        # Label Properties Group
        self.label_group = QGroupBox("Label Properties")
        label_layout = QGridLayout()

        l_label_font = QLabel("Font size")
        self.label_font_control = QDoubleSpinBox()
        self.label_font_control.setMaximum(10.0)
        self.label_font_control.setMinimum(1.0)
        self.label_font_control.setSingleStep(0.5)
        self.label_font_control.setValue(5.0)
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
            "White", "Black", "Red", "Green", "Blue", "Yellow", "Cyan", "Magenta",
            "Orange", "Purple", "Brown", "Pink", "Gray", "Olive", "Navy", "Lime",
            "Maroon", "Teal", "Silver", "Gold"
        ])
        self.label_color_control.setCurrentText("White")
        self.label_color_control.currentTextChanged.connect(self.on_label_color_changed)

        # Add to label group layout
        label_layout.addWidget(l_label_font, 0, 0)
        label_layout.addWidget(self.label_font_control, 0, 1)
        label_layout.addWidget(l_label_pos, 1, 0)
        label_layout.addWidget(self.label_position_control, 1, 1)
        label_layout.addWidget(l_label_color, 2, 0)
        label_layout.addWidget(self.label_color_control, 2, 1)
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
        # Insert group boxes into the Properties panel layout (exclude Chromosome/Region Management)
        # They are displayed on the Layers panel's right side via operations_panel
        self.top_layout.insertWidget(1, self.model_group)
        self.top_layout.insertWidget(2, self.numbers_group)
        self.top_layout.insertWidget(3, self.label_group)
        self.top_layout.insertWidget(4, self.canvas_group)

    def _update_style_availability(self):
        # Rebuild the style combo based on current conditions
        current_style = self.model_style_select.currentText()
        current_color = self.model_color_select.currentText()
        
        # Check chromosome count and color mode constraints
        disable_tube = False
        is_multi_chrom = False
        if len(self.layers) > 0:
            disable_tube = True
            for layer in self.layers:
                try:
                    df = layer.df
                    num_chrom = int(df['chrom'].nunique())
                    color_mode = layer.cache_props.get('color_mode', 'rainbow')
                    
                    if num_chrom > 1:
                        is_multi_chrom = True
                    
                    # If any layer is NOT (single-chromosome + rainbow), enable tube
                    if num_chrom != 1 or color_mode != 'rainbow':
                        disable_tube = False
                        break
                except Exception:
                    disable_tube = False
                    break
        
        # Rebuild the combo with appropriate options
        self.model_style_select.blockSignals(True)  # Prevent triggering events during rebuild
        self.model_style_select.clear()
        
        # Always add basic styles
        self.model_style_select.addItem("line")
        
        # Add points/tube based on layer constraints and performance
        layers_row_num = [l.df.shape[0] for l in self.layers] if self.layers else []
        points_thresh = 20000
        tube_thresh = 5000
        
        if len(layers_row_num) == 0 or all([n <= points_thresh for n in layers_row_num]):
            self.model_style_select.addItem('points')
        
        has_tube_option = False
        if not disable_tube and (len(layers_row_num) == 0 or all([n <= tube_thresh for n in layers_row_num])):
            self.model_style_select.addItem('tube')
            has_tube_option = True
        
        # Show/hide tube performance controls based on tube availability
        self.l_perf_mode.setVisible(has_tube_option)
        self.perf_mode_control.setVisible(has_tube_option)
        
        # Update color controls and chromosome management based on chromosome count
        self.model_color_select.blockSignals(True)
        if is_multi_chrom:
            # Multi-chromosome: only rainbow mode; show both Chromosome and Region management on the right panel
            self.model_color_select.clear()
            self.model_color_select.addItem("Rainbow (Multi-chromosome)")
            self.model_color_select.setCurrentIndex(0)
            self.chrom_group.setVisible(True)
            self.region_group.setVisible(True)
            self._update_chromosome_list()
        else:
            # Single chromosome: allow all color modes; hide Chromosome management, keep Region management visible
            self.model_color_select.clear()
            single_color_options = [
                "White", "Black", "Red", "Green", "Blue", "Yellow", "Cyan", "Magenta",
                "Orange", "Purple", "Brown", "Pink", "Gray", "Olive", "Navy", "Lime",
                "Maroon", "Teal", "Silver", "Gold"
            ]
            items = ["Rainbow"] + [f"Single - {c}" for c in single_color_options]
            self.model_color_select.addItems(items)
            # Restore previous selection if valid
            for i in range(self.model_color_select.count()):
                if self.model_color_select.itemText(i) == current_color:
                    self.model_color_select.setCurrentIndex(i)
                    break
            self.chrom_group.setVisible(False)
            self.region_group.setVisible(True)
        self.model_color_select.blockSignals(False)
        
        # Restore selection or fallback to line
        if current_style == 'tube' and disable_tube:
            current_style = 'line'
        
        # Set the current style
        for i in range(self.model_style_select.count()):
            if self.model_style_select.itemText(i) == current_style:
                self.model_style_select.setCurrentIndex(i)
                break
        
        self.model_style_select.blockSignals(False)

    def connect_with(self, layer):
        super().connect_with(layer)
        # Update style availability after connecting with layer
        self._update_style_availability()

    def update_params(self):
        self.on_opacity_changed()
        self.on_width_changed()


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

    def on_width_changed(self):
        style = self.model_style_select.currentText()
        width = self.width_control.value()
        for layer in self.layers:
            layer.cache_props['width'] = width
            for o in layer.vis_objs:
                if style == "line":
                    o.set_data(width=width)
                else:
                    layer.remove()
                    layer.draw(width=width)
                    if layer.parent:
                        layer.parent.re_render(parent=True)
        self.on_opacity_changed()

    def on_opacity_changed(self):
        val = self.opacity_control.value()
        for layer in self.layers:
            layer.set_props('opacity', val)
            layer.cache_props['opacity'] = val

    def on_model_style_change(self):
        style = self.model_style_select.currentText()
        for layer in self.layers:
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
                self.width_control.setMaximum(2.0)
                self.width_control.setMinimum(0)
                self.width_control.setSingleStep(0.05)
                self.width_control.setValue(0.1)
            if layer.parent:
                layer.parent.re_render(parent=True)

    def on_model_color_change(self):
        text = self.model_color_select.currentText()
        is_single = text.startswith('Single - ')
        color_name = text.replace('Single - ', '') if is_single else None
        color_map = {
            "White": "#FFFFFF", "Black": "#000000", "Red": "#FF0000", "Green": "#008000",
            "Blue": "#0000FF", "Yellow": "#FFFF00", "Cyan": "#00FFFF", "Magenta": "#FF00FF",
            "Orange": "#FFA500", "Purple": "#800080", "Brown": "#A52A2A", "Pink": "#FFC0CB",
            "Gray": "#808080", "Olive": "#808000", "Navy": "#000080", "Lime": "#00FF00",
            "Maroon": "#800000", "Teal": "#008080", "Silver": "#C0C0C0", "Gold": "#FFD700"
        }
        hex_color = color_map.get(color_name, "#FFFFFF") if is_single else None
        for layer in self.layers:
            layer.cache_props['color_mode'] = 'single' if is_single else 'rainbow'
            if is_single and hex_color is not None:
                layer.cache_props['single_color'] = hex_color
            layer.remove()
            layer.draw()
            if layer.parent:
                layer.parent.re_render(parent=True)
        # Update style availability after color mode change
        self._update_style_availability()

    def on_numbers_mode_change(self):
        mode_text = self.numbers_mode.currentText()
        if mode_text.startswith('Follow'):
            mode_key = 'follow'
        elif mode_text == 'White':
            mode_key = 'white'
        else:
            mode_key = 'black'
        # apply to the current canvas control
        if len(self.layers) > 0:
            canvas_control = self.layers[0].canvas.control_panel
            canvas_control.set_chr_number_color_mode(mode_key)

    def on_numbers_enable_change(self):
        enabled = self.numbers_enable.isChecked()
        if len(self.layers) > 0:
            canvas_control = self.layers[0].canvas.control_panel
            canvas_control.set_chr_numbers_enabled(enabled)

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

    def on_create_region_subset(self):
        region = self.region_input.text().strip()
        if len(self.layers) == 0:
            QMessageBox.warning(self, "Invalid input", "No layer is available to create a region subset.")
            return
        if region == "":
            QMessageBox.warning(self, "Invalid input", "Region is empty. Please enter a region like 'chr1:100000-200000'.")
            return
        # parse region like chr1:100000-200000
        try:
            chrom, pos = region.split(':')
            start, end = pos.replace(',', '').split('-')
            start = int(start)
            end = int(end)
        except Exception:
            QMessageBox.warning(self, "Invalid input", "Region format error. Expected 'chr:start-end', e.g. 'chr1:100000-200000'.")
            return
        
        # Use the layer currently selected in the canvas control
        layer = self.layers[0].canvas.control_panel.current_layer or self.layers[0]
        if not hasattr(layer, 'df'):
            QMessageBox.warning(self, "Invalid state", "Current layer has no dataframe to subset from.")
            return
        df = layer.df
        chr_colormap = layer.cache_props.get('chr_colormap', {})
        # Normalize chromosome value to handle inputs like 'chr1' vs '1'
        chrom_str = df['chrom'].astype(str)
        chrom_norm = chrom.lower().replace('chr', '')
        mask_chr = (chrom_str.str.lower() == chrom.lower()) | (chrom_str.str.lower() == chrom_norm)
        s0, s1 = (start, end) if start <= end else (end, start)
        # Use overlap selection to be robust to bin edges
        try:
            starts = df['start'].astype(int)
            ends = df['end'].astype(int)
        except Exception:
            starts = df['start']
            ends = df['end']
        pos_overlap = (starts <= s1) & (ends >= s0)
        sub_df = df[mask_chr & pos_overlap].copy()
        if sub_df.shape[0] <= 0:
            QMessageBox.warning(self, "No data", f"No pixels overlap with region {chrom}:{s0}-{s1}.")
            return
        name = f"region: {chrom}:{s0}-{s1}"
        # Ensure a valid color map for the new subset layer
        if not isinstance(chr_colormap, dict) or len(chr_colormap) == 0:
            # fallback to single color using region color
            chr_colormap = {chrom: self.region_color_hex.text() or "#FF6A00"}
        new_layer = layer.canvas.control_panel.add_chromatin_layer(sub_df, chr_colormap, parent=layer, name=name)
        if new_layer.parent:
            new_layer.parent.re_render(parent=True)

    def on_label_font_changed(self):
        val = self.label_font_control.value()
        # apply to current canvas only
        if len(self.layers) == 0:
            return
        canvas = self.layers[0].canvas
        canvas.set_layer_title_font_size(val)

    def on_label_position_changed(self):
        position = self.label_position_control.currentText()
        # apply to current canvas only
        if len(self.layers) == 0:
            return
        canvas = self.layers[0].canvas
        canvas.set_layer_title_position(position)

    def on_label_color_changed(self):
        color_name = self.label_color_control.currentText()
        # apply to current canvas only
        if len(self.layers) == 0:
            return
        canvas = self.layers[0].canvas
        canvas.set_layer_title_color(color_name)

    def on_bg_color_changed(self):
        color_name = self.bg_color_control.currentText()
        # apply to current canvas only
        if len(self.layers) == 0:
            return
        canvas = self.layers[0].canvas
        canvas.set_background_color(color_name)

    def on_perf_mode_changed(self):
        mode_text = self.perf_mode_control.currentText()
        # Extract segment count from text
        if "50" in mode_text:
            segments = 50
        elif "100" in mode_text:
            segments = 100
        elif "200" in mode_text:
            segments = 200
        else:
            segments = 50
        
        # Update all layers and re-render if currently using tube
        current_style = self.model_style_select.currentText()
        for layer in self.layers:
            layer.cache_props['tube_gradient_segments'] = segments
            if current_style == 'tube':
                layer.remove()
                layer.draw()
                if layer.parent:
                    layer.parent.re_render(parent=True)


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

    def _update_selected_chromosome_display(self):
        # Update color display for selected chromosome
        selected_chrom = self.chrom_select.currentText()
        if selected_chrom and len(self.layers) > 0:
            layer = self.layers[0]
            chr_colormap = layer.cache_props.get('chr_colormap', {})
            current_color = chr_colormap.get(selected_chrom, "#FF0000")
            
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
            
        current_color = self.chrom_hex_input.text() or "#FF0000"
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
                name = f'Chr {selected_chrom} subset'
                new_layer = current_layer.canvas.control_panel.add_chromatin_layer(
                    subset_df, chr_colormap, parent=current_layer, name=name
                )
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





