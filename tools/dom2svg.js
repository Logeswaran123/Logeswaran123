// Converts each [data-svg] element on the page into standalone SVG markup, using the layout
// Chrome computed for it. Text becomes <text> with one x per glyph, so the image matches the
// browser's line breaks, kerning and letter spacing exactly. The result is written into a
// textarea with id svg-out, as JSON, for build.py to read from --dump-dom.

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

  // Distance from the top of a text fragment's box to its baseline, per pixel of font size.
  // Measured rather than read from the font so it matches Chrome.
  const ascents = new Map();
  function ascent(cs) {
    const key = `${cs.fontFamily}|${cs.fontWeight}|${cs.fontStyle}`;
    if (ascents.has(key)) return ascents.get(key);
    const span = document.createElement('span');
    span.style.cssText = `font-family:${cs.fontFamily};font-weight:${cs.fontWeight};font-style:${cs.fontStyle};font-size:100px;line-height:normal;position:absolute;left:0;top:0;white-space:nowrap`;
    span.textContent = 'H';
    const mark = document.createElement('span');
    mark.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline';
    span.append(mark);
    document.body.append(span);
    const range = document.createRange();
    range.selectNodeContents(span.firstChild);
    const a = (mark.getBoundingClientRect().bottom - range.getBoundingClientRect().top) / 100;
    span.remove();
    ascents.set(key, a);
    return a;
  }

  function convert(root) {
    const R = root.getBoundingClientRect();
    const fonts = {};

    function box(el) {
      const r = el.getBoundingClientRect();
      return { x: r.left - R.left, y: r.top - R.top, w: r.width, h: r.height };
    }

    function text(node, cs) {
      const s = node.data;
      const range = document.createRange();
      const size = parseFloat(cs.fontSize);
      const upper = cs.textTransform === 'uppercase';
      const runs = [];
      let run = null;
      for (let i = 0; i < s.length; i++) {
        if (/\s/.test(s[i])) continue;
        range.setStart(node, i);
        range.setEnd(node, i + 1);
        const r = range.getClientRects()[0];
        if (!r) continue;
        const base = r.top - R.top + ascent(cs) * size;
        if (!run || Math.abs(run.base - base) > 0.5) {
          run = { base, xs: [], chars: '' };
          runs.push(run);
        }
        run.xs.push(r2(r.left - R.left));
        run.chars += upper ? s[i].toUpperCase() : s[i];
      }
      const family = cs.fontFamily.split(',')[0].replace(/['"]/g, '').trim();
      const key = `${family}|${cs.fontWeight}|${cs.fontStyle}`;
      return runs
        .map((run) => {
          fonts[key] = (fonts[key] || '') + run.chars;
          return (
            `<text x="${run.xs.join(' ')}" y="${r2(run.base)}" font-family="'${family}'" ` +
            `font-weight="${cs.fontWeight}" font-size="${r2(size)}" ${paint('fill', cs.color)}>${esc(run.chars)}</text>`
          );
        })
        .join('');
    }

    // Inline icons: copy the markup with every computed fill and stroke written out, since
    // currentColor and CSS do not carry over into the standalone image.
    function icon(el) {
      const b = box(el);
      const clone = el.cloneNode(true);
      const src = [...el.querySelectorAll('*')];
      [...clone.querySelectorAll('*')].forEach((c, i) => {
        const cs = getComputedStyle(src[i]);
        for (const prop of ['fill', 'stroke']) {
          const p = rgba(cs[prop]);
          c.setAttribute(prop, p ? p.hex : 'none');
        }
      });
      for (const [k, v] of Object.entries({ x: b.x, y: b.y, width: b.w, height: b.h })) clone.setAttribute(k, r2(v));
      return new XMLSerializer().serializeToString(clone).replace(/ xmlns="[^"]*"/g, '');
    }

    function element(el) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return '';
      let out = '';
      const b = box(el);

      const rr = parseFloat(cs.borderTopLeftRadius) || 0;
      if (rgba(cs.backgroundColor)) {
        out += `<rect x="${r2(b.x)}" y="${r2(b.y)}" width="${r2(b.w)}" height="${r2(b.h)}"${rr ? ` rx="${rr}"` : ''} ${paint('fill', cs.backgroundColor)}/>`;
      }
      // A border on all four sides (chips) is a stroked rect; single rules are thin rects.
      const [t, r, bt, l] = ['Top', 'Right', 'Bottom', 'Left'].map((s) => parseFloat(cs[`border${s}Width`]) || 0);
      if (t > 0 && t === r && t === bt && t === l) {
        out += `<rect x="${r2(b.x + t / 2)}" y="${r2(b.y + t / 2)}" width="${r2(b.w - t)}" height="${r2(b.h - t)}"${rr ? ` rx="${r2(rr - t / 2)}"` : ''} fill="none" ${paint('stroke', cs.borderTopColor)} stroke-width="${t}"/>`;
      } else {
        if (t > 0) out += `<rect x="${r2(b.x)}" y="${r2(b.y)}" width="${r2(b.w)}" height="${t}" ${paint('fill', cs.borderTopColor)}/>`;
        if (bt > 0) out += `<rect x="${r2(b.x)}" y="${r2(b.y + b.h - bt)}" width="${r2(b.w)}" height="${bt}" ${paint('fill', cs.borderBottomColor)}/>`;
      }

      if (el instanceof SVGSVGElement) return out + icon(el);
      for (const child of el.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) out += text(child, cs);
        else if (child.nodeType === Node.ELEMENT_NODE) out += element(child);
      }
      return out;
    }

    return {
      name: root.dataset.svg,
      width: Math.ceil(R.width),
      height: Math.ceil(R.height),
      body: element(root),
      fonts,
    };
  }

  window.dom2svg = async () => {
    await document.fonts.ready;
    const out = document.createElement('textarea');
    out.id = 'svg-out';
    out.textContent = JSON.stringify([...document.querySelectorAll('[data-svg]')].map(convert));
    document.body.append(out);
  };
})();
