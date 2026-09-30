#!/usr/bin/env python3
"""Produce the daily record from the exchange's own records.

Every figure here is defined in METHODOLOGY.md; the section numbers in the
comments point at the definition. No currency amount is printed or written:
the published series are returns and ratios relative to net asset value. Nor is
any count of the account's activity printed, such as how many days held
positions: the workflow's log is public, and such counts are trade statistics.

It reads every retained copy of the exchange's records together (`combine`).
Without --out it prints what it would publish, writing nothing. With --out it
publishes into that checkout of the record, anchors the new manifest and
completes the pending proofs.

Exit status: 0 when the run succeeded; 2 when the record was written but a
proof has stayed pending for too long, so that the workflow commits the record
and then reports the delay; anything else means nothing is to be committed.

    python3 pull.py --record-inception 2026-10-01 \
        --archive private/archive/*.json.enc \
        --passphrase-file PATH \
        [--out DIR] [--ots PATH]
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from decimal import Decimal

INSTRUMENT = "BTCUSDT"                                               # section 1
MARK_PRICE_URL = "https://fapi.binance.com/fapi/v1/markPriceKlines"
BENCHMARK_URL = "https://data-api.binance.vision/api/v3/klines"
BENCHMARK_SYMBOL = "BTCUSDT"

# Income types, by what they are to the record (section 2). External cash flows
# are transfers and credits: money that reaches the account by any way other
# than trading. A rebate or a reward is paid by the exchange, not earned from
# the market, and counted as a return it would be published as performance.
TRANSFER_TYPES = {"TRANSFER", "INTERNAL_TRANSFER"}
CREDIT_TYPES = {"REFERRAL_KICKBACK", "COMMISSION_REBATE", "API_REBATE", "FEE_RETURN",
                "CONTEST_REWARD", "BFUSD_REWARD"}
FLOW_TYPES = TRANSFER_TYPES | CREDIT_TYPES
COST_TYPES = {"COMMISSION", "FUNDING_FEE"}
REALIZED_TYPES = {"REALIZED_PNL"}
# Types the exchange reports that are neither a cash flow nor a cost nor a
# realized result, and are published under other_frac. A type outside all the
# sets stops the run: a credit of an unknown kind would otherwise be published
# as performance, which is how a deposit could be shown as a return.
OTHER_TYPES = {"INSURANCE_CLEAR", "CROSS_COLLATERAL_TRANSFER", "OPTIONS_PREMIUM_FEE",
               "OPTIONS_SETTLE_PROFIT", "POSITION_LIMIT_INCREASE_FEE", "DELIVERED_SETTELMENT",
               "COIN_SWAP_DEPOSIT", "COIN_SWAP_WITHDRAW", "AUTO_EXCHANGE",
               "STRATEGY_UMFUTURES_TRANSFER"}
KNOWN_TYPES = FLOW_TYPES | COST_TYPES | REALIZED_TYPES | OTHER_TYPES

# The wallet and the ledger are both exact to the exchange's own precision, so
# any real gap is a defect, not rounding. This leaves room only for float noise.
RECONCILIATION_TOLERANCE = 1e-9

# Section 1: every figure is in the account's base currency.
BASE_CURRENCY = "USDT"
# Section 2: a valuation point is the end of a UTC day. The exchange stamps it
# one second before midnight; this allows for it moving by a few minutes.
VALUATION_POINT_SLACK_MS = 5 * 60_000

# Entry prices rebuilt from fills are computed exactly; this only allows for the
# exchange stating an average to fewer digits than the division gives.
ENTRY_TOLERANCE = Decimal("1e-9")

# A proof is complete once the calendars' Bitcoin transaction confirms, which
# usually takes a few hours. One still pending this long after its commit is
# reported.
PROOF_PATIENCE_HOURS = 24

# Where the record keeps its proofs: those of the daily manifests, and those of
# the monthly reports' manifests (section 6).
PROOF_FOLDERS = ("attest", "reports")


# --- sources ---------------------------------------------------------------

def read_archive(path, passphrase_file):
    """Decrypt a retained copy of the exchange's records. Nothing touches the disk.

    Returns the copy as it was fetched, whose hash a manifest may list, and the
    document it holds.
    """
    plain = subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "600000",
         "-pass", f"file:{os.path.expanduser(passphrase_file)}", "-in", path],
        capture_output=True, check=True).stdout
    return plain, json.loads(plain)


# The salt of the account commitment, held with the record's other secrets. The
# identifiers it commits to are short enough to try every value, so the register
# carries a salted commitment and not a hash (tools/account_commitment.py).
ACCOUNT_SALT = "TRACK_ACCOUNT_SALT"


def account_commitment(salt, identity):
    """The commitment the account register carries for an account."""
    return hashlib.sha256(f"{salt}:{identity['uid']}:{identity['alias']}".encode()).hexdigest()


def registered_commitments(register_path):
    """The account commitments the register carries: every 64-hex string in it."""
    with open(register_path, encoding="utf-8") as f:
        return set(re.findall(r"\b[0-9a-f]{64}\b", f.read()))


def check_account(docs, registered, salt):
    """Refuse to produce the record from any account but the registered ones.

    A key names no account of itself, so every copy since the collector began
    asking carries the exchange's own answer to "whose key is this", and each
    answer must match a commitment in the register. Copies fetched before the
    collector asked carry none and are passed over; the newest copy must carry
    one, or the check could be dropped simply by no longer asking. Nothing is
    printed that would name the account.

    Returns the number of copies checked.
    """
    if not salt:
        raise SystemExit(f"{ACCOUNT_SALT} is not set; the account cannot be checked and "
                         f"the record is not produced")
    if not registered:
        raise SystemExit("the account register carries no account commitment; "
                         "the record is not produced")
    newest = max(docs, key=lambda d: d["fetched_at_ms"])
    if not newest.get("account"):
        raise SystemExit("the newest copy does not say which account the key belongs to; "
                         "the record is not produced")
    checked = 0
    for doc in docs:
        identity = doc.get("account")
        if not identity:
            continue
        if account_commitment(salt, identity) not in registered:
            raise SystemExit(f"the copy fetched at {ms_to_iso(doc['fetched_at_ms'])} was read "
                             f"from an account the register does not list; "
                             f"the record is not produced")
        checked += 1
    return checked


def daily_records(doc):
    """The exchange's daily record of the account: one net asset value a day.

    `nav = wallet + unrealized` (section 2), every term at the valuation point:
    the wallet balance of the record, plus each position's signed size times the
    record's mark price less the position's entry price.

    The record also states a margin balance, the wallet plus the exchange's own
    total of unrealized P&L, and that total is not used. Measured over the
    days before record inception, it was struck at the mark price of the day's last funding settlement
    (16:00 UTC) while the wallet and the mark price were those of the end of the
    day, which moved daily returns by up to 1.1 percentage points. It is still
    read for one purpose: the positions' stated P&L must add up to it, or the
    record is not internally consistent and nothing is produced.
    """
    out = []
    for v in json.loads(doc["daily_records_response"])["snapshotVos"]:
        data = v.get("data") or {}
        assets = data.get("assets") or []
        stated = data.get("position") or []
        ts = int(v["updateTime"])
        day = ms_to_day(ts)

        # Section 1: the base currency is USDT and no currency is converted, so
        # the wallet is the USDT balance alone. Another asset carrying a balance
        # would otherwise be added to it one for one.
        if not assets:
            raise SystemExit(f"on {day} the record holds no balance; the record is not produced")
        held_assets = [a for a in assets if float(a.get("walletBalance") or 0)
                       or float(a.get("marginBalance") or 0)]
        other = sorted({a.get("asset", "") for a in held_assets} - {BASE_CURRENCY})
        if other:
            raise SystemExit(f"on {day} the account holds {', '.join(other)} as well as "
                             f"{BASE_CURRENCY}; the record is not produced")
        base = [a for a in assets if a.get("asset") == BASE_CURRENCY]
        if not base:
            raise SystemExit(f"on {day} the record holds no {BASE_CURRENCY} balance; "
                             f"the record is not produced")
        wallet = sum(float(a["walletBalance"]) for a in base)
        margin = sum(float(a["marginBalance"]) for a in base)

        # Section 2: the valuation point is the end of the UTC day. A record
        # stamped at another hour would be published as an end-of-day value, and
        # the mark check cannot notice because it reads the same timestamp.
        if not 0 <= 86_400_000 - 1 - ts % 86_400_000 <= VALUATION_POINT_SLACK_MS:
            raise SystemExit(f"the record stamped {ms_to_iso(ts)} is not at the end of its UTC day; "
                             f"the record is not produced")

        owed = sum(float(p["unRealizedProfit"]) for p in stated)
        held_now = [p for p in stated if float(p["positionAmt"]) != 0]
        if not margin and held_now:
            raise SystemExit(f"on {day} the record holds positions but no margin balance to check "
                             f"them against; the record is not produced")
        if margin and abs((margin - wallet) - owed) / abs(margin) > RECONCILIATION_TOLERANCE:
            raise SystemExit(f"on {day} the record's balance and its positions disagree; "
                             f"the record is not produced")

        held = held_now
        marks = {float(p["markPrice"]) for p in held}
        if len(marks) > 1:
            raise SystemExit(f"on {day} the record carries more than one mark price; "
                             f"the record is not produced")
        mark = marks.pop() if marks else None
        unrealized = sum(float(p["positionAmt"]) * (mark - float(p["entryPrice"])) for p in held)

        out.append({"date": day, "ts": ts, "nav": wallet + unrealized,
                    "wallet": wallet, "mark": mark})
    out.sort(key=lambda r: r["ts"])
    return out


def income_entries(doc):
    """The account income ledger, de-duplicated across overlapping pages."""
    seen, out = set(), []
    for body in doc["income_responses"]:
        for e in json.loads(body):
            key = json.dumps(e, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append({"ts": int(e["time"]), "type": e["incomeType"],
                        "amount": float(e["income"])})
    out.sort(key=lambda e: e["ts"])
    return out


def fills_of(doc):
    """The instrument's fills, de-duplicated across overlapping pages, oldest first."""
    if "trade_responses" not in doc:
        raise SystemExit("the copy holds no fills, so no entry price can be confirmed; "
                         "the record is not produced")
    seen = {}
    for body in doc["trade_responses"]:
        for t in json.loads(body):
            seen[t["id"]] = t
    return sorted(seen.values(), key=lambda t: (int(t["time"]), t["id"]))


# The exchange finishes a day's record within this many days of the day ending
# (as measured: a day later). A day still inside the window may be read
# incomplete; one older than it that does not add up is an inconsistency.
SETTLE_DAYS = 3


def valuation(v):
    """The part of a daily record that the figures are computed from.

    The valuation point, the wallet balances and every position that holds a
    quantity. Two parts of a record are left out because the exchange revises
    them after handing the day out, and neither reaches a published figure. It
    has been seen to add an empty position entry, which moves nothing. And it
    recomputes the margin balance, whose unrealized P&L is marked at a different
    hour from the rest of the record (the reason net asset value is not taken
    from it, above); the margin balance is still read there, to check that the
    positions add up to it on the day the record is produced.
    """
    data = v.get("data") or {}
    return [int(v["updateTime"]),
            sorted([a.get("asset", ""), a.get("walletBalance", "")]
                   for a in data.get("assets") or []),
            sorted([p.get("symbol", ""), p.get("positionAmt", ""), p.get("entryPrice", ""),
                    p.get("markPrice", ""), p.get("unRealizedProfit", "")]
                   for p in data.get("position") or [] if Decimal(p.get("positionAmt") or "0"))]


def combine(copies):
    """One document from every retained copy of the exchange's records.

    The exchange hands out an account's daily records for 30 days only, and its
    income ledger and fills for a limited time, so a record older than that is
    computed from the copies retained day by day. Each day is taken from the
    newest copy that holds the whole of it.

    The exchange completes a daily record after handing it out. Its first record
    of a day has been seen to hold no position, and the position the account was
    holding at the valuation point to appear in the record a day later. The newest copy of a day therefore wins,
    and a day whose record was revised is named in the run's output. What keeps a
    revision from moving a figure already published is that published rows are
    final: a run that would change one stops. A revision of a day published
    earlier is an incident (section 5).

    The income ledger and the fills are another matter. An entry or a fill that
    changed after the day ended has never been seen, and would mean the account's
    history itself had been rewritten, so it stops the run, as does a recorded day
    that no copy holds whole after it ended.
    """
    records, ledger, fills, revised = {}, {}, {}, []
    for copy in sorted(copies, key=lambda c: c["fetched_at_ms"]):
        fetched = ms_to_day(copy["fetched_at_ms"])
        if "trade_responses" not in copy:
            raise SystemExit(f"the copy fetched on {fetched} holds no fills, so no entry price can "
                             f"be confirmed; the record is not produced")
        for v in json.loads(copy["daily_records_response"]).get("snapshotVos") or []:
            day = ms_to_day(int(v["updateTime"]))
            if day in records and valuation(records[day][1]) != valuation(v):
                revised.append(day)
            records[day] = (fetched, v)

        start = copy["window"]["start_ms"]
        first = ms_to_day(start + (-start) % 86_400_000)       # the first day it holds whole
        for what, kept, bodies, key in (
                ("income ledger", ledger, copy["income_responses"],
                 lambda e: json.dumps(e, sort_keys=True)),
                ("fills", fills, copy["trade_responses"], lambda t: str(t["id"]))):
            held = {}
            for body in bodies:
                for item in json.loads(body):
                    held.setdefault(ms_to_day(int(item["time"])), {})[key(item)] = item
            day = first
            while day <= fetched:
                closed = day < fetched
                items = held.get(day, {})
                if closed and day in kept and kept[day][1] and kept[day][2] != items:
                    raise SystemExit(f"the exchange's {what} of {day} differs between the copies "
                                     f"fetched on {kept[day][0]} and {fetched}; the record is not produced")
                kept[day] = (fetched, closed, items)
                day = ms_to_day(day_to_ms(day) + 86_400_000)

    for day in sorted(records):
        for what, kept in (("income ledger", ledger), ("fills", fills)):
            if not kept.get(day, (None, False))[1]:
                raise SystemExit(f"no copy holds the {what} of {day} whole after the day ended; "
                                 f"the record is not produced")

    if revised:
        print(f"# the exchange revised its record of {', '.join(sorted(set(revised)))}; "
              f"the newest copy of each day is the one read")
    return {"daily_records_response": json.dumps(
                {"snapshotVos": [records[day][1] for day in sorted(records)]}),
            "income_responses": [json.dumps(
                [e for day in sorted(ledger) for e in ledger[day][2].values()])],
            "trade_responses": [json.dumps(
                [t for day in sorted(fills) for t in fills[day][2].values()])],
            "revised_days": sorted(set(revised))}


def held_sides(v):
    """{side: (size, entry price)} for each side of a daily record that holds a quantity."""
    out = {}
    for p in (v.get("data") or {}).get("position") or []:
        amount = Decimal(p["positionAmt"])
        if amount:
            out["LONG" if amount > 0 else "SHORT"] = (abs(amount), Decimal(p["entryPrice"]))
    return out


def check_entries(doc):
    """Days whose positions do not follow from the previous record and the fills between.

    Starting from the sizes and entry prices of one daily record, every fill up
    to the next record's timestamp is applied the way the exchange keeps a
    position: a fill that adds to a side moves its entry price to the
    size-weighted average, a fill that reduces it leaves the entry price where it
    was, and a side that reaches zero starts again. The next record must show the
    same sizes and entry prices. That is what shows the record's positions to be
    those of the valuation point, which the valuation relies on (section 2).

    Returns (days checked, days that disagree). The first record in the copy has
    nothing before it and is not checked.
    """
    vos = sorted(json.loads(doc["daily_records_response"])["snapshotVos"],
                 key=lambda v: int(v["updateTime"]))
    fills = fills_of(doc)
    checked, wrong = [], []
    for prev, cur in zip(vos, vos[1:]):
        start, end = int(prev["updateTime"]), int(cur["updateTime"])
        book = {side: list(pos) for side, pos in held_sides(prev).items()}
        bad = False
        for t in fills:
            if not start < int(t["time"]) <= end:
                continue
            side = t["positionSide"]
            if side not in ("LONG", "SHORT"):          # the account is in hedge mode (section 1)
                bad = True
                break
            size, entry = book.get(side, [Decimal(0), Decimal(0)])
            qty, price = Decimal(t["qty"]), Decimal(t["price"])
            if (side == "LONG") == (t["side"] == "BUY"):
                book[side] = [size + qty, (size * entry + qty * price) / (size + qty)]
            else:
                left = size - qty
                book[side] = [left, entry if left > 0 else Decimal(0)]
        expected = {s: (q, e) for s, (q, e) in book.items() if q}
        actual = held_sides(cur)
        if not bad:
            bad = set(expected) != set(actual) or any(
                expected[s][0] != actual[s][0]
                or abs(expected[s][1] - actual[s][1]) > ENTRY_TOLERANCE * actual[s][1]
                for s in actual)
        checked.append(ms_to_day(end))
        if bad:
            wrong.append(ms_to_day(end))
    return checked, wrong


def mark_minute(ts):
    """Start of the minute that contains a timestamp."""
    return ts - ts % 60_000


def day_end_mark_candles(records):
    """The public mark-price candle of the minute that holds each record's timestamp.

    Public data, no key; one request for each day that held a position.
    """
    out = {}
    for r in records:
        start = mark_minute(r["ts"])
        q = urllib.parse.urlencode({"symbol": INSTRUMENT, "interval": "1m",
                                    "startTime": start, "limit": 1})
        with urllib.request.urlopen(f"{MARK_PRICE_URL}?{q}", timeout=30) as resp:
            rows = json.loads(resp.read())
        if rows and int(rows[0][0]) == start:
            out[r["date"]] = rows[0]
    return out


def check_marks(records, candles):
    """Days whose record does not carry the end-of-day mark price (section 2).

    The record's mark price must lie within the range of the public mark price
    in the minute that holds the record's timestamp. A day without that candle
    cannot be confirmed, and is listed as well.
    """
    wrong = []
    for r in records:
        if r["mark"] is None:
            continue
        k = candles.get(r["date"])
        if k is None or not float(k[3]) <= r["mark"] <= float(k[2]):
            wrong.append(r["date"])
    return wrong


def benchmark_responses(days):
    """The venue's response holding each day's candle, as received (sections 3 and 5).

    One request a day, for the candle that opens at the start of that day, so
    that the file published for a day is exactly the response its close is read
    from. Public data, no key.
    """
    out = {}
    for day in days:
        q = urllib.parse.urlencode({"symbol": BENCHMARK_SYMBOL, "interval": "1d",
                                    "startTime": day_to_ms(day), "limit": 1})
        with urllib.request.urlopen(f"{BENCHMARK_URL}?{q}", timeout=30) as r:
            out[day] = r.read()
    return out


def benchmark_close(body, day, now):
    """The close of a day's candle, read from the response that holds it.

    A candle whose close time is still ahead is forming: its last price is the
    price now, not a close. A response that does not hold the day's candle gives
    no close either.
    """
    rows = json.loads(body)
    if not rows or ms_to_day(int(rows[0][0])) != day or int(rows[0][6]) >= now:
        return None
    return float(rows[0][4])


def program_versions(register_path):
    """(deployed day, version) from the version register, oldest first."""
    rows = []
    for line in open(register_path):
        m = re.match(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", line)
        if m:
            rows.append((m.group(2), m.group(1)))
    rows.sort()
    if not rows:
        raise SystemExit(f"no version found in {register_path}")
    return rows


# --- time ------------------------------------------------------------------

def now_ms():
    return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)


def ms_to_day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def ms_to_iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_ms(iso):
    return int(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def day_to_ms(day):
    return int(dt.datetime.strptime(day, "%Y-%m-%d")
               .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


# --- the record ------------------------------------------------------------

def build(records, income, closes, versions, inception, leverage):
    """The three daily series of section 5.

    Returns (equity rows, transfer rows, income rows). Amounts stay inside this
    function: every value returned is a ratio or an index.
    """
    records = [r for r in records if r["date"] >= inception]
    if not records or records[0]["date"] != inception:
        raise SystemExit(f"no record of the account for record inception {inception}")

    equity, transfers, income_daily, checks = [], [], [], []
    idx = idx_l1 = 100.0
    prev = records[0]
    prev_close = closes.get(prev["date"])

    equity.append({"date_utc": prev["date"], "mark_ts_utc": ms_to_iso(prev["ts"]),
                   "flow_frac": None, "ret_twr": None, "nav_idx": idx,
                   "ret_l1": None, "nav_l1_idx": idx_l1,
                   "btc_close": prev_close, "ret_btc": None,
                   "version": version_at(versions, prev["date"])})

    for cur in records[1:]:
        # The valuation interval runs from the previous point (exclusive) to
        # this one (inclusive), and spans any day the exchange did not record.
        window = [e for e in income if prev["ts"] < e["ts"] <= cur["ts"]]
        unknown = sorted({e["type"] for e in window} - KNOWN_TYPES)
        if unknown:
            raise SystemExit(f"on {cur['date']} the income ledger holds {', '.join(unknown)}, "
                             f"which is neither a transfer nor a cost nor a result; a credit of an "
                             f"unknown kind would be published as performance. Classify it in "
                             f"pull.py; the record is not produced")
        flow = sum(e["amount"] for e in window if e["type"] in FLOW_TYPES)

        # Section 4. The net transfer is treated as occurring at the start.
        opening = prev["nav"] + flow
        if opening <= 0:
            raise SystemExit(f"the interval ending {cur['date']} opens at nothing to invest "
                             f"(the account was emptied or is past its wallet); "
                             f"the record is not produced")
        if cur["nav"] <= 0:
            raise SystemExit(f"on {cur['date']} the account is worth nothing or less; "
                             f"the record is not produced")
        ret = cur["nav"] / opening - 1
        ret_l1 = ret / leverage                                    # section 3
        idx *= 1 + ret
        idx_l1 *= 1 + ret_l1
        # A close the benchmark did not report leaves the day's return empty, and
        # the next day's too: carrying the last close forward would publish a
        # two-day move as one day's return (section 3).
        close = closes.get(cur["date"])
        ret_btc = (close / prev_close - 1) if close and prev_close else None

        equity.append({"date_utc": cur["date"], "mark_ts_utc": ms_to_iso(cur["ts"]),
                       "flow_frac": flow / prev["nav"], "ret_twr": ret, "nav_idx": idx,
                       "ret_l1": ret_l1, "nav_l1_idx": idx_l1,
                       "btc_close": close, "ret_btc": ret_btc,
                       "version": version_at(versions, cur["date"])})

        for e in window:
            if e["type"] in FLOW_TYPES:
                transfers.append({"ts_utc": ms_to_iso(e["ts"]),
                                  "amount_frac": e["amount"] / prev["nav"],
                                  "kind": "transfer" if e["type"] in TRANSFER_TYPES else "credit"})

        # Section 9: the types grouped under other_frac are named, without their
        # separate amounts. A name that is not a plain identifier could break the
        # published table, and is not published as it is.
        other = [e for e in window if e["type"] in OTHER_TYPES]
        names = sorted({e["type"] for e in other})
        if any(not re.fullmatch(r"[A-Z0-9_]+", name) for name in names):
            raise SystemExit(f"on {cur['date']} the income ledger holds a type whose name cannot be "
                             f"published as it is; the record is not produced")
        income_daily.append({
            "date_utc": cur["date"],
            "realized_pnl_frac": total(window, REALIZED_TYPES) / prev["nav"],
            "costs_frac": total(window, COST_TYPES) / prev["nav"],
            "other_frac": sum(e["amount"] for e in other) / prev["nav"],
            "other_types": ";".join(names),
        })

        # The wallet balance moves only by transfers and by the income ledger;
        # unrealized P&L sits outside it. So the two sources must agree, and a
        # disagreement means a missing ledger page, an unrecognized income type
        # or a misread balance field. Reported as a fraction, never as an amount.
        moved = cur["wallet"] - prev["wallet"]
        explained = sum(e["amount"] for e in window)  # transfers included
        checks.append((cur["date"], abs(moved - explained) / prev["nav"]))

        prev, prev_close = cur, close

    return equity, transfers, income_daily, checks


def total(entries, types):
    return sum(e["amount"] for e in entries if e["type"] in types)


def version_at(versions, day):
    live = [v for deployed, v in versions if deployed <= day]
    return live[-1] if live else versions[0][1]


# --- monthly statistics ----------------------------------------------------

def day_of(date_utc):
    return dt.date.fromisoformat(date_utc)


def link(returns):
    """The geometric link of daily returns (section 3); None when there is none.

    A day without a value is skipped: the next day's return already spans it.
    """
    returns = [r for r in returns if r is not None]
    if not returns:
        return None
    out = 1.0
    for r in returns:
        out *= 1 + r
    return out - 1


def sample_deviation(returns):
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    return math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))


def annualized_volatility(returns):
    """sqrt(365) times the standard deviation of daily returns (section 4)."""
    sd = sample_deviation(returns)
    return None if sd is None else math.sqrt(365) * sd


def sharpe_ratio(returns):
    """sqrt(365) times the mean daily return over its deviation, risk-free rate zero (section 4)."""
    sd = sample_deviation(returns)
    if not sd:
        return None
    return math.sqrt(365) * (sum(returns) / len(returns)) / sd


def correlation(pairs):
    """Correlation of daily returns with the benchmark's (section 3); None under three days."""
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if not sxx or not syy:
        return None
    return sxy / math.sqrt(sxx * syy)


def drawdowns(path):
    """(maximum drawdown, current drawdown, day of the last high) along [(day, index), ...].

    Measured on the index, not on net asset value, so that a transfer is neither
    a loss nor a recovery (section 4). An index equal to the high is a new high.
    """
    peak, peak_day, worst = path[0][1], path[0][0], 0.0
    for day, level in path:
        if level >= peak:
            peak, peak_day = level, day
        worst = max(worst, 1 - level / peak)
    return worst, 1 - path[-1][1] / peak, peak_day


def trailing(rows, through, days):
    """Time-weighted return over the trailing window of calendar days ending at `through`.

    Risk Limits, section 3. A window longer than the record runs from record
    inception.
    """
    end = day_of(through)
    return link([r["ret_twr"] for r in rows if (end - day_of(r["date_utc"])).days < days])


def full_months(inception, through):
    """Calendar months wholly within the record, the month of record inception not counted."""
    first, last = day_of(inception), day_of(through)
    count = (last.year - first.year) * 12 + (last.month - first.month)
    if (last + dt.timedelta(days=1)).month == last.month:
        count -= 1                                  # the last month has not ended
    return max(count, 0)


def money_weighted(equity, transfers):
    """Money-weighted return since record inception, and its basis (section 3).

    Worked out from the published ratios alone, so that anyone can reproduce it:
    the net asset value is rebuilt up to scale from `flow_frac` and `ret_twr`, and
    each transfer is sized by `amount_frac` against the value before it. Until the
    record spans 365 days the rate is stated for the period ("period"), and as an
    annual rate after ("annual").
    """
    if len(equity) < 2:
        return None, None
    ts = [iso_to_ms(r["mark_ts_utc"]) for r in equity]
    level = [1.0]
    for r in equity[1:]:
        level.append(level[-1] * (1 + r["flow_frac"]) * (1 + r["ret_twr"]))
    flows = [(ts[0], level[0])]
    for t in transfers:
        at = iso_to_ms(t["ts_utc"])
        i = next(k for k in range(1, len(ts)) if ts[k - 1] < at <= ts[k])
        flows.append((at, t["amount_frac"] * level[i - 1]))
    end, span = ts[-1], (ts[-1] - ts[0]) / 86_400_000

    def gap(y):
        return level[-1] - sum(f * (1 + y) ** ((end - at) / 86_400_000 / 365) for at, f in flows)

    lo, hi = -0.999999999, 1e9
    if gap(lo) * gap(hi) > 0:
        return None, None
    for _ in range(300):
        mid = (lo + hi) / 2
        if gap(lo) * gap(mid) <= 0:
            hi = mid
        else:
            lo = mid
    y = (lo + hi) / 2
    if span < 365:
        return (1 + y) ** (span / 365) - 1, "period"
    return y, "annual"


def monthly_rows(equity, transfers):
    """The rows of `data/monthly.csv`: one per calendar month (sections 3 to 5).

    Each row is struck at the last valuation point of the month that the record
    holds, stated in `through_utc`; for the month in progress that point moves
    with every run.
    """
    rows = []
    for month in sorted({r["date_utc"][:7] for r in equity}):
        upto = [r for r in equity if r["date_utc"][:7] <= month]
        inside = [r for r in upto if r["date_utc"][:7] == month]
        before = upto[:len(upto) - len(inside)]
        through = inside[-1]["date_utc"]
        month_returns = [r["ret_twr"] for r in inside if r["ret_twr"] is not None]
        all_returns = [r["ret_twr"] for r in upto if r["ret_twr"] is not None]
        pairs = [(r["ret_twr"], r["ret_btc"]) for r in inside
                 if r["ret_twr"] is not None and r["ret_btc"] is not None]
        opening = [(before[-1]["date_utc"], before[-1]["nav_idx"])] if before else []
        month_max = drawdowns(opening + [(r["date_utc"], r["nav_idx"]) for r in inside])[0]
        worst, current, high = drawdowns([(r["date_utc"], r["nav_idx"]) for r in upto])
        # For comparison (section 4): the same measure on the derived series and the Benchmark.
        worst_l1 = drawdowns([(r["date_utc"], r["nav_l1_idx"]) for r in upto])[0]
        closes = [(r["date_utc"], r["btc_close"]) for r in upto if r["btc_close"] is not None]
        worst_btc = drawdowns(closes)[0] if closes else None
        mwr, basis = money_weighted(upto, [t for t in transfers
                                           if t["ts_utc"] <= upto[-1]["mark_ts_utc"]])
        rows.append({
            "month": month,
            "through_utc": through,
            "ret_twr": link(month_returns),
            "ret_l1": link([r["ret_l1"] for r in inside]),
            "ret_btc": link([r["ret_btc"] for r in inside]),
            "ret_twr_itd": upto[-1]["nav_idx"] / 100 - 1 if all_returns else None,
            "ret_l1_itd": upto[-1]["nav_l1_idx"] / 100 - 1 if all_returns else None,
            "ret_btc_itd": link([r["ret_btc"] for r in upto]),
            "mwr_itd": mwr,
            "mwr_basis": basis,
            "vol_ann": annualized_volatility(month_returns),
            "vol_ann_itd": annualized_volatility(all_returns),
            "worst_day": min(month_returns) if month_returns else None,
            "best_day": max(month_returns) if month_returns else None,
            "worst_day_itd": min(all_returns) if all_returns else None,
            "best_day_itd": max(all_returns) if all_returns else None,
            "corr_btc": correlation(pairs),
            "sharpe_itd": (sharpe_ratio(all_returns)
                           if full_months(equity[0]["date_utc"], through) >= 12 else None),
            "return_days_itd": len(all_returns),
            "max_drawdown_month": month_max,
            "max_drawdown": worst,
            "max_drawdown_l1": worst_l1,
            "max_drawdown_btc": worst_btc,
            "drawdown": current,
            "days_underwater": (day_of(through) - day_of(high)).days,
            "trailing_30d": trailing(upto, through, 30),
            "trailing_65d": trailing(upto, through, 65),
        })
    return rows


# --- output ----------------------------------------------------------------

EQUITY_COLUMNS = ["date_utc", "mark_ts_utc", "flow_frac", "ret_twr", "nav_idx",
                  "ret_l1", "nav_l1_idx", "btc_close", "ret_btc", "version"]
INCOME_COLUMNS = ["date_utc", "realized_pnl_frac", "costs_frac", "other_frac", "other_types"]
TRANSFER_COLUMNS = ["ts_utc", "amount_frac", "kind"]
CORRECTIONS_COLUMNS = ["date", "file", "column", "published_value", "corrected_value",
                       "reason"]                                   # section 5
MONTHLY_COLUMNS = ["month", "through_utc",
                   "ret_twr", "ret_l1", "ret_btc",
                   "ret_twr_itd", "ret_l1_itd", "ret_btc_itd",
                   "mwr_itd", "mwr_basis",
                   "vol_ann", "vol_ann_itd",
                   "worst_day", "best_day", "worst_day_itd", "best_day_itd",
                   "corr_btc", "sharpe_itd", "return_days_itd",
                   "max_drawdown_month", "max_drawdown", "max_drawdown_l1", "max_drawdown_btc",
                   "drawdown", "days_underwater",
                   "trailing_30d", "trailing_65d"]
PLACES = {"flow_frac": 8, "ret_twr": 8, "ret_l1": 8, "ret_btc": 8,
          "nav_idx": 6, "nav_l1_idx": 6, "btc_close": 2,
          "amount_frac": 8, "realized_pnl_frac": 8, "costs_frac": 8, "other_frac": 8}
PLACES.update({c: 8 for c in MONTHLY_COLUMNS
               if c not in ("month", "through_utc", "mwr_basis", "return_days_itd",
                            "days_underwater")})


def as_csv(rows, columns):
    out = [",".join(columns)]
    for r in rows:
        out.append(",".join(fmt(c, r[c]) for c in columns))
    return "\n".join(out)


def check_unchanged(path, rows, columns):
    """A row that has been published is final.

    The series is recomputed from record inception on every run, so a change in
    any early value would move every later index. Whatever has already been
    published must come out of this run identical, character for character; a
    correction is issued through `data/corrections.csv` (section 5), never by
    rewriting a row.
    """
    if not os.path.exists(path):
        return 0
    published = open(path).read().splitlines()
    fresh = as_csv(rows, columns).splitlines()
    if not published:
        return 0
    if published[0] != fresh[0]:
        raise SystemExit(f"the columns of {path} have changed; the record is not produced")
    for i, line in enumerate(published[1:], start=1):
        if i >= len(fresh):
            raise SystemExit(f"this run drops the published row {line.split(',')[0]}; "
                             f"the record is not produced")
        if fresh[i] != line:
            raise SystemExit(f"this run would change the published row "
                             f"{line.split(',')[0]}; the record is not produced")
    return len(published) - 1


def check_monthly_unchanged(path, rows):
    """Monthly rows are final once a later month has a row (section 5).

    The one row that may be replaced is the last one published, and only while
    no later month has a row: it is the month in progress. Even then it must be
    the same month and must not move back in time.
    """
    if not os.path.exists(path):
        return
    published = open(path).read().splitlines()
    fresh = as_csv(rows, MONTHLY_COLUMNS).splitlines()
    if not published:
        return
    if published[0] != fresh[0]:
        raise SystemExit(f"the columns of {path} have changed; the record is not produced")
    if len(fresh) < len(published):
        raise SystemExit("this run drops a published month; the record is not produced")
    in_progress = len(published) - 1 if len(fresh) == len(published) else None
    for i, line in enumerate(published[1:], start=1):
        if i != in_progress:
            if fresh[i] != line:
                raise SystemExit(f"this run would change the final row of {line.split(',')[0]}; "
                                 f"the record is not produced")
            continue
        old, new = line.split(","), fresh[i].split(",")
        if new[0] != old[0] or new[1] < old[1]:
            raise SystemExit(f"this run would move the row of {old[0]} back; "
                             f"the record is not produced")


def fmt(column, value):
    if value is None:
        return ""
    if column in PLACES:
        return f"{value:.{PLACES[column]}f}"
    return str(value)


# --- publication -----------------------------------------------------------

def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def retained_copies(copies):
    """Every retained copy the figures were computed from, by the name it is kept under.

    A copy is retained encrypted as `account/NAME.enc` or `archive/NAME.enc`; the
    manifest lists it as `account/NAME` (sections 2 and 6), so that a verifier
    given the decrypted copy checks it with the same command as the published
    files. Every copy is listed, not only this run's: a day is read from the
    newest copy that holds it, so an older copy still decides published figures
    and belongs inside what the day's hash covers.
    """
    out = {}
    for path, plain in copies.items():
        name = os.path.basename(path)
        name = name[:-len(".enc")] if name.endswith(".enc") else name
        out[f"{os.path.basename(os.path.dirname(path)) or 'account'}/{name}"] = plain
    return out


def publish(root, equity, transfers, income_daily, monthly, benchmark, private):
    """Write the record into a checkout of it (sections 5 and 6), or write nothing.

    The manifest covers two kinds of file, so that the day's hash reaches
    everything the figures rest on: the published files, and `private`, the
    retained copies of the exchange's responses, listed by name with the hash of
    their plaintext (section 2). Only the first kind is written; the second are
    hashes of files that are not in the record, which is why the published check
    skips what it cannot find.

    Every check comes before the first write. A published row that would change,
    a published benchmark response that differs from the one received, a day
    without its benchmark response, or a manifest that already exists stops the
    run with nothing written.

    Returns the path of the manifest, named after the last day it publishes, or
    None when there is no new day to publish.
    """
    tables = [("data/equity_daily.csv", equity, EQUITY_COLUMNS),
              ("data/income_daily.csv", income_daily, INCOME_COLUMNS),
              ("data/transfers.csv", transfers, TRANSFER_COLUMNS)]
    published = check_unchanged(os.path.join(root, tables[0][0]), equity, EQUITY_COLUMNS)
    for rel, rows, columns in tables[1:]:
        check_unchanged(os.path.join(root, rel), rows, columns)
    check_monthly_unchanged(os.path.join(root, "data/monthly.csv"), monthly)
    tables.append(("data/monthly.csv", monthly, MONTHLY_COLUMNS))

    new_days = [r["date_utc"] for r in equity[published:]]
    if not new_days:
        return None
    last = new_days[-1]
    manifest = os.path.join(root, "attest", f"{last}.sha256")
    if os.path.exists(manifest):
        raise SystemExit(f"a manifest for {last} already exists; the record is not produced")

    raws = {}
    for day in (r["date_utc"] for r in equity):
        rel = f"raw/{day}/btc.json"
        path = os.path.join(root, rel)
        body = benchmark.get(day)
        if os.path.exists(path):
            if body is not None and read_bytes(path) != body:
                raise SystemExit(f"the benchmark response published for {day} differs from the "
                                 f"one received; the record is not produced")
        elif day in new_days:
            if body is None:
                raise SystemExit(f"no benchmark response for {day}; the record is not produced")
            raws[rel] = body
        else:
            raise SystemExit(f"{day} is published without its benchmark response; "
                             f"the record is not produced")

    # Nothing has been written up to here.
    for rel, rows, columns in tables:
        write_bytes(os.path.join(root, rel), (as_csv(rows, columns) + "\n").encode())
    corrections = "data/corrections.csv"
    if not os.path.exists(os.path.join(root, corrections)):
        write_bytes(os.path.join(root, corrections), (",".join(CORRECTIONS_COLUMNS) + "\n").encode())
    for rel, body in raws.items():
        write_bytes(os.path.join(root, rel), body)

    listed = {rel: read_bytes(os.path.join(root, rel))
              for rel in [t[0] for t in tables] + [corrections] + list(raws)}
    listed.update(private)
    write_bytes(manifest, "".join(f"{hashlib.sha256(data).hexdigest()}  {rel}\n"
                                  for rel, data in sorted(listed.items())).encode())
    return manifest


# --- anchoring -------------------------------------------------------------

def run_ots(ots, *args):
    return subprocess.run([ots, *args], capture_output=True, text=True)


def stamp(path, ots):
    """Anchor a file with OpenTimestamps; its proof is written beside it (section 6).

    The client submits the file's hash to public calendars and needs at least
    two of them to answer. The daily commit carries the manifest together with
    its proof, so a manifest that cannot be anchored is not committed; the next
    run publishes that day together with its own.
    """
    out = run_ots(ots, "stamp", path)
    if out.returncode != 0 or not os.path.exists(path + ".ots"):
        said = (out.stderr + out.stdout).strip().splitlines()
        raise SystemExit(f"{os.path.basename(path)} could not be anchored"
                         f"{': ' + said[-1] if said else ''}; the record is not committed")
    return path + ".ots"


def proof_complete(path, ots):
    """Whether a proof carries a Bitcoin block attestation, as the client itself decides."""
    out = run_ots(ots, "info", path)
    if out.returncode != 0:
        raise SystemExit(f"{path} is not a readable proof; the record is not produced")
    return "BitcoinBlockHeaderAttestation(" in out.stdout + out.stderr


def committed_at(root, rel):
    """When a file was added to the record's history, in milliseconds; None if it was not."""
    out = subprocess.run(["git", "-C", root, "log", "--diff-filter=A", "--format=%ct", "--", rel],
                         capture_output=True, text=True)
    seconds = out.stdout.split()
    return int(seconds[-1]) * 1000 if out.returncode == 0 and seconds else None


def upgrade_proofs(root, ots, now):
    """Complete the record's pending proofs, and name those pending for too long (section 6).

    A proof is pending until the calendars' Bitcoin transaction confirms. Each
    run asks the client to complete every pending proof. The client keeps the
    earlier proof as a backup beside it and refuses to upgrade while such a
    backup exists, so the backup is removed before and after: it is not part of
    the record. A proof still pending more than PROOF_PATIENCE_HOURS after it was
    committed is overdue; one not yet committed is not.

    Returns (complete, completed by this run, pending, overdue), each a list of
    paths relative to the checkout.
    """
    complete, completed, pending, overdue = [], [], [], []
    rels = [f"{folder}/{name}" for folder in PROOF_FOLDERS if os.path.isdir(os.path.join(root, folder))
            for name in sorted(os.listdir(os.path.join(root, folder))) if name.endswith(".ots")]
    for rel in rels:
        path = os.path.join(root, rel)
        if proof_complete(path, ots):
            complete.append(rel)
            continue
        backup = path + ".bak"
        if os.path.exists(backup):
            os.remove(backup)
        run_ots(ots, "upgrade", path)
        if os.path.exists(backup):
            os.remove(backup)
        if proof_complete(path, ots):
            completed.append(rel)
            continue
        pending.append(rel)
        since = committed_at(root, rel)
        if since is not None and now - since > PROOF_PATIENCE_HOURS * 3_600_000:
            overdue.append(rel)
    return complete, completed, pending, overdue


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record-inception", required=True, metavar="YYYY-MM-DD",
                    help="first valuation point: the end of this UTC day (section 1)")
    ap.add_argument("--archive", required=True, nargs="+", metavar="COPY",
                    help="every encrypted copy of the exchange's records; the newest is this run's")
    ap.add_argument("--passphrase-file", required=True)
    ap.add_argument("--leverage", type=float, default=3.0, help="section 1")
    ap.add_argument("--versions", default=os.path.join(os.path.dirname(__file__),
                                                       "attest", "versions.md"))
    ap.add_argument("--accounts", default=os.path.join(os.path.dirname(__file__),
                                                       "attest", "accounts.md"))
    ap.add_argument("--out", metavar="DIR",
                    help="a checkout of the record to publish into; without it nothing is written")
    ap.add_argument("--ots", default="ots", help="the OpenTimestamps client")
    a = ap.parse_args()

    copies = {path: read_archive(path, a.passphrase_file) for path in a.archive}
    # The newest copy holds this run's own responses, which the day's manifest lists.
    newest = max(copies, key=lambda path: copies[path][1]["fetched_at_ms"])
    checked = check_account([doc for _, doc in copies.values()],
                            registered_commitments(a.accounts), os.environ.get(ACCOUNT_SALT))
    print(f"# the account the key reads, against the register: agrees in {checked} copies")
    history = combine([doc for _, doc in copies.values()])
    records = daily_records(history)
    income = income_entries(history)
    if not records:
        raise SystemExit("the copies hold no record of the account")

    # The exchange finishes a day's record after handing it out, so its newest
    # record may still be missing the position held at that valuation point.
    # A day whose positions do not follow from the fills is not
    # published while it is still within that window; the record ends at the day
    # before it and gains the day once the exchange has finished it. A day older
    # than the window that does not follow is an inconsistency, and stops the run.
    _, behind = check_entries(history)
    behind = sorted(d for d in behind if d >= a.record_inception)
    if behind:
        unsettled = ms_to_day(now_ms() - SETTLE_DAYS * 86_400_000)
        stale = [d for d in behind if d < unsettled]
        if stale:
            raise SystemExit(f"the record's positions do not follow from the fills on "
                             f"{', '.join(stale)}; the record is not produced")
        records = [r for r in records if r["date"] < behind[0]]
        if not records:
            raise SystemExit(f"the exchange has not finished its record of {behind[0]}, and there "
                             f"is no earlier day; the record is not produced")
        print(f"# the exchange has not finished its record of {', '.join(behind)}; "
              f"the record ends at {records[-1]['date']}")

    held = [r for r in records if r["date"] >= a.record_inception and r["mark"] is not None]
    wrong = check_marks(held, day_end_mark_candles(held))
    if wrong:
        raise SystemExit(f"the record's mark price is not the end-of-day mark price on "
                         f"{', '.join(wrong)}; the record is not produced")
    print("# mark price of the record against the public mark price of its last minute: agrees")

    print("# sizes and entry prices of the record against the previous record and the fills "
          "between: agree")

    benchmark = benchmark_responses([r["date"] for r in records if r["date"] >= a.record_inception])
    now = now_ms()
    closes = {}
    for day, body in benchmark.items():
        close = benchmark_close(body, day, now)
        if close is not None:
            closes[day] = close

    equity, transfers, income_daily, checks = build(
        records, income, closes, program_versions(a.versions),
        a.record_inception, a.leverage)
    monthly = monthly_rows(equity, transfers)

    # The gap itself is not printed: a gap of one unit of the exchange's precision,
    # as a share of net asset value, would state the account's size.
    worst = max(checks, key=lambda c: c[1]) if checks else None
    if worst:
        if worst[1] > RECONCILIATION_TOLERANCE:
            raise SystemExit(f"the income ledger does not explain the wallet balance on "
                             f"{worst[0]}; the record is not produced")
        print(f"# wallet against income ledger: agrees within {RECONCILIATION_TOLERANCE:.0e} "
              f"of net asset value\n")

    if a.out:
        manifest = publish(a.out, equity, transfers, income_daily, monthly, benchmark,
                           retained_copies({path: plain for path, (plain, _) in copies.items()}))
        if manifest is None:
            print("# nothing new to publish; nothing written")
        else:
            print(f"# published into {a.out}, manifest {os.path.relpath(manifest, a.out)}:")
            print(open(manifest).read(), end="")
            proof = stamp(manifest, a.ots)
            print(f"# anchored: {os.path.relpath(proof, a.out)}, pending until Bitcoin confirms")
        complete, completed, pending, overdue = upgrade_proofs(a.out, a.ots, now_ms())
        print(f"# proofs: {len(complete)} complete, {len(completed)} completed by this run, "
              f"{len(pending)} pending")
        if overdue:
            print(f"# pending for more than {PROOF_PATIENCE_HOURS} hours after commit: "
                  f"{', '.join(overdue)}")
            sys.exit(2)
        return

    published = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "equity_daily.csv")
    kept = check_unchanged(published, equity, EQUITY_COLUMNS)
    print(f"# published rows unchanged by this run: {kept}")

    print(f"# test mode: nothing is written. {len(equity)} days from "
          f"{equity[0]['date_utc']} to {equity[-1]['date_utc']}\n")
    print("--- data/equity_daily.csv ---")
    print(as_csv(equity, EQUITY_COLUMNS))
    print("\n--- data/transfers.csv ---")
    print(as_csv(transfers, TRANSFER_COLUMNS) if transfers
          else "ts_utc,amount_frac\n(no external transfer in the period)")
    print("\n--- data/income_daily.csv ---")
    print(as_csv(income_daily, INCOME_COLUMNS))
    print("\n--- data/monthly.csv ---")
    print(as_csv(monthly, MONTHLY_COLUMNS))


if __name__ == "__main__":
    main()
