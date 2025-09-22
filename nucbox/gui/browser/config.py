"""
Configuration for NucBrowser rendering.
This project now uses a single backend: PyVista.
"""

# PyVista-only settings
PYVISTA_SETTINGS = {
    'auto_update': True,
}

# Performance settings for gradient tubes
TUBE_GRADIENT_SEGMENTS = 50

def get_backend():
    """Return the only supported backend name."""
    return 'pyvista'

def set_backend(backend):
    """Kept for API compatibility; always returns True for 'pyvista'."""
    return backend.lower() == 'pyvista'