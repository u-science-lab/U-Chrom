uchrom.im
=========

Imaging-side processing of DNA-FISH data: detections into traces, missing loci, duplicate spots.

.. automodule:: uchrom.im
   :members:

Spot-to-fibre tracing
---------------------

The jie spatial genome aligner, an independent re-implementation of Jia et al. 2023, *Nature
Biotechnology* 41:1004 (doi:10.1038/s41587-022-01568-9).

.. automodule:: uchrom.im.trace
   :members: align_spots, SpotAlignerParams, score_alignment

Gaussian-chain polymer primitives
`````````````````````````````````

.. automodule:: uchrom.im.trace._polymer
   :members: expected_distance, expected_distance_sq, bond_log_probability, mahalanobis_cost, fit_scale_factor, fit_scale_factor_from_matrix

Imputation
----------

.. automodule:: uchrom.im.impute
   :members: impute_coordinates, impute_linear, impute_cubic, impute_snapfish, evaluate_imputation
