uchrom.im
=========

Image-pipeline utilities for DNA-FISH data.

.. automodule:: uchrom.im
   :members:

Spot-to-fiber tracing
---------------------

.. automodule:: uchrom.im.trace

jie — spatial genome aligner
````````````````````````````

Independent reimplementation of Jia & Ren 2022 (*Nature Biotechnology*
22, doi:10.1038/s41587-022-01568-9).


Gaussian-chain polymer primitives
`````````````````````````````````

.. automodule:: uchrom.im.trace._polymer
   :members: expected_distance, expected_distance_sq, bond_log_probability, mahalanobis_cost, fit_scale_factor, fit_scale_factor_from_matrix
