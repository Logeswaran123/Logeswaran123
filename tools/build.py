"""Build the profile README and its SVG blocks in the colours and type of logeswaranofficial.com.

    pip install fonttools brotli
    python tools/build.py

Needs Chrome or Chromium (set CHROME if it is not on PATH). Content comes from
tools/profile.toml and the site's RSS feed. Writes assets/*-{light,dark}.svg and README.md.
"""

import base64
import html
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
ASSETS = ROOT / "assets"
FONTS = {
    "Inter Variable": TOOLS / "fonts" / "inter-latin-wght-normal.woff2",
    ("JetBrains Mono", 400): TOOLS / "fonts" / "jetbrains-mono-latin-400-normal.woff2",
    ("JetBrains Mono", 600): TOOLS / "fonts" / "jetbrains-mono-latin-600-normal.woff2",
}

# 24x24 icons; the brand paths are the ones in the site's src/data/profile.ts.
ICONS = {
    "linkedin": '<path fill="currentColor" d="M20.4 20.5h-3.6v-5.6c0-1.3 0-3-1.9-3s-2.1 1.4-2.1 2.9v5.7H9.4V9h3.4v1.6h.1a3.8 3.8 0 0 1 3.4-1.9c3.6 0 4.3 2.4 4.3 5.5v6.3zM5.3 7.4a2.1 2.1 0 1 1 0-4.2 2.1 2.1 0 0 1 0 4.2zm1.8 13.1H3.5V9h3.6v11.5zM22.2 0H1.8C.8 0 0 .8 0 1.7v20.6c0 1 .8 1.7 1.8 1.7h20.4c1 0 1.8-.8 1.8-1.7V1.7c0-1-.8-1.7-1.8-1.7z"/>',
    "medium": '<path fill="currentColor" d="M13.5 12a6.8 6.8 0 1 1-13.5 0 6.8 6.8 0 0 1 13.5 0zm7.4 0c0 3.5-1.5 6.4-3.4 6.4-1.9 0-3.4-2.9-3.4-6.4s1.5-6.4 3.4-6.4c1.9 0 3.4 2.9 3.4 6.4zM24 12c0 3.2-.5 5.7-1.2 5.7-.7 0-1.2-2.5-1.2-5.7s.5-5.7 1.2-5.7c.7 0 1.2 2.5 1.2 5.7z"/>',
    "globe": '<g fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c2.5 2.7 3.8 5.9 3.8 9.5s-1.3 6.8-3.8 9.5c-2.5-2.7-3.8-5.9-3.8-9.5s1.3-6.8 3.8-9.5z"/></g>',
}


def e(s):
    return html.escape(s, quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "profile-readme-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def chrome():
    for c in [os.environ.get("CHROME"), "google-chrome", "chromium", "chromium-browser"]:
        if c and shutil.which(c):
            return shutil.which(c)
    found = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux*/chrome"))
    if found:
        return str(found[-1])
    raise SystemExit("Chrome not found; set CHROME")


def render(url, dark):
    """Load url in headless Chrome and return what dom2svg.js wrote into the page."""
    out = subprocess.run(
        [
            chrome(), "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            "--allow-file-access-from-files", "--window-size=1280,4000",
            f"--blink-settings=preferredColorScheme={0 if dark else 1}",
            "--virtual-time-budget=10000", "--dump-dom", url,
        ],
        capture_output=True, text=True, check=True, timeout=180,
    ).stdout
    start = out.rfind('<textarea id="svg-out">')
    if start < 0:
        raise SystemExit(f"no output from {url}")
    found = out[start:].split(">", 1)[1].split("</textarea>", 1)[0]
    return json.loads(html.unescape(found))


def load_posts(site, count):
    root = ET.fromstring(fetch(f"{site}/rss.xml"))
    return [
        {
            "title": item.findtext("title"),
            "href": item.findtext("link"),
            "date": parsedate_to_datetime(item.findtext("pubDate")),
        }
        for item in list(root.iter("item"))[:count]
    ]


def page(p, posts):
    """The README blocks as one HTML page, each marked with data-svg.

    Also returns the README layout: a list of paragraphs, each a list of (name, href, alt).
    Blocks in one paragraph sit on separate lines, except link chips, which share one.
    """
    groups, parts = [], []

    def add(name, href, alt, cls, inner):
        groups[-1].append((name, href, alt))
        parts.append(f'<div data-svg="{name}" class="{cls}">{inner}</div>')

    groups.append([])
    add(
        "header", p["site"], f"{p['name']}, {p['role']}",
        "block",
        f'<p class="name">{e(p["name"])}</p>'
        f'<p class="lede">{e(p["role"])} · {e(p["location"])}</p>'
        f'<p>{e(p["summary"])}</p>',
    )

    groups.append([])
    for link in p["links"]:
        add(
            f"link-{slug(link['label'])}", link["href"], link["label"],
            "chip-wrap",
            f'<span class="chip"><svg viewBox="0 0 24 24" width="13" height="13">{ICONS[link["icon"]]}</svg>'
            f"{e(link['label'])}</span>",
        )

    groups.append([])
    add("title-projects", f"{p['site']}/about/", "Selected projects", "block", '<p class="section-title">Selected projects</p>')
    for i, proj in enumerate(p["projects"]):
        add(
            f"project-{slug(proj['name'])}", proj["href"], f"{proj['name']}: {proj['description']}",
            f"block row{' ruled' if i else ''}",
            f'<p><span class="label">{e(proj["name"])}</span><span class="desc">{e(proj["description"])}</span></p>',
        )

    groups.append([])
    add("title-posts", p["site"] + "/", "Posts", "block", '<p class="section-title">Posts</p>')
    for i, post in enumerate(posts):
        add(
            f"post-{slug(post['href'].rstrip('/').rsplit('/', 1)[-1])}", post["href"], post["title"],
            f"block row{' ruled' if i else ''}",
            f'<p class="label">{e(post["title"])}</p><p class="date">{post["date"]:%b %Y}</p>',
        )

    faces = "".join(
        f"@font-face{{font-family:'{fam}';font-weight:{w};src:url('{path.as_uri()}')}}"
        for fam, w, path in [
            ("Inter Variable", "100 900", FONTS["Inter Variable"]),
            ("JetBrains Mono", "400", FONTS[("JetBrains Mono", 400)]),
            ("JetBrains Mono", "600", FONTS[("JetBrains Mono", 600)]),
        ]
    )
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
      <style>{faces}{(TOOLS / 'page.css').read_text()}</style></head>
      <body>{''.join(parts)}<script>{(TOOLS / 'dom2svg.js').read_text()}</script>
      <script>dom2svg()</script></body></html>"""
    return doc, groups


_instances = {}


def font_data(family, weight, chars):
    # recalcTimestamp=False keeps the output identical between runs.
    weight = int(weight)
    if family.startswith("Inter"):
        if weight not in _instances:
            f = TTFont(FONTS["Inter Variable"], recalcTimestamp=False)
            f = instancer.instantiateVariableFont(f, {"wght": weight})
            buf = io.BytesIO()
            f.save(buf)
            _instances[weight] = buf.getvalue()
        f = TTFont(io.BytesIO(_instances[weight]), recalcTimestamp=False)
    else:
        f = TTFont(FONTS[(family, 600 if weight >= 500 else 400)], recalcTimestamp=False)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = []
    opts.hinting = False
    opts.name_IDs = []
    opts.notdef_outline = True
    s = subset.Subsetter(opts)
    s.populate(text="".join(sorted(set(chars))))
    s.subset(f)
    buf = io.BytesIO()
    f.flavor = "woff2"
    f.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def write_svg(block, theme):
    faces = "".join(
        f"@font-face{{font-family:'{fam}';font-weight:{w};"
        f"src:url(data:font/woff2;base64,{font_data(fam, w, chars)}) format('woff2')}}"
        for key, chars in sorted(block["fonts"].items())
        for fam, w, _ in [key.split("|")]
    )
    w, h = block["width"], block["height"]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"<style>{faces}</style>{block['body']}</svg>\n"
    )
    (ASSETS / f"{block['name']}-{theme}.svg").write_text(svg)


def readme(groups):
    def img(name, href, alt):
        return (
            f'<a href="{e(href)}"><picture>'
            f'<source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img alt="{e(alt)}" src="assets/{name}-light.svg">'
            f"</picture></a>"
        )

    paragraphs = []
    for group in groups:
        if group[0][0].startswith("link-"):
            paragraphs.append(" ".join(img(*b) for b in group))
        else:
            paragraphs.append("<br>\n".join(img(*b) for b in group))
    text = "<!-- Generated by tools/build.py; edit tools/profile.toml instead. -->\n\n"
    (ROOT / "README.md").write_text(text + "\n\n".join(paragraphs) + "\n")


def main():
    p = tomllib.loads((TOOLS / "profile.toml").read_text())
    doc, groups = page(p, load_posts(p["site"], p["posts"]))

    ASSETS.mkdir(exist_ok=True)
    for old in [*ASSETS.glob("*-light.svg"), *ASSETS.glob("*-dark.svg")]:
        old.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "page.html"
        path.write_text(doc)
        for theme in ["light", "dark"]:
            for block in render(path.as_uri(), theme == "dark"):
                write_svg(block, theme)
    readme(groups)


if __name__ == "__main__":
    main()
