"""Drive the prototype page in a real browser: measure load, run the sample, screenshot."""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8799/"
OUT = sys.argv[1] if len(sys.argv) > 1 else "page.png"

transferred = {"requests": 0, "external": []}


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 1100})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # Track requests, not responses: an external reference that fails to
        # resolve never produces a response, which is exactly the case a gate
        # for "reaches no external host" must not miss.
        def on_request(request):
            transferred["requests"] += 1
            if not request.url.startswith(URL):
                transferred["external"].append(request.url)

        page.on("request", on_request)

        for attempt in range(30):
            try:
                page.goto(URL, wait_until="load")
                break
            except Exception:
                if attempt == 29:
                    raise
                page.wait_for_timeout(500)
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Ready in')",
            timeout=120_000,
        )
        boot_status = page.inner_text("#status")
        print("boot:", boot_status)

        page.click("#sample")
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Analyzed in')",
            timeout=120_000,
        )
        print("run :", page.inner_text("#status"))

        headings = page.eval_on_selector_all("#out h1, #out h2", "els => els.map(e => e.textContent)")
        tables = page.eval_on_selector_all("#out table", "els => els.length")
        print(f"output: {len(headings)} sections, {tables} tables")
        print("sections:", " | ".join(headings[:12]))

        print(f"network: {transferred['requests']} requests")
        print("external hosts:", sorted({u.split('/')[2] for u in transferred['external']}) or "none")

        page.screenshot(path=OUT, full_page=False)
        print("screenshot:", OUT)

        failures = []
        if transferred["external"]:
            hosts = sorted({u.split("/")[2] for u in transferred["external"]})
            failures.append(f"page reached external hosts: {hosts}")
        if errors:
            failures.append(f"JS errors: {errors[:5]}")
        if not headings:
            failures.append("analyzer produced no output sections")

        browser.close()
        for failure in failures:
            print("FAIL:", failure)
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
