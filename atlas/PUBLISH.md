# Publishing the atlas

The atlas is a Cloudflare R2 bucket (`u-chrom-atlas`) served at `https://uchrom-atlas-r2.u-science.org`
(custom domain of the bucket; `uchrom-atlas.u-science.org` is kept for the atlas web page).  Credentials are never
kept in the repository: put an R2 API token (Object Read & Write, this bucket only) in your environment as
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` and use the S3 endpoint
`https://<account id>.r2.cloudflarestorage.com` (bucket settings -> S3 API).

1. **Embed** every linked file so the store is self-contained, and make it cheap to open over HTTP:

       python -m uchrom.core.embedded STORE.chromdata.zarr          # embeds, skips what is embedded
       python -m uchrom.core.embedded STORE.chromdata.zarr --upgrade # consolidated metadata, chromsizes, var attrs

2. **Upload** (the S3 API of R2 needs a region of `auto`, and the newer AWS CLI checksums off):

       export AWS_DEFAULT_REGION=auto AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
       aws s3 sync STORE.chromdata.zarr s3://u-chrom-atlas/NAME.chromdata.zarr/ --endpoint-url $R2_ENDPOINT \
           --cache-control "public, max-age=3600"

3. **Describe it** in `atlas/datasets.json` (its `study` — one entry of `studies` with the citation, doi, source,
   licence —, `name`, title, organism, tissue; counts are read from the store), then build and upload the catalog:

       python -m uchrom.core.atlas build atlas/datasets.json --root example-data --out catalog.json
       aws s3 cp catalog.json s3://u-chrom-atlas/catalog.json --endpoint-url $R2_ENDPOINT --content-type application/json

4. **Verify** over the public domain:

       python atlas/verify.py

5. **The static page** (`atlas/site`).  Draw the dataset thumbnails from the stores (a section's spots coloured by
   cluster + a 40-Mb window of its bulk contact map; `"figure"` in `datasets.json` pins the section / colour column /
   region, `"hero"` lists the datasets of the page's top figure) and commit `atlas/site/figures/`:

       python -m uchrom.core.atlas figures atlas/datasets.json --root example-data      # -> atlas/site/figures

   then `python -m uchrom.core.atlas site dist/site --catalog catalog.json --hosted URL` and deploy `dist/site`
   (`deploy/README.md`).

Notes learned the hard way: Cloudflare rejects Python's default `urllib` user agent on the public domain (aiohttp /
fsspec and `uchrom.core.atlas.fetch_catalog` are fine); the first open of a store reads ~17 small objects, so
re-uploading a store after `--upgrade` only changes its `zarr.json` files.
