import re, sys, html, json, subprocess, pathlib
src=pathlib.Path(sys.argv[1]); imgmap=json.loads(pathlib.Path(sys.argv[2]).read_text()); out=pathlib.Path(sys.argv[3])
md=src.read_text(encoding='utf-8')
L=md.splitlines(); title=L[0].lstrip('# ').strip(); body="\n".join(L[3:])
SERIF='font-family:"Lora", Georgia, serif;'; MONO='font-family:"IBM Plex Mono", "Courier New", monospace;'
INK='#1c1917'; TXT='#44403c'; MUTE='#78716c'; RULE='#e4ddd4'; RED='#b91c1c'; CODEBG='#f0ebe0'
def figure(m):
    alt,path,cap=m.group(1),m.group(2),m.group(3).strip()
    cap=cap[:1].upper()+cap[1:]
    url=imgmap[pathlib.Path(path).name]
    return f'\n<!--FIG {html.escape(alt)}|{url}|{html.escape(cap)}-->\n'
body=re.sub(r"!\[([^\]]*)\]\(([^)]+)\)\s*\n\s*\nHow to read it:(.*?)\n(?=\n|$)", figure, body, flags=re.S)
frag=subprocess.run(["pandoc","-f","markdown-implicit_figures","-t","html5","--wrap=none"],input=body,capture_output=True,text=True,check=True).stdout
def fig_html(m):
    alt,url,cap=m.group(1),m.group(2),m.group(3)
    return (f'<img class="shot" src="{url}" alt="{alt}" style="width:100%;display:block;border:1px solid #d6cfc4;margin:14px 0 6px" width="100%">\n'
            f'<p class="shot-cap" style=\'{MONO}font-size:10.5px;color:{MUTE};letter-spacing:0.04em;margin-bottom:6px\'>HOW TO READ IT</p>\n'
            f'<p class="shot-cap" style="font-size:12.5px;color:{TXT};line-height:1.65;margin-bottom:22px">{cap}</p>')
frag=re.sub(r'<!--FIG (.*?)\|(.*?)\|(.*?)-->', fig_html, frag, flags=re.S)
frag=re.sub(r'`([^`]+)`', r'<code>\1</code>', frag)
# split into intro + sections
parts=re.split(r'<h2 id="[^"]*">(.*?)</h2>', frag)
intro, secs = parts[0], list(zip(parts[1::2], parts[2::2]))
def style(h):
    h=re.sub(r'<p>', f'<p class="body-p" style="font-size:13.5px;color:{TXT};line-height:1.75;margin-bottom:16px">', h)
    h=re.sub(r'<code>', f'<code style=\'{MONO}font-size:12px;background:{CODEBG};border:1px solid {RULE};padding:0 4px;color:{INK};white-space:nowrap\'>', h)
    # numbered list -> phase rows
    def ol(m):
        items=re.findall(r'<li>(.*?)</li>', m.group(0), flags=re.S); rows=[]
        for i,it in enumerate(items,1):
            t,_,rest=it.partition('. ')
            rows.append(f'<div class="phase-row" style="display:flex;gap:16px;padding:14px 0;border-bottom:1px solid {RULE}"><div class="phase-num" style=\'{SERIF}font-size:26px;font-weight:700;color:{RED};line-height:1;min-width:34px\'>{i:02d}</div><div class="phase-content"><div class="phase-title" style=\'{SERIF}font-size:15.5px;font-weight:600;color:{INK};margin-bottom:4px\'>{t}</div><div class="phase-desc" style="font-size:13.5px;color:{TXT};line-height:1.7">{rest}</div></div></div>')
        return f'<div class="phase-rows" style="border-top:1px solid {RULE};margin-bottom:24px">'+"".join(rows)+'</div>'
    h=re.sub(r'<ol[^>]*>.*?</ol>', ol, h, flags=re.S)
    h=re.sub(r'<ul>', '<ul class="fact-list" style="margin-bottom:22px;list-style:none;padding-left:0">', h)
    h=re.sub(r'<li>', f'<li class="li" style="position:relative;padding:5px 0 5px 20px;font-size:13.5px;color:{TXT};line-height:1.7"><span class="bullet" style="position:absolute;left:0;color:{RED}">&#9656;</span>', h)
    h=h.replace('<table>', '<table class="spec-table" style="width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:24px" width="100%">')
    h=re.sub(r'<thead>\s*<tr>', '<thead><tr style="border-bottom:2px solid #b5aca0">', h)
    h=re.sub(r'<th>', f'<th style=\'{MONO}font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{MUTE};padding:8px 10px;text-align:left;font-weight:500\' align="left">', h)
    h=re.sub(r'<tr>', f'<tr style="border-bottom:1px solid {RULE}">', h)
    h=re.sub(r'<td>', f'<td style="padding:9px 10px;vertical-align:top;line-height:1.55;font-size:13px;color:{TXT}" valign="top">', h)
    h=re.sub(r'<colgroup>.*?</colgroup>','',h,flags=re.S)
    h=re.sub(r'<a href="([^"]+)">', f'<a href="\\1" target="_blank" rel="noopener" style="color:{RED};text-decoration:none">', h)
    return h
intro=style(intro)
out_secs=[]
for n,(t,b) in enumerate(secs,1):
    out_secs.append(f'''  <section class="section-wrap" style="margin-bottom:52px;position:relative">
    <div class="section-header" style="position:relative;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid {RULE}">
      <div class="section-bg-num" style='position:absolute;top:-10px;right:0;{SERIF}font-size:80px;font-weight:700;color:{INK};opacity:0.05;line-height:1'>{n:02d}</div>
      <div class="section-eyebrow" style='{MONO}font-size:10px;letter-spacing:0.12em;color:{RED};text-transform:uppercase;margin-bottom:4px'>{n:02d} /</div>
      <h2 class="section-title" style='{SERIF}font-size:22px;font-weight:600;color:{INK};line-height:1.25'>{t}</h2>
    </div>
{style(b)}
  </section>''')
refs=[("Normalization and the Advanced Security Information Model (ASIM)","https://learn.microsoft.com/azure/sentinel/normalization"),
("Jupyter notebooks and the Microsoft Sentinel data lake","https://learn.microsoft.com/azure/sentinel/datalake/notebooks-overview"),
("Create and manage Jupyter notebook jobs","https://learn.microsoft.com/azure/sentinel/datalake/notebook-jobs"),
("Plan costs and understand Microsoft Sentinel pricing and billing","https://learn.microsoft.com/azure/sentinel/billing")]
reflis="".join(f'<li style="padding:6px 0;border-bottom:1px solid {RULE};font-size:12.5px;color:{TXT}"><a href="{u}" target="_blank" rel="noopener" style="color:{RED};text-decoration:none">{html.escape(t)}</a><span class="ref-src" style=\'{MONO}font-size:10px;color:{MUTE};margin-left:8px\'>Microsoft Learn</span></li>' for t,u in refs)
n=len(secs)+1
refsec=f'''  <section class="section-wrap" style="margin-bottom:52px;position:relative">
    <div class="section-header" style="position:relative;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid {RULE}">
      <div class="section-eyebrow" style='{MONO}font-size:10px;letter-spacing:0.12em;color:{RED};text-transform:uppercase;margin-bottom:4px'>{n:02d} /</div>
      <h2 class="section-title" style='{SERIF}font-size:22px;font-weight:600;color:{INK};line-height:1.25'>References</h2>
    </div>
    <ul class="ref-list" style="list-style:none;padding-left:0">{reflis}</ul>
  </section>'''
page=f'''<!-- wp:html -->
<div class="bleed" style="width:100%">
<main class="main" style="padding:8px 0 50px;background:#f5f0e8">
<div class="content-wrap" style="max-width:1400px;margin:0 auto">
  <div class="intro-wrap" style="border-bottom:1px solid {RULE};padding-bottom:36px;margin-bottom:44px">
    <h1 class="intro-title" style='{SERIF}font-size:28px;font-weight:700;color:{INK};line-height:1.25;margin-bottom:20px;letter-spacing:-0.3px'>{html.escape(title)}</h1>
    <div class="intro-body">
{intro}
    </div>
    <div class="intro-meta" style='{MONO}font-size:10px;color:{MUTE};border-top:1px solid {RULE};padding-top:16px;margin-top:8px;letter-spacing:0.05em'>DAVID BROGGY  &middot;  2026-10-26  &middot;  DEPLOYED IN A TEST TENANT</div>
  </div>
{chr(10).join(out_secs)}
{refsec}
  <footer class="footer" style='border-top:1px solid {RULE};padding:24px 0 0;margin-top:36px;text-align:center;{MONO}font-size:10px;color:{MUTE};letter-spacing:0.06em' align="center">FIELD NOTES  &middot;  TEST-TENANT DATA ONLY  &middot;  SIMPLE-SECURITY.CA</footer>
</div>
</main>
</div>
<!-- /wp:html -->'''
out.write_text(page,encoding='utf-8'); print(out, len(page), 'sections', len(secs))
