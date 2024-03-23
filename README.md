# NucBox

Ultra fast chromosome 3D reconstraction.

## Install

Install from source:

```bash
$ git clone https://github.com/Nanguage/NucBox.git
$ cd NucBox
$ pip install -e .
```

## Usage

Reconstruct genome using Nuc Dynamics algorithm:

```bash
$ python -m nucbox.simu.nucdyn --arch=cuda ./cell1.pairs.gz ./out1.csv --use-grid=True --scale=0.01
```


Visualize the reconstructed genome:

```bash
$ python -m nucbox.gui.browser ./out1.csv
```

Convert the particles csv file to pdb file(for visualization in pymol or vmd):

```bash
$ python -m nucbox.utils.io particles_to_pdb ./out1.csv ./out1.pdb --split-by-chrom=True
```
