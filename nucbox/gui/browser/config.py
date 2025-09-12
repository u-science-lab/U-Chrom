"""
Configuration module for NucBrowser rendering backend.
Allows switching between VisPy and PyVista backends.
"""

import os


# Default backend selection
# Can be overridden by environment variable NUCBROWSER_BACKEND
DEFAULT_BACKEND = os.environ.get('NUCBROWSER_BACKEND', 'pyvista').lower()

# Validate backend choice
if DEFAULT_BACKEND not in ['vispy', 'pyvista']:
    DEFAULT_BACKEND = 'pyvista'

# Performance settings for PyVista
PYVISTA_SETTINGS = {
    'auto_update': False,  # Manual control over rendering
    'multi_samples': 4,    # Anti-aliasing samples
    'line_smoothing': True,
    'point_smoothing': True,
    'polygon_smoothing': True,
}

# Performance settings for gradient tubes
TUBE_GRADIENT_SEGMENTS = 50  # Maximum segments for gradient tubes

def get_backend():
    """Get the currently configured backend."""
    return DEFAULT_BACKEND

def set_backend(backend):
    """Set the default backend for new canvas instances."""
    global DEFAULT_BACKEND
    if backend.lower() in ['vispy', 'pyvista']:
        DEFAULT_BACKEND = backend.lower()
        return True
    return False