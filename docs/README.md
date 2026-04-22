# U-Chrom documentation

Sphinx + MyST sources for the U-Chrom docs.

## Build locally

```bash
pip install -e '.[docs]'
cd docs
make html
open build/html/index.html
```

## Live reload

```bash
pip install sphinx-autobuild
cd docs
make livehtml
```

## Read the Docs

The site is built automatically from `.readthedocs.yaml` at the repo
root.  The configuration installs `.[docs]` plus `docs/requirements.txt`
and runs Sphinx over `docs/source/`.

## Layout

```
docs/
├── Makefile
├── README.md
├── requirements.txt      # Sphinx-only deps (RTD installs these)
└── source/
    ├── conf.py           # Sphinx config
    ├── index.md          # landing page
    ├── install.md
    ├── concepts.md
    ├── changelog.md
    ├── license.md
    ├── _static/
    │   └── logo.svg      # symlinked from uchrom/browser/uc.svg
    ├── api/              # .rst files, one per top-level module
    ├── guide/            # long-form user guide chapters
    └── tutorials/        # symlinks to ../../../tutorials/*.ipynb
```

The tutorial notebooks live under the repo's top-level `tutorials/`
directory; `docs/source/tutorials/` holds symlinks so Sphinx picks them
up via `nbsphinx` without duplicating sources.
