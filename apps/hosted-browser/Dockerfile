# The hosted U-Chrom web browser.  Build context: the repository root (wrangler: image_build_context "../..").
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY apps/hosted-browser/requirements-hosted.txt /tmp/requirements.txt
COPY packages/chromdata /src/chromdata
COPY pyproject.toml README.md /src/
COPY uchrom /src/uchrom

# One layer, so that what is deleted here is really gone from the image:
# the dependencies the web server needs, the data model (chromdata) and the package without their (training-time)
# dependencies, then
# - the test suites the packages ship (tens of MB),
# - everything byte-compiled now (a cold start would otherwise compile the dependencies' modules: seconds).
RUN pip install -r /tmp/requirements.txt \
 && pip install --no-deps /src/chromdata /src \
 && rm -rf /src /tmp/requirements.txt \
 && find /usr/local/lib/python3.12/site-packages -type d \( -name tests -o -name test \) -prune -exec rm -rf {} + \
 && python -m compileall -q /usr/local/lib/python3.12/site-packages

EXPOSE 8000
CMD ["python", "-m", "uchrom.browser", "--web", "--hosted", "--host=0.0.0.0", "--port=8000", "--open_browser=False"]
