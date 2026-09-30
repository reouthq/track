# Pre-registration manifest, 2026-09-30

**BTC-1** · account inception 2026-09-28 · record inception 2026-10-01 · own capital.

**Record inception: the end of 2026-10-01 UTC**, the first valuation point of the record. The period
from account inception to record inception is the pilot, which is not part of the record
(Methodology, section 1).

This manifest records, before record inception, the documents that define the strategy's
scope, the method of measurement and the review thresholds. Its
SHA-256 hash is anchored on the Bitcoin blockchain with OpenTimestamps; the proof is the `.ots` file
of the same name. Any later change to an item listed here is made by issuing a new, dated and
anchored manifest. This file is not edited.

## 1. Documents fixed by this manifest

| Item | File | SHA-256 |
|---|---|---|
| public | `README.md` | `11467c51ca192c8c3c3cecb0e898d79df868c0be1973e8598d209b17b5b3739a` |
| public | `METHODOLOGY.md` | `2a23b20c5f5fbef5ac05a32038a76d3823db8407e430b20adabb019031ddd19e` |
| public | `DISCLOSURE.md` | `51c5077bf4cb54d95b8a756caf7881bd92b572cc59c3636510bbfe97e2538719` |
| public | `RISK_LIMITS.md` | `fb09131ad5c399b4bacc5456484b30fa6f6bab00c78480f465adb2672cd3e3ac` |
| public | `CHANGELOG.md` | `7adbae74e69d3bd8a2113a108c5c1c19debfafc0385eb45be79c174db7bfbede` |
| public | `attest/accounts.md` | `8f2c295470fa74c8be5c2613ee27374f83921fdefa3ebd4f9426d53e247efe09` |
| public | `attest/versions.md` | `1e5170858bbe85b332197693ac92b5a078f255ac7bd2d234f517d39fc3c9d146` |
| sealed | `2026-09-30-preregistration.sealed.md` (deployed parameters, model checksums and the hashes of internal documents; not public, available to verifiers under NDA) | `7f5bf50d89803afc06b9c52e50e9b3c35628ada684935dd1f375134c8943bf35` |
| internal (hash only) | internal risk policy | `95959e94859d8837474539d07ae070331af1e07813c18b5c5479e57299220255` |
| internal (hash only) | deployed configuration | `9b107d42ae4212c08a26011ef24b193c3f8cf57b50eb0a4062036c4901ed7ebe` |
| internal (hash only) | model file checksums | `4b265384c0ddb34d56076f991271be92d9722067459e12dc76b1bc4f9cc3d488` |
| internal (hash only) | live entry point | `b796a10b35d6e294117ec013304b0dc2907213b112b2309e6a4455d886718196` |

## 2. Internal files

- Deployed configuration: the complete configuration of the deployed strategy and the procedure
  for reproducing its backtest. Fixed here so that the deployed configuration is not open to later
  revision.
- Internal risk policy: the unabridged document of which the public Risk Limits are the excerpt.
- Model file checksums: the hashes of the deployed model files. The live process does not start if
  any hash differs.
- Live entry point: the source file whose deployed parameter line is reproduced verbatim in the
  sealed manifest.

## 3. Account

One USDT-margined futures account, listed in the account register, funded with reout's proprietary
capital, account inception 2026-09-28 17:50:45 UTC. The account identifier and the size of the account are
available under NDA. Roster and transition procedure: the account register and the Methodology, section 7.

## 4. Verification

```
ots verify 2026-09-30-preregistration.md.ots
sha256sum METHODOLOGY.md DISCLOSURE.md RISK_LIMITS.md    # compare with section 1
```

The `.ots` proof for the sealed manifest is also published. It establishes that the sealed file
existed at this date without disclosing its contents.
