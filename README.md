# NucBox

Ultra fast chromosome 3D reconstraction.

## Install

```bash
$ pip install nucbox
```

For enhanced rendering performance (recommended):
```bash
$ pip install pyvista==0.43.0 pyvistaqt==0.11.0
```

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

# Use original VisPy renderer (if needed)
$ NUCBROWSER_BACKEND=vispy python -m nucbox.gui.browser ./out1.csv
```

### Rendering Features
- **PyVista Backend** (default): Hardware-accelerated rendering with 5-6x performance improvement
- **VisPy Backend**: Original lightweight renderer
- **Rendering Modes**: Tube (3D), Line, Points
- **Runtime Switching**: Change renderer via menu without restarting

![demo](./demo1.png)

Convert the particles CSV file to PDB file(for visualization in PyMol or VMD):

```bash
$ python -m nucbox.utils.io particles_to_pdb ./out1.csv ./out1.pdb --split-by-chrom=True
```
