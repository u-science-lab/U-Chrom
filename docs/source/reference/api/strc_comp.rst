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

Single cells: scA/B
-------------------

Each cell's compartment value per bin: the mean CpG frequency of the bin's contact partners in that cell
(Tan et al. 2021, Dip-C; scHiCluster's compartment score as an option).

.. autoclass:: uchrom.strc.comp.single_cell.ScABParams
   :members:

.. autofunction:: uchrom.strc.comp.single_cell.single_cell_compartments

.. autofunction:: uchrom.strc.comp.single_cell.scab_sums

.. autofunction:: uchrom.strc.comp.single_cell.normalize_scab

.. autofunction:: uchrom.strc.comp.eig.saddle_strength
