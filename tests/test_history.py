"""Checks of computing the record from every retained copy of the exchange's records.

The exchange hands out an account's daily records for 30 days only, so a record
older than that can only be computed from copies retained day by day. The copies
here are made by fetch.py itself, from a stand-in for the exchange that answers
as the exchange was measured to (tests/test_fetch.py).

Run: python3 -m unittest discover -s tests
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch  # noqa: E402
import pull  # noqa: E402

DAY = 86_400_000
HOUR = 3_600_000
START = fetch.ACCOUNT_START_MS
INCEPTION = pull.ms_to_day(START)
VERSIONS = [("2026-01-01", "1.0")]


def day(i):
    return pull.ms_to_day(START + i * DAY)


def record(i):
    """The daily record of day i: flat, the wallet less every day's funding and commission."""
    wallet = f"{1000 - 1.5 * (i + 1):.8f}"
    return {"type": "futures", "updateTime": START + (i + 1) * DAY - 1000,
            "data": {"assets": [{"asset": "USDT", "walletBalance": wallet, "marginBalance": wallet}],
                     "position": []}}


def ledger(i):
    return [{"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "-0.50000000",
             "asset": "USDT", "time": START + i * DAY, "tranId": 2 * i + 1},
            {"symbol": "BTCUSDT", "incomeType": "COMMISSION", "income": "-1.00000000",
             "asset": "USDT", "time": START + i * DAY + 12 * HOUR, "tranId": 2 * i + 2}]


def trades(i):
    """A position opened and closed within day i, at one price."""
    return [{"symbol": "BTCUSDT", "id": 2 * i + 1, "time": START + i * DAY + 10 * HOUR,
             "side": "BUY", "positionSide": "LONG", "qty": "0.010", "price": "100000.0"},
            {"symbol": "BTCUSDT", "id": 2 * i + 2, "time": START + i * DAY + 11 * HOUR,
             "side": "SELL", "positionSide": "LONG", "qty": "0.010", "price": "100000.0"}]


class Exchange:
    """Daily records for at most the 30 days from the start asked for; pages from the oldest."""

    def __call__(self, url, params):
        if url.endswith("/api/v3/account"):
            return 200, json.dumps({"uid": 123456789}).encode()
        if url.endswith("/fapi/v2/balance"):
            return 200, json.dumps([{"asset": "USDT", "accountAlias": "aliasOurs00000"}]).encode()
        start, end = params["startTime"], params["endTime"]
        if "accountSnapshot" in url:
            end = min(end, start + 30 * DAY)
        days = range(max(0, (start - START) // DAY - 1), (end - START) // DAY + 1)
        if "accountSnapshot" in url:
            vos = [record(i) for i in days if start <= record(i)["updateTime"] <= end]
            return 200, json.dumps({"code": 200, "msg": "", "snapshotVos": vos}).encode()
        items = [x for i in days for x in (ledger(i) if "income" in url else trades(i))
                 if start <= x["time"] <= end]
        return 200, json.dumps(items[:params["limit"]]).encode()


def copy_on(i):
    """The copy fetched on day i, at the hour of the daily run."""
    return fetch.fetch(Exchange(), START + i * DAY + 8 * HOUR + 30 * 60_000)


def with_records(copy, change):
    body = json.loads(copy["daily_records_response"])
    for v in body["snapshotVos"]:
        change(v)
    return dict(copy, daily_records_response=json.dumps(body))


def with_items(copy, name, change):
    """A copy whose ledger or fill pages hold change(item) for each item, or drop it for None."""
    pages = [json.dumps([y for y in (change(x) for x in json.loads(body)) if y is not None])
             for body in copy[name]]
    return dict(copy, **{name: pages})


def response(d):
    open_ms = pull.day_to_ms(d)
    return json.dumps([[open_ms, "0", "0", "0", "50000", "0", open_ms + DAY - 1]]).encode()


class DayByDay(unittest.TestCase):

    def publish(self, root, copies):
        history = pull.combine(copies)
        self.assertEqual(pull.check_entries(history)[1], [])
        records = pull.daily_records(history)
        closes = {r["date"]: 50_000.0 for r in records}
        equity, transfers, income, checks = pull.build(
            records, pull.income_entries(history), closes, VERSIONS, INCEPTION, 3.0)
        # A ledger entry left out of the combination would open a gap here.
        self.assertLessEqual(max((gap for _, gap in checks), default=0.0),
                             pull.RECONCILIATION_TOLERANCE)
        newest = max(copies, key=lambda c: c["fetched_at_ms"])
        private = pull.retained_copies({f"account/{newest['fetched_at_ms']}.json.enc":
                                        json.dumps(newest).encode()})
        manifest = pull.publish(root, equity, transfers, income, pull.monthly_rows(equity, transfers),
                                {r["date_utc"]: response(r["date_utc"]) for r in equity}, private)
        self.assertIsNotNone(manifest)
        return equity

    def test_the_record_goes_on_past_the_days_the_exchange_hands_out(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        copies = []
        for i in range(1, 46):
            copies.append(copy_on(i))
            equity = self.publish(root, copies)
            self.assertEqual(equity[-1]["date_utc"], day(i - 1))
        self.assertNotEqual(pull.daily_records(copies[-1])[0]["date"], INCEPTION)
        self.assertEqual([r["date_utc"] for r in equity], [day(i) for i in range(45)])
        first, last = (float(record(i)["data"]["assets"][0]["walletBalance"]) for i in (0, 44))
        self.assertAlmostEqual(equity[-1]["nav_idx"], 100 * last / first)


class Agreement(unittest.TestCase):

    def test_one_copy_gives_what_it_holds(self):
        copy = copy_on(9)
        history = pull.combine([copy])
        self.assertEqual(pull.daily_records(history), pull.daily_records(copy))
        self.assertEqual(pull.income_entries(history), pull.income_entries(copy))
        self.assertEqual(pull.fills_of(history), pull.fills_of(copy))

    def test_the_order_the_copies_are_given_in_does_not_matter(self):
        self.assertEqual(pull.combine([copy_on(5), copy_on(9)]), pull.combine([copy_on(9), copy_on(5)]))

    def test_an_entry_that_came_after_an_earlier_fetch_on_its_own_day_is_taken(self):
        # Fetched in the morning, the earlier copy holds day 5 only up to then.
        history = pull.combine([copy_on(5), copy_on(6)])
        self.assertIn(START + 5 * DAY + 12 * HOUR, [e["ts"] for e in pull.income_entries(history)])

    def test_a_copy_that_starts_inside_a_day_is_not_taken_for_that_day(self):
        # Fetched 82 days in, the later copy's ledger starts 80 days back, after day 2's funding.
        history = pull.combine([copy_on(60), copy_on(82)])
        self.assertIn(START + 2 * DAY, [e["ts"] for e in pull.income_entries(history)])

    def test_an_empty_position_entry_added_to_a_record_later_moves_nothing(self):
        def change(v):
            if v["updateTime"] == record(3)["updateTime"]:
                v["data"]["position"].append({"symbol": "BTCUSDT", "positionAmt": "0.000",
                                              "entryPrice": "0.0", "markPrice": "100000.0",
                                              "unRealizedProfit": "0.00000000"})
        history = pull.combine([copy_on(5), with_records(copy_on(6), change)])
        self.assertEqual(pull.daily_records(history),
                         pull.daily_records(pull.combine([copy_on(5), copy_on(6)])))


class Disagreement(unittest.TestCase):

    def assertStops(self, copies, words):
        with self.assertRaises(SystemExit) as stop:
            pull.combine(copies)
        self.assertIn(words, str(stop.exception))

    def test_a_record_the_exchange_revised_is_read_from_the_newest_copy(self):
        # The exchange completes a daily record after handing it out (as seen:
        # the position held at the valuation point appeared a day later). The day
        # is read from the newest copy, and named as revised.
        def change(v):
            if v["updateTime"] == record(3)["updateTime"]:
                v["data"]["assets"][0]["walletBalance"] = "995.00000000"
        history = pull.combine([with_records(copy_on(5), change), copy_on(6)])
        self.assertEqual(history["revised_days"], [day(3)])
        rows = {r["date"]: r for r in pull.daily_records(history)}
        self.assertEqual(rows[day(3)]["wallet"], float(record(3)["data"]["assets"][0]["walletBalance"]))

    def test_a_margin_balance_the_exchange_revised_does_not_stop_the_run(self):
        # The exchange recomputes the margin balance a day or two after handing a
        # day out, and no published figure is taken from it, so the copies may
        # differ there. The day is then read from the newest copy, whose positions
        # do add up to it.
        def stale(v):
            if v["updateTime"] == record(3)["updateTime"]:
                v["data"]["assets"][0]["marginBalance"] = "1995.00000000"
        history = pull.combine([with_records(copy_on(5), stale), copy_on(6)])
        rows = {r["date"]: r for r in pull.daily_records(history)}
        self.assertEqual(rows[day(3)]["nav"], rows[day(3)]["wallet"])

    def test_a_record_whose_positions_do_not_add_up_to_its_balance_stops_the_run(self):
        def change(v):
            v["data"]["assets"][0]["marginBalance"] = "1995.00000000"
        history = pull.combine([with_records(copy_on(6), change)])
        with self.assertRaises(SystemExit) as stop:
            pull.daily_records(history)
        self.assertIn("balance and its positions disagree", str(stop.exception))

    def test_a_ledger_entry_gone_from_a_later_copy_stops_the_run(self):
        gone = with_items(copy_on(6), "income_responses",
                          lambda e: None if e["time"] == START + 3 * DAY + 12 * HOUR else e)
        self.assertStops([copy_on(5), gone], f"income ledger of {day(3)}")

    def test_a_ledger_entry_whose_amount_differs_stops_the_run(self):
        changed = with_items(copy_on(6), "income_responses",
                             lambda e: dict(e, income="-1.10000000")
                             if e["time"] == START + 3 * DAY + 12 * HOUR else e)
        self.assertStops([copy_on(5), changed], f"income ledger of {day(3)}")

    def test_a_fill_that_differs_between_copies_stops_the_run(self):
        changed = with_items(copy_on(6), "trade_responses",
                             lambda t: dict(t, price="100001.0") if t["id"] == 7 else t)
        self.assertStops([copy_on(5), changed], f"fills of {day(3)}")

    def test_a_recorded_day_that_no_copy_holds_whole_stops_the_run(self):
        late = dict(copy_on(6), window={"start_ms": START + 2 * DAY + HOUR,
                                        "end_ms": START + 6 * DAY + 8 * HOUR})
        self.assertStops([late], f"of {day(0)} whole")

    def test_a_recorded_day_held_only_by_a_copy_fetched_before_it_ended_stops_the_run(self):
        early = dict(copy_on(6), fetched_at_ms=START + 5 * DAY + 8 * HOUR)
        self.assertStops([early], f"of {day(5)} whole")

    def test_a_copy_without_fills_stops_the_run(self):
        copy = copy_on(6)
        del copy["trade_responses"]
        self.assertStops([copy], "holds no fills")


if __name__ == "__main__":
    unittest.main()



class UnfinishedRecord(unittest.TestCase):
    """The exchange finishes a day's record after handing it out, as seen.

    pull.main leaves such a day for the next run and ends the record at the day
    before it; what it trims on is the check below.
    """

    def test_a_record_missing_the_position_the_fills_show_is_seen_as_unfinished(self):
        def strip_last(doc):
            vos = json.loads(doc["daily_records_response"])["snapshotVos"]
            vos[-1]["data"]["position"] = []
            return dict(doc, daily_records_response=json.dumps({"snapshotVos": vos}))

        # Day 5 ends holding a position: its closing fill is gone from the copy.
        held = with_items(copy_on(6), "trade_responses",
                          lambda t: None if t["id"] == 12 else t)
        _, behind = pull.check_entries(strip_last(held))
        self.assertIn(day(5), behind)
