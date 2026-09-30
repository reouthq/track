# Methodology

This Methodology sets out how the performance record of BTC-1 (the "Program") is measured,
calculated, published and verified, and the conditions under which this document and the Program
may be changed.

## Summary of key terms

| Term | Provision |
|---|---|
| Program | A fully systematic directional strategy in BTCUSDT perpetual futures, long and short |
| Valuation | Daily, as of the exchange's end-of-day mark. Net Asset Value includes open positions marked to market |
| Performance | Daily time-weighted returns, net of all trading costs and geometrically linked. The money-weighted return is reported alongside in the Monthly Report |
| Leverage | Notional exposure of up to three times equity. A derived series, the actual returns divided by three, is published for comparison only and does not represent a traded account |
| Benchmark | Bitcoin, buy-and-hold, compared with the one-times derived series |
| Publication | Returns and ratios only. No currency amounts, positions or individual fills |
| Reporting | Monthly, on the third calendar day of the following month, irrespective of performance. No month is omitted |
| Corrections | Published figures are not amended. Errors of any size are corrected by a separate, logged correction |
| Verification | Daily files, published and unpublished, are hashed and timestamped on the Bitcoin blockchain. Unpublished data is available under NDA (section 6) |
| Governance | Amendments to this document and changes of version take effect only once anchored. No version change is made in response to losses |

**Precedence.** This document is anchored before Record Inception and amended only as section 7 sets
out. In the event of a discrepancy between a published figure and the code that produced it, the
code and the underlying exchange data prevail, and the discrepancy is treated as an incident
(section 5).

**Industry standards.** No claim of compliance with the Global Investment Performance Standards
(GIPS) is made, and the record has not been subject to independent verification. The Methodology
uses time-weighted returns, a cash flow policy established in advance, returns net of transaction
costs, a composite from which no account is excluded, and a disclosed benchmark.

---

## 1. Scope

| Term | Definition |
|---|---|
| Program | BTC-1, a single fully automated strategy trading long and short |
| Instrument | BTCUSDT perpetual futures, USDT-margined |
| Venue | The trading venue of the Account, as recorded in the account register. A change of venue is governed by section 7 |
| Account | The designated futures account or accounts recorded in the account register. No other trading activity is conducted in the Account |
| Capital | Proprietary capital at Record Inception. No management or performance fees are charged, and gross and net returns are therefore identical. External capital or fees may be introduced as section 7 sets out; the record continues, and from then returns are reported both gross and net of fees |
| Account Inception | The date of the first deposit into the Account, as recorded in the account register |
| Record Inception | The Valuation Point at the end of the UTC day specified in the pre-registration manifest (section 7). The first daily return of the record is that of the following day |
| Base currency | USDT. All published figures are returns or ratios. No currency conversion or adjustment for stablecoin risk is applied |
| Leverage | Notional exposure of up to three times equity, compounded continuously. Long and short positions may be held concurrently |
| Discretion | Entries, exits and position sizes are determined solely by the system. The only permitted manual actions are a suspension of new entries, the risk-reduction provision of the Risk Limits, section 4, and the venue failure procedure of the Risk Limits, section 5, each recorded in the intervention log when used. Any other manual action constitutes an intervention and is reported |

A change to any term in this table other than Capital constitutes a change to the Program. Such a
change takes effect only after this document has been amended in accordance with section 7 and the
change has been announced in a Monthly Report. A change of Capital is made in the same way but does
not change the Program, and the record continues. Prior performance is not restated.

## 2. Data and valuation

**Data sources.** All figures are derived from exchange API responses retrieved daily by a public
automated workflow, using a read-only key held apart from the keys used for trading. Each data
commit names the workflow run that produced it, and run logs are public for as long as the hosting
service retains them. Requests may pass through network infrastructure operated by reout; the
traffic is encrypted end to end and the exchange's certificate is validated, so that the
infrastructure can neither read nor alter it.

| Data | Source | Publication |
|---|---|---|
| Balance and open positions | The exchange's daily account record | Hash only. Derived returns are published |
| Income ledger: transfers, realized P&L, commissions, funding and other income types | The exchange's income history, all types | Hash only. Daily totals and individual transfers are published as a share of NAV |
| Benchmark price | Spot BTCUSDT daily close (section 3) | Published unmodified |

Account-level data is not published, as it would disclose the size of the Account, its positions and
its fills. It is retained encrypted, its daily hashes are anchored, and it is available under NDA
(section 6). A change of API endpoint or field name that leaves the data above unchanged is a change
of code, not of this document.

A day is published once the exchange has completed its record of it, normally the following day and
sometimes later. A manual run after a missed scheduled run executes identical code and is recorded
as an incident. A separate ledger of the Account is kept on reout's servers and reconciled against
the record monthly (section 5). The exchange does not sign its responses, so the record evidences
what the workflow received, when it was committed and the anchoring of its hash (section 6).

**Valuation Point.** The Account is valued once daily, as of the timestamp of the exchange's daily
account record (the "Valuation Point") at the end of the UTC day: the same day as the Benchmark's
close, and before the next day's funding settlement. Each valuation interval runs from the preceding
Valuation Point (exclusive) to the current one (inclusive). NAV at Record Inception is the base of
the record. A missed Valuation Point is an incident, and the next interval spans the gap.

**Net Asset Value.** Net Asset Value ("NAV") is `nav = wallet + unrealized`. `wallet` is the wallet
balance in the exchange's daily record, excluding unrealized P&L; `unrealized` is the sum, over all
positions in that record, of signed position size times the difference between the record's mark
price and the position's entry price. The exchange's aggregate unrealized figure is not used. Before
publication the mark price is checked against the exchange's public mark price history, and each
position against the previous record and the fills in between. Commissions and funding are settled
within the Account and so are reflected in NAV and in all returns. Returns are before taxes.

**Positions open at Record Inception.** The record begins on the Account as the Program holds it.
Open positions are valued at the mark price of the first Valuation Point and included in the opening
NAV; only their movement after it counts towards returns. No position is opened or closed because
the record begins.

**External cash flows.** External cash flows are transfers into and out of the Account, and credits:
amounts the exchange pays into the Account other than as the result of trading, such as rebates and
rewards. A credit is not earned from the market and is not a return. Each flow is allocated to the
valuation interval in which its exchange timestamp falls, and $F_t$ denotes the net flow in interval
$t$. Realized P&L, commissions, funding and other income are internal to the Account and are not
treated as cash flows.

**Aggregation.** Where more than one account is recorded in the account register, `wallet`,
`unrealized`, `nav` and $F_t$ are aggregated across accounts as of the same Valuation Point, and the
record is presented as a single series.

## 3. Returns and benchmark

**Daily time-weighted return.** External cash flows are assumed to occur at the start of the
valuation interval. This convention is fixed in advance and may not be revised retrospectively.

$$
r_t = \frac{\mathrm{NAV}_t}{\mathrm{NAV}_{t-1} + F_t} - 1
$$

Days on which an external cash flow occurred are identified in the Monthly Report, together with the
timestamp of the flow.

**Period return.** Returns for longer periods are calculated by geometric linking of daily returns,
$R = \prod_{t} (1 + r_t) - 1$. Reporting periods are UTC calendar months. The first period runs from
Record Inception to the end of that month.

**Money-weighted return.** The money-weighted return is the annual rate $y$ that satisfies

$$
\mathrm{NAV}_T = \sum_{i} F_i \,(1 + y)^{(T - t_i)/365}
$$

where $F_i$ is either NAV at Record Inception, treated as the initial contribution, or a subsequent
transfer (contributions positive) at time $t_i$ in days, and $T$ is the current Valuation Point. For
periods shorter than one year the return is stated for the period and is not annualized. The
time-weighted return reflects the performance of the strategy, and the money-weighted return the
return on capital. Both are reported.

**Leverage-normalized series.** To permit comparison with unlevered strategies and with the
Benchmark, a derived series is calculated by dividing each daily return by $L = 3$, the Program's
maximum notional multiple (section 1):

$$
r^{(1)}_t = \frac{r_t}{L}
$$

The derived series scales daily P&L, including costs, by $1/L$. Because $L$ is the maximum, it
represents at most one times notional exposure, and less on any day on which the Account ran below
its maximum. Effects that arise only at the live multiple, such as margin calls or liquidation, are
not modeled; should one occur, it is reported as an incident and the series is annotated. The series
is labeled as derived wherever it is shown and does not represent a traded account.

**Benchmark.** The benchmark (the "Benchmark") is bitcoin bought and held, measured by the spot
BTCUSDT daily close on the venue in the account register, without leverage or costs; a change of
venue does not restate past values. It is compared with the leverage-normalized series, since
returns at different leverage are not comparable, and the correlation of daily returns with it is
reported monthly. No simulated or backtested result is used as a benchmark: live performance is
assessed against the thresholds of the Risk Limits.

## 4. Risk statistics

| Statistic | Definition |
|---|---|
| Maximum drawdown | $\max_t \left(1 - \frac{I_t}{\max_{s \le t} I_s}\right)$ over daily Valuation Points. Intraday drawdowns are not captured, so this figure is a lower bound |
| Current drawdown | $1 - \frac{I_T}{\max_{s \le T} I_s}$ as of the latest Valuation Point $T$ |
| Days underwater | Number of days since the most recent high of $I_t$ |
| Annualized volatility | $\sqrt{365}\,\sigma(r_t)$, measured over all calendar days |
| Sharpe ratio | $\sqrt{365}\,\bar{r} / \sigma(r_t)$, with a risk-free rate of zero. Not reported until the record spans twelve full months, and thereafter reported with its sample size |
| Worst day, best day | $\min_t r_t$ and $\max_t r_t$ over the period |

$I_t$ denotes the cumulative index of daily time-weighted returns, set to 100 at Record Inception.
Drawdown statistics are calculated on this index, so that external cash flows are not treated as
gains or losses, and they include unrealized changes in open positions. For comparison, the maximum
drawdown is also reported for the leverage-normalized series and for the Benchmark, measured in the
same way on the derived index and on the Benchmark's daily close.

**Trade statistics.** Trade-level statistics, including the number of trades, holding periods and
the long/short split, are not published. They are available under NDA (section 6).

## 5. Publication and reporting

**Published figures.** All published figures are returns or ratios relative to NAV (section 2). The
following are published:

1. Daily: the time-weighted return and its cumulative index, the leverage-normalized return and its
   cumulative index, the net external cash flow as a share of NAV, the Benchmark close and return, and
   the Program version in effect.
2. Daily: realized P&L and trading costs as a share of NAV. Commissions and funding are combined, as
   their separate totals would disclose position size.
3. Each external transfer, as a share of NAV.
4. Monthly: the statistics set out in sections 3 and 4 and the position against the Risk Limits.
   Figures for the current month are updated daily until month end.
5. A log of corrections.

Cumulative indices are set to 100 at Record Inception. File formats and column definitions are set
out in the repository guide.

**Official record.** The published figures, the published Benchmark data and the anchored hashes of
unpublished account data together constitute the official record. Monthly Reports, their PDF versions
and the public website are generated from the official record by scripts maintained in the
repository. In case of inconsistency, the official record prevails.

**Monthly Report.** A report for each month (the "Monthly Report") is published on the third
calendar day of the next, whatever the result, as plain text and as PDF. No month is omitted. It
sets out returns, risk statistics and the Benchmark comparison (sections 3 and 4), the position
against the Risk Limits, the month's external cash flows and costs, the versions in effect, the
outcome of reconciliation, changes and incidents, and the hashes of the month's files. Only the
descriptions of changes, incidents, reviews and reconciliation differences are written rather than
generated, and they are written at the time.

**Reconciliation.** Each Monthly Report states whether three sources agree for the month:
the record's ledger, reout's server ledger, and the exchange's own transaction statement for the
Account. The sources are deemed to agree where (i) the wallet balance at the final Valuation Point of
the month matches across all three within 0.01 USDT, (ii) the cumulative income ledger reconciles to
that balance, and (iii) every external transfer appears in each source with identical timestamps and
amounts. Only the outcome of the reconciliation is published. Any difference is disclosed and
explained. A reconciliation not complete at the publication date is reported as pending and concluded
in the following Monthly Report.

**Changes.** Changes to the Account, the Program version or any term in section 1 follow section 7
and are reported, with their effective date, in the Monthly Report for the month in which they take
effect.

**Corrections.** Published figures are not amended, except the current month's, which are updated
daily until month end, each version anchored. An error in a Monthly Report is corrected by a notice
stating the error, its cause and the corrected figures; an error in a data value, by an entry in the
log of corrections, with the original value retained. Every error is corrected, whatever its size,
and every correction is anchored.

**Incidents.** From Record Inception, every operational incident (outages, missed Valuation Points,
manual actions, defects, exchange downtime) is entered in the incident log when it occurs and
disclosed in that month's Monthly Report with its timing, its effect and its remediation, whether or
not it affected P&L. Manual actions are also entered in the intervention log.

## 6. Verification

**Anchoring.** Each daily commit includes a manifest containing the SHA-256 hash of every file for
that day, published and unpublished, including the exchange's responses the day was computed from,
together with an OpenTimestamps proof anchoring the manifest to the Bitcoin blockchain. Monthly
Reports and corrections are anchored in the same manner. A proof becomes final once the
corresponding Bitcoin transaction is confirmed, typically within several hours of the commit. The
documents are fixed by the pre-registration manifest and by the changelog (section 7).

**Public verification.** Any party may check the published files against the daily manifest, verify
the manifest's proof and review the workflow and its public execution logs. The verification
procedure is described in the repository guide.

**Verifier access.** Prospective allocators and independent verifiers may request, subject to a
non-disclosure agreement, a separate read-only API key to the Account, the exchange's transaction
statements, the unpublished daily account data and individual fills. An independent verifier may
also inspect the sealed configuration, solely to confirm it against the hash recorded in the
pre-registration manifest.

## 7. Governance

**Documents.** This Methodology, the Disclosure and the Risk Limits are subject to version control.
An amendment takes effect only once the new version has been hashed and anchored, and the amendment
and its rationale have been recorded in the changelog. Amendments apply prospectively, and prior
reports are not recalculated. The thresholds in the Risk Limits may not be amended while the Account
is in drawdown.

**Program versions.** The deployed version may change; the record attaches to the Program, not to a
version. Each version is entered in the version register with its deployment date, its class and the
hash of its sealed configuration, anchored before deployment. The sealed configuration fixes the
design in full, including any procedure that takes in new market data on a fixed schedule; its hash
covers the procedure, not the data, and running the procedure is not a change of version.

| Class | Scope | Treatment |
|---|---|---|
| Renewal | Retraining on more recent data within the existing design and rules | Announced in the version register at least seven days before deployment. Thresholds of the Risk Limits unchanged |
| Logic | A change to entry, exit, sizing or filtering rules, or to the model itself (how it is trained or built), within the strategy category stated in the Disclosure | As for Renewal, and deployed only once it has passed an acceptance test declared before its results were known. Disclosed at the level of strategy category, not of thesis or implementation |
| Program | A change to any term in section 1 other than Capital | This Methodology is amended and the change is announced before it takes effect. A change of Program closes the record and commences a new one |

A change of version resets no statistic: drawdown, days underwater and trailing measures run on the
Program's single continuous series. Renewals follow a schedule announced in advance and are neither
brought forward nor put off because of recent performance. A renewal that fails its pre-declared
acceptance test is not deployed, and this is disclosed in the Monthly Report. No version change is
made in response to losses.

**Account roster.** The record comprises all accounts recorded in the account register. Accounts are
added or removed only in accordance with the following procedure, which prevents a change of account
from excluding any period from the record:

1. The change is announced in the Monthly Report before it takes effect.
2. The account register is updated, hashed and anchored.
3. Capital is moved only by transfers recorded in the record on both sides.
4. Both accounts remain in the ledger throughout the transition.
5. An account is removed only once its balance is zero and fully reconciled.

Former accounts remain in the ledger permanently.

**Pre-registration.** Before Record Inception, the following are hashed and anchored on the Bitcoin
blockchain in the pre-registration manifest: the date of Record Inception, this Methodology, the
Disclosure, the Risk Limits, reout's internal risk policy (hash only), the account register, the
version register and the sealed configuration of the deployed strategy (hash only). Any subsequent
change to the methodology, the deployed configuration or the thresholds is therefore independently
detectable.