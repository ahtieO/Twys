"""Standalone browser checks against a running, isolated TWYS development server.

Example (the server MUST use a disposable TWYS_DATA_DIR):
    TWYS_TEST_URL=http://127.0.0.1:8765 TWYS_TEST_ALLOW_LOCAL_MUTATIONS=1 \
        python tests/browser_smoke.py

Playwright and Chromium are separate developer tools, not runtime dependencies.
Synthetic journal/image fixtures exist only in browser routes, never in SQLite.
Optional internet providers are deliberately unavailable in this smoke test;
their availability and real Windows desktop behavior require separate checks.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


BASE = os.environ.get("TWYS_TEST_URL", "http://127.0.0.1:8000").rstrip("/")
OUTPUT = Path(os.environ.get("TWYS_TEST_OUTPUT", "/tmp/twys-browser"))
LABEL = re.sub(r"[^a-zA-Z0-9_-]", "-", os.environ.get("TWYS_TEST_LABEL", "smoke"))
UID = "a" * 20
TRADE = {
    "uid": UID, "instrument": "EURUSD", "source": "synthetic_ui_test",
    "traded_at": "2026-01-01T12:00:00Z", "direction": "LONG",
    "outcome": "unknown", "realized_r": None, "verified_realized_r": None,
    "planned_r": None, "requires_r_review": False, "r_basis": None,
    "rules_followed": None, "rating": None, "emotion": None,
    "session": None, "timeframe": None, "outcome_basis": None,
    "entry_price": None, "stop_price": None, "exit_price": None,
    "lots": None, "net_pnl": None, "mentions": [], "flags": [],
    "reasoning": "SYNTHETIC UI TEST — browser-only fixture, not a user trade.",
    "mistake": None, "review": None, "markdown": None, "original_json": {},
    "images": [{"name": "Synthetic chart A", "file": "test-a.svg"},
               {"name": "Synthetic chart B", "file": "test-b.svg"}],
}


def synthetic_image(index: int) -> str:
    color = "#74d6b0" if index == 0 else "#8daff5"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600" viewBox="0 0 960 600">
<rect width="960" height="600" fill="#10151c"/>
<path d="M60 160H900M60 260H900M60 360H900M60 460H900M200 100V500M400 100V500M600 100V500M800 100V500" stroke="#26323e"/>
<path d="M60 430L180 330L280 370L380 280L500 320L620 180L760 240L900 120" fill="none" stroke="{color}" stroke-width="5"/>
<text x="60" y="60" fill="#f1f3f6" font-family="Arial" font-size="25">SYNTHETIC UI TEST · CHART {index + 1}</text>
<text x="60" y="555" fill="#97a4b5" font-family="Arial" font-size="20">Browser fixture only · no market prices or user journal data</text></svg>'''


def main() -> None:
    if os.environ.get("TWYS_TEST_ALLOW_LOCAL_MUTATIONS") != "1":
        raise SystemExit("Use a disposable TWYS_DATA_DIR for the server, then set "
                         "TWYS_TEST_ALLOW_LOCAL_MUTATIONS=1. This checks real favorite persistence.")
    if urlparse(BASE).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Browser smoke accepts a loopback server only.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {"url": BASE, "status": "running", "checks": [], "page_errors": [],
              "external_requests_stubbed": [], "screenshots": [],
              "scope": "Local browser functionality; optional external providers stubbed. "
                       "Synthetic journal records are browser-only route fixtures."}
    fixtures = {"journal": False}
    origin = urlparse(BASE).netloc

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("TWYS_TEST_CHROMIUM", "/usr/bin/chromium"),
            headless=True, args=["--no-sandbox"],
        )
        context = browser.new_context(viewport={"width": 1450, "height": 1000},
                                      reduced_motion="no-preference")
        page = context.new_page()
        page.set_default_timeout(12000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        initial_favorites = None

        def fulfilled(route, body):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

        def route_request(route):
            parsed = urlparse(route.request.url)
            path = parsed.path
            if parsed.netloc != origin:
                report["external_requests_stubbed"].append(parsed.netloc)
                # Empty successful scripts avoid network-error noise while explicitly
                # exercising TWYS's missing-provider fallback. No external code runs.
                route.fulfill(status=200, content_type="application/javascript", body="")
                return
            if path.startswith("/api/v2/markets/") and path.endswith("/positioning"):
                fulfilled(route, {"records": [], "errors": ["Offline browser test"]})
            elif path.startswith("/api/v2/markets/") and path.endswith("/social"):
                fulfilled(route, {"items": [], "searches": [], "status": "unavailable"})
            elif path == "/api/v2/calendar":
                fulfilled(route, {"events": [], "provider": "Browser test", "status": "unavailable",
                                  "message": "External feeds disabled for this local UI check."})
            elif path == "/api/v2/news":
                fulfilled(route, {"items": [], "status": "unavailable", "warnings": []})
            elif path == "/api/v2/macro":
                fulfilled(route, {"series": [], "scenarios": [], "methodology": "Offline browser test"})
            elif path == "/api/v2/macro/news":
                fulfilled(route, {"events": [], "headlines": [], "note": "Offline browser test"})
            elif path in {"/api/v2/symbols/crypto", "/api/v2/symbols/provider"}:
                fulfilled(route, {"results": [], "status": "unavailable"})
            elif path == "/api/v2/coverage" and fixtures["journal"]:
                fulfilled(route, {"records": 1, "fields": {}, "sections": {
                    "records": True, "screenshot_review": True, "performance": False,
                    "setup": False, "psychology": False}})
            elif path == "/api/trades" and fixtures["journal"]:
                query = parse_qs(parsed.query).get("q", [""])[0].lower()
                rows = [TRADE] if not query or query in json.dumps(TRADE).lower() else []
                fulfilled(route, {"rows": rows, "total": len(rows), "metrics": {
                    "win_rate": None, "mean_r": None, "r_coverage": 0}})
            elif path == "/api/facets" and fixtures["journal"]:
                fulfilled(route, {"instrument": [{"value": "EURUSD", "count": 1}]})
            elif path == f"/api/trade/{UID}":
                fulfilled(route, TRADE)
            elif path.startswith(f"/api/trade/{UID}/image/"):
                route.fulfill(status=200, content_type="image/svg+xml",
                              body=synthetic_image(int(path.rsplit("/", 1)[1])))
            else:
                route.continue_()

        context.route("**/*", route_request)

        def checked(message):
            report["checks"].append(message)

        def screenshot(name):
            filename = OUTPUT / f"{LABEL}-{name}.png"
            page.screenshot(path=str(filename), full_page=True, animations="disabled")
            report["screenshots"].append(str(filename))

        def navigate(name):
            page.locator(f'.nav-item[data-page="{name}"]').click()
            expect(page.locator(f'.nav-item[data-page="{name}"]')).to_have_class(re.compile("active"))
            expect(page.locator(f'.nav-item[data-page="{name}"]')).to_have_attribute("aria-current", "page")
            expect(page.locator('.nav-item[aria-current="page"]')).to_have_count(1)

        def assert_focus_trapped(dialog_selector):
            # Find visible interactive descendants rather than relying on a fixed
            # control count; the source drawer's content is loaded asynchronously.
            page.locator(dialog_selector).evaluate("""dialog => {
                const controls = [...dialog.querySelectorAll('button, a[href], input, select, textarea, [tabindex]')]
                    .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);
                if (!controls.length) throw new Error('Dialog has no keyboard controls');
                controls.at(-1).focus();
            }""")
            page.keyboard.press("Tab")
            assert page.locator(dialog_selector).evaluate("""dialog => {
                const first = [...dialog.querySelectorAll('button, a[href], input, select, textarea, [tabindex]')]
                    .find(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);
                return first === document.activeElement;
            }"""), f"Tab escaped {dialog_selector}"
            page.keyboard.press("Shift+Tab")
            assert page.locator(dialog_selector).evaluate("""dialog => {
                const controls = [...dialog.querySelectorAll('button, a[href], input, select, textarea, [tabindex]')]
                    .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);
                return controls.at(-1) === document.activeElement;
            }"""), f"Shift+Tab escaped {dialog_selector}"

        try:
            health = context.request.get(BASE + "/api/health")
            assert health.ok, f"Health failed: {health.status}"
            saved = context.request.get(BASE + "/api/v2/favorites")
            assert saved.ok
            initial_favorites = saved.json()["symbols"]
            page.goto(BASE, wait_until="domcontentloaded")
            expect(page.locator(".v22-markethead h1")).to_contain_text("XAUUSD")
            expect(page.locator("#v22-fav")).to_be_visible()
            expect(page.locator(".identity .brandtext b")).to_have_text("TWYS")
            expect(page.locator("#theme-switch")).to_be_visible()
            expect(page.locator('.nav-item[data-page="marketdesk"]')).to_have_attribute("aria-current", "page")
            screenshot("markets")
            checked("Real application startup, Markets rendering, supplied TWYS logo and accessible navigation state")

            # Real local API and persistent favorite data, restored in finally.
            original = "XAUUSD" in initial_favorites
            page.locator("#v22-fav").click()
            expect(page.locator("#v22-fav")).to_contain_text(
                "Add to Watchlist" if original else "Watchlisted")
            saved_after = context.request.get(BASE + "/api/v2/favorites").json()["symbols"]
            assert ("XAUUSD" in saved_after) != original
            if original:
                page.locator("#v22-fav").click()
                expect(page.locator("#v22-fav")).to_contain_text("Watchlisted")
            navigate("watchlist")
            expect(page.locator('[data-v24-watch="XAUUSD"]')).to_be_visible()
            page.locator('[data-v24-watch="XAUUSD"]').click()
            expect(page.locator("#v24-watch-title")).to_contain_text("XAUUSD")
            checked("Favorite toggle persists through real local API and Watchlist navigation")

            page.locator("#global-search-button").click()
            expect(page.locator("#global-query")).to_be_focused()
            assert_focus_trapped("#global-search-overlay")
            page.keyboard.press("Escape")
            expect(page.locator("#global-search-overlay")).to_be_hidden()
            expect(page.locator("#global-search-button")).to_be_focused()
            assert not page.locator("#app").evaluate("el => el.inert")
            page.locator("#global-search-button").click()
            page.locator("#global-query").fill("EURUSD")
            expect(page.locator('.v2-searchhit[data-id="EURUSD"]').first).to_be_visible()
            page.locator('.v2-searchhit[data-id="EURUSD"]').first.click()
            expect(page.locator(".v22-markethead h1")).to_contain_text("EURUSD")
            page.keyboard.press("Control+k")
            expect(page.locator("#global-search-overlay")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.locator("#global-search-overlay")).to_be_hidden()
            checked("Real local market search, Ctrl+K / Escape, search focus trap and opener restoration")

            navigate("journal22")
            expect(page.locator("#v22-connectnotion")).to_be_visible()
            checked("Empty journal renders connection guidance without invented trades")

            navigate("newsdesk")
            expect(page.locator("#v22-news-calendar")).to_contain_text("No verified economic events")
            navigate("macro")
            expect(page.locator("#v24-macro-theories")).to_contain_text("Offline browser test")
            navigate("connections")
            expect(page.locator("#v2-notiontoken")).to_be_visible()
            expect(page.locator("#v2-saveproviders")).to_be_visible()
            navigate("data")
            expect(page.locator("#import-submit")).to_be_disabled()
            checked("News/Macro unavailable-feed states, connection controls and Data import navigation")

            fixtures["journal"] = True
            # Re-evaluate coverage only to expose the normal conditional Chart Review
            # navigation. All synthetic journal results remain browser route mocks.
            page.evaluate("v2RefreshCoverage()")
            navigate("marketdesk")
            expect(page.locator(".v22-markethead")).to_be_visible()
            navigate("journal22")
            expect(page.locator(f'tr[data-trade="{UID}"]')).to_be_visible()
            page.locator("#trade-search").fill("no-such-synthetic-record")
            expect(page.locator("#trade-count")).to_have_text("0 MATCHING TRADES")
            page.locator("#trade-search").fill("EURUSD")
            expect(page.locator("#trade-count")).to_have_text("1 MATCHING TRADES")
            page.locator(f'tr[data-trade="{UID}"]').click()
            expect(page.locator("#drawer-content")).to_contain_text("SYNTHETIC UI TEST")
            assert_focus_trapped("#overlay")
            page.keyboard.press("Escape")
            expect(page.locator("#overlay")).to_be_hidden()
            checked("Synthetic browser-only journal search, source details and Escape close")

            navigate("screenshots")
            expect(page.locator("[data-photo-index]")).to_have_count(2)
            page.locator('[data-photo-index="0"] .thumb').click()
            expect(page.locator("#lightbox")).to_be_visible()
            assert_focus_trapped("#lightbox")
            expect(page.locator("#v28-photo-caption")).to_contain_text("1 / 2")
            page.wait_for_function("document.querySelector('#lightbox-image').naturalWidth > 0")
            page.keyboard.press("ArrowRight")
            expect(page.locator("#v28-photo-caption")).to_contain_text("2 / 2")
            page.keyboard.press("ArrowLeft")
            expect(page.locator("#v28-photo-caption")).to_contain_text("1 / 2")
            page.locator("#lightbox-image").click()
            expect(page.locator("#lightbox-image")).to_have_class(re.compile("v28-photo-zoom"))
            page.locator("#lightbox-image").click()
            screenshot("gallery-viewer")
            page.keyboard.press("Escape")
            expect(page.locator("#lightbox")).to_be_hidden()
            page.locator("[data-view-trade]").first.click()
            expect(page.locator("#overlay")).to_be_visible()
            expect(page.locator("#lightbox")).to_be_hidden()
            expect(page.locator("#drawer-content")).to_contain_text("SYNTHETIC UI TEST")
            assert_focus_trapped("#overlay")
            # Close and reopen to verify the actual clicked source button receives
            # focus again instead of the page behind it or a hidden dialog.
            page.keyboard.press("Escape")
            expect(page.locator("[data-view-trade]").first).to_be_focused()
            page.locator("[data-view-trade]").first.click()
            expect(page.locator("#drawer-content")).to_contain_text("SYNTHETIC UI TEST")
            expect(page.locator("#close-detail")).to_be_focused()
            page.evaluate("""() => document.addEventListener('click', () => {
                window.__twysSmokeNestedFocus = document.activeElement;
            }, {capture: true, once: true})""")
            page.locator(".detail-photo").first.click()
            expect(page.locator("#lightbox")).to_be_visible()
            assert_focus_trapped("#lightbox")
            page.keyboard.press("Escape")
            expect(page.locator("#lightbox")).to_be_hidden()
            expect(page.locator("#overlay")).to_be_visible()
            page.wait_for_function("document.activeElement === window.__twysSmokeNestedFocus")
            assert page.locator("#overlay").evaluate("el => el.contains(document.activeElement)")
            assert page.locator("#app").evaluate("el => el.inert")
            page.keyboard.press("Escape")
            expect(page.locator("#overlay")).to_be_hidden()
            expect(page.locator("[data-view-trade]").first).to_be_focused()
            checked("Gallery arrows/zoom/details and nested photo/source dialog focus traps, Escape order and restoration")

            for width, height in ((1366, 768), (1100, 800), (900, 800)):
                page.set_viewport_size({"width": width, "height": height})
                navigate("marketdesk")
                expect(page.locator(".v22-markethead")).to_be_visible()
                expect(page.locator("#global-search-button")).to_be_visible()
                page.locator("#global-search-button").click()
                expect(page.locator("#global-query")).to_be_visible()
                page.keyboard.press("Escape")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), \
                    f"Horizontal document overflow at {width}px"
                screenshot(f"markets-{width}")
            checked("Market workspace and search at 1450, 1366, 1100 and 900px without document overflow")

            page.emulate_media(reduced_motion="reduce")
            navigate("watchlist")
            expect(page.locator("#v24-watch-title")).to_be_visible()
            assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
            page.wait_for_timeout(350)
            moving = page.evaluate("""() => document.getAnimations().filter(a =>
                a.playState === 'running' && a.effect?.target?.closest?.('#app')).length""")
            assert moving == 0, "App has active animations despite reduced-motion preference"
            checked("Reduced-motion preference preserves navigation with no active app animations")
            assert not report["page_errors"], report["page_errors"]
            report["status"] = "passed"
        except Exception as exc:
            report["status"] = "failed"
            report["failure"] = str(exc)
            screenshot("failure")
            raise
        finally:
            if initial_favorites is not None:
                # Restore only the symbol this test changed, never unrelated favorites.
                restore = context.request.post(BASE + "/api/v2/favorites", data={
                    "symbol": "XAUUSD", "favorite": "XAUUSD" in initial_favorites})
                report["favorites_restored"] = restore.ok
                if not restore.ok:
                    report["status"] = "failed"
            report["external_requests_stubbed"] = sorted(set(report["external_requests_stubbed"]))
            destination = OUTPUT / f"{LABEL}-report.json"
            destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
            browser.close()
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
