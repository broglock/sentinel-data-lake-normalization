# Task-focused web UI and recorded demo: design

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.

## Intent

**What the user asked for:** an animated demo of how the web UI is used operationally, and a cleanup of the web UI so it is focused on specific tasks; today it is "way too busy".

**Agreed decisions:**

- The UI is organized around three jobs: Hunt, Onboard a source, Review and approve.
- Approach: restructure inside the existing plain-JavaScript frontend (no build step). The REST API, MCP server and engine do not change.
- The demo is a recorded video (MP4, plus a GIF of the Hunt chapter) for customer admins. It emphasises control points, approvals and day-to-day effort.

**Assumptions (not stated by the user):**

- Work is in demo mode; live-mode behaviour of screens is preserved but not re-tested against a tenant.
- The cleaned-up UI replaces the current one (no toggle back to the old layout).
- Existing screenshots in `docs/screenshots/` are regenerated after the cleanup.

**Success criteria:**

1. A person can complete each of the three jobs from Home without visiting a screen under More.
2. Each screen has one primary action and at most one sentence of subtitle; detail (YAML, KQL, evidence, raw JSON) is collapsed by default.
3. All 18 existing tests pass unchanged; a new Playwright UI test walks the three jobs on demo data.
4. `tools/record_demo.py` produces `docs/demo/lakehunt-demo.mp4` (about 3 minutes) and `docs/demo/lakehunt-hunt.gif` from a fresh demo instance, without touching other running instances.

## 1. Structure

**Navigation:** Home · Hunt · Onboard · Approve (pending-count badge) · More ▾

- **More** holds: Coverage, Registry, Connectors (catalog), Build and deploy (full bundle), API and agents, Settings and audit, About (the "why an index" explainer).
- **Role-aware visibility** (UI only; the API's role checks stay as they are):
  - Viewer: Home, Hunt, More (read-only screens).
  - Analyst: adds Onboard.
  - Admin: adds Approve and Settings and audit.

**Home** (replaces Overview):

- Three task cards with live counts: Hunt (search box on the card), Onboard a source ("N sources need review"), Review and approve ("N changes waiting").
- One **Needs attention** list merging: sources needing field review, sources below the 90% extraction target, validations waiting on a person, pending approvals. Each row has one button to the fix.
- Removed from Home: KPI tiles, extraction chart (to Coverage), "why an index" explainer (to About), onboarding pipeline chips, recent validations, job budget.

**Onboard:** one flow per source, with a stepper mapped to the existing stages:

| Step | Stage(s) covered | Replaces |
|---|---|---|
| 1 Pick source | detected | Sources list and pipeline |
| 2 Decide fields | proposed, in_review | Field review (left column) |
| 3 Preview | in_review | Field review live-preview panel |
| 4 Submit | registry (awaiting approval) | Submit buttons on review/registry |
| 5 Deploy | deployed | Build and deploy, filtered to this source |
| 6 Validate | validating → live | Validation, for this source |

The Onboard landing page lists sources grouped by stage, each with its one next action. "Plan a new connector" links to More > Connectors.

**Approve:** an inbox of pending changes (cards); history collapsed below.

**Routing:** existing hashes keep working. `#/overview` → Home, `#/sources` → Onboard, `#/review/<table>` → Onboard step 2 for that table, `#/validation/<group>` → Onboard step 6, `#/approvals` → Approve. Other existing routes stay under More.

## 2. Screens

**Shared rules:** a page header (title, one sentence at most, primary action on the right); one primary action per screen; no cards nested in cards; detail behind "Show details" (`<details>`); same LevelBlue palette and CSS tokens in `styles.css`.

**Hunt:**

- Results open with a one-line summary: sources, events, failures and successes.
- Then the timeline, then **Where it appears**.
- Sign-ins, Network sessions and Seen with it move into tabs.
- Raw pivot unchanged.
- **Multiple values:** input containing commas or line breaks is split into chips with "Hunt one value at a time — pick one"; no search runs until one is picked.

**Decide fields (step 2):**

- One row per field: name, plain-language recommendation, confidence badge, Accept, Change.
- Change expands the existing decision card (value class, role, evidence, effect).
- High-confidence fields are grouped first under "Accept all N high-confidence".
- Source-type preset is one dropdown at the top.
- The progress bar stays.

**Preview (step 3):**

- Extraction rate (target 90%) and template match (target 70%), each with a pass or below-target badge.
- Entity counts by type and role.
- Three raw → index row pairs.
- "Show generated code" (YAML and lake KQL), collapsed.
- Primary action: Submit for approval (step 4 confirms the request and shows its approval number).

**Deploy (step 5):** the KQL job(s) and notebook group for this source only, the portal steps, and "Download bundle". In demo mode, "Re-run index now".

**Validate (step 6):**

- The four checks as a checklist; the automatic checks run when the step opens.
- The person's check shows three row pairs with "The rows match" and "Something is wrong".
- The canary input appears only when needed.

**Approve card:**

- Number, title, requester and time.
- "What this changes" in 2–3 plain bullets derived from the payload: table, field roles, KQL job count against the limit. For deployments: solutions installed and tables created with plan and retention.
- The preview numbers when available.
- Approve, and Reject with reason.
- YAML and the request JSON collapsed.

**Screens under More** keep their content, with the shared rules applied (header, collapsed detail).

## 3. Code structure

- `app/static/app.js` (809 lines) is split by job into plain ES modules loaded with `<script type="module">`, no build step:
  - `static/js/core.js`: api, helpers, router, nav.
  - One file each for `home`, `hunt`, `onboard`, `approve` and `more`.
  - `static/js/charts.js`: the existing bar and timeline renderers.
- Existing helper functions (`api`, `esc`, `st`, `barChart`, `timelineChart`, `modal`, `toast`) move unchanged into `core.js` or `charts.js`.
- Backend: no API changes required. If "What this changes" or Needs attention needs data the current endpoints lack, it is computed client-side from existing responses: `/overview`, `/tables`, `/approvals`, `/validation`, `/build`.

## 4. Testing

- `python -m pytest tests`: the existing 18 tests pass unchanged.
- New `tests/test_ui.py` (Playwright, Chromium, skipped if browsers are not installed):
  - Starts the app on a free port with a temporary data directory.
  - Home shows the three cards and BadgeReader_CL in Needs attention.
  - Analyst onboards BadgeReader_CL through steps 1–4.
  - Admin approves it from Approve.
  - Steps 5–6 pass validation, including the person's check.
  - Hunt for `203.0.113.45` shows at least 3 sources.
  - Hunt with a comma-separated list shows chips.
  - A Viewer does not see Onboard or Approve.
- Manual check: each screen at 1440×900 and at phone width, light and dark themes.

## 5. Demo video

Audience: customer admins. Length: about 3 minutes.

| # | Chapter | Shown | Caption focus |
|---|---|---|---|
| 0 | Title (5s) | "Lake Hunt: one search across every Sentinel data lake source" | n/a |
| 1 | Home (15s) | The three jobs; BadgeReader_CL needs attention | Each day starts from what needs a person |
| 2 | Onboard as Analyst (60s) | Pick → preset → accept high-confidence → change one field → preview passes → submit | No ASIM names typed; nothing is live yet |
| 3 | Approve as Admin (30s) | Switch role → What this changes → Approve → audit entry | Every change waits for an Admin and is audited |
| 4 | Deploy and validate (30s) | This source's KQL job and portal steps → four checks | The one manual portal step; checks prove it works |
| 5 | Hunt as Analyst (45s) | 203.0.113.45 → spray → Entra success → AWS → jsmith → badge-in before the "remote" sign-in → Raw | One search across every source, back to the original log line |
| 6 | Close (10s) | Approvals, audit, agents cannot approve, data is synthetic | n/a |

**Implementation (`tools/record_demo.py`):**

- Starts a fresh demo instance on port 8090 with a temporary data directory.
- Records with Playwright Chromium at 1440×900 (WebM).
- Injects a caption bar, a visible cursor and click highlights through `page.evaluate`, so they are in the recording.
- Uses a pace per action tuned for reading.
- Converts to MP4 (H.264) and a Hunt-chapter GIF (about 45 s, reduced frame rate and width) with the ffmpeg binary from the `imageio-ffmpeg` pip package. It is added to `requirements-dev.txt`; nothing is installed system-wide.
- Writes to `docs/demo/`.
- Reuses the page-driving helpers from `tests/test_ui.py` where practical, so the demo and the test follow the same flows.

## Out of scope

- Any REST API, MCP, engine or deployment change.
- A framework rewrite or build step.
- Live-mode testing against a tenant.
- Voice-over audio.
