"""Checks of collecting the exchange's export of the transaction history, against a stand-in.

The stand-in answers as the exchange was measured to: a request gives a download id,
the export is "processing" for a while and then "completed" with a link, and the file is a zip
holding one CSV with six columns.

Run: python3 -m unittest discover -s tests
"""

import calendar
import contextlib
import io
import json
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch  # noqa: E402
import transactions  # noqa: E402

HEADER = '"Date(UTC)","type","Amount","Asset","Symbol","Transaction ID"\n'
ROW = '"2026-11-02 12:14:05","TRANSFER","6897.12345678","USDT","","987654321"\n'


def zipped(text, name="export.csv", extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(name, text)
        if extra:
            z.writestr(extra, "x")
    return buffer.getvalue()


def ms(*parts):
    return calendar.timegm(parts + (0,) * (6 - len(parts))) * 1000


class Exchange:

    def __init__(self, processing=2, refuse=False, never=False):
        self.processing, self.refuse, self.never = processing, refuse, never
        self.requests = []

    def __call__(self, url, params):
        self.requests.append((url, dict(params)))
        if url == transactions.REQUEST:
            if self.refuse:
                return 400, b'{"code": -1003, "msg": "Too many requests."}'
            return 200, b'{"avgCostTimestampOfLast30d": 7241, "downloadId": "545923594199212032"}'
        if self.never or self.processing > 0:
            self.processing -= 1
            return 200, json.dumps({"downloadId": "545923594199212032", "status": "processing", "url": ""}).encode()
        return 200, json.dumps({"downloadId": "545923594199212032", "status": "completed",
                                "url": "https://files.example/export.zip"}).encode()


class Period(unittest.TestCase):

    def test_a_month_that_has_ended_is_taken_whole(self):
        start, end = transactions.period("2026-10", ms(2026, 11, 15))
        self.assertEqual((start, end), (ms(2026, 10, 1), ms(2026, 11, 1) - 1))

    def test_a_month_not_yet_ended_is_taken_to_now(self):
        now = ms(2026, 10, 15, 16, 30)
        self.assertEqual(transactions.period("2026-10", now), (ms(2026, 10, 1), now))

    def test_nothing_before_the_first_deposit_is_asked_for(self):
        self.assertEqual(transactions.period("2026-09", ms(2026, 10, 2))[0], fetch.ACCOUNT_START_MS)

    def test_december_ends_with_the_year(self):
        self.assertEqual(transactions.period("2026-12", ms(2027, 1, 5))[1], ms(2027, 1, 1) - 1)

    def test_the_previous_month(self):
        self.assertEqual(transactions.previous_month(ms(2026, 10, 1, 1)), "2026-09")
        self.assertEqual(transactions.previous_month(ms(2027, 1, 1, 1)), "2026-12")

    def test_a_month_without_the_account_or_not_a_month_is_refused(self):
        for month in ("2026-08", "2026-13", "26-09"):
            with self.assertRaises(SystemExit, msg=month):
                transactions.period(month, ms(2026, 10, 2))


class Export(unittest.TestCase):

    def run_export(self, exchange, data):
        sleeps, fetched = [], []

        def fetch_file(url):
            fetched.append(url)
            return data

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = transactions.export(exchange, fetch_file, ms(2026, 9, 6), ms(2026, 10, 1) - 1, sleep=sleeps.append)
        return result, sleeps, fetched, out.getvalue()

    def test_the_export_is_collected_once_generated_and_kept_as_received(self):
        data = zipped(HEADER + ROW)
        result, sleeps, fetched, _ = self.run_export(Exchange(processing=2), data)
        self.assertEqual(result, data)
        self.assertEqual(len(sleeps), 3)                      # two checks still processing, the third completed
        self.assertEqual(fetched, ["https://files.example/export.zip"])

    def test_the_period_asked_for_is_the_one_given(self):
        exchange = Exchange(processing=0)
        self.run_export(exchange, zipped(HEADER + ROW))
        self.assertEqual(exchange.requests[0], (transactions.REQUEST,
                                                {"startTime": ms(2026, 9, 6), "endTime": ms(2026, 10, 1) - 1}))
        self.assertEqual(exchange.requests[1][1], {"downloadId": "545923594199212032"})

    def test_the_log_states_no_amount(self):
        _, _, _, log = self.run_export(Exchange(processing=1), zipped(HEADER + ROW))
        self.assertNotIn("6897", log)
        self.assertNotIn("987654321", log)

    def test_a_refused_request_stops_with_the_exchanges_code_only(self):
        with self.assertRaises(SystemExit) as stop:
            self.run_export(Exchange(refuse=True), zipped(HEADER + ROW))
        self.assertIn("code -1003", str(stop.exception))

    def test_an_export_never_generated_stops(self):
        with self.assertRaises(SystemExit) as stop:
            self.run_export(Exchange(never=True), zipped(HEADER + ROW))
        self.assertIn("not generated in time", str(stop.exception))

    def test_a_file_that_is_not_the_export_is_refused(self):
        for data in (b"<html>expired</html>",
                     zipped(HEADER + ROW, extra="second.csv"),
                     zipped(HEADER + ROW, name="export.txt"),
                     zipped('"Time","Type","Amount","Asset","Symbol","Transaction ID"\n' + ROW)):
            with self.assertRaises(SystemExit):
                self.run_export(Exchange(processing=0), data)


if __name__ == "__main__":
    unittest.main()
