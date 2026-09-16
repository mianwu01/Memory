"""Export the meeting HTML to PDF/PNG using an installed Playwright Chromium."""
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default=str(Path.home() / ".cache/ms-playwright/chromium-1187/chrome-linux/chrome"))
    args = ap.parse_args()
    libraries = ROOT / ".tmp/chromium-libs"
    if libraries.exists():
        os.environ["LD_LIBRARY_PATH"] = ":".join([str(libraries / "usr/lib64"),
            str(libraries / "lib64"), os.environ.get("LD_LIBRARY_PATH", "")])
    from playwright.sync_api import sync_playwright
    out = ROOT / "results/real/yujia_meeting_2026_09_04"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.browser,
                                             args=["--no-sandbox", "--disable-gpu"])
        page = browser.new_page(viewport={"width": 1400, "height": 850}, device_scale_factor=1)
        page.goto((out / "slides.html").as_uri())
        page.pdf(path=str(out / "slides.pdf"), print_background=True, prefer_css_page_size=True)
        for i, slide in enumerate(page.locator(".slide").all(), 1):
            slide.screenshot(path=str(out / f"slide-{i}.png"))
        browser.close()
    print(out / "slides.pdf")


if __name__ == "__main__":
    main()
