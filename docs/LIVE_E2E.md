# Live Studionet end-to-end run

The Direct Mode tests prove the contract logic against scripted model answers. They cannot prove how the contract
behaves on a real network: real validators, real consensus, value movement, rejection of value sent to non-payable
methods. `scripts/live_e2e.py` does that, and writes a report you can read and attach to a pull request.

## Run it in GitHub Codespaces

1. Open the repository in a Codespace. The dev container installs everything (`scripts/setup.sh`) the first time.
2. In the terminal:

   ```bash
   python scripts/run_report.py --fast
   ```

   `--fast` skips the time-gated phase (see below). Leave it out for the complete run.
3. Open `reports/primacy-report-<time>.md` (static checks and tests) and `reports/live-e2e-<time>.md` (the live run).

Everything runs from one command. `run_report.py` does, in order:

| Phase | What happens | Needs network |
|---|---|---|
| static | GenVM linter; the committed ABI is compared with the one generated from the contract | no |
| tests | The Direct Mode suite and the rehearsals of this script on a local simulator | only to download GenVM once |
| live | `live_e2e.py` against Studionet | yes |

Useful variants:

```bash
python scripts/run_report.py --no-live          # no network needed after setup
python scripts/run_report.py --skip-tests       # only static checks and the live run
python scripts/live_e2e.py --fast               # only the live run
python scripts/live_e2e.py --sim                # rehearse the live run offline (scripted model answers)
```

| Flag | Meaning |
|---|---|
| `--fast` | Skip the time-gated void/close phase. The run ends with the main bounty still open. |
| `--rpc URL` | Use another endpoint. Also `PRIMACY_RPC_URL`. Default `https://studio.genlayer.com/api`. |
| `--out DIR` | Report directory. Default `reports/`. |
| `--tx-timeout SECONDS` | How long to wait for each transaction to be decided. Default 900. |
| `--commit-window SECONDS` | Commit window of the main bounty. Default 1800; widened automatically on a slow network. |
| `--reveal-window SECONDS` | Reveal window of the main bounty. Default 900. |
| `--model-retries N` | Extra adjudication attempts when a model answer is inconclusive. Default 2. |
| `--sim` | Offline rehearsal on a local simulator. The report is labelled as a rehearsal. |

## How long it takes

The consensus rounds that call a language model dominate the run. When the model answers decisively, plan for
roughly 15 to 30 minutes with `--fast`, depending on validator speed. Every inconclusive answer adds the contract's own
retry cooldown (5 minutes, then 10), which the script waits out, so a hesitant model makes the run longer.
Without `--fast`, the script also waits out the main bounty's commit window (30 minutes by default, counted from the
bounty's creation) so that it can exercise voiding and closing; budget 35 to 60 minutes. These are estimates; the
report records the real duration. A run that is interrupted still writes a partial report.

## What the run does

| Scenario | Content |
|---|---|
| S01 Deployment | Deploys a fresh copy of the contract, checks `get_info`, checks the deployed ABI methods |
| S02 Ledger and access control | Deposits, zero deposit rejected, credit privacy, value sent to non-payable methods rejected, malformed inputs to views |
| S03 Bounty creation guards | Every boundary of reward, bond, slots, deadlines and scope; duplicate ids; insufficient credit |
| S04 Cancel and sponsor isolation | Cancel before any commit; a second sponsor can reuse an id; cross-sponsor calls cannot touch another bounty |
| S05 Main lifecycle | Commit, reveal, wrong hunter, tampered reveal, strict queue order, real validator adjudication of an original finding, a reworded duplicate, a verbatim copy (caught by the deterministic guard), an out-of-scope opinion, a prompt-injection attempt, a retry case, the per-hunter limit |
| S06 Time-gated paths | Early void and early close rejected; the hidden commitment passes its reveal deadline and can be voided by a stranger; the bond goes to the sponsor; close after commits ended; nothing is accepted after close |
| S07 Accounting and withdrawals | Rebuilds every account's expected credit from first principles and compares it with the contract, withdraws everything, checks no double withdrawal and an empty contract |

Throwaway accounts are created and funded for the run (`sim_fundAccount`); they hold only test GEN.

## Reading the report

The first table gives the **verdict**:

| Verdict | Meaning | Exit status |
|---|---|---|
| `PASS` | Every hard check held, nothing errored, and the run exercised the reward path and at least one duplicate or invalid settlement | 0 |
| `FAIL` | A hard check failed or a step errored | 1 |
| `INCOMPLETE` | The run could not start, was aborted, or left a coverage gap (for example the model never accepted any finding as distinct, so no reward was ever paid) | 2 |

Each step is one of two kinds:

* **Hard** checks are rules the contract enforces itself: access control, ordering, deadlines, bond and reward
  accounting, and the ledger reconciliation. They must hold on any network. A hard failure is a defect in the
  contract or in the script and fails the run.
* **Soft** checks depend on what a language model decided or on how the network handles value. A divergence is
  reported (`DIVERGED`) with what was expected and what happened, and never fails the run. Examples: the model
  accepted the reworded duplicate as distinct; the native balance of a withdrawing account did not rise by exactly
  the credit.

The **Adjudications** table lists, for each finding, what the model decided and why (`in_scope`, `actionable`,
`duplicate_of`, `confidence`). The **Transactions** table lists every transaction with its hash, whether it
succeeded and how consensus ended.

## Triage guide

| What you see | Likely cause | What to do |
|---|---|---|
| Verdict `INCOMPLETE`, "no finding was ever accepted as distinct" | The model answered inconclusively or all validators failed (model unavailable, quota) | Look at the Adjudications table for `inconclusive_assessment` or failure reasons. Re-run. If it persists, the network's model service is the issue, not the contract. |
| Verdict `INCOMPLETE`, "could not start" | The RPC is unreachable or the network refused to fund throwaway accounts | Check `--rpc`. For the second case provide eight pre-funded keys in `PRIMACY_ACCOUNT_KEYS` (see below). |
| A hard failure in S02–S05 | A contract rule did not hold | This is a real finding. The report gives expected and observed values and the transaction hash. Reproduce it in Direct Mode and fix the contract. |
| Ledger reconciliation fails | A settlement path moved the wrong amount, or a transaction's outcome was unknown | If the report says "ledger expectations are uncertain", a transaction timed out and its effect is unknown; the check is downgraded to soft. Otherwise this is a real defect. |
| Steps marked `ERROR` | A call raised something the script did not expect (timeout, unreadable receipt) | Re-run; if it repeats, inspect the transaction hash on the network's explorer. |
| Many soft divergences about model behavior | The model on this network judges differently from the expectations in the script | Read the rationales. The contract is behaving as designed if it handled the answers it received. Adjust the example texts in `TOPICS` if you want a stricter expectation. |
| Steps skipped with "the model path looks unavailable" | Two findings stayed undecided after every retry | The script stops waiting on further model calls and finishes the steps that do not need them. Re-run later. |

## Pre-funded accounts

If the network will not fund new accounts, the run stops with a message. Provide eight private keys of accounts
that each hold at least 0.01 GEN, in the order `sponsor, sponsor2, h1, h2, h3, h4, h5, caller`:

```bash
export PRIMACY_ACCOUNT_KEYS=0xKEY1,0xKEY2,0xKEY3,0xKEY4,0xKEY5,0xKEY6,0xKEY7,0xKEY8
python scripts/run_report.py --skip-tests --fast
```

Use test-only keys. Never put a key that holds real value in an environment variable that is logged, and never
commit one.

## A note on the rehearsal

`--sim` (and the tests under `tests/rehearsal/`) run this very script against a local simulator with scripted model
answers. They prove that the script, the report logic and the contract agree with each other. A report produced that
way says "Rehearsal run" at the top and is **not** a Studionet result.
