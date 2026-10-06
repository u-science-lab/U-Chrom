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

## Cloudflare Pages CI

`.github/workflows/docs-cloudflare-pages.yml` builds the Sphinx site on
pull requests to `main`, and builds plus deploys on pushes to `main` or
manual `workflow_dispatch` runs.

The workflow publishes `docs/build/html` to the Cloudflare Pages project
`u-chrom-docs`.  Configure these GitHub repository secrets before using
the deploy job:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

Use a scoped Cloudflare API token that can edit/deploy the `u-chrom-docs`
Pages project.

The auto-discovery tutorial links to exported exploration notebooks.  CI
does not regenerate those agent outputs; the published snapshot lives in
`docs/source/_extra/_auto_discovery_notebooks/` and is copied to
`docs/build/html/_auto_discovery_notebooks/` by `html_extra_path`.

## Layout

```
docs/
├── Makefile
├── README.md
├── requirements.txt      # Sphinx-only deps installed by CI
└── source/
    ├── conf.py           # Sphinx config
    ├── index.md          # landing page
    ├── install.md
    ├── concepts.md
    ├── changelog.md
    ├── license.md
    ├── _static/
    │   └── logo.svg      # a copy of packages/uchrom/uchrom/browser/uc.svg
    ├── _extra/           # static publish-only files copied to HTML root
    ├── api/              # .rst files, one per top-level module
    ├── guide/            # long-form user guide chapters
    └── tutorials/        # symlinks to ../../../tutorials/*.ipynb
```

The tutorial notebooks live under the repo's top-level `tutorials/`
directory; `docs/source/tutorials/` holds symlinks so Sphinx picks them
up via `myst-nb` without duplicating sources.
