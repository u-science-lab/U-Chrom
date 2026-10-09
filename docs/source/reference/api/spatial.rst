uchrom.spatial
==============

Cells in tissue: neighbour graphs from cell positions (one frame per section / field of view), spatial
autocorrelation of per-cell values (Moran's I, Geary's C) and tests of spatial variation (SPARK-X) — for 3-D
genome features of spatial Hi-C spots or traced cells — with covariates such as the cells' transcriptomes, to ask
what varies in space beyond the cell types.

.. automodule:: uchrom.spatial.graph
   :members: spatial_neighbors, SpatialGraph, cell_positions_table

.. automodule:: uchrom.spatial.autocorr
   :members: spatial_autocorr, cell_values, bh_adjust

.. automodule:: uchrom.spatial.sparkx
   :members: sparkx, coordinate_kernels, acat, by_adjust, KERNELS

.. automodule:: uchrom.spatial.variable
   :members: spatially_variable, covariate_matrix
