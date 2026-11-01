"""Build the profile README and its SVG blocks in the style of logeswaranofficial.com.

    pip install fonttools brotli pillow
    python tools/build.py

Needs Chrome or Chromium (set CHROME if it is not on PATH). Content comes from
tools/profile.toml, the site's RSS feed and its /tags/ page. Writes assets/*-{light,dark}.svg
and README.md.
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
from PIL import Image

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
ASSETS = ROOT / "assets"
INSET = 14  # left inset of every block, matching .block in page.css
SKY_WIDTH = 826  # 840 with the inset
FONTS = {
    "Inter Variable": TOOLS / "fonts" / "inter-latin-wght-normal.woff2",
    ("JetBrains Mono", 400): TOOLS / "fonts" / "jetbrains-mono-latin-400-normal.woff2",
    ("JetBrains Mono", 600): TOOLS / "fonts" / "jetbrains-mono-latin-600-normal.woff2",
}

# 24x24 icons; the four brand paths are the ones in the site's src/data/profile.ts.
ICONS = {
    "github": '<path fill="currentColor" d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 0-.8.4-1.3.7-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2 0-.4-.5-1.6.2-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.7 1.6.2 2.8.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.5.4.9 1.1.9 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .3"/>',
    "linkedin": '<path fill="currentColor" d="M20.4 20.5h-3.6v-5.6c0-1.3 0-3-1.9-3s-2.1 1.4-2.1 2.9v5.7H9.4V9h3.4v1.6h.1a3.8 3.8 0 0 1 3.4-1.9c3.6 0 4.3 2.4 4.3 5.5v6.3zM5.3 7.4a2.1 2.1 0 1 1 0-4.2 2.1 2.1 0 0 1 0 4.2zm1.8 13.1H3.5V9h3.6v11.5zM22.2 0H1.8C.8 0 0 .8 0 1.7v20.6c0 1 .8 1.7 1.8 1.7h20.4c1 0 1.8-.8 1.8-1.7V1.7c0-1-.8-1.7-1.8-1.7z"/>',
    "medium": '<path fill="currentColor" d="M13.5 12a6.8 6.8 0 1 1-13.5 0 6.8 6.8 0 0 1 13.5 0zm7.4 0c0 3.5-1.5 6.4-3.4 6.4-1.9 0-3.4-2.9-3.4-6.4s1.5-6.4 3.4-6.4c1.9 0 3.4 2.9 3.4 6.4zM24 12c0 3.2-.5 5.7-1.2 5.7-.7 0-1.2-2.5-1.2-5.7s.5-5.7 1.2-5.7c.7 0 1.2 2.5 1.2 5.7z"/>',
    "email": '<path fill="currentColor" d="M2 5.5A1.5 1.5 0 0 1 3.5 4h17A1.5 1.5 0 0 1 22 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 2 18.5v-13zm2 .8v.4l8 5 8-5v-.4H4zm16 2.7-7.5 4.7a1 1 0 0 1-1 0L4 9v9h16V9z"/>',
    "globe": '<g fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c2.5 2.7 3.8 5.9 3.8 9.5s-1.3 6.8-3.8 9.5c-2.5-2.7-3.8-5.9-3.8-9.5s1.3-6.8 3.8-9.5z"/></g>',
}


def icon(name, size):
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}">{ICONS[name]}</svg>'


def clean(s):
    return re.sub(r"\s+", " ", s).strip()


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
            "--allow-file-access-from-files", "--force-device-scale-factor=2",
            "--force-prefers-reduced-motion", "--window-size=1280,4000",
            f"--blink-settings=preferredColorScheme={0 if dark else 1}",
            "--virtual-time-budget=20000", "--dump-dom", url,
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
    posts = []
    for item in list(root.iter("item"))[:count]:
        posts.append({
            "title": item.findtext("title"),
            "href": item.findtext("link"),
            "description": item.findtext("description") or "",
            "date": parsedate_to_datetime(item.findtext("pubDate")),
            "tags": [c.text for c in item.findall("category")],
        })
    return posts


def avatar(site):
    im = Image.open(io.BytesIO(fetch(f"{site}/avatar.jpg"))).convert("RGB").resize((176, 176), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def page(p, posts):
    """The README blocks as one HTML page, each block marked with data-svg."""
    blocks = []  # (name, href, alt) in README order; None marks a row break
    parts = []

    def add(name, href, alt, markup):
        blocks.append((name, href, alt))
        parts.append(markup.replace("<BLOCK", f'<div data-svg="{name}"', 1))

    nav = "".join(
        f'<span class="{"active" if label == "About" else ""}">{label}</span>'
        for label in ["Posts", "About", "Tags", "Archive", "Contact"]
    )
    socials = "".join(icon(n, 17) for n in ["github", "linkedin", "medium", "email"])
    bio = "".join(f"<p>{e(clean(b))}</p>" for b in p["bio"])
    add(
        "header", f"{p['site']}/about/",
        f"{p['name']}. {p['role']}, {p['location']}. {p['tagline']}.",
        f"""<BLOCK class="block shell">
          <aside class="sidebar">
            <div><img class="avatar" src="{avatar(p['site'])}" alt="">
            <p class="name">{e(p['name'])}</p><p class="tagline">{e(p['tagline'])}</p></div>
            <nav class="nav">{nav}</nav>
            <div class="socials">{socials}</div>
          </aside>
          <div class="intro">
            <h1 class="page-title">{e(p['name'])}</h1>
            <p class="page-lede">{e(p['role'])} · {e(p['location'])}</p>
            {bio}
          </div>
        </div>""",
    )

    for i, link in enumerate(p["links"]):
        add(
            f"link-{slug(link['label'])}", link["href"], link["label"],
            f'<BLOCK class="link-wrap{" first" if i == 0 else ""}">'
            f'<span class="link">{icon(link["icon"], 14)}{e(link["label"])}</span></div>',
        )
    blocks.append(None)

    def title(name, href, label):
        add(f"title-{name}", href, label, f'<BLOCK class="block"><h2 class="section-title">{label}</h2></div>')

    title("posts", p["site"] + "/", "Posts")
    for i, post in enumerate(posts):
        chips = "".join(f'<span class="chip">{e(t)}</span>' for t in post["tags"])
        last = " last" if i == len(posts) - 1 else ""
        add(
            f"post-{slug(post['href'].rstrip('/').rsplit('/', 1)[-1])}", post["href"], post["title"],
            f"""<BLOCK class="block"><div class="card{last}">
              <h2 class="title">{e(post['title'])}</h2>
              <p class="description">{e(post['description'])}</p>
              <div class="footer"><span class="meta">{post['date']:%b} {post['date'].day}, {post['date']:%Y}</span>{chips}</div>
            </div></div>""",
        )

    title("projects", f"{p['site']}/about/", "Selected projects")
    for proj in p["projects"]:
        desc = e(clean(proj["description"]))
        if proj.get("featured"):
            tech = "".join(f'<span class="chip">{e(t)}</span>' for t in proj.get("tech", []))
            markup = f"""<BLOCK class="block"><div class="entry">
              <p class="entry-title">{e(proj['name'])}</p>
              <p class="entry-body">{desc}</p>
              <div class="chip-row" style="margin-bottom:8px"><span class="chip">Code</span></div>
              <div class="chip-row">{tech}</div>
            </div></div>"""
        else:
            markup = f"""<BLOCK class="block"><div class="compact"><p>
              <span class="strong">{e(proj['name'])}</span><span class="muted">: {desc}</span>
              <span class="chip">Code</span></p></div></div>"""
        add(f"project-{slug(proj['name'])}", proj["href"], f"{proj['name']}: {clean(proj['description'])}", markup)

    title("experience", f"{p['site']}/about/", "Experience")
    roles = "".join(
        f"""<div class="entry"><div class="entry-head">
          <p class="entry-title">{e(r['title'])}, {e(r['org'])}</p>
          <p class="meta period">{e(r['period'])}</p></div></div>"""
        for r in p["experience"]
    )
    add(
        "experience", f"{p['site']}/about/",
        "; ".join(f"{r['title']}, {r['org']}, {r['period']}" for r in p["experience"]),
        f'<BLOCK class="block roles">{roles}</div>',
    )

    title("tags", f"{p['site']}/tags/", "Tags")
    blocks.append(("sky", f"{p['site']}/tags/", "Star chart of the tags used on the site's posts"))

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
    return doc, blocks


def sky_page(site):
    """The site's live /tags/ page with dom2svg.js attached to its star chart."""
    doc = fetch(f"{site}/tags/").decode()
    doc = doc.replace("<head>", f'<head><base href="{site}/">', 1)
    # Label halos take GitHub's page colour instead of the site's, and the chart is drawn at
    # the README blocks' width.
    hook = f"""<style>
        :root {{ --bg: #ffffff; }}
        :root[data-theme='dark'] {{ --bg: #0d1117; }}
        .main-inner {{ max-width: none; }}
        .sky {{ width: {SKY_WIDTH}px; }}
      </style>
      <script>{(TOOLS / 'dom2svg.js').read_text()}</script>
      <script>setTimeout(() => {{
        document.querySelector('nav.sky').dataset.svg = 'sky';
        dom2svg();
      }}, 4000)</script>"""
    return doc.replace("</body>", hook + "</body>", 1)


_instances = {}


def font_data(family, weight, chars):
    weight = int(weight)
    if family.startswith("Inter"):
        if weight not in _instances:
            f = instancer.instantiateVariableFont(TTFont(FONTS["Inter Variable"]), {"wght": weight})
            buf = io.BytesIO()
            f.save(buf)
            _instances[weight] = buf.getvalue()
        f = TTFont(io.BytesIO(_instances[weight]))
    else:
        f = TTFont(FONTS[(family, 600 if weight >= 500 else 400)])
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
    w, h, body = block["width"], block["height"], block["body"]
    if block["name"] == "sky":
        w += INSET
        body = f'<g transform="translate({INSET} 0)">{body}</g>'
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"<style>{faces}</style>{body}</svg>\n"
    )
    (ASSETS / f"{block['name']}-{theme}.svg").write_text(svg)


def readme(blocks):
    lines = ["<!-- Generated by tools/build.py; edit tools/profile.toml instead. -->", ""]
    row = []
    for b in blocks:
        if b is None:
            lines += [" ".join(row), ""]
            row = []
            continue
        name, href, alt = b
        img = (
            f'<a href="{e(href)}"><picture>'
            f'<source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img alt="{e(alt)}" src="assets/{name}-light.svg">'
            f"</picture></a>"
        )
        if name.startswith("link-"):
            row.append(img)
        else:
            lines += [img, ""]
    (ROOT / "README.md").write_text("\n".join(lines).rstrip() + "\n")


def main():
    p = tomllib.loads((TOOLS / "profile.toml").read_text())
    posts = load_posts(p["site"], p["posts"])
    doc, blocks = page(p, posts)
    sky = sky_page(p["site"])

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "page.html").write_text(doc)
        (Path(tmp) / "sky.html").write_text(sky)
        ASSETS.mkdir(exist_ok=True)
        for old in ASSETS.glob("*-light.svg"):
            old.unlink()
        for old in ASSETS.glob("*-dark.svg"):
            old.unlink()
        for theme in ["light", "dark"]:
            dark = theme == "dark"
            rendered = render((Path(tmp) / "page.html").as_uri(), dark)
            rendered += render((Path(tmp) / "sky.html").as_uri(), dark)
            for block in rendered:
                write_svg(block, theme)
    readme(blocks)


if __name__ == "__main__":
    main()
