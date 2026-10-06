"""Checks of the fingerprint ledger that the archive workflow keeps.

The ledger is what would notice the exchange revising a day it had closed. It
lives inside the workflow, so the code under test is lifted out of the workflow
file itself: a copy here could pass while the deployed one was broken.

Run: python3 -m unittest discover -s tests
"""

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import unittest

WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".github", "workflows", "archive.yml")
START = "# A day the exchange has closed must never change afterwards."
END = "# Responses are kept as received,"
DAY = "2026-03-08"


def fingerprint_block():
    """The deployed fingerprint code, taken out of the workflow."""
    body = re.search(r"python3 - <<'EOF'\n(.*?)\n          EOF", open(WORKFLOW).read(),
                     re.S).group(1)
    lines = [line[10:] for line in body.split("\n")]
    first = next(i for i, l in enumerate(lines) if l.strip().startswith(START))
    last = next(i for i, l in enumerate(lines) if l.strip().startswith(END))
    return compile("\n".join(lines[first:last]), "archive.yml", "exec")


def day_ms(day, hour=23):
    return int(dt.datetime.strptime(day, "%Y-%m-%d").replace(
        tzinfo=dt.timezone.utc).timestamp() * 1000) + hour * 3_600_000


def position(amount, entry="50000", mark="49900", unrealized="10"):
    return {"symbol": "BTCUSDT", "positionAmt": amount, "entryPrice": entry,
            "markPrice": mark, "unRealizedProfit": unrealized}


EMPTY = position("0", "0", "49900", "0")


def snapshot(day, balance, positions=()):
    return {"updateTime": day_ms(day),
            "data": {"assets": [{"asset": "USDT", "walletBalance": balance,
                                 "marginBalance": balance}],
                     "position": list(positions)}}


def ledger_page(day, amount, tran=1):
    return json.dumps([{"time": day_ms(day, hour=12), "tranId": tran,
                        "incomeType": "COMMISSION", "income": amount}])


def fill_page(day, price, trade=1):
    return json.dumps([{"id": trade, "time": day_ms(day, hour=12), "symbol": "BTCUSDT",
                        "side": "SELL", "positionSide": "SHORT", "price": price, "qty": "0.001"}])


class FingerprintLedger(unittest.TestCase):

    def run_block(self, vos, income_bodies=(), trade_bodies=(), today="2026-03-12"):
        env = {"vos": vos, "income_bodies": list(income_bodies),
               "trade_bodies": list(trade_bodies), "hashlib": hashlib, "json": json, "os": os}

        class FixedNow(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=tz)

        env["dt"] = type("m", (), {"datetime": FixedNow, "timezone": dt.timezone,
                                   "timedelta": dt.timedelta})
        exec(fingerprint_block(), env)
        with open("archive/days.json") as f:
            return env["drift"], json.load(f)

    def rewrite(self, change):
        with open("archive/days.json") as f:
            known = json.load(f)
        change(known)
        with open("archive/days.json", "w") as f:
            json.dump(known, f)

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.back = os.getcwd()
        os.chdir(self.home)
        fake_env = os.path.join(self.home, "env")
        open(fake_env, "w").close()
        os.environ["GITHUB_ENV"] = fake_env
        self.addCleanup(os.chdir, self.back)

    # --- what is kept -----------------------------------------------------

    def test_a_first_sighting_records_every_closed_day(self):
        drift, known = self.run_block([snapshot(DAY, "100")], [ledger_page(DAY, "-1")],
                                      [fill_page(DAY, "50000")])
        self.assertEqual(drift, [])
        self.assertEqual(sorted(known), [DAY])
        self.assertEqual(sorted(known[DAY]), ["fills", "income", "raw", "valuation"])

    def test_the_same_fetch_again_reports_no_change(self):
        args = ([snapshot(DAY, "100", [position("-0.1")])], [ledger_page(DAY, "-1")],
                [fill_page(DAY, "50000")])
        self.run_block(*args)
        drift, known = self.run_block(*args)
        self.assertEqual(drift, [])
        self.assertNotIn("raw_changes", known[DAY])

    def test_the_first_sighting_is_the_one_kept(self):
        _, first = self.run_block([snapshot(DAY, "100")])
        self.run_block([snapshot(DAY, "999")])
        with open("archive/days.json") as f:
            self.assertEqual(json.load(f)[DAY]["valuation"], first[DAY]["valuation"])

    def test_a_new_day_is_added_without_disturbing_the_others(self):
        self.run_block([snapshot(DAY, "100")])
        drift, known = self.run_block([snapshot(DAY, "100"), snapshot("2026-03-09", "110")],
                                      today="2026-03-13")
        self.assertEqual(drift, [])
        self.assertEqual(sorted(known), [DAY, "2026-03-09"])

    def test_a_day_past_the_daily_records_span_is_not_drift(self):
        # The daily records are asked for over the last 29 days (fetch.py). A day that
        # has aged out of that span is absent from the copy, not revised.
        args = ([snapshot(DAY, "100", [position("-0.1")])], [ledger_page(DAY, "-1")],
                [fill_page(DAY, "50000")])
        _, first = self.run_block(*args)
        drift, known = self.run_block([], args[1], args[2], today="2026-04-08")
        self.assertEqual(drift, [])
        self.assertEqual(known[DAY]["valuation"], first[DAY]["valuation"])
        self.assertEqual(known[DAY]["raw"], first[DAY]["raw"])
        self.assertNotIn("used_changes", known[DAY])

    def test_a_day_past_the_ledger_span_is_not_drift(self):
        # The income ledger and the fills are asked for over the last 80 days (fetch.py).
        args = ([snapshot(DAY, "100")], [ledger_page(DAY, "-1")], [fill_page(DAY, "50000")])
        _, first = self.run_block(*args)
        drift, known = self.run_block([], [], [], today="2026-05-28")
        self.assertEqual(drift, [])
        self.assertEqual(known[DAY], first[DAY])

    def test_the_cut_first_day_of_the_ledger_span_is_not_drift(self):
        # On the 80th day the ledger's span starts inside the day, so part of it is gone.
        both = "[" + ledger_page(DAY, "-1")[1:-1] + ", " + ledger_page(DAY, "-2", tran=2)[1:-1] + "]"
        self.run_block([snapshot(DAY, "100")], [both])
        drift, _ = self.run_block([], [ledger_page(DAY, "-2", tran=2)], today="2026-05-27")
        self.assertEqual(drift, [])

    def test_a_ledger_entry_lost_inside_the_span_is_caught(self):
        self.run_block([snapshot(DAY, "100")], [ledger_page(DAY, "-1")])
        drift, _ = self.run_block([snapshot(DAY, "100")], [], today="2026-03-20")
        self.assertEqual(drift, [DAY])

    def test_a_day_the_exchange_may_still_complete_is_not_fingerprinted(self):
        # It completes a record after handing it out, so a day is
        # fingerprinted only once it has been settled for SETTLE_DAYS.
        _, known = self.run_block([snapshot(DAY, "100")], today="2026-03-10")
        self.assertNotIn(DAY, known)
        _, known = self.run_block([snapshot(DAY, "100")], today="2026-03-12")
        self.assertIn(DAY, known)

    def test_the_day_still_running_is_not_fingerprinted(self):
        # Its ledger is still filling; fingerprinting it would flag every run.
        _, known = self.run_block([snapshot("2026-03-09", "100"), snapshot("2026-03-10", "110")],
                                  today="2026-03-13")
        self.assertEqual(sorted(known), ["2026-03-09"])

    # --- what stops the job -----------------------------------------------

    def test_a_revised_balance_is_caught(self):
        self.run_block([snapshot(DAY, "100")])
        drift, _ = self.run_block([snapshot(DAY, "999")])
        self.assertEqual(drift, [DAY])

    def test_a_revised_margin_balance_alone_is_not_drift(self):
        # The exchange recomputes it after publishing a day; no figure is taken
        # from it, so it must not stop the job.
        self.run_block([snapshot(DAY, "100")])
        revised = snapshot(DAY, "100")
        revised["data"]["assets"][0]["marginBalance"] = "137"
        drift, _ = self.run_block([revised])
        self.assertEqual(drift, [])

    def test_a_revised_position_is_caught(self):
        self.run_block([snapshot(DAY, "100", [position("-0.1", entry="50000")])])
        drift, _ = self.run_block([snapshot(DAY, "100", [position("-0.1", entry="50001")])])
        self.assertEqual(drift, [DAY])

    def test_a_position_that_appears_with_a_quantity_is_caught(self):
        self.run_block([snapshot(DAY, "100", [EMPTY])])
        drift, _ = self.run_block([snapshot(DAY, "100", [EMPTY, position("0.2")])])
        self.assertEqual(drift, [DAY])

    def test_a_revised_ledger_entry_is_caught(self):
        self.run_block([snapshot(DAY, "100")], [ledger_page(DAY, "-1")])
        drift, _ = self.run_block([snapshot(DAY, "100")], [ledger_page(DAY, "-2")])
        self.assertEqual(drift, [DAY])

    def test_an_entry_added_to_a_closed_day_is_caught(self):
        self.run_block([snapshot(DAY, "100")], [ledger_page(DAY, "-1")])
        drift, _ = self.run_block([snapshot(DAY, "100")],
                                  [ledger_page(DAY, "-1"), ledger_page(DAY, "-3", tran=2)])
        self.assertEqual(drift, [DAY])

    def test_a_revised_fill_is_caught(self):
        self.run_block([snapshot(DAY, "100")], [], [fill_page(DAY, "50000")])
        drift, _ = self.run_block([snapshot(DAY, "100")], [], [fill_page(DAY, "50001")])
        self.assertEqual(drift, [DAY])

    # --- what is written down but does not stop it -------------------------

    def test_an_empty_position_entry_added_later_is_noticed_not_drift(self):
        # What the exchange has been seen to do to a day: one empty entry became two.
        self.run_block([snapshot(DAY, "100", [EMPTY])])
        drift, known = self.run_block([snapshot(DAY, "100", [EMPTY, EMPTY])])
        self.assertEqual(drift, [])
        self.assertEqual(len(known[DAY]["raw_changes"]), 1)
        self.assertEqual(known[DAY]["raw_changes"][0]["noticed"], "2026-03-12T00:00:00Z")

    def test_a_raw_change_is_noticed_once(self):
        self.run_block([snapshot(DAY, "100", [EMPTY])])
        self.run_block([snapshot(DAY, "100", [EMPTY, EMPTY])])
        _, known = self.run_block([snapshot(DAY, "100", [EMPTY, EMPTY])])
        self.assertEqual(len(known[DAY]["raw_changes"]), 1)

    def test_a_part_fingerprinted_for_the_first_time_is_not_a_change(self):
        # A ledger written before fills were kept has no fills fingerprint.
        args = ([snapshot(DAY, "100")], [ledger_page(DAY, "-1")], [fill_page(DAY, "50000")])
        self.run_block(*args)
        self.rewrite(lambda known: known[DAY].pop("fills"))
        drift, known = self.run_block(*args)
        self.assertEqual(drift, [])
        self.assertIn("fills", known[DAY])

    def test_a_ledger_from_before_this_rule_is_carried_over(self):
        # The ledger in an older layout: the raw record under "records",
        # no valuation fingerprint, and then the empty entry added by the exchange.
        self.run_block([snapshot(DAY, "100", [EMPTY])], [ledger_page(DAY, "-1")])

        def as_before(known):
            known[DAY]["records"] = known[DAY].pop("raw")
            known[DAY].pop("valuation")
            known[DAY].pop("fills")
        self.rewrite(as_before)
        drift, known = self.run_block([snapshot(DAY, "100", [EMPTY, EMPTY])],
                                      [ledger_page(DAY, "-1")])
        self.assertEqual(drift, [])
        self.assertNotIn("records", known[DAY])
        self.assertEqual(sorted(k for k in known[DAY] if k != "raw_changes"),
                         ["fills", "income", "raw", "valuation"])
        self.assertEqual(len(known[DAY]["raw_changes"]), 1)


if __name__ == "__main__":
    unittest.main()
