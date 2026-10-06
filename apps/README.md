# Deploying the atlas on Cloudflare

Two Workers in one account (`u-science.org` is a zone of it); neither needs a secret in the repository.

| | what | where | needs |
|---|---|---|---|
| `atlas/deploy/` | the static atlas page (`atlas/site`) | `uchrom-atlas.u-science.org` | Workers Free |
| `hosted-browser/` | a Worker + a container running `python -m uchrom.browser --web --hosted` | `uchrom-browser.u-science.org` | **Workers Paid** (Containers), Docker running locally |

The data (`u-chrom-atlas` R2 bucket at `uchrom-atlas-r2.u-science.org`) is separate: `atlas/PUBLISH.md` (dataset by dataset: build, verify, upload, draw the thumbnails).

## Log in once

    npx wrangler login          # opens the browser; or export CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID

## The page

    python apps/atlas/build.py figures apps/atlas/datasets.json --root example-data      # only when a dataset changed
    python apps/atlas/build.py site apps/atlas/deploy/dist --catalog catalog.json --hosted https://uchrom-browser.u-science.org
    cd apps/atlas/deploy && npx wrangler deploy

## The browser

    cd apps/hosted-browser && npm install && npx wrangler deploy      # builds the image (Docker), pushes it, creates the Worker

**Bump `RELEASE` in `wrangler.jsonc` on every deploy**: instances are named after it, so a deploy starts fresh containers on the new image (a running
container was not replaced reliably by the rolling update; the old ones sleep and stop by themselves; visitors' open datasets are lost).

`instance_type` (`standard-1`: 1/2 vCPU, 4 GiB), `INSTANCES` (2: visitors are spread over them by a hash of their session cookie)
and `max_instances` (4: the previous release's two instances keep running until `sleepAfter`, and **a new release cannot start
while they fill the limit** — it must stay at least twice `INSTANCES`) and `sleepAfter` (15 min) in `wrangler.jsonc` / `src/index.ts` set the cost; the server's own
limits (4 datasets and 30 idle minutes per visitor, 64 visitors per instance, pseudo-bulk of at most 5,000 cells) are
`HostedConfig` in `uchrom/browser/web/hosted.py`.
