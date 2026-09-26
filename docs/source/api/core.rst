uchrom.core
===========

.. automodule:: uchrom.core
   :members:
   :undoc-members:
   :exclude-members: ChromData, ResultRecord, ResultsStore, IntervalTable, IntervalStore

ChromData
---------

.. autoclass:: uchrom.core.ChromData
   :members:
   :undoc-members:
   :show-inheritance:

UChromProject
-------------

.. autoclass:: uchrom.core.UChromProject
   :members:
   :undoc-members:
   :show-inheritance:

Results store
-------------

.. automodule:: uchrom.core.results
   :members: ResultRecord, ResultsStore

Calling convention helpers
--------------------------

.. automodule:: uchrom.core.convention
   :members:

Locus axis (bins)
-----------------

.. automodule:: uchrom.core.bins
   :members:

Interval tables
---------------

.. automodule:: uchrom.core.intervals
   :members: IntervalTable, IntervalStore, INTERVAL_KINDS

Storage: .chromdata.zarr
------------------------

.. automodule:: uchrom.core.zarrcd
   :members: write_zarr, container_kind, Container, SpotRows, sort_order

Backed mode
-----------

.. automodule:: uchrom.core.backed
   :members: BackedChromData, BackedArray, BackedFrame
