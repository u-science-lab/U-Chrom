uchrom.fea
==========

Geometric / statistical features over chromatin traces.

.. automodule:: uchrom.fea
   :members:

Distance-based aggregates
-------------------------

.. automodule:: uchrom.fea.distance
   :members:

Contact maps
------------

Maps linked to a ``ChromData`` as matrices, rebinned, observed / expected.

.. automodule:: uchrom.fea.maps
   :members:

Banded reads of large maps
--------------------------

One chromosome's pixels near the diagonal as a sparse band, and the expected contact per separation: what the
Hi-C structure callers share.

.. automodule:: uchrom.fea.band
   :members:

Pseudo-bulk maps
----------------

Per-cell maps summed per group of cells into ICE-balanced maps linked to the cells.

.. automodule:: uchrom.fea.pseudobulk_maps
   :members:

Imputing single-cell maps
-------------------------

Random walk with restart on each cell's contact graph (scHiCluster, SnapHiC), whole chromosomes or sliding
windows, and SnapHiC's per-diagonal z-scores; native kernels in ``uchrom-maps``.

.. automodule:: uchrom.fea.impute_rwr
   :members: ImputeParams, impute_maps, rwr_band, zscore_band, auto_window, plan_windows, convolve_maps, rwr_dense

Pileups (APA)
-------------

A linked map aggregated around known loops or boundaries.

.. automodule:: uchrom.fea.pileup_maps
   :members:

Comparing structures
--------------------

Model ensembles, models against imaging, models against their contacts.

.. automodule:: uchrom.fea.compare
   :members:

Positions in the nucleus
------------------------

.. automodule:: uchrom.fea.positions
   :members:

Axis-wise preprocessing
-----------------------

.. automodule:: uchrom.fea.arc
   :members: axis_variance_cube, filter_normalize, axis_weight

Interval projection
-------------------

.. automodule:: uchrom.fea.project
   :members:

Sequence features
-----------------

.. automodule:: uchrom.fea.sequence
   :members:

Annotation features
-------------------

.. automodule:: uchrom.fea.annotation
   :members:

Peak features
-------------

.. automodule:: uchrom.fea.peaks
   :members:

Feature registry
----------------

.. automodule:: uchrom.fea.registry
   :members:
