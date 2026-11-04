# Amendment manifest, 2026-11-04

**BTC-1** · record inception 2026-10-01.

This manifest records an amendment to the Disclosure, sections 2 and 3, as entered in the
changelog. Its SHA-256 hash is anchored on the Bitcoin blockchain with OpenTimestamps; the proof is
the `.ots` file of the same name. The amendment takes effect once the proof is made. This file is
not edited.

## 1. Documents fixed by this manifest

| Item | File | SHA-256 |
|---|---|---|
| public | `DISCLOSURE.md` | `f9ed907478a37ae43fc85d72a0de89f4725f81d592245233ced9612b577967ee` |
| public | `CHANGELOG.md` | `5173c5f87c2bfcd492e0eee8a1b4b3c6acbbe9ff9e05cf9cf31fecdb6c84ada6` |

## 2. The amendment

- Section 2: research notes are published: findings on research practice and on markets, stated so
  as not to describe the thesis or the implementation. The thesis and implementation behind any
  finding, experimental results that would identify a program's inputs, models, parameters, gates
  or a candidate change, and development data remain unpublished.
- Section 3: research notes may report findings from reout's research, in a form that discloses
  neither the inputs, models, parameters, gates or execution rules of a program, nor a candidate
  change to one.
- Nothing in the Methodology or the Risk Limits changes, and no published figure is affected.

## 3. Verification

```
ots verify 2026-11-04-amendment.md.ots
sha256sum DISCLOSURE.md CHANGELOG.md    # compare with section 1
```
