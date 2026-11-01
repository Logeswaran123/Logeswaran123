// Converts each [data-svg] element on the page into standalone SVG markup, using the layout
// Chrome computed for it. Text becomes <text> with one x per glyph, so the image matches the
// browser's line breaks, kerning and letter spacing exactly. The result is written into a
// <textarea id="svg-out"> as JSON for build.py to read from --dump-dom.

(() => {
  const r2 = (v) => Math.round(v * 100) / 100;
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  function rgba(c) {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    const a = p.length > 3 ? p[3] : 1;
    if (a === 0) return null;
    const hex = '#' + p.slice(0, 3).map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
    return { hex, a };
  }

  function paint(attr, c) {
    const v = rgba(c);
    if (!v) return `${attr}="none"`;
    return v.a < 1 ? `${attr}="${v.hex}" ${attr}-opacity="${r2(v.a)}"` : `${attr}="${v.hex}"`;
  }

  // Distance from the top of a text fragment's box to its baseline, and the box height, both
  // per pixel of font size. Measured rather than read from the font so it matches Chrome.
  const metricsCache = new Map();
  function metrics(cs) {
    const key = `${cs.fontFamily}|${cs.fontWeight}|${cs.fontStyle}`;
    if (metricsCache.has(key)) return metricsCache.get(key);
    const span = document.createElement('span');
    span.style.cssText = `font-family:${cs.fontFamily};font-weight:${cs.fontWeight};font-style:${cs.fontStyle};font-size:100px;line-height:normal;position:absolute;left:0;top:0;white-space:nowrap`;
    span.textContent = 'H';
    const mark = document.createElement('span');
    mark.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline';
    span.append(mark);
    document.body.append(span);
    const range = document.createRange();
    range.selectNodeContents(span.firstChild);
    const box = range.getBoundingClientRect();
    const m = { ascent: (mark.getBoundingClientRect().bottom - box.top) / 100, height: box.height / 100 };
    span.remove();
    metricsCache.set(key, m);
    return m;
  }

  function radius(cs, w, h) {
    const v = cs.borderTopLeftRadius;
    if (v.endsWith('%')) return (parseFloat(v) / 100) * Math.min(w, h);
    return parseFloat(v) || 0;
  }

  function convert(root) {
    const R = root.getBoundingClientRect();
    const fonts = {};
    let clipId = 0;
    const defs = [];

    function box(el) {
      const r = el.getBoundingClientRect();
      return { x: r.left - R.left, y: r.top - R.top, w: r.width, h: r.height };
    }

    function text(node, cs) {
      const s = node.data;
      const range = document.createRange();
      const m = metrics(cs);
      const size = parseFloat(cs.fontSize);
      const upper = cs.textTransform === 'uppercase';
      const runs = [];
      let run = null;
      for (let i = 0; i < s.length; i++) {
        if (/\s/.test(s[i])) continue;
        range.setStart(node, i);
        range.setEnd(node, i + 1);
        const rects = range.getClientRects();
        if (!rects.length) continue;
        const r = rects[0];
        const scale = r.height / (m.height * size) || 1;
        const base = r.top - R.top + m.ascent * size * scale;
        if (!run || Math.abs(run.base - base) > 0.5) {
          run = { base, scale, xs: [], chars: '' };
          runs.push(run);
        }
        run.xs.push(r2(r.left - R.left));
        run.chars += upper ? s[i].toUpperCase() : s[i];
      }
      // A text-shadow halo becomes a stroked copy drawn first. paint-order would not do: with one
      // x per glyph, each glyph's stroke would cover the fill of the one before it.
      const shadow = cs.textShadow !== 'none' && rgba(cs.textShadow);
      const halo = shadow ? `${paint('fill', cs.textShadow)} ${paint('stroke', cs.textShadow)} stroke-width="6" stroke-linejoin="round"` : '';
      const key = `${cs.fontFamily.split(',')[0].replace(/['"]/g, '').trim()}|${cs.fontWeight}|${cs.fontStyle}`;
      return runs
        .map((run) => {
          fonts[key] = (fonts[key] || '') + run.chars;
          const [family, weight, style] = key.split('|');
          const head =
            `<text x="${run.xs.join(' ')}" y="${r2(run.base)}" font-family="'${family}'" ` +
            `font-weight="${weight}"${style !== 'normal' ? ` font-style="${style}"` : ''} ` +
            `font-size="${r2(size * run.scale)}" `;
          const glyphs = esc(run.chars);
          return (
            (halo ? `${head}${halo}>${glyphs}</text>` : '') +
            `${head}${paint('fill', cs.color)}>${glyphs}</text>`
          );
        })
        .join('');
    }

    function nestedSvg(el) {
      const b = box(el);
      const clone = el.cloneNode(true);
      const src = [el, ...el.querySelectorAll('*')];
      const dst = [clone, ...clone.querySelectorAll('*')];
      src.forEach((o, i) => {
        const c = dst[i];
        const cs = getComputedStyle(o);
        for (const a of [...c.attributes]) {
          if (a.name === 'class' || a.name === 'style' || a.name.startsWith('data-') || a.name.startsWith('aria-')) {
            c.removeAttribute(a.name);
          }
        }
        if (o === el) return;
        if (cs.display === 'none' || cs.visibility === 'hidden') {
          c.setAttribute('display', 'none');
          return;
        }
        for (const [prop, attr] of [['fill', 'fill'], ['stroke', 'stroke']]) {
          const v = cs[prop];
          if (v === 'none') c.setAttribute(attr, 'none');
          else {
            const p = rgba(v);
            if (p) {
              c.setAttribute(attr, p.hex);
              if (p.a < 1) c.setAttribute(`${attr}-opacity`, r2(p.a));
            } else c.setAttribute(attr, 'none');
          }
        }
        if (cs.strokeWidth) c.setAttribute('stroke-width', parseFloat(cs.strokeWidth));
        if (cs.opacity !== '1') c.setAttribute('opacity', cs.opacity);
      });
      clone.setAttribute('x', r2(b.x));
      clone.setAttribute('y', r2(b.y));
      clone.setAttribute('width', r2(b.w));
      clone.setAttribute('height', r2(b.h));
      clone.removeAttribute('xmlns');
      return new XMLSerializer().serializeToString(clone).replace(/ xmlns="[^"]*"/g, '');
    }

    function element(el) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return '';
      if (el.matches('textarea, script, style, .anchor')) return '';
      let out = '';
      const b = box(el);

      if (el !== root) {
        const bg = rgba(cs.backgroundColor);
        const rr = radius(cs, b.w, b.h);
        if (bg) out += `<rect x="${r2(b.x)}" y="${r2(b.y)}" width="${r2(b.w)}" height="${r2(b.h)}"${rr ? ` rx="${r2(rr)}"` : ''} ${paint('fill', cs.backgroundColor)}/>`;
        const sides = ['Top', 'Right', 'Bottom', 'Left'].map((s) => ({
          w: cs[`border${s}Style`] === 'none' ? 0 : parseFloat(cs[`border${s}Width`]),
          c: cs[`border${s}Color`],
        }));
        const uniform = sides.every((s) => s.w === sides[0].w && s.c === sides[0].c);
        if (uniform && sides[0].w > 0 && rgba(sides[0].c)) {
          const w = sides[0].w;
          out += `<rect x="${r2(b.x + w / 2)}" y="${r2(b.y + w / 2)}" width="${r2(b.w - w)}" height="${r2(b.h - w)}"${rr ? ` rx="${r2(Math.max(rr - w / 2, 0))}"` : ''} fill="none" ${paint('stroke', sides[0].c)} stroke-width="${w}"/>`;
        } else {
          const [t, r, bt, l] = sides;
          const edge = (x, y, w, h, s) =>
            s.w > 0 && rgba(s.c) ? `<rect x="${r2(x)}" y="${r2(y)}" width="${r2(w)}" height="${r2(h)}" ${paint('fill', s.c)}/>` : '';
          out += edge(b.x, b.y, b.w, t.w, t);
          out += edge(b.x + b.w - r.w, b.y, r.w, b.h, r);
          out += edge(b.x, b.y + b.h - bt.w, b.w, bt.w, bt);
          out += edge(b.x, b.y, l.w, b.h, l);
        }
      }

      if (el.tagName === 'IMG') {
        const rr = radius(cs, b.w, b.h);
        let clip = '';
        if (rr) {
          const id = `c${clipId++}`;
          defs.push(`<clipPath id="${id}"><rect x="${r2(b.x)}" y="${r2(b.y)}" width="${r2(b.w)}" height="${r2(b.h)}" rx="${r2(rr)}"/></clipPath>`);
          clip = ` clip-path="url(#${id})"`;
        }
        const pad = parseFloat(cs.borderTopWidth) || 0;
        return `<image href="${esc(el.currentSrc || el.src)}" x="${r2(b.x + pad)}" y="${r2(b.y + pad)}" width="${r2(b.w - 2 * pad)}" height="${r2(b.h - 2 * pad)}" preserveAspectRatio="xMidYMid slice"${clip}/>` + out;
      }
      if (el.tagName === 'CANVAS') {
        return `<image href="${el.toDataURL('image/png')}" x="${r2(b.x)}" y="${r2(b.y)}" width="${r2(b.w)}" height="${r2(b.h)}"/>`;
      }
      if (el instanceof SVGSVGElement) return out + nestedSvg(el);

      for (const child of el.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) out += text(child, cs);
        else if (child.nodeType === Node.ELEMENT_NODE) out += element(child);
      }
      const op = parseFloat(cs.opacity);
      return op < 1 ? `<g opacity="${r2(op)}">${out}</g>` : out;
    }

    const body = element(root);
    return {
      name: root.dataset.svg,
      width: Math.ceil(R.width),
      height: Math.ceil(R.height),
      body: (defs.length ? `<defs>${defs.join('')}</defs>` : '') + body,
      fonts,
    };
  }

  async function run() {
    await document.fonts.ready;
    const out = document.createElement('textarea');
    out.id = 'svg-out';
    out.textContent = JSON.stringify([...document.querySelectorAll('[data-svg]')].map(convert));
    document.body.append(out);
  }

  window.dom2svg = run;
})();
