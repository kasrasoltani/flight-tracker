"""
Proves the CSV-writing part actually works -- does ONE real search
(not the full 124-checks-per-hour bot) and writes it to data/prices.csv
the exact same way the real bot will.

Run with:
    python test_csv_write.py
"""
from datetime import datetime, date
from playwright.sync_api import sync_playwright

from scraper import search_pateh, ensure_csv, append_rows, CSV_PATH

ORIGIN, DEST, FLIGHT_DATE = "IST", "TBZ", date(2026, 7, 5)

ensure_csv()

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    results = search_pateh(page, ORIGIN, DEST, FLIGHT_DATE)
    browser.close()

now = datetime.utcnow().isoformat()
rows = []
for r in results:
    rows.append({
        "timestamp_utc": now, "site": "pateh.com", "origin": ORIGIN,
        "destination": DEST, "flight_date": FLIGHT_DATE.isoformat(),
        "airline": r["airline"],
        "price": float(r["price"].replace(",", "")),
        "currency": r["currency"], "notes": r.get("notes", ""),
    })
append_rows(rows)

print(f"Wrote {len(rows)} row(s) to {CSV_PATH}\n")
print("Last few lines of the CSV file now:")
with open(CSV_PATH) as f:
    for line in f.readlines()[-5:]:
        print(" ", line.strip())
