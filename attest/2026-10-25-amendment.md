# Amendment manifest, 2026-10-25

**BTC-1** · record inception 2026-10-01.

This manifest records an amendment to the Methodology, sections 2 and 3, as entered in the
changelog, and the repository guide's description of the file it adds. Its SHA-256 hash is anchored
on the Bitcoin blockchain with OpenTimestamps; the proof is the `.ots` file of the same name. The
amendment takes effect once the proof is made. This file is not edited.

## 1. Documents fixed by this manifest

| Item | File | SHA-256 |
|---|---|---|
| public | `METHODOLOGY.md` | `82cddbbb71e2be22819bdafccbcdb591b0e808db7ea1ccfc11b96f2bbd8356b2` |
| public | `README.md` | `b4043f7a5b1fe2aeeeba3284eb34ccf1f0b1c0e8e3770608c303a25b77fce13d` |
| public | `CHANGELOG.md` | `43b57afc9b2723855864d021af50dfaa072fe53a9ceff390e8d4f436795f4097` |

## 2. The amendment

- Section 3: each external cash flow ends a sub-period of its valuation interval, and the daily
  return links the sub-periods. It applies to valuation intervals ending on or after 2026-10-22.
- Section 2: the Account is valued immediately before each external cash flow, from the preceding
  daily record, the income ledger and the fills before the flow, at the public mark price of the
  flow's minute.
- The interval ending 2026-10-22 was first published under the previous convention, which treated
  external cash flows as occurring at the start of the interval. Its values, and the index values
  after it, are corrected in the log of corrections, the published values retained there.

## 3. Verification

```
ots verify 2026-10-25-amendment.md.ots
sha256sum METHODOLOGY.md README.md CHANGELOG.md    # compare with section 1
```
