"""
Run this after you've collected at least a couple of days of data:

    python analyze.py

Prints the lowest price seen so far for each tracked route/date, and
saves a price-vs-time chart per route/date so you can visually spot
things like "price bottoms out ~36h before departure, then climbs."
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

CSV_PATH = Path(__file__).parent / "data" / "prices.csv"


def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["timestamp_utc"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    priced = df.dropna(subset=["price"]).copy()
    if priced.empty:
        print("No priced results yet -- let the tracker run a while first.")
        return

    priced["flight_date"] = pd.to_datetime(priced["flight_date"])
    priced["route"] = priced["origin"] + "->" + priced["destination"]
    priced["hours_to_departure"] = (
        (priced["flight_date"] - priced["timestamp_utc"]).dt.total_seconds() / 3600
    )

    print("\nLowest price seen so far, per site / route / date:")
    print(
        priced.groupby(["site", "route", "flight_date"])["price"]
        .agg(["min", "max", "count"])
        .sort_values("min")
    )

    # "Sold out" / disappeared check: did a route+date that used to have
    # results ever switch to no_results? If so, report how close to
    # departure that happened.
    no_results = df[df["notes"] == "no_results"].copy()
    if not no_results.empty:
        no_results["flight_date"] = pd.to_datetime(no_results["flight_date"])
        no_results["route"] = no_results["origin"] + "->" + no_results["destination"]
        no_results["hours_to_departure"] = (
            (no_results["flight_date"] - no_results["timestamp_utc"]).dt.total_seconds() / 3600
        )
        print("\n'No results' events (only meaningful if a route had prices before this):")
        print(
            no_results.groupby(["site", "route", "flight_date"])["hours_to_departure"]
            .min()
            .sort_values()
        )

    out_dir = Path(__file__).parent
    for (site, route, fdate), group in priced.groupby(["site", "route", "flight_date"]):
        group = group.sort_values("timestamp_utc")
        plt.figure(figsize=(8, 4))
        plt.plot(group["timestamp_utc"], group["price"], marker="o")
        plt.title(f"{site}  {route}  for {fdate.date()}")
        plt.xlabel("Checked at (UTC)")
        plt.ylabel("Price")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        fname = out_dir / f"chart_{site}_{route.replace('->','-')}_{fdate.date()}.png"
        plt.savefig(fname)
        plt.close()

    print(f"\nCharts saved to {out_dir}/chart_*.png")


if __name__ == "__main__":
    main()
