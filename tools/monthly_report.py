#!/usr/bin/env python3
"""The monthly report of the record (Methodology, section 5).

Every figure is taken from `data/` as published, with the corrections in
`data/corrections.csv` applied; nothing is recomputed except the month's sums of
daily shares, which the report names as such. The thresholds are read from the
Risk Limits, and the written text from the registers in `attest/`, where it was
entered at the time. The report carries no time of its own making, so the same
files give the same report, byte for byte.

    python3 tools/monthly_report.py --month 2026-10 [--root DIR] [--ots PATH]

It writes reports/YYYY-MM.md, the PDF rendered from it (tools/report_pdf.py),
reports/YYYY-MM.sha256 with the hashes of both, and the OpenTimestamps proof of
that manifest, all four or none: nothing is moved into reports/ until the
manifest has been anchored.

Nothing is written when the month has no row in the data, when the data files
are not those of an anchored manifest, when that manifest is dated before the
month's last day (the month is not yet published to its end), when a correction
does not match the value it corrects, when a threshold cannot be read, or when
the month's report already exists: a published report is corrected by a new
file, never rewritten.
"""

import argparse
import calendar
import csv
import datetime as dt
import glob
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pull  # noqa: E402  (anchoring, as the daily workflow anchors)
import report_pdf  # noqa: E402

DATA = ["data/corrections.csv", "data/equity_daily.csv", "data/income_daily.csv",
        "data/monthly.csv", "data/transfers.csv"]

# The column that identifies a row of each table, as data/corrections.csv names it.
KEYS = {"data/equity_daily.csv": "date_utc", "data/income_daily.csv": "date_utc",
        "data/transfers.csv": "ts_utc", "data/monthly.csv": "month"}

# Each metric of the Risk Limits, read from a row of data/monthly.csv in the units
# its thresholds are stated in. A drawdown is published as a positive fraction of
# the high (Methodology, section 4); its thresholds are negative percentages.
METRICS = {
    "Account drawdown": lambda m: None if m["drawdown"] is None else -m["drawdown"] * 100,
    "Trailing 30-day return": lambda m: None if m["trailing_30d"] is None else m["trailing_30d"] * 100,
    "Trailing 65-day return": lambda m: None if m["trailing_65d"] is None else m["trailing_65d"] * 100,
    "Days underwater": lambda m: m["days_underwater"],
}

REGISTERS = {"versions": "attest/versions.md", "accounts": "attest/accounts.md",
             "incidents": "attest/incidents.md", "interventions": "attest/interventions.md",
             "reviews": "attest/reviews.md", "reconciliation": "attest/reconciliation.md",
             "changelog": "CHANGELOG.md"}

# The words by which a report says its month's reconciliation was still open, and
# by which the next report knows to give the outcome.
NOT_COMPLETE = "was not complete when this report was published"

MINUS = "−"
DASH = "—"


def refuse(message):
    raise SystemExit(f"{message}; the report is not produced")


# --- reading ----------------------------------------------------------------

def read_bytes(root, rel):
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        refuse(f"{rel} is missing")
    with open(path, "rb") as f:
        return f.read()


def number(value):
    return None if value in ("", None) else float(value)


def markdown_table(text, heading=None):
    """The rows of the first table in `text`, or of the first after `heading`, as dicts.

    A row whose first cell is "n/a" says the table is empty, and is left out.
    """
    if heading is not None:
        at = text.find(heading)
        if at < 0:
            return None
        text = text[at:]
    lines = []
    for line in text.splitlines():
        if line.startswith("|"):
            lines.append(line)
        elif lines:
            break
    if len(lines) < 2:
        return None
    cells = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines]
    header = cells[0]
    return [dict(zip(header, row)) for row in cells[2:] if row and row[0].lower() != "n/a"]


def thresholds(root):
    """[(metric, levels as stated, levels as numbers, unit)] from the Risk Limits, section 3."""
    rows = markdown_table(read_bytes(root, "RISK_LIMITS.md").decode(), "## 3. Thresholds")
    if not rows:
        refuse("the thresholds of the Risk Limits cannot be read")
    out = []
    for row in rows:
        metric, *stated = list(row.values())[:4]
        values = []
        for cell in stated:
            m = re.fullmatch(r"([−-]?\d+(?:\.\d+)?)%?", cell)
            if not m:
                refuse(f"the threshold {cell!r} of {metric} cannot be read")
            values.append(float(m.group(1).replace(MINUS, "-")))
        out.append((metric, stated, values, "percent" if stated[0].endswith("%") else "days"))
    if sorted(m for m, *_ in out) != sorted(METRICS):
        refuse("the Risk Limits state metrics this report does not read")
    return out


def level(value, values, unit):
    """The deepest level a value has reached: none, review, risk reduction or program review."""
    if value is None:
        return "not assessed"
    reached = (lambda v, t: v <= t) if unit == "percent" else (lambda v, t: v >= t)
    for name, threshold in reversed(list(zip(("review", "risk reduction", "program review"), values))):
        if reached(value, threshold):
            return name
    return "none"


def apply_corrections(tables):
    """Apply each row of data/corrections.csv to the value it names, and return those rows."""
    applied = []
    for c in tables["data/corrections.csv"]:
        rel = c["file"]
        if rel not in KEYS:
            refuse(f"a correction names {rel}, which the report does not read")
        rows = [r for r in tables[rel] if r.get(KEYS[rel]) == c["date"]]
        if len(rows) != 1 or c["column"] not in rows[0]:
            refuse(f"a correction to {rel}, {c['date']}, {c['column']} names no published value")
        if rows[0][c["column"]] != c["published_value"]:
            refuse(f"a correction to {rel}, {c['date']}, {c['column']} does not match the published value")
        rows[0][c["column"]] = c["corrected_value"]
        applied.append(c)
    return applied


def anchored_in(root, contents):
    """The latest daily manifest listing every data file with the bytes read, and its proof."""
    wanted = {rel: hashlib.sha256(data).hexdigest() for rel, data in contents.items()}
    for path in sorted(glob.glob(os.path.join(root, "attest", "*.sha256")), reverse=True):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.sha256", os.path.basename(path)):
            continue
        listed = {}
        with open(path) as f:
            for line in f.read().splitlines():
                digest, _, rel = line.partition("  ")
                listed[rel] = digest
        if all(listed.get(rel) == digest for rel, digest in wanted.items()):
            if not os.path.exists(path + ".ots"):
                refuse(f"{os.path.relpath(path, root)} lists the data files but has no proof")
            return os.path.relpath(path, root), wanted
    refuse("the data files are not those listed in any anchored manifest")


# --- writing ----------------------------------------------------------------

def pct(value, digits=2):
    if value is None:
        return DASH
    shown = round(value * 100, digits)
    if shown == 0:
        return f"{0:.{digits}f}%"
    return f"{'+' if shown > 0 else MINUS}{abs(shown):.{digits}f}%"


def magnitude(value, digits=2):
    """A percentage that has no sign, such as a volatility."""
    return DASH if value is None else f"{value * 100:.{digits}f}%"


def ratio(value, digits=2):
    if value is None:
        return DASH
    shown = round(value, digits)
    return f"{MINUS if shown < 0 else ''}{abs(shown):.{digits}f}"


def points(value, unit):
    if value is None:
        return DASH
    if unit == "days":
        return f"{value:.0f}"
    return f"{MINUS if round(value, 1) < 0 else ''}{abs(value):.1f}%"


def index(value):
    return DASH if value is None else f"{value:.2f}"


def table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(row) + " |" for row in rows]


def days_between(first, last):
    day, end, out = dt.date.fromisoformat(first), dt.date.fromisoformat(last), []
    while day <= end:
        out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def render(root, month):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        refuse(f"{month!r} is not a month")
    contents = {rel: read_bytes(root, rel) for rel in DATA}
    manifest, hashes = anchored_in(root, contents)
    tables = {rel: list(csv.DictReader(io.StringIO(data.decode()))) for rel, data in contents.items()}
    corrections = apply_corrections(tables)
    registers = {name: markdown_table(read_bytes(root, rel).decode()) or []
                 for name, rel in REGISTERS.items()}
    limits = thresholds(root)

    equity = tables["data/equity_daily.csv"]
    monthly = [r for r in tables["data/monthly.csv"] if r["month"] <= month]
    if not equity or not monthly or monthly[-1]["month"] != month:
        refuse(f"the record has no row for {month}")
    raw = monthly[-1]
    m = {k: v if k in ("month", "through_utc", "mwr_basis") else number(v) for k, v in raw.items()}

    inception = equity[0]["date_utc"]
    year, mon = int(month[:4]), int(month[5:])
    first = max(f"{month}-01", inception)
    last = f"{month}-{calendar.monthrange(year, mon)[1]:02d}"
    if os.path.basename(manifest)[:10] < last:
        refuse(f"the record is not yet published to the end of {month}")
    inside = [r for r in equity if r["date_utc"].startswith(month)]
    by_date = {r["date_utc"]: r for r in equity}
    income = [r for r in tables["data/income_daily.csv"] if r["date_utc"].startswith(month)]
    transfers = [t for t in tables["data/transfers.csv"] if t["ts_utc"].startswith(month)]
    name = f"{calendar.month_name[mon]} {year}"

    L = []
    w = L.append
    w(f"# Monthly report: {name}")
    w("")
    w("BTC-1, the record of reout.")
    w("")
    w(f"- Month: {month}")
    w(f"- Record inception: {inception}")
    w(f"- Valuation points in this report: {first} to {m['through_utc']}")
    for name, address, _ in report_pdf.VERIFY:
        w(f"- {name}: `{address}`")
    w("")
    if first > f"{month}-01":
        w(f"This is the first report. It covers the part of the month from record inception, {inception}.")
        w("")
    w("Every figure is taken from the record's data files, listed with their hashes in part 8, and is a "
      "return or a ratio relative to net asset value; no currency amount is published. The descriptions "
      "of changes, incidents, review findings and reconciliation differences are written by reout at the "
      "time, in the registers they are quoted from (Methodology, section 5).")
    w("")

    # 1. Returns
    w("## 1. Returns")
    w("")
    mwr = (f"{pct(m['mwr_itd'])}, for the period" if m["mwr_basis"] == "period"
           else f"{pct(m['mwr_itd'])}, annualized" if m["mwr_basis"] == "annual" else DASH)
    L += table(["", "Month", "Since record inception"], [
        ["Time-weighted return, as traded", pct(m["ret_twr"]), pct(m["ret_twr_itd"])],
        ["Time-weighted return, derived 1×", pct(m["ret_l1"]), pct(m["ret_l1_itd"])],
        ["Money-weighted return", DASH, mwr],
    ])
    w("")
    w("Daily valuation points of the month:")
    w("")
    L += table(["Date (UTC)", "Return", "Index", "Return, 1×", "Index, 1×", "Benchmark return", "Version"],
               [[r["date_utc"], pct(number(r["ret_twr"])), index(number(r["nav_idx"])),
                 pct(number(r["ret_l1"])), index(number(r["nav_l1_idx"])), pct(number(r["ret_btc"])),
                 r["version"]] for r in inside])
    w("")
    w("Index at the last valuation point of each month since record inception:")
    w("")
    L += table(["Month", "Last valuation point", "Index", "Index, 1×"],
               [[r["month"], r["through_utc"], index(number(by_date[r["through_utc"]]["nav_idx"])),
                 index(number(by_date[r["through_utc"]]["nav_l1_idx"]))] for r in monthly])
    w("")

    # 2. Risk
    w("## 2. Risk")
    w("")
    sharpe = (f"{ratio(m['sharpe_itd'])}, from {m['return_days_itd']:.0f} daily returns"
              if m["sharpe_itd"] is not None else "not reported until the record spans twelve full months")
    L += table(["", "Month", "Since record inception"], [
        ["Annualized volatility", magnitude(m["vol_ann"]), magnitude(m["vol_ann_itd"])],
        ["Worst day", pct(m["worst_day"]), pct(m["worst_day_itd"])],
        ["Best day", pct(m["best_day"]), pct(m["best_day_itd"])],
        ["Maximum drawdown", pct(None if m["max_drawdown_month"] is None else -m["max_drawdown_month"]),
         pct(None if m["max_drawdown"] is None else -m["max_drawdown"])],
        ["Maximum drawdown, derived 1×", DASH,
         pct(None if m["max_drawdown_l1"] is None else -m["max_drawdown_l1"])],
        ["Current drawdown", DASH, pct(None if m["drawdown"] is None else -m["drawdown"])],
        ["Days underwater", DASH, DASH if m["days_underwater"] is None else f"{m['days_underwater']:.0f}"],
        ["Sharpe ratio", DASH, sharpe],
    ])
    w("")
    w(f"Drawdowns are measured on the index at daily valuation points and are a lower bound; the current "
      f"drawdown and the days underwater are those at {m['through_utc']}.")
    w("")

    # 3. Benchmark
    w("## 3. Benchmark")
    w("")
    corr = ratio(m["corr_btc"])
    L += table(["", "Month", "Since record inception"], [
        ["Benchmark return", pct(m["ret_btc"]), pct(m["ret_btc_itd"])],
        ["Benchmark maximum drawdown", DASH,
         pct(None if m["max_drawdown_btc"] is None else -m["max_drawdown_btc"])],
        ["Correlation of daily returns with the benchmark", corr, DASH],
    ])
    w("")

    # 4. Risk Limits
    w("## 4. Position against the Risk Limits")
    w("")
    rows = []
    for metric, stated, values, unit in limits:
        value = METRICS[metric](m)
        rows.append([metric, points(value, unit), *stated, level(value, values, unit)])
    L += table(["Metric", "Current", "Review", "Risk reduction", "Program review", "Level reached"], rows)
    w("")
    w(f"Assessed at the last valuation point of the month, {m['through_utc']}. None of the levels stops "
      "trading by itself; the action taken at each is set out in the Risk Limits.")
    w("")
    reviews = [r for r in registers["reviews"] if list(r.values())[0][:7] == month]
    if reviews:
        w("Reviews under the Risk Limits in the month, as entered in the review register:")
        w("")
        L += table(list(reviews[0].keys()), [list(r.values()) for r in reviews])
    else:
        w("No review under the Risk Limits was entered for the month.")
    w("")

    # 5. Flows and costs
    w("## 5. Flows and costs")
    w("")
    if transfers:
        # A credit (a rebate or a reward paid by the exchange) is an external flow,
        # not a return, and is named as what it is.
        L += table(["Timestamp (UTC)", "Flow", "Share of net asset value"],
                   [[t["ts_utc"],
                     "credit" if t.get("kind") == "credit"
                     else "deposit" if number(t["amount_frac"]) > 0 else "withdrawal",
                     pct(number(t["amount_frac"]), 4)] for t in transfers])
    else:
        w("No external flow in the month.")
    w("")
    costs = sum(number(r["costs_frac"]) or 0.0 for r in income)
    w(f"Costs, commissions and funding combined: {pct(costs, 4)} of net asset value, the sum of the "
      "month's daily shares.")
    w("")
    other = [(r["date_utc"], r["other_types"].replace(";", ", ")) for r in income if r.get("other_types")]
    if other:
        w("Other income types, by day:")
        w("")
        L += table(["Date (UTC)", "Types"], [[d, t] for d, t in other])
    else:
        w("No other income type in the month.")
    w("")

    # 6. Version
    w("## 6. Program version")
    w("")
    runs = []
    for r in inside:
        if runs and runs[-1][0] == r["version"]:
            runs[-1][2], runs[-1][3] = r["date_utc"], runs[-1][3] + 1
        else:
            runs.append([r["version"], r["date_utc"], r["date_utc"], 1])
    classes = {r.get("Version"): r.get("Class", "") for r in registers["versions"]}
    L += table(["Version", "Class", "In force from", "In force to", "Valuation points"],
               [[v, classes.get(v, DASH) or DASH, a, b, str(n)] for v, a, b, n in runs])
    w("")

    # 7. Reconciliation, changes and incidents
    w("## 7. Reconciliation, changes and incidents")
    w("")
    w("### Reconciliation")
    w("")
    outcomes = {r["Month"]: r for r in registers["reconciliation"]}
    earlier = f"{year - (mon == 1)}-{12 if mon == 1 else mon - 1:02d}"
    earlier_report = os.path.join(root, "reports", f"{earlier}.md")
    carried = False
    if earlier in outcomes and os.path.exists(earlier_report):
        with open(earlier_report, encoding="utf-8") as f:
            carried = NOT_COMPLETE in f.read()
    if carried:
        w(f"The reconciliation of {earlier}, which was not complete when that report was published:")
        w("")
        L += table(list(outcomes[earlier].keys()), [list(outcomes[earlier].values())])
        w("")
    if month in outcomes:
        L += table(list(outcomes[month].keys()), [list(outcomes[month].values())])
    else:
        w(f"The reconciliation of {month} {NOT_COMPLETE}. Its outcome is given in the next report.")
    w("")

    w("### Changes")
    w("")
    changes = []
    for r in registers["versions"]:
        day = r.get("Deployed (UTC)", "")[:10]
        if first <= day <= last:
            changes.append(f"Version {r.get('Version')} ({r.get('Class')}) took effect on {day}.")
        elif day > last:
            changes.append(f"Version {r.get('Version')} ({r.get('Class')}) is announced to take effect on {day}.")
    for r in registers["accounts"]:
        day = r.get("Account inception (UTC)", "")[:10]
        if first <= day <= last or day > last:
            changes.append(f"Account {r.get('#')} ({r.get('Type')}), inception {day}, status {r.get('Status')}.")
    for r in registers["changelog"]:
        if r.get("Date (UTC)", "")[:7] == month:
            changes.append(f"{r.get('File')}: {r.get('Change')} ({r.get('Date (UTC)')}).")
    for line in changes or ["No change took effect or was announced in the month."]:
        w(f"- {line}")
    w("")

    w("### Incidents")
    w("")
    missed = [d for d in days_between(first, last) if d not in by_date]
    entered = [r for r in registers["incidents"] if list(r.values())[0][:7] == month]
    actions = [r for r in registers["interventions"] if list(r.values())[0][:7] == month]
    if entered:
        w("As entered in the incident log:")
        w("")
        L += table(list(entered[0].keys()), [list(r.values()) for r in entered])
        w("")
    if missed:
        w("Days of the month without a published valuation point at the time of this report: "
          + ", ".join(missed) + ".")
        w("")
    if actions:
        w("Manual actions, as entered in the intervention log:")
        w("")
        L += table(list(actions[0].keys()), [list(r.values()) for r in actions])
        w("")
    if not (entered or missed or actions):
        w("No incident was entered in the incident log for the month, no manual action was logged, and "
          "every day of the month has a published valuation point.")
        w("")

    w("### Corrections")
    w("")
    ours = [c for c in corrections if c["date"][:7] == month]
    if ours:
        L += table(["Row", "File", "Column", "Published value", "Corrected value", "Reason"],
                   [[c["date"], c["file"], c["column"], c["published_value"], c["corrected_value"], c["reason"]]
                    for c in ours])
    else:
        w("No correction to a value of the month.")
    w("")

    # 8. Hashes
    w("## 8. Data files and proofs")
    w("")
    L += table(["File", "SHA-256"], [[f"`{rel}`", f"`{hashes[rel]}`"] for rel in DATA])
    w("")
    w(f"These are the files this report was produced from. They are listed with these hashes in "
      f"`{manifest}`, whose proof is `{manifest}.ots`. A file cannot state its own hash: the hashes of this "
      f"report and of its PDF are anchored beside it, in `reports/{month}.sha256` and its proof.")
    w("")
    w("---")
    w("")
    w("Generated by `tools/monthly_report.py`. Past results do not indicate future results. Nothing here is "
      "an offer, a solicitation or investment advice.")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--month", required=True, metavar="YYYY-MM")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="a checkout of the record")
    ap.add_argument("--ots", default="ots", help="the OpenTimestamps client")
    a = ap.parse_args()
    reports = os.path.join(a.root, "reports")
    names = [f"{a.month}.md", f"{a.month}.pdf", f"{a.month}.sha256", f"{a.month}.sha256.ots"]
    for name in names:
        if os.path.exists(os.path.join(reports, name)):
            refuse(f"reports/{name} already exists")

    markdown = render(a.root, a.month).encode("utf-8")
    pdf = report_pdf.render(markdown.decode("utf-8"), f"reports/{a.month}.md",
                            hashlib.sha256(markdown).hexdigest())
    files = {names[0]: markdown, names[1]: pdf}
    files[names[2]] = "".join(f"{hashlib.sha256(data).hexdigest()}  reports/{name}\n"
                              for name, data in sorted(files.items())).encode()

    os.makedirs(reports, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=f".staging-{a.month}-", dir=reports)
    try:
        for name, data in files.items():
            with open(os.path.join(staging, name), "wb") as f:
                f.write(data)
        pull.stamp(os.path.join(staging, names[2]), a.ots)
        for name in names:
            os.replace(os.path.join(staging, name), os.path.join(reports, name))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print("written: " + ", ".join(f"reports/{name}" for name in names))


if __name__ == "__main__":
    main()
