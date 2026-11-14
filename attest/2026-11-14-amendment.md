# Amendment manifest, 2026-11-14

**BTC-1** · record inception 2026-10-01.

This manifest records an editorial amendment to the Methodology, sections 1, 2, 5 and 7, as entered
in the changelog. Its SHA-256 hash is anchored on the Bitcoin blockchain with OpenTimestamps; the
proof is the `.ots` file of the same name. The amendment takes effect once the proof is made. This
file is not edited.

## 1. Documents fixed by this manifest

| Item | File | SHA-256 |
|---|---|---|
| public | `METHODOLOGY.md` | `673034bfe7d059370bb6f3409cc4d1860501544fe91082ff7b5d2d4c903b8a4a` |
| public | `CHANGELOG.md` | `8b0c661f2e04080003b03b8f95baee76815f960fd3e56d0fa1779a30c0807b0b` |

## 2. The amendment

- Section 1, Leverage: exposure is stated as a multiple of current equity, "so that returns
  compound", in place of "compounded continuously", which could be read as continuous compounding
  of returns. The term is unchanged in substance.
- Section 2, value at a cash flow: the balance and positions of the preceding daily record are
  "adjusted for" the income ledger entries and "updated for" the fills before the flow, in place of
  "moved by", and the mark price is that of "the minute in which the flow falls".
- Section 5: the Monthly Report is published on the third calendar day "of the following month";
  its descriptions are "written by hand rather than generated" and "written as the events occur".
- Section 7: "the Methodology" is capitalized as the defined term.
- No calculation, threshold or term changes, and no published figure is affected.

## 3. Verification

```
ots verify 2026-11-14-amendment.md.ots
sha256sum METHODOLOGY.md CHANGELOG.md    # compare with section 1
```
