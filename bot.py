"""
Telegram bot — send /check to get an instant price digest.

Fetches the latest prices.csv directly from GitHub (no local file needed),
runs the same digest logic, and replies in seconds.

Deploy on Railway: set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GITHUB_REPO env vars.
"""

import io
import os
import time

import pandas as pd
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
GITHUB_REPO = os.environ.get("GITHUB_REPO", "kasrasoltani/flight-tracker")
CSV_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/data/prices.csv"

MIN_READINGS_FOR_TREND = 6
MIN_DATES_FOR_WEEKDAY_PATTERN = 3


def send(chat_id: str, text: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )


def get_updates(offset=None):
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params={"timeout": 30, "offset": offset},
            timeout=35,
        )
        return r.json().get("result", [])
    except Exception:
        return []


def trend_label(prices: pd.Series) -> str:
    if len(prices) < MIN_READINGS_FOR_TREND:
        return "⏳ not enough checks yet for a trend"
    recent = prices.iloc[-3:].mean()
    prior = prices.iloc[-6:-3].mean()
    if recent < prior * 0.98:
        return "📉 trending down"
    if recent > prior * 1.02:
        return "📈 trending up"
    return "➡️ flat"


def floor_note(prices: pd.Series) -> str:
    n = len(prices)
    if n < MIN_READINGS_FOR_TREND:
        return f"🤷 only {n} check(s) so far"
    best = prices.min()
    since = n - 1 - prices.values[::-1].argmin()
    return f"🎯 lowest seen is {best:,.0f}, unbeaten for {since} check(s)"


def build_digest() -> str:
    r = requests.get(CSV_URL, timeout=15)
    r.raise_for_status()

    df = pd.read_csv(io.StringIO(r.text), parse_dates=["timestamp_utc"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price"]).copy()

    if df.empty:
        return "No price data yet."

    df["flight_date"] = pd.to_datetime(df["flight_date"])
    today = pd.Timestamp.now().normalize()
    df = df[(df["flight_date"] >= today) & (df["flight_date"] <= today + pd.Timedelta(days=20))]
    if df.empty:
        return "No flights found in the next 20 days."
    df["route"] = df["origin"] + " → " + df["destination"]

    # Next 5 days: cheapest per route
    next5 = df[df["flight_date"] <= today + pd.Timedelta(days=5)]
    lines = ["📊 <b>Flight price digest</b>", f"🗂 {len(df)} price points so far", ""]
    if not next5.empty:
        lines.append("🚀 <b>Cheapest in next 5 days:</b>")
        latest_ts5 = next5.groupby(["site", "route", "flight_date"])["timestamp_utc"].transform("max")
        latest5 = next5[next5["timestamp_utc"] == latest_ts5]
        for route, grp in latest5.groupby("route"):
            best = grp.loc[grp["price"].idxmin()]
            lines.append(f"• {route}: <b>{best['price']:,.0f} {best['currency']}</b> on {best['flight_date'].date()} ({best['airline']})")
        lines.append("")

    latest_ts = df.groupby(["site", "route", "flight_date"])["timestamp_utc"].transform("max")
    latest = df[df["timestamp_utc"] == latest_ts]

    best_now = latest.loc[latest["price"].idxmin()]
    lines.append(
        f"🔥 Cheapest right now: <b>{best_now['price']:,.0f} {best_now['currency']}</b>"
        f" -- {best_now['route']} on {best_now['flight_date'].date()} ({best_now['airline']})"
    )
    lines.append("")

    lines.append("✈️ <b>By route:</b>")
    for route, rgroup in df.groupby("route"):
        rlatest = latest[latest["route"] == route]
        if rlatest.empty:
            continue
        best_row = rlatest.loc[rlatest["price"].idxmin()]
        same_flight = rgroup[rgroup["flight_date"] == best_row["flight_date"]]
        series = same_flight.groupby("timestamp_utc")["price"].min().sort_index()
        lines.append(
            f"• <b>{route}</b>: {best_row['price']:,.0f} on {best_row['flight_date'].date()}\n"
            f"   {trend_label(series)}\n"
            f"   {floor_note(series)}"
        )
    lines.append("")

    medians = df.groupby("route")["price"].median().sort_values()
    if len(medians) > 1:
        lines.append("💸 <b>Cheapest route on average:</b>")
        for route, med in medians.items():
            lines.append(f"   {route}: {med:,.0f}")
        lines.append("")

    n_dates = df["flight_date"].nunique()
    if n_dates >= MIN_DATES_FOR_WEEKDAY_PATTERN:
        df["weekday"] = df["flight_date"].dt.day_name()
        weekday_avg = df.groupby("weekday")["price"].mean().sort_values()
        lines.append("📅 <b>Cheapest day of week:</b>")
        for wd, avg in weekday_avg.items():
            lines.append(f"   {wd}: {avg:,.0f}")

    return "\n".join(lines)


def main():
    print("Bot running. Send /check in Telegram.")
    offset = None
    while True:
        updates = get_updates(offset)
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message", {})
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            if chat_id != TELEGRAM_CHAT_ID:
                continue

            if text == "/check":
                send(chat_id, "⏳ Fetching latest prices...")
                try:
                    send(chat_id, build_digest())
                except Exception as e:
                    send(chat_id, f"❌ Error: {e}")

            elif text == "/help":
                send(chat_id, "/check — get instant price digest\n/help — show this")

        time.sleep(1)


if __name__ == "__main__":
    main()
