# Installation

## From PyPI

```bash
pip install u-chrom
```

## From source

```bash
git clone https://github.com/Nanguage/U-Chrom.git
cd U-Chrom
pip install -e .
```

## Optional dependencies

The browser module (`uchrom.browser`) and bulk MDS reconstruction pull in
heavier dependencies that you only need for certain workflows:

```bash
# Browser — PyVista + PyQt5
pip install "pyvista>=0.43,<0.45" "pyvistaqt>=0.11,<0.12" PyQt5 qdarkgraystyle

# Bulk MDS reconstruction — PyTorch
pip install "torch>=2.0"
```

## GPU acceleration

The tensor-heavy steps (axis-wise variance cube, F-test, MDS) run
through PyTorch on the best available device:

| Device | Precision | Typical use |
|--------|-----------|-------------|
| `cuda` | float64 | NVIDIA desktop / server |
| `mps`  | float32 | Apple Silicon |
| `cpu`  | float64 | fallback |

Pass `device="auto"` (the default) to pick automatically, or an explicit
device name to pin.  GPU support is optional — everything works on CPU.

## Verifying the install

```python
import uchrom
print(uchrom.__version__)

from uchrom import ChromData
```

If that works, the core package is usable.  If you installed the browser
extras:

```bash
python -m uchrom.browser --help
```
