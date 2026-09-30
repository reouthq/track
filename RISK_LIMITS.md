# Risk Limits

These Risk Limits apply to the Program from Record Inception (Methodology, section 1) and are
anchored beforehand in the pre-registration manifest. This document is the public extract of reout's
internal risk policy, the hash of which is included in the same manifest. The thresholds may not be
amended while the Account is in drawdown. Each Monthly Report states the Account's position against
them.

---

## 1. Scope and principles

Position-level exits, including stop-loss, take-profit and time limits, form part of the strategy
and are applied systematically to every trade. This document governs the Account as a whole.

Performance thresholds are alerts and triggers for review, not automatic stops. A stop on P&L alone
cannot tell an ordinary losing period from a deterioration of the strategy (section 2) and, once
triggered, forgoes any subsequent recovery; tail risk is managed through position sizing instead
(Methodology, section 1).

Operational halts are reserved for system faults, meaning evidence that the system is not operating as
designed, whose signals are specific and have a defined remedy (section 5). Whether the strategy has
decayed cannot be told from P&L alone within a useful time, so it is judged through the reviews of
section 4 and the scheduled renewals of the Program (Methodology, section 7).

## 2. Pre-declared ranges

The thresholds in section 3 define the ranges within which the Program is expected to operate. They
were derived before Record Inception from a backtest of the Program as deployed, including all of
its trading rules. They describe the adverse outcomes the Program is expected to withstand and are
not a forecast of performance. Results within these ranges are consistent with normal operation.
Results beyond them are reviewed in accordance with section 4.

## 3. Thresholds

| Metric | Review (alert) | Risk reduction (half-size entries) | Program review (full re-validation) |
|---|---|---|---|
| Account drawdown | −30% | −37% | −46% |
| Trailing 30-day return | −21% | −25% | −31% |
| Trailing 65-day return | −20% | −27% | −34% |
| Days underwater | 187 | 199 | 249 |

All thresholds apply to the Account as traded, with notional exposure of up to three times equity.
Account drawdown is the current drawdown, and days underwater is the number of days since the most
recent high, both measured at daily Valuation Points on the index of daily time-weighted returns, so
that external cash flows are not treated as gains or losses. The trailing 30-day and 65-day returns
are time-weighted returns over the respective trailing windows, measured on the same Valuation
Points (Methodology, sections 3 and 4). The thresholds are assessed once daily, at the Valuation
Point.

**At one times exposure.** For comparison with unlevered programs, the same levels are stated below
for the leverage-normalized series (Methodology, section 3), which divides the Account's daily
returns by three, its maximum notional multiple. These levels were derived from the same backtest by
the same rule and are for reference only: the thresholds above are the ones assessed.

| Metric | Review | Risk reduction | Program review |
|---|---|---|---|
| Drawdown at one times | −11% | −14% | −17% |
| Trailing 30-day return at one times | −7% | −9% | −11% |
| Trailing 65-day return at one times | −7% | −10% | −12% |
| Days underwater at one times | 169 | 189 | 236 |

## 4. Review and outcomes

**Review.** Promptly, and in any case within two business days of a threshold being reached, reout
(i) compares live results with expected behavior, (ii) assesses the prevailing market regime and
(iii) verifies the integrity of data and infrastructure. The findings are recorded in the Monthly
Report. Trading is suspended only if a system fault under section 5 is confirmed.

**Risk reduction.** In addition to the review, new positions may be sized at one half of their normal
size while the Account's drawdown exceeds the risk-reduction threshold. Use of this provision is optional and is
recorded in the intervention log (Methodology, section 1). Existing positions are not closed early on
account of P&L.

**Program review.** A full re-validation of the Program, concluding in one of three outcomes announced
in the Monthly Report: continuation unchanged, continuation at reduced size, or retirement of the
Program, which closes the record (Methodology, section 7). A decision to retire is based on the
findings of the review and not on the level of P&L that triggered it.

## 5. Operational halts and venue failure

The system suspends the opening of new positions, while continuing to manage existing positions in
accordance with its rules, upon evidence that it is not operating as designed: a required market data
feed is stale, its record of positions disagrees with the exchange, or a required component fails to
load. Where a check at start-up fails, the system does not start, and open positions remain subject
to the exit orders held at the exchange until it is restarted. The specific signals and their
thresholds are internal. A manual halt is also available. It blocks new entries only and does not
close positions.

**Venue failure.** The Account is held at a single trading venue (Methodology, section 1). If the
venue suspends withdrawals of the base currency for more than 24 hours other than for announced
maintenance, becomes subject to insolvency proceedings or to a regulatory order to cease operating,
or does not complete a small test withdrawal within 24 hours, new entries are suspended, every open
position is closed at market and the Account's assets are withdrawn from the venue as far as it
permits. These steps are taken by the operator under this rule, are recorded in the intervention
log and the incident log, and are not a discretionary action (section 6). The record continues
across the event; trading resumes only in accordance with the Methodology, section 7.

## 6. Prohibited actions

The following actions are prohibited:

- Amending a threshold in place, or treating a current episode as an exception.
- Raising the Program's maximum notional exposure (Methodology, section 1) while the Account is in
  drawdown. Changes in exposure made by the system's own sizing rules, within that maximum, are not
  affected.
- Closing existing positions on a discretionary basis. The venue failure procedure in section 5
  is not discretionary.
- Suspending the strategy on P&L alone, contrary to section 1.
- Changing the deployed version in response to a loss, or resetting any metric in this document upon
  a change of version (Methodology, section 7).
