"""Checks of the monthly report against a record published by pull.py itself.

Run: python3 -m unittest discover -s tests
"""

import csv
import datetime as dt
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import monthly_report  # noqa: E402
import pull  # noqa: E402

VERSIONS = [("2026-01-01", "1.3")]
DOCUMENTS = ["RISK_LIMITS.md", "CHANGELOG.md", "attest/versions.md", "attest/accounts.md",
             "attest/incidents.md", "attest/interventions.md", "attest/reviews.md",
             "attest/reconciliation.md"]
MINUS = "−"


def dates(first, last):
    day, end, out = dt.date.fromisoformat(first), dt.date.fromisoformat(last), []
    while day <= end:
        out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def navs(first, last, values=(100,)):
    """[(day, nav)] from first to last: the values given, then the last of them held."""
    days = dates(first, last)
    return [(d, float(values[min(i, len(values) - 1)])) for i, d in enumerate(days)]


def response(day, close):
    open_ms = pull.day_to_ms(day)
    return json.dumps([[open_ms, "0", "0", "0", str(close), "0", open_ms + 86_399_999]]).encode()


def entry(day, kind, amount, hour=12):
    return {"ts": pull.day_to_ms(day) + hour * 3_600_000, "type": kind, "amount": float(amount)}


class Report(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        os.makedirs(os.path.join(self.root, "attest"))
        for rel in DOCUMENTS:
            shutil.copy(os.path.join(HERE, rel), os.path.join(self.root, rel))

    def publish(self, days, ledger=()):
        """Publish [(day, nav), ...] into the checkout as the daily workflow does, and anchor it."""
        records = [{"date": d, "ts": pull.day_to_ms(d) + 86_399_000, "nav": n, "wallet": n, "mark": None}
                   for d, n in days]
        closes = {d: 50_000.0 + 100 * (i % 7) for i, (d, _) in enumerate(days)}
        equity, transfers, income, _ = pull.build(records, list(ledger), closes, VERSIONS, days[0][0], 3.0)
        manifest = pull.publish(self.root, equity, transfers, income, pull.monthly_rows(equity, transfers),
                                {d: response(d, closes[d]) for d, _ in days}, {"account/copy.json": b"{}"})
        open(manifest + ".ots", "wb").close()
        return pull.monthly_rows(equity, transfers)

    def reanchor(self):
        """A manifest of the data files as they now are, as the next day's run would write."""
        latest = sorted(glob.glob(os.path.join(self.root, "attest", "????-??-??.sha256")))[-1]
        day = (dt.date.fromisoformat(os.path.basename(latest)[:10]) + dt.timedelta(days=1)).isoformat()
        path = os.path.join(self.root, "attest", f"{day}.sha256")
        with open(path, "w") as f:
            for rel in monthly_report.DATA:
                with open(os.path.join(self.root, rel), "rb") as g:
                    f.write(f"{hashlib.sha256(g.read()).hexdigest()}  {rel}\n")
        open(path + ".ots", "wb").close()

    def render(self, month):
        return monthly_report.render(self.root, month)

    def append(self, rel, row):
        with open(os.path.join(self.root, rel), "a") as f:
            f.write(row + "\n")

    def line(self, text, start):
        return next(l for l in text.splitlines() if l.startswith(start))

    # --- figures ----------------------------------------------------------

    def test_the_months_figures_are_those_published(self):
        row = self.publish(navs("2026-03-01", "2026-03-31", [100 + (i % 5) for i in range(31)]))[0]
        text = self.render("2026-03")
        self.assertIn(monthly_report.pct(row["ret_twr"]), self.line(text, "| Time-weighted return, as traded"))
        self.assertIn(monthly_report.pct(row["ret_btc"]), self.line(text, "| Benchmark return"))
        self.assertIn(monthly_report.pct(-row["max_drawdown_l1"]),
                      self.line(text, "| Maximum drawdown, derived 1×"))
        self.assertIn(monthly_report.pct(-row["max_drawdown_btc"]),
                      self.line(text, "| Benchmark maximum drawdown"))
        volatility = self.line(text, "| Annualized volatility")
        self.assertIn(f"{row['vol_ann'] * 100:.2f}%", volatility)
        self.assertNotIn("+", volatility)                     # a volatility has no sign

    def test_the_same_files_give_the_same_report(self):
        self.publish(navs("2026-03-01", "2026-03-31", [100, 101, 99, 102, 98, 97, 103]))
        self.assertEqual(self.render("2026-03"), self.render("2026-03"))

    def test_the_account_drawdown_is_placed_against_its_thresholds(self):
        # From 100 down to 66 and held: a drawdown of 34%, past review (-30%), short of risk reduction (-37%).
        self.publish(navs("2026-03-01", "2026-03-31", [100, 90, 80, 70, 66]))
        line = self.line(self.render("2026-03"), "| Account drawdown")
        self.assertIn(f"{MINUS}34.0%", line)
        self.assertTrue(line.endswith("| review |"), line)

    def test_a_month_that_reached_no_level_says_none(self):
        self.publish(navs("2026-03-01", "2026-03-31", [100, 101, 102]))
        self.assertTrue(self.line(self.render("2026-03"), "| Account drawdown").endswith("| none |"))

    def test_a_negative_correlation_is_written_with_a_minus_sign(self):
        self.publish(navs("2026-03-01", "2026-03-31", [100 - (i % 7) for i in range(31)]))
        line = self.line(self.render("2026-03"), "| Correlation of daily returns")
        self.assertNotIn("-", line.replace("|---", ""))

    def test_transfers_and_the_sum_of_daily_costs_are_stated(self):
        days = navs("2026-03-01", "2026-03-31", [100, 150])
        self.publish(days, [entry("2026-03-02", "TRANSFER", 50, hour=6),
                            entry("2026-03-02", "COMMISSION", -1), entry("2026-03-03", "FUNDING_FEE", -0.3)])
        text = self.render("2026-03")
        self.assertIn("| 2026-03-02T06:00:00Z | deposit | +50.0000% |", text)
        self.assertIn(f"{MINUS}1.2000% of net asset value, the sum of the month's daily shares", text)

    def test_other_income_types_are_named(self):
        self.publish(navs("2026-03-01", "2026-03-31"),
                     [entry("2026-03-02", "INSURANCE_CLEAR", -1), entry("2026-03-02", "AUTO_EXCHANGE", 1)])
        self.assertIn("| 2026-03-02 | AUTO_EXCHANGE, INSURANCE_CLEAR |", self.render("2026-03"))

    def test_a_credit_is_listed_among_the_flows_as_a_credit(self):
        self.publish(navs("2026-03-01", "2026-03-31"), [entry("2026-03-02", "API_REBATE", 1)])
        self.assertIn("| credit |", self.render("2026-03"))

    def test_no_currency_amount_reaches_the_report(self):
        self.publish(navs("2026-03-01", "2026-03-31", [123_456.78, 135_802.46, 130_000.12]))
        text = self.render("2026-03")
        for amount in ("123456", "135802", "130000"):
            self.assertNotIn(amount, text)

    # --- the month's extent -----------------------------------------------

    def test_the_first_report_covers_the_month_from_record_inception(self):
        self.publish(navs("2026-03-05", "2026-03-31", [100, 101]))
        text = self.render("2026-03")
        self.assertIn("It covers the part of the month from record inception, 2026-03-05.", text)
        self.assertIn("- Valuation points in this report: 2026-03-05 to 2026-03-31", text)

    def test_the_head_names_where_the_report_is_checked(self):
        self.publish(navs("2026-03-05", "2026-03-31", [100, 101]))
        text = self.render("2026-03")
        self.assertIn("- The record: `github.com/reouthq/track`", text)
        self.assertIn("- How to check it: `reout.io/verify`", text)

    def test_a_day_without_a_valuation_point_is_listed_as_an_incident(self):
        self.publish([d for d in navs("2026-03-01", "2026-03-31") if d[0] != "2026-03-03"])
        self.assertIn("without a published valuation point at the time of this report: 2026-03-03.",
                      self.render("2026-03"))

    def test_a_month_not_yet_published_to_its_end_is_refused(self):
        self.publish(navs("2026-03-01", "2026-03-20"))
        with self.assertRaises(SystemExit):
            self.render("2026-03")

    def test_a_month_without_data_is_refused(self):
        self.publish(navs("2026-03-01", "2026-03-31"))
        with self.assertRaises(SystemExit):
            self.render("2026-04")

    # --- registers --------------------------------------------------------

    def test_incidents_of_the_month_are_quoted_and_others_are_not(self):
        self.publish(navs("2026-03-01", "2026-04-02"))
        self.append("attest/incidents.md", "| 2026-03-31 02:00 | 2026-03-31 03:00 | outage | March outage | none | restarted |")
        self.append("attest/incidents.md", "| 2026-04-02 02:00 | 2026-04-02 03:00 | outage | April outage | none | restarted |")
        text = self.render("2026-03")
        self.assertIn("March outage", text)
        self.assertNotIn("April outage", text)

    def test_an_open_reconciliation_is_stated_and_the_next_report_gives_it(self):
        self.publish(navs("2026-03-01", "2026-04-30"))
        march = self.render("2026-03")
        self.assertIn(f"The reconciliation of 2026-03 {monthly_report.NOT_COMPLETE}.", march)
        os.makedirs(os.path.join(self.root, "reports"))
        with open(os.path.join(self.root, "reports", "2026-03.md"), "w") as f:
            f.write(march)
        self.append("attest/reconciliation.md", "| 2026-03 | agrees | agrees | agrees | The three sources agree. |")
        april = self.render("2026-04")
        self.assertIn("The reconciliation of 2026-03, which was not complete when that report was published:", april)
        self.assertIn("The three sources agree.", april)

    def test_a_version_taking_effect_in_the_month_is_a_change(self):
        self.publish(navs("2026-03-01", "2026-03-31"))
        self.append("attest/versions.md", "| 2 | 1.4 | 2026-03-02 | renewal | abc | `attest/x.ots` |")
        self.assertIn("- Version 1.4 (renewal) took effect on 2026-03-02.", self.render("2026-03"))

    # --- corrections and anchoring ---------------------------------------

    def published_cell(self, rel, key, column):
        with open(os.path.join(self.root, rel)) as f:
            return next(r[column] for r in csv.DictReader(f) if r[monthly_report.KEYS[rel]] == key)

    def test_a_correction_is_applied_and_listed(self):
        self.publish(navs("2026-03-01", "2026-03-31", [100, 110, 121]))
        published = self.published_cell("data/equity_daily.csv", "2026-03-02", "nav_idx")
        self.append("data/corrections.csv", f"2026-03-02,data/equity_daily.csv,nav_idx,{published},111.0,example")
        self.reanchor()                          # a correction is anchored like any other file of the day
        text = self.render("2026-03")
        self.assertIn(f"| nav_idx | {published} | 111.0 | example |",
                      self.line(text, "| 2026-03-02 | data/equity_daily.csv"))
        self.assertIn("| 111.00 |", self.line(text, "| 2026-03-02 | +10.00%"))

    def test_a_correction_that_does_not_match_the_published_value_is_refused(self):
        self.publish(navs("2026-03-01", "2026-03-31", [100, 110, 121]))
        self.append("data/corrections.csv", "2026-03-02,data/equity_daily.csv,nav_idx,999.0,111.0,example")
        self.reanchor()
        with self.assertRaises(SystemExit):
            self.render("2026-03")

    def test_data_that_no_anchored_manifest_lists_is_refused(self):
        self.publish(navs("2026-03-01", "2026-03-31"))
        self.append("data/transfers.csv", "2026-03-02T06:00:00Z,0.10000000")
        with self.assertRaises(SystemExit):
            self.render("2026-03")

    # --- the files written ------------------------------------------------

    def run_main(self, stamp="ok"):
        ots = os.path.join(self.root, "ots-stand-in")
        with open(ots, "w") as f:
            f.write('#!/bin/sh\nif [ "$1" = stamp ]; then\n  [ "$STAND_IN_STAMP" = fail ] && exit 1\n'
                    '  printf pending > "$2.ots"\nfi\nexit 0\n')
        os.chmod(ots, 0o755)
        run = [sys.executable, os.path.join(HERE, "tools", "monthly_report.py"), "--month", "2026-03",
               "--root", self.root, "--ots", ots]
        return subprocess.run(run, capture_output=True, text=True, env=dict(os.environ, STAND_IN_STAMP=stamp))

    def reports(self):
        folder = os.path.join(self.root, "reports")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_the_report_its_pdf_and_their_anchored_manifest_are_written(self):
        self.publish(navs("2026-03-01", "2026-03-31", [100, 101, 99]))
        self.assertEqual(self.run_main().returncode, 0)
        self.assertEqual(self.reports(), ["2026-03.md", "2026-03.pdf", "2026-03.sha256", "2026-03.sha256.ots"])
        folder = os.path.join(self.root, "reports")

        def read(name):
            with open(os.path.join(folder, name), "rb") as f:
                return f.read()

        md, pdf = read("2026-03.md"), read("2026-03.pdf")
        self.assertEqual(read("2026-03.sha256").decode(),
                         f"{hashlib.sha256(md).hexdigest()}  reports/2026-03.md\n"
                         f"{hashlib.sha256(pdf).hexdigest()}  reports/2026-03.pdf\n")
        self.assertIn(hashlib.sha256(md).hexdigest().encode(), pdf)          # the PDF states the Markdown's hash
        self.assertEqual(md.decode(), self.render("2026-03"))

    def test_nothing_is_written_when_the_manifest_cannot_be_anchored(self):
        self.publish(navs("2026-03-01", "2026-03-31"))
        result = self.run_main(stamp="fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reports(), [])

    def test_a_published_report_is_never_rewritten(self):
        self.publish(navs("2026-03-01", "2026-03-31"))
        self.assertEqual(self.run_main().returncode, 0)
        with open(os.path.join(self.root, "reports", "2026-03.md"), "rb") as f:
            before = f.read()
        self.assertNotEqual(self.run_main().returncode, 0)
        with open(os.path.join(self.root, "reports", "2026-03.md"), "rb") as f:
            self.assertEqual(f.read(), before)


if __name__ == "__main__":
    unittest.main()
