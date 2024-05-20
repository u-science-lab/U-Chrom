# NucBox

Ultra fast single cell genome 3D reconstraction.

## Install

```bash
$ pip install nucbox
```

Install from source:

```bash
$ git clone https://github.com/Nanguage/NucBox.git
$ cd NucBox
$ pip install -e .
```

## Usage

Reconstruct 3D genome structure using Nuc Dynamics algorithm:

```bash
$ python -m nucbox.simu.nucdyn --arch=cuda ./cell1.pairs.gz ./out1.csv --use-grid=True --scale=0.01
```

Parameters:

| Parameter | Description | Default |
| --- | --- | --- |
| `--arch` | Use `cuda` for GPU acceleration or `cpu` for CPU | `cpu` |
| `--genome-ranges` | Genome ranges to reconstruct | `None` |
| `--pow` | Power of the distance | `-0.33` |
| `--bb-lower` | Lower bound of the bead-bead interaction | `0.1` |
| `--bb-upper` | Upper bound of the bead-bead interaction | `1.1` |
| `--lower` | Lower bound of the distance | `0.8` |
| `--upper` | Upper bound of the distance | `1.2` |
| `--scale` | Scale of the distance | `1.0` |
| `--repulsive-lim` | Repulsive limit | `2.0` |
| `--hot` | Hot temperature | `5000.0` |
| `--cold` | Cold temperature | `10.0` |
| `--dyns` | Number of dynamics | `500` |
| `--random-seed` | Random seed | `0` |
| `--time-step` | Time step | `0.01` |
| `--size-steps` | Size steps | `[8, 4, 2, 0.4, 0.2, 0.1]` |
| `--max-radius` | Maximum radius | `10.0` |
| `--use-grid` | Use grid | `False` |
| `--grid-range-scale` | Grid range scale | `5.0` |
| `--cell-capacity` | Cell capacity | `10000` |
| `--shift-freq` | Shift frequency | `10` |
| `--min-skip` | Minimum skip | `2` |
| `--violated-threshold` | Violated threshold | `5.0` |


Visualize the reconstructed genome:

```bash
$ python -m nucbox.gui.browser ./out1.csv
```

![demo](./demo1.png)

Convert the particles CSV file to PDB file(for visualization in PyMol or VMD):

```bash
$ python -m nucbox.utils.io particles_to_pdb ./out1.csv ./out1.pdb --split-by-chrom=True
```
