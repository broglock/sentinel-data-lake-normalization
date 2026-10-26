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


def nav_keys(flow):
    return set(flow.page.locator("#nav a[data-nav]").evaluate_all("els => els.map(e => e.dataset.nav)"))


def test_home_shows_jobs_and_attention(flow):
    flow.as_role("admin")
    flow.goto("home")
    assert flow.page.locator(".task").count() == 3
    assert flow.page.locator(".att", has_text="BadgeReader_CL").count() == 1
    assert flow.page.locator("#nav a.on[data-nav=home]").count() == 1


def test_home_counts_read_naturally(flow):
    # before onboarding, exactly one source (BadgeReader_CL) needs field review
    text = flow.page.locator(".task", has_text="Onboard a source").locator(".task-n").inner_text()
    assert text == "1 source needs review"


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
    assert flow.page.locator(".task h2").get_by_text("Coverage", exact=True).count() == 1
    flow.goto("about")
    assert flow.page.locator("text=ASIM parser").first.is_visible()


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


def test_preview_detail_collapsed_and_survives_reload(flow):
    flow.page.goto(flow.base + "/#/onboard/BadgeReader_CL/preview")
    flow.page.reload()                                                 # a hash change alone keeps the page; reload drops in-memory decisions
    flow.page.wait_for_selector("#pv .kpi")
    assert flow.page.locator("#pv .st", has_text="90%").count() == 1
    code = flow.page.locator("details.more", has_text="Show generated code")
    assert code.count() == 1 and code.get_attribute("open") is None
    assert flow.page.locator("#pv .pair").count() <= 3
    # undecided fields are submitted with their recommendation; the warning must say so
    assert flow.page.locator(".callout.warn", has_text="recommendation").is_visible()


def test_analyst_submits_badge_reader(flow):
    flow.as_role("analyst")
    flow.open_onboarding("BadgeReader_CL")
    flow.decide_all_fields()
    flow.preview_and_submit()
    assert flow.page.locator("#main", has_text="Approval #").is_visible()
    assert flow.page.url.endswith("#/onboard/BadgeReader_CL/submit")
    assert flow.page.locator('#nav a[data-nav="approve"]').count() == 0     # analysts do not approve


def test_reject_needs_reason(flow):
    flow.as_role("admin")
    flow.page.goto(flow.base + "/#/approvals")
    flow.page.wait_for_url("**/#/approve")
    card = flow.page.locator("section.approval", has_text="BadgeReader_CL").first
    card.wait_for()
    assert card.locator("[data-noconfirm]").is_hidden()         # the reason box stays folded until Reject
    card.locator("[data-no]").click()
    assert card.locator("[data-noconfirm]").is_visible()
    card.locator("[data-noconfirm]").click()
    assert flow.page.locator(".toast.err", has_text="reason").is_visible()
    assert card.is_visible()                                   # still pending


def test_admin_approves_badge_reader(flow):
    flow.approve_pending("BadgeReader_CL")
    details = flow.page.locator("details.more", has_text="History")
    details.wait_for()                                         # the inbox re-renders after the approval toast
    assert flow.page.locator("section.approval", has_text="BadgeReader_CL").count() == 0
    assert details.count() == 1 and details.get_attribute("open") is None


def set_stage(flow, table, stage):
    r = flow.page.request.post(f"{flow.base}/api/v1/onboarding/{table}/stage", data={"stage": stage, "note": "test"},
                               headers={"X-LakeHunt-Demo-Role": "analyst"})
    assert r.ok, r.text()


def test_approved_in_live_mode_points_to_deploy(flow):
    # live mode leaves an approved source at stage "registry" until someone creates the jobs; emulate that
    flow.as_role("analyst")
    set_stage(flow, "BadgeReader_CL", "registry")
    flow.goto("onboard")
    assert flow.page.locator(".att", has_text="BadgeReader_CL").get_by_role("link").inner_text() == "Deploy"
    flow.goto("onboard/BadgeReader_CL/submit")
    assert flow.page.locator("#main h2", has_text="Approved").is_visible()
    assert flow.page.locator("ol.stepper .step a", has_text="Deploy").count() == 1
    flow.goto("onboard/BadgeReader_CL/deploy")
    flow.click(flow.page.locator("#markdep"))
    flow.page.wait_for_url("**/#/onboard/BadgeReader_CL/validate")
    flow.page.locator(".vgroup [data-rerun]").first.wait_for()
    set_stage(flow, "BadgeReader_CL", "deployed")              # hand the next test the demo-mode state


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
    flow.page.wait_for_selector(".vgroup [data-rerun]")
    assert flow.page.locator(".vgroup").count() >= 2


def test_badge_reader_now_in_jsmith_hunt(flow):
    flow.hunt("jsmith@contoso.com")
    assert flow.page.locator("#htab", has_text="BadgeReader_CL:main").count() == 1


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


def test_nav_more_label_shows_arrow(flow):
    flow.goto("home")
    after = flow.page.evaluate("() => getComputedStyle(document.querySelector('#nav details.nav-more > summary'), '::after').content")
    assert after in ('" ▾"', '" ▴"')



def test_opening_validate_keeps_live_source_live(flow):
    flow.as_role("analyst")
    flow.goto("onboard/AWSCloudTrail/validate")
    flow.page.locator(".vgroup [data-rerun]").first.wait_for()
    flow.page.wait_for_timeout(500)
    st = flow.page.request.get(flow.base + "/api/v1/onboarding/AWSCloudTrail").json()["stage"]
    assert (st or {}).get("stage", "live") == "live"


def test_fast_navigation_shows_the_latest_screen(flow):
    flow.as_role("analyst")
    flow.goto("home")
    flow.page.evaluate("() => { location.hash = '#/onboard/CommonSecurityLog/fields'; setTimeout(() => { location.hash = '#/hunt'; }, 30); }")
    flow.page.wait_for_timeout(2500)
    assert flow.page.locator("#hv").is_visible()
    assert flow.page.locator("#preset").count() == 0


def test_tooltips_escape_log_values(flow):
    flow.goto("home")
    res = flow.page.evaluate("""async () => {
      window.__xss = 0;
      const m = await import('/static/js/charts.js');
      const evil = '<img src=x onerror="window.__xss=1">';
      const host = document.createElement('div'); document.body.appendChild(host);
      host.innerHTML = m.timelineChart([{SourceGroup: evil, EventStartTime: '2026-10-22T09:00:00Z', EventType: evil, EventResult: 'Failure', MatchedAs: evil, Entities: [evil]}])
        + m.barChart([{label: evil, value: 0.5, note: evil}]);
      let imgs = 0;
      for (const el of host.querySelectorAll('[data-tip]')) {
        el.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: 10, clientY: 10}));
        imgs += document.getElementById('tip').querySelectorAll('img').length;
      }
      await new Promise((r) => setTimeout(r, 300));
      host.remove();
      return {xss: window.__xss, imgs};
    }""")
    assert res == {"xss": 0, "imgs": 0}


BADGE_DECISIONS = {"id": "BadgeReader_CL:main", "preset": "physical", "vendor": "Contoso", "product": "Badge readers",
                   "fields": [{"field": "RawData.holder", "kind": "kv", "entity": "user", "role": "Actor", "asim": "ActorUsername"},
                              {"field": "RawData.reader", "kind": "kv", "entity": "ip", "role": "Dvc", "asim": "DvcIpAddr"}],
                   "result": {"field": "RawData.result", "kind": "kv", "map": {"granted": "Success", "denied": "Failure"}},
                   "text_column": "RawData", "templates": []}


def test_rejection_reason_reaches_the_analyst(flow):
    # runs last: a rejected registry change sends the table back to review
    r = flow.page.request.post(flow.base + "/api/v1/registry/from-decisions/BadgeReader_CL", data={"decisions": BADGE_DECISIONS, "submit": True},
                               headers={"X-LakeHunt-Demo-Role": "analyst"})
    assert r.ok, r.text()
    flow.as_role("admin")
    flow.goto("approve")
    card = flow.page.locator("section.approval", has_text="BadgeReader_CL").first
    card.locator("[data-no]").click()
    card.locator("input[aria-label='Reason for rejecting']").fill("Holder should be the Target")
    card.locator("[data-noconfirm]").click()
    flow.page.locator(".toast", has_text="Rejected #").wait_for()
    flow.as_role("analyst")
    flow.goto("home")
    assert flow.page.locator(".att", has_text="BadgeReader_CL").filter(has_text="Holder should be the Target").count() == 1
    flow.goto("onboard/BadgeReader_CL/fields")
    assert flow.page.locator(".callout", has_text="Holder should be the Target").is_visible()
