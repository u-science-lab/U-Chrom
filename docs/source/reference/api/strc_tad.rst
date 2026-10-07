uchrom.strc.tad
===============

.. automodule:: uchrom.strc.tad
   :members:

FISHnet (per-allele, graph-theory)
----------------------------------

.. autoclass:: uchrom.strc.tad.fishnet.FISHnetParams
   :members:

.. autofunction:: uchrom.strc.tad.fishnet.call_domains_fishnet

.. autofunction:: uchrom.strc.tad.fishnet.call_domains_fishnet_trace

F-test caller
-------------

.. autoclass:: uchrom.strc.tad.arc_pval.TADCallerParams
   :members:

.. autofunction:: uchrom.strc.tad.arc_pval.call_tads_by_pval

Insulation score (Hi-C maps)
----------------------------

Boundaries and domains of a linked contact map by the diamond insulation score (Crane et al. 2015, in
cooltools' formulation).

.. autoclass:: uchrom.strc.tad.insulation.InsulationParams
   :members:

.. autofunction:: uchrom.strc.tad.insulation.call_tads_insulation

.. autofunction:: uchrom.strc.tad.insulation.insulation_score

Low-level kernels:

.. autofunction:: uchrom.strc.tad.insulation.diamond_sums

.. autofunction:: uchrom.strc.tad.insulation.n_valid_pixels

.. autofunction:: uchrom.strc.tad.insulation.full_diamond

.. autofunction:: uchrom.strc.tad.insulation.boundary_strength

.. autofunction:: uchrom.strc.tad.insulation.threshold_li

.. autofunction:: uchrom.strc.tad.insulation.threshold_otsu

Directionality index
--------------------

.. autoclass:: uchrom.strc.tad.di_caller.DICallerParams
   :members:

.. autofunction:: uchrom.strc.tad.di_caller.call_tads_di

Low-level kernels:

.. automodule:: uchrom.strc.tad.di
   :members:

.. automodule:: uchrom.strc.tad.utils
   :members:

Comparing boundaries
--------------------

.. autofunction:: uchrom.strc.tad.compare.tad_boundaries

.. autofunction:: uchrom.strc.tad.compare.compare_boundaries

.. autofunction:: uchrom.strc.tad.compare.boundary_frequency
