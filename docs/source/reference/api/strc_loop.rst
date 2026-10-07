uchrom.strc.loop
================

.. automodule:: uchrom.strc.loop
   :members:

.. autoclass:: uchrom.strc.loop.axiswise_f.LoopCallerParams
   :members:

.. autofunction:: uchrom.strc.loop.axiswise_f.call_loops_axiswise_f

HiCCUPS (Hi-C maps)
-------------------

Loops of a linked contact map by local enrichment (Rao et al. 2014, in cooltools' formulation).

.. autoclass:: uchrom.strc.loop.hiccups.HiccupsParams
   :members:

.. autofunction:: uchrom.strc.loop.hiccups.call_loops_hiccups

.. autofunction:: uchrom.strc.loop.hiccups.merge_resolutions

.. autofunction:: uchrom.strc.loop.hiccups.hiccups_pixels

Mustache (Hi-C maps)
--------------------

Loops of a linked contact map by scale-space blob detection (Roayaei Ardakany et al. 2020).

.. autoclass:: uchrom.strc.loop.mustache.MustacheParams
   :members:

.. autofunction:: uchrom.strc.loop.mustache.call_loops_mustache

Comparing loop calls
--------------------

.. autofunction:: uchrom.strc.loop.compare.match_loops

.. autofunction:: uchrom.strc.loop.compare.score_loops
