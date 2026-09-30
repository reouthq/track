#!/usr/bin/env python3
"""The commitment that ties the record's key to the account it may read.

A key names no account of itself, so the account register carries a commitment
to the identifiers the exchange gives for the account, and the record refuses to
run against a key that does not match it (pull.py, check_account).

The commitment is salted. The identifiers are short — nine digits and fourteen
characters — so a plain hash of them could be undone by trying every value; the
salt makes that useless without it. The salt is held with the record's other
secrets and given, with the identifiers, to verifiers under a non-disclosure
agreement, who can then check the commitment themselves.

Prints the commitment and nothing else: the commitment is public, the
identifiers it commits to are not.

    TRACK_ACCOUNT_SALT=... python3 tools/account_commitment.py \\
        --archive <copy.json.enc>... --passphrase-file <file>
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pull  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", nargs="+", required=True, help="retained copies of the records")
    ap.add_argument("--passphrase-file", required=True, help="file holding the passphrase")
    a = ap.parse_args()

    salt = os.environ.get(pull.ACCOUNT_SALT)
    if not salt:
        raise SystemExit(f"{pull.ACCOUNT_SALT} is not set; no commitment is computed")

    seen = {}
    for path in a.archive:
        _, doc = pull.read_archive(path, a.passphrase_file)
        identity = doc.get("account")
        if identity:
            seen.setdefault(pull.account_commitment(salt, identity), []).append(
                pull.ms_to_iso(doc["fetched_at_ms"]))

    if not seen:
        raise SystemExit("no copy names an account; fetch.py has not been run since it did")
    for commitment, when in sorted(seen.items(), key=lambda kv: kv[1][-1]):
        print(f"{commitment}  from {len(when)} copy(ies), newest {when[-1]}")


if __name__ == "__main__":
    main()
