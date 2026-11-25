"""Shared Direct Mode test harness for Primacy.

The harness mirrors deposited and withdrawn value into the VM balance (Direct
Mode does not move value by itself), tracks every bounty it creates, and offers
``check()``, an independent recomputation of the contract's accounting
invariants from public views.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from gltest.direct.loader import create_address

from scripts.primacy_commit import raw_commitment as off_chain_commitment
from scripts.primacy_commit import new_salt

CONTRACT = "contracts/primacy.py"
RUNNER = "v0.2.16"
NOW = "2026-10-01T12:00:00Z"
NOW_TS = int(datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc).timestamp())
HOUR = 3600
DAY = 24 * HOUR
REWARD = 10**15
BOND = 10**13
SCOPE = "Documentation errata: wrong statements, broken examples, and incorrect numbers in the Atlas SDK reference manual."
PROMPT_PATTERN = r"(?s)impartial triage judge for a first-finder reward program.*Allowed duplicate_of values"

TITLES = {
    "pagination": "Pagination guide states a page size limit of 50 but the API allows 100",
    "retry": "Retry example sleeps in milliseconds although the sleep helper takes seconds",
    "timeout": "Default timeout is documented as 30 seconds while the client constant is 10 seconds",
    "auth": "Authentication chapter shows a deprecated token header in every sample request",
    "color": "I think the documentation theme colors are ugly and should be redesigned",
}
BODIES = {
    "pagination": (
        "In the pagination guide the sentence under 'Limits' says that the maximum page size is 50 items. "
        "The reference table for the list endpoint and the server code both allow 100 items per page, "
        "so readers believe they must issue twice as many requests as needed."
    ),
    "retry": (
        "The retry example in the error handling chapter calls sleep(500) and the comment says it waits half a "
        "second. The sleep helper documented two pages earlier takes seconds, so the example actually waits "
        "more than eight minutes before retrying."
    ),
    "timeout": (
        "The configuration chapter says the default request timeout is 30 seconds. The client source defines "
        "DEFAULT_TIMEOUT as 10 seconds, so users who rely on the documented value see unexpected failures."
    ),
    "auth": (
        "Every sample request in the authentication chapter uses the X-Token header which was deprecated in "
        "favor of the Authorization header, so copying the samples yields warnings and eventual rejection."
    ),
    "color": (
        "The pale grey on white of the documentation theme is hard to look at and I would prefer a darker "
        "palette with more contrast and a nicer overall feeling."
    ),
}


def addr(value) -> str:
    return "0x" + value.as_bytes.hex().lower()


def at(ts) -> str:
    return datetime.fromtimestamp(int(ts), timezone.utc).isoformat().replace("+00:00", "Z")


def verdict(in_scope="yes", actionable="yes", duplicate_of="none", confidence=92, rationale="Clear."):
    return {
        "in_scope": in_scope,
        "actionable": actionable,
        "duplicate_of": duplicate_of,
        "confidence": confidence,
        "rationale": rationale,
    }


DISTINCT = verdict()
DEFAULT = object()


def duplicate(label="H1", confidence=92):
    return verdict(duplicate_of=label, confidence=confidence, rationale="Same root cause.")


@dataclass
class Sub:
    index: int
    hunter: object
    title: str
    body: str
    salt: str
    commitment: str


class Harness:
    def __init__(self, vm, deploy):
        self.vm = vm
        vm.warp(NOW)
        self.c = deploy(CONTRACT, sdk_version=RUNNER)
        self.contract_address = vm._contract_address
        self.alice = create_address("alice")
        self.bob = create_address("bob")
        self.charlie = create_address("charlie")
        self.dave = create_address("dave")
        self.erin = create_address("erin")
        self.frank = create_address("frank")
        self.people = [self.alice, self.bob, self.charlie, self.dave, self.erin, self.frank]
        self.sponsor = self.alice
        self.bounty_id = "B1"
        self.bounties = []
        self.deposited = 0
        self.withdrawn = 0
        self.expect_balance = True

    # ---- time -----------------------------------------------------------

    def warp(self, ts):
        self.vm.warp(at(ts))

    # ---- credit ---------------------------------------------------------

    def deposit(self, who, amount):
        self.vm.sender = who
        self.vm.value = amount
        assert self.c.deposit_credit() == amount
        self.vm.value = 0
        balance = self.vm._balances.get(self.contract_address, 0)
        self.vm.deal(self.contract_address, balance + amount)
        self.deposited += amount

    def withdraw(self, who):
        self.vm.sender = who
        amount = self.c.withdraw_credit()
        balance = self.vm._balances.get(self.contract_address, 0)
        self.vm.deal(self.contract_address, balance - amount)
        self.withdrawn += amount
        return amount

    def credit(self, who):
        return self.c.get_credit(addr(who))

    # ---- bounties -------------------------------------------------------

    def create_bounty(self, sponsor=None, bounty_id=None, fund=True, scope=SCOPE, reward=REWARD,
                      slots=2, bond=BOND, commit_in=2 * HOUR, reveal_window=HOUR,
                      review_tail=2 * DAY, commit_by=None, review_by=None, track=True):
        sponsor = sponsor or self.sponsor
        bounty_id = bounty_id or self.bounty_id
        commit_by = commit_by if commit_by is not None else NOW_TS + commit_in
        review_by = review_by if review_by is not None else commit_by + reveal_window + review_tail
        if fund:
            self.deposit(sponsor, reward * slots)
        self.vm.sender = sponsor
        key = self.c.create_bounty(bounty_id, scope, reward, slots, bond, commit_by, reveal_window, review_by)
        if track:
            self.bounties.append((sponsor, bounty_id))
        return key

    def bounty(self, sponsor=None, bounty_id=None):
        return self.c.get_bounty(addr(sponsor or self.sponsor), bounty_id or self.bounty_id)

    def findings(self, sponsor=None, bounty_id=None):
        return self.c.get_findings(addr(sponsor or self.sponsor), bounty_id or self.bounty_id)

    def finding(self, index, sponsor=None, bounty_id=None):
        return self.c.get_finding(addr(sponsor or self.sponsor), bounty_id or self.bounty_id, index)

    # ---- findings -------------------------------------------------------

    def make_sub(self, hunter, topic="pagination", sponsor=None, bounty_id=None, title=None, body=None, salt=None):
        sponsor = sponsor or self.sponsor
        bounty_id = bounty_id or self.bounty_id
        title = title if title is not None else TITLES[topic]
        body = body if body is not None else BODIES[topic]
        salt = salt or new_salt()
        digest = off_chain_commitment(addr(sponsor), bounty_id, addr(hunter), salt, title, body)
        return Sub(-1, hunter, title, body, salt, digest)

    def commit(self, hunter, topic="pagination", sponsor=None, bounty_id=None, fund=True, **kwargs):
        sponsor = sponsor or self.sponsor
        bounty_id = bounty_id or self.bounty_id
        sub = self.make_sub(hunter, topic, sponsor, bounty_id, **kwargs)
        if fund:
            self.deposit(hunter, self.bounty(sponsor, bounty_id)["bond_wei"])
        self.vm.sender = hunter
        sub.index = self.c.commit_finding(addr(sponsor), bounty_id, sub.commitment)
        return sub

    def reveal(self, sub, sponsor=None, bounty_id=None, sender=None):
        self.vm.sender = sender or sub.hunter
        self.c.reveal_finding(addr(sponsor or self.sponsor), bounty_id or self.bounty_id,
                              sub.index, sub.title, sub.body, sub.salt)

    def submit(self, hunter, topic="pagination", **kwargs):
        sub = self.commit(hunter, topic, **kwargs)
        self.reveal(sub, sponsor=kwargs.get("sponsor"), bounty_id=kwargs.get("bounty_id"))
        return sub

    # ---- adjudication ---------------------------------------------------

    def set_verdict(self, analysis=DEFAULT):
        self.vm.clear_mocks()
        self.vm.mock_llm(PROMPT_PATTERN, json.dumps(DISTINCT if analysis is DEFAULT else analysis))

    def adjudicate(self, analysis=DEFAULT, caller=None, sponsor=None, bounty_id=None):
        self.set_verdict(analysis)
        self.vm.sender = caller or self.dave
        return self.c.adjudicate(addr(sponsor or self.sponsor), bounty_id or self.bounty_id)

    def adjudicate_raw(self, caller=None, sponsor=None, bounty_id=None):
        self.vm.sender = caller or self.dave
        return self.c.adjudicate(addr(sponsor or self.sponsor), bounty_id or self.bounty_id)

    def void(self, index, caller=None, sponsor=None, bounty_id=None):
        self.vm.sender = caller or self.dave
        self.c.void_unrevealed(addr(sponsor or self.sponsor), bounty_id or self.bounty_id, index)

    def close(self, caller=None, sponsor=None, bounty_id=None):
        self.vm.sender = caller or self.dave
        self.c.close_bounty(addr(sponsor or self.sponsor), bounty_id or self.bounty_id)

    # ---- invariants -----------------------------------------------------

    def check(self):
        """Recompute every accounting invariant independently from public views."""
        acct = self.c.get_accounting()
        credits = sum(self.credit(person) for person in self.people)
        assert credits == acct["total_credits"], "per-account credits must sum to total_credits"
        locked = 0
        for sponsor, bounty_id in self.bounties:
            bounty = self.bounty(sponsor, bounty_id)
            findings = self.findings(sponsor, bounty_id)
            assert bounty["finding_count"] == len(findings)
            heads = [f for f in findings if f["status"] == "distinct"]
            assert bounty["heads"] == len(heads)
            assert bounty["heads"] <= bounty["slots"]
            if bounty["status"] == "open":
                assert bounty["escrow"] == (bounty["slots"] - bounty["heads"]) * bounty["reward_wei"]
                locked += bounty["escrow"]
            else:
                assert bounty["escrow"] == 0
                assert bounty["cursor"] == bounty["finding_count"]
            for f in findings:
                if f["status"] in ("committed", "revealed"):
                    assert f["bond_wei"] == bounty["bond_wei"] and f["bond_state"] == "locked"
                    assert bounty["status"] == "open"
                    locked += f["bond_wei"]
                else:
                    assert f["bond_wei"] == 0 and f["bond_state"] in ("refunded", "forfeited_to_sponsor")
                assert (f["reward_wei"] == bounty["reward_wei"]) == (f["status"] == "distinct")
            for f in findings[: bounty["cursor"]]:
                assert f["status"] not in ("committed", "revealed")
            if bounty["cursor"] < bounty["finding_count"]:
                assert findings[bounty["cursor"]]["status"] in ("committed", "revealed")
        assert locked == acct["total_locked"], "locked must equal open escrow plus pending bonds"
        assert acct["accounted_liabilities"] == self.deposited - self.withdrawn
        assert acct["solvent"] is True
        if self.expect_balance:
            assert acct["contract_balance"] == acct["accounted_liabilities"]
            assert acct["unallocated_balance"] == 0
            assert acct["balance_shortfall"] == 0
        return acct
