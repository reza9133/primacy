# Primacy report 20261124T154230Z

| Phase | Result | Detail |
|---|---|---|
| Static checks | PASS | linter and ABI drift |
| Automated tests | PASS | 422 tests, 0 failed, 0 skipped, 73.5s |
| Live Studionet run | INCOMPLETE | hard passed 3, hard failed 0, model aligned 0, model diverged 0, 8.6s |

## Static checks

- **PASS** genvm-lint check contracts/primacy.py
- **PASS** artifacts/primacy.abi.json matches the contract

## Automated tests

Of the 422 tests, 55 are tagged adversarial, 41 are seeded fuzz runs and 6 rehearse the live script on a local simulator.

| File | Tests | Failed | Skipped | Seconds |
|---|---|---|---|---|
| test_adjudication | 115 | 0 | 0 | 4.1 |
| test_adversarial | 22 | 0 | 0 | 1.0 |
| test_commit_reveal | 65 | 0 | 0 | 1.9 |
| test_creation | 56 | 0 | 0 | 1.8 |
| test_fuzz | 41 | 0 | 0 | 16.3 |
| test_ledger | 19 | 0 | 0 | 0.5 |
| test_lifecycle | 15 | 0 | 0 | 0.4 |
| test_live_script | 6 | 0 | 0 | 38.1 |
| test_offchain_tool | 31 | 0 | 0 | 0.3 |
| test_report_logic | 6 | 0 | 0 | 0.0 |
| test_smoke | 1 | 0 | 0 | 0.0 |
| test_validators | 45 | 0 | 0 | 2.0 |

## Live Studionet run

Full report: `reports/live-e2e-20261124T154452Z.md`

- Contract: `not deployed`
- Verdict: **INCOMPLETE** (deployment failed: GenLayerError: Transaction failed)
