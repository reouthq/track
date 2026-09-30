# Program versions

Every deployed version of the program, in order. The sealed configuration of each version is
hashed and anchored before deployment (Methodology, section 7). The record is one series across
versions; no metric is reset on a change of version. Version 1.0 was deployed before record inception,
before this rule applied, and its sealed configuration is anchored before record inception.

A version number says the class of the change that made it. A renewal raises the last place
(1.0 to 1.0.1), a logic change the second (1.0 to 1.1), and a program change that keeps the mandate
the first (1.x to 2.0). A change of mandate is not a version: it closes the record and opens a new
one under a new name.

Renewals are scheduled monthly. Each month a renewal is trained and tested against an acceptance
test declared before its results are known. A renewal that passes is announced in this register and
deployed no earlier than seven days later; a month in which none passes keeps the version in effect,
and the Monthly Report says so. Logic changes are made when ready, under the same notice and test.

| # | Version | Deployed (UTC) | Class | Sealed configuration hash | Anchor |
|---|---|---|---|---|---|
| 1 | 1.0 | 2026-09-28 | initial | set at pre-registration | `attest/<date>-preregistration.md.ots` |
