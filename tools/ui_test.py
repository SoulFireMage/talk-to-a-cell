"""
Drive the page in headless Chrome: no-key message, a real-cell test, a direct question,
and expert mode. Needs an OpenRouter key in $OPENROUTER_API_KEY.

Run: OPENROUTER_API_KEY=... venv/bin/python tools/ui_test.py [url] [screenshot_dir]
"""

import os
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7861/"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "."
KEY = os.environ["OPENROUTER_API_KEY"]


def chat_text(page):
    return page.locator(".bubble-wrap, [role='log']").first.inner_text()


def wait_for_turn(page, needle, timeout=240_000):
    page.wait_for_function(
        """(needle) => { const el = document.querySelector('.bubble-wrap') || document.querySelector('[role="log"]');
                         return el && el.innerText.includes(needle) && !el.innerText.trim().endsWith('…'); }""",
        arg=needle, timeout=timeout,
    )


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1200, "height": 1000})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(URL)
    page.wait_for_selector("text=Talk to a Cell", timeout=60_000)
    page.wait_for_function("() => !!window.TTAC", timeout=60_000)
    page.screenshot(path=f"{SHOTS}/01-start.png")

    # 1. No key: should explain what to do.
    page.get_by_role("button", name="🧪 Show me it working").click()
    wait_for_turn(page, "OpenRouter key", timeout=20_000)
    print("[no key] OK")

    # 2. Key, then a real-cell test.
    page.get_by_text("⚙️ Settings: your OpenRouter key").click()
    page.get_by_label("OpenRouter API key").fill(KEY)
    page.get_by_role("button", name="Clear chat").click()
    page.get_by_role("button", name="🧪 Show me it working").click()
    wait_for_turn(page, "What C2S actually said")
    page.wait_for_timeout(8_000)  # the explanation arrives after the C2S box
    page.screenshot(path=f"{SHOTS}/02-real-cell.png", full_page=True)
    print("[real cell]\n" + chat_text(page)[-1500:])

    # 3. Follow-up that needs conversation memory.
    page.get_by_placeholder("e.g. Show me a real B cell").fill("Nice. Do another one, but a different kind of cell.")
    page.get_by_role("button", name="Send").click()
    page.wait_for_timeout(3_000)
    wait_for_turn(page, "different kind of cell")
    page.wait_for_function("() => (document.querySelector('.bubble-wrap').innerText.match(/What C2S actually said/g) || []).length >= 2", timeout=240_000)
    page.wait_for_timeout(8_000)
    print("[follow-up]\n" + chat_text(page)[-900:])

    # 4. Expert mode, no key involved.
    page.get_by_role("tab", name="🔬 Expert mode (no key needed)").click()
    page.get_by_label("Load a real cell (its label is revealed after C2S answers)").click()
    page.get_by_role("option", name="Real cell 7 (label hidden)").click()
    page.wait_for_timeout(1_500)
    page.get_by_role("button", name="Which cell is this?", exact=True).click()
    page.wait_for_selector("text=C2S says", timeout=120_000)
    page.screenshot(path=f"{SHOTS}/03-expert.png", full_page=True)
    print("[expert] " + page.locator("text=C2S says").first.inner_text(), "|",
          page.locator("text=Experts labelled this cell").first.inner_text())

    print("console errors:", errors or "none")
    browser.close()
