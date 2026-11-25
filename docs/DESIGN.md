# Primacy design notes

This document explains why the contract behaves as it does, which invariants it keeps, and where its limits are.
The source of truth is `contracts/primacy.py`; every number below is a constant defined at the top of that file.

## 1. Money model

Primacy never moves money between wallets while settling. It keeps an internal ledger:

* `credits[address]`: GEN that belongs to an address and is free to use.
* `total_credits`: the sum of every entry in `credits`.
* `total_locked`: GEN held for open bounties (unpaid reward escrow) and for pending bonds.

Value enters only through `deposit_credit()` and leaves only through `withdraw_credit()`, which sends exactly the
caller's own credit to the caller after the credit has been deducted. Every other step (creating a bounty, a
commit, a reward, a refund, a forfeit) is an arithmetic move between `credits` and `total_locked`.

Consequences:

* There is no settlement step that can send value to several recipients, so there is nothing to strand if one
  recipient is a contract that rejects the transfer.
* Withdrawal is pull-based. A hunter cannot be blocked from receiving a reward by another party.
* `get_accounting()` exposes `accounted_liabilities = total_credits + total_locked` next to the real contract
  balance, so anyone can check `solvent`.

### Invariants

These are checked after every step of the fuzz suite and at the end of the live run, using only public views.

1. The credits of all accounts add up to `total_credits`.
2. `total_locked` equals the escrow of open bounties plus the bonds of findings in `committed` or `revealed`.
3. An open bounty's escrow equals `(slots − heads) × reward`. A closed or cancelled bounty has zero escrow.
4. `heads` equals the number of `distinct` findings and never exceeds `slots`.
5. A finding is `distinct` if and only if it was paid exactly `reward_wei`.
6. A finding that is no longer pending holds no bond, and its bond state is `refunded` or `forfeited_to_sponsor`.
7. Every finding before the cursor is final. The finding at the cursor, if any, is `committed` or `revealed`.
8. `accounted_liabilities` equals everything ever deposited minus everything ever withdrawn.

## 2. State machines

### Bounty

```
            create_bounty
                 │
              ┌──▼──┐   cancel_bounty (no commits yet)   ┌───────────┐
              │ open ├───────────────────────────────────▶ cancelled │
              └──┬───┘                                     └───────────┘
   all slots     │  close_bounty after commit_by with nothing pending,
   filled        │  or after review_by
        ┌────────▼───┐
        │   closed   │
        └────────────┘
```

Closing releases leftover escrow to the sponsor and settles whatever is still pending:

| Finding at close | Result | Bond |
|---|---|---|
| `committed`, reveal window already over | `void` | forfeited to sponsor |
| `committed`, still inside its reveal window, closed because slots filled | `late` | refunded |
| `revealed` and closed because slots filled | `late` | refunded |
| `revealed` and closed for any other reason | `unresolved` | refunded |

### Finding

```
committed ──reveal──▶ revealed ──adjudicate──▶ distinct | duplicate | invalid | unresolved
    │                    │
    └─void_unrevealed──▶ void       (any pending finding may also end as late / unresolved when the bounty closes)
```

## 3. Deadlines

For a bounty created at time `T` with commit cutoff `C`, reveal window `W` and review deadline `R`:

| Rule | Value |
|---|---|
| `C` | between `T + 10 min` and `T + 60 d` |
| `W` | between 5 minutes and 7 days |
| `R` | between `C + W + 1 d` and `C + W + 90 d` |
| A commit is accepted | while `now < C` and the bounty is open |
| A finding committed at `t` may be revealed | while `now < t + W` |
| A commitment may be voided by anyone | once `now ≥ t + W` |
| `adjudicate` works | while the bounty is open and `now < R` |
| `close_bounty` works | after `R`, or after `C` when no finding is pending |

The review tail of at least one day guarantees that every reveal window has long elapsed before the review
deadline, so a close after `R` never discards a finding that could still have been revealed.

Time comes from the transaction timestamp, which all validators agree on; the contract never reads a clock of
its own.

## 4. Commit–reveal

The commitment is

```
SHA-256( field("primacy/v1") ‖ field(bounty_key) ‖ field(hunter) ‖ field(salt) ‖ field(title) ‖ field(body) )
field(x) = <byte length of x in UTF-8> ":" x ";"
```

* `bounty_key` is `<sponsor lowercase hex>:<bounty id>`, so a commitment cannot be replayed in another bounty.
* `hunter` is the committing address, so a copycat cannot reuse an observed commitment, and a reveal by anyone but
  the committer is refused.
* The length prefix makes the field boundaries unambiguous: moving characters from the title to the body changes the
  digest.
* The salt (16–64 characters of `[A-Za-z0-9_-]`) stops anyone guessing a short or predictable finding from its hash.
* Revealed text is *validated, never rewritten*. Leading or trailing whitespace, control characters, bidirectional
  and zero-width characters and surrogates are refused outright. This closes the class of attacks where the text a
  validator sees differs from the text a human sees. `scripts/primacy_commit.py` applies the same rules so an honest
  hunter cannot commit to text that could never be revealed.

Commit order is priority. Because `adjudicate` only ever looks at the earliest undecided finding, a later finding
cannot be accepted before an earlier one, and a later finding is always compared against everything accepted before
it.

## 5. Adjudication

### The queue

`bounty.cursor` points at the earliest finding that is not final. `adjudicate` operates on exactly that finding:

* `committed` (not yet revealed): refuse, "awaits reveal or voiding". Anyone can call `void_unrevealed` once the
  reveal window has passed. This is what prevents one hunter who never reveals from blocking everyone else.
* `revealed`: judge it.
* Otherwise the cursor has already moved on.

### Deterministic copy guard

Before any model call, the candidate is compared with every accepted finding using Jaccard similarity over 3-word
shingles of lowercased word characters. A similarity of at least 90 %, with at least 12 words on both sides, is a
`duplicate` of that finding with no model involved. This catches the cheap attack (resubmit the same text with
a changed title or punctuation) without spending a consensus round, and it cannot be talked out of its answer.

### Prompt construction

The scope, the accepted findings and the candidate are all untrusted. They are placed between `BEGIN_…`/`END_…`
markers carrying a fence of the form `FENCE-<20 hex>`, which is derived from a hash of every untrusted byte. Text
cannot contain its own fence, because the fence depends on the text, so it cannot forge a closing marker. If a
collision did occur, the prompt is refused and the attempt counts as an operational failure. The instructions
repeat after the data, and say that nothing between the markers is an instruction.

The model must return one JSON object. The contract accepts only: `in_scope` and `actionable` in
`{yes, no, unclear}`, `duplicate_of` in `{none, unclear, H1…Hn}` (labels of accepted findings), an integer
`confidence` 0–100, and an optional short rationale. Anything else is a failure, not a guess.

### Decision table

See the README. The important design choice is that **uncertainty never pays and never punishes**. Low confidence,
`unclear` in any field, or a mix of "yes" and "unclear" produces an inconclusive result. Inconclusive results are
retried; they do not forfeit a bond and do not award a reward.

### Equivalence principle

`adjudicate` uses a custom leader/validator pair (`gl.vm.run_nondet_unsafe`). The leader runs the prompt. Each
validator runs it again independently and compares *bounded classification fields* with the leader's answer:

| Leader's outcome | Validator agrees when |
|---|---|
| `distinct` | its own outcome is `distinct` |
| `duplicate` | its own outcome is `duplicate` **of the same accepted finding** (who is paid depends on it) |
| `invalid` | its own outcome is `invalid` and it names at least one "no" in common with the leader (`in_scope` or `actionable`); a bond is at stake |
| `inconclusive` | its own outcome is `inconclusive` |
| failure | it also failed (a failed observation never authorizes anything, so the diagnostics may differ) |

Prose (the rationale) is never compared. A leader answer that is malformed, or whose declared outcome does not match
what the table derives from its own classification, is rejected by every validator. The leader and validator
functions read no storage and no message data; they work from an immutable snapshot taken before the call.

### Failure budgets

Each finding tracks `attempts` (inconclusive answers) and `failures` (operational problems: malformed output, no
consensus, model unavailable).

* After every non-decision a cooldown starts: 5 minutes, doubling per attempt, capped at 2 hours.
* 3 inconclusive answers, or 6 failures, resolve the finding as `unresolved` with the bond refunded.

Cooldowns bound how often a stuck finding can burn consensus rounds, and the budgets guarantee the queue moves on.

## 6. Hostile participants

| Attacker | Attempt | Defence |
|---|---|---|
| Front-runner | Watch a reveal, resubmit it first | Impossible: reveals only happen after commits; the commit fixes priority and the commitment is bound to the committer's address |
| Copycat | Copy an accepted finding with cosmetic changes | Deterministic copy guard, then model duplicate detection |
| Author of a finding | Put instructions in the finding text | Fenced untrusted text; instructions in data are ignored; any "unclear" blocks payment |
| Author of a finding | Forge the fence marker | The fence is derived from the text; collisions abort the prompt |
| Author of a finding | Unicode tricks (bidi, zero-width, control characters) | Refused at reveal, never normalized |
| Hunter | Never reveal, to stall the queue | Anyone can void after the reveal window; the bond goes to the sponsor |
| Hunter | Reveal someone else's commitment | Reveal is limited to the committing address |
| Hunter | Reveal different text | Hash mismatch |
| Hunter | Re-commit the same finding many times | 4 findings per hunter per bounty; each locks a bond |
| Sponsor | Submit findings to their own bounty | Refused |
| Sponsor | Reclaim the reward after hunters committed | `cancel_bounty` works only while no finding exists |
| Anyone | Call methods with value attached | Non-deposit methods refuse value |
| Anyone | Call `adjudicate` repeatedly | Cooldown and attempt budget per finding |
| Validator | Disagree with the leader about who is paid | Duplicate agreement requires the same label |
| Model | Return malformed, oversized or out-of-vocabulary output | Normalizer rejects it; counts as a failure |
| Model | Claim an amount or recipient | Output has no such field; payments are derived by contract code |

## 7. Known limitations

These are real. None of them lets anyone take funds that are not theirs; they are about fairness, liveness and
cost.

1. **Queue stuffing by many addresses.** The cap of 32 findings per bounty is shared and each hunter is capped
   at 4, but one actor with several addresses can fill the queue. The deterrent is the bond: each finding locks
   one, and an invalid finding forfeits it. **Set the bond to 5–10 % of the reward or more** and keep the commit
   window short. A bounty where the bond is tiny relative to the reward invites this.
2. **Back-off stalls.** Adjudication is strictly ordered. A finding whose model answers keep failing holds the
   queue until its budget is spent. Because the cooldown doubles, six failed attempts need waits of about
   5 + 10 + 20 + 40 + 80 minutes, roughly two and a half hours. This is the price of an ordering guarantee that
   nobody can bypass.
3. **The sponsor controls the scope.** Validators judge against the sponsor's text. A sponsor can write a scope
   that excludes everything, or a vague one that invites disputes. Hunters should read the scope first. There is no
   appeal mechanism.
4. **Head-text bias.** A new finding is compared only with accepted (`distinct`) findings, using the text of the
   first accepted report of each defect. It is not compared with earlier duplicates or rejected findings. An
   unusually terse first report of a defect can make later, better-written reports of the same defect look distinct.
5. **No truth verification.** The model sees text only. It can say that a finding is specific and in scope; it cannot
   tell whether the documentation really contains the error. The sponsor is the party who checks the facts.
6. **Plain transfers are stranded.** GEN sent to the contract address without calling `deposit_credit()` is not
   credited to anyone and cannot be recovered. `get_accounting().unallocated_balance` shows any such amount.
7. **Findings are public.** Revealed text is on chain permanently.
8. **Direct Mode is not the network.** The Direct Mode test environment does not move value, does not roll back
   storage when a call fails, and does not enforce `payable`. The contract is written so that every state change
   happens after all of its checks, and the live end-to-end run covers value movement and non-payable rejection on
   a real network.

## 8. Choices worth knowing about

* **Why a credit ledger rather than direct transfers?** One-recipient withdrawals are the only place value leaves.
  Reward distribution therefore cannot fail halfway.
* **Why strict order instead of "best finding wins"?** Priority has to be something an attacker cannot influence
  after the fact. The commit position is fixed on chain before any text is visible.
* **Why a deterministic guard before the model?** It is free, instant, and immune to prompt manipulation for the
  most common abuse.
* **Why compare only bounded fields in consensus?** Models phrase rationales differently every time. Comparing prose
  would make honest validators disagree constantly, while comparing the decision, and the identity of the duplicated
  finding when that determines a payment, loses nothing that affects money.
* **Why does `invalid` need a shared defect?** It is the only outcome that confiscates a bond from a hunter on a
  single judgement. Two validators both saying "invalid" because of different reasons is not enough agreement for that.
