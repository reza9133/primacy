# Primacy report 20261124T184835Z

| Phase | Result | Detail |
|---|---|---|
| Static checks | PASS | linter and ABI drift |
| Automated tests | not run | |
| Live Studionet run | PASS | hard passed 161, hard failed 0, model aligned 10, model diverged 9, 2519.5s |

## Static checks

- **PASS** genvm-lint check contracts/primacy.py
- **PASS** artifacts/primacy.abi.json matches the contract

## Live Studionet run

Full report: `reports/live-e2e-20261124T184838Z.md`

- Contract: `0xf49Fca785788a2a3881c593F33B2E20113FD99e1`
- Verdict: **PASS**

Model or environment expectations that diverged (informational):
- S02 Ledger and access control: native balance of the sender fell by the deposit (expected 1000000000000000, observed 101000000000010352)
- S07 Accounting and withdrawals: sponsor's native balance rose by the credit (expected 660000000000000, observed -756259200010352)
- S07 Accounting and withdrawals: sponsor2's native balance rose by the credit (expected 200000000000000, observed -756259200010352)
- S07 Accounting and withdrawals: h1's native balance rose by the credit (expected 240000000000000, observed -756259200010352)
- S07 Accounting and withdrawals: h2's native balance rose by the credit (expected 60000000000000, observed -756259200010352)
- S07 Accounting and withdrawals: h3's native balance rose by the credit (expected 260000000000000, observed -756259200010352)
- S07 Accounting and withdrawals: h4's native balance rose by the credit (expected 20000000000000, observed -756259200010352)
- S07 Accounting and withdrawals: h5's native balance rose by the credit (expected 60000000000000, observed -756259200010352)
- S07 Accounting and withdrawals: Ledger reconciliation (after withdrawals): contract balance equals liabilities (expected 0, observed 60000000000000)

Model verdicts:

| Finding | Status | In scope | Actionable | Duplicate of | Confidence |
|---|---|---|---|---|---|
| 0 (pagination) | distinct | yes | yes | -1 | 90 |
| 1 (pagination_reworded) | duplicate | yes | yes | 0 | 100 |
| 2 (retry) | distinct | yes | yes | -1 | 100 |
| 3 (opinion) | invalid | no | no | -1 | 98 |
| 4 (copy) | duplicate | yes | yes | 0 | 100 |
| 5 (injection) | invalid | no | no | -1 | 100 |
