"""Checks of the monthly statistics against cases whose answer is known.

Run: python3 -m unittest discover -s tests
"""

import datetime as dt
import math
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pull  # noqa: E402

VERSIONS = [("2026-01-01", "1.0")]


def mark(day):
    return pull.day_to_ms(day) + 86_399_000


def transfer(day, amount, hour=12):
    return {"ts": pull.day_to_ms(day) + hour * 3_600_000, "type": "TRANSFER", "amount": float(amount)}


def run(days, ledger=(), closes=None):
    """(equity, transfers, monthly rows) for [(day, nav), ...]."""
    records = [{"date": d, "ts": mark(d), "nav": float(n), "wallet": float(n), "mark": None}
               for d, n in days]
    equity, transfers, _, _ = pull.build(records, list(ledger), dict(closes or {}), VERSIONS,
                                         days[0][0], 3.0)
    return equity, transfers, pull.monthly_rows(equity, transfers)


def consecutive(start, navs):
    first = dt.date.fromisoformat(start)
    return [((first + dt.timedelta(days=i)).isoformat(), n) for i, n in enumerate(navs)]


def by_month(rows):
    return {r["month"]: r for r in rows}


class Returns(unittest.TestCase):

    def test_a_month_links_its_daily_returns(self):
        _, _, rows = run([("2026-09-28", 100), ("2026-09-29", 110), ("2026-09-30", 121),
                          ("2026-10-01", 133.1)])
        m = by_month(rows)
        self.assertEqual(sorted(m), ["2026-09", "2026-10"])
        self.assertAlmostEqual(m["2026-09"]["ret_twr"], 0.21)
        self.assertAlmostEqual(m["2026-10"]["ret_twr"], 0.10)
        self.assertEqual(m["2026-09"]["through_utc"], "2026-09-30")
        self.assertEqual(m["2026-10"]["through_utc"], "2026-10-01")

    def test_since_inception_follows_the_index(self):
        _, _, rows = run([("2026-09-28", 100), ("2026-09-29", 110), ("2026-09-30", 121),
                          ("2026-10-01", 133.1)])
        self.assertAlmostEqual(by_month(rows)["2026-10"]["ret_twr_itd"], 0.331)
        self.assertAlmostEqual(by_month(rows)["2026-10"]["ret_l1_itd"],
                               (1 + 0.1 / 3) ** 3 - 1)

    def test_a_month_holding_only_record_inception_has_no_return(self):
        _, _, rows = run([("2026-09-30", 100), ("2026-10-01", 110)],
                         closes={"2026-09-30": 50_000.0, "2026-10-01": 55_000.0})
        september = by_month(rows)["2026-09"]
        for column in ("ret_twr", "ret_l1", "ret_btc", "ret_twr_itd", "ret_l1_itd",
                       "ret_btc_itd", "mwr_itd", "trailing_30d", "trailing_65d"):
            self.assertIsNone(september[column], column)
        self.assertEqual(september["return_days_itd"], 0)
        self.assertAlmostEqual(by_month(rows)["2026-10"]["ret_twr"], 0.10)
        self.assertAlmostEqual(by_month(rows)["2026-10"]["ret_btc"], 0.10)

    def test_a_month_without_any_benchmark_close_has_no_benchmark_return(self):
        # A missing close is not a flat benchmark: the return is unknown, not zero.
        _, _, rows = run([("2026-09-30", 100), ("2026-10-01", 110), ("2026-10-02", 121)],
                         closes={"2026-09-30": 50_000.0})
        october = by_month(rows)["2026-10"]
        self.assertIsNone(october["ret_btc"])
        self.assertIsNone(october["ret_btc_itd"])
        self.assertAlmostEqual(october["ret_twr"], 0.21)

    def test_the_one_times_series_links_its_own_returns(self):
        _, _, rows = run([("2026-09-28", 100), ("2026-09-29", 130), ("2026-09-30", 169)])
        self.assertAlmostEqual(rows[0]["ret_l1"], 1.1 * 1.1 - 1)

    def test_the_benchmark_is_linked_for_the_month_and_since_inception(self):
        closes = {"2026-09-29": 100.0, "2026-09-30": 110.0, "2026-10-01": 121.0}
        _, _, rows = run([("2026-09-29", 100), ("2026-09-30", 100), ("2026-10-01", 100)],
                         closes=closes)
        m = by_month(rows)
        self.assertAlmostEqual(m["2026-09"]["ret_btc"], 0.10)
        self.assertAlmostEqual(m["2026-10"]["ret_btc"], 0.10)
        self.assertAlmostEqual(m["2026-10"]["ret_btc_itd"], 0.21)


class Risk(unittest.TestCase):

    def test_volatility_is_the_annualized_sample_deviation(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 101), ("2026-09-03", 99.99)])
        self.assertAlmostEqual(rows[0]["vol_ann"], math.sqrt(365) * math.sqrt(2e-4), places=10)

    def test_a_single_return_has_no_volatility(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 101)])
        self.assertIsNone(rows[0]["vol_ann"])

    def test_worst_and_best_day(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 105), ("2026-09-03", 94.5),
                          ("2026-09-04", 94.5)])
        self.assertAlmostEqual(rows[0]["worst_day"], -0.10)
        self.assertAlmostEqual(rows[0]["best_day"], 0.05)

    def test_returns_that_move_with_the_benchmark_correlate_fully(self):
        closes = {"2026-09-01": 100.0, "2026-09-02": 102.0, "2026-09-03": 99.96,
                  "2026-09-04": 101.9592}
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 104), ("2026-09-03", 99.84),
                          ("2026-09-04", 103.8336)], closes=closes)
        self.assertAlmostEqual(rows[0]["corr_btc"], 1.0)

    def test_fewer_than_three_days_have_no_correlation(self):
        closes = {"2026-09-01": 100.0, "2026-09-02": 102.0, "2026-09-03": 101.0}
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 104), ("2026-09-03", 102)],
                         closes=closes)
        self.assertIsNone(rows[0]["corr_btc"])

    def test_the_sharpe_ratio_waits_for_twelve_full_months(self):
        self.assertEqual(pull.full_months("2026-01-15", "2027-01-30"), 11)
        self.assertEqual(pull.full_months("2026-01-15", "2027-01-31"), 12)
        self.assertEqual(pull.full_months("2026-09-06", "2026-09-30"), 0)
        self.assertEqual(pull.full_months("2026-09-06", "2026-10-31"), 1)
        levels, level = [], 100.0
        for i in range(382):                                   # 2026-01-15 to 2027-01-31
            if i:
                level *= 1.002 if i % 2 else 0.9995
            levels.append(level)
        equity, _, rows = run(consecutive("2026-01-15", levels))
        m = by_month(rows)
        self.assertEqual(m["2027-01"]["through_utc"], "2027-01-31")
        self.assertIsNone(m["2026-12"]["sharpe_itd"])          # eleven full months
        returns = [r["ret_twr"] for r in equity if r["ret_twr"] is not None]
        self.assertAlmostEqual(m["2027-01"]["sharpe_itd"], pull.sharpe_ratio(returns))
        _, _, shorter = run(consecutive("2026-01-15", levels[:-1]))    # ends 2027-01-30
        self.assertEqual(by_month(shorter)["2027-01"]["through_utc"], "2027-01-30")
        self.assertIsNone(by_month(shorter)["2027-01"]["sharpe_itd"])


class Drawdown(unittest.TestCase):

    def test_maximum_and_current_drawdown_and_days_underwater(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 110), ("2026-09-03", 99),
                          ("2026-09-04", 105)])
        r = rows[0]
        self.assertAlmostEqual(r["max_drawdown"], 0.10)
        self.assertAlmostEqual(r["drawdown"], 1 - 105 / 110)
        self.assertEqual(r["days_underwater"], 2)
        self.assertAlmostEqual(r["max_drawdown_month"], 0.10)

    def test_the_derived_series_and_the_benchmark_have_their_own_drawdown(self):
        days = [("2026-09-01", 100), ("2026-09-02", 130), ("2026-09-03", 91), ("2026-09-04", 100)]
        closes = {"2026-08-31": 50_000, "2026-09-01": 60_000, "2026-09-02": 45_000,
                  "2026-09-03": 48_000, "2026-09-04": 54_000}
        _, _, rows = run(days, closes=closes)
        r = rows[0]
        self.assertAlmostEqual(r["max_drawdown"], 0.30)
        # A third of each daily return: +10%, then -10% from the high.
        self.assertAlmostEqual(r["max_drawdown_l1"], 0.10)
        self.assertAlmostEqual(r["max_drawdown_btc"], 0.25)

    def test_without_a_benchmark_close_there_is_no_benchmark_drawdown(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 90)])
        self.assertIsNone(rows[0]["max_drawdown_btc"])
        self.assertAlmostEqual(rows[0]["max_drawdown_l1"], 1 - (1 - 0.10 / 3))

    def test_a_withdrawal_is_neither_a_loss_nor_a_drawdown(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 110), ("2026-09-03", 55)],
                         [transfer("2026-09-03", -55)])
        self.assertAlmostEqual(rows[0]["drawdown"], 0.0)
        self.assertAlmostEqual(rows[0]["max_drawdown"], 0.0)
        self.assertEqual(rows[0]["days_underwater"], 0)

    def test_a_new_high_ends_the_days_underwater(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 90), ("2026-09-03", 101)])
        self.assertEqual(rows[0]["days_underwater"], 0)
        self.assertAlmostEqual(rows[0]["drawdown"], 0.0)
        self.assertAlmostEqual(rows[0]["max_drawdown"], 0.10)

    def test_the_month_drawdown_starts_from_the_previous_month_end(self):
        _, _, rows = run([("2026-09-29", 100), ("2026-09-30", 110), ("2026-10-01", 104.5),
                          ("2026-10-02", 110)])
        october = by_month(rows)["2026-10"]
        self.assertAlmostEqual(october["max_drawdown_month"], 0.05)
        self.assertAlmostEqual(october["drawdown"], 0.0)


class Trailing(unittest.TestCase):

    def test_the_window_counts_calendar_days_across_a_missed_day(self):
        level, days = 100.0, []
        start = dt.date(2026, 9, 1)
        for i in range(40):
            day = start + dt.timedelta(days=i)
            if i:
                level *= 1.01
            if day.day == 5 and day.month == 10:
                continue                           # the exchange did not record this day
            days.append((day.isoformat(), level))
        _, _, rows = run(days)
        october = by_month(rows)["2026-10"]
        self.assertAlmostEqual(october["trailing_30d"], 1.01 ** 30 - 1)

    def test_a_window_longer_than_the_record_runs_from_inception(self):
        _, _, rows = run(consecutive("2026-09-01", [100, 101, 102, 103]))
        self.assertAlmostEqual(rows[0]["trailing_30d"], rows[0]["ret_twr_itd"])
        self.assertAlmostEqual(rows[0]["trailing_65d"], rows[0]["ret_twr_itd"])


def xirr_from_amounts(navs_with_ms, flows_ms):
    """Money-weighted rate straight from amounts, independently of pull.py."""
    t0, n0 = navs_with_ms[0]
    tend, nend = navs_with_ms[-1]
    cash = [(t0, n0)] + flows_ms

    def gap(y):
        return nend - sum(f * (1 + y) ** ((tend - t) / 86_400_000 / 365) for t, f in cash)
    lo, hi = -0.999999999, 1e9
    for _ in range(300):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if gap(lo) * gap(mid) <= 0 else (mid, hi)
    return (lo + hi) / 2


class MoneyWeighted(unittest.TestCase):

    def test_without_transfers_it_equals_the_time_weighted_return(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 104), ("2026-09-03", 98)])
        self.assertEqual(rows[0]["mwr_basis"], "period")
        self.assertAlmostEqual(rows[0]["mwr_itd"], rows[0]["ret_twr_itd"], places=9)

    def test_a_deposit_before_a_loss_weighs_the_loss_more(self):
        _, _, rows = run([("2026-09-01", 100), ("2026-09-02", 105), ("2026-09-03", 255),
                          ("2026-09-04", 229.5)], [transfer("2026-09-03", 150)])
        self.assertLess(rows[0]["mwr_itd"], rows[0]["ret_twr_itd"])

    def test_it_is_worked_out_from_the_ratios_as_from_the_amounts(self):
        days = [("2026-09-01", 100), ("2026-09-02", 105), ("2026-09-03", 160), ("2026-09-04", 150)]
        deposit = transfer("2026-09-03", 50)
        _, _, rows = run(days, [deposit])
        y = xirr_from_amounts([(mark(d), n) for d, n in days], [(deposit["ts"], 50.0)])
        span = (mark("2026-09-04") - mark("2026-09-01")) / 86_400_000
        self.assertAlmostEqual(rows[0]["mwr_itd"], (1 + y) ** (span / 365) - 1, places=9)

    def test_after_a_year_it_is_an_annual_rate(self):
        _, _, rows = run([("2026-01-01", 100), ("2027-01-02", 110)])
        last = rows[-1]
        self.assertEqual(last["mwr_basis"], "annual")
        self.assertAlmostEqual(last["mwr_itd"], 1.1 ** (365 / 366) - 1, places=9)


class MonthlyRowsAreFinal(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = os.path.join(self.root, "monthly.csv")

    def publish(self, rows):
        with open(self.path, "w") as f:
            f.write(pull.as_csv(rows, pull.MONTHLY_COLUMNS) + "\n")

    def test_the_month_in_progress_may_move_forward(self):
        self.publish(run(consecutive("2026-09-01", [100, 101, 102]))[2])
        pull.check_monthly_unchanged(self.path, run(consecutive("2026-09-01", [100, 101, 102, 99]))[2])

    def test_the_month_in_progress_may_not_move_back(self):
        self.publish(run(consecutive("2026-09-01", [100, 101, 102]))[2])
        with self.assertRaises(SystemExit):
            pull.check_monthly_unchanged(self.path, run(consecutive("2026-09-01", [100, 101]))[2])

    def test_a_month_is_final_once_a_later_month_has_a_row(self):
        self.publish(run(consecutive("2026-09-29", [100, 101]))[2])
        changed = run([("2026-09-29", 100), ("2026-09-30", 102), ("2026-10-01", 103)])[2]
        with self.assertRaises(SystemExit):
            pull.check_monthly_unchanged(self.path, changed)

    def test_an_ended_month_that_comes_out_the_same_is_accepted(self):
        self.publish(run(consecutive("2026-09-29", [100, 101]))[2])
        pull.check_monthly_unchanged(self.path, run(consecutive("2026-09-29", [100, 101, 103]))[2])

    def test_a_final_row_that_would_change_is_refused(self):
        self.publish(run(consecutive("2026-09-29", [100, 101, 103, 104]))[2])
        changed = run([("2026-09-29", 100), ("2026-09-30", 100.5), ("2026-10-01", 103),
                       ("2026-10-02", 104)])[2]
        with self.assertRaises(SystemExit):
            pull.check_monthly_unchanged(self.path, changed)

    def test_a_dropped_month_is_refused(self):
        self.publish(run(consecutive("2026-09-29", [100, 101, 103]))[2])
        with self.assertRaises(SystemExit):
            pull.check_monthly_unchanged(self.path, run(consecutive("2026-09-29", [100, 101]))[2])

    def test_the_file_has_no_exponent_and_no_nan(self):
        rows = run(consecutive("2026-09-01", [100, 100.0000001, 100, 101]))[2]
        text = pull.as_csv(rows, pull.MONTHLY_COLUMNS)
        self.assertNotIn("e-", text)
        self.assertNotIn("nan", text.lower())
        self.assertEqual(text.splitlines()[0].split(","), pull.MONTHLY_COLUMNS)


if __name__ == "__main__":
    unittest.main()
