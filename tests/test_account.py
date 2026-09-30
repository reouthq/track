"""Checks of the refusal to produce the record from any account but the registered one.

A key names no account of itself: swapping it would point the record at another
account, and every other check would pass on the wrong account's figures.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pull  # noqa: E402

SALT = "0123456789abcdef0123456789abcdef"
OURS = {"uid": "123456789", "alias": "aliasOurs00000"}
OTHER = {"uid": "987654321", "alias": "aliasOther0000"}
REGISTERED = {pull.account_commitment(SALT, OURS)}


def copy(ms, account=None):
    doc = {"fetched_at_ms": ms}
    if account:
        doc["account"] = account
    return doc


class TheRegisteredAccountOnly(unittest.TestCase):

    def test_copies_from_the_registered_account_pass(self):
        self.assertEqual(pull.check_account([copy(1, OURS), copy(2, OURS)], REGISTERED, SALT), 2)

    def test_copies_from_before_the_collector_asked_are_passed_over(self):
        self.assertEqual(pull.check_account([copy(1), copy(2, OURS)], REGISTERED, SALT), 1)

    def test_a_copy_from_another_account_stops_the_run(self):
        self.assertRaises(SystemExit, pull.check_account,
                          [copy(1, OURS), copy(2, OTHER), copy(3, OURS)], REGISTERED, SALT)

    def test_a_newest_copy_that_does_not_say_whose_key_stops_the_run(self):
        # Otherwise the check could be dropped by simply no longer asking.
        self.assertRaises(SystemExit, pull.check_account, [copy(1, OURS), copy(2)], REGISTERED, SALT)

    def test_a_missing_salt_stops_the_run(self):
        self.assertRaises(SystemExit, pull.check_account, [copy(1, OURS)], REGISTERED, "")

    def test_the_wrong_salt_stops_the_run(self):
        self.assertRaises(SystemExit, pull.check_account, [copy(1, OURS)], REGISTERED, "f" * 32)

    def test_a_register_without_a_commitment_stops_the_run(self):
        self.assertRaises(SystemExit, pull.check_account, [copy(1, OURS)], set(), SALT)

    def test_the_commitment_is_read_from_the_register_as_written(self):
        path = os.path.join(tempfile.mkdtemp(), "accounts.md")
        with open(path, "w") as f:
            f.write(f"| # | Account commitment |\n|---|---|\n| 1 | `{next(iter(REGISTERED))}` |\n")
        self.assertEqual(pull.registered_commitments(path), REGISTERED)

    def test_the_repository_register_carries_a_commitment(self):
        here = os.path.dirname(os.path.abspath(pull.__file__))
        self.assertEqual(len(pull.registered_commitments(os.path.join(here, "attest", "accounts.md"))), 1)

    def test_a_refusal_does_not_name_the_account(self):
        with self.assertRaises(SystemExit) as caught:
            pull.check_account([copy(1, OTHER)], REGISTERED, SALT)
        message = str(caught.exception)
        for value in (OTHER["uid"], OTHER["alias"], OURS["uid"], OURS["alias"]):
            self.assertNotIn(value, message)


if __name__ == "__main__":
    unittest.main()
