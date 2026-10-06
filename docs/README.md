# U-Chrom documentation

Sphinx + MyST sources for the U-Chrom docs.

## Build locally

```bash
pip install -r docs/requirements.txt          # Sphinx; conf.py imports the packages from packages/
sphinx-build -b html docs/source docs/build/html
open docs/build/html/index.html
```

The tutorials are rendered as committed (executed); the build does not run them.

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

## Deploying by hand

GitHub Actions are not available at the moment; deploy the built site with Wrangler (logged in with
`npx wrangler login`):

```bash
npx wrangler pages deploy docs/build/html --project-name u-chrom-docs --branch main
```

## Layout

```
docs/
├── Makefile
├── README.md
├── requirements.txt      # Sphinx-only deps installed by CI
└── source/
    ├── conf.py           # Sphinx config
    ├── index.md          # landing page: the chapters
    ├── start/            # install, quick start, concepts, datasets
    ├── data/ io/ imaging/ recon/ structures/ features/ cells/ viz/ discovery/
    │                     # one folder per chapter: index.md + method pages
    ├── reference/        # API (api/*.rst), format spec, data sources, development, changelog, licence
    ├── tutorials/        # symlinks to ../../../tutorials/*.ipynb
    ├── _static/          # the logo
    └── _extra/           # static publish-only files copied to the HTML root
```

The tutorial notebooks live under the repository's top-level `tutorials/`; `docs/source/tutorials/`
holds symlinks so Sphinx picks them up via `myst-nb` without duplicating sources.
