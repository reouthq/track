# Designated accounts

The track is the sum of the accounts listed here. Changes follow the Methodology, section 7, and are
announced in the monthly report before they happen. Accounts are never removed from history.

| # | Venue | Type | Owner | Account inception (UTC) | Status |
|---|---|---|---|---|---|
| 1 | Binance | USDT-margined futures account | reout (proprietary account) | 2026-09-28 17:50:45 | active |

The record begins at record inception, fixed in the pre-registration manifest.

Account identifiers are disclosed to verifiers under NDA (Methodology, section 6), not published.
What is published is a commitment to them, which the record checks on every run: the exchange is
asked which account the record's key belongs to, and nothing is produced unless the answer matches.

| # | Account commitment |
|---|---|
| 1 | `52ab3bb4bd1e5997929381ac579f8f5bdcb7312f8ab7e10f4d79241250c9bb0c` |

The commitment is the SHA-256 of `salt:uid:alias`, where `uid` is the exchange's identifier of the
user, `alias` the exchange's alias of the account's USDT futures balance, and `salt` a secret held
with the record's other secrets. The identifiers are short enough to try every value, so the salt is
what keeps them private; it is given, with the identifiers, to verifiers under NDA, who can then
compute the commitment themselves.
