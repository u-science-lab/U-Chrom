"""Sphinx configuration for U-Chrom docs."""

from __future__ import annotations

import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------
# Project path
# ---------------------------------------------------------------------
# Allow ``import uchrom`` when running Sphinx locally without a pip install.
sys.path.insert(0, os.path.abspath("../.."))
sys.path.insert(0, os.path.abspath("../../discovery"))  # uchrom_discovery

import uchrom  # noqa: E402

# ---------------------------------------------------------------------
# Project information
# ---------------------------------------------------------------------
project = "U-Chrom"
author = "Weize Xu"
copyright = f"{datetime.now():%Y}, {author}"
version = release = uchrom.__version__

# ---------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
    "myst_nb",  # superset of myst_parser, also renders .ipynb (no pandoc)
    "sphinx_copybutton",
]

autosummary_generate = True
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_mock_imports = [
    "torch",
    "taichi",
    "pyvista",
    "pyvistaqt",
    "PyQt5",
    "vtk",
    "vtkmodules",
    "fire",
    "cooler",
    "h5py",
    "hicstraw",
    "qdarkgraystyle",
    "scooby",
    "matplotlib",
    "matplotlib.cm",
    "matplotlib.colors",
    "matplotlib.pyplot",
    "scipy",
    "scipy.interpolate",
    "scipy.optimize",
    "scipy.signal",
    "scipy.sparse",
    "scipy.sparse.csgraph",
    "scipy.spatial",
    "scipy.spatial.distance",
    "scipy.stats",
    "sklearn",
    "sklearn.cluster",
    "sklearn.metrics",
    "sklearn.metrics.pairwise",
    "sklearn.neighbors",
    "networkx",
    "networkx.algorithms",
    "networkx.algorithms.community",
    "astropy",
    "astropy.table",
]

napoleon_numpy_docstring = True
napoleon_google_docstring = True

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "substitution",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "pandas": ("https://pandas.pydata.org/docs", None),
    "matplotlib": ("https://matplotlib.org/stable", None),
    "anndata": ("https://anndata.readthedocs.io/en/stable", None),
}

# Execute notebooks during the Sphinx build and cache results so
# re-builds are fast.  The cache lives in docs/source/.jupyter_cache/.
nb_execution_mode = "cache"
nb_execution_timeout = 600
nb_execution_raise_on_error = True

# ---------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "**/.ipynb_checkpoints"]

html_theme = "furo"
html_static_path = ["_static"]
html_extra_path = ["_extra"]
html_title = f"{project} {version}"
html_theme_options = {
    "sidebar_hide_name": False,
    "light_logo": "logo.svg",
    "dark_logo": "logo.svg",
    "source_repository": "https://github.com/Nanguage/U-Chrom",
    "source_branch": "main",
    "source_directory": "docs/source/",
}

# myst-nb auto-registers .md and .ipynb; keep .rst too.
source_suffix = [".rst", ".md", ".ipynb"]

master_doc = "index"
