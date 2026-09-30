"""Checks of the notice sent when the Account reaches a level of the Risk Limits.

Run: python3 -m unittest discover -s tests
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))

import limit_alert  # noqa: E402

COLUMNS = "month,through_utc,drawdown,days_underwater,trailing_30d,trailing_65d"


def run(root, topic=""):
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["limit_alert.py", "--root", root]), \
            mock.patch.dict(os.environ, {"NTFY_TOPIC": topic}), contextlib.redirect_stdout(out):
        limit_alert.main()
    return out.getvalue()


class LimitAlert(unittest.TestCase):
    def setUp(self):
        # As in the rehearsal: the record's folder holds data only, and the Risk Limits
        # are this repository's own.
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data"))

    def tearDown(self):
        shutil.rmtree(self.root)

    def month(self, row):
        with open(os.path.join(self.root, "data", "monthly.csv"), "w") as f:
            f.write(COLUMNS + "\n" + row + "\n")

    def test_nothing_to_assess_before_the_first_month(self):
        self.assertIn("nothing to assess", run(self.root))

    def test_within_every_range_it_names_no_level(self):
        self.month("2026-10,2026-10-31,0.10000000,12,0.00600000,0.31500000")
        out = run(self.root)
        self.assertEqual(out.count(": none"), 4)
        self.assertNotIn("reached", out)

    def test_a_level_reached_is_named_and_values_are_not_printed(self):
        # A drawdown of 44% is past review (−30%) and risk reduction (−37%), short of program review (−46%).
        self.month("2026-10,2026-10-31,0.44000000,190,0.00600000,0.31500000")
        out = run(self.root)
        self.assertIn("Account drawdown: risk reduction", out)
        self.assertIn("Days underwater: review", out)
        self.assertIn("no notification channel is set", out)
        self.assertNotIn("44", out)

    def test_a_notice_is_sent_when_a_channel_is_set(self):
        self.month("2026-10,2026-10-31,0.44000000,12,0.00600000,0.31500000")
        sent = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def urlopen(req, timeout):
            sent["url"], sent["body"] = req.full_url, req.data.decode()
            return Response()

        with mock.patch.object(limit_alert.urllib.request, "urlopen", urlopen):
            out = run(self.root, topic="a-topic")
        self.assertIn("notice sent: HTTP 200", out)
        self.assertEqual(sent["url"], "https://ntfy.sh/a-topic")
        self.assertIn("within 24 hours", sent["body"])


if __name__ == "__main__":
    unittest.main()
