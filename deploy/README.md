# Deploying the atlas on Cloudflare

Two Workers in one account (`u-science.org` is a zone of it); neither needs a secret in the repository.

| | what | where | needs |
|---|---|---|---|
| `atlas-site/` | the static atlas page (`atlas/site`) | `uchrom-atlas.u-science.org` | Workers Free |
| `browser/` | a Worker + a container running `python -m uchrom.browser --web --hosted` | `uchrom-browser.u-science.org` | **Workers Paid** (Containers), Docker running locally |

The data (`u-chrom-atlas` R2 bucket at `uchrom-atlas-r2.u-science.org`) is separate: `atlas/PUBLISH.md`.

## Log in once

    npx wrangler login          # opens the browser; or export CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID

## The page

    python -m uchrom.core.atlas site deploy/atlas-site/dist --catalog catalog.json    # catalog.json: atlas/PUBLISH.md step 3
    cd deploy/atlas-site && npx wrangler deploy

## The browser

    cd deploy/browser && npm install && npx wrangler deploy      # builds the image (Docker), pushes it, creates the Worker

`instance_type` (`standard-1`: 1/2 vCPU, 4 GiB), `max_instances` / `INSTANCES` (2: visitors are spread over them by a
hash of their session cookie) and `sleepAfter` (15 min) in `wrangler.jsonc` / `src/index.ts` set the cost; the server's own
limits (4 datasets and 30 idle minutes per visitor, 64 visitors per instance, pseudo-bulk of at most 5,000 cells) are
`HostedConfig` in `uchrom/browser/web/hosted.py`.
