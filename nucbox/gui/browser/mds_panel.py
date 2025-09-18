"""
MDS (Multidimensional Scaling) control panel for Hi-C structure inference.
"""

import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
                            QComboBox, QProgressBar, QTextEdit, QGroupBox,
                            QFileDialog, QMessageBox, QSlider)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

from nucbox.utils.hic_io import read_hic_bed, validate_hic_data, get_chromosome_colormap
from nucbox.utils.minimds_algorithm import infer_3d_structure_minimds, MiniMDS
import numpy as np


def optimize_mds_parameters(hic_df, resolution):
    """Optimize MDS parameters based on data characteristics."""
    try:
        # Analyze data characteristics
        n_contacts = len(hic_df)
        n_positions = len(set(hic_df['chr1'].astype(str) + '_' + hic_df['pos1'].astype(str)) | 
                         set(hic_df['chr2'].astype(str) + '_' + hic_df['pos2'].astype(str)))
        
        # Calculate data density
        density = n_contacts / n_positions if n_positions > 0 else 0
        
        # Optimize parameters based on data size and density
        optimized_params = {}
        
        # Alpha parameter optimization (UI range: 1.0-10.0)
        if density > 0.1:  # High density data
            optimized_params['alpha'] = 8.0
            optimized_params['alpha2'] = 4.0
        elif density > 0.05:  # Medium density
            optimized_params['alpha'] = 6.0
            optimized_params['alpha2'] = 3.0
        else:  # Low density data
            optimized_params['alpha'] = 4.0
            optimized_params['alpha2'] = 2.0
            
        # Weight parameter optimization (UI range: 0.0-1.0)
        if n_contacts > 1000:
            optimized_params['weight'] = 0.8
        elif n_contacts > 500:
            optimized_params['weight'] = 0.6
        else:
            optimized_params['weight'] = 0.4
            
        # Resolution ratio optimization (UI range: 2-50, integer)
        if n_positions > 1000:
            optimized_params['res_ratio'] = 5
        elif n_positions > 500:
            optimized_params['res_ratio'] = 10
        else:
            optimized_params['res_ratio'] = 20
            
        # Domain smoothing optimization (UI range: 0.01-1.0)
        if density > 0.1:
            optimized_params['domain_smoothing'] = 0.8
        else:
            optimized_params['domain_smoothing'] = 0.5
            
        # Min size fraction optimization
        if n_positions > 2000:
            optimized_params['min_size_fraction'] = 0.01
        elif n_positions > 1000:
            optimized_params['min_size_fraction'] = 0.02
        else:
            optimized_params['min_size_fraction'] = 0.05
            
        return optimized_params
        
    except Exception as e:
        # Return default parameters if optimization fails
        return {
            'alpha': 6.0,
            'alpha2': 3.0,
            'weight': 0.6,
            'res_ratio': 10,
            'domain_smoothing': 0.5,
            'min_size_fraction': 0.02
        }


class MDSWorker(QThread):
    """Worker thread for MDS computation."""
    
    status = pyqtSignal(str)  # Status message
    finished = pyqtSignal(object, dict)  # particles_df, metadata
    error = pyqtSignal(str)
    
    def __init__(self, hic_df, resolution, mds_params, use_partitioned=True):
        super().__init__()
        self.hic_df = hic_df
        self.resolution = resolution
        self.mds_params = mds_params
        self.use_partitioned = use_partitioned
        
    def run(self):
        try:
            import time
            
            # Check if thread should terminate
            if self.isInterruptionRequested():
                return
                
            self.status.emit("Initializing MDS computation...")
            time.sleep(0.2)  # Small delay to show status
            
            # Check if thread should terminate
            if self.isInterruptionRequested():
                return
                
            self.status.emit("Loading Hi-C data...")
            time.sleep(0.2)
            
            # Check if thread should terminate
            if self.isInterruptionRequested():
                return
                
            self.status.emit("Creating distance matrix...")
            time.sleep(0.2)
            
            # Check if thread should terminate
            if self.isInterruptionRequested():
                return
            
            # Infer 3D structure using miniMDS algorithm
            self.status.emit("Running miniMDS algorithm...")
            
            # Check if thread should terminate before starting heavy computation
            if self.isInterruptionRequested():
                return
                
            particles_df, metadata = infer_3d_structure_minimds(
                self.hic_df, 
                self.resolution,
                use_partitioned=self.use_partitioned,
                **self.mds_params
            )
            
            # Check if thread should terminate before finishing
            if self.isInterruptionRequested():
                return
                
            self.status.emit("Finalizing results...")
            time.sleep(0.2)
            
            # Check if thread should terminate before finishing
            if self.isInterruptionRequested():
                return
                
            self.status.emit("MDS computation complete!")
            self.finished.emit(particles_df, metadata)
            
        except Exception as e:
            # Only emit error if not interrupted
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


class MDSPanel(QWidget):
    """MDS control panel for Hi-C structure inference."""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.hic_df = None
        self.particles_df = None
        self.metadata = None
        self.worker = None
        
        self.setup_ui()
        
    def __del__(self):
        """Clean up worker thread on destruction."""
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1000)  # Wait up to 1 second
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()
        
    def setup_ui(self):
        """Setup the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("Hi-C Structure Inference")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # File input section
        file_group = QGroupBox("Input Data")
        file_layout = QVBoxLayout(file_group)
        
        # File selection
        file_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: #666; font-style: italic;")
        self.browse_btn = QPushButton("Browse Hi-C BED...")
        self.browse_btn.clicked.connect(self.browse_file)
        file_row.addWidget(self.file_label)
        file_row.addWidget(self.browse_btn)
        file_layout.addLayout(file_row)
        
        # Data info
        self.data_info = QTextEdit()
        self.data_info.setMaximumHeight(100)
        self.data_info.setReadOnly(True)
        self.data_info.setPlaceholderText("Data information will appear here after loading...")
        file_layout.addWidget(self.data_info)
        
        layout.addWidget(file_group)
        
        # MDS parameters section
        params_group = QGroupBox("MDS Parameters")
        params_layout = QVBoxLayout(params_group)
        
        # Resolution
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Resolution (bp):"))
        self.resolution_spin = QSpinBox()
        self.resolution_spin.setRange(1000, 10000000)
        self.resolution_spin.setValue(100000)
        self.resolution_spin.setSuffix(" bp")
        res_row.addWidget(self.resolution_spin)
        res_row.addStretch()
        params_layout.addLayout(res_row)
        
        # Partitioned MDS
        self.partitioned_check = QCheckBox("Use Partitioned MDS (for large datasets)")
        self.partitioned_check.setChecked(True)
        self.partitioned_check.stateChanged.connect(self.toggle_partition_params)
        params_layout.addWidget(self.partitioned_check)
        
        # Partition size
        self.partition_row = QHBoxLayout()
        self.partition_row.addWidget(QLabel("Partition Size:"))
        self.partition_spin = QSpinBox()
        self.partition_spin.setRange(100, 5000)
        self.partition_spin.setValue(1000)
        self.partition_row.addWidget(self.partition_spin)
        self.partition_row.addStretch()
        params_layout.addLayout(self.partition_row)
        
        # MDS iterations
        iter_row = QHBoxLayout()
        iter_row.addWidget(QLabel("Max Iterations:"))
        self.max_iter_spin = QSpinBox()
        self.max_iter_spin.setRange(50, 1000)
        self.max_iter_spin.setValue(300)
        iter_row.addWidget(self.max_iter_spin)
        iter_row.addStretch()
        params_layout.addLayout(iter_row)
        
        # Alpha parameter (scaling factor)
        alpha_row = QHBoxLayout()
        alpha_row.addWidget(QLabel("Alpha (scaling factor):"))
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(1.0, 10.0)
        self.alpha_spin.setValue(4.0)
        self.alpha_spin.setDecimals(1)
        self.alpha_spin.setSingleStep(0.5)
        alpha_row.addWidget(self.alpha_spin)
        alpha_row.addStretch()
        params_layout.addLayout(alpha_row)
        
        # Alpha2 parameter (short-range scaling)
        alpha2_row = QHBoxLayout()
        alpha2_row.addWidget(QLabel("Alpha2 (short-range):"))
        self.alpha2_spin = QDoubleSpinBox()
        self.alpha2_spin.setRange(1.0, 5.0)
        self.alpha2_spin.setValue(2.5)
        self.alpha2_spin.setDecimals(1)
        self.alpha2_spin.setSingleStep(0.1)
        alpha2_row.addWidget(self.alpha2_spin)
        alpha2_row.addStretch()
        params_layout.addLayout(alpha2_row)
        
        # Weight parameter (distance decay prior)
        weight_row = QHBoxLayout()
        weight_row.addWidget(QLabel("Weight (distance decay):"))
        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(0.0, 1.0)
        self.weight_spin.setValue(0.05)
        self.weight_spin.setDecimals(3)
        self.weight_spin.setSingleStep(0.01)
        weight_row.addWidget(self.weight_spin)
        weight_row.addStretch()
        params_layout.addLayout(weight_row)
        
        # Resolution ratio (for partitioned MDS)
        self.res_ratio_row = QHBoxLayout()
        self.res_ratio_row.addWidget(QLabel("Resolution Ratio:"))
        self.res_ratio_spin = QSpinBox()
        self.res_ratio_spin.setRange(2, 50)
        self.res_ratio_spin.setValue(10)
        self.res_ratio_row.addWidget(self.res_ratio_spin)
        self.res_ratio_row.addStretch()
        params_layout.addLayout(self.res_ratio_row)
        
        # Domain smoothing parameter
        self.domain_smooth_row = QHBoxLayout()
        self.domain_smooth_row.addWidget(QLabel("Domain Smoothing:"))
        self.domain_smooth_spin = QDoubleSpinBox()
        self.domain_smooth_spin.setRange(0.01, 1.0)
        self.domain_smooth_spin.setValue(0.1)
        self.domain_smooth_spin.setDecimals(2)
        self.domain_smooth_spin.setSingleStep(0.01)
        self.domain_smooth_row.addWidget(self.domain_smooth_spin)
        self.domain_smooth_row.addStretch()
        params_layout.addLayout(self.domain_smooth_row)
        
        # Minimum size fraction
        self.min_size_row = QHBoxLayout()
        self.min_size_row.addWidget(QLabel("Min Size Fraction:"))
        self.min_size_spin = QDoubleSpinBox()
        self.min_size_spin.setRange(0.01, 0.5)
        self.min_size_spin.setValue(0.05)
        self.min_size_spin.setDecimals(2)
        self.min_size_spin.setSingleStep(0.01)
        self.min_size_row.addWidget(self.min_size_spin)
        self.min_size_row.addStretch()
        params_layout.addLayout(self.min_size_row)
        
        layout.addWidget(params_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.optimize_btn = QPushButton("Optimize Parameters")
        self.optimize_btn.clicked.connect(self.optimize_parameters)
        self.optimize_btn.setEnabled(False)
        button_layout.addWidget(self.optimize_btn)
        
        self.run_btn = QPushButton("Run MDS")
        self.run_btn.clicked.connect(self.run_mds)
        self.run_btn.setEnabled(False)
        self.run_btn.setStyleSheet("QPushButton { background-color: #CD18FC; color: white; font-weight: bold; }")
        button_layout.addWidget(self.run_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_mds)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("QPushButton { background-color: #666; color: white; }")
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Status display (replacing progress bar)
        self.status_label = QLabel("Ready to start MDS computation...")
        self.status_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
        
        # Results section
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)
        
        self.results_text = QTextEdit()
        self.results_text.setMaximumHeight(150)
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("MDS results will appear here...")
        results_layout.addWidget(self.results_text)
        
        # Add to visualization button
        self.add_viz_btn = QPushButton("Add to Visualization")
        self.add_viz_btn.clicked.connect(self.add_to_visualization)
        self.add_viz_btn.setEnabled(False)
        results_layout.addWidget(self.add_viz_btn)
        
        layout.addWidget(results_group)
        
        # Initialize UI state
        self.toggle_partition_params()
        
    def toggle_partition_params(self):
        """Toggle partition parameter visibility."""
        enabled = self.partitioned_check.isChecked()
        self.partition_spin.setEnabled(enabled)
        self.res_ratio_spin.setEnabled(enabled)
        self.domain_smooth_spin.setEnabled(enabled)
        self.min_size_spin.setEnabled(enabled)
        
    def browse_file(self):
        """Browse for Hi-C BED file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Hi-C BED File", "",
            "BED Files (*.bed *.bed.gz);;All Files (*)"
        )
        
        if file_path:
            self.load_hic_file(file_path)
            
    def load_hic_file(self, file_path: str):
        """Load Hi-C BED file."""
        try:
            # Read Hi-C data
            self.hic_df = read_hic_bed(file_path, self.resolution_spin.value())
            
            # Validate data
            if not validate_hic_data(self.hic_df):
                # Provide detailed error information
                error_msg = "Hi-C data validation failed. Please check:\n\n"
                error_msg += f"• File format: Should be BED format with 7 columns\n"
                error_msg += f"• Required columns: chr1, start1, end1, chr2, start2, end2, count\n"
                error_msg += f"• Data loaded: {len(self.hic_df)} contacts\n"
                error_msg += f"• Columns found: {list(self.hic_df.columns)}\n"
                error_msg += f"• Minimum contacts required: 10\n\n"
                error_msg += "Please use the example file: example_hic_data.bed"
                
                QMessageBox.warning(self, "Invalid Data", error_msg)
                return
            
            # Update UI
            self.file_label.setText(os.path.basename(file_path))
            self.file_label.setStyleSheet("color: #000; font-style: normal;")
            
            # Show data info
            info_text = f"Data loaded successfully!\n"
            info_text += f"File: {os.path.basename(file_path)}\n"
            info_text += f"Contacts: {len(self.hic_df):,}\n"
            info_text += f"Chromosomes: {sorted(self.hic_df['chr1'].unique())}\n"
            info_text += f"Resolution: {self.resolution_spin.value():,} bp"
            
            self.data_info.setText(info_text)
            
            # Enable buttons
            self.optimize_btn.setEnabled(True)
            self.run_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load Hi-C file:\n{str(e)}")
            
    def optimize_parameters(self):
        """Optimize MDS parameters."""
        if self.hic_df is None:
            return
            
        try:
            self.optimize_btn.setEnabled(False)
            self.optimize_btn.setText("Optimizing...")
            
            # Run optimization in a separate thread
            QTimer.singleShot(100, self._run_optimization)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Parameter optimization failed:\n{str(e)}")
            self.optimize_btn.setEnabled(True)
            self.optimize_btn.setText("Optimize Parameters")
            
    def _run_optimization(self):
        """Run parameter optimization."""
        try:
            best_params = optimize_mds_parameters(self.hic_df, self.resolution_spin.value())
            
            # Update UI with best parameters
            if 'alpha' in best_params:
                self.alpha_spin.setValue(best_params['alpha'])
            if 'alpha2' in best_params:
                self.alpha2_spin.setValue(best_params['alpha2'])
            if 'weight' in best_params:
                self.weight_spin.setValue(best_params['weight'])
            if 'res_ratio' in best_params:
                self.res_ratio_spin.setValue(best_params['res_ratio'])
            if 'domain_smoothing' in best_params:
                self.domain_smooth_spin.setValue(best_params['domain_smoothing'])
            if 'min_size_fraction' in best_params:
                self.min_size_spin.setValue(best_params['min_size_fraction'])
                
            # Display optimization results
            results_text = "Parameter optimization complete!\n"
            results_text += f"Optimized parameters:\n"
            for param, value in best_params.items():
                results_text += f"  {param}: {value}\n"
            results_text += "\nParameters have been automatically updated in the interface."
            
            self.results_text.setText(results_text)
            
        except Exception as e:
            self.results_text.append(f"Optimization failed: {str(e)}")
        finally:
            self.optimize_btn.setEnabled(True)
            self.optimize_btn.setText("Optimize Parameters")
            
    def run_mds(self):
        """Run MDS structure inference."""
        if self.hic_df is None:
            return
            
        try:
            # Prepare miniMDS parameters
            mds_params = {
                'alpha': self.alpha_spin.value(),
                'alpha2': self.alpha2_spin.value(),
                'weight': self.weight_spin.value(),
                'num_threads': 1,  # Use single thread for stability
                'classical': False,
                'res_ratio': self.res_ratio_spin.value(),
                'domain_smoothing': self.domain_smooth_spin.value(),
                'min_size_fraction': self.min_size_spin.value(),
                'max_memory': 32000000
            }
            
            use_partitioned = self.partitioned_check.isChecked()
            
            # Disable UI and enable cancel
            self.run_btn.setEnabled(False)
            self.run_btn.setText("Running...")
            self.cancel_btn.setEnabled(True)
            self.status_label.setVisible(True)
            self.status_label.setText("Initializing MDS computation...")
            
            # Start worker thread
            self.worker = MDSWorker(
                self.hic_df, 
                self.resolution_spin.value(),
                mds_params,
                use_partitioned
            )
            self.worker.status.connect(self.status_label.setText)
            self.worker.finished.connect(self.on_mds_finished)
            self.worker.error.connect(self.on_mds_error)
            self.worker.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"MDS computation failed:\n{str(e)}")
            self.reset_ui()
            
    def on_mds_finished(self, particles_df, metadata):
        """Handle MDS completion."""
        self.particles_df = particles_df
        self.metadata = metadata
        
        # Update results display
        results_text = f"MDS completed successfully!\n"
        results_text += f"Points: {metadata.get('n_points', 'N/A')}\n"
        results_text += f"Method: {metadata.get('method', 'N/A')}\n"
        stress = metadata.get('stress', 'N/A')
        if isinstance(stress, (int, float)):
            results_text += f"Stress: {stress:.6f}\n"
        else:
            results_text += f"Stress: {stress}\n"
        results_text += f"Iterations: {metadata.get('n_iter', 'N/A')}\n"
        results_text += f"Resolution: {metadata.get('resolution', 'N/A'):,} bp"
        
        self.results_text.setText(results_text)
        
        # Enable add to visualization button
        self.add_viz_btn.setEnabled(True)
        
        # Reset UI
        self.reset_ui()
        
    
    def on_mds_error(self, error_msg):
        """Handle MDS error."""
        QMessageBox.critical(self, "MDS Error", f"MDS computation failed:\n{error_msg}")
        self.reset_ui()
        
    def cancel_mds(self):
        """Cancel MDS computation."""
        if self.worker is not None and self.worker.isRunning():
            # Request interruption (safer than terminate)
            self.worker.requestInterruption()
            # Don't wait here - let the thread finish naturally
            # The worker will handle cleanup in its run method
            
        self.reset_ui()
        self.results_text.append("MDS computation cancelled by user.")
        
    def reset_ui(self):
        """Reset UI to normal state."""
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run MDS")
        self.cancel_btn.setEnabled(False)
        self.status_label.setVisible(False)
        
    def add_to_visualization(self):
        """Add MDS results to visualization."""
        if self.particles_df is None:
            return
            
        try:
            # Generate chromosome colormap
            chr_colormap = get_chromosome_colormap(self.particles_df)
            
            # Add to main window
            layer_name = f"MDS_Structure_{self.metadata.get('resolution', 100000)}bp"
            layer = self.main_window.canvas.control_panel.add_chromatin_layer(
                self.particles_df, chr_colormap, name=layer_name
            )
            
            # Switch to the canvas control panel (visualization interface)
            if hasattr(self.main_window, 'control_stack') and hasattr(self.main_window, 'canvas'):
                # Switch to the current canvas control panel instead of the layer panel
                self.main_window.control_stack.setCurrentWidget(self.main_window.canvas.control_panel)
                
                # Select the newly added layer so user can immediately adjust its properties
                if hasattr(layer, 'list_item'):
                    layer.list_item.setSelected(True)
                    # Trigger the selection change to show layer properties
                    self.main_window.canvas.control_panel.layer_control.list.setCurrentItem(layer.list_item)
            
            self.results_text.append(f"Added to visualization as layer: {layer_name}")
            self.results_text.append("Switched to visualization interface. You can now adjust layer properties.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add to visualization:\n{str(e)}")
