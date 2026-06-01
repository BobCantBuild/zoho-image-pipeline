"""Re-capture just the records table area with proper scroll + sizing."""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

OUT = Path(__file__).parent / "screenshots"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # Wider+taller viewport so all 12 columns fit
    ctx = browser.new_context(viewport={"width": 1900, "height": 1100})
    page = ctx.new_page()
    page.goto("https://zoho-image-pipeline.streamlit.app/",
              wait_until="domcontentloaded", timeout=90_000)
    time.sleep(25)            # wait for streamlit to render

    # Scroll so the records table sits near the top of the viewport
    page.evaluate("window.scrollTo(0, 640)")
    time.sleep(2)

    page.screenshot(
        path=str(OUT / "07_records_full.png"),
        clip={"x": 0, "y": 0, "width": 1900, "height": 800},
    )
    print("  saved 07_records_full.png")

    # Just the records table (column headers + ~5 rows)
    page.evaluate("window.scrollTo(0, 700)")
    time.sleep(2)
    page.screenshot(
        path=str(OUT / "08_records_table_only.png"),
        clip={"x": 0, "y": 0, "width": 1900, "height": 380},
    )
    print("  saved 08_records_table_only.png")

    browser.close()
