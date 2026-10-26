import re, base64, subprocess, sys, pathlib, html
src = pathlib.Path(sys.argv[1]); imgdir = src.parent / "img"; out = pathlib.Path(sys.argv[2])
md = src.read_text(encoding="utf-8")
# title and byline
lines = md.splitlines()
title = lines[0].lstrip("# ").strip()
byline = lines[2].strip()
body = "\n".join(lines[3:])
# figures: image + "How to read it:" paragraph
def fig(m):
    alt, path, cap = m.group(1), m.group(2), m.group(3)
    b64 = base64.b64encode((src.parent / path).read_bytes()).decode()
    cap = html.escape(cap.strip()); cap = cap[:1].upper() + cap[1:]
    cap = re.sub(r"`([^`]+)`", r"<code>\1</code>", cap)
    return (f'\n<figure><div class="frame"><img src="data:image/png;base64,{b64}" alt="{html.escape(alt)}"></div>'
            f'<figcaption><span class="howto">How to read it</span>{cap}</figcaption></figure>\n')
body = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)\s*\n\s*\nHow to read it:(.*?)\n(?=\n|$)", fig, body, flags=re.S)
frag = subprocess.run(["pandoc", "-f", "markdown-implicit_figures", "-t", "html5", "--wrap=none"],
                      input=body, capture_output=True, text=True, check=True).stdout
# lead paragraph
frag = frag.replace("<p>", '<p class="lead">', 1)
# wrap tables
frag = re.sub(r"<table>", '<div class="tablewrap"><table>', frag).replace("</table>", "</table></div>")
# method list
frag = re.sub(r'<ol[^>]*>', '<ol class="methods">', frag, count=1)
# bold the term before the first period in each method item
frag = re.sub(r'(<ol class="methods">.*?</ol>)', lambda m: re.sub(r"<li>([^.<]+)\.", r"<li><strong>\1.</strong>", m.group(1)), frag, flags=re.S)
words = len(re.sub(r"<[^>]+>", " ", md).split())
mins = max(1, round(words / 230))
css = pathlib.Path("style.css").read_text()
page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{css}</style></head>
<body>
<header class="mast"><div class="mast-in">
  <div class="brand"><svg viewBox="0 0 36 24" width="36" height="24" aria-hidden="true"><path d="M8 22 L14 2" stroke="#00AAFF" stroke-width="4"/><path d="M16 22 L22 2" stroke="#001AFF" stroke-width="4"/><path d="M24 22 L30 2" stroke="#D5FE51" stroke-width="4"/></svg><span>LevelBlue</span></div>
  <p class="kicker">Microsoft Sentinel data lake</p>
  <h1>{html.escape(title)}</h1>
  <p class="meta">{html.escape(byline)} <span class="dot"></span> {mins} min read</p>
</div></header>
<main class="post">
{frag}
</main>
<footer class="foot"><div class="foot-in">© 2026 LevelBlue Intellectual Property. LevelBlue logo, and registered trademarks and service marks are the property of LevelBlue Intellectual Property and/or LevelBlue affiliated companies. All other marks are the property of their respective owners.</div></footer>
</body></html>"""
out.write_text(page, encoding="utf-8")
print(out, len(page), words, "words")
