"""Checks of the publication of the record into a checkout of it.

Run: python3 -m unittest discover -s tests
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pull  # noqa: E402

VERSIONS = [("2026-01-01", "1.0")]
D1, D2, D3 = "2026-03-01", "2026-03-02", "2026-03-03"
PRIVATE = {"account/2026-03-03T083000Z.json": b'{"fetched_at_ms": 1772526600000}'}


def mark(day):
    return pull.day_to_ms(day) + 86_399_000


def response(day, close):
    open_ms = pull.day_to_ms(day)
    return json.dumps([[open_ms, "0", "0", "0", str(close), "0", open_ms + 86_399_999]]).encode()


def commission(day, amount):
    return {"ts": pull.day_to_ms(day) + 12 * 3_600_000, "type": "COMMISSION", "amount": float(amount)}


def series(days, ledger=()):
    """(equity, transfers, income, monthly, benchmark responses) for [(day, nav), ...] and a ledger."""
    records = [{"date": d, "ts": mark(d), "nav": float(n), "wallet": float(n), "mark": None}
               for d, n in days]
    closes = {d: 50_000.0 + i for i, (d, _) in enumerate(days)}
    equity, transfers, income, _ = pull.build(records, list(ledger), closes, VERSIONS,
                                              days[0][0], 3.0)
    return (equity, transfers, income, pull.monthly_rows(equity, transfers),
            {d: response(d, closes[d]) for d, _ in days})


class Publication(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def publish(self, days, ledger=(), private=PRIVATE):
        return pull.publish(self.root, *series(days, ledger), private)

    def read(self, rel):
        with open(os.path.join(self.root, rel), "rb") as f:
            return f.read()

    def tree(self):
        out = {}
        for folder, _, files in os.walk(self.root):
            for name in files:
                rel = os.path.relpath(os.path.join(folder, name), self.root)
                out[rel] = self.read(rel)
        return out

    def manifest_lines(self, path):
        with open(path) as f:
            return [line.split("  ", 1) for line in f.read().splitlines()]

    # --- what is written -------------------------------------------------

    def test_the_first_publication_writes_every_file_and_a_manifest(self):
        manifest = self.publish([(D1, 100), (D2, 110)])
        self.assertEqual(os.path.relpath(manifest, self.root), f"attest/{D2}.sha256")
        for rel in ("data/equity_daily.csv", "data/income_daily.csv", "data/transfers.csv",
                    "data/monthly.csv", "data/corrections.csv", f"raw/{D1}/btc.json",
                    f"raw/{D2}/btc.json"):
            self.assertIn(rel, self.tree())

    def test_the_benchmark_response_is_published_as_received(self):
        self.publish([(D1, 100), (D2, 110)])
        self.assertEqual(self.read(f"raw/{D2}/btc.json"), series([(D1, 100), (D2, 110)])[4][D2])

    def test_every_published_file_matches_its_line_in_the_manifest(self):
        manifest = self.publish([(D1, 100), (D2, 110)])
        hashed_only = ("account/",)
        published = [rel for _, rel in self.manifest_lines(manifest)
                     if not rel.startswith(hashed_only)]
        self.assertEqual(len(published), 7)
        for digest, rel in self.manifest_lines(manifest):
            if rel.startswith(hashed_only):
                self.assertNotIn(rel, self.tree())          # hash only, never published
            else:
                self.assertEqual(hashlib.sha256(self.read(rel)).hexdigest(), digest, rel)

    def test_the_manifest_lists_the_retained_copies_and_nothing_else_unpublished(self):
        manifest = self.publish([(D1, 100), (D2, 110)])
        lines = dict((rel, digest) for digest, rel in self.manifest_lines(manifest))
        (name, data), = PRIVATE.items()
        self.assertEqual(lines[name], hashlib.sha256(data).hexdigest())
        self.assertEqual([rel for rel in lines if rel.startswith("account/")], [name])

    def test_the_retained_copies_are_listed_by_the_names_they_are_kept_by(self):
        self.assertEqual(pull.retained_copies({"private/account/2026-03-03T083000Z.json.enc": b"one",
                                               "private/archive/2026-03-01T000000Z.json.enc": b"two"}),
                         {"account/2026-03-03T083000Z.json": b"one",
                          "archive/2026-03-01T000000Z.json": b"two"})

    def test_the_manifest_is_in_the_format_sha256sum_reads(self):
        manifest = self.publish([(D1, 100), (D2, 110)])
        text = open(manifest).read()
        self.assertTrue(text.endswith("\n"))
        for line in text.splitlines():
            self.assertRegex(line, r"^[0-9a-f]{64}  [A-Za-z0-9_./-]+$")

    def test_corrections_already_written_are_kept(self):
        kept = b"date,file,column,published_value,corrected_value,reason\n" \
               b"2026-03-01,data/equity_daily.csv,ret_twr,0.1,0.2,example\n"
        os.makedirs(os.path.join(self.root, "data"))
        with open(os.path.join(self.root, "data", "corrections.csv"), "wb") as f:
            f.write(kept)
        self.publish([(D1, 100), (D2, 110)])
        self.assertEqual(self.read("data/corrections.csv"), kept)

    def test_no_currency_amount_reaches_any_file_written(self):
        self.publish([(D1, 123_456.78), (D2, 135_802.458)])
        for rel, data in self.tree().items():
            self.assertNotIn(b"123456", data, rel)
            self.assertNotIn(b"135802", data, rel)

    # --- the next day ----------------------------------------------------

    def test_running_again_with_no_new_day_changes_nothing(self):
        self.publish([(D1, 100), (D2, 110)])
        before = self.tree()
        self.assertIsNone(self.publish([(D1, 100), (D2, 110)]))
        self.assertEqual(self.tree(), before)

    def test_a_new_day_gets_its_own_manifest_and_leaves_the_earlier_files(self):
        first = self.publish([(D1, 100), (D2, 110)])
        before = self.tree()
        second = self.publish([(D1, 100), (D2, 110), (D3, 121)])
        self.assertEqual(os.path.relpath(second, self.root), f"attest/{D3}.sha256")
        after = self.tree()
        for rel in (os.path.relpath(first, self.root), f"raw/{D1}/btc.json", f"raw/{D2}/btc.json"):
            self.assertEqual(after[rel], before[rel], rel)
        listed = [rel for _, rel in self.manifest_lines(second)]
        self.assertIn(f"raw/{D3}/btc.json", listed)
        self.assertNotIn(f"raw/{D2}/btc.json", listed)       # it belongs to an earlier day

    def test_the_month_in_progress_is_replaced_by_the_next_day(self):
        self.publish([(D1, 100), (D2, 110)])
        second = self.publish([(D1, 100), (D2, 110), (D3, 121)])
        rows = self.read("data/monthly.csv").decode().splitlines()
        self.assertEqual(len(rows), 2)                      # one month, replaced in place
        self.assertTrue(rows[1].startswith("2026-03,2026-03-03,"))
        self.assertIn("data/monthly.csv", [rel for _, rel in self.manifest_lines(second)])

    # --- what writes nothing ---------------------------------------------

    def assertWritesNothing(self, run):
        before = self.tree()
        with self.assertRaises(SystemExit):
            run()
        self.assertEqual(self.tree(), before)

    def test_a_change_to_a_published_row_writes_nothing(self):
        self.publish([(D1, 100), (D2, 110)])
        self.assertWritesNothing(lambda: self.publish([(D1, 100), (D2, 111), (D3, 121)]))

    def test_a_change_to_a_published_income_row_alone_writes_nothing(self):
        # The returns are the same; only the ledger behind the day's costs differs.
        self.publish([(D1, 100), (D2, 110)], [commission(D2, -1)])
        equity_before = self.read("data/equity_daily.csv")
        self.assertWritesNothing(
            lambda: self.publish([(D1, 100), (D2, 110), (D3, 121)], [commission(D2, -2)]))
        self.assertTrue(pull.as_csv(series([(D1, 100), (D2, 110)], [commission(D2, -2)])[0],
                                    pull.EQUITY_COLUMNS).encode() in equity_before)

    def test_a_benchmark_response_unlike_the_published_one_writes_nothing(self):
        self.publish([(D1, 100), (D2, 110)])
        equity, transfers, income, monthly, benchmark = series([(D1, 100), (D2, 110), (D3, 121)])
        benchmark[D1] = response(D1, 1)
        self.assertWritesNothing(
            lambda: pull.publish(self.root, equity, transfers, income, monthly, benchmark,
                                PRIVATE))

    def test_a_new_day_without_its_benchmark_response_writes_nothing(self):
        self.publish([(D1, 100), (D2, 110)])
        equity, transfers, income, monthly, benchmark = series([(D1, 100), (D2, 110), (D3, 121)])
        del benchmark[D3]
        self.assertWritesNothing(
            lambda: pull.publish(self.root, equity, transfers, income, monthly, benchmark,
                                PRIVATE))

    def test_a_published_day_whose_benchmark_file_is_gone_writes_nothing(self):
        self.publish([(D1, 100), (D2, 110)])
        os.remove(os.path.join(self.root, "raw", D1, "btc.json"))
        self.assertWritesNothing(lambda: self.publish([(D1, 100), (D2, 110), (D3, 121)]))

    def test_an_existing_manifest_is_never_overwritten(self):
        os.makedirs(os.path.join(self.root, "attest"))
        with open(os.path.join(self.root, "attest", f"{D2}.sha256"), "w") as f:
            f.write("already here\n")
        self.assertWritesNothing(lambda: self.publish([(D1, 100), (D2, 110)]))


if __name__ == "__main__":
    unittest.main()
