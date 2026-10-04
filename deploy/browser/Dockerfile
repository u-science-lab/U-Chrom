# The hosted U-Chrom web browser.  Build context: the repository root (wrangler: image_build_context "../..").
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY deploy/browser/requirements-hosted.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# the package itself, without its (training-time) dependencies
COPY pyproject.toml README.md /src/
COPY uchrom /src/uchrom
RUN pip install --no-deps /src && rm -rf /src \
 # byte-compile everything now: a cold start otherwise compiles the dependencies' modules (seconds)
 && python -m compileall -q /usr/local/lib/python3.12/site-packages

EXPOSE 8000
CMD ["python", "-m", "uchrom.browser", "--web", "--hosted", "--host=0.0.0.0", "--port=8000", "--open_browser=False"]
