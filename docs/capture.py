"""
Capture dashboard screenshots for documentation.
Uses Playwright headless Chromium.
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

URL = "https://zoho-image-pipeline.streamlit.app/"
OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        print(f"Loading {URL}...")
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        # Streamlit Cloud cold-starts slowly + may show "Yes, get this app back up"
        # Wait long enough for app to wake, then verify visible.
        for attempt in range(8):
            time.sleep(10)
            try:
                if page.locator("text=CUSTOMER REVIEW ANALYSIS").first.is_visible():
                    print(f"  app visible after {(attempt+1)*10}s")
                    break
            except Exception:
                pass
            # Try clicking the "Yes" wake button if Streamlit is asleep
            try:
                btn = page.get_by_role("button", name="Yes, get this app back up!")
                if btn.is_visible():
                    print("  clicking wake button…")
                    btn.click()
            except Exception:
                pass
        time.sleep(5)

        # Full page screenshot
        full = OUT / "01_full_dashboard.png"
        page.screenshot(path=str(full), full_page=True)
        print(f"  saved {full.name}")

        # Section 1: Header — clip from full page (already loaded)
        page.screenshot(path=str(OUT / "02_header.png"),
                        clip={"x": 0, "y": 50, "width": 1600, "height": 170})
        print("  saved 02_header.png")

        # Section 2: Metric cards
        page.screenshot(path=str(OUT / "03_section1_metrics.png"),
                        clip={"x": 0, "y": 190, "width": 1600, "height": 175})
        print("  saved 03_section1_metrics.png")

        # Section 3: Filter bar (with Records header)
        page.screenshot(path=str(OUT / "04_section2_filters.png"),
                        clip={"x": 0, "y": 430, "width": 1600, "height": 200})
        print("  saved 04_section2_filters.png")

        # Section 4: Records table — scroll down to show fully
        page.evaluate("window.scrollTo(0, 480)")
        time.sleep(2)
        page.screenshot(path=str(OUT / "05_section3_records.png"),
                        clip={"x": 0, "y": 150, "width": 1600, "height": 600})
        print("  saved 05_section3_records.png")

        # Records table — wide capture of column headers + first few rows
        page.evaluate("window.scrollTo(0, 600)")
        time.sleep(2)
        page.screenshot(path=str(OUT / "06_records_table.png"), full_page=False)
        print("  saved 06_records_table.png")

        browser.close()
        print("Done.")


if __name__ == "__main__":
    main()
