"""Render each artboard to PNG (2x) and PDF, plus one combined PDF.

The artboards are static, so the markup inside <x-dc> renders as plain HTML.
"""
import json, os, re, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(HERE, "..", "canvas", "project")
OUT = os.path.join(HERE, "..", "export")
os.makedirs(os.path.join(OUT, "png"), exist_ok=True)
os.makedirs(os.path.join(OUT, "pdf"), exist_ok=True)
W, H = 1080, 1350

names = json.load(open(os.path.join(HERE, "boards.json")))


def plain(src):
    inner = re.search(r"<x-dc>(.*)</x-dc>", src, re.S).group(1)
    inner = inner.replace("<helmet>", "").replace("</helmet>", "")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"></head>'
            f'<body style="margin:0">{inner}</body></html>')


pages = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
    for fname, title, slug in names:
        html = plain(open(os.path.join(PROJ, fname), encoding="utf-8").read())
        pg.set_content(html)
        pg.wait_for_timeout(150)
        # overflow check: any element extending past the root
        over = pg.evaluate("""() => { const r = document.querySelector('body > div'); const out = [];
          r.querySelectorAll('*').forEach(e => { const b = e.getBoundingClientRect();
            if (b.width && (b.right > 1081 || b.bottom > 1351)) out.push(e.tagName + ':' + (e.textContent||'').slice(0,40)); });
          const main = r.children[1]; return {out: out.slice(0,5), mainScroll: main.scrollHeight, mainClient: main.clientHeight}; }""")
        print(slug, over)
        pg.screenshot(path=os.path.join(OUT, "png", f"{slug}.png"), clip={"x": 0, "y": 0, "width": W, "height": H})
        pg.pdf(path=os.path.join(OUT, "pdf", f"{slug}.pdf"), width=f"{W}px", height=f"{H}px",
               print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        pages.append(os.path.join(OUT, "pdf", f"{slug}.pdf"))
    b.close()

from pypdf import PdfWriter
w = PdfWriter()
for f in pages:
    w.append(f)
w.write(os.path.join(OUT, "sentinel-data-lake-normalization-infographics.pdf"))
print("done")
