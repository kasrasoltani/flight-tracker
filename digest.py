"""
Builds one neat "what's going on" summary and sends it to Telegram.

The GitHub Actions workflow runs this automatically once a day. You can
also run it manually any time to check in:

    python digest.py

Everything here is deliberately hedged. With only a handful of hourly
checks spread across a rolling window of dates, there isn't enough data
for confident predictions -- so the message says "best guess so far,"
not "guaranteed," and stays quiet about patterns it doesn't have enough
data to support yet (e.g. day-of-week pricing needs several different
flight dates before it means anything).
"""

import os
from pathlib import Path

import pandas as pd
import requests

CSV_PATH = Path(__file__).parent / "data" / "prices.csv"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MIN_READINGS_FOR_TREND = 6        # ~6 hourly checks before commenting on trend/floor
MIN_DATES_FOR_WEEKDAY_PATTERN = 3  # need a few different flight dates in the data


def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=15,
    )


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
        return f"🤷 only {n} check(s) so far -- too early to guess a floor"
    best = prices.min()
    since = n - 1 - prices.values[::-1].argmin()
    return (
        f"🎯 lowest seen is {best:,.0f}, unbeaten for {since} check(s) -- "
        f"maybe near the floor, but that's a guess, not a guarantee"
    )


def main():
    if not CSV_PATH.exists():
        send_telegram("📊 Daily flight digest: no data collected yet.")
        return

    df = pd.read_csv(CSV_PATH, parse_dates=["timestamp_utc"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price"]).copy()
    if df.empty:
        send_telegram("📊 Daily flight digest: no priced results logged yet.")
        return

    df["flight_date"] = pd.to_datetime(df["flight_date"])
    df["route"] = df["origin"] + " → " + df["destination"]

    lines = ["📊 <b>Flight price digest</b>", f"🗂 {len(df)} price points so far", ""]

    # Latest snapshot per (site, route, flight_date) -- ALL flights at the
    # most recent check time, not just one arbitrary row. Without this,
    # two flights logged with the same timestamp (e.g. two airlines found
    # in the same scrape) could cause the cheaper one to get silently
    # dropped instead of compared.
    latest_ts = df.groupby(["site", "route", "flight_date"])["timestamp_utc"].transform("max")
    latest = df[df["timestamp_utc"] == latest_ts]

    best_now = latest.loc[latest["price"].idxmin()]
    lines.append(
        f"🔥 Cheapest right now: <b>{best_now['price']:,.0f} {best_now['currency']}</b> "
        f"-- {best_now['route']} on {best_now['flight_date'].date()} "
        f"({best_now['airline']})"
    )
    lines.append("")

    # Per-route: best option found, its trend, and a hedged floor guess
    lines.append("✈️ <b>By route:</b>")
    for route, rgroup in df.groupby("route"):
        rlatest = latest[latest["route"] == route]
        if rlatest.empty:
            continue
        best_row = rlatest.loc[rlatest["price"].idxmin()]
        # Collapse to one price per check-time (the cheapest flight seen
        # at that moment) so trend/floor math isn't confused by multiple
        # airlines sharing a timestamp.
        same_flight = rgroup[rgroup["flight_date"] == best_row["flight_date"]]
        series = same_flight.groupby("timestamp_utc")["price"].min().sort_index()
        lines.append(
            f"• <b>{route}</b>: {best_row['price']:,.0f} on {best_row['flight_date'].date()}\n"
            f"   {trend_label(series)}\n"
            f"   {floor_note(series)}"
        )
    lines.append("")

    # Route comparison by typical (median) price
    medians = df.groupby("route")["price"].median().sort_values()
    if len(medians) > 1:
        lines.append("💸 <b>Cheapest route on average:</b>")
        for route, med in medians.items():
            lines.append(f"   {route}: {med:,.0f}")
        lines.append("")

    # Day-of-week pattern -- only once enough distinct flight dates exist
    n_dates = df["flight_date"].nunique()
    if n_dates >= MIN_DATES_FOR_WEEKDAY_PATTERN:
        df["weekday"] = df["flight_date"].dt.day_name()
        weekday_avg = df.groupby("weekday")["price"].mean().sort_values()
        lines.append("📅 <b>Cheapest day of week (so far):</b>")
        for wd, avg in weekday_avg.items():
            lines.append(f"   {wd}: {avg:,.0f}")
    else:
        lines.append(f"ℹ️ Day-of-week pattern needs more spread of dates -- have {n_dates} so far.")

    send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
