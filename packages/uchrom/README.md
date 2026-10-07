# u-chrom

The U-Chrom analysis library (`import uchrom`): reading chromatin data (`.pairs`, `.cool`,
`.hic`, `.3dg`, FOF-CT, seqFISH, pyHiM), 3-D reconstruction from single-cell and bulk Hi-C
and from imaging, structure calling (compartments, TADs, loops), per-locus features,
single-cell embeddings, plots and the desktop browser.

It works on [`chromdata`](../chromdata) objects (`ChromData`, the `.chromdata.zarr` store);
the native reconstruction engine is [`uchrom-recon`](../uchrom-recon) (extra `recon`) and
the web browser [`uchrom-browser`](../uchrom-browser) (extra `web`).

```bash
pip install -e packages/chromdata -e packages/uchrom          # from the repository root
uv pip install -e "packages/uchrom[web]"                      # uv finds the sibling packages itself
```

```python
import uchrom as uc
cd = uc.ChromData.read("data.chromdata.zarr")
```

Tests: `cd packages/uchrom && pytest tests`.  Documentation: the repository's
[README](../../README.md) and `docs/`.
