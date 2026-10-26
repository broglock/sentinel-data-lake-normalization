"""Record the Lake Hunt demo video and a GIF of the Hunt chapter from a fresh demo instance.

Run from the product folder:
    python tools/record_demo.py                 # docs/demo/lakehunt-demo.mp4 and docs/demo/lakehunt-hunt.gif
    python tools/record_demo.py --screenshots   # also refreshes docs/screenshots/
Needs: pip install -r requirements-dev.txt  and  python -m playwright install chromium
The demo instance runs on port 8090 with its own temporary database; other instances are not touched.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import imageio_ffmpeg  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui_flows import Flow, demo_server  # noqa: E402
from tools import demo_architecture  # noqa: E402

OUT = ROOT / "docs" / "demo"
SHOTS = ROOT / "docs" / "screenshots"
SIZE = {"width": 1440, "height": 900}

# Caption bar, visible cursor and click ring, injected into every page so they are part of the recording.
OVERLAY_JS = r"""
(() => {
  if (window.__lhOverlay) return; window.__lhOverlay = true;
  const css = `#lh-cap{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:1100px;background:rgba(5,5,47,.93);color:#fff;
    font:600 22px/1.35 Arial,sans-serif;padding:14px 26px;border-radius:12px;z-index:2147483646;box-shadow:0 8px 30px rgba(0,0,0,.35);border-left:6px solid #CAFF00}
  #lh-cap:empty{display:none}
  #lh-cur{position:fixed;left:0;top:0;width:24px;height:24px;z-index:2147483647;pointer-events:none;
    background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24'><path d='M3 2l7 19 2.6-7.6L20 11z' fill='white' stroke='%2305052F' stroke-width='1.6' stroke-linejoin='round'/></svg>") no-repeat}
  .lh-ring{position:fixed;width:38px;height:38px;margin:-19px 0 0 -19px;border:3px solid #33A7FF;border-radius:50%;z-index:2147483645;pointer-events:none;animation:lhr .5s ease-out forwards}
  @keyframes lhr{from{transform:scale(.3);opacity:1}to{transform:scale(1.5);opacity:0}}`;
  const put = (x, y) => { const c = document.getElementById("lh-cur"); if (c) { c.style.left = x + "px"; c.style.top = y + "px"; } };
  const add = () => {
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
    const cap = document.createElement("div"); cap.id = "lh-cap"; cap.textContent = sessionStorage.getItem("lh-cap") || ""; document.body.appendChild(cap);
    const cur = document.createElement("div"); cur.id = "lh-cur"; document.body.appendChild(cur);
    const [x, y] = (sessionStorage.getItem("lh-pos") || "720,450").split(",").map(Number); put(x, y);
  };
  if (document.body) add(); else document.addEventListener("DOMContentLoaded", add);
  document.addEventListener("mousemove", (e) => { put(e.clientX, e.clientY); sessionStorage.setItem("lh-pos", e.clientX + "," + e.clientY); }, true);
  document.addEventListener("mousedown", (e) => { const r = document.createElement("div"); r.className = "lh-ring"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px"; document.body.appendChild(r); setTimeout(() => r.remove(), 600); }, true);
  window.__lhCaption = (t) => { sessionStorage.setItem("lh-cap", t || ""); const c = document.getElementById("lh-cap"); if (c) c.textContent = t || ""; };
})();
"""


def title_card(page, title: str, lines: list[str]) -> None:
    rows = "".join(f"<p>{x}</p>" for x in lines)
    page.set_content(f"""<html><body style="margin:0;height:100vh;display:flex;flex-direction:column;justify-content:center;
      padding:0 120px;background:#05052F;color:#fff;font-family:Arial,sans-serif">
      <div style="display:flex;gap:4px;transform:skewX(-20deg);margin-bottom:28px"><i style="width:12px;height:56px;background:#00AAFF"></i>
      <i style="width:12px;height:56px;background:#001AFF"></i><i style="width:12px;height:56px;background:#D5FE51"></i></div>
      <h1 style="font-size:56px;margin:0 0 18px">{title}</h1>
      <div style="font-size:26px;color:#C9CCE6;line-height:1.5">{rows}</div></body></html>""")


def record() -> tuple[Path, tuple[float, float]]:
    vids = Path(tempfile.mkdtemp(prefix="lakehunt-video-"))
    with demo_server(8090) as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport=SIZE, record_video_dir=str(vids), record_video_size=SIZE)
        ctx.add_init_script(OVERLAY_JS)
        t0 = time.monotonic()
        page = ctx.new_page()
        f = Flow(page, base, animate=True, pace=1.6)   # long enough to read each caption
        mark = lambda: time.monotonic() - t0  # noqa: E731

        title_card(page, "LevelBlue Lake Hunt", ["One search across every Sentinel data lake source.",
                                                 "A walk through the three jobs, for the admins who run it."])
        page.wait_for_timeout(5000)
        demo_architecture.play(page, f)                 # chapter 0: the building blocks and the daily scan
        f.as_role("analyst")
        f.home_tour()                                   # chapter 1: Home
        f.onboard_badge_reader()                        # chapter 2: Onboard (analyst)
        f.as_role("admin")
        f.say("Now the Admin.")
        f.approve_pending("BadgeReader_CL")             # chapter 3: Approve (admin)
        f.click(page.locator("#nav details.nav-more > summary"))
        f.click(page.locator('#nav a[data-nav="admin"]'))
        audit = page.locator("#main tr", has_text="approv").first
        audit.wait_for()
        audit.scroll_into_view_if_needed()
        f.say("The audit log records who approved what, and when.")
        f.wait(5)
        f.as_role("analyst")
        f.deploy_and_validate("BadgeReader_CL")         # chapter 4: Deploy and validate
        hunt_start = mark()
        f.hunt_story()                                  # chapter 5: Hunt
        hunt_end = mark()
        f.say("")
        title_card(page, "What the admin controls", [
            "Every mapping and workspace change waits for an Admin and is written to the audit log.",
            "AI agents can draft mappings; they cannot approve them.",
            "Demo data is synthetic: contoso.com names and documentation IP ranges."])
        page.wait_for_timeout(8000)
        video = Path(page.video.path())
        ctx.close()
        browser.close()
    return video, (max(0.0, hunt_start - 0.5), hunt_end + 0.5)


def convert(webm: Path, hunt: tuple[float, float]) -> None:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-movflags", "+faststart", str(OUT / "lakehunt-demo.mp4")], check=True)
    start, end = hunt
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", str(webm),
                    "-vf", "fps=8,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer",
                    str(OUT / "lakehunt-hunt.gif")], check=True)


def screenshots() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*.png"):
        old.unlink()
    with demo_server() as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=SIZE)
        f = Flow(page, base)
        shot = lambda name: page.screenshot(path=str(SHOTS / name))  # noqa: E731
        f.as_role("admin")
        f.goto("home"); shot("01-home.png")
        f.open_onboarding("BadgeReader_CL")
        page.locator('.frow[data-row="RawData.holder"] [data-change]').click(); shot("02-onboard-fields.png")
        f.decide_all_fields()
        page.locator("#toPreview").click(); page.wait_for_selector("#pv .kpi"); shot("03-preview.png")
        page.locator("#submit").click(); page.locator("#main h2", has_text="Waiting for an Admin").wait_for()
        f.goto("approve"); page.locator("text=becomes searchable with roles").wait_for(); shot("05-approve.png")
        f.approve_pending("BadgeReader_CL")
        f.deploy_and_validate("BadgeReader_CL"); shot("06-validate.png")
        f.hunt("203.0.113.45"); shot("04-hunt.png")
        f.goto("coverage"); shot("07-coverage.png")
        page.evaluate("() => localStorage.setItem('lh.theme', 'dark')")
        f.goto("hunt/203.0.113.45"); page.reload(); page.wait_for_selector("#hsum"); shot("08-hunt-dark.png")
        browser.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--screenshots", action="store_true", help="also refresh docs/screenshots/")
    ap.add_argument("--keep-webm", action="store_true", help="keep the raw WebM next to the MP4")
    a = ap.parse_args()
    webm, hunt = record()
    convert(webm, hunt)
    if a.keep_webm:
        shutil.copy(webm, OUT / "lakehunt-demo.webm")
    print(f"Wrote {OUT / 'lakehunt-demo.mp4'} and {OUT / 'lakehunt-hunt.gif'}")
    if a.screenshots:
        screenshots()
        print(f"Refreshed {SHOTS}")


if __name__ == "__main__":
    main()
