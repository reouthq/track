"""Checks of the figures in pull.py against cases whose answer is known.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pull  # noqa: E402

VERSIONS = [("2026-01-01", "1.0")]
L = 3.0


def mark(day):
    """The exchange marks its daily record at the end of the day."""
    return pull.day_to_ms(day) + 86_399_000


def rec(day, nav, wallet=None):
    return {"date": day, "ts": mark(day), "nav": float(nav),
            "wallet": float(nav if wallet is None else wallet), "mark": None}


def entry(day, kind, amount, hour=12):
    return {"ts": pull.day_to_ms(day) + hour * 3_600_000,
            "type": kind, "amount": float(amount)}


def build(records, income=(), closes=None, inception=None):
    return pull.build(list(records), list(income), dict(closes or {}), VERSIONS,
                      inception or records[0]["date"], L)


class Returns(unittest.TestCase):

    def test_return_without_a_flow(self):
        equity, _, _, _ = build([rec("2026-03-01", 100), rec("2026-03-02", 110)])
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.10)

    def test_a_deposit_alone_earns_nothing(self):
        # 100 in the account, 50 paid in, 150 at the end: nothing was earned.
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 150)],
            [entry("2026-03-02", "TRANSFER", 50)])
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.0)
        self.assertAlmostEqual(equity[1]["flow_frac"], 0.5)

    def test_a_deposit_is_removed_from_the_return(self):
        # 100 + 50 paid in, ending at 165: the 150 earned 10 per cent.
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 165)],
            [entry("2026-03-02", "TRANSFER", 50)])
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.10)

    def test_a_withdrawal_is_removed_from_the_return(self):
        # 100 less 40 taken out, ending at 66: the 60 earned 10 per cent.
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 66)],
            [entry("2026-03-02", "TRANSFER", -40)])
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.10)
        self.assertAlmostEqual(equity[1]["flow_frac"], -0.4)

    def test_a_flow_before_the_valuation_point_belongs_to_the_earlier_interval(self):
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 150), rec("2026-03-03", 150)],
            [entry("2026-03-02", "TRANSFER", 50)])
        self.assertAlmostEqual(equity[1]["flow_frac"], 0.5)
        self.assertAlmostEqual(equity[2]["flow_frac"], 0.0)


class Inception(unittest.TestCase):

    def test_the_first_row_is_indexed_at_100_and_has_no_return(self):
        equity, _, _, _ = build([rec("2026-03-01", 100), rec("2026-03-02", 110)])
        first = equity[0]
        self.assertEqual(first["nav_idx"], 100.0)
        self.assertEqual(first["nav_l1_idx"], 100.0)
        for column in ("ret_twr", "ret_l1", "flow_frac", "ret_btc"):
            self.assertIsNone(first[column])

    def test_days_before_record_inception_are_not_measured(self):
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 200), rec("2026-03-03", 220)],
            inception="2026-03-02")
        self.assertEqual([r["date_utc"] for r in equity], ["2026-03-02", "2026-03-03"])
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.10)

    def test_a_record_inception_the_exchange_did_not_record_is_refused(self):
        with self.assertRaises(SystemExit):
            build([rec("2026-03-01", 100)], inception="2026-02-01")


class Indices(unittest.TestCase):

    def test_the_index_compounds(self):
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 110), rec("2026-03-03", 121)])
        self.assertAlmostEqual(equity[2]["nav_idx"], 121.0)

    def test_the_one_times_series_is_the_return_divided_by_the_leverage(self):
        equity, _, _, _ = build([rec("2026-03-01", 100), rec("2026-03-02", 130)])
        self.assertAlmostEqual(equity[1]["ret_l1"], 0.30 / L)

    def test_the_one_times_index_compounds_on_its_own(self):
        # Not the levered index divided by L: each daily return is scaled first,
        # then linked, so the two differ once more than one day has passed.
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 130), rec("2026-03-03", 169)])
        self.assertAlmostEqual(equity[2]["nav_l1_idx"], 100 * 1.1 * 1.1)
        self.assertNotAlmostEqual(equity[2]["nav_l1_idx"], equity[2]["nav_idx"] / L)


class MissingDays(unittest.TestCase):

    def test_a_missed_day_has_no_row_and_the_next_return_spans_it(self):
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-03", 121)])
        self.assertEqual([r["date_utc"] for r in equity], ["2026-03-01", "2026-03-03"])
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.21)

    def test_the_spanning_interval_collects_the_income_of_both_days(self):
        _, _, income_daily, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-03", 100)],
            [entry("2026-03-02", "COMMISSION", -1), entry("2026-03-03", "COMMISSION", -2)])
        self.assertEqual(len(income_daily), 1)
        self.assertAlmostEqual(income_daily[0]["costs_frac"], -0.03)


class IncomeLedger(unittest.TestCase):

    def test_each_kind_of_income_is_reported_separately(self):
        _, _, income_daily, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 100)],
            [entry("2026-03-02", "REALIZED_PNL", 5),
             entry("2026-03-02", "COMMISSION", -1),
             entry("2026-03-02", "FUNDING_FEE", -2),
             entry("2026-03-02", "INSURANCE_CLEAR", -4),
             entry("2026-03-02", "TRANSFER", 50)])
        row = income_daily[0]
        self.assertAlmostEqual(row["realized_pnl_frac"], 0.05)
        self.assertAlmostEqual(row["costs_frac"], -0.03)   # commission and funding
        self.assertAlmostEqual(row["other_frac"], -0.04)   # never the transfer

    def test_the_types_grouped_as_other_income_are_named_without_their_amounts(self):
        _, _, income_daily, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 100)],
            [entry("2026-03-02", "REALIZED_PNL", 5),
             entry("2026-03-02", "INSURANCE_CLEAR", -4),
             entry("2026-03-02", "COMMISSION", -1),
             entry("2026-03-02", "AUTO_EXCHANGE", 1, hour=13),
             entry("2026-03-02", "INSURANCE_CLEAR", -2, hour=14),
             entry("2026-03-02", "TRANSFER", 50)])
        self.assertEqual(income_daily[0]["other_types"], "AUTO_EXCHANGE;INSURANCE_CLEAR")
        line = pull.as_csv(income_daily, pull.INCOME_COLUMNS).splitlines()[1]
        self.assertTrue(line.endswith(",AUTO_EXCHANGE;INSURANCE_CLEAR"), line)

    def test_a_rebate_or_a_reward_is_an_external_flow_and_not_a_return(self):
        # Paid by the exchange, not earned from the market: counted as a return it
        # would be published as performance.
        equity, transfers, income_daily, checks = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 103)],
            [entry("2026-03-02", "COMMISSION_REBATE", 1),
             entry("2026-03-02", "CONTEST_REWARD", 2, hour=13)])
        self.assertAlmostEqual(equity[1]["flow_frac"], 0.03)
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.0)
        self.assertEqual([t["kind"] for t in transfers], ["credit", "credit"])
        self.assertEqual(income_daily[-1]["other_types"], "")
        self.assertAlmostEqual(income_daily[-1]["other_frac"], 0.0)
        self.assertLessEqual(max(gap for _, gap in checks), pull.RECONCILIATION_TOLERANCE)

    def test_a_transfer_is_named_a_transfer(self):
        _, transfers, _, _ = build([rec("2026-03-01", 100), rec("2026-03-02", 150)],
                                   [entry("2026-03-02", "TRANSFER", 50)])
        self.assertEqual(transfers[0]["kind"], "transfer")

    def test_a_day_without_other_income_names_nothing(self):
        _, _, income_daily, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 100)],
            [entry("2026-03-02", "COMMISSION", -1), entry("2026-03-02", "REALIZED_PNL", 2)])
        self.assertEqual(income_daily[0]["other_types"], "")
        self.assertTrue(pull.as_csv(income_daily, pull.INCOME_COLUMNS).splitlines()[1].endswith(","))

    def test_a_type_name_that_could_break_the_published_table_is_refused(self):
        with self.assertRaises(SystemExit):
            build([rec("2026-03-01", 100), rec("2026-03-02", 100)],
                  [entry("2026-03-02", "ODD,NAME", 1)])

    def test_a_transfer_is_published_as_a_share_of_the_previous_value(self):
        _, transfers, _, _ = build(
            [rec("2026-03-01", 200), rec("2026-03-02", 250)],
            [entry("2026-03-02", "TRANSFER", 50, hour=6)])
        self.assertEqual(len(transfers), 1)
        self.assertAlmostEqual(transfers[0]["amount_frac"], 0.25)
        self.assertEqual(transfers[0]["ts_utc"], "2026-03-02T06:00:00Z")


class Reconciliation(unittest.TestCase):
    """The wallet balance moves only by the income ledger, transfers included."""

    def test_a_consistent_day_leaves_no_gap(self):
        _, _, _, checks = build(
            [rec("2026-03-01", 100, wallet=100), rec("2026-03-02", 120, wallet=104)],
            [entry("2026-03-02", "REALIZED_PNL", 5), entry("2026-03-02", "COMMISSION", -1)])
        self.assertLess(checks[0][1], pull.RECONCILIATION_TOLERANCE)

    def test_a_missing_ledger_entry_is_caught(self):
        _, _, _, checks = build(
            [rec("2026-03-01", 100, wallet=100), rec("2026-03-02", 120, wallet=104)],
            [entry("2026-03-02", "REALIZED_PNL", 5)])   # the commission is missing
        self.assertGreater(checks[0][1], pull.RECONCILIATION_TOLERANCE)

    def test_an_income_type_nobody_classified_stops_the_run(self):
        # It moves the wallet, so the reconciliation stays silent: a credit of an
        # unknown kind would be published as performance. Verified against the exchange:
        # one INTERNAL_TRANSFER of 100 on a 100 -> 200 day published +100%.
        with self.assertRaises(SystemExit) as stop:
            build([rec("2026-03-01", 100, wallet=100), rec("2026-03-02", 100, wallet=107)],
                  [entry("2026-03-02", "SOMETHING_NEW", 7)])
        self.assertIn("SOMETHING_NEW", str(stop.exception))

    def test_an_internal_transfer_is_a_cash_flow_not_a_return(self):
        equity, transfers, _, _ = build(
            [rec("2026-03-01", 100, wallet=100), rec("2026-03-02", 200, wallet=200)],
            [entry("2026-03-02", "INTERNAL_TRANSFER", 100)])
        self.assertAlmostEqual(equity[1]["ret_twr"], 0.0)
        self.assertAlmostEqual(equity[1]["flow_frac"], 1.0)
        self.assertEqual(len(transfers), 1)


class AnEmptiedAccount(unittest.TestCase):
    """An interval with nothing to invest, and an account worth nothing or less."""

    def test_a_withdrawal_that_empties_the_account_stops_the_run(self):
        with self.assertRaises(SystemExit) as stop:
            build([rec("2026-03-01", 100, wallet=100), rec("2026-03-02", 0, wallet=0)],
                  [entry("2026-03-02", "TRANSFER", -100)])
        self.assertIn("opens at nothing to invest", str(stop.exception))

    def test_an_account_worth_less_than_nothing_stops_the_run(self):
        # Past the wallet after a liquidation: the index would turn negative and
        # every later return would have its sign flipped.
        with self.assertRaises(SystemExit) as stop:
            build([rec("2026-03-01", 100, wallet=100), rec("2026-03-02", -5, wallet=-5)],
                  [entry("2026-03-02", "REALIZED_PNL", -105)])
        self.assertIn("worth nothing or less", str(stop.exception))


class Benchmark(unittest.TestCase):

    def test_the_benchmark_return_comes_from_the_daily_closes(self):
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 100)],
            closes={"2026-03-01": 50_000.0, "2026-03-02": 55_000.0})
        self.assertAlmostEqual(equity[1]["ret_btc"], 0.10)
        self.assertEqual(equity[1]["btc_close"], 55_000.0)

    def test_a_close_the_venue_did_not_publish_leaves_two_returns_empty(self):
        # The day of the missing close, and the day after it: carrying the last
        # close forward would publish a two-day move as one day's return.
        equity, _, _, _ = build(
            [rec("2026-03-01", 100), rec("2026-03-02", 100), rec("2026-03-03", 100)],
            closes={"2026-03-01": 50_000.0, "2026-03-03": 55_000.0})
        self.assertIsNone(equity[1]["ret_btc"])
        self.assertIsNone(equity[2]["ret_btc"])
        self.assertEqual(equity[2]["btc_close"], 55_000.0)


class BenchmarkResponses(unittest.TestCase):

    @staticmethod
    def response(day, close):
        open_ms = pull.day_to_ms(day)
        return json.dumps([[open_ms, "0", "0", "0", str(close), "0", open_ms + 86_399_999]]).encode()

    def test_a_day_that_has_ended_gives_its_close(self):
        body = self.response("2026-03-01", 50_000)
        self.assertEqual(pull.benchmark_close(body, "2026-03-01", pull.day_to_ms("2026-03-02")),
                         50_000.0)

    def test_the_day_still_running_is_not_a_close(self):
        # The candle of the current day carries the price now, not a close.
        body = self.response("2026-03-02", 51_000)
        self.assertIsNone(pull.benchmark_close(body, "2026-03-02",
                                               pull.day_to_ms("2026-03-02") + 3_600_000))

    def test_a_response_holding_another_day_gives_no_close(self):
        body = self.response("2026-03-01", 50_000)
        self.assertIsNone(pull.benchmark_close(body, "2026-03-02", pull.day_to_ms("2026-03-05")))

    def test_an_empty_response_gives_no_close(self):
        self.assertIsNone(pull.benchmark_close(b"[]", "2026-03-01", pull.day_to_ms("2026-03-05")))

    def test_a_candle_covers_exactly_one_utc_day(self):
        k = json.loads(self.response("2026-03-01", 50_000))[0]
        self.assertEqual(k[6] - k[0] + 1, 86_400_000)


class PublishedRowsAreFinal(unittest.TestCase):

    COLUMNS = ["date_utc", "ret_twr"]
    ROWS = [{"date_utc": "2026-03-01", "ret_twr": None},
            {"date_utc": "2026-03-02", "ret_twr": 0.10}]

    def write(self, text):
        import tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_an_identical_run_is_accepted(self):
        path = self.write(pull.as_csv(self.ROWS, self.COLUMNS))
        self.assertEqual(pull.check_unchanged(path, self.ROWS, self.COLUMNS), 2)

    def test_a_further_day_may_be_appended(self):
        path = self.write(pull.as_csv(self.ROWS[:1], self.COLUMNS))
        self.assertEqual(pull.check_unchanged(path, self.ROWS, self.COLUMNS), 1)

    def test_a_changed_value_is_refused(self):
        path = self.write(pull.as_csv(self.ROWS, self.COLUMNS))
        moved = [self.ROWS[0], {"date_utc": "2026-03-02", "ret_twr": 0.11}]
        with self.assertRaises(SystemExit):
            pull.check_unchanged(path, moved, self.COLUMNS)

    def test_a_dropped_day_is_refused(self):
        path = self.write(pull.as_csv(self.ROWS, self.COLUMNS))
        with self.assertRaises(SystemExit):
            pull.check_unchanged(path, self.ROWS[:1], self.COLUMNS)

    def test_changed_columns_are_refused(self):
        path = self.write(pull.as_csv(self.ROWS, self.COLUMNS))
        with self.assertRaises(SystemExit):
            pull.check_unchanged(path, self.ROWS, ["date_utc"])

    def test_nothing_published_yet_is_not_an_error(self):
        self.assertEqual(pull.check_unchanged("/nonexistent.csv", self.ROWS, self.COLUMNS), 0)


class Determinism(unittest.TestCase):

    def test_the_same_input_gives_the_same_bytes(self):
        records = [rec("2026-03-01", 100), rec("2026-03-02", 137.7),
                   rec("2026-03-03", 101.19)]
        income = [entry("2026-03-02", "TRANSFER", 33.3),
                  entry("2026-03-03", "COMMISSION", -0.17)]
        closes = {"2026-03-01": 50_000.0, "2026-03-02": 51_234.56, "2026-03-03": 49_876.54}
        first = pull.as_csv(build(records, income, closes)[0], pull.EQUITY_COLUMNS)
        second = pull.as_csv(build(records, income, closes)[0], pull.EQUITY_COLUMNS)
        self.assertEqual(first, second)
        self.assertNotIn("e-", first)      # no exponent form in a published figure
        self.assertNotIn("nan", first.lower())


class Register(unittest.TestCase):

    def test_the_version_in_force_is_the_last_one_deployed(self):
        versions = [("2026-01-01", "1.3"), ("2026-03-02", "1.4")]
        self.assertEqual(pull.version_at(versions, "2026-03-01"), "1.3")
        self.assertEqual(pull.version_at(versions, "2026-03-02"), "1.4")
        self.assertEqual(pull.version_at(versions, "2026-03-03"), "1.4")


def position(amount, entry_price, mark_price, stated):
    return {"symbol": "BTCUSDT", "positionAmt": str(amount), "entryPrice": str(entry_price),
            "markPrice": str(mark_price), "unRealizedProfit": str(stated)}


def record_doc(day, wallet, positions, margin=None):
    """A daily record whose margin balance agrees with its positions' stated P&L."""
    stated = sum(float(p["unRealizedProfit"]) for p in positions)
    margin = wallet + stated if margin is None else margin
    return {"daily_records_response": json.dumps({"snapshotVos": [
        {"updateTime": mark(day),
         "data": {"assets": [{"asset": "USDT", "walletBalance": str(wallet),
                             "marginBalance": str(margin)}],
                  "position": positions}}]})}


class Valuation(unittest.TestCase):
    """nav = wallet + each position's size times (record mark price - entry price)."""

    def test_a_flat_account_is_worth_its_wallet(self):
        r = pull.daily_records(record_doc("2026-03-01", 100.5, []))[0]
        self.assertEqual(r["nav"], 100.5)
        self.assertEqual(r["wallet"], 100.5)
        self.assertIsNone(r["mark"])
        self.assertEqual(r["date"], "2026-03-01")

    def test_a_short_position_gains_when_the_mark_is_below_its_entry(self):
        doc = record_doc("2026-03-01", 100, [position(-0.1, 50_000, 49_000, 100)])
        self.assertAlmostEqual(pull.daily_records(doc)[0]["nav"], 200.0)

    def test_a_long_position_gains_when_the_mark_is_above_its_entry(self):
        doc = record_doc("2026-03-01", 100, [position(0.2, 50_000, 51_000, 200)])
        self.assertAlmostEqual(pull.daily_records(doc)[0]["nav"], 300.0)

    def test_both_sides_of_a_hedge_are_added(self):
        doc = record_doc("2026-03-01", 100, [position(0.2, 50_000, 51_000, 200),
                                             position(-0.1, 52_000, 51_000, 100)])
        self.assertAlmostEqual(pull.daily_records(doc)[0]["nav"], 400.0)

    def test_the_exchanges_own_total_of_unrealized_pnl_is_not_used(self):
        # The stated P&L was struck at another price: 60, where the record's mark
        # price gives 100. The balance agrees with the stale figure; nav does not.
        doc = record_doc("2026-03-01", 100, [position(-0.1, 50_000, 49_000, 60)])
        r = pull.daily_records(doc)[0]
        self.assertAlmostEqual(r["nav"], 200.0)
        self.assertEqual(r["mark"], 49_000.0)

    def test_a_record_whose_balance_disagrees_with_its_positions_is_refused(self):
        doc = record_doc("2026-03-01", 100, [position(-0.1, 50_000, 49_000, 7)], margin=100)
        with self.assertRaises(SystemExit):
            pull.daily_records(doc)

    def test_a_record_with_two_mark_prices_is_refused(self):
        doc = record_doc("2026-03-01", 100, [position(0.2, 50_000, 51_000, 200),
                                             position(-0.1, 52_000, 51_001, 100.1)])
        with self.assertRaises(SystemExit):
            pull.daily_records(doc)

    def test_an_emptied_position_left_in_the_record_is_ignored(self):
        doc = record_doc("2026-03-01", 100, [position(0, 50_000, 1, 0)])
        r = pull.daily_records(doc)[0]
        self.assertEqual(r["nav"], 100.0)
        self.assertIsNone(r["mark"])


class WhatARecordMustHold(unittest.TestCase):
    """Guards on the exchange's daily record itself (sections 1 and 2)."""

    def stops(self, doc, words):
        with self.assertRaises(SystemExit) as stop:
            pull.daily_records(doc)
        self.assertIn(words, str(stop.exception))

    def test_a_balance_in_another_currency_stops_the_run(self):
        # No currency is converted (section 1), so another asset would be added
        # to the wallet one for one.
        doc = record_doc("2026-03-01", 100, [])
        v = json.loads(doc["daily_records_response"])["snapshotVos"][0]
        v["data"]["assets"].append({"asset": "BNB", "walletBalance": "2.5", "marginBalance": "2.5"})
        doc = {"daily_records_response": json.dumps({"snapshotVos": [v]})}
        self.stops(doc, "holds BNB as well as USDT")

    def test_a_zero_balance_in_another_currency_is_ignored(self):
        doc = record_doc("2026-03-01", 100, [])
        v = json.loads(doc["daily_records_response"])["snapshotVos"][0]
        v["data"]["assets"].append({"asset": "BNB", "walletBalance": "0", "marginBalance": "0"})
        doc = {"daily_records_response": json.dumps({"snapshotVos": [v]})}
        self.assertEqual(pull.daily_records(doc)[0]["nav"], 100)

    def test_a_record_without_a_balance_stops_the_run(self):
        # It would otherwise be published as a day worth nothing, and final.
        doc = {"daily_records_response": json.dumps({"snapshotVos": [
            {"updateTime": mark("2026-03-01"), "data": {}}]})}
        self.stops(doc, "holds no balance")

    def test_a_record_stamped_at_another_hour_stops_the_run(self):
        # The mark check reads the same timestamp, so it cannot notice.
        doc = record_doc("2026-03-01", 100, [])
        v = json.loads(doc["daily_records_response"])["snapshotVos"][0]
        v["updateTime"] = mark("2026-03-01") - 8 * 3_600_000
        doc = {"daily_records_response": json.dumps({"snapshotVos": [v]})}
        self.stops(doc, "not at the end of its UTC day")

    def test_positions_without_a_margin_balance_stop_the_run(self):
        # The balance-versus-positions check divides by the margin balance, so a
        # zero would skip the only check there is on the record.
        doc = record_doc("2026-03-01", 100, [position("0.1", 50000, 51000, 100)], margin=0)
        self.stops(doc, "no margin balance to check")

    def test_a_negative_margin_balance_is_still_checked(self):
        # Dividing by a negative margin made every comparison pass.
        doc = record_doc("2026-03-01", -100, [position("0.1", 50000, 51000, 999)], margin=-100)
        self.stops(doc, "balance and its positions disagree")


class EndOfDayMarkPrice(unittest.TestCase):

    @staticmethod
    def minute(low, high):
        return [0, "0", str(high), str(low), "0", "0", 0]

    @staticmethod
    def held(day, mark_price):
        return {"date": day, "ts": mark(day), "nav": 1.0, "wallet": 1.0, "mark": mark_price}

    def test_the_minute_asked_for_holds_the_valuation_point(self):
        self.assertEqual(pull.mark_minute(mark("2026-03-01")),
                         pull.day_to_ms("2026-03-01") + 23 * 3_600_000 + 59 * 60_000)

    def test_a_mark_price_within_the_last_minute_is_accepted(self):
        wrong = pull.check_marks([self.held("2026-03-01", 50_000.0)],
                                 {"2026-03-01": self.minute(49_990, 50_010)})
        self.assertEqual(wrong, [])

    def test_a_mark_price_from_earlier_in_the_day_is_refused(self):
        wrong = pull.check_marks([self.held("2026-03-01", 50_200.0)],
                                 {"2026-03-01": self.minute(49_990, 50_010)})
        self.assertEqual(wrong, ["2026-03-01"])

    def test_a_day_without_its_minute_cannot_be_confirmed(self):
        self.assertEqual(pull.check_marks([self.held("2026-03-01", 50_000.0)], {}),
                         ["2026-03-01"])

    def test_a_day_without_positions_needs_no_mark(self):
        self.assertEqual(pull.check_marks([self.held("2026-03-01", None)], {}), [])


class LedgerPages(unittest.TestCase):

    def test_overlapping_ledger_pages_are_not_counted_twice(self):
        one = {"time": 1, "incomeType": "COMMISSION", "income": "-1"}
        two = {"time": 2, "incomeType": "COMMISSION", "income": "-2"}
        doc = {"income_responses": [json.dumps([one, two]), json.dumps([two])]}
        self.assertEqual(len(pull.income_entries(doc)), 2)

    def test_two_entries_of_the_same_size_at_the_same_instant_both_survive(self):
        # Two identical fills in one millisecond are one page apart at worst;
        # the exchange gives each its own transaction id.
        a = {"time": 1, "tranId": 10, "incomeType": "COMMISSION", "income": "-1"}
        b = {"time": 1, "tranId": 11, "incomeType": "COMMISSION", "income": "-1"}
        doc = {"income_responses": [json.dumps([a, b])]}
        self.assertEqual(len(pull.income_entries(doc)), 2)


def fill(trade, day, hour, side, position_side, qty, price):
    return {"id": trade, "time": pull.day_to_ms(day) + hour * 3_600_000, "side": side,
            "positionSide": position_side, "qty": str(qty), "price": str(price)}


def entries_doc(days, fills=()):
    """Daily records given as (day, [(signed size, entry price), ...]), with fills."""
    vos = [{"updateTime": mark(day),
            "data": {"assets": [{"asset": "USDT", "walletBalance": "1", "marginBalance": "1"}],
                     "position": [{"symbol": "BTCUSDT", "positionAmt": str(size),
                                   "entryPrice": str(entry), "markPrice": "1",
                                   "unRealizedProfit": "0"} for size, entry in held]}}
           for day, held in days]
    return {"daily_records_response": json.dumps({"snapshotVos": vos}),
            "trade_responses": [json.dumps(list(fills))]}


class EntryPricesFromFills(unittest.TestCase):
    """Each record's positions must follow from the previous record and the fills."""

    D1, D2, D3 = "2026-03-01", "2026-03-02", "2026-03-03"

    def test_adding_to_a_side_moves_its_entry_to_the_weighted_average(self):
        doc = entries_doc([(self.D1, [(-0.1, 50_000)]), (self.D2, [(-0.2, 51_000)])],
                          [fill(1, self.D2, 9, "SELL", "SHORT", 0.1, 52_000)])
        self.assertEqual(pull.check_entries(doc), ([self.D2], []))

    def test_reducing_a_side_leaves_its_entry_price(self):
        doc = entries_doc([(self.D1, [(-0.3, 51_000)]), (self.D2, [(-0.2, 51_000)])],
                          [fill(1, self.D2, 9, "BUY", "SHORT", 0.1, 49_000)])
        self.assertEqual(pull.check_entries(doc)[1], [])

    def test_a_side_that_closes_and_reopens_starts_again(self):
        doc = entries_doc([(self.D1, [(0.1, 50_000)]), (self.D2, [(0.2, 53_000)])],
                          [fill(1, self.D2, 1, "SELL", "LONG", 0.1, 51_000),
                           fill(2, self.D2, 2, "BUY", "LONG", 0.2, 53_000)])
        self.assertEqual(pull.check_entries(doc)[1], [])

    def test_both_sides_are_kept_apart(self):
        doc = entries_doc([(self.D1, [(0.1, 50_000)]), (self.D2, [(0.1, 50_000), (-0.1, 52_000)])],
                          [fill(1, self.D2, 3, "SELL", "SHORT", 0.1, 52_000)])
        self.assertEqual(pull.check_entries(doc)[1], [])

    def test_an_entry_price_from_before_a_late_fill_is_refused(self):
        # The fill at 20:00 moved the entry to 51,000; a record still showing
        # 50,000 was not struck at the valuation point.
        doc = entries_doc([(self.D1, [(0.1, 50_000)]), (self.D2, [(0.2, 50_000)])],
                          [fill(1, self.D2, 20, "BUY", "LONG", 0.1, 52_000)])
        self.assertEqual(pull.check_entries(doc)[1], [self.D2])

    def test_a_size_that_does_not_follow_from_the_fills_is_refused(self):
        doc = entries_doc([(self.D1, [(0.1, 50_000)]), (self.D2, [(0.3, 51_000)])],
                          [fill(1, self.D2, 9, "BUY", "LONG", 0.1, 52_000)])
        self.assertEqual(pull.check_entries(doc)[1], [self.D2])

    def test_a_position_closed_by_fills_must_be_gone_from_the_record(self):
        doc = entries_doc([(self.D1, [(0.1, 50_000)]), (self.D2, [(0.1, 50_000)])],
                          [fill(1, self.D2, 9, "SELL", "LONG", 0.1, 51_000)])
        self.assertEqual(pull.check_entries(doc)[1], [self.D2])

    def test_a_fill_at_the_valuation_point_belongs_to_that_day(self):
        at_mark = fill(1, self.D2, 0, "BUY", "LONG", 0.1, 52_000)
        at_mark["time"] = mark(self.D2)
        doc = entries_doc([(self.D1, [(0.1, 50_000)]), (self.D2, [(0.2, 51_000)]),
                           (self.D3, [(0.2, 51_000)])], [at_mark])
        self.assertEqual(pull.check_entries(doc), ([self.D2, self.D3], []))

    def test_a_fill_just_after_the_valuation_point_belongs_to_the_next_day(self):
        after = fill(1, self.D2, 0, "BUY", "LONG", 0.1, 52_000)
        after["time"] = mark(self.D2) + 1
        doc = entries_doc([(self.D1, [(0.1, 50_000)]), (self.D2, [(0.1, 50_000)]),
                           (self.D3, [(0.2, 51_000)])], [after])
        self.assertEqual(pull.check_entries(doc)[1], [])

    def test_a_day_without_fills_must_repeat_the_previous_positions(self):
        same = entries_doc([(self.D1, [(-0.1, 50_000)]), (self.D2, [(-0.1, 50_000)])])
        moved = entries_doc([(self.D1, [(-0.1, 50_000)]), (self.D2, [(-0.1, 50_100)])])
        self.assertEqual(pull.check_entries(same)[1], [])
        self.assertEqual(pull.check_entries(moved)[1], [self.D2])

    def test_a_fill_outside_hedge_mode_is_refused(self):
        doc = entries_doc([(self.D1, []), (self.D2, [(0.1, 50_000)])],
                          [fill(1, self.D2, 9, "BUY", "BOTH", 0.1, 50_000)])
        self.assertEqual(pull.check_entries(doc)[1], [self.D2])

    def test_the_first_record_has_nothing_to_follow(self):
        doc = entries_doc([(self.D1, [(0.1, 50_000)])])
        self.assertEqual(pull.check_entries(doc), ([], []))

    def test_a_copy_without_fills_is_refused(self):
        doc = entries_doc([(self.D1, []), (self.D2, [])])
        del doc["trade_responses"]
        with self.assertRaises(SystemExit):
            pull.check_entries(doc)


if __name__ == "__main__":
    unittest.main()
