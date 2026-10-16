# Installation

U-Chrom needs Python ≥ 3.11.  The packages are not on PyPI yet; install them from the repository:

```bash
git clone https://github.com/u-science-lab/U-Chrom.git
cd U-Chrom
pip install -e "packages/chromdata[remote]" -e packages/uchrom   # the data model (+ reading stores over HTTP) + the analysis library
pip install -e packages/uchrom-browser                           # + the web browser
pip install ./packages/uchrom-recon                               # + the native reconstruction engine (needs Rust)
```

With [uv](https://docs.astral.sh/uv/), `uv pip install -e "packages/uchrom[web,recon]"` resolves the
sibling packages from their folders by itself.

## The packages

| Package (import) | Folder | What it is | Needs |
|------------------|--------|------------|-------|
| `chromdata` | `packages/chromdata` | the data model and the `.chromdata.zarr` store | numpy, pandas, zarr, pyarrow |
| `u-chrom` (`uchrom`) | `packages/uchrom` | the analysis library | chromdata, PyTorch, scipy, scikit-learn, cooler, ... |
| `uchrom-browser` (`uchrom_browser`) | `packages/uchrom-browser` | the web browser | chromdata, FastAPI, uvicorn |
| `uchrom-recon` (`uchrom_recon`) | `packages/uchrom-recon` | native engine: NucDynamics, EMber, IGM (Rust; CPU and GPU) | numpy (Rust to build) |

`chromdata` alone reads and writes stores (local or over HTTP) without the analysis library; the web
browser needs only `chromdata`.

## Optional dependencies

| Extra | Installs | Needed for |
|-------|----------|------------|
| `u-chrom[web]` | uchrom-browser | the web browser |
| `u-chrom[recon]` | uchrom-recon | NucDynamics, EMber, IGM (`uchrom.recon.sc`, `uchrom.recon.bulk.deconv`) |
| `u-chrom[hic]` | hic-straw | reading `.hic` files |
| `u-chrom[umap]` | umap-learn | UMAP in `uchrom.emb.embed_cells` (PCA / t-SNE need only scikit-learn) |
| `u-chrom[emb]` / `[emb-full]` | FastHigashi (from GitHub; needs NumPy < 2) / Higashi | `uchrom.emb.higashi` |
| `u-chrom[plot3d]` | PyVista | `uchrom.pl.plot_structure_3d` |
| `chromdata[contacts]` | cooler, h5py | linked / embedded contact maps |
| `chromdata[anndata]`, `[multiome]` | anndata, mudata | linked AnnData / MuData (`u-chrom[anndata]`, `[multiome]` too) |
| `chromdata[remote]` | fsspec, aiohttp, s3fs | stores over HTTP / S3 |
| `chromdata[spatial]`, `[spatialdata]` | shapely, geopandas, spatialdata | cell outlines as geometries, SpatialData links |
| `chromdata[im]` | astropy | PyHiM ECSV traces (`ChromData.from_pyhim_trace`) |
| `chromdata[all]` | all of chromdata's extras | |

## GPU acceleration

The structure callers, the distance features and MDS run on PyTorch (`device="auto"` picks CUDA
(float64), Apple MPS (float32) or the CPU).  The native engine runs NucDynamics, EMber and IGM on
all CPU cores, or on the GPU through wgpu (Metal on macOS, Vulkan on Linux); `device="auto"` uses the
GPU when there is one.  Everything works on the CPU.

## Check the installation

```python
import uchrom, chromdata
print(uchrom.__version__, chromdata.__version__)
from uchrom.recon.sc.nucdyn import native_available, engine_info
print(native_available() and engine_info())
```

```bash
python -m uchrom_browser --help
```

To work on U-Chrom itself (tests, docs, the frontend), see [development](../reference/development).
