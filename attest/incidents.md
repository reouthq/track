# Operational incidents

Every operational incident from record inception, meaning an outage, a missed valuation point, a
manual action, a defect or exchange downtime, is entered here when it occurs, including incidents
with no effect on P&L, and listed in the monthly report for the month in which it occurred
(Methodology, section 5). Entries are not edited: a later finding about an incident is entered as a
new row that refers to it. Manual actions are also logged in the intervention log.

| Start (UTC) | End (UTC) | Kind | What happened | Effect on the record | Remedy |
|---|---|---|---|---|---|
| 2026-10-01 23:59:59 | 2026-10-09 10:11:24 | Defect | Software defect, present from before record inception: part of the live program's entry selection did not apply part of its tested specification. | More entries were taken than under the tested specification. With the defect in the next row, a reconstruction of 2026-09-28 to 2026-10-21 gives 16 trades under the specification against the 54 taken. Recorded P&L is as traded. | Corrected and deployed 2026-10-09 10:11:24. |
| 2026-10-01 23:59:59 | 2026-10-25 05:49:31 | Defect | Software defect, present from before record inception: in the same part of the live program, a setting differed from its tested specification. Exits of the account's positions were not affected. | As in the previous row. Alone, the reconstruction gives 19 trades against 16. Recorded P&L is as traded. | Corrected and deployed 2026-10-25 05:49:31; a check against the specification was added to the pre-deployment tests. |
| 2026-10-22 07:53:08 | 2026-10-22 08:04:03 | Manual action | The program was restarted with its capital set to a fixed amount below the account's wallet, to reduce the size of new positions, and restarted again with its capital taken from the wallet, as specified. | No position was opened while the setting was in effect. | Reverted 2026-10-22 08:04:03. Entered in the intervention log. |
