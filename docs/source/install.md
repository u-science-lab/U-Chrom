# Installation

## From PyPI

```bash
pip install u-chrom
```

## From source

```bash
git clone https://github.com/Nanguage/U-Chrom.git
cd U-Chrom
pip install -e packages/chromdata -e .                # or: uv pip install -e .
```

The repository is a monorepo: the data model (`chromdata`), the web browser
(`uchrom-browser`), auto-discovery (`uchrom-discovery`) and the native engine
(`uchrom-recon`) are packages of their own under `packages/`.  pip installs
them from their folders (`pip install -e packages/uchrom-browser -e ".[web]"`);
`uv pip install` finds them through `[tool.uv.sources]`.  `chromdata` alone
(`pip install -e packages/chromdata`) reads and writes `.chromdata.zarr`
stores without the analysis library.

## Optional dependencies

Some workflows need heavier dependencies that are published as extras:

| Extra | Installs | Needed for |
|-------|----------|------------|
| `browser` | PyVista, pyvistaqt, VTK, PyQt5, qdarkgraystyle | `python -m uchrom.browser` |
| `web` | uchrom-browser (FastAPI, uvicorn) | `python -m uchrom.browser --web` (browser in a web page) |
| `hic` | hic-straw | reading `.hic` files |
| `anndata` | anndata | `ChromData.link_anndata` / `to_anndata`, seqFISH RNA |
| `multiome` | mudata | `ChromData.load_linked_mudata` |
| `umap` | umap-learn | UMAP in `uchrom.emb.embed_cells` (PCA / t-SNE need only scikit-learn) |
| `im` | astropy | `ChromData.from_pyhim_trace` |
| `snapfish` | scikit-image | SnapFISH-IMPUTE (`uchrom.im.impute`) |
| `emb` / `emb-full` | FastHigashi / Higashi | `uchrom.emb.higashi` |

```bash
pip install "u-chrom[browser]"
pip install "u-chrom[browser,hic,anndata]"   # several at once
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
