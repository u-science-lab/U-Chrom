uchrom.datasets
===============

Every dataset U-Chrom knows, as a ``ChromData`` (``load``: an atlas store over HTTP, or a dataset built
once from its original files by a registered loader) or as its original files (``fetch``).  See
:doc:`../../start/datasets`; where each dataset comes from: :doc:`../data_sources`.

.. automodule:: uchrom.datasets
   :members: load, fetch, atlas, list_datasets, list_atlas, files, path, data_dir
