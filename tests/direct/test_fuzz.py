"""Seeded random operation sequences checked against two independent oracles.

Oracle 1 is ``Harness.check``: structural and conservation invariants recomputed from public views.
Oracle 2 is ``reconcile`` below: every account's credit is re-derived from nothing but its own deposits,
withdrawals, funding, bonds and the final public status of every finding.

Every call may legitimately be rejected. A rejection must be a deliberate contract error (never an
unexpected crash) and must leave no trace in any observable state.
"""

import json
import random
from collections import Counter

import pytest
from gltest.direct.loader import create_address

from tests.direct.helpers import (
    BOND, DAY, DISTINCT, HOUR, NOW_TS, REWARD, SCOPE, addr, duplicate, verdict,
)

pytestmark = pytest.mark.fuzz

SEEDS = list(range(40))
STEPS = 90
TERMINAL = {"distinct", "duplicate", "invalid", "unresolved", "void", "late"}
STICKY_FIELDS = ("status", "reward_wei", "bond_state", "duplicate_of", "decided_at", "hunter", "commitment",
                 "title", "body")
VOCAB = (
    "pagination limit sample header token retry sleep timeout default client server example chapter table "
    "reference endpoint response request cache index schema column value format widget handler parser "
    "warning deprecated option flag batch stream buffer cursor offset window shard replica quorum lease"
).split()
VERDICTS = [
    DISTINCT, DISTINCT, DISTINCT,
    duplicate("H1"), duplicate("H2"), duplicate("H3"), duplicate("H9"),
    verdict(in_scope="no"), verdict(actionable="no"), verdict(in_scope="unclear"),
    verdict(confidence=40), verdict(duplicate_of="unclear"),
    "not an object", {"unrelated": True}, [], None,
]
OUTCOMES = Counter()


class World:
    def __init__(self, h, rng):
        self.h = h
        self.rng = rng
        self.now = NOW_TS
        self.dep = Counter()
        self.wd = Counter()
        self.funded = Counter()
        self.bonds = Counter()
        self.pending = []          # committed, not yet revealed: (sponsor, bounty_id, sub)
        self.terminal = {}         # (sponsor_hex, bounty_id, index) -> frozen finding
        self.counter = 0
        self.texts = []
        self.sponsors = [h.alice, h.bob]
        self.actors = list(h.people)
        self.ids = ["F1", "F2", "F3"]

    # ---- observation ---------------------------------------------------

    def fingerprint(self):
        h = self.h
        return json.dumps([
            h.c.get_accounting(),
            [[h.bounty(s, b), h.findings(s, b)] for s, b in h.bounties],
            [h.credit(p) for p in h.people],
        ], sort_keys=True, default=str)

    def attempt(self, label, fn):
        before = self.fingerprint()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - classified right below
            assert type(exc).__name__ == "UserError" and "[EXPECTED]" in str(exc), f"{label}: unexpected crash {exc!r}"
            assert self.fingerprint() == before, f"{label}: a rejected call changed observable state"
            OUTCOMES[label + ":rejected"] += 1
            return False, None
        OUTCOMES[label + ":ok"] += 1
        return True, result

    # ---- invariants ----------------------------------------------------

    def reconcile(self):
        h = self.h
        expected = Counter()
        for who in h.people:
            key = addr(who)
            expected[key] += self.dep[key] - self.wd[key] - self.funded[key] - self.bonds[key]
        for sponsor, bounty_id in h.bounties:
            bounty = h.bounty(sponsor, bounty_id)
            sponsor_key = addr(sponsor)
            if bounty["status"] != "open":
                expected[sponsor_key] += (bounty["slots"] - bounty["heads"]) * bounty["reward_wei"]
            for f in h.findings(sponsor, bounty_id):
                hunter_key = f["hunter"].lower()
                if f["status"] == "distinct":
                    expected[hunter_key] += bounty["reward_wei"] + bounty["bond_wei"]
                elif f["bond_state"] == "refunded":
                    expected[hunter_key] += bounty["bond_wei"]
                elif f["bond_state"] == "forfeited_to_sponsor":
                    expected[sponsor_key] += bounty["bond_wei"]
        for who in h.people:
            assert h.credit(who) == expected[addr(who)], f"credit of {addr(who)} does not reconcile"

    def check_terminal_findings_are_immutable(self):
        h = self.h
        for sponsor, bounty_id in h.bounties:
            for f in h.findings(sponsor, bounty_id):
                key = (addr(sponsor), bounty_id, f["index"])
                frozen = {name: f[name] for name in STICKY_FIELDS}
                if key in self.terminal:
                    assert self.terminal[key] == frozen, f"terminal finding {key} changed"
                elif f["status"] in TERMINAL:
                    self.terminal[key] = frozen

    def verify(self):
        self.h.check()
        self.reconcile()
        self.check_terminal_findings_are_immutable()

    # ---- operations ----------------------------------------------------

    def text(self):
        self.counter += 1
        if self.texts and self.rng.random() < 0.15:
            return self.rng.choice(self.texts)  # a verbatim re-report
        words = [self.rng.choice(VOCAB) for _ in range(self.rng.choice([4, 8, 14, 20, 35]))]
        pair = (f"Finding {self.counter} {words[0]}", " ".join(words))
        self.texts.append(pair)
        return pair

    def op_deposit(self):
        who = self.rng.choice(self.actors)
        amount = self.rng.choice([1, BOND, 2 * BOND, REWARD, 3 * REWARD])
        self.h.deposit(who, amount)
        self.dep[addr(who)] += amount
        OUTCOMES["deposit:ok"] += 1

    def op_withdraw(self):
        who = self.rng.choice(self.actors)
        ok, amount = self.attempt("withdraw", lambda: self.h.withdraw(who))
        if ok:
            self.wd[addr(who)] += amount

    def op_create(self):
        h, rng = self.h, self.rng
        sponsor = rng.choice(self.sponsors)
        bounty_id = rng.choice(self.ids)
        reward = rng.choice([10**14, REWARD, 3 * REWARD])
        bond = rng.choice([10**12, BOND, 10**14])
        slots = rng.randint(1, 4)
        commit_by = self.now + rng.choice([700, HOUR, 2 * HOUR, 5 * HOUR])
        reveal_window = rng.choice([400, HOUR, 2 * HOUR])
        review_by = commit_by + reveal_window + rng.choice([DAY, DAY + 1, 2 * DAY])
        if rng.random() < 0.85:
            h.deposit(sponsor, reward * slots)
            self.dep[addr(sponsor)] += reward * slots

        def call():
            h.vm.sender = sponsor
            return h.c.create_bounty(bounty_id, SCOPE, reward, slots, bond, commit_by, reveal_window, review_by)

        ok, _ = self.attempt("create", call)
        if ok:
            h.bounties.append((sponsor, bounty_id))
            self.funded[addr(sponsor)] += reward * slots

    def pick_bounty(self):
        return self.rng.choice(self.h.bounties) if self.h.bounties else None

    def op_commit(self):
        h, rng = self.h, self.rng
        target = self.pick_bounty()
        if target is None:
            return
        sponsor, bounty_id = target
        hunter = rng.choice(self.actors)
        title, body = self.text()
        sub = h.make_sub(hunter, sponsor=sponsor, bounty_id=bounty_id, title=title, body=body)
        bond = h.bounty(sponsor, bounty_id)["bond_wei"]
        if rng.random() < 0.8:
            h.deposit(hunter, bond)
            self.dep[addr(hunter)] += bond

        def call():
            h.vm.sender = hunter
            return h.c.commit_finding(addr(sponsor), bounty_id, sub.commitment)

        ok, index = self.attempt("commit", call)
        if ok:
            sub.index = index
            self.bonds[addr(hunter)] += bond
            self.pending.append((sponsor, bounty_id, sub))

    def op_reveal(self):
        h, rng = self.h, self.rng
        if not self.pending:
            return
        slot = rng.randrange(len(self.pending))
        sponsor, bounty_id, sub = self.pending[slot]
        sender = sub.hunter if rng.random() < 0.85 else rng.choice(self.actors)
        salt = sub.salt if rng.random() < 0.92 else "x" * 16
        title = sub.title if rng.random() < 0.97 else sub.title + "!"

        def call():
            h.vm.sender = sender
            return h.c.reveal_finding(addr(sponsor), bounty_id, sub.index, title, sub.body, salt)

        ok, _ = self.attempt("reveal", call)
        if ok:
            self.pending.pop(slot)

    def op_adjudicate(self):
        h, rng = self.h, self.rng
        target = self.pick_bounty()
        if target is None:
            return
        sponsor, bounty_id = target
        analysis = rng.choice(VERDICTS)
        caller = rng.choice(self.actors)
        ok, result = self.attempt("adjudicate", lambda: h.adjudicate(analysis, caller, sponsor, bounty_id))
        if ok:
            assert result in TERMINAL | {"revealed"}, result
            OUTCOMES["adjudicate->" + result] += 1

    def op_void(self):
        h, rng = self.h, self.rng
        target = self.pick_bounty()
        if target is None:
            return
        sponsor, bounty_id = target
        count = h.bounty(sponsor, bounty_id)["finding_count"]
        index = rng.randrange(count + 1) if count else 0
        caller = rng.choice(self.actors)
        self.attempt("void", lambda: h.void(index, caller, sponsor, bounty_id))

    def op_close(self):
        h, rng = self.h, self.rng
        target = self.pick_bounty()
        if target is None:
            return
        sponsor, bounty_id = target
        caller = rng.choice(self.actors)
        self.attempt("close", lambda: h.close(caller, sponsor, bounty_id))

    def op_cancel(self):
        h = self.h
        target = self.pick_bounty()
        if target is None:
            return
        sponsor, bounty_id = target

        def call():
            h.vm.sender = sponsor
            return h.c.cancel_bounty(bounty_id)

        self.attempt("cancel", call)

    def op_warp(self):
        self.now += self.rng.choice([30, 301, 1800, HOUR, 2 * HOUR, 5 * HOUR, DAY, 3 * DAY])
        self.h.warp(self.now)
        OUTCOMES["warp:ok"] += 1

    def run(self, steps):
        weighted = (
            [self.op_deposit] * 2 + [self.op_withdraw] * 2 + [self.op_create] * 3 + [self.op_commit] * 8
            + [self.op_reveal] * 7 + [self.op_adjudicate] * 9 + [self.op_void] * 2 + [self.op_close] * 2
            + [self.op_cancel] * 1 + [self.op_warp] * 4
        )
        for _ in range(steps):
            self.rng.choice(weighted)()
            self.verify()


@pytest.mark.parametrize("seed", SEEDS)
def test_random_sequences_keep_every_invariant(h, seed):
    world = World(h, random.Random(seed))
    world.op_create()          # every run starts with at least one bounty attempt
    world.run(STEPS)
    # Drain: let every deadline pass, close everything, and withdraw all credit.
    world.now += 30 * DAY
    h.warp(world.now)
    for sponsor, bounty_id in list(h.bounties):
        if h.bounty(sponsor, bounty_id)["status"] == "open":
            h.close(h.frank, sponsor, bounty_id)
    world.verify()
    for who in h.people:
        if h.credit(who):
            world.wd[addr(who)] += h.withdraw(who)
    acct = world.h.check()
    world.reconcile()
    assert acct["total_credits"] == 0 and acct["total_locked"] == 0 and acct["contract_balance"] == 0


def test_fuzz_exercised_every_interesting_path():
    if not OUTCOMES:
        pytest.skip("fuzz seeds did not run in this session")
    wanted = [
        "create:ok", "create:rejected", "commit:ok", "commit:rejected", "reveal:ok", "reveal:rejected",
        "adjudicate->distinct", "adjudicate->duplicate", "adjudicate->invalid", "adjudicate->revealed",
        "void:ok", "close:ok", "withdraw:ok", "withdraw:rejected", "cancel:ok",
    ]
    missing = [name for name in wanted if OUTCOMES[name] == 0]
    assert not missing, f"fuzz never reached: {missing}; saw {dict(OUTCOMES)}"
