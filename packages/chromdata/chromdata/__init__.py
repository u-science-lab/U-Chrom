"""ChromData: one data model for single-cell Hi-C, spatial Hi-C and chromatin tracing.

The in-memory object (:class:`ChromData`: cells › traces › spots on a shared locus axis, contact maps linked per
cell) and its store, ``.chromdata.zarr`` (Zarr v3 + Parquet; ``.cdz`` = the same tree in one zip file), read in
parts from disk or over HTTP.  The format specification is ``spec.md`` next to this package.

    from chromdata import ChromData
    cd = ChromData.read("x.chromdata.zarr", backed=True)

The analysis library (reconstruction, structures, features, embeddings) is ``uchrom`` and the web browser
``uchrom-browser``; both build on this package.
"""

from ._version import __version__
from .settings import settings
from .cdata import ChromData, read_fofct_table
from .clusters import ClusterTable
from .results import ResultRecord, ResultsStore
from .project import UChromProject

__all__ = ["ChromData", "ClusterTable", "ResultRecord", "ResultsStore", "UChromProject", "read_fofct_table", "settings", "__version__"]
