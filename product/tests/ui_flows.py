"""Browser flows shared by the UI tests (tests/test_ui.py) and the demo recorder (tools/record_demo.py).

In tests, Flow runs fast and silent. The recorder passes animate=True: the cursor glides to each target,
text is typed key by key, and say() shows a caption. Captions belong to the flows so the video always
follows the tested path.
"""
from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def demo_server(port: int | None = None):
    """Start a fresh demo instance with its own temporary database; yield its base URL."""
    port = port or free_port()
    env = {**os.environ, "LAKEHUNT_MODE": "demo", "LAKEHUNT_AUTH": "none",
           "LAKEHUNT_DATA_DIR": tempfile.mkdtemp(prefix="lakehunt-ui-")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port),
                             "--log-level", "warning"], cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 60
        while True:
            try:
                urllib.request.urlopen(base + "/healthz", timeout=2)
                break
            except OSError:
                if proc.poll() is not None or time.time() > deadline:
                    raise RuntimeError("Lake Hunt did not start on " + base)
                time.sleep(0.3)
        yield base
    finally:
        proc.terminate()
        proc.wait(10)


class Flow:
    def __init__(self, page, base: str, animate: bool = False, pace: float = 1.0):
        self.page, self.base, self.animate, self.pace = page, base, animate, pace

    # ---- primitives
    def say(self, text: str) -> None:
        if self.animate:
            self.page.evaluate("t => window.__lhCaption && window.__lhCaption(t)", text)

    def wait(self, seconds: float) -> None:
        if self.animate:
            self.page.wait_for_timeout(int(seconds * 1000 * self.pace))

    def click(self, locator) -> None:
        locator.scroll_into_view_if_needed()
        if self.animate:
            box = locator.bounding_box()
            if box:
                self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=25)
                self.page.wait_for_timeout(250)
        locator.click()

    def type(self, locator, text: str) -> None:
        self.click(locator)
        locator.fill("")
        if self.animate:
            locator.press_sequentially(text, delay=60)
        else:
            locator.fill(text)

    def goto(self, route: str) -> None:
        self.page.goto(f"{self.base}/#/{route}")
        self.page.wait_for_selector("#nav a")
        self.page.wait_for_selector("#main .loader", state="detached")

    def as_role(self, role: str) -> None:
        """Switch the demo role with the top-bar selector (the page reloads)."""
        if not self.page.url.startswith(self.base):
            self.goto("home")
        sel = self.page.locator("#demoRole")
        if sel.input_value() != role:
            if self.animate:
                self.click(sel)
            with self.page.expect_navigation():
                sel.select_option(role)
        self.page.wait_for_selector("#nav a")

    # ---- hunt
    def hunt(self, value: str) -> None:
        p = self.page
        if not p.url.split("#", 1)[-1].startswith("/hunt"):   # re-clicking the nav on Hunt re-renders and detaches #hv
            self.click(p.locator('#nav a[data-nav="hunt"]'))
            p.wait_for_selector("#hv")
        self.type(p.locator("#hv"), value)
        p.locator("#hv").press("Enter")
        p.wait_for_selector("#hsum, #hpick, #hnone")

    def open_raw(self) -> str:
        """Open the original log row of the first event; return the modal text and close it."""
        p = self.page
        self.click(p.locator("#htabs [data-tab=events]"))
        self.click(p.locator("#htab [data-pv]").first)
        pre = p.locator(".modal-raw pre").first
        pre.wait_for()
        text = pre.inner_text()
        self.wait(3)
        self.click(p.locator("[data-close]"))
        return text

    # ---- onboard
    def open_onboarding(self, table: str) -> None:
        p = self.page
        self.click(p.locator('#nav a[data-nav="onboard"]'))
        p.wait_for_selector("text=Needs a decision")
        self.click(p.locator(".att", has_text=table).get_by_role("link"))
        p.wait_for_selector("#preset")

    def decide_all_fields(self, show_change: str | None = None) -> None:
        """Optionally open one field's choices (for the video), then accept every remaining recommendation."""
        p = self.page
        if show_change and p.locator(f'.frow[data-row="{show_change}"] [data-change]').count():
            self.say("Each field comes with a recommendation and its evidence. Change opens the plain-language choices.")
            self.click(p.locator(f'.frow[data-row="{show_change}"] [data-change]'))
            self.wait(4)
            self.click(p.locator(f'.frow[data-row="{show_change}"] .frow-body [data-accept]'))
        if p.locator("#acceptHigh").count():
            self.say("High-confidence fields can be accepted in one click.")
            self.click(p.locator("#acceptHigh"))
            self.wait(2)
        for _ in range(50):
            acc = p.locator(".frow:not(.accepted):not(.skipped) :is([data-accept], [data-taccept])").first
            if not acc.count():
                return
            self.click(acc)
        raise AssertionError("fields still undecided after 50 accepts")

    def preview_and_submit(self) -> None:
        p = self.page
        self.click(p.locator("#toPreview"))
        p.wait_for_selector("#pv .kpi")
        self.say("The preview runs the mapping on sample rows: rows with an entity and template match, against their targets.")
        self.wait(5)
        self.click(p.locator("#submit"))
        p.locator("#main h2", has_text="Waiting for an Admin").wait_for()   # not the toast, which says "waiting for an Admin" too
        self.say("Submitted. Nothing is live until an Admin approves it.")
        self.wait(4)

    def onboard_badge_reader(self) -> None:
        self.say("An analyst onboards a new source: a badge reader nobody has reviewed yet.")
        self.open_onboarding("BadgeReader_CL")
        self.wait(2)
        self.say("Pick the kind of source; it sets sensible defaults. No ASIM field names to type.")
        self.wait(3)
        self.decide_all_fields(show_change="RawData.holder")
        self.preview_and_submit()

    # ---- approve
    def approve_pending(self, text: str) -> None:
        p = self.page
        self.click(p.locator('#nav a[data-nav="approve"]'))
        card = p.locator("section.approval", has_text=text).first
        card.wait_for()
        card.locator("text=becomes searchable with roles").wait_for()
        self.say("The Admin sees what the change does in plain words, with the preview numbers. Details stay folded.")
        self.wait(6)
        self.click(card.locator("[data-ok]"))
        p.wait_for_selector("text=Approved #")
        self.say("Approved, and written to the audit log.")
        self.wait(3)

    def deploy_and_validate(self, table: str = "BadgeReader_CL") -> None:
        p = self.page
        self.click(p.locator('#nav a[data-nav="onboard"]'))
        self.click(p.locator(".att", has_text=table).get_by_role("link"))
        p.wait_for_selector("ol.stepper .step.now >> text=Deploy")
        self.say("Deploy shows only this source's job and the portal steps: the one manual step.")
        self.wait(5)
        self.click(p.locator("#next"))
        p.locator("[data-hc=yes]").first.wait_for()
        self.say("Three checks run on their own. The fourth needs a person: do the raw rows match the index?")
        self.wait(5)
        self.click(p.locator("[data-hc=yes]").first)
        p.wait_for_selector("text=all four passed")
        self.say("All four checks passed. The badge reader is live and searchable with roles.")
        self.wait(4)

    # ---- storyboard pieces used only by the recorder
    def home_tour(self) -> None:
        p = self.page
        self.goto("home")
        self.say("The daily scan found a new table, BadgeReader_CL. Home lists it with everything else that needs a person.")
        self.wait(4)
        row = p.locator(".att", has_text="BadgeReader_CL")
        row.scroll_into_view_if_needed()
        box = row.bounding_box()
        if box:
            p.mouse.move(box["x"] + 60, box["y"] + box["height"] / 2, steps=25)
        self.wait(4)

    def hunt_story(self) -> None:
        p = self.page
        self.say("One search for the suspicious IP, across every source in the lake.")
        self.hunt("203.0.113.45")
        self.wait(3)
        self.say("A password spray: failures across sign-in sources, then a success, then an AWS console sign-in from the same IP.")
        self.wait(7)
        self.click(p.locator("#htabs [data-tab=related]"))
        self.say("jsmith shows up in the same events. Hunt the user next.")
        self.wait(3)
        self.click(p.locator("#htab tr[data-hunt]", has_text="jsmith").first)
        p.wait_for_selector("#hsum")
        self.say("The badge reader onboarded a minute ago puts jsmith in the office minutes before the 'remote' sign-in.")
        self.wait(8)
        self.say("Every result goes back to the original log line.")
        self.open_raw()
