uchrom.recon.fish
=================

Joint Hi-C + FISH 3-D chromosome reconstruction.

.. automodule:: uchrom.recon.fish

GEM-FISH — three-stage joint optimiser
--------------------------------------

Independent PyTorch reimplementation of Abbas et al. 2019
(*Nature Communications* 10:2049, doi:10.1038/s41467-019-10005-6).


Internal components
-------------------

Loss primitives
```````````````

.. automodule:: uchrom.recon.fish._losses
   :members: hic_kl_loss, polymer_energy, fish_distance_loss, rg_squared, rg_loss

Hi-C preprocessing
``````````````````

.. automodule:: uchrom.recon.fish._hic
   :members:

Stage-1 TAD-level optimisation
``````````````````````````````

.. automodule:: uchrom.recon.fish._tad_level
   :members: Stage1Params, reconstruct_tad_level

Stage-2 intra-TAD optimisation
``````````````````````````````

.. automodule:: uchrom.recon.fish._intra_tad
   :members: Stage2Params, reconstruct_intra_tad

Stage-3 assembly
````````````````

.. automodule:: uchrom.recon.fish._assembly
   :members: AssemblyParams, assemble, gap_distance_from_contacts
