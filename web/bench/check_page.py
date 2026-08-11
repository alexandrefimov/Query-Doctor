"""Drive the prototype page in a real browser: measure load, run the sample, screenshot."""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8799/"
OUT = sys.argv[1] if len(sys.argv) > 1 else "page.png"

transferred = {"bytes": 0, "requests": 0, "external": []}


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 1100})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        def on_response(resp):
            transferred["requests"] += 1
            if not resp.url.startswith("http://127.0.0.1:8799/"):
                transferred["external"].append(resp.url)
            try:
                transferred["bytes"] += len(resp.body())
            except Exception:
                pass

        page.on("response", on_response)

        page.goto(URL, wait_until="load")
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Готово за')",
            timeout=120_000,
        )
        boot_status = page.inner_text("#status")
        print("boot:", boot_status)

        page.click("#sample")
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Разобрано за')",
            timeout=120_000,
        )
        print("run :", page.inner_text("#status"))

        headings = page.eval_on_selector_all("#out h1, #out h2", "els => els.map(e => e.textContent)")
        tables = page.eval_on_selector_all("#out table", "els => els.length")
        print(f"output: {len(headings)} sections, {tables} tables")
        print("sections:", " | ".join(headings[:12]))

        print(f"network: {transferred['requests']} requests, "
              f"{transferred['bytes'] / 1048576:.1f} MB total")
        print("external hosts:", sorted({u.split('/')[2] for u in transferred['external']}) or "none")

        page.screenshot(path=OUT, full_page=False)
        print("screenshot:", OUT)
        if errors:
            print("JS ERRORS:", errors[:5])
        browser.close()
        return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
