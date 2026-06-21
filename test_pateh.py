"""
Quick one-off test -- NOT the full bot, just checks that search_pateh()
actually works against the live site before we trust it.

Run with:
    python test_pateh.py
"""
from datetime import date
from playwright.sync_api import sync_playwright

from scraper import search_pateh

TEST_DATE = date(2026, 7, 5)  # change this to try a different date

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)  # headless=False so you can watch it
    page = browser.new_page()
    results = search_pateh(page, "IST", "TBZ", TEST_DATE)
    browser.close()

print(f"\nFound {len(results)} flights for IST->TBZ on {TEST_DATE}:\n")
for r in results:
    print(f"  {r['airline']:<25} {r['price']:>15} {r['currency']}  {r['notes']}")
