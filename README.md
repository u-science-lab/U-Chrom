# U-Chrom

Chromatin structure analysis toolkit.

## Install

```bash
$ pip install u-chrom
```

For enhanced rendering performance (recommended):
```bash
$ pip install pyvista==0.43.0 pyvistaqt==0.11.0
```

Install from source:

```bash
$ git clone https://github.com/Nanguage/U-Chrom.git
$ cd U-Chrom
$ pip install -e .
```

## Usage

Reconstruct genome using Nuc Dynamics algorithm:

```bash
$ python -m uchrom.recon.sc.nucdyn --arch=cuda ./cell1.pairs.gz ./out1.csv --use-grid=True --scale=0.01
```

Visualize the reconstructed genome:

```bash
$ python -m uchrom.browser ./out1.csv
```

### Rendering Features
- **PyVista Backend** (default): Hardware-accelerated rendering with 5-6x performance improvement
- **Rendering Modes**: Tube (3D), Line, Points

![demo](./demo1.png)

Convert the particles CSV file to PDB file(for visualization in PyMol or VMD):

```bash
$ python -m uchrom.io particles_to_pdb ./out1.csv ./out1.pdb --split-by-chrom=True
```
