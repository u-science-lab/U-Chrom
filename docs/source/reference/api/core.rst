chromdata (the data model)
==========================

The data model and its store are the ``chromdata`` package (``packages/chromdata``; formerly ``uchrom.core``,
deprecated name).

.. automodule:: chromdata
   :members:
   :undoc-members:
   :exclude-members: ChromData, ResultRecord, ResultsStore, IntervalTable, IntervalStore, UChromProject

ChromData
---------

.. autoclass:: chromdata.ChromData
   :members:
   :undoc-members:
   :show-inheritance:

UChromProject
-------------

.. autoclass:: chromdata.UChromProject
   :members:
   :undoc-members:
   :show-inheritance:

Results store
-------------

.. automodule:: chromdata.results
   :members: ResultRecord, ResultsStore

Calling convention helpers
--------------------------

.. automodule:: uchrom.convention
   :members:

Locus axis (bins)
-----------------

.. automodule:: chromdata.bins
   :members:

Interval tables
---------------

.. automodule:: chromdata.intervals
   :members: IntervalTable, IntervalStore, INTERVAL_KINDS

Storage: .chromdata.zarr
------------------------

.. automodule:: chromdata.zarrcd
   :members: write_zarr, container_kind, Container, SpotRows, sort_order

Backed mode
-----------

.. automodule:: chromdata.backed
   :members: BackedChromData, BackedArray, BackedFrame
