# Task-focused UI and recorded demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Lake Hunt web UI around three jobs (Hunt, Onboard a source, Review and approve), with detail collapsed. Then record a 3-minute demo video of it for customer admins.

**Architecture:**

- The 809-line `app/static/app.js` becomes plain ES modules under `app/static/js/` (no build step):
  - `core.js`: helpers, router, navigation.
  - `charts.js`
  - One module per job: `home.js`, `hunt.js`, `onboard.js` + `fields.js`, `approve.js`.
  - `more.js`: reference screens.
- The move is incremental. Task 1 moves the old screens unchanged into `legacy.js`. Each later task replaces one screen and adds a redirect from its old URL. Task 8 deletes `legacy.js`.
- The REST API, MCP and engine do not change.
- A Playwright flow library (`tests/ui_flows.py`) drives both the UI tests and the demo recorder, so the video follows the tested flows.

**Tech Stack:** plain JavaScript ES modules, CSS custom properties, FastAPI (unchanged), pytest, Playwright for Python (sync API, Chromium), ffmpeg from the `imageio-ffmpeg` pip package.

**Spec:** `docs/superpowers/specs/2026-10-24-task-focused-ui-and-demo-design.md`

## Global Constraints

- No build step and no new frontend dependencies: browsers load `/static/js/main.js` as `type="module"`.
- No change to `app/routers/*.py`, `app/core.py`, `app/engine/*`, `app/providers/*` or `deploy/*`.
- `python -m pytest tests`: all 18 existing tests pass unchanged after every task.
- Every screen has a page header (title, at most one sentence of subtitle, primary action on the right) and one primary action. YAML, KQL, evidence and raw JSON sit in collapsed `<details>` by default.
- Same LevelBlue palette and CSS tokens in `app/static/styles.css`. Lime is an accent only, never text on white.
- Navigation: Home · Hunt · Onboard · Approve (pending badge) · More. Viewer sees Home, Hunt and More (without Settings and audit). Analyst adds Onboard. Admin adds Approve and Settings and audit.
- Old URLs keep working:
  - `#/overview` → `#/home`
  - `#/sources` → `#/onboard`
  - `#/review/<table>` → `#/onboard/<table>/fields`
  - `#/validation/<group>` → `#/onboard/<table>/validate`
  - `#/approvals` → `#/approve`
- Preview targets: extraction 90%, template match 70%.
- Demo video: 1440×900, about 3 minutes, captions in the frame. Output: `docs/demo/lakehunt-demo.mp4` and `docs/demo/lakehunt-hunt.gif` (Hunt chapter, about 45 s). Recorded from a fresh demo instance on port 8090 with its own temporary data directory.
- Run every command from the product folder: `C:\Users\bob\OneDrive - LevelBlue\Documents\Claude\Projects\Sentinel Data Lake Normalization\product`. Use the venv Python `C:\Users\bob\AppData\Local\Temp\lhvenv\Scripts\python.exe` (Python 3.12, already has `requirements-dev.txt`). Below it is written as `PY`; in PowerShell set `$PY = "C:\Users\bob\AppData\Local\Temp\lhvenv\Scripts\python.exe"` and call `& $PY ...`.

## Review Focus

1. **Page reload in the middle of onboarding.** Field decisions live in browser memory. Reloading on the Preview step must still render a preview, built from the recommendations, rather than an error. Pinned by `test_preview_detail_collapsed_and_survives_reload` (Task 5).
2. **A Viewer opens a deep link to a screen they cannot use** (for example `#/onboard/BadgeReader_CL` or `#/approve`). Expected: a "needs the analyst/admin role" message, not a crash or a half-rendered form. Pinned by `test_viewer_nav_and_guard` (Task 2).
3. **Hunt values that contain `/` or that are lists.** A URL such as `http://example.com/a/b` must route and show "Not found", not break the router. A comma-separated list must become pick-one chips. Pinned by `test_hunt_url_value_routes` and `test_hunt_list_becomes_chips` (Task 3).
4. **Rejecting without a reason.** The requester needs to know what to change, so an empty reason must be refused, with a message and no reject call. Pinned by `test_reject_needs_reason` (Task 6).
5. **A table with several live groups** (CommonSecurityLog has FortiGate and Palo Alto). The Validate step must show one check card per group, not only the first. Pinned by `test_validate_shows_each_group` (Task 7).

---

### Task 0: Baseline under version control

The folder is not a git repository today. This task makes every later task reviewable and reversible.

**Files:**
- Check: `.gitignore` (already created on 2026-10-24 during the publish-readiness cleanup)

- [ ] **Step 1: Confirm `.gitignore` holds these lines (add any that are missing)**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
var/
tests/node_modules/
docs/demo/*.webm
```

- [ ] **Step 2: Initialise the repository and commit the baseline**

```bash
git init
git add -A
git commit -m "chore: baseline Lake Hunt 1.0.0 before UI restructure"
```

Expected: one commit; `git status` clean.

---

### Task 1: Split app.js into ES modules (no behavior change) and add the UI test harness

**Files:**
- Create: `app/static/js/core.js`, `app/static/js/charts.js`, `app/static/js/legacy.js`, `app/static/js/main.js`
- Create: `tests/ui_flows.py`, `tests/test_ui.py`
- Modify: `app/static/index.html` (script tag)
- Delete: `app/static/app.js`

**Interfaces:**
- Produces, from `core.js`: `$`, `$$`, `esc`, `pct`, `num`, `when`, `enc`, `ME`, `can(role)`, `demoRole()`, `api(path, opts)`, `toast(msg, err)`, `st(status, label)`, `tier(t)`, `layerTag(l)`, `modal(title, html, wide)`, `jsyaml(obj)`, `ROUTES`, `renderNav(active)`, `refreshPending()`, `router()`, `start()`.
- Produces, from `charts.js`: `barChart(items, opts)`, `spark(values, opts)`, `timelineChart(rows, width)`.
- Produces, from `tests/ui_flows.py`: `demo_server(port=None)` (a context manager that yields the base URL), and the class `Flow(page, base, animate=False)` with `goto(route)`, `as_role(role)`, `click(locator)`, `type(locator, text)`, `say(text)` and `wait(seconds)`.

- [ ] **Step 1: Install Chromium for Playwright (once per machine)**

Run: `PY -m playwright install chromium`
Expected: Chromium downloads into the Playwright cache under `%LOCALAPPDATA%\ms-playwright`.

- [ ] **Step 2: Write the flow library `tests/ui_flows.py`**

```python
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
    def __init__(self, page, base: str, animate: bool = False):
        self.page, self.base, self.animate = page, base, animate

    # ---- primitives
    def say(self, text: str) -> None:
        if self.animate:
            self.page.evaluate("t => window.__lhCaption && window.__lhCaption(t)", text)

    def wait(self, seconds: float) -> None:
        if self.animate:
            self.page.wait_for_timeout(int(seconds * 1000))

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
```

- [ ] **Step 3: Write the failing smoke test `tests/test_ui.py`**

```python
"""Browser tests for the web UI (Playwright, Chromium). Skipped when Chromium for Playwright is not installed:
    python -m playwright install chromium
Tests in this module share one demo instance and run in file order (the onboarding flow builds on itself).
"""
from __future__ import annotations

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from tests.ui_flows import Flow, demo_server  # noqa: E402


@pytest.fixture(scope="module")
def flow():
    with demo_server() as base, sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except sync_api.Error as e:
            pytest.skip(f"Chromium for Playwright is not installed: {e}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        f = Flow(page, base)
        f.errors = errors
        yield f
        browser.close()


def test_app_loads_from_modules(flow):
    flow.goto("coverage")
    assert flow.page.locator("#nav a").count() >= 5
    assert flow.page.locator("#main h1").first.is_visible()
    assert flow.page.locator("text=Something went wrong").count() == 0
    assert flow.errors == []
    assert flow.page.evaluate("() => !!document.querySelector('script[type=module][src=\"/static/js/main.js\"]')")
```

- [ ] **Step 4: Run it to make sure it fails**

Run: `PY -m pytest tests/test_ui.py -v`
Expected: FAIL at the `script[type=module]` assertion (the page still loads `app.js`).

- [ ] **Step 5: Create `app/static/js/charts.js`**

1. Open `app/static/app.js` and copy lines 64–138 verbatim: the `// ---- charts` comment through the end of `timelineChart`.
2. Put `export ` before `function barChart`, `function spark` and `function timelineChart`.
3. Put this line at the top of the file:

```js
import { esc, pct, when } from "./core.js";
```

- [ ] **Step 6: Create `app/static/js/core.js`**

1. Start the file with this comment:

```js
/* LevelBlue Lake Hunt web UI: shared helpers, router and navigation. Plain ES modules, no build step. */
```

2. Copy verbatim from `app.js`, in this order:
   - Lines 4–62: helpers through `modal`.
   - Lines 608–612: `jsyaml`.
   - Lines 140–187: navigation, `ROUTES`, `router`, `refreshPending`.
   - Lines 794–809: `start`.
3. Put `export ` before every top-level `const` and `function` **except** `LEVEL`, `tipEl`, `ICON` and `NAV`. That covers `$`, `$$`, `esc`, `pct`, `num`, `when`, `enc`, `ME`, `can`, `demoRole`, `api`, `toast`, `st`, `tier`, `layerTag`, `modal`, `jsyaml`, `renderNav`, `ROUTES`, `router` and `refreshPending`.
4. Leave `let pendingCount` unexported.
5. Delete the line `"use strict";` (modules are strict already).
6. Replace the self-invoking start, `(async function start() {` … `})();`, with a named export. Keep the body unchanged:

```js
export async function start() {
  // body of lines 796–808, unchanged
}
```

- [ ] **Step 7: Create `app/static/js/legacy.js` (old screens, moved unchanged; deleted in Task 8)**

1. Copy `app.js` lines 189–607, then lines 614–792, verbatim. That is overview through the end of `ROUTES.admin`, without `jsyaml`.
2. Put this at the top:

```js
/* Screens not yet restructured. Each later task moves one out; Task 8 deletes this file. */
import { ROUTES, $, $$, esc, pct, num, when, enc, ME, can, demoRole, api, toast, st, tier, layerTag, modal, jsyaml,
  renderNav, refreshPending, router } from "./core.js";
import { barChart, spark, timelineChart } from "./charts.js";
```

- [ ] **Step 8: Create `app/static/js/main.js`**

```js
/* Entry point: each module registers its screens in ROUTES, then the app starts. */
import { start } from "./core.js";
import "./legacy.js";

start();
```

- [ ] **Step 9: Load the module from `app/static/index.html` and delete `app.js`**

Replace `<script src="/static/app.js"></script>` with:

```html
<script type="module" src="/static/js/main.js"></script>
```

Then delete `app/static/app.js`.

- [ ] **Step 10: Run the UI test and the full suite**

Run: `PY -m pytest tests -v`
Expected: `test_app_loads_from_modules` PASSES; the 17 existing tests pass, with 1 skipped (Kusto).

- [ ] **Step 11: Check by hand that every old screen still renders**

Run `PY -m uvicorn app.main:app --port 8091` in the background. Open these and confirm each renders with no console errors: `http://localhost:8091/#/overview`, `#/hunt/203.0.113.45`, `#/sources`, `#/review/BadgeReader_CL`, `#/catalog`, `#/registry`, `#/validation`, `#/deploy`, `#/approvals`, `#/coverage`, `#/api`, `#/admin`. Stop the server.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor(ui): split app.js into ES modules; add Playwright UI harness"
```

---

### Task 2: Navigation, role guard, page parts, Home, More and About

**Files:**
- Modify: `app/static/js/core.js` (navigation section and `start`)
- Create: `app/static/js/home.js`, `app/static/js/onboard.js` (only `nextStep` and `stepHref` for now), `app/static/js/more.js` (only `more` and `about` for now)
- Modify: `app/static/js/main.js`, `app/static/js/legacy.js` (delete `ROUTES.overview`)
- Modify: `app/static/styles.css` (append the task-layout block)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: everything `core.js` produced in Task 1.
- Produces, in `core.js`:
  - `pageHeader(title, subHtml = "", actionsHtml = "")`: returns HTML. `title` is escaped; `subHtml` and `actionsHtml` are trusted HTML.
  - `disclose(summary, html, open = false)`: returns `<details class="more">`.
  - `NAV`, `MORE_NAV`: arrays of `[key, label, minRole]`; `MORE_NAV` rows add a 4th item, a description.
  - `ALIAS`: an object mapping an old page key to `(arg) => newHash` without the `#/`. Later tasks add entries.
- Produces, in `onboard.js`: `nextStep(tableRow)`, which returns `{ step, label, why, attention, href? }`, and `stepHref(tableRow, next)`, which returns a hash string.

- [ ] **Step 1: Write the failing tests (append to `tests/test_ui.py`)**

```python
def nav_keys(flow):
    return set(flow.page.locator("#nav a[data-nav]").evaluate_all("els => els.map(e => e.dataset.nav)"))


def test_home_shows_jobs_and_attention(flow):
    flow.as_role("admin")
    flow.goto("home")
    assert flow.page.locator(".task").count() == 3
    assert flow.page.locator(".att", has_text="BadgeReader_CL").count() == 1
    assert flow.page.locator("#nav a.on[data-nav=home]").count() == 1


def test_overview_link_redirects_to_home(flow):
    flow.page.goto(flow.base + "/#/overview")
    flow.page.wait_for_url("**/#/home")


def test_viewer_nav_and_guard(flow):
    flow.as_role("viewer")
    assert nav_keys(flow) == {"home", "hunt", "coverage", "registry", "catalog", "deploy", "api", "about"}
    flow.goto("home")
    assert flow.page.locator(".task").count() == 1          # Hunt only
    flow.goto("approve")
    assert flow.page.locator("text=needs the admin role").is_visible()
    flow.goto("admin")
    assert flow.page.locator("text=needs the admin role").is_visible()
    flow.as_role("admin")
    assert {"onboard", "approve", "admin"} <= nav_keys(flow)


def test_more_and_about(flow):
    flow.goto("more")
    assert flow.page.locator(".task", has_text="Coverage").count() == 1
    flow.goto("about")
    assert flow.page.locator("text=ASIM parser").first.is_visible()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `PY -m pytest tests/test_ui.py -v`
Expected: the four new tests FAIL (no `.task`, no `data-nav`, no `#/more`).

- [ ] **Step 3: Replace the navigation section of `core.js`**

In `core.js`, delete everything from `// ---- navigation` (the `ICON` constant) through the end of `refreshPending`. Put this in its place:

```js
// ------------------------------------------------------------------ page parts
export const pageHeader = (title, sub = "", actions = "") =>
  `<div class="ph"><div class="ph-text"><h1>${esc(title)}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}</div>${actions ? `<div class="ph-actions">${actions}</div>` : ""}</div>`;
export const disclose = (summary, html, open = false) =>
  `<details class="more"${open ? " open" : ""}><summary>${esc(summary)}</summary><div class="more-body">${html}</div></details>`;

// ------------------------------------------------------------------ navigation
const ICON = {
  home: '<path d="M2 9h5V2H2zm7 5h5V2H9zM2 14h5v-3H2z" fill="currentColor"/>',
  hunt: '<circle cx="7" cy="7" r="4.5" stroke="currentColor" fill="none" stroke-width="1.8"/><path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="2"/>',
  onboard: '<circle cx="8" cy="4" r="2.5" fill="currentColor"/><path d="M3 14c0-3 2.2-5 5-5s5 2 5 5z" fill="currentColor"/>',
  approve: '<path d="M2 8l4 4 8-9" stroke="currentColor" fill="none" stroke-width="2"/>',
  coverage: '<path d="M2 14V8h3v6zm4.5 0V4h3v10zM11 14V1h3v13z" fill="currentColor"/>',
  registry: '<path d="M3 2h10v12H3zM5 5h6M5 8h6M5 11h4" stroke="currentColor" fill="none" stroke-width="1.4"/>',
  catalog: '<path d="M2 3h12v2H2zm0 4h12v2H2zm0 4h8v2H2z" fill="currentColor"/>',
  deploy: '<path d="M8 1l5 5h-3v5H6V6H3zM2 13h12v2H2z" fill="currentColor"/>',
  api: '<path d="M5 4L1 8l4 4M11 4l4 4-4 4" stroke="currentColor" fill="none" stroke-width="1.6"/>',
  admin: '<circle cx="8" cy="8" r="2.5" fill="currentColor"/><path d="M8 1v2.5M8 12.5V15M1 8h2.5M12.5 8H15M3 3l1.8 1.8M11.2 11.2L13 13M3 13l1.8-1.8M11.2 4.8L13 3" stroke="currentColor" stroke-width="1.5"/>',
  about: '<circle cx="8" cy="8" r="6.5" stroke="currentColor" fill="none" stroke-width="1.4"/><path d="M8 7v4.5M8 4.5v.5" stroke="currentColor" stroke-width="1.8"/>',
};
export const NAV = [["home", "Home", "viewer"], ["hunt", "Hunt", "viewer"], ["onboard", "Onboard", "analyst"], ["approve", "Approve", "admin"]];
export const MORE_NAV = [
  ["coverage", "Coverage", "viewer", "Extraction rate per source, drift, and why a source drops."],
  ["registry", "Registry", "viewer", "Every mapping, its versions, and YAML export for Git."],
  ["catalog", "Connectors", "viewer", "The Content hub catalog: plan a connector's tables and tier."],
  ["deploy", "Build and deploy", "viewer", "All KQL jobs, notebook settings and the deployment bundle."],
  ["api", "API and agents", "viewer", "The REST API, the MCP endpoint and what agents may do."],
  ["admin", "Settings and audit", "admin", "Environment settings, roles and the audit log."],
  ["about", "About", "viewer", "Why an index: ASIM coverage across the content catalog."],
];
const ROUTE_ROLE = { more: "viewer", ...Object.fromEntries([...NAV, ...MORE_NAV].map(([k, , r]) => [k, r])) };
let pendingCount = 0;

export function renderNav(active) {
  const link = ([k, label]) => `<a href="#/${k}" data-nav="${k}" class="${active === k ? "on" : ""}"><svg viewBox="0 0 16 16">${ICON[k] || ""}</svg>${label}${k === "approve" && pendingCount ? `<span class="n">${pendingCount}</span>` : ""}</a>`;
  const visible = (items) => items.filter(([, , r]) => can(r));
  const moreOpen = active === "more" || MORE_NAV.some(([k]) => k === active);
  $("#nav").innerHTML = visible(NAV).map(link).join("") +
    `<details class="nav-more"${moreOpen ? " open" : ""}><summary>More</summary>${visible(MORE_NAV).map(link).join("")}</details>`;
}

export async function refreshPending() {
  try { pendingCount = can("admin") ? (await api("/approvals?status=pending")).length : 0; } catch { pendingCount = 0; }
}

export const ROUTES = {};
// Old links keep working: each old page key maps to its new hash (without "#/"). Later modules add entries.
export const ALIAS = { overview: () => "home" };

export async function router() {
  const hash = location.hash.replace(/^#\/?/, "") || "home";
  const [page, ...rest] = hash.split("/");
  const arg = rest.length ? decodeURIComponent(rest.join("/")) : null;
  if (ALIAS[page]) { location.replace("#/" + ALIAS[page](arg)); return; }
  const route = ROUTES[page] ? page : "home";
  renderNav(route);
  $("#nav").classList.remove("open");
  const main = $("#main");
  const need = ROUTE_ROLE[page] || ROUTE_ROLE[route];   // guard by the requested page, even before its module exists
  if (need && !can(need)) {
    main.innerHTML = pageHeader("Not available") +
      `<div class="card"><p>This screen needs the ${esc(need)} role. You are signed in as ${esc(ME.role)}.</p><a class="btn" href="#/home">Go to Home</a></div>`;
    return;
  }
  main.innerHTML = `<div class="loader">Loading…</div>`;
  try {
    await ROUTES[route](main, arg);
  } catch (e) {
    main.innerHTML = `<div class="card"><h2>Something went wrong</h2><p class="muted">${esc(e.message)}</p></div>`;
  }
  window.scrollTo(0, 0);
}
```

In `start()`, register the hash listener just before `router()`, because the old top-level `window.addEventListener("hashchange", router);` line was removed with the section above:

```js
  await refreshPending();
  window.addEventListener("hashchange", router);
  router();
```

- [ ] **Step 4: Create `app/static/js/onboard.js` (helpers used by Home; the screens follow in Task 4)**

```js
/* Onboard: one flow per source. Steps: pick → fields → preview → submit → deploy → validate. */
import { enc, pct } from "./core.js";

// The next action for a table, from its onboarding stage and coverage status.
export function nextStep(t) {
  const live = (t.groups || []).find((g) => g.status === "live");
  switch (t.stage) {
    case "detected":
    case "proposed":
      return { step: "fields", label: "Review fields", attention: true,
        why: t.status === "classifier-only" ? "Searchable by value only; fields not reviewed" : "New table; fields not reviewed" };
    case "in_review": return { step: "fields", label: "Continue review", why: "Field review in progress", attention: true };
    case "failed": return { step: "fields", label: "Back to review", why: "Validation found a problem", attention: true };
    case "registry": return { step: "submit", label: "View request", why: "Waiting for an Admin", attention: false };
    case "deployed": return { step: "deploy", label: "Deploy", why: "Approved; jobs to create", attention: true };
    case "validating": return { step: "validate", label: "Finish validation", why: "A check needs a person", attention: true };
    default:
      if (t.status === "review" && live) {
        return { step: "coverage", href: `#/coverage/${enc(live.id)}`, label: "Explain drop", attention: true,
          why: `Extraction ${pct(t.extraction)}, below the 90% target` };
      }
      return { step: "fields", label: "View mapping", why: "Live", attention: false };
  }
}

export const stepHref = (t, n) => n.href || `#/onboard/${enc(t.name)}/${n.step}`;
```

- [ ] **Step 5: Create `app/static/js/home.js`**

```js
/* Home: the three jobs and one list of what needs a person. */
import { ROUTES, $, api, esc, enc, can, pageHeader, st } from "./core.js";
import { nextStep, stepHref } from "./onboard.js";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

ROUTES.home = async (main) => {
  const [t, pend] = await Promise.all([
    can("analyst") ? api("/tables") : Promise.resolve({ tables: [] }),
    can("admin") ? api("/approvals?status=pending") : Promise.resolve([]),
  ]);
  const todo = t.tables.map((x) => ({ t: x, n: nextStep(x) })).filter((x) => x.n.attention);
  const review = todo.filter((x) => x.n.step === "fields").length;
  const rows = [
    ...pend.map((a) => `<div class="att"><div><b>#${a.id} ${esc(a.title)}</b><div class="small muted">Requested by ${esc(a.requested_by)}; waiting for an Admin</div></div><a class="btn sm primary" href="#/approve">Review</a></div>`),
    ...todo.map(({ t: x, n }) => `<div class="att"><div><b>${esc(x.name)}</b> ${st(x.status)}<div class="small muted">${esc(n.why)}</div></div><a class="btn sm" href="${stepHref(x, n)}">${esc(n.label)}</a></div>`),
  ];
  main.innerHTML = pageHeader("What do you want to do?") + `
    <div class="tasks">
      <div class="task"><h2>Hunt</h2><p class="muted">Search one IP, user, host, URL or hash across every source.</p>
        <form class="hero-search" id="hhome"><input type="search" id="hq" aria-label="Value to hunt" placeholder="203.0.113.45, CONTOSO\\jsmith, a host…"><button class="btn primary">Hunt</button></form></div>
      ${can("analyst") ? `<a class="task" href="#/onboard"><h2>Onboard a source</h2><p class="muted">Decide what each field holds, preview it, submit it.</p><span class="task-n">${review ? `${plural(review, "source")} need review` : "Nothing waiting"}</span></a>` : ""}
      ${can("admin") ? `<a class="task" href="#/approve"><h2>Review and approve</h2><p class="muted">Changes wait here before they reach the tenant.</p><span class="task-n">${pend.length ? `${plural(pend.length, "change")} waiting` : "Nothing waiting"}</span></a>` : ""}
    </div>
    ${can("analyst") ? `<section class="card section"><h2>Needs attention <span class="count">${rows.length}</span></h2>${rows.join("") || `<div class="empty">Nothing needs you right now.</div>`}</section>` : ""}`;
  $("#hhome").onsubmit = (e) => { e.preventDefault(); const v = $("#hq").value.trim(); if (v) location.hash = "#/hunt/" + enc(v); };
};
```

- [ ] **Step 6: Create `app/static/js/more.js` (More index and About; other screens move here in Task 8)**

```js
/* More: reference screens for setup and administration. */
import { ROUTES, api, esc, num, pct, can, pageHeader, MORE_NAV } from "./core.js";

ROUTES.more = async (main) => {
  main.innerHTML = pageHeader("More", "Reference screens for setup and administration.") +
    `<div class="tasks">${MORE_NAV.filter(([, , r]) => can(r)).map(([k, label, , d]) => `<a class="task" href="#/${k}"><h2>${esc(label)}</h2><p class="muted">${esc(d)}</p></a>`).join("")}</div>`;
};

ROUTES.about = async (main) => {
  const c = (await api("/overview")).catalog;
  main.innerHTML = pageHeader("Why an index", `From the Microsoft Sentinel content catalog (${esc(c.solutions)} solutions).`) + `
    <div class="card"><div class="grid g2">
      <div class="kpi"><span class="v">${num(c.tables)}</span><span class="l">tables written by ${num(c.connectors)} data connectors</span></div>
      <div class="kpi"><span class="v">${num(c.tablesWithAsim)}</span><span class="l">of those tables have an ASIM parser (${pct(c.tablesWithAsim / c.tables, 1)})</span></div></div>
      <div class="callout" style="margin-top:14px">ASIM parsers are stored functions and lake KQL does not run them. Lake Hunt applies ASIM logic where Microsoft ships it, registry rules and templates everywhere else, and a value classifier as the floor, so every table is searchable with one set of field names.</div></div>`;
};
```

- [ ] **Step 7: Register the modules and remove the old Overview**

In `main.js`, import the new modules **before** `legacy.js`:

```js
import { start } from "./core.js";
import "./home.js";
import "./onboard.js";
import "./more.js";
import "./legacy.js";

start();
```

In `legacy.js`, delete the whole `ROUTES.overview = async (main) => { … };` block, including its `// ---- overview` comment.

- [ ] **Step 8: Append the task-layout CSS to `app/static/styles.css`**

Put this block before the first `@media (max-width: 1100px)` line:

```css
/* ---- task-focused layout */
.ph { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 18px; }
.ph-text { flex: 1; min-width: 0; }
.ph .sub { margin: 0; }
.ph-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.tasks { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.task { display: flex; flex-direction: column; gap: 6px; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 18px 20px; box-shadow: var(--shadow); color: var(--ink); }
a.task:hover { border-color: var(--blue); text-decoration: none; }
.task h2 { margin: 0; }
.task p { margin: 0 0 6px; }
.task-n { margin-top: auto; font-weight: 700; color: var(--link); }
.section { margin-top: 16px; }
.count { font-size: 12px; font-weight: 700; color: var(--ink-3); background: var(--surface-2); border-radius: 99px; padding: 1px 8px; }
.att { display: flex; gap: 12px; align-items: center; justify-content: space-between; padding: 10px 0; border-top: 1px solid var(--rule); }
.card h2 + .att, .more-body > .att:first-child { border-top: 0; }
details.more { margin-top: 16px; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); }
details.more > summary { cursor: pointer; padding: 12px 18px; font-weight: 700; color: var(--ink-2); }
details.more > .more-body { padding: 0 18px 16px; }
.card details.more { border: 0; background: none; margin-top: 12px; }
.card details.more > summary { padding: 6px 0; }
.card details.more > .more-body { padding: 0; }
nav.side details.nav-more > summary { cursor: pointer; list-style: none; font-size: 11px; text-transform: uppercase; letter-spacing: .6px; color: var(--ink-3); margin: 18px 10px 6px; }
nav.side details.nav-more > summary::-webkit-details-marker { display: none; }
nav.side details.nav-more > summary::after { content: " ▾"; }
nav.side details.nav-more[open] > summary::after { content: " ▴"; }
```

In the existing `@media (max-width: 760px)` block, add:

```css
  .ph { flex-direction: column; }
  .att { flex-wrap: wrap; }
```

- [ ] **Step 9: Run the UI tests and the full suite**

Run: `PY -m pytest tests -v`
Expected: all UI tests PASS; the existing tests pass, with 1 skipped.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(ui): task navigation with role guard, Home, More and About"
```

---

### Task 3: Hunt

**Files:**
- Create: `app/static/js/hunt.js`
- Modify: `app/static/js/main.js` (import), `app/static/js/legacy.js` (delete `ROUTES.hunt`), `app/static/styles.css`
- Modify: `tests/ui_flows.py` (add `hunt`, `open_raw`), `tests/test_ui.py`

**Interfaces:**
- Consumes: from `core.js`, `ROUTES`, `$`, `$$`, `api`, `esc`, `num`, `when`, `enc`, `ME`, `st`, `tier`, `modal` and `pageHeader`; from `charts.js`, `timelineChart`.
- Produces: `splitValues(text)`, which returns a deduplicated `string[]` (split on commas, semicolons and line breaks, trimmed). `Flow.hunt(value)` and `Flow.open_raw()` in `ui_flows.py`.

- [ ] **Step 1: Add the Hunt flows to `Flow` in `tests/ui_flows.py`**

```python
    # ---- hunt
    def hunt(self, value: str) -> None:
        p = self.page
        self.click(p.locator('#nav a[data-nav="hunt"]'))
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
```

- [ ] **Step 2: Write the failing tests (append to `tests/test_ui.py`)**

```python
def test_hunt_shows_summary_tabs_and_raw_row(flow):
    flow.as_role("analyst")
    flow.hunt("203.0.113.45")
    summary = flow.page.locator("#hsum").inner_text()
    assert summary.startswith("Seen in ")
    assert int(summary.split()[2]) >= 3                     # "Seen in N sources …"
    assert flow.page.locator(".kpi").count() == 0           # no KPI tiles on Hunt any more
    assert "203.0.113.45" in flow.open_raw()


def test_hunt_list_becomes_chips(flow):
    flow.hunt("203.0.113.45, jsmith@contoso.com")
    assert flow.page.locator("text=Hunt one value at a time").is_visible()
    assert flow.page.locator("#hpick [data-pick]").count() == 2
    flow.click(flow.page.locator("#hpick [data-pick]").nth(1))
    flow.page.wait_for_selector("#hsum")
    assert flow.page.url.endswith("#/hunt/jsmith%40contoso.com")


def test_hunt_url_value_routes(flow):
    flow.hunt("http://example.com/a/b")
    assert flow.page.locator("#hnone").is_visible()
    assert flow.page.locator("text=Something went wrong").count() == 0
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `PY -m pytest tests/test_ui.py -v -k hunt`
Expected: FAIL (no `#hsum`, `#hpick` or `#hnone` in the old screen).

- [ ] **Step 4: Create `app/static/js/hunt.js`**

```js
/* Hunt: one value across every indexed source. */
import { ROUTES, $, $$, api, esc, num, when, enc, ME, st, tier, modal, pageHeader } from "./core.js";
import { timelineChart } from "./charts.js";

export const splitValues = (text) => [...new Set(String(text).split(/[,;\n]+/).map((x) => x.trim()).filter(Boolean))];

const EXAMPLES = [["203.0.113.45", "suspicious IP"], ["CONTOSO\\jsmith", "user, Windows format"], ["jsmith@contoso.com", "user, UPN"],
  ["198.51.100.7", "outbound destination"], ["WS-0412", "workstation"]];
const result = (r) => st(r === "Success" ? "ok" : r === "Failure" ? "fail" : "info", r || "–");
const rawBtn = (p) => `<button class="btn sm" data-pv='${esc(JSON.stringify(p))}'>Raw</button>`;

ROUTES.hunt = async (main, q) => {
  main.innerHTML = pageHeader("Hunt", "One value across every indexed source, back to the original log line.") + `
    <div class="card"><div class="hero-search"><input type="search" id="hv" aria-label="Value to hunt" placeholder="An IP, DOMAIN\\user, user@domain, host, URL or hash" value="${esc(q || "")}">
      <select id="hd" aria-label="Period"><option value="1">24 hours</option><option value="3">3 days</option><option value="7" selected>7 days</option><option value="30">30 days</option></select>
      <button class="btn primary" id="hgo">Hunt</button></div>
      ${ME.mode === "demo" ? `<div class="row small" style="margin-top:10px"><span class="muted">Try:</span>${EXAMPLES.map(([v, l]) => `<button class="btn sm ghost" data-ex="${esc(v)}" title="${esc(l)}">${esc(v)}</button>`).join("")}</div>` : ""}</div>
    <div id="hres" class="section"></div>`;
  const out = $("#hres");

  const go = async (text) => {
    const vals = splitValues(text);
    if (!vals.length) return;
    if (vals.length > 1) {
      out.innerHTML = `<div class="card" id="hpick"><h2>Hunt one value at a time</h2><p class="muted">Pick the value to search first.</p>
        <div class="row">${vals.map((v) => `<button class="btn" data-pick="${esc(v)}">${esc(v)}</button>`).join("")}</div></div>`;
      $$("[data-pick]", out).forEach((b) => (b.onclick = () => { $("#hv").value = b.dataset.pick; go(b.dataset.pick); }));
      return;
    }
    const v = vals[0];
    history.replaceState(null, "", "#/hunt/" + enc(v));
    const days = $("#hd").value;
    out.innerHTML = `<div class="loader">Searching the index…</div>`;
    try {
      const [r, auth, net] = await Promise.all([api(`/hunt/value?v=${enc(v)}&days=${days}`), api(`/hunt/auth?user=${enc(v)}&days=${days}`), api(`/hunt/network?ip=${enc(v)}&days=${days}`)]);
      const srcs = r.sources;
      if (!srcs.length) {
        out.innerHTML = `<div class="card" id="hnone"><div class="empty">Not found in the index for this period. Try a longer period, or check <a href="#/coverage">Coverage</a> for sources that are searchable by value only.</div></div>`;
        return;
      }
      const events = srcs.reduce((a, s) => a + s.Events, 0);
      const fails = r.timeline.filter((t) => t.EventResult === "Failure").length, succ = r.timeline.filter((t) => t.EventResult === "Success").length;
      const short = v.toLowerCase().split("\\").pop().split("@")[0];
      const tabs = [
        ["where", "Where it appears", srcs.length, () => `<div class="tbl-wrap"><table><tr><th>Source</th><th>As</th><th>Roles</th><th>Results</th><th class="num">Events</th><th>Tier</th></tr>${srcs.map((s) => `<tr><td><b>${esc(s.SourceGroup)}</b><div class="small muted">${when(s.FirstSeen)} to ${when(s.LastSeen)}</div></td><td>${esc(s.EntityType)}</td><td>${s.Roles.map((x) => `<span class="tag">${esc(x)}</span>`).join("")}</td><td>${s.Results.map(result).join(" ")}</td><td class="num">${num(s.Events)}</td><td>${s.Tiers.map(tier).join("")}</td></tr>`).join("")}</table></div>`],
        ["events", "Events", r.timeline.length, () => `<div class="tbl-wrap"><table><tr><th>Time</th><th>Source</th><th>Event</th><th>Matched as</th><th>Other entities</th><th></th></tr>${r.timeline.slice(0, 200).map((t) => `<tr><td>${when(t.EventStartTime)}</td><td>${esc(t.SourceGroup)}</td><td>${esc(t.EventType || "–")} ${t.EventResult ? result(t.EventResult) : ""}</td><td><span class="tag">${esc(t.MatchedAs)}</span></td><td class="small">${t.Entities.filter((e) => !e.toLowerCase().includes(short)).slice(0, 4).map(esc).join("<br>")}</td><td>${rawBtn({ table: t.SourceTable, time: t.EventStartTime, value: v, key: t.SourceRecordKey, group: t.SourceGroup })}</td></tr>`).join("")}</table></div>`],
        ["auth", "Sign-ins", auth.length, () => `<div class="tbl-wrap"><table><tr><th>Time</th><th>Source</th><th>Result</th><th>User as logged</th><th>From IP</th><th></th></tr>${auth.slice(0, 50).map((a) => `<tr><td>${when(a.EventStartTime)}</td><td>${esc(a.SourceGroup)}</td><td>${result(a.EventResult)}</td><td class="mono">${esc(a.User)}</td><td>${a.SrcIpAddr ? `<a href="#/hunt/${enc(a.SrcIpAddr)}">${esc(a.SrcIpAddr)}</a>` : "–"}</td><td>${rawBtn({ table: a.SourceTable, time: a.EventStartTime, value: a.User, key: a.SourceRecordKey, group: a.SourceGroup })}</td></tr>`).join("")}</table></div>`],
        ["net", "Network sessions", net.length, () => `<div class="tbl-wrap"><table><tr><th>Source</th><th>From</th><th>To</th><th class="num">Port</th><th>Action</th><th class="num">Sessions</th></tr>${net.map((n) => `<tr><td>${esc(n.SourceGroup)}</td><td>${esc(n.SrcIpAddr)}</td><td>${esc(n.DstIpAddr)}</td><td class="num">${esc(n.DstPortNumber ?? "")}</td><td>${n.Actions.map(esc).join(", ")}</td><td class="num">${n.Sessions}</td></tr>`).join("")}</table></div>`],
        ["related", "Seen with it", r.related.length, () => `<p class="small muted">Entities in the same events. Pick one to hunt it next.</p><div class="tbl-wrap"><table><tr><th>Entity</th><th>Roles</th><th class="num">Sources</th><th class="num">Events</th></tr>${r.related.map((x) => `<tr class="click" data-hunt="${esc(x.Value)}"><td><span class="tag">${esc(x.EntityType)}</span> <b>${esc(x.Value)}</b></td><td>${x.Roles.map(esc).join(", ")}</td><td class="num">${x.Sources.length}</td><td class="num">${x.Events}</td></tr>`).join("")}</table></div>`],
      ].filter(([k, , n]) => k === "where" || n > 0);
      out.innerHTML = `<p class="summary" id="hsum">Seen in <b>${srcs.length}</b> source${srcs.length === 1 ? "" : "s"} · <b>${num(events)}</b> event${events === 1 ? "" : "s"} · <b>${fails}</b> failure${fails === 1 ? "" : "s"}, <b>${succ}</b> success${succ === 1 ? "" : "es"}</p>
        <div class="card"><h2>Timeline</h2>${timelineChart(r.timeline)}</div>
        <div class="card section"><div class="tabs" id="htabs">${tabs.map(([k, l, n], i) => `<button data-tab="${k}" class="${i ? "" : "on"}">${l} <span class="count">${n}</span></button>`).join("")}</div><div id="htab"></div></div>`;
      const show = (k) => {
        $$("#htabs [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === k));
        $("#htab").innerHTML = tabs.find(([x]) => x === k)[3]();
        $$("[data-hunt]", $("#htab")).forEach((x) => (x.onclick = () => { $("#hv").value = x.dataset.hunt; go(x.dataset.hunt); }));
        $$("[data-pv]", $("#htab")).forEach((x) => (x.onclick = async () => {
          const p = JSON.parse(x.dataset.pv);
          const rows = await api(`/hunt/pivot?table=${enc(p.table)}&time=${enc(p.time)}&value=${enc(p.value)}&key=${enc(p.key)}&group=${enc(p.group)}`);
          modal(`Original row in ${p.table}`, `<div class="modal-raw">${rows.length ? rows.map((row) => `<pre>${esc(JSON.stringify(row, null, 2))}</pre>`).join("<br>") : `<div class="empty">No raw row found</div>`}</div>`);
        }));
      };
      $$("#htabs [data-tab]").forEach((b) => (b.onclick = () => show(b.dataset.tab)));
      show("where");
    } catch (e) { out.innerHTML = `<div class="callout warn">${esc(e.message)}</div>`; }
  };

  $("#hgo").onclick = () => go($("#hv").value);
  $("#hv").addEventListener("keydown", (e) => { if (e.key === "Enter") go($("#hv").value); });
  $$("[data-ex]").forEach((b) => (b.onclick = () => { $("#hv").value = b.dataset.ex; go(b.dataset.ex); }));
  if (q) go(q);
};
```

- [ ] **Step 5: Wire it in**

- In `main.js`, add `import "./hunt.js";` after `import "./home.js";`.
- In `legacy.js`, delete the `ROUTES.hunt = …` block and its `// ---- hunt` comment.
- Append to the task-layout CSS block in `styles.css`:

```css
.summary { font-size: 16px; margin: 0 0 14px; color: var(--ink-2); }
.summary b { color: var(--ink); }
.tabs .count { margin-left: 4px; }
```

- [ ] **Step 6: Run the tests**

Run: `PY -m pytest tests -v`
Expected: all PASS (1 skipped).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(ui): focused Hunt with summary line, tabs and pick-one chips"
```

---

### Task 4: Onboard landing, stepper and the Decide fields step

**Files:**
- Modify: `app/static/js/onboard.js` (landing, stepper, step dispatch, aliases)
- Create: `app/static/js/fields.js` (decision state, Decide fields step)
- Modify: `app/static/js/main.js`, `app/static/js/legacy.js` (delete `ROUTES.sources`, `EFFECT` and `ROUTES.review`), `app/static/styles.css`
- Modify: `tests/ui_flows.py` (`open_onboarding`, `decide_all_fields`), `tests/test_ui.py`

**Interfaces:**
- Consumes: `nextStep`, `stepHref` (Task 2); `pageHeader`, `disclose`, `ALIAS` (Task 2).
- Produces:
  - In `fields.js`:
    - `getState(table)`: returns `Promise<ctx>`, where `ctx = { table, P, S }`; it is cached per table in memory.
    - `decisionsPayload(ctx)`: returns the decisions object `POST /registry/from-decisions` expects.
    - `renderFields(main, table, head)`.
  - In `onboard.js`: `STEPS` (an array of `[key, label]`) and `stepper(table, current, stage)` (returns HTML).
  - Step keys: `fields`, `preview`, `submit`, `deploy`, `validate`. Tasks 5 and 7 register their renderers in `STEP_VIEWS`, which `onboard.js` exports.

- [ ] **Step 1: Add the onboarding flows to `Flow` in `tests/ui_flows.py`**

```python
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
```

- [ ] **Step 2: Write the failing tests (append to `tests/test_ui.py`)**

```python
def test_onboard_landing_and_old_links(flow):
    flow.as_role("analyst")
    flow.goto("onboard")
    assert flow.page.locator("section", has_text="Needs a decision").locator(".att", has_text="BadgeReader_CL").count() == 1
    flow.page.goto(flow.base + "/#/sources")
    flow.page.wait_for_url("**/#/onboard")
    flow.page.goto(flow.base + "/#/review/BadgeReader_CL")
    flow.page.wait_for_url("**/#/onboard/BadgeReader_CL/fields")


def test_fields_are_one_line_rows_until_changed(flow):
    flow.open_onboarding("BadgeReader_CL")
    p = flow.page
    assert p.locator("ol.stepper .step.now", has_text="Decide fields").count() == 1
    assert p.locator(".frow").count() >= 3
    assert p.locator(".frow-body").count() == 0                       # nothing expanded by default
    flow.click(p.locator('.frow[data-row="RawData.holder"] [data-change]'))
    assert p.locator('.frow[data-row="RawData.holder"] .frow-body .choice').count() >= 4
    flow.decide_all_fields()
    assert p.locator(".frow:not(.accepted):not(.skipped)").count() == 0
    assert p.locator("text=Every field is decided").is_visible()
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `PY -m pytest tests/test_ui.py -v -k "onboard or fields"`
Expected: FAIL (no `#/onboard` route; the aliases are missing).

- [ ] **Step 4: Create `app/static/js/fields.js`**

```js
/* Onboard step 2 (Decide fields): one row per field with the recommendation; Change opens the choices.
   Decisions are kept in memory per table so steps 2 and 3 share them. */
import { $, $$, api, esc, pct, num, enc, st, modal, toast, disclose } from "./core.js";

export const EFFECT = {
  "ip:Src": "Hunters see it as the source IP; sign-in and network views use it as SrcIpAddr.",
  "ip:Dst": "Network views use it as the destination (DstIpAddr).",
  "ip:Dvc": "Recorded as the reporting device's address (DvcIpAddr).",
  "ip:Unknown": "Found by hunt_value, but no direction is claimed.",
  "user:Target": "Sign-in views list it as the account signing in (TargetUsername).",
  "user:Actor": "Audit views list it as who did it (ActorUsername).",
  "user:Src": "Network views list it as the user behind the traffic (SrcUsername).",
  "user:Unknown": "Found by hunt_value, but no role is claimed.",
  "host:Dvc": "Recorded as the device that wrote the log (DvcHostname).",
  "host:Src": "Recorded as the source machine (SrcHostname).",
  "host:Dst": "Recorded as the destination machine (DstHostname).",
};

const STATE = new Map();

function initDecisions(ctx) {
  const { P, S } = ctx;
  S.dec = {}; S.tpl = {}; S.open = {}; S.topen = {};
  P.cards.forEach((c) => {
    const rec = c.recommended || {};
    const base = { accepted: false, kind: c.kind, use: c.decision };
    if (c.decision === "entity") Object.assign(base, { entity: rec.entity, role: rec.role, asim: rec.asim });
    if (c.decision === "field") Object.assign(base, { asim: rec.asim });
    if (c.decision === "result") base.map = Object.fromEntries((c.values || []).map((v) => [v.value, v.suggested]));
    if (c.decision === "event_type") base.map = Object.fromEntries((c.values || []).map((v) => [v.value, ""]));
    if (c.decision === "skip") base.accepted = true;
    S.dec[c.field] = base;
  });
  (P.templates || []).forEach((t, i) => {
    S.tpl[i] = { include: t.share >= 0.02, outcome: t.outcomeSuggested || "", eventType: t.eventTypeSuggested || "", regex: t.suggestedRegex, match: t.suggestedMatch,
      slots: Object.fromEntries(t.slots.map((s) => [s.slot, { ...s.recommended, name: "" }])), accepted: false };
  });
}

export async function getState(table, preset = null) {
  if (!preset && STATE.has(table)) return STATE.get(table);
  const P = await api(`/tables/${enc(table)}/proposals${preset ? `?preset=${enc(preset)}` : ""}`);
  const prev = STATE.get(table);
  const ctx = { table, P, S: { meta: prev ? prev.S.meta : { id: `${table}:main`, vendor: "", product: "" } } };
  initDecisions(ctx);
  STATE.set(table, ctx);
  return ctx;
}

export function decisionsPayload({ P, S }) {
  const fields = [], d = { id: S.meta.id, preset: P.preset, vendor: S.meta.vendor, product: S.meta.product, fields, templates: [] };
  for (const [f, x] of Object.entries(S.dec)) {
    if (x.use === "entity" && x.entity) fields.push({ field: f, kind: x.kind, entity: x.entity, role: x.role || "Unknown", asim: x.asim || "" });
    if (x.use === "field" && x.asim) fields.push({ field: f, kind: x.kind, entity: "", role: "", asim: x.asim });
    if (x.use === "result") d.result = { field: f, kind: x.kind, map: x.map };
    if (x.use === "event_type") { const m = Object.fromEntries(Object.entries(x.map || {}).filter(([, v]) => v)); d.event_type = Object.keys(m).length ? { field: f, kind: x.kind, map: m, default: "Other" } : { field: f, kind: x.kind }; }
    if (x.use === "record_key") d.record_key = { field: f, kind: x.kind };
  }
  const tpls = P.templates || [];
  Object.entries(S.tpl).forEach(([i, t]) => {
    if (!t.include) return;
    let rx = t.regex; const slots = {}; const used = new Set();
    tpls[i].slots.forEach((s) => {
      const sl = t.slots[s.slot] || {};
      let name = sl.name || sl.asim || (sl.entity ? `${sl.entity}_${sl.role || "Unknown"}` : s.slot);
      name = name.replace(/\W/g, "") || s.slot; let n = name, k = 2; while (used.has(n)) n = name + k++; used.add(n);
      rx = rx.split(`(?P<${s.slot}>`).join(`(?P<${n}>`);
      slots[n] = sl.entity ? { entity: sl.entity, role: sl.role || "Unknown" } : {};
    });
    d.templates.push({ id: `tpl-${+i + 1}`, match: t.match, regex: rx, event_type: t.eventType, event_result: t.outcome, tier: 1, slots });
  });
  if (P.textColumn && (d.templates.length || P.kvSource)) d.text_column = P.textColumn;
  if (!d.event_type && !P.textColumn) delete d.event_type;
  return d;
}

export function counts({ S }) {
  const all = Object.values(S.dec).filter((x) => x.use !== "skip");
  const tpl = Object.values(S.tpl).filter((t) => t.include);
  return { done: all.filter((x) => x.accepted).length + tpl.filter((t) => t.accepted).length, total: all.length + tpl.length };
}

function summaryOf(x) {
  if (x.use === "skip") return "Skipped: stays in the raw table.";
  if (x.use === "entity") return `Indexed as <b>${esc(x.entity)}:${esc(x.role)}</b>${x.asim ? ` → ASIM <b>${esc(x.asim)}</b>` : ""}`;
  if (x.use === "result") return `Result: ${Object.entries(x.map).filter(([, o]) => o !== "Ignore").map(([v, o]) => `<code>${esc(v)}</code> → ${esc(o)}`).join(", ") || "no values mapped"}`;
  if (x.use === "event_type") return "Used as the event type";
  if (x.use === "record_key") return "Used as the unique ID for pivots";
  if (x.use === "field") return x.asim ? `Mapped to ASIM <b>${esc(x.asim)}</b>` : "Not mapped";
  return "";
}

const roleChoicesFor = (P, e) => P.roleChoices[e] || [{ value: "Unknown", label: "No role", help: "Searched by value" }];

function cardBody(P, cd, x) {
  const rec = cd.recommended || {};
  const f = esc(cd.field);
  if (cd.decision === "entity" || x.use === "entity") {
    const ents = P.entityChoices.map((e) => `<button class="choice ${x.entity === e.value && x.use !== "skip" ? "on" : ""} ${rec.entity === e.value ? "rec" : ""}" data-f="${f}" data-entity="${e.value}"><b>${esc(e.label)}</b></button>`).join("");
    const roles = x.entity ? roleChoicesFor(P, x.entity).map((r) => `<button class="choice ${x.role === r.value ? "on" : ""} ${rec.role === r.value && rec.entity === x.entity ? "rec" : ""}" data-f="${f}" data-role="${r.value}"><b>${esc(r.label)}</b><span>${esc(r.help)}</span></button>`).join("") : "";
    return `<div class="qlabel">What is in this field?</div><div class="choices">${ents}</div>
      ${x.entity ? `<div class="qlabel">What role does it play in the event?</div><div class="choices">${roles}</div>` : ""}
      <div class="effect">${x.entity ? `Indexed as <b>${esc(x.entity)}:${esc(x.role || "Unknown")}</b>${x.asim ? ` → ASIM <b>${esc(x.asim)}</b>` : ""}. ${esc(EFFECT[`${x.entity}:${x.role}`] || "Found by hunt_value.")}` : "Skipped: stays in the raw table, reachable through search_raw."}</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use this</button><button class="btn sm ghost" data-skip="${f}">Skip field</button></div>`;
  }
  if (cd.decision === "result") {
    return `<div class="qlabel">Which values mean success and which mean failure?</div><div class="vmap">${(cd.values || []).map((v) => {
      const cur = x.map[v.value] || "Ignore";
      return `<code>${esc(v.value || "(empty)")}</code><span class="small muted">${num(v.rows)} rows</span><span class="seg">${["Success", "Failure", "Ignore"].map((o) => `<button class="${o === "Success" ? "s" : o === "Failure" ? "f" : "i"} ${cur === o ? "on" : ""}" data-f="${f}" data-v="${esc(v.value)}" data-o="${o}">${o}</button>`).join("")}</span>`; }).join("")}</div>
      <div class="effect">Becomes EventResult. auth_events can then filter on Success or Failure.</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use as the result</button><button class="btn sm ghost" data-skip="${f}">Don't use</button></div>`;
  }
  if (cd.decision === "event_type") {
    return `<div class="qlabel">Name the activity for each value (leave blank to keep the value as is)</div><div class="vmap">${(cd.values || []).map((v) => `<code>${esc(v.value || "(empty)")}</code><span class="small muted">${num(v.rows)} rows</span><select data-f="${f}" data-etv="${esc(v.value)}"><option value="">(keep value)</option>${["Logon", "Logoff", "NetworkSession", "HTTPsession", "Other"].map((o) => `<option ${x.map[v.value] === o ? "selected" : ""}>${o}</option>`).join("")}</select>`).join("")}</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use as the event type</button><button class="btn sm ghost" data-skip="${f}">Don't use</button></div>`;
  }
  if (cd.decision === "record_key") {
    return `<div class="effect">Used to build SourceRecordKey so every index row points back to exactly one raw row.</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use as the unique ID</button><button class="btn sm ghost" data-skip="${f}">Don't use</button></div>`;
  }
  return `<div class="qlabel">Map to an ASIM field (not an entity)</div><select data-f="${f}" data-asim>${["", ...P.asimFields].map((a) => `<option ${x.asim === a ? "selected" : ""} value="${esc(a)}">${esc(a || "(don't map)")}</option>`).join("")}</select>
    <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use this</button><button class="btn sm ghost" data-skip="${f}">Skip field</button></div>`;
}

function rowHtml(ctx, cd) {
  const { P, S } = ctx, x = S.dec[cd.field], f = esc(cd.field);
  const open = S.open[cd.field] && !x.accepted;
  return `<div class="frow ${x.accepted ? "accepted" : ""}" data-row="${f}">
    <div class="frow-line"><span class="fname">${f}</span><span class="conf ${esc(cd.confidence || "none")}">${esc(cd.confidence || "no")} confidence</span>
      <span class="frow-rec">${x.accepted ? summaryOf(x) : esc(cd.reason)}</span>
      <span class="frow-act">${x.accepted ? `${st("ok", "decided")}<button class="btn ghost sm" data-change="${f}">Change</button>` : `<button class="btn sm primary" data-accept="${f}">Accept</button><button class="btn sm" data-change="${f}">${open ? "Close" : "Change"}</button>`}</span></div>
    ${open ? `<div class="frow-body"><div class="samples">${(cd.samples || []).slice(0, 5).map((s) => `<code title="${esc(s)}">${esc(s)}</code>`).join("")}</div><div class="small muted">${pct(cd.fillRate)} filled</div>${cardBody(P, cd, x)}</div>` : ""}
  </div>`;
}

function tplRow(ctx, t, i) {
  const { P, S } = ctx, s = S.tpl[i], open = S.topen[i] && !s.accepted;
  const slotRows = t.slots.map((sl) => {
    const v = s.slots[sl.slot];
    return `<tr><td><code>${esc(sl.token)}</code></td>
      <td><select data-ti="${i}" data-slot="${sl.slot}" data-k="entity">${P.entityChoices.map((e) => `<option value="${e.value}" ${v.entity === e.value ? "selected" : ""}>${esc(e.label)}</option>`).join("")}</select></td>
      <td>${v.entity ? `<select data-ti="${i}" data-slot="${sl.slot}" data-k="role">${roleChoicesFor(P, v.entity).map((r) => `<option value="${r.value}" ${v.role === r.value ? "selected" : ""}>${esc(r.label)}</option>`).join("")}</select>` : `<span class="muted small">–</span>`}</td></tr>`;
  }).join("");
  return `<div class="frow ${s.accepted ? "accepted" : ""} ${s.include ? "" : "skipped"}" data-trow="${i}">
    <div class="frow-line"><label class="inline"><input type="checkbox" data-tinc="${i}" ${s.include ? "checked" : ""}> Include</label>
      <span class="frow-rec"><code>${esc(t.template.length > 90 ? t.template.slice(0, 89) + "…" : t.template)}</code> <span class="small muted">${pct(t.share, 1)} of lines${s.outcome ? ` · ${esc(s.outcome)}` : ""}</span></span>
      ${s.include ? `<span class="frow-act">${s.accepted ? `${st("ok", "decided")}<button class="btn ghost sm" data-tchange="${i}">Change</button>` : `<button class="btn sm primary" data-taccept="${i}">Accept</button><button class="btn sm" data-tchange="${i}">${open ? "Close" : "Change"}</button>`}</span>` : ""}</div>
    ${open && s.include ? `<div class="frow-body"><pre style="white-space:pre-wrap">${esc(t.template)}</pre><div class="small muted">Example: <code>${esc(t.example)}</code></div>
      <div class="qlabel">What outcome does this message mean?</div>
      <span class="seg">${[["Success", "s"], ["Failure", "f"], ["", "i"]].map(([o, k]) => `<button class="${k} ${s.outcome === o ? "on" : ""}" data-ti="${i}" data-out="${o}">${o || "No outcome"}</button>`).join("")}</span>
      ${t.outcomeSuggested ? `<span class="small muted">Suggested: ${esc(t.outcomeSuggested)} (wording of the message)</span>` : ""}
      ${t.slots.length ? `<div class="qlabel">What does each placeholder hold?</div><div class="tbl-wrap"><table><tr><th>Placeholder</th><th>Holds</th><th>Role</th></tr>${slotRows}</table></div>` : ""}
      ${disclose("Advanced: match text and regex", `<div class="grid g2"><label class="small">Match text<input type="text" data-ti="${i}" data-match value="${esc(s.match)}" style="width:100%"></label><label class="small">Regex<input type="text" data-ti="${i}" data-regex value="${esc(s.regex)}" style="width:100%;font-family:var(--mono)"></label></div>`)}
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-taccept="${i}">Use this template</button></div></div>` : ""}
  </div>`;
}

export async function renderFields(main, table, head) {
  const ctx = await getState(table);
  const draw = () => {
    const { P, S } = ctx;
    const live = (P.existing || []).find((e) => e.status === "live");
    const cards = P.cards.filter((c) => c.decision !== "skip");
    const pending = cards.filter((c) => !S.dec[c.field].accepted);
    const high = pending.filter((c) => c.confidence === "high");
    const rest = pending.filter((c) => c.confidence !== "high");
    const done = cards.filter((c) => S.dec[c.field].accepted);
    const skipped = P.cards.filter((c) => c.decision === "skip");
    const tpls = P.templates || [];
    const c = counts(ctx);
    const preset = P.presets.find((p) => p.value === P.preset);
    main.innerHTML = head + `
      ${live ? `<div class="callout blue">This table already has a live mapping (<a href="#/registry/${enc(live.id)}">${esc(live.id)}</a>, version ${live.version}). Saving here creates a new draft for approval.</div>` : ""}
      <div class="card section"><div class="row"><label class="inline"><b>Kind of source</b> <select id="preset">${P.presets.map((p) => `<option value="${esc(p.value)}" ${P.preset === p.value ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select></label>
        <span class="small muted">${esc(preset ? preset.hint : "")}</span></div></div>
      ${high.length ? `<section class="card section"><div class="row"><h2>High confidence <span class="count">${high.length}</span></h2><button class="btn lime right" id="acceptHigh">Accept all ${high.length} high-confidence</button></div>${high.map((cd) => rowHtml(ctx, cd)).join("")}</section>` : ""}
      ${rest.length ? `<section class="card section"><h2>Needs a decision <span class="count">${rest.length}</span></h2>${rest.map((cd) => rowHtml(ctx, cd)).join("")}</section>` : ""}
      ${!pending.length ? `<div class="card section"><p>${st("ok", "done")} Every field is decided. Check the preview next.</p></div>` : ""}
      ${tpls.length ? `<section class="card section"><h2>Message templates <span class="count">${tpls.length}</span></h2><p class="small muted">Common message shapes in ${esc(P.textColumn)}. Shapes under 2% of lines start excluded.</p>${tpls.map((t, i) => tplRow(ctx, t, i)).join("")}</section>` : ""}
      ${done.length ? disclose(`Decided (${done.length})`, done.map((cd) => rowHtml(ctx, cd)).join("")) : ""}
      ${skipped.length ? disclose(`${skipped.length} fields left in the raw table`, `<p class="small muted">No entity-like values. Include one to map it to an ASIM field.</p><div class="row">${skipped.map((s) => `<button class="btn sm" data-include="${esc(s.field)}">${esc(s.field)}</button>`).join("")}</div>`) : ""}
      ${P.asimParsers.length ? disclose(`Microsoft ASIM parsers for this table (${P.asimParsers.length})`, `<p class="small muted">${esc(P.pathHelp)}</p><div class="tbl-wrap"><table><tr><th>Parser</th><th>Schema</th><th>Product</th><th></th></tr>${P.asimParsers.slice(0, 8).map((p) => `<tr><td class="mono">${esc(p.builtIn || p.parser)}</td><td>${esc(p.schema)}</td><td>${esc(p.product)}</td><td><button class="btn sm" data-expand="${esc(p.parser)}">Expand to lake KQL</button></td></tr>`).join("")}</table></div>`) : ""}
      <div class="sticky-bar section"><span class="small"><b>${c.done}</b> of ${c.total} decided</span><div class="progress"><i style="width:${c.total ? (100 * c.done) / c.total : 100}%"></i></div>
        ${pending.length ? `<button class="btn ghost" id="acceptAll">Accept all recommendations</button>` : ""}
        <a class="btn primary" id="toPreview" href="#/onboard/${enc(table)}/preview">Next: Preview</a></div>`;
    bind();
  };

  const bind = () => {
    const { S } = ctx;
    const P = () => ctx.P;
    $("#preset").onchange = async (e) => { await getState(table, e.target.value); Object.assign(ctx, STATE.get(table)); STATE.set(table, ctx); draw(); };
    $$("[data-change]", main).forEach((b) => (b.onclick = () => { const f = b.dataset.change, x = S.dec[f], cd = P().cards.find((c) => c.field === f); if (x.accepted) { x.accepted = false; if (x.use === "skip") x.use = cd.decision; S.open[f] = true; } else S.open[f] = !S.open[f]; draw(); }));
    $$("[data-entity]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.f]; x.use = "entity"; x.entity = b.dataset.entity; const rc = roleChoicesFor(P(), x.entity); x.role = rc.some((r) => r.value === x.role) ? x.role : rc[0].value; x.asim = P().asimByEntityRole[`${x.entity}:${x.role}`] || ""; draw(); }));
    $$("[data-role]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.f]; x.role = b.dataset.role; x.asim = P().asimByEntityRole[`${x.entity}:${x.role}`] || ""; draw(); }));
    $$("[data-accept]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.accept]; if (x.use === "skip") x.use = "entity"; x.accepted = true; S.open[b.dataset.accept] = false; draw(); }));
    $$("[data-skip]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.skip]; x.use = "skip"; x.accepted = true; S.open[b.dataset.skip] = false; draw(); }));
    $$("[data-include]", main).forEach((b) => (b.onclick = () => { const f = b.dataset.include, cd = P().cards.find((c) => c.field === f); cd.decision = "field"; S.dec[f] = { accepted: false, kind: cd.kind, use: "field", asim: "" }; S.open[f] = true; draw(); }));
    $$("[data-o]", main).forEach((b) => (b.onclick = () => { S.dec[b.dataset.f].map[b.dataset.v] = b.dataset.o; draw(); }));
    $$("[data-etv]", main).forEach((s) => (s.onchange = () => { S.dec[s.dataset.f].map[s.dataset.etv] = s.value; }));
    $$("[data-asim]", main).forEach((s) => (s.onchange = () => { S.dec[s.dataset.f].asim = s.value; }));
    $$("[data-tinc]", main).forEach((c) => (c.onchange = () => { S.tpl[c.dataset.tinc].include = c.checked; draw(); }));
    $$("[data-tchange]", main).forEach((b) => (b.onclick = () => { const i = b.dataset.tchange; if (S.tpl[i].accepted) { S.tpl[i].accepted = false; S.topen[i] = true; } else S.topen[i] = !S.topen[i]; draw(); }));
    $$("[data-taccept]", main).forEach((b) => (b.onclick = () => { S.tpl[b.dataset.taccept].accepted = true; S.topen[b.dataset.taccept] = false; draw(); }));
    $$("[data-out]", main).forEach((b) => (b.onclick = () => { S.tpl[b.dataset.ti].outcome = b.dataset.out; draw(); }));
    $$("select[data-slot]", main).forEach((s) => (s.onchange = () => { const v = S.tpl[s.dataset.ti].slots[s.dataset.slot]; v[s.dataset.k] = s.value; if (s.dataset.k === "entity") v.role = roleChoicesFor(P(), s.value)[0].value; v.asim = P().asimByEntityRole[`${v.entity}:${v.role}`] || ""; draw(); }));
    $$("[data-match]", main).forEach((i) => (i.onchange = () => { S.tpl[i.dataset.ti].match = i.value; }));
    $$("[data-regex]", main).forEach((i) => (i.onchange = () => { S.tpl[i.dataset.ti].regex = i.value; }));
    $$("[data-expand]", main).forEach((b) => (b.onclick = async () => {
      b.disabled = true; b.textContent = "Expanding…";
      try {
        const r = await api("/asim/expand", { method: "POST", body: { parser: b.dataset.expand } });
        modal(`${r.parser} as lake KQL`, `<p>${r.lakeSafe ? st("ok", "lake-safe: no function calls left") : st("review", "function calls left: " + r.remainingCalls.join(", "))}</p><pre>${esc(r.query)}</pre>`);
      } catch (e) { toast(e.message, true); }
      b.disabled = false; b.textContent = "Expand to lake KQL";
    }));
    if ($("#acceptHigh")) $("#acceptHigh").onclick = () => { P().cards.forEach((c) => { if (c.confidence === "high" && S.dec[c.field].use !== "skip") S.dec[c.field].accepted = true; }); draw(); };
    if ($("#acceptAll")) $("#acceptAll").onclick = () => { P().cards.forEach((c) => (S.dec[c.field].accepted = true)); Object.values(S.tpl).forEach((t) => { if (t.include) t.accepted = true; }); draw(); };
  };
  draw();
}
```

- [ ] **Step 5: Add the landing page, stepper and step dispatch to `onboard.js`**

1. Replace the import line at the top of `onboard.js` with:

```js
import { ROUTES, ALIAS, api, esc, enc, pct, st, pageHeader, disclose } from "./core.js";
import { renderFields } from "./fields.js";
```

2. Append:

```js
export const STEPS = [["pick", "Pick source"], ["fields", "Decide fields"], ["preview", "Preview"], ["submit", "Submit"], ["deploy", "Deploy"], ["validate", "Validate"]];
const STAGE_STEP = { detected: "fields", proposed: "fields", in_review: "fields", failed: "fields", registry: "submit", deployed: "deploy", validating: "validate", live: "validate" };
// Renderers per step: (main, table, headHtml, stage) => Promise. Tasks 5 and 7 add preview, submit, deploy, validate.
export const STEP_VIEWS = { fields: (main, table, head) => renderFields(main, table, head) };

export function stepper(table, current, stage) {
  const reached = STEPS.findIndex(([k]) => k === (STAGE_STEP[stage] || "fields"));
  return `<ol class="stepper">${STEPS.map(([k, label], i) => {
    const cls = k === current ? "now" : (i < reached || stage === "live") ? "done" : "";
    const reachable = k === "pick" || i <= Math.max(reached, 2);
    const inner = `<b>${i + 1}</b>${esc(label)}`;
    return `<li class="step ${cls}">${reachable ? `<a href="${k === "pick" ? "#/onboard" : `#/onboard/${enc(table)}/${k}`}">${inner}</a>` : `<span>${inner}</span>`}</li>`;
  }).join("")}</ol>`;
}

async function stageOf(table) {
  const o = await api(`/onboarding/${enc(table)}`);
  if (o.stage) return o.stage.stage;
  const live = await api("/registry?status=live");
  return live.some((r) => r.group.table === table) ? "live" : "detected";
}

async function landing(main) {
  const r = await api("/tables");
  const row = (t) => { const n = nextStep(t); return `<div class="att"><div><b>${esc(t.name)}</b> ${st(t.status)}<div class="small muted">${esc(n.why)}</div></div><a class="btn sm ${n.attention ? "primary" : ""}" href="${stepHref(t, n)}">${esc(n.label)}</a></div>`; };
  const groups = [
    ["Needs a decision", (t) => ["detected", "proposed", "in_review", "failed"].includes(t.stage)],
    ["Waiting for approval", (t) => t.stage === "registry"],
    ["Deploy and validate", (t) => ["deployed", "validating"].includes(t.stage)],
  ];
  const live = r.tables.filter((t) => t.stage === "live");
  main.innerHTML = pageHeader("Onboard a source", "Map a source's fields, get it approved, deployed and validated.", `<a class="btn" href="#/catalog">Plan a new connector</a>`) +
    groups.map(([h, f]) => { const ts = r.tables.filter(f); return ts.length ? `<section class="card section"><h2>${h} <span class="count">${ts.length}</span></h2>${ts.map(row).join("")}</section>` : ""; }).join("") +
    disclose(`Live sources (${live.length})`, live.map(row).join(""));
}

ROUTES.onboard = async (main, arg) => {
  if (!arg) return landing(main);
  if (arg.startsWith("~group/")) {            // old #/validation/<group> links: a group id is not always "<table>:…" (CEF:Fortinet/Fortigate)
    const gid = arg.slice("~group/".length);
    const g = (await api("/registry")).find((r) => r.id === gid);
    location.replace(g ? `#/onboard/${enc(g.group.table)}/validate` : "#/onboard");
    return;
  }
  const [table, want] = arg.split("/");
  const stage = await stageOf(table);
  const step = STEP_VIEWS[want] ? want : (STAGE_STEP[stage] in STEP_VIEWS ? STAGE_STEP[stage] : "fields");
  const head = pageHeader(table, `Stage: ${esc(stage.replace(/_/g, " "))}`) + stepper(table, step, stage);
  await STEP_VIEWS[step](main, table, head, stage);
};

ALIAS.sources = () => "onboard";
ALIAS.review = (arg) => (arg ? `onboard/${enc(arg)}/fields` : "onboard");
```

- [ ] **Step 6: Wire it in**

- In `main.js`, add `import "./fields.js";` after `import "./onboard.js";`.
- In `legacy.js`, delete the `ROUTES.sources` block, the `EFFECT` constant and the whole `ROUTES.review` block, with their comments (old `app.js` lines 305–584).
- In `legacy.js` and in `more.js`, any link to `#/review/` or `#/sources` keeps working through the aliases; leave them.
- Append to the task-layout CSS block in `styles.css`:

```css
ol.stepper { list-style: none; margin: 0 0 18px; padding: 0; }
ol.stepper .step a, ol.stepper .step span { display: block; color: inherit; }
ol.stepper .step a:hover { text-decoration: none; }
ol.stepper .step b { display: inline-block; margin-right: 6px; }
.frow { border-top: 1px solid var(--rule); padding: 10px 0; }
.card h2 + .frow, .row + .frow, .more-body > .frow:first-child { border-top: 0; }
.frow-line { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.frow .fname { font-family: var(--mono); font-weight: 700; font-size: 13.5px; }
.frow-rec { flex: 1; min-width: 220px; color: var(--ink-2); }
.frow-act { display: flex; gap: 6px; align-items: center; }
.frow.accepted .fname { color: var(--good-ink); }
.frow.skipped { opacity: .7; }
.frow-body { margin: 10px 0 4px; padding: 12px 14px; background: var(--surface-2); border-radius: 8px; }
```

- [ ] **Step 7: Run the tests**

Run: `PY -m pytest tests -v`
Expected: all PASS (1 skipped).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(ui): Onboard landing, stepper and one-line field decisions"
```

---

### Task 5: Preview and Submit steps

**Files:**
- Modify: `app/static/js/fields.js` (add `renderPreview`), `app/static/js/onboard.js` (register `preview` and `submit`, add `renderSubmit`)
- Modify: `tests/ui_flows.py` (`preview_and_submit`, `onboard_badge_reader`), `tests/test_ui.py`

**Interfaces:**
- Consumes: `getState`, `decisionsPayload`, `counts` (Task 4); `barChart` from `charts.js`; `refreshPending`, `renderNav` from `core.js`.
- Produces:
  - `renderPreview(main, table, head)` in `fields.js` and `renderSubmit(main, table, head, stage)` in `onboard.js`.
  - The Submit step shows the text "Waiting for an Admin" and "Approval #N".
  - `Flow.onboard_badge_reader()`.

- [ ] **Step 1: Add the flows to `tests/ui_flows.py`**

```python
    def preview_and_submit(self) -> None:
        p = self.page
        self.click(p.locator("#toPreview"))
        p.wait_for_selector("#pv .kpi")
        self.say("The preview runs the mapping on sample rows: rows with an entity and template match, against their targets.")
        self.wait(5)
        self.click(p.locator("#submit"))
        p.wait_for_selector("text=Waiting for an Admin")
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
```

- [ ] **Step 2: Write the failing tests (append to `tests/test_ui.py`)**

```python
def test_preview_detail_collapsed_and_survives_reload(flow):
    flow.page.goto(flow.base + "/#/onboard/BadgeReader_CL/preview")
    flow.page.reload()                                                 # a hash change alone keeps the page; reload drops in-memory decisions
    flow.page.wait_for_selector("#pv .kpi")
    assert flow.page.locator("#pv .st", has_text="90%").count() == 1
    code = flow.page.locator("details.more", has_text="Show generated code")
    assert code.count() == 1 and code.get_attribute("open") is None
    assert flow.page.locator("#pv .pair").count() <= 3


def test_analyst_submits_badge_reader(flow):
    flow.as_role("analyst")
    flow.open_onboarding("BadgeReader_CL")
    flow.decide_all_fields()
    flow.preview_and_submit()
    assert flow.page.locator("text=Approval #").is_visible()
    assert flow.page.url.endswith("#/onboard/BadgeReader_CL/submit")
    assert flow.page.locator('#nav a[data-nav="approve"]').count() == 0     # analysts do not approve
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `PY -m pytest tests/test_ui.py -v -k "preview or submits"`
Expected: FAIL (the preview step falls back to fields; no `#pv`).

- [ ] **Step 4: Add `renderPreview` to `fields.js`**

1. Change the first import line of `fields.js` to:

```js
import { $, $$, api, esc, pct, num, enc, st, modal, toast, disclose, refreshPending } from "./core.js";
import { barChart } from "./charts.js";
```

2. Append:

```js
export async function renderPreview(main, table, head) {
  const ctx = await getState(table);
  const { S } = ctx;
  const c = counts(ctx);
  main.innerHTML = head + `
    ${c.done < c.total ? `<div class="callout warn">${c.total - c.done} of ${c.total} fields are not decided yet. They stay searchable by value only. <a href="#/onboard/${enc(table)}/fields">Decide them</a></div>` : ""}
    <div class="card section" id="pv"><div class="loader">Running the mapping on sample rows…</div></div>
    ${disclose("Name and details", `<div class="grid g3"><label>Group ID<br><input type="text" id="gid" value="${esc(S.meta.id)}" style="width:100%"></label>
      <label>Vendor<br><input type="text" id="vendor" value="${esc(S.meta.vendor)}" style="width:100%"></label>
      <label>Product<br><input type="text" id="product" value="${esc(S.meta.product)}" style="width:100%"></label></div>`)}
    <div class="sticky-bar section"><a class="btn" href="#/onboard/${enc(table)}/fields">Back to fields</a><span class="right"></span>
      <button class="btn" id="saveDraft">Save draft</button><button class="btn primary" id="submit">Submit for approval</button></div>`;
  const pv = $("#pv");
  try {
    const r = await api(`/tables/${enc(table)}/preview`, { method: "POST", body: { decisions: decisionsPayload(ctx) } });
    if (r.errors && r.errors.length) {
      pv.innerHTML = `<h2>The mapping has problems</h2><div class="callout warn">${r.errors.map(esc).join("<br>")}</div>`;
    } else {
      const cov = r.coverage;
      const okE = cov.ExtractionRate >= 0.9, okT = cov.TemplateMatchRate === null || cov.TemplateMatchRate >= 0.7;
      pv.innerHTML = `<h2>What the index will hold <span class="muted small" style="font-weight:400">on ${num(cov.RawRows)} sample rows</span></h2>
        <div class="grid g2"><div class="kpi"><span class="v">${pct(cov.ExtractionRate)}</span><span class="l">rows with an entity ${st(okE ? "ok" : "review", okE ? "meets 90%" : "below 90%")}</span></div>
          <div class="kpi"><span class="v">${cov.TemplateMatchRate === null ? "n/a" : pct(cov.TemplateMatchRate)}</span><span class="l">template match ${cov.TemplateMatchRate === null ? "" : st(okT ? "ok" : "review", okT ? "meets 70%" : "below 70%")}</span></div></div>
        <h3 class="section">Entities by type and role</h3>
        ${barChart(Object.entries(r.byEntity).slice(0, 8).map(([k, v]) => ({ label: k, value: v, status: "" })), { max: Math.max(...Object.values(r.byEntity), 1), fmt: (v) => num(Math.round(v)), width: 520 })}
        <div class="row small">${Object.entries(r.byResult).map(([k, v]) => `<span class="tag">${esc(k)}: ${num(v)}</span>`).join("")}</div>
        <h3 class="section">Sample rows</h3>
        ${r.pairs.slice(0, 3).map((p) => `<div class="pair"><div><div class="small muted">Raw row</div><pre>${esc(JSON.stringify(p.raw, null, 1))}</pre></div><div><div class="small muted">Index rows</div><pre>${esc(p.index.map((e) => `${e.EntityType}:${e.Role} = ${e.Value}${e.EventResult ? "  " + e.EventResult : ""}`).join("\n"))}</pre></div></div>`).join("") || `<div class="empty">No rows produced an entity yet</div>`}
        ${disclose("Show generated code", `<h3>Registry YAML</h3><pre>${esc(r.yaml)}</pre><h3 class="section">Lake KQL</h3><pre>${esc(r.kql)}</pre>`)}`;
    }
  } catch (e) { pv.innerHTML = `<div class="callout warn">${esc(e.message)}</div>`; }
  const save = async (submit) => {
    S.meta.id = $("#gid").value.trim() || `${table}:main`; S.meta.vendor = $("#vendor").value; S.meta.product = $("#product").value;
    $$("#saveDraft, #submit").forEach((b) => (b.disabled = true));
    try {
      const r = await api(`/registry/from-decisions/${enc(table)}`, { method: "POST", body: { decisions: decisionsPayload(ctx), submit } });
      toast(submit ? `Submitted. Approval #${r.approval} is waiting for an Admin.` : "Draft saved");
      await refreshPending();
      location.hash = submit ? `#/onboard/${enc(table)}/submit` : `#/onboard/${enc(table)}/fields`;
    } catch (e) { toast(e.message, true); $$("#saveDraft, #submit").forEach((b) => (b.disabled = false)); }
  };
  $("#saveDraft").onclick = () => save(false);
  $("#submit").onclick = () => save(true);
}
```

- [ ] **Step 5: Add `renderSubmit` to `onboard.js` and register both steps**

1. Change the imports of `onboard.js` to:

```js
import { ROUTES, ALIAS, api, esc, enc, pct, when, can, st, pageHeader, disclose } from "./core.js";
import { renderFields, renderPreview } from "./fields.js";
```

2. Replace the `STEP_VIEWS` line with:

```js
export const STEP_VIEWS = {
  fields: (main, table, head) => renderFields(main, table, head),
  preview: (main, table, head) => renderPreview(main, table, head),
  submit: (main, table, head, stage) => renderSubmit(main, table, head, stage),
};
```

3. Append:

```js
async function renderSubmit(main, table, head, stage) {
  const pend = (await api("/approvals?status=pending")).filter((a) => a.kind === "registry" && a.payload.group.table === table);
  const a = pend[0];
  main.innerHTML = head + `<div class="card section">${a
    ? `<h2>Waiting for an Admin</h2><p>Approval <b>#${a.id}</b> was requested by ${esc(a.requested_by)} at ${when(a.requested_at)}. Nothing is live until an Admin approves it.</p>${can("admin") ? `<a class="btn primary" href="#/approve">Review it now</a>` : ""}`
    : ["deployed", "validating", "live"].includes(stage)
      ? `<h2>Approved</h2><p>The mapping is live. Next, deploy and validate it.</p><a class="btn primary" href="#/onboard/${enc(table)}/deploy">Next: Deploy</a>`
      : `<h2>Nothing submitted yet</h2><p>Decide the fields and check the preview, then submit from the preview step.</p><a class="btn primary" href="#/onboard/${enc(table)}/preview">Go to preview</a>`}</div>`;
}
```

- [ ] **Step 6: Run the tests**

Run: `PY -m pytest tests -v`
Expected: all PASS (1 skipped).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(ui): Preview step with targets and collapsed code; Submit step"
```

---

### Task 6: Approve inbox

**Files:**
- Create: `app/static/js/approve.js`
- Modify: `app/static/js/main.js`, `app/static/js/legacy.js` (delete `ROUTES.approvals`), `app/static/styles.css`
- Modify: `tests/ui_flows.py` (`approve_pending`), `tests/test_ui.py`

**Interfaces:**
- Consumes: `api`, `esc`, `pct`, `num`, `when`, `enc`, `ME`, `st`, `toast`, `modal`, `pageHeader`, `disclose`, `jsyaml`, `refreshPending`, `router` and `ALIAS` from `core.js`.
- Produces:
  - `ROUTES.approve`.
  - The alias `approvals` → `approve`.
  - `Flow.approve_pending(text)`.
  - Approval cards are `section.approval[data-aid]`; the approve button is `[data-ok]`; the reject controls are `[data-no]`, `#rjr-<id>` and `[data-noconfirm]`.

- [ ] **Step 1: Add the flow to `tests/ui_flows.py`**

```python
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
```

- [ ] **Step 2: Write the failing tests (append to `tests/test_ui.py`)**

```python
def test_reject_needs_reason(flow):
    flow.as_role("admin")
    flow.page.goto(flow.base + "/#/approvals")
    flow.page.wait_for_url("**/#/approve")
    card = flow.page.locator("section.approval", has_text="BadgeReader_CL").first
    card.wait_for()
    card.locator("[data-no]").click()
    card.locator("[data-noconfirm]").click()
    assert flow.page.locator(".toast.err", has_text="reason").is_visible()
    assert card.is_visible()                                   # still pending


def test_admin_approves_badge_reader(flow):
    flow.approve_pending("BadgeReader_CL")
    assert flow.page.locator("section.approval", has_text="BadgeReader_CL").count() == 0
    details = flow.page.locator("details.more", has_text="History")
    assert details.count() == 1 and details.get_attribute("open") is None
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `PY -m pytest tests/test_ui.py -v -k "reject or approves"`
Expected: FAIL (no `#/approve` route; no alias).

- [ ] **Step 4: Create `app/static/js/approve.js`**

```js
/* Approve: an inbox of pending changes. Each card says in plain words what the change does. */
import { ROUTES, ALIAS, $, $$, api, esc, pct, num, when, enc, ME, st, toast, modal, pageHeader, disclose, jsyaml, refreshPending, router } from "./core.js";

const ROLE_WORDS = {
  "user:Actor": "who did it", "user:Target": "the account signing in", "user:Src": "the user behind the traffic",
  "ip:Src": "source IP", "ip:Dst": "destination IP", "ip:Dvc": "reporting device IP",
  "host:Dvc": "reporting device", "host:Src": "source machine", "host:Dst": "destination machine",
};
const roleWords = (k) => { const [e, r] = k.split(":"); return ROLE_WORDS[k] || (r === "Unknown" ? `${e}, no role claimed` : `${e} (${r})`); };

function staticBullets(a, budget) {
  if (a.kind === "registry") {
    const g = a.payload.group, out = [];
    (g.exclude_text || []).forEach((t) => out.push(`Lines containing <code>${esc(t)}</code> are marked as noise and left out of the index.`));
    out.push(g.engine === "kql_job" ? `Indexed by KQL jobs (${num(budget.kqlJobs)} of ${num(budget.limit)} jobs in use now).` : "Indexed by the hourly notebook; no KQL job is added.");
    return out;
  }
  return [
    ...(a.payload.solutions || []).map((s) => `Install the <b>${esc(s.name)}</b> solution from the Content hub.`),
    ...(a.payload.tables || []).map((t) => `Create table <b>${esc(t.name)}</b> on the ${esc(t.plan === "Auxiliary" ? "Lake" : t.plan)} plan, kept ${num(t.retentionDays)} days.`),
  ];
}

function card(a, budget) {
  return `<section class="card section approval" data-aid="${a.id}">
    <div class="row"><h2>#${a.id} ${esc(a.title)}</h2><span class="muted small right">requested by ${esc(a.requested_by)} at ${when(a.requested_at)}</span></div>
    <h3>What this changes</h3>
    <ul class="changes" id="ch-${a.id}">${a.kind === "registry" ? `<li class="muted" data-pvli>Checking what the index will hold…</li>` : ""}${staticBullets(a, budget).map((x) => `<li>${x}</li>`).join("")}</ul>
    ${disclose("Show request details", a.kind === "registry" ? `<pre>${esc(jsyaml(a.payload.group))}</pre>` : `<pre>${esc(JSON.stringify(a.payload, null, 2))}</pre>`)}
    <div class="row section"><button class="btn primary" data-ok="${a.id}">Approve</button><button class="btn danger" data-no="${a.id}">Reject</button>
      <span class="row" id="rj-${a.id}" hidden><input type="text" id="rjr-${a.id}" aria-label="Reason for rejecting" placeholder="Reason, sent back to the requester" style="min-width:320px"><button class="btn danger" data-noconfirm="${a.id}">Confirm reject</button></span></div>
  </section>`;
}

async function fillPreview(a) {
  const li = $(`#ch-${a.id} [data-pvli]`);
  if (!li) return;
  try {
    const g = a.payload.group;
    const r = await api(`/tables/${enc(g.table)}/preview`, { method: "POST", body: { group: g } });
    if (r.errors && r.errors.length) { li.outerHTML = `<li>${st("review", "check")} ${r.errors.map(esc).join("; ")}</li>`; return; }
    const ents = Object.entries(r.byEntity).map(([k, n]) => `${esc(roleWords(k))} (${num(n)})`).join(", ");
    const c = r.coverage;
    li.outerHTML = `<li><b>${esc(g.table)}</b> becomes searchable with roles: ${ents || "none"}.</li>
      <li>On ${num(c.RawRows)} sample rows, ${pct(c.ExtractionRate)} have an entity (target 90%)${c.TemplateMatchRate === null ? "" : ` and ${pct(c.TemplateMatchRate)} match a template (target 70%)`}.</li>`;
  } catch (e) { li.textContent = "Preview unavailable: " + e.message; }
}

ROUTES.approve = async (main) => {
  const [rows, b] = await Promise.all([api("/approvals"), api("/build")]);
  const pend = rows.filter((r) => r.status === "pending"), done = rows.filter((r) => r.status !== "pending");
  main.innerHTML = pageHeader("Review and approve", ME.mode === "demo"
    ? "Nothing reaches the tenant until you approve it. In demo mode, approving simulates the Azure calls."
    : "Nothing reaches the tenant until you approve it. Approving runs the change with the app's managed identity.") +
    (pend.length ? pend.map((a) => card(a, b.budget)).join("") : `<div class="card"><div class="empty">Nothing is waiting for approval.</div></div>`) +
    disclose(`History (${done.length})`, `<div class="tbl-wrap"><table><tr><th>#</th><th>Change</th><th>Status</th><th>Requested</th><th>Decided</th><th></th></tr>${done.map((a) => `<tr><td>${a.id}</td><td>${esc(a.title)}</td><td>${st(a.status)}</td><td>${esc(a.requested_by)}<div class="small muted">${when(a.requested_at)}</div></td><td>${esc(a.decided_by || "")}<div class="small muted">${when(a.decided_at)}</div></td><td>${a.result ? `<button class="btn sm" data-res="${a.id}">Result</button>` : ""}</td></tr>`).join("")}</table></div>`);
  const byId = Object.fromEntries(rows.map((r) => [String(r.id), r]));
  $$("[data-res]").forEach((x) => (x.onclick = () => modal("Result", `<pre>${esc(JSON.stringify(byId[x.dataset.res].result, null, 2))}</pre>`)));
  $$("[data-ok]").forEach((x) => (x.onclick = async () => {
    x.disabled = true;
    try { await api(`/approvals/${x.dataset.ok}/approve`, { method: "POST" }); toast(`Approved #${x.dataset.ok}`); }
    catch (e) { toast(e.message, true); }
    await refreshPending(); router();
  }));
  $$("[data-no]").forEach((x) => (x.onclick = () => { $(`#rj-${x.dataset.no}`).hidden = false; $(`#rjr-${x.dataset.no}`).focus(); }));
  $$("[data-noconfirm]").forEach((x) => (x.onclick = async () => {
    const id = x.dataset.noconfirm, reason = $(`#rjr-${id}`).value.trim();
    if (!reason) { toast("Give a reason, so the requester knows what to change.", true); return; }
    try { await api(`/approvals/${id}/reject`, { method: "POST", body: { reason } }); toast(`Rejected #${id}`); }
    catch (e) { toast(e.message, true); }
    await refreshPending(); router();
  }));
  pend.filter((a) => a.kind === "registry").forEach(fillPreview);
};

ALIAS.approvals = () => "approve";
```

- [ ] **Step 5: Wire it in**

- In `main.js`, add `import "./approve.js";` after `import "./fields.js";`.
- In `legacy.js`, delete the `ROUTES.approvals` block and its comment.
- In `legacy.js` `renderPlan` (catalog), change `location.hash = "#/approvals";` to `location.hash = "#/approve";`.
- Append to the task-layout CSS block:

```css
ul.changes { margin: 0 0 4px; padding-left: 20px; }
ul.changes li { margin: 4px 0; }
.approval h2 { margin: 0; }
```

- [ ] **Step 6: Run the tests**

Run: `PY -m pytest tests -v`
Expected: all PASS (1 skipped).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(ui): Approve inbox with plain-language change summary and reasoned reject"
```

---

### Task 7: Deploy and Validate steps

**Files:**
- Modify: `app/static/js/onboard.js` (`renderDeploy`, `renderValidate`, register them, alias `validation`)
- Modify: `app/static/js/legacy.js` (delete `ROUTES.validation`), `app/static/styles.css`
- Modify: `tests/ui_flows.py` (`deploy_and_validate`), `tests/test_ui.py`

**Interfaces:**
- Consumes: `STEP_VIEWS` and `stepper` (Task 4); `api`, `modal`, `toast`, `ME`, `can`, `st`, `when`, `disclose` from `core.js`.
- Produces:
  - Deploy step: the "next" button is `#next` (stage `deployed`/`validating`/`live`) or `#markdep` (stage `registry` in live mode).
  - Validate step: one `.vgroup[data-gid]` card per live group. The hand-check buttons are `[data-hc=yes|no]`. The success text is "all four passed".
  - `Flow.deploy_and_validate(table)`.

- [ ] **Step 1: Add the flow to `tests/ui_flows.py`**

```python
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
```

- [ ] **Step 2: Write the failing tests (append to `tests/test_ui.py`)**

```python
def test_deploy_and_validate_badge_reader(flow):
    flow.as_role("analyst")
    flow.deploy_and_validate("BadgeReader_CL")
    assert flow.page.locator(".vgroup").count() == 1
    flow.page.goto(flow.base + "/#/validation/BadgeReader_CL:main")
    flow.page.wait_for_url("**/#/onboard/BadgeReader_CL/validate")
    flow.page.goto(flow.base + "/#/validation/" + "CEF%3AFortinet%2FFortigate")     # group id that does not start with its table
    flow.page.wait_for_url("**/#/onboard/CommonSecurityLog/validate")


def test_validate_shows_each_group(flow):
    flow.goto("onboard/CommonSecurityLog/validate")
    flow.page.wait_for_selector(".vgroup .checks")
    assert flow.page.locator(".vgroup").count() >= 2


def test_badge_reader_now_in_jsmith_hunt(flow):
    flow.hunt("jsmith@contoso.com")
    assert flow.page.locator("#htab", has_text="BadgeReader_CL:main").count() == 1
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `PY -m pytest tests/test_ui.py -v -k "deploy or validate or jsmith"`
Expected: FAIL (the deploy step is not registered; no `.vgroup`).

- [ ] **Step 4: Add the two steps to `onboard.js`**

1. Change the core import of `onboard.js` to:

```js
import { ROUTES, ALIAS, $, $$, api, esc, enc, pct, when, can, ME, st, modal, toast, pageHeader, disclose } from "./core.js";
```

2. Add these two lines to the `STEP_VIEWS` object:

```js
  deploy: (main, table, head, stage) => renderDeploy(main, table, head, stage),
  validate: (main, table, head) => renderValidate(main, table, head),
```

3. Append:

```js
async function renderDeploy(main, table, head, stage) {
  const [b, reg] = await Promise.all([api("/build"), api("/registry?status=live")]);
  const mine = reg.filter((r) => r.group.table === table).map((r) => r.id);
  const jobs = b.jobs.filter((j) => mine.includes(j.group));
  const nb = b.notebookGroups.filter((g) => mine.includes(g));
  const ready = ["deployed", "validating", "live"].includes(stage);
  main.innerHTML = head + `<div class="card section">${!mine.length
    ? `<h2>Not approved yet</h2><p>This source has no live mapping. Submit it for approval first.</p>`
    : `<h2>What runs for this source</h2>
      ${jobs.length ? `<div class="tbl-wrap"><table><tr><th>KQL job to create</th><th>Output table</th><th></th></tr>${jobs.map((j) => `<tr><td class="mono">${esc(j.name)}</td><td class="mono">${esc(j.output)}</td><td><button class="btn sm" data-file="${esc(j.file)}">View query</button></td></tr>`).join("")}</table></div>` : ""}
      ${nb.length ? `<p><b>${nb.map(esc).join(", ")}</b> ${nb.length > 1 ? "are" : "is"} indexed by the hourly notebook. There is no KQL job to create.</p>` : ""}
      ${disclose("Portal steps", `<pre style="white-space:pre-wrap;max-height:none">${esc(b.files["DEPLOY.md"])}</pre>`)}
      <div class="row section"><a class="btn" href="/api/v1/build/bundle.zip">Download bundle</a>${ME.mode === "demo" ? `<button class="btn" id="runidx">Re-run index now</button>` : ""}
        ${ready ? `<a class="btn primary right" id="next" href="#/onboard/${enc(table)}/validate">Next: Validate</a>`
          : `<button class="btn primary right" id="markdep" ${can("analyst") ? "" : "disabled"}>I've created the jobs: mark deployed</button>`}</div>`}</div>`;
  $$("[data-file]", main).forEach((x) => (x.onclick = () => modal(x.dataset.file, `<pre style="max-height:70vh">${esc(b.files[x.dataset.file])}</pre>`)));
  if ($("#runidx")) $("#runidx").onclick = async () => { const r = await api("/index/run", { method: "POST" }); toast(r.message || `Indexed ${r.entityRows} entity rows from ${r.groups} groups`); };
  if ($("#markdep")) $("#markdep").onclick = async () => {
    try { await api(`/onboarding/${enc(table)}/stage`, { method: "POST", body: { stage: "deployed", note: "jobs created in the portal" } }); location.hash = `#/onboard/${enc(table)}/validate`; }
    catch (e) { toast(e.message, true); }
  };
}

const verdict = (r) => r.passed ? st("ok", "all four passed") : r.checks.some((c) => c.passed === false) ? st("fail", "back to review") : st("pending", "waiting on you");

function checksHtml(r) {
  return `<ol class="checks">${r.checks.map((c) => `<li class="check"><div class="head"><b>${esc(c.label)}</b>${c.passed === true ? st("ok", "pass") : c.passed === false ? st("fail", "fail") : st("pending", "needs you")}</div>
    <div class="small muted">${esc(c.detail)}</div>
    ${c.check === "hand" && c.passed !== true && Array.isArray(c.data) ? `${c.data.slice(0, 3).map((p) => `<div class="pair"><div><div class="small muted">Raw</div><pre>${esc(JSON.stringify(p.raw[0] || {}, null, 1))}</pre></div><div><div class="small muted">Index</div><pre>${esc(p.index.map((e) => `${e.EntityType}:${e.Role} = ${e.Value}${e.EventResult ? "  " + e.EventResult : ""}`).join("\n"))}</pre></div></div>`).join("")}
      <div class="row"><button class="btn sm primary" data-hc="yes">The rows match</button><button class="btn sm danger" data-hc="no">Something is wrong</button></div>` : ""}
    ${c.check === "canary" && c.data && c.data.needsOperator ? `<div class="row"><input type="text" data-cv placeholder="Test value you generated, e.g. 192.0.2.250"><button class="btn sm" data-cvgo>Check</button></div>` : ""}
  </li>`).join("")}</ol>`;
}

async function renderValidate(main, table, head) {
  const reg = (await api("/registry?status=live")).filter((r) => r.group.table === table);
  if (!reg.length) { main.innerHTML = head + `<div class="card section"><h2>Not live yet</h2><p>Validation runs once the mapping is approved and deployed.</p></div>`; return; }
  main.innerHTML = head + reg.map((r, i) => `<section class="card section vgroup" data-gid="${esc(r.id)}" id="vg${i}"><h2>${esc(r.id)}</h2><div class="loader">Running the four checks…</div></section>`).join("");
  const show = (box, gid, r, body) => {
    box.innerHTML = `<div class="row"><h2>${esc(gid)} ${verdict(r)}</h2><button class="btn sm right" data-rerun>Run checks again</button></div>
      ${r.run_at ? `<p class="small muted">Last run ${when(r.run_at)}</p>` : ""}${checksHtml(r)}
      ${r.passed ? `<div class="callout section">Live: ${esc(table)} is searchable with roles. <a href="#/hunt">Hunt it</a></div>` : ""}`;
    $$("[data-hc]", box).forEach((b) => (b.onclick = () => run(box, gid, { ...body, handCheck: b.dataset.hc === "yes" })));
    const cv = $("[data-cvgo]", box);
    if (cv) cv.onclick = () => run(box, gid, { ...body, canaryValue: $("[data-cv]", box).value });
    $("[data-rerun]", box).onclick = () => run(box, gid, {});
  };
  const run = async (box, gid, body) => {
    box.innerHTML = `<h2>${esc(gid)}</h2><div class="loader">Running the four checks…</div>`;
    try { show(box, gid, await api(`/validation/${enc(gid)}/run`, { method: "POST", body }), body); }
    catch (e) { box.innerHTML = `<h2>${esc(gid)}</h2><div class="callout warn">${esc(e.message)}</div>`; }
  };
  await Promise.all(reg.map(async (r, i) => {
    const box = $(`#vg${i}`);
    const last = (await api(`/validation?group=${enc(r.id)}`))[0];
    if (last && last.passed) show(box, r.id, last, {});
    else await run(box, r.id, {});
  }));
}

ALIAS.validation = (arg) => (arg ? `onboard/~group/${enc(arg)}` : "onboard");
```

- [ ] **Step 5: Wire it in**

- In `legacy.js`, delete the `ROUTES.validation` block and its comment.
- Append to the task-layout CSS block:

```css
.checks { list-style: none; margin: 0; padding: 0; }
.check { border-top: 1px solid var(--rule); padding: 10px 0; }
.check:first-child { border-top: 0; }
.check .head { display: flex; gap: 10px; align-items: center; margin-bottom: 2px; }
.vgroup h2 { margin: 0; }
```

- [ ] **Step 6: Run the tests**

Run: `PY -m pytest tests -v`
Expected: all PASS (1 skipped).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(ui): per-source Deploy and Validate steps"
```

---

### Task 8: Move the reference screens into More and delete legacy.js

**Files:**
- Modify: `app/static/js/more.js` (receives `catalog`, `renderPlan`, `registry`, `deploy`, `coverage`, `api`, `admin`)
- Delete: `app/static/js/legacy.js`
- Modify: `app/static/js/main.js`, `app/static/styles.css` (remove unused rules)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: everything in `core.js` and `charts.js`.
- Produces: nothing new. Every `MORE_NAV` key has a route.

- [ ] **Step 1: Write the failing test (append to `tests/test_ui.py`)**

```python
@pytest.mark.parametrize("route", ["coverage", "registry", "catalog", "deploy", "api", "admin", "catalog/Okta%20Single%20Sign-On"])
def test_more_screens_use_page_header(flow, route):
    flow.as_role("admin")
    flow.goto(route)
    assert flow.page.locator("#main .ph h1").count() == 1
    assert flow.page.locator("text=Something went wrong").count() == 0


def test_no_legacy_module(flow):
    flow.goto("home")
    srcs = flow.page.evaluate("() => performance.getEntriesByType('resource').map(r => r.name)")
    assert not any(s.endswith("/legacy.js") for s in srcs)
    assert flow.errors == []
```

`Okta Single Sign-On` is the catalog folder of the Okta solution (checked against `GET /api/v1/catalog/solutions?q=okta` on 2026-10-24).

- [ ] **Step 2: Run it to make sure it fails**

Run: `PY -m pytest tests/test_ui.py -v -k "more_screens or legacy"`
Expected: FAIL (the legacy screens have no `.ph`; `legacy.js` is loaded).

- [ ] **Step 3: Move the screens**

1. Cut every remaining block out of `legacy.js` and paste it at the end of `more.js`: `ROUTES.catalog`, `renderPlan`, `ROUTES.registry`, `ROUTES.deploy`, `ROUTES.coverage`, `ROUTES.api` and `ROUTES.admin`.
2. Change the import lines of `more.js` to:

```js
import { ROUTES, $, $$, api, esc, num, pct, when, enc, ME, can, demoRole, toast, st, tier, layerTag, modal, jsyaml, pageHeader, disclose, renderNav, refreshPending, router, MORE_NAV } from "./core.js";
import { barChart, spark } from "./charts.js";
```

3. Apply these exact edits to the moved code. Each one replaces an `<h1>…</h1><p class="sub">…</p>` pair with `pageHeader`, keeping the wording but cutting the subtitle to one sentence:

| Screen | Replace the h1 + sub with |
|---|---|
| `ROUTES.catalog` | `${pageHeader("Connectors", "Every data connector in the Content hub, the tables it writes, and whether an ASIM parser exists.")}` |
| `renderPlan` | Keep the `<p><a href="#/catalog">← Connectors</a></p>` line, then `${pageHeader(p.solution.name, `${esc(p.solution.author)}. Plan where each table lives, then request the deployment.`)}` |
| `ROUTES.registry` (list) | `${pageHeader("Registry", "One entry per table and message format; the single definition every job builds from.", `<a class="btn" href="/api/v1/registry/export" target="_blank">Export YAML</a>`)}`, and delete the old Export YAML button inside the card |
| `ROUTES.registry` (one entry) | Keep the `← Registry` line, then `${pageHeader(gid, `${st(r.status)} version ${r.version}, last changed by ${esc(r.updated_by)} at ${when(r.updated_at)}`)}` |
| `ROUTES.deploy` | `${pageHeader("Build and deploy", "Every KQL job, the notebook configuration and the MCP queries, generated from the live registry.", `<a class="btn primary" href="/api/v1/build/bundle.zip">Download bundle</a>`)}`, and wrap the `<div class="card"><h2>Steps</h2>…</div>` content in `disclose("Portal steps", …)` |
| `ROUTES.coverage` | `${pageHeader("Coverage", "How deeply each source is indexed; status turns to review below 90% extraction and 70% template match.")}`, then insert before the table card: `<div class="card"><h2>Extraction rate by source</h2>${barChart(cov.slice().sort((a, b) => a.ExtractionRate - b.ExtractionRate).map((r) => ({ label: r.SourceGroup, value: r.ExtractionRate, status: r.Status, muted: r.Tier === 2, href: "#/coverage/" + enc(r.SourceGroup), note: `${num(r.RawRows)} raw rows · tier ${r.Tier}` })), { threshold: 0.9 })}</div>` and add `section` to the class of the table card |
| `ROUTES.api` | `${pageHeader("API and agents", "Every screen is built on the REST API; agents connect through the MCP endpoint and cannot approve changes.")}` |
| `ROUTES.admin` | `${pageHeader("Settings and audit", "Settings come from the container's environment variables; change them there and restart the revision.")}` |

4. In the moved `renderPlan`, the success handler navigates to `#/approve` (changed in Task 6). Make it go there only for Admins: replace the single line that starts `try { const r = await api("/deployments"` with the line below, and keep the `catch (e) { toast(e.message, true); }` line that follows it.

```js
    try { const r = await api("/deployments", { method: "POST", body }); toast(`Approval #${r.approval} requested`); await refreshPending(); if (can("admin")) location.hash = "#/approve"; }
```

5. In the moved coverage `explain()`, the "It carries entities" link guesses the table from the group ID, which is wrong for `CEF:…` groups. Fix it.
   - Add this as the first line of `explain`:

     ```js
     const table = (cov.find((c) => c.SourceGroup === id) || {}).SourceTable || id.split(":")[0];
     ```

   - Change the link from `#/review/${enc(id.split(":")[0])}` to `#/onboard/${enc(table)}/fields`.

- [ ] **Step 4: Delete `legacy.js` and its import**

Delete `app/static/js/legacy.js`. The final `main.js`:

```js
/* Entry point: each module registers its screens in ROUTES, then the app starts. */
import { start } from "./core.js";
import "./home.js";
import "./hunt.js";
import "./onboard.js";
import "./fields.js";
import "./approve.js";
import "./more.js";

start();
```

- [ ] **Step 5: Remove CSS rules nothing uses any more**

Search for `.pipe`, `.lane`, `.grp`, `.storyline`, `.foot` and `.sticky-side` in `app/static/js/*.js`:

Run: `PY -c "import pathlib,re;t=''.join(p.read_text(encoding='utf-8') for p in pathlib.Path('app/static/js').glob('*.js'));print([c for c in ['pipe','lane','grp','storyline','foot','sticky-side'] if re.search(r'\b'+c+r'\b',t)])"`

Then delete the `styles.css` rules for every class the command did **not** print (expected: `.pipe`, `.lane`, `.lane h4`, `nav.side .grp`, `.storyline`, `.foot`). Keep the rest.

- [ ] **Step 6: Run the tests**

Run: `PY -m pytest tests -v`
Expected: all PASS (1 skipped).

- [ ] **Step 7: Check at phone width and in dark theme**

Run `PY -m uvicorn app.main:app --port 8091`. In a browser at 390 px wide and at 1440 px, open Home, Hunt (`203.0.113.45`), Onboard → BadgeReader_CL → fields, and Approve, in both the Light and Dark theme. Confirm there is no horizontal page scroll (wide tables scroll inside `.tbl-wrap`), all text is readable, and the burger menu shows the nav. Fix any issue in `styles.css` before committing.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(ui): reference screens under More with page headers; remove legacy module"
```

---

### Task 9: Demo recorder, screenshots and README

**Files:**
- Create: `tools/record_demo.py`
- Modify: `requirements-dev.txt` (add `imageio-ffmpeg`), `tests/ui_flows.py` (`home_tour`, `hunt_story`)
- Modify: `README.md`
- Replace: `docs/screenshots/*.png`
- Create: `docs/demo/lakehunt-demo.mp4`, `docs/demo/lakehunt-hunt.gif`

**Interfaces:**
- Consumes: `demo_server`, `Flow` and every flow method above.
- Produces: `python tools/record_demo.py [--screenshots] [--keep-webm]`.

- [ ] **Step 1: Add the dependency**

Append `imageio-ffmpeg` to `requirements-dev.txt`, then run: `PY -m pip install imageio-ffmpeg`
Expected: installed; `PY -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"` prints a path to an `ffmpeg` executable.

- [ ] **Step 2: Add the two storyboard flows to `Flow` in `tests/ui_flows.py`**

```python
    # ---- storyboard pieces used only by the recorder
    def home_tour(self) -> None:
        p = self.page
        self.goto("home")
        self.say("Each day starts from what needs a person: three jobs, and one list of what needs attention.")
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
```

- [ ] **Step 3: Write `tools/record_demo.py`**

```python
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
        f = Flow(page, base, animate=True)
        mark = lambda: time.monotonic() - t0  # noqa: E731

        title_card(page, "LevelBlue Lake Hunt", ["One search across every Sentinel data lake source.",
                                                 "A walk through the three jobs, for the admins who run it."])
        page.wait_for_timeout(5000)
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
        page.locator("#submit").click(); page.wait_for_selector("text=Waiting for an Admin")
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
```

- [ ] **Step 4: Record and check the output**

Run: `PY tools/record_demo.py --screenshots`
Expected:
- It prints the two output paths and the screenshots folder.
- `docs/demo/lakehunt-demo.mp4` is roughly 2.5–4 minutes long. Check with `PY -c "import imageio_ffmpeg as f;print(f.count_frames_and_secs('docs/demo/lakehunt-demo.mp4'))"`.
- `lakehunt-hunt.gif` is under 15 MB.

Watch the MP4 all the way through. Confirm:
- Every caption is readable and on screen long enough to read.
- The cursor reaches each control before it is clicked.
- No caption covers the control being clicked.
- The jsmith hunt shows the BadgeReader_CL lane.

If a caption covers a control, raise `bottom` in `#lh-cap` or scroll the target higher in that flow, then re-record.

- [ ] **Step 5: Update `README.md`**

1. Replace the screenshot references: `docs/screenshots/01-overview.png` → `01-home.png`, `03-field-review.png` → `02-onboard-fields.png`. `04-hunt.png` keeps its name.
2. Replace the "What it does" table with:

```markdown
| Screen | Purpose |
|---|---|
| Home | The three jobs (Hunt, Onboard a source, Review and approve) with live counts, and one Needs attention list: sources to review, sources below the 90% extraction target, checks waiting on a person, pending approvals. |
| Hunt | One search for an IP, a user in any format, a host, URL or hash. A one-line summary, a timeline per source, and tabs for where it appears, events, sign-ins, network sessions and entities seen with it. Every row opens the original log line. A pasted list becomes pick-one chips. |
| Onboard | One flow per source: pick source → decide fields → preview → submit → deploy → validate. Fields are one-line rows with a recommendation; Change opens the plain-language choices. Generated YAML and KQL stay folded. |
| Approve | An inbox of pending changes. Each card says in plain words what the change does, with the preview numbers. Approve, or reject with a reason. Admins only. |
| More | Coverage (extraction per source and drift), Registry (versions, YAML export), Connectors (Content hub catalog and plans), Build and deploy (all jobs and the bundle), API and agents, Settings and audit, About. |
```

3. Add this section after "Run the demo locally":

```markdown
## Demo video

`docs/demo/lakehunt-demo.mp4` (about 3 minutes) walks through the three jobs for an admin audience: onboarding the badge reader as an Analyst, approving it as an Admin, deploying and validating it, then hunting the planted incident. `docs/demo/lakehunt-hunt.gif` is the Hunt chapter alone.

To re-record after a UI change (a fresh demo instance runs on port 8090; nothing else is touched):

    pip install -r requirements-dev.txt
    python -m playwright install chromium
    python tools/record_demo.py --screenshots
```

4. In the "Checks run on this build" table, change the pytest row to: `18 API tests and the browser tests in tests/test_ui.py (Home, role-based navigation, Hunt, the full onboarding flow, Approve, validation) pass`.
5. In the Layout block, replace `static/            web UI (plain JavaScript, no build step)` with `static/            web UI: index.html, styles.css and js/ (plain ES modules, no build step)`, and add `tools/              catalog builder, demo recorder`.

- [ ] **Step 6: Run the full suite one last time**

Run: `PY -m pytest tests -v`
Expected: all PASS (1 skipped).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(demo): recorded demo video, Hunt GIF and refreshed screenshots"
```
