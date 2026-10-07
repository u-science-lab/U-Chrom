"""Sphinx configuration for U-Chrom docs."""

from __future__ import annotations

import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------
# Project path
# ---------------------------------------------------------------------
# Allow ``import uchrom`` when running Sphinx locally without a pip install:
# the monorepo's packages (packages/): uchrom, chromdata, uchrom_browser, uchrom_discovery
for _pkg in ("uchrom", "chromdata", "uchrom-browser", "uchrom-discovery"):
    sys.path.insert(0, os.path.abspath(f"../../packages/{_pkg}"))

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
    "pyvista",
    "vtk",
    "vtkmodules",
    "fire",
    "cooler",
    "h5py",
    "hicstraw",
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
napoleon_use_ivar = True          # "Attributes" sections as fields (dataclass members are documented by autodoc)
# numpy-style type descriptions ("ndarray, shape (n, 3)", "ChromData, in memory or backed") are parsed into
# cross-references; words that match several attributes (shape, backed, ...) are not ambiguous references
suppress_warnings = ["ref.python"]

myst_heading_anchors = 3   # links to sections: page.md#a-heading

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

# The tutorials are committed executed (with outputs, run on real data): the build does not run them.
nb_execution_mode = "off"
nb_execution_timeout = 600
nb_execution_raise_on_error = True

# ---------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "**/.ipynb_checkpoints",
                    # auto-discovery (uchrom-discovery) is left out of the docs until it settles; to bring it
                    # back, drop these three patterns, add discovery/index to index.md and
                    # html_extra_path = ["_extra"] (the exported agent notebooks)
                    "discovery/**", "tutorials/takei2025_*auto_discovery.ipynb", "reference/api/auto_discovery.rst"]

html_theme = "furo"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_extra_path = []          # ["_extra"]: the auto-discovery exports (see exclude_patterns)
# the sidebar: "U-Chrom 0.3" ("(dev)" for a development version)
_short = ".".join(release.split(".")[:2])
html_baseurl = "https://u-chrom-docs.u-science.org/"   # canonical links point at the custom domain
html_title = f"{project} {_short}" + (" (dev)" if "dev" in release else "")
html_favicon = "_static/favicon.png"
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
