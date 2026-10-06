"""``python -m uchrom.io particles_to_pdb IN.csv OUT.pdb [--split_by_chrom]``: a structure as PDB (PyMOL / VMD)."""

import fire

from ._io import particles_to_pdb

if __name__ == "__main__":
    fire.Fire({"particles_to_pdb": particles_to_pdb})
