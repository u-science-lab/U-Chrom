"""The tutorial gallery: one card per tutorial — a thumbnail of one of its figures, its title, a line on what
it shows — in a responsive grid.

A page lists the cards of a section with a directive whose content is YAML::

    ```{tutorial-gallery}
    - tutorial: tad_calling          # tutorials/tad_calling.ipynb (a page of the docs)
      text: TADs from 3-D distances (ArcFISH), against Hi-C
      image: 1                       # which figure of the executed notebook (1 = the first; default 1)
      crop: [0, 0, 0.5, 1]           # optional: the part of it (left, top, right, bottom; fractions)
    ```

The title is the notebook's first heading.  The thumbnails are cut from the figures the committed notebooks
already hold (no execution) when the HTML is written, into ``_static/gallery/`` (WebP); a gallery page is rebuilt when
one of its notebooks changes.  A tutorial that is not a page of the docs is reported as a warning.
"""

from __future__ import annotations

import base64
import html
import io
import json
import posixpath
import re
from pathlib import Path

import yaml
from docutils import nodes
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

logger = logging.getLogger(__name__)

#: largest thumbnail (pixels: twice the card on a high-density screen; the aspect ratio is kept, the card
#: letterboxes it)
THUMB_SIZE = (600, 375)
THUMB_DIR = "_static/gallery"


def _notebook(srcdir: str, name: str) -> Path:
    return Path(srcdir) / "tutorials" / f"{name}.ipynb"


def _title(nb: Path) -> str:
    """The first heading of the notebook."""
    cells = json.loads(nb.read_text())["cells"]
    for c in cells:
        if c["cell_type"] == "markdown":
            for line in "".join(c["source"]).splitlines():
                if line.startswith("#"):
                    return line.lstrip("#").strip()
    return nb.stem


def _inline(text: str) -> str:
    """Escaped text with ``code`` spans as <code>."""
    parts = re.split(r"`([^`]+)`", text)
    return "".join(f"<code>{html.escape(p)}</code>" if k % 2 else html.escape(p) for k, p in enumerate(parts))


def _figures(nb: Path) -> list:
    out = []
    for c in json.loads(nb.read_text())["cells"]:
        if c["cell_type"] != "code":
            continue
        for o in c.get("outputs", []):
            png = o.get("data", {}).get("image/png")
            if png:
                out.append(base64.b64decode("".join(png) if isinstance(png, list) else png))
    return out


def _ext() -> str:
    """WebP thumbnails (a tenth of a PNG of a heat map); the figure as it is (PNG) without Pillow."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return "png"
    return "webp"


def _thumbnail(nb: Path, image: int, crop, dest: Path) -> None:
    figures = _figures(nb)
    if not figures:
        raise ValueError(f"{nb.name} has no figure output")
    if not 1 <= image <= len(figures):
        raise ValueError(f"{nb.name}: image={image}, but it has {len(figures)} figure(s)")
    data = figures[image - 1]
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except ImportError:                               # no Pillow: the figure as it is
        dest.write_bytes(data)
        return
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if crop:
        l, t, r, b = crop
        im = im.crop((round(l * im.width), round(t * im.height), round(r * im.width), round(b * im.height)))
    im.thumbnail(THUMB_SIZE, Image.LANCZOS)
    im.save(dest, "WEBP", quality=85, method=6)


class TutorialGallery(SphinxDirective):
    has_content = True

    def run(self):
        try:
            items = yaml.safe_load("\n".join(self.content)) or []
        except yaml.YAMLError as exc:
            raise self.error(f"tutorial-gallery: not YAML ({exc})")
        env = self.env
        docname = env.docname
        registry = env.__dict__.setdefault("tutorial_gallery", {}).setdefault(docname, [])
        builder = env.app.builder
        cards = []
        for item in items:
            name = item.get("tutorial")
            nb = _notebook(env.srcdir, name or "")
            target = f"tutorials/{name}"
            if not name or target not in env.found_docs or not nb.exists():
                logger.warning(f"tutorial-gallery: {name!r} is not a tutorial page of the docs",
                               location=self.get_location())
                continue
            env.note_dependency(str(nb))
            n_figures = len(_figures(nb))
            if not 1 <= int(item.get("image", 1)) <= n_figures:
                logger.warning(f"tutorial-gallery: {name}: image={item.get('image', 1)}, but the executed notebook "
                               f"has {n_figures} figure(s)", location=self.get_location())
                continue
            registry.append({"tutorial": name, "image": int(item.get("image", 1)), "crop": item.get("crop")})
            title = item.get("title") or _title(nb)
            href = builder.get_relative_uri(docname, target) if hasattr(builder, "get_relative_uri") else ""
            src = posixpath.relpath(f"{THUMB_DIR}/{name}.{_ext()}", posixpath.dirname(docname) or ".")
            cards.append(
                f'<a class="uc-card" href="{html.escape(href)}">'
                f'<span class="uc-card-img"><img src="{html.escape(src)}" alt="" loading="lazy"></span>'
                f'<span class="uc-card-title">{_inline(title)}</span>'
                f'<span class="uc-card-text">{_inline(item.get("text", ""))}</span></a>')
        return [nodes.raw("", '<div class="uc-gallery">' + "".join(cards) + "</div>", format="html")]


def _purge(app, env, docname):
    env.__dict__.get("tutorial_gallery", {}).pop(docname, None)


def _merge(app, env, docnames, other):
    mine = env.__dict__.setdefault("tutorial_gallery", {})
    for doc, items in other.__dict__.get("tutorial_gallery", {}).items():
        if doc in docnames:
            mine[doc] = items


def _write_thumbnails(app, exception):
    if exception is not None or app.builder.format != "html":
        return
    out = Path(app.outdir) / THUMB_DIR
    for items in app.env.__dict__.get("tutorial_gallery", {}).values():
        for item in items:
            try:
                _thumbnail(_notebook(app.srcdir, item["tutorial"]), item["image"], item["crop"],
                           out / f"{item['tutorial']}.{_ext()}")
            except ValueError as exc:
                logger.warning(f"tutorial-gallery: {exc}")


def setup(app):
    app.add_directive("tutorial-gallery", TutorialGallery)
    app.connect("env-purge-doc", _purge)
    app.connect("env-merge-info", _merge)
    app.connect("build-finished", _write_thumbnails)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
