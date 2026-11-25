import pytest

from tests.direct.helpers import BOND, DAY, HOUR, NOW_TS, REWARD, addr, verdict

COMMIT_BY = NOW_TS + 2 * HOUR
REVIEW_BY = COMMIT_BY + HOUR + 2 * DAY


# ---------------------------- voiding unrevealed commitments ----------------------------


def test_void_is_gated_by_the_reveal_deadline_and_forfeits_the_bond_to_the_sponsor(h):
    h.create_bounty()
    sub = h.commit(h.bob)
    h.vm.sender = h.dave
    h.warp(NOW_TS + HOUR - 1)
    with h.vm.expect_revert("cannot be voided"):
        h.c.void_unrevealed(addr(h.alice), "B1", sub.index)
    h.warp(NOW_TS + HOUR)
    h.c.void_unrevealed(addr(h.alice), "B1", sub.index)
    f = h.finding(0)
    assert f["status"] == "void" and f["bond_state"] == "forfeited_to_sponsor" and f["reason"] == "not_revealed_in_time"
    assert h.credit(h.alice) == BOND and h.credit(h.bob) == 0
    assert h.bounty()["cursor"] == 1
    h.check()


def test_void_cannot_be_repeated_or_applied_to_revealed_findings(h):
    h.create_bounty()
    revealed = h.submit(h.bob)
    hidden = h.commit(h.charlie, "retry")
    h.warp(NOW_TS + HOUR)
    h.vm.sender = h.dave
    with h.vm.expect_revert("cannot be voided"):
        h.c.void_unrevealed(addr(h.alice), "B1", revealed.index)
    h.c.void_unrevealed(addr(h.alice), "B1", hidden.index)
    with h.vm.expect_revert("cannot be voided"):
        h.c.void_unrevealed(addr(h.alice), "B1", hidden.index)
    with h.vm.expect_revert("Finding not found"):
        h.c.void_unrevealed(addr(h.alice), "B1", 9)
    h.check()


def test_voiding_an_unrevealed_head_unblocks_the_queue(h):
    h.create_bounty(slots=2)
    blocker = h.commit(h.bob, "pagination")
    waiting = h.commit(h.charlie, "retry")
    h.reveal(waiting)
    h.set_verdict()
    h.vm.sender = h.dave
    with h.vm.expect_revert("awaits reveal or voiding"):
        h.c.adjudicate(addr(h.alice), "B1")
    h.warp(NOW_TS + HOUR)
    h.void(blocker.index)
    # The reveal window of the revealed finding is irrelevant once it is revealed.
    assert h.adjudicate() == "distinct"
    assert h.finding(1)["status"] == "distinct"
    assert h.credit(h.alice) == BOND
    h.check()


def test_a_later_unrevealed_commit_does_not_block_an_earlier_revealed_one(h):
    h.create_bounty(slots=2)
    first = h.submit(h.bob, "pagination")
    h.commit(h.charlie, "retry")
    assert h.adjudicate() == "distinct"
    h.set_verdict()
    h.vm.sender = h.dave
    with h.vm.expect_revert("awaits reveal or voiding"):
        h.c.adjudicate(addr(h.alice), "B1")
    assert first.index == 0
    h.check()


def test_void_out_of_order_keeps_the_cursor_on_the_first_pending_finding(h):
    h.create_bounty(slots=3)
    h.submit(h.bob, "pagination")
    hidden = h.commit(h.charlie, "retry")
    h.submit(h.dave, "timeout")
    h.warp(NOW_TS + HOUR)
    h.void(hidden.index)
    assert h.bounty()["cursor"] == 0
    assert h.adjudicate() == "distinct"
    assert h.bounty()["cursor"] == 2  # skips the voided finding
    assert h.adjudicate() == "distinct"
    h.check()


# ---------------------------- closing ----------------------------


def test_close_requires_commit_window_end_and_nothing_pending(h):
    h.create_bounty(slots=3)
    h.vm.sender = h.dave
    with h.vm.expect_revert("cannot be closed yet"):
        h.c.close_bounty(addr(h.alice), "B1")
    h.warp(COMMIT_BY - 1)
    with h.vm.expect_revert("cannot be closed yet"):
        h.c.close_bounty(addr(h.alice), "B1")
    h.warp(COMMIT_BY)
    h.c.close_bounty(addr(h.alice), "B1")
    bounty = h.bounty()
    assert bounty["status"] == "closed" and bounty["close_reason"] == "commit_window_ended"
    assert bounty["escrow"] == 0 and h.credit(h.alice) == REWARD * 3
    h.check()


def test_close_returns_only_unused_slots_to_the_sponsor(h):
    h.create_bounty(slots=3)
    h.submit(h.bob)
    h.adjudicate()
    h.warp(COMMIT_BY)
    h.close()
    assert h.credit(h.alice) == REWARD * 2 and h.credit(h.bob) == REWARD + BOND
    h.check()


def test_close_before_review_deadline_is_refused_while_a_finding_is_pending(h):
    h.create_bounty(slots=3)
    h.submit(h.bob)
    h.warp(COMMIT_BY + 5 * HOUR)
    h.vm.sender = h.dave
    with h.vm.expect_revert("cannot be closed yet"):
        h.c.close_bounty(addr(h.alice), "B1")
    assert h.bounty()["status"] == "open"
    h.check()


def test_review_deadline_closes_pending_findings_as_unresolved_and_voids_hidden_commits(h):
    h.create_bounty(slots=3)
    pending = h.submit(h.bob)
    hidden = h.commit(h.charlie, "retry")
    h.warp(REVIEW_BY - 1)
    h.vm.sender = h.dave
    with h.vm.expect_revert("cannot be closed yet"):
        h.c.close_bounty(addr(h.alice), "B1")
    h.warp(REVIEW_BY)
    h.c.close_bounty(addr(h.alice), "B1")
    bounty = h.bounty()
    assert bounty["status"] == "closed" and bounty["close_reason"] == "review_deadline"
    assert h.finding(pending.index)["status"] == "unresolved"
    assert h.finding(pending.index)["bond_state"] == "refunded"
    assert h.finding(pending.index)["reason"] == "bounty_closed:review_deadline"
    assert h.finding(hidden.index)["status"] == "void"
    assert h.finding(hidden.index)["bond_state"] == "forfeited_to_sponsor"
    assert h.credit(h.bob) == BOND and h.credit(h.charlie) == 0
    assert h.credit(h.alice) == REWARD * 3 + BOND
    h.check()


def test_adjudication_is_closed_at_the_review_deadline(h):
    h.create_bounty(bounty_id="B1")
    h.create_bounty(bounty_id="B2")
    h.submit(h.bob, bounty_id="B1")
    h.submit(h.bob, bounty_id="B2")
    h.set_verdict()
    h.vm.sender = h.dave
    h.warp(REVIEW_BY - 1)
    assert h.c.adjudicate(addr(h.alice), "B1") == "distinct"
    h.warp(REVIEW_BY)
    with h.vm.expect_revert("Review window elapsed"):
        h.c.adjudicate(addr(h.alice), "B2")
    assert h.finding(0, bounty_id="B2")["status"] == "revealed"
    h.check()


def test_sponsor_cannot_dodge_payment_by_waiting_hunters_have_a_full_day_after_the_last_reveal(h):
    # review_by must be at least commit_by + reveal_window + 24h, so a hunter who commits at the
    # last second and reveals at the last second still gets a day of permissionless adjudication.
    h.create_bounty(slots=1)
    h.warp(COMMIT_BY - 1)
    sub = h.commit(h.bob)
    h.warp(COMMIT_BY - 1 + HOUR - 1)
    h.reveal(sub)
    h.warp(COMMIT_BY + HOUR + DAY - 1)
    assert h.adjudicate() == "distinct"
    assert h.credit(h.bob) == REWARD + BOND
    h.check()


def test_closed_bounty_rejects_every_further_action(h):
    h.create_bounty(slots=1)
    sub = h.submit(h.bob)
    h.adjudicate()
    assert h.bounty()["status"] == "closed"
    h.vm.sender = h.dave
    h.set_verdict()
    with h.vm.expect_revert("Bounty is not open"):
        h.c.close_bounty(addr(h.alice), "B1")
    with h.vm.expect_revert("Bounty is not open"):
        h.c.adjudicate(addr(h.alice), "B1")
    with h.vm.expect_revert("cannot be cancelled"):
        h.vm.sender = h.alice
        h.c.cancel_bounty("B1")
    with h.vm.expect_revert("not awaiting reveal"):
        h.vm.sender = h.bob
        h.c.reveal_finding(addr(h.alice), "B1", sub.index, sub.title, sub.body, sub.salt)
    h.check()


def test_every_credit_can_be_withdrawn_and_the_contract_ends_empty(h):
    h.create_bounty(slots=2)
    h.submit(h.bob, "pagination")
    h.submit(h.charlie, "color")
    h.commit(h.dave, "retry")
    h.adjudicate()
    h.adjudicate(verdict(in_scope="no"))
    h.warp(NOW_TS + HOUR)
    h.void(2)
    h.warp(COMMIT_BY)
    h.close()
    total = 0
    for person in h.people:
        if h.credit(person):
            total += h.withdraw(person)
    assert total == REWARD * 2 + 3 * BOND  # reward pool plus every bond: nothing lost, nothing created
    acct = h.check()
    assert acct["total_credits"] == 0 and acct["total_locked"] == 0 and acct["contract_balance"] == 0


def test_two_bounties_are_fully_isolated(h):
    h.create_bounty(bounty_id="B1", slots=1)
    h.create_bounty(bounty_id="B2", slots=1, sponsor=h.bob)
    a = h.submit(h.charlie, "pagination", bounty_id="B1")
    b = h.submit(h.charlie, "pagination", bounty_id="B2", sponsor=h.bob)
    assert (a.index, b.index) == (0, 0)
    h.adjudicate(bounty_id="B1")
    assert h.bounty(bounty_id="B1")["status"] == "closed"
    assert h.bounty(h.bob, "B2")["status"] == "open" and h.finding(0, h.bob, "B2")["status"] == "revealed"
    h.adjudicate(sponsor=h.bob, bounty_id="B2")
    assert h.credit(h.charlie) == 2 * (REWARD + BOND)
    h.check()


def test_same_hunter_limit_is_per_bounty(h):
    h.create_bounty(bounty_id="B1", slots=8)
    h.create_bounty(bounty_id="B2", slots=8)
    for i in range(4):
        h.commit(h.bob, bounty_id="B1", title=f"first {i}", body=f"first body {i}")
        h.commit(h.bob, bounty_id="B2", title=f"second {i}", body=f"second body {i}")
    h.check()
