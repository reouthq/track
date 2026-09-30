"""Checks of fetching the exchange's records, against a stand-in for the exchange.

The stand-in answers as the exchange does: items in time order, both ends of the
requested span included, at most `limit` items a page. Asked for daily records,
it answers with those of the 30 days from the start of the span asked for and
no more, as the exchange was measured to.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch  # noqa: E402

DAY = 86_400_000
HOUR = 3_600_000
START = fetch.ACCOUNT_START_MS
RECORD_SPAN = 30 * DAY


def day_end(i):
    """The timestamp of the daily record of the i-th day from the first deposit."""
    return START + (i + 1) * DAY - 1000


UID = 123456789
ALIAS = "aliasOurs00000"


class Exchange:

    def __init__(self, income=(), fills=(), records=None, newest=None, failing=None,
                 uid=UID, alias=ALIAS):
        self.income = sorted(income, key=lambda x: x["time"])
        self.fills = sorted(fills, key=lambda x: x["time"])
        self.records = records    # a daily-records response to give as it is
        self.newest = newest      # the newest daily record held; None: every day that ended
        self.failing = failing
        self.uid, self.alias = uid, alias
        self.requests = []

    def __call__(self, url, params):
        self.requests.append((url, dict(params)))
        if self.failing and self.failing in url:
            return 400, b'{"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}'
        if url.endswith("/api/v3/account"):
            return 200, json.dumps({"accountType": "SPOT", "uid": self.uid} if self.uid
                                   else {"accountType": "SPOT"}).encode()
        if url.endswith("/fapi/v2/balance"):
            return 200, json.dumps([{"asset": "BNB", "accountAlias": "other"},
                                    {"asset": "USDT", "accountAlias": self.alias}] if self.alias
                                   else [{"asset": "BNB", "accountAlias": "other"}]).encode()
        if "accountSnapshot" in url:
            if self.records is not None:
                return 200, self.records
            end = min(params["endTime"], params["startTime"] + RECORD_SPAN,
                      self.newest if self.newest is not None else params["endTime"])
            stamps = [t for t in range(day_end(0), end + 1, DAY) if t >= params["startTime"]]
            return 200, json.dumps({"code": 200, "msg": "", "snapshotVos": [
                {"type": "futures", "updateTime": t, "data": {}} for t in stamps]}).encode()
        items = self.income if "income" in url else self.fills
        chosen = [x for x in items if params["startTime"] <= x["time"] <= params["endTime"]]
        return 200, json.dumps(chosen[:params["limit"]]).encode()


class TheAccountTheKeyBelongsTo(unittest.TestCase):
    """A key names no account of itself; the copy has to carry which one it read."""

    def test_the_copy_carries_the_user_and_the_futures_account(self):
        doc = fetch.fetch(Exchange(), START + 5 * DAY)
        self.assertEqual(doc["account"], {"uid": str(UID), "alias": ALIAS})

    def test_the_alias_is_the_one_of_the_base_currency(self):
        doc = fetch.fetch(Exchange(alias="aliasOther0000"), START + 5 * DAY)
        self.assertEqual(doc["account"]["alias"], "aliasOther0000")

    def test_an_exchange_that_names_no_user_stops_the_fetch(self):
        self.assertRaises(SystemExit, fetch.fetch, Exchange(uid=None), START + 5 * DAY)

    def test_an_account_with_no_balance_in_the_base_currency_stops_the_fetch(self):
        self.assertRaises(SystemExit, fetch.fetch, Exchange(alias=None), START + 5 * DAY)

    def test_the_identifiers_are_asked_for_every_time_the_records_are(self):
        exchange = Exchange()
        fetch.fetch(exchange, START + 5 * DAY)
        asked = [url for url, _ in exchange.requests]
        self.assertIn("https://api.binance.com/api/v3/account", asked)
        self.assertIn("https://fapi.binance.com/fapi/v2/balance", asked)


def ledger(times):
    return [{"time": t, "tranId": i, "incomeType": "COMMISSION", "income": "-0.12345678"}
            for i, t in enumerate(times)]


def unique_income(doc):
    return {json.dumps(e, sort_keys=True) for body in doc["income_responses"] for e in json.loads(body)}


def newest_record(doc):
    return max(v["updateTime"] for v in json.loads(doc["daily_records_response"])["snapshotVos"])


class Paging(unittest.TestCase):

    def test_every_entry_arrives_across_pages(self):
        exchange = Exchange(income=ledger(range(START + 1, START + 2501)))
        doc = fetch.fetch(exchange, START + 3 * DAY)
        self.assertEqual(len(unique_income(doc)), 2500)
        self.assertEqual(len(doc["income_responses"]), 3)

    def test_entries_sharing_a_millisecond_at_a_page_boundary_are_kept(self):
        times = list(range(START + 1, START + 998)) + [START + 5000] * 6 + list(range(START + 6000, START + 6400))
        exchange = Exchange(income=ledger(times))
        doc = fetch.fetch(exchange, START + 3 * DAY)
        self.assertEqual(len(unique_income(doc)), len(times))

    def test_a_full_page_within_one_millisecond_stops_the_fetch(self):
        exchange = Exchange(income=ledger([START + 7] * 1200))
        with self.assertRaises(SystemExit) as stop:
            fetch.fetch(exchange, START + 3 * DAY)
        self.assertIn("cannot be paged", str(stop.exception))

    def test_an_error_from_the_exchange_stops_with_its_code_and_message_only(self):
        exchange = Exchange(income=ledger([START + 1]), failing="income")
        with self.assertRaises(SystemExit) as stop:
            fetch.fetch(exchange, START + 3 * DAY)
        self.assertIn("HTTP 400", str(stop.exception))
        self.assertIn("code -1021", str(stop.exception))
        self.assertNotIn("0.12345678", str(stop.exception))


class DailyRecords(unittest.TestCase):

    def test_records_are_asked_for_from_the_first_deposit_while_it_is_recent(self):
        exchange = Exchange()
        fetch.fetch(exchange, START + 5 * DAY)
        asked = next(p for url, p in exchange.requests if "accountSnapshot" in url)
        self.assertEqual(asked["startTime"], START)

    def test_the_newest_days_arrive_once_the_first_deposit_is_further_back_than_the_exchange_answers_for(self):
        now = START + 45 * DAY + 2 * HOUR
        exchange = Exchange()
        doc = fetch.fetch(exchange, now)
        asked = next(p for url, p in exchange.requests if "accountSnapshot" in url)
        self.assertLessEqual(asked["endTime"] - asked["startTime"], RECORD_SPAN)
        self.assertEqual(newest_record(doc), day_end(44))

    def test_a_newest_record_a_day_behind_the_last_day_that_ended_passes(self):
        doc = fetch.fetch(Exchange(newest=day_end(8)), START + 10 * DAY + 2 * HOUR)
        self.assertEqual(newest_record(doc), day_end(8))

    def test_records_that_stopped_arriving_stop_the_fetch(self):
        with self.assertRaises(SystemExit) as stop:
            fetch.fetch(Exchange(newest=day_end(7)), START + 10 * DAY + 2 * HOUR)
        self.assertIn("stopped arriving", str(stop.exception))

    def test_no_record_at_all_stops_the_fetch(self):
        with self.assertRaises(SystemExit) as stop:
            fetch.fetch(Exchange(records=b'{"snapshotVos": []}'), START + 3 * DAY)
        self.assertIn("stopped arriving", str(stop.exception))


class Spans(unittest.TestCase):

    def test_fills_are_asked_for_in_spans_the_exchange_accepts(self):
        now = START + 20 * DAY
        exchange = Exchange()
        fetch.fetch(exchange, now)
        spans = [(p["startTime"], p["endTime"]) for url, p in exchange.requests if "userTrades" in url]
        self.assertTrue(all(end - start <= fetch.FILL_SPAN_MS for start, end in spans))
        self.assertEqual(spans[0][0], START)
        self.assertEqual(spans[-1][1], now)
        self.assertTrue(all(later[0] == earlier[1] for earlier, later in zip(spans, spans[1:])))

    def test_fills_across_spans_all_arrive(self):
        fills = [{"id": i, "time": START + i * DAY // 2} for i in range(1, 40)]
        doc = fetch.fetch(Exchange(fills=fills), START + 21 * DAY)
        self.assertEqual({t["id"] for b in doc["trade_responses"] for t in json.loads(b)},
                         set(range(1, 40)))

    def test_the_lookback_never_reaches_before_the_first_deposit(self):
        doc = fetch.fetch(Exchange(), START + 5 * DAY)
        self.assertEqual(doc["window"]["start_ms"], START)

    def test_the_lookback_never_exceeds_eighty_days(self):
        now = START + 200 * DAY
        doc = fetch.fetch(Exchange(), now)
        self.assertEqual(doc["window"]["start_ms"], now - 80 * DAY)


class Document(unittest.TestCase):

    def test_every_response_is_kept_as_received(self):
        records = b'{"snapshotVos": [{"updateTime": 1788739199000, "data": {}}]}'
        exchange = Exchange(income=ledger([START + 1, START + 2]), records=records)
        doc = fetch.fetch(exchange, START + 2 * DAY)
        self.assertEqual(doc["daily_records_response"], records.decode())
        self.assertEqual(json.loads(doc["income_responses"][0]),
                         json.loads(json.dumps(ledger([START + 1, START + 2]))))

    def test_the_summary_states_dates_and_no_count(self):
        records = b'{"snapshotVos": [{"updateTime": 1788739199000, "data": {"assets": [{"walletBalance": "1000.25"}]}}]}'
        exchange = Exchange(income=ledger([START + i for i in range(1, 14)]),
                            fills=[{"id": i, "time": START + i} for i in range(1, 18)], records=records)
        text = "\n".join(fetch.summary(fetch.fetch(exchange, START + 2 * DAY)))
        self.assertIn("2026-09-06", text)
        for hidden in ("13", "17", "1000", "0.12345678"):     # entries, fills, a balance, an amount
            self.assertNotIn(hidden, text)


if __name__ == "__main__":
    unittest.main()
