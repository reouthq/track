#!/usr/bin/env python3
"""The exchange's own record of the account's transactions for a month, as the exchange generates it.

The export is requested, collected once the exchange has generated it, and kept as the bytes
received: a zip holding one CSV. It is a record made by the exchange apart from the responses the
daily workflow retrieves, and the third source of the monthly reconciliation (Methodology,
section 5). The exchange allows five such exports a month.

The log states statuses, dates and the file's name only.

    BINANCE_API_KEY=... BINANCE_API_SECRET=... python3 transactions.py [--month YYYY-MM] --out DIR
"""

import argparse
import calendar
import csv
import datetime as dt
import io
import json
import os
import re
import time
import urllib.request
import zipfile

import fetch

REQUEST = "https://fapi.binance.com/fapi/v1/income/asyn"
COLLECT = "https://fapi.binance.com/fapi/v1/income/asyn/id"
# As measured: the export was generated in about a minute.
WAIT_S, TRIES = 15, 40
COLUMNS = ["Date(UTC)", "type", "Amount", "Asset", "Symbol", "Transaction ID"]


def stamp(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def period(month, now):
    """(start, end) in milliseconds: the month, from the first deposit at the earliest, to now at the latest."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise SystemExit(f"FAIL transaction export: {month!r} is not a month")
    year, mon = int(month[:4]), int(month[5:])
    start = calendar.timegm((year, mon, 1, 0, 0, 0)) * 1000
    end = calendar.timegm((year + (mon == 12), mon % 12 + 1, 1, 0, 0, 0)) * 1000 - 1
    start, end = max(start, fetch.ACCOUNT_START_MS), min(end, now)
    if start >= end:
        raise SystemExit(f"FAIL transaction export: {month} holds no time of the account")
    return start, end


def previous_month(now):
    first = dt.datetime.fromtimestamp(now / 1000, dt.timezone.utc).replace(day=1)
    return (first - dt.timedelta(days=1)).strftime("%Y-%m")


def download(url):
    """The file behind a link the exchange signed.

    It is served from a content network the proxy does not admit, and is fetched directly; the link
    is signed and short-lived, and the file is checked for its form before it is kept.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "reout-track"}), timeout=60) as r:
        return r.read()


def check(data):
    """Refuse a file that is not the export as measured: a zip of one CSV with the export's columns."""
    if data[:2] != b"PK":
        raise SystemExit("FAIL transaction export: the file is not a zip")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if len(names) != 1 or not names[0].lower().endswith(".csv"):
            raise SystemExit("FAIL transaction export: the zip does not hold exactly one CSV")
        text = z.read(names[0]).decode("utf-8-sig")
    header = next(csv.reader(io.StringIO(text)), [])
    if header != COLUMNS:
        raise SystemExit("FAIL transaction export: the CSV does not have the export's columns")


def export(call, fetch_file, start, end, sleep=time.sleep):
    """The bytes of the export of [start, end], once the exchange has generated it."""
    status, body = call(REQUEST, {"startTime": start, "endTime": end})
    if status != 200:
        fetch.refuse("transaction export request", status, body)
    download_id = json.loads(body)["downloadId"]
    for _ in range(TRIES):
        sleep(WAIT_S)
        status, body = call(COLLECT, {"downloadId": download_id})
        if status != 200:
            fetch.refuse("transaction export", status, body)
        state = json.loads(body)
        print(f"export: {state.get('status')}")
        if state.get("status") == "completed" and state.get("url"):
            data = fetch_file(state["url"])
            check(data)
            return data
    raise SystemExit("FAIL transaction export: not generated in time")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--month", default="", help="YYYY-MM; the month before this one if empty")
    ap.add_argument("--out", required=True, help="the folder to write the export into")
    a = ap.parse_args()
    now = int(time.time() * 1000)
    month = a.month or previous_month(now)
    start, end = period(month, now)
    print(f"export of {month}: {stamp(start)} to {stamp(end)}")
    call = fetch.signed_caller(os.environ["BINANCE_API_KEY"], os.environ["BINANCE_API_SECRET"].encode())
    data = export(call, download, start, end)
    name = f"transactions-{stamp(start)}-{stamp(end)}.zip"
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, name), "wb") as f:
        f.write(data)
    print(f"kept as {name}")


if __name__ == "__main__":
    main()
