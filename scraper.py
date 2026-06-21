"""
Flight price tracker -- IST/ADB to TBZ/OMH/IKA.

Logs every observation to data/prices.csv, and sends a Telegram alert
when a new low price shows up for a tracked route+date.

STATUS: navigation to each site's route page is real and confirmed.
The "do the search and read the price" step inside search_pateh()
and search_alibaba() is a placeholder -- see README.md Part A for how
to fill it in using `playwright codegen` (no guessing needed).
"""

import argparse
import csv
import os
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import jdatetime
import requests

# ---------------------------------------------------------------------------
# CONFIG -- edit this section to change what gets tracked
# ---------------------------------------------------------------------------

# (origin, destination, label) in priority order.
ROUTES = [
    ("IST", "TBZ", "priority"),
    ("IST", "OMH", "backup"),
    ("IST", "IKA", "backup, least preferred"),
    ("ADB", "IKA", "Izmir direct -- easier for you"),
]

# Checks every single day starting from today, through this date.
# Recalculated fresh each run, so it automatically drops dates that
# have already passed -- no need to maintain a list by hand.
LAST_DATE_TO_CHECK = date(2026, 7, 20)


def build_target_dates() -> list[date]:
    today = date.today()
    dates = []
    d = today
    while d <= LAST_DATE_TO_CHECK:
        dates.append(d)
        d += timedelta(days=1)
    return dates


TARGET_DATES = build_target_dates()

CSV_PATH = Path(__file__).parent / "data" / "prices.csv"
CSV_HEADERS = [
    "timestamp_utc", "site", "origin", "destination", "flight_date",
    "airline", "price", "currency", "notes",
]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Alert if a new price is at least this much below the best seen so far.
DROP_ALERT_THRESHOLD = 0.05  # 5%


# ---------------------------------------------------------------------------
# SITE-SPECIFIC SEARCH FUNCTIONS
# These two are the only functions that need real selectors filled in.
# ---------------------------------------------------------------------------

def search_pateh(page, origin: str, dest_code: str, flight_date: date) -> list[dict]:
    """
    Search pateh.com for origin -> dest_code on flight_date.

    Confirmed working: the route page accepts the date directly as a URL
    parameter -- no clicking needed. The date has to be in the Jalali
    (Persian) calendar, formatted YYYY-MM-DD.

    Confirmed selectors (found via browser inspection on 2026-06-20):
      - price text:   p.text-secondary-blue-600.font-extrabold
      - airline name: p.text-2xs.text-gray-500.text-clip
    Prices and airline names appear in matching order, one pair per
    flight card, so we zip them together rather than walking the DOM
    tree to pair them -- simpler, and good enough for personal use.
    """
    jalali_date = jdatetime.date.fromgregorian(date=flight_date).strftime("%Y-%m-%d")
    url = f"https://www.pateh.com/flight/int-{origin.lower()}all-{dest_code.lower()}all/?departing={jalali_date}"
    page.goto(url, wait_until="domcontentloaded")

    try:
        page.wait_for_selector("p.text-secondary-blue-600.font-extrabold", timeout=15000)
    except PlaywrightTimeoutError:
        return []  # no flights found for this date (or page didn't load in time)

    prices = [el.inner_text().strip() for el in page.locator("p.text-secondary-blue-600.font-extrabold").all()]
    airlines = [el.inner_text().strip() for el in page.locator("p.text-2xs.text-gray-500.text-clip").all()]

    note = ""
    if len(prices) != len(airlines):
        note = f"mismatch: {len(prices)} prices vs {len(airlines)} airline names -- check manually"

    results = []
    for i in range(min(len(prices), len(airlines))):
        results.append({
            "airline": airlines[i],
            "price": prices[i],
            "currency": "IRT",
            "notes": note,
        })
    return results


SEARCHERS = {
    "pateh.com": search_pateh,
}


# ---------------------------------------------------------------------------
# Plumbing -- CSV logging, price-drop detection, Telegram alerts
# ---------------------------------------------------------------------------

def ensure_csv():
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADERS)


def load_best_known_prices() -> dict:
    """Returns {(site, origin, dest, flight_date_str): lowest_price_seen_so_far}."""
    best = {}
    if not CSV_PATH.exists():
        return best
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                price = float(row["price"])
            except (KeyError, ValueError, TypeError):
                continue
            key = (row["site"], row["origin"], row["destination"], row["flight_date"])
            if key not in best or price < best[key]:
                best[key] = price
    return best


def append_rows(rows: list[dict]):
    if not rows:
        return
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        for row in rows:
            writer.writerow(row)


def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, would have sent:", message)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=15,
        )
    except requests.RequestException as e:
        print("Telegram send failed:", e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--same-day", action="store_true",
                        help="Only check today's flights (runs every 30 min on departure day)")
    args = parser.parse_args()

    target_dates = [date.today()] if args.same_day else TARGET_DATES
    drop_threshold = 0.02 if args.same_day else DROP_ALERT_THRESHOLD  # tighter on same day

    ensure_csv()
    best_known = load_best_known_prices()
    now = datetime.now(timezone.utc).isoformat()
    new_rows = []
    alerts = []
    errors = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        for origin, dest_code, _label in ROUTES:
            for flight_date in target_dates:
                for site, search_fn in SEARCHERS.items():
                    try:
                        results = search_fn(page, origin, dest_code, flight_date)
                    except NotImplementedError as e:
                        errors.append(f"{site} {origin}-{dest_code} {flight_date}: {e}")
                        continue
                    except Exception as e:
                        errors.append(f"{site} {origin}-{dest_code} {flight_date}: {e}")
                        continue

                    if not results:
                        # Search worked but came back empty -- worth logging
                        # explicitly so we can later tell "sold out" apart
                        # from "we never managed to check."
                        new_rows.append({
                            "timestamp_utc": now, "site": site, "origin": origin,
                            "destination": dest_code, "flight_date": flight_date.isoformat(),
                            "airline": "", "price": "", "currency": "", "notes": "no_results",
                        })
                        continue

                    for r in results:
                        try:
                            price = float(str(r["price"]).replace(",", "").strip())
                        except (ValueError, KeyError):
                            continue
                        row = {
                            "timestamp_utc": now,
                            "site": site,
                            "origin": origin,
                            "destination": dest_code,
                            "flight_date": flight_date.isoformat(),
                            "airline": r.get("airline", ""),
                            "price": price,
                            "currency": r.get("currency", ""),
                            "notes": r.get("notes", ""),
                        }
                        new_rows.append(row)

                        key = (site, origin, dest_code, flight_date.isoformat())
                        prev_best = best_known.get(key)
                        if prev_best is not None and price <= prev_best * (1 - drop_threshold):
                            prefix = "🚨 <b>SAME-DAY DROP</b>" if args.same_day else "📉 <b>New low spotted!</b>"
                            msg = (
                                f"{prefix}\n"
                                f"✈️ {origin} → {dest_code}  •  {flight_date}\n"
                                f"💰 <b>{price:,.0f} {row['currency']}</b> ({r.get('airline','')})"
                            )
                            if prev_best:
                                pct = (1 - price / prev_best) * 100
                                msg += f"\n⬇️ down {pct:.0f}% from the previous low of {prev_best:,.0f}"
                            alerts.append(msg)
                            best_known[key] = price

        browser.close()

    append_rows(new_rows)
    print(f"Logged {len(new_rows)} rows.")

    if errors:
        print(f"{len(errors)} searches failed/skipped, e.g.:")
        for e in errors[:5]:
            print("  -", e)

    for a in alerts:
        send_telegram(a)

    priced_rows = [r for r in new_rows if r["price"] != ""]
    if not priced_rows and errors:
        send_telegram(
            f"⚠️ Heads up: price check ran but logged 0 prices "
            f"({len(errors)} searches failed). Might be getting blocked -- "
            f"worth checking manually."
        )


if __name__ == "__main__":
    main()
