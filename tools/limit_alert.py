#!/usr/bin/env python3
"""Tell the operator when the Account has reached a level of the Risk Limits.

The Risk Limits (section 4) promise a review within two business days of a threshold being reached, so
reaching one must not wait for someone to look. Run after each daily record, this reads the latest
row of data/monthly.csv and the thresholds of the Risk Limits, the same way the Monthly Report does
(tools/monthly_report.py), and prints the level each metric has reached. While any metric stands at
a level, it sends one notice a day to the channel named by NTFY_TOPIC, if one is set.

The thresholds are read from this repository's own Risk Limits, which are the ones in force;
the record may be published elsewhere (during the rehearsal, into a private repository).

The log names levels only, never values; the values are in the published files already.

    python3 tools/limit_alert.py --root <a checkout of the record>
"""

import argparse
import csv
import io
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monthly_report as mr  # noqa: E402  (the thresholds and the levels, as the report reads them)

REPOSITORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def latest_month(root):
    rel = "data/monthly.csv"
    if not os.path.exists(os.path.join(root, rel)):
        return None
    rows = list(csv.DictReader(io.StringIO(mr.read_bytes(root, rel).decode())))
    if not rows:
        return None
    return {k: (v if k in ("month", "through_utc", "mwr_basis") else mr.number(v)) for k, v in rows[-1].items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="a checkout of the record")
    a = ap.parse_args()

    row = latest_month(a.root)
    if row is None:
        print("# no month published yet; nothing to assess")
        return
    reached = []
    for metric, _stated, values, unit in mr.thresholds(REPOSITORY):
        name = mr.level(mr.METRICS[metric](row), values, unit)
        print(f"# {metric}: {name}")
        if name not in ("none", "not assessed"):
            reached.append(f"{metric}: {name}")
    if not reached:
        return

    message = ("A level of the Risk Limits has been reached (" + "; ".join(reached) + ", as of "
               f"{row['through_utc']}). The review is due within 24 hours of the level being reached "
               "(Risk Limits, section 4).")
    topic = os.environ.get("NTFY_TOPIC", "")
    if not topic:
        print("# a level is reached, and no notification channel is set (NTFY_TOPIC)")
        return
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode(), method="POST",
                                 headers={"Title": "BTC-1: Risk Limits level reached", "Priority": "high"})
    with urllib.request.urlopen(req, timeout=20) as r:
        print(f"# notice sent: HTTP {r.status}")


if __name__ == "__main__":
    main()
