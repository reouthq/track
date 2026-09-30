"""Checks of anchoring and of completing proofs, against a stand-in for the client.

The real client talks to public calendars and to Bitcoin, which a test must not
depend on. The stand-in below behaves as the client was measured to behave
(opentimestamps-client 0.7.2): a proof is complete when it carries a
BitcoinBlockHeaderAttestation; an upgrade that changes a proof leaves the old
one as FILE.bak and refuses to run while such a backup exists; a pending
upgrade and a failed stamp exit with 1.

Run: python3 -m unittest discover -s tests
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pull  # noqa: E402

PENDING = "verify PendingAttestation('https://calendar.example')\n"
COMPLETE = "verify BitcoinBlockHeaderAttestation(900000)\n"

STAND_IN = r'''#!/usr/bin/env python3
import os, shutil, sys
command, path = sys.argv[1], sys.argv[-1]
with open(os.environ["STAND_IN_LOG"], "a") as log:
    log.write(f"{command} {os.path.basename(path)}\n")
if command == "stamp":
    if os.environ.get("STAND_IN_STAMP") == "fail":
        print("Failed to create timestamp: need at least 2 attestations but received 0 within timeout",
              file=sys.stderr)
        sys.exit(1)
    open(path + ".ots", "w").write(PENDING)
elif command == "info":
    text = open(path).read()
    if "Attestation" not in text:
        print("Error! not a timestamp file", file=sys.stderr)
        sys.exit(1)
    print(text, end="")
elif command == "upgrade":
    if os.path.exists(path + ".bak"):
        print("Could not backup timestamp: already exists", file=sys.stderr)
        sys.exit(1)
    if COMPLETE in open(path).read():
        print("Success! Timestamp complete")
        sys.exit(0)
    mode = os.environ.get("STAND_IN_UPGRADE", "pending")
    if mode == "confirms":
        shutil.copy(path, path + ".bak")
        open(path, "w").write(COMPLETE)
        print("Success! Timestamp complete")
        sys.exit(0)
    if mode == "unreachable":
        print("Could not connect to calendar", file=sys.stderr)
        sys.exit(1)
    print("Failed! Timestamp not complete", file=sys.stderr)
    sys.exit(1)
'''


class Anchoring(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.ots = os.path.join(self.root, "ots")
        with open(self.ots, "w") as f:
            f.write(STAND_IN.replace("PENDING", repr(PENDING)).replace("COMPLETE", repr(COMPLETE)))
        os.chmod(self.ots, os.stat(self.ots).st_mode | stat.S_IEXEC)
        self.log = os.path.join(self.root, "calls.log")
        open(self.log, "w").close()
        self.set_env(STAND_IN_LOG=self.log, STAND_IN_STAMP="ok", STAND_IN_UPGRADE="pending")
        self.record = os.path.join(self.root, "record")
        os.makedirs(os.path.join(self.record, "attest"))

    def set_env(self, **values):
        for key, value in values.items():
            before = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, b=before: os.environ.__setitem__(k, b)
                            if b is not None else os.environ.pop(k, None))

    def proof(self, name, text):
        path = os.path.join(self.record, "attest", name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def calls(self):
        with open(self.log) as f:
            return f.read().splitlines()

    def upgrade(self, now=None):
        return pull.upgrade_proofs(self.record, self.ots, now or int(time.time() * 1000))

    def commit(self, rel, hours_ago):
        env = dict(os.environ)
        when = f"@{int(time.time() - hours_ago * 3600)} +0000"
        env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        git = ["git", "-C", self.record, "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(git + ["init", "-q"], check=True, env=env)
        subprocess.run(git + ["add", rel], check=True, env=env)
        subprocess.run(git + ["commit", "-q", "-m", "proof"], check=True, env=env)

    # --- stamping --------------------------------------------------------

    def test_a_new_manifest_is_anchored_beside_it(self):
        manifest = self.proof("2026-03-02.sha256", "hashes\n")
        proof = pull.stamp(manifest, self.ots)
        self.assertEqual(proof, manifest + ".ots")
        self.assertTrue(os.path.exists(proof))

    def test_a_manifest_the_calendars_do_not_anchor_stops_the_run(self):
        self.set_env(STAND_IN_STAMP="fail")
        manifest = self.proof("2026-03-02.sha256", "hashes\n")
        with self.assertRaises(SystemExit) as stop:
            pull.stamp(manifest, self.ots)
        self.assertIn("not committed", str(stop.exception))
        self.assertFalse(os.path.exists(manifest + ".ots"))

    # --- completing ------------------------------------------------------

    def test_a_complete_proof_is_left_alone(self):
        self.proof("2026-03-01.sha256.ots", COMPLETE)
        complete, completed, pending, overdue = self.upgrade()
        self.assertEqual(complete, ["attest/2026-03-01.sha256.ots"])
        self.assertNotIn("upgrade 2026-03-01.sha256.ots", self.calls())

    def test_a_confirmed_proof_is_completed_and_leaves_no_backup(self):
        self.set_env(STAND_IN_UPGRADE="confirms")
        path = self.proof("2026-03-02.sha256.ots", PENDING)
        complete, completed, pending, overdue = self.upgrade()
        self.assertEqual(completed, ["attest/2026-03-02.sha256.ots"])
        self.assertIn(COMPLETE, open(path).read())
        self.assertFalse(os.path.exists(path + ".bak"))

    def test_a_backup_left_behind_does_not_block_the_upgrade(self):
        self.set_env(STAND_IN_UPGRADE="confirms")
        path = self.proof("2026-03-02.sha256.ots", PENDING)
        with open(path + ".bak", "w") as f:
            f.write(PENDING)
        _, completed, _, _ = self.upgrade()
        self.assertEqual(completed, ["attest/2026-03-02.sha256.ots"])
        self.assertFalse(os.path.exists(path + ".bak"))

    def test_a_proof_not_yet_confirmed_stays_pending(self):
        path = self.proof("2026-03-02.sha256.ots", PENDING)
        complete, completed, pending, overdue = self.upgrade()
        self.assertEqual((complete, completed, pending, overdue),
                         ([], [], ["attest/2026-03-02.sha256.ots"], []))
        self.assertEqual(open(path).read(), PENDING)

    def test_an_unreachable_calendar_leaves_the_proof_pending_without_stopping(self):
        self.set_env(STAND_IN_UPGRADE="unreachable")
        self.proof("2026-03-02.sha256.ots", PENDING)
        _, _, pending, overdue = self.upgrade()
        self.assertEqual(pending, ["attest/2026-03-02.sha256.ots"])
        self.assertEqual(overdue, [])

    def test_the_proof_of_a_monthly_report_is_completed_as_well(self):
        self.set_env(STAND_IN_UPGRADE="confirms")
        os.makedirs(os.path.join(self.record, "reports"))
        path = os.path.join(self.record, "reports", "2026-03.sha256.ots")
        with open(path, "w") as f:
            f.write(PENDING)
        _, completed, _, _ = self.upgrade()
        self.assertEqual(completed, ["reports/2026-03.sha256.ots"])
        self.assertIn(COMPLETE, open(path).read())

    def test_only_proofs_are_considered(self):
        self.proof("2026-03-02.sha256", "hashes\n")
        self.proof("accounts.md", "register\n")
        self.assertEqual(self.upgrade(), ([], [], [], []))
        self.assertEqual(self.calls(), [])

    def test_an_unreadable_proof_stops_the_run(self):
        self.proof("2026-03-02.sha256.ots", "not a proof\n")
        with self.assertRaises(SystemExit):
            self.upgrade()

    # --- patience --------------------------------------------------------

    def test_a_proof_pending_for_more_than_a_day_after_its_commit_is_overdue(self):
        self.proof("2026-03-02.sha256.ots", PENDING)
        self.commit("attest/2026-03-02.sha256.ots", hours_ago=30)
        _, _, pending, overdue = self.upgrade()
        self.assertEqual(overdue, ["attest/2026-03-02.sha256.ots"])

    def test_a_proof_committed_less_than_a_day_ago_is_not_overdue(self):
        self.proof("2026-03-02.sha256.ots", PENDING)
        self.commit("attest/2026-03-02.sha256.ots", hours_ago=2)
        _, _, pending, overdue = self.upgrade()
        self.assertEqual(pending, ["attest/2026-03-02.sha256.ots"])
        self.assertEqual(overdue, [])

    def test_a_proof_not_yet_committed_is_not_overdue(self):
        self.proof("2026-03-02.sha256.ots", PENDING)
        _, _, _, overdue = self.upgrade(now=int(time.time() * 1000) + 10 * 86_400_000)
        self.assertEqual(overdue, [])

    def test_a_confirmed_proof_is_never_overdue(self):
        self.set_env(STAND_IN_UPGRADE="confirms")
        self.proof("2026-03-02.sha256.ots", PENDING)
        self.commit("attest/2026-03-02.sha256.ots", hours_ago=30)
        _, completed, _, overdue = self.upgrade()
        self.assertEqual(completed, ["attest/2026-03-02.sha256.ots"])
        self.assertEqual(overdue, [])


if __name__ == "__main__":
    unittest.main()
