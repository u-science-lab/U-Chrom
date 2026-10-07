uchrom.strc.comp
================

.. automodule:: uchrom.strc.comp
   :members:

.. autoclass:: uchrom.strc.comp.axes_pc.CompartmentCallerParams
   :members:

.. autofunction:: uchrom.strc.comp.axes_pc.call_compartments_axes_pc

Hi-C maps: cis eigenvector and saddle strength
----------------------------------------------

A/B compartments of a linked contact map (bulk or pseudo-bulk) by the cis eigenvector of observed /
expected, and their strength by saddle analysis.

.. autoclass:: uchrom.strc.comp.eig.EigCompartmentParams
   :members:

.. autofunction:: uchrom.strc.comp.eig.call_compartments_eig

.. autoclass:: uchrom.strc.comp.eig.SaddleParams
   :members:

.. autofunction:: uchrom.strc.comp.eig.compartment_strength

Low-level kernels:

.. autofunction:: uchrom.strc.comp.eig.cis_eigs

.. autofunction:: uchrom.strc.comp.eig.saddle_strength
