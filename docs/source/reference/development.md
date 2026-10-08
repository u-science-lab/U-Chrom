# Development

## The repository

```
packages/
├── chromdata/          the data model (pyproject, README, spec.md, chromdata/, tests/)
├── uchrom/             the analysis library u-chrom (uchrom/, tests/)
├── uchrom-browser/     the web browser (uchrom_browser/ with frontend/ and the built static/, tests/)
├── uchrom-recon/       the native reconstruction engine (Rust: src/, tests/; Python: python/uchrom_recon)
└── uchrom-discovery/   auto-discovery (uchrom_discovery/, tests/)
apps/
├── atlas/              the atlas page, thumbnails, publishing; recipes/ builds every dataset from its sources
└── hosted-browser/     the public web browser (Cloudflare Worker + container)
benchmarks/             the measurements behind the paper's figures (+ benchmarks/<name>/tests)
tutorials/              the tutorial notebooks (executed; docs/source/tutorials links to them)
docs/                   this documentation (Sphinx + MyST)
```

Dependencies point one way: `chromdata` ← `uchrom-browser`; `chromdata` ← `uchrom` ←
`uchrom-discovery`.  `chromdata` and `uchrom-browser` never import `uchrom` (their
`tests/test_standalone.py` check it).  New data-model code goes into `chromdata`, new analyses into
`uchrom`.

## Install for development

```bash
uv pip install -e "packages/uchrom[web,recon]" -e packages/uchrom-discovery   # uv finds the siblings itself
# or with pip:
pip install -e "packages/chromdata[all]" -e "packages/uchrom-browser[test]" -e packages/uchrom \
            -e packages/uchrom-discovery
pip install ./packages/uchrom-recon          # Rust toolchain; or: cd packages/uchrom-recon && maturin develop --release
```

## Tests

Each package has its own `tests` package; run each from its folder:

```bash
(cd packages/uchrom && pytest tests)
(cd packages/chromdata && pytest tests)
(cd packages/uchrom-browser && pytest tests)
(cd packages/uchrom-discovery && pytest tests)
(cd apps/atlas && pytest tests)
(cd packages/uchrom-recon && cargo test --release)               # add --features gpu for the GPU backend
pytest benchmarks/fig2/tests benchmarks/bulk/tests                # benchmark helpers
(cd packages/uchrom-browser/uchrom_browser/frontend && npm test)  # the frontend (vitest)
```

A test goes to the package whose code it tests.  Shared fixtures (an object with every attribute, a
store with linked / embedded contact maps, a folder atlas, an HTTP server with range requests, store
comparisons) are in `chromdata.testing`.

## The web browser's frontend

The React / Three.js app is `packages/uchrom-browser/uchrom_browser/frontend`; it is built into
`uchrom_browser/static`, which is committed (users need no Node):

```bash
cd packages/uchrom-browser/uchrom_browser/frontend
npm install && npm test && npm run build
```

Keep `uchrom_browser/API.md` in sync with `server.py` / `data.py`.

## Tutorials and docs

Tutorials are Jupyter notebooks in `tutorials/`, committed **executed**: they run end to end on real
data (from the atlas or fetched with `uchrom.datasets`; see [datasets](../datasets/index)), and the docs build only
renders them.  After changing a tutorial, re-run it from the repository root:

```bash
jupyter nbconvert --to notebook --execute --inplace tutorials/<name>.ipynb
```

A new tutorial gets a link in `docs/source/tutorials/` and an entry in its chapter's `index.md`.
Build the docs:

```bash
pip install -r docs/requirements.txt
sphinx-build -b html docs/source docs/build/html
```

## Data and validation

Every dataset a tutorial, test or benchmark uses is registered in `uchrom.datasets`
(`packages/uchrom/uchrom/datasets/_sources.py`: source URL, md5) or built by a recipe in
`apps/atlas/recipes/`, and documented in `apps/atlas/recipes/README.md` (size, source, licence,
users); data are never committed, except the small fixtures of the unit tests
(`packages/*/tests/fixtures/`).  A new method is validated on the real datasets its paper used, and the
real-data numbers go into the commit message.
