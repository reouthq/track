#!/usr/bin/env python3
"""Fetch the exchange's own records of the designated account, as received.

The workflow that preserves the records and the workflow that publishes the
record both start here, so that they work from records fetched by one piece of
code. The output is one JSON document holding every response unmodified: the
daily records of the account, its income ledger and the instrument's fills. Its
hash is therefore a hash of what the exchange sent.

The log states dates only: no balance, no fill and no count of entries or fills,
since the workflows' logs are public and such counts are trade statistics.

    BINANCE_API_KEY=... BINANCE_API_SECRET=... python3 fetch.py --out /tmp/records.json
"""

import argparse
import calendar
import datetime as dt
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# The account's first deposit. Nothing before it is asked for.
ACCOUNT_START_MS = calendar.timegm((2026, 9, 6, 0, 0, 0)) * 1000
# The exchange's documentation gives the income ledger three months. A request
# reaching further back is answered without error (as measured, up to
# 400 days), so that limit would not announce itself: ask for 80 days, inside it.
MAX_LOOKBACK_MS = 80 * 86_400_000
# Daily records are asked for over the last 29 days only. Asked for a longer
# span, the exchange answers with the 30 days from its start and leaves out the
# newest days without saying so (as measured).
RECORD_SPAN_MS = 29 * 86_400_000
# A day's record is handed out after the day ends and may not be out yet when
# the fetch runs, so the newest record may be that of the day before the last
# one that ended. An older one means new days have stopped arriving.
RECORD_LAG_DAYS = 2
# The program's one instrument (Methodology, section 1); fills are asked for by instrument.
INSTRUMENT = "BTCUSDT"
# The account is margined in this currency, and it is the alias of this currency's
# futures balance that names the account (account_identity).
BASE_CURRENCY = "USDT"
# The widest span of fills the exchange accepts in one request.
FILL_SPAN_MS = 7 * 86_400_000 - 1
PAGE_SIZE = 1000
MAX_PAGES = 200


def signed_caller(key, secret):
    """A function that sends a signed request and returns (HTTP status, body)."""
    def call(url, params):
        q = dict(params)
        q["timestamp"] = int(time.time() * 1000)
        q["recvWindow"] = 10000
        qs = urllib.parse.urlencode(q)
        qs += "&signature=" + hmac.new(secret, qs.encode(), hashlib.sha256).hexdigest()
        req = urllib.request.Request(url + "?" + qs,
                                     headers={"X-MBX-APIKEY": key, "User-Agent": "reout-track"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            return None, str(e).encode()
    return call


def refuse(what, status, body):
    """Stop, stating the exchange's error code and message, which carry no account data."""
    try:
        d = json.loads(body)
        detail = f"code {d.get('code')}: {d.get('msg')}"
    except Exception:
        detail = body[:200].decode(errors="replace")
    raise SystemExit(f"FAIL {what}: HTTP {status} ({detail})")


def paged(call, what, url, params, start, end):
    """Every page of one time span, each kept as received.

    A page resumes at the last item's millisecond rather than after it. That
    repeats those items in the next page, which the readers of the document
    remove, instead of dropping any others that share the millisecond. A full page
    that cannot move past its millisecond cannot be paged at all, and stops the
    fetch rather than end it short.
    """
    bodies, cursor = [], start
    for _ in range(MAX_PAGES):
        status, body = call(url, dict(params, startTime=cursor, endTime=end, limit=PAGE_SIZE))
        if status != 200:
            refuse(what, status, body)
        page = json.loads(body)
        bodies.append(body.decode())
        if len(page) < PAGE_SIZE:
            return bodies
        latest = max(int(x["time"]) for x in page)
        if latest <= cursor:
            raise SystemExit(f"FAIL {what}: a full page within one millisecond cannot be paged")
        cursor = latest
    raise SystemExit(f"FAIL {what}: more than {MAX_PAGES} pages")


def account_identity(call):
    """Which account the key belongs to: the user's identifier and the futures
    account's own alias.

    A key names no account of itself. Without this the record would follow
    whichever account a key was last issued for, and every check below it would
    pass on the wrong account's figures. The identifiers are kept in the copy,
    which is retained encrypted, and the record refuses to be produced unless
    they match what was registered before it began (pull.py, check_account). They
    are never published: an identifier is account data, held for verifiers under
    a non-disclosure agreement.

    Only the two identifiers are kept, not the responses that carry them: those
    also hold the spot wallet, which is no part of the record.
    """
    status, body = call("https://api.binance.com/api/v3/account", {})
    if status != 200:
        refuse("the account", status, body)
    uid = json.loads(body).get("uid")

    status, body = call("https://fapi.binance.com/fapi/v2/balance", {})
    if status != 200:
        refuse("the futures balances", status, body)
    alias = next((b.get("accountAlias") for b in json.loads(body)
                  if b.get("asset") == BASE_CURRENCY), None)

    if not uid or not alias:
        raise SystemExit("FAIL the account: the exchange named no account for this key; "
                         "the copy is not kept")
    return {"uid": str(uid), "alias": str(alias)}


def fetch(call, now):
    """The document of the exchange's records up to `now`, in milliseconds."""
    start = max(ACCOUNT_START_MS, now - MAX_LOOKBACK_MS)
    status, records = call("https://api.binance.com/sapi/v1/accountSnapshot",
                           {"type": "FUTURES", "startTime": max(start, now - RECORD_SPAN_MS),
                            "endTime": now, "limit": 30})
    if status != 200:
        refuse("daily records", status, records)
    newest = max((int(v["updateTime"]) for v in json.loads(records).get("snapshotVos") or []),
                 default=None)
    if newest is None or newest < now - now % 86_400_000 - RECORD_LAG_DAYS * 86_400_000:
        seen = (dt.datetime.fromtimestamp(newest / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
                if newest is not None else "none")
        raise SystemExit(f"FAIL daily records: the newest is from {seen}; "
                         f"new days have stopped arriving")
    income = paged(call, "income ledger", "https://fapi.binance.com/fapi/v1/income", {}, start, now)
    fills, span = [], start
    while span < now:
        end = min(span + FILL_SPAN_MS, now)
        fills += paged(call, "fills", "https://fapi.binance.com/fapi/v1/userTrades",
                       {"symbol": INSTRUMENT}, span, end)
        span = end
    return {"fetched_at_ms": now,
            "account": account_identity(call),
            "window": {"start_ms": start, "end_ms": now},
            "daily_records_response": records.decode(),
            "income_responses": income,
            "trade_responses": fills}


def summary(doc):
    """The dates a document covers, for the log. Nothing else, not even a count."""
    days = sorted(dt.datetime.fromtimestamp(v["updateTime"] / 1000, dt.timezone.utc)
                  .strftime("%Y-%m-%d")
                  for v in json.loads(doc["daily_records_response"]).get("snapshotVos") or [])
    since = dt.datetime.fromtimestamp(doc["window"]["start_ms"] / 1000, dt.timezone.utc)
    return [f"daily records: {days[0] + ' to ' + days[-1] if days else 'none'}",
            f"income ledger and fills: from {since:%Y-%m-%d}"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="where to write the document")
    a = ap.parse_args()
    call = signed_caller(os.environ["BINANCE_API_KEY"], os.environ["BINANCE_API_SECRET"].encode())
    doc = fetch(call, int(time.time() * 1000))
    for line in summary(doc):
        print(line)
    with open(a.out, "wb") as f:
        f.write(json.dumps(doc, indent=1).encode())


if __name__ == "__main__":
    main()
