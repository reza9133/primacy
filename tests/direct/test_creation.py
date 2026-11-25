import pytest

from tests.direct.helpers import (
    BOND, DAY, HOUR, NOW_TS, REWARD, SCOPE, addr,
)

MIN_COMMIT = 10 * 60
MIN_REVEAL = 5 * 60
MIN_TAIL = DAY
MAX_TAIL = 90 * DAY


def base(**over):
    params = dict(
        bounty_id="B1", scope=SCOPE, reward=REWARD, slots=2, bond=BOND,
        commit_by=NOW_TS + 2 * HOUR, reveal_window=HOUR, review_by=NOW_TS + 2 * HOUR + HOUR + 2 * DAY,
    )
    params.update(over)
    return params


def call_create(h, who=None, **over):
    p = base(**over)
    h.vm.sender = who or h.alice
    return h.c.create_bounty(p["bounty_id"], p["scope"], p["reward"], p["slots"], p["bond"],
                             p["commit_by"], p["reveal_window"], p["review_by"])


def test_create_locks_exact_reward_from_credit_and_records_terms(h):
    h.deposit(h.alice, REWARD * 2 + 777)
    key = call_create(h)
    assert key == addr(h.alice) + ":B1"
    h.bounties.append((h.alice, "B1"))
    bounty = h.bounty()
    assert bounty["status"] == "open"
    assert bounty["sponsor"].lower() == addr(h.alice)
    assert bounty["reward_wei"] == REWARD and bounty["slots"] == 2 and bounty["bond_wei"] == BOND
    assert bounty["escrow"] == REWARD * 2
    assert bounty["finding_count"] == 0 and bounty["heads"] == 0 and bounty["cursor"] == 0
    assert bounty["created_at"] == NOW_TS
    assert h.credit(h.alice) == 777
    acct = h.check()
    assert acct["total_locked"] == REWARD * 2 and acct["total_credits"] == 777


def test_scope_whitespace_is_normalized_but_length_is_bounded(h):
    h.deposit(h.alice, REWARD * 2)
    call_create(h, scope="  Docs   errata\n\tin   the   Atlas   manual only  ")
    h.bounties.append((h.alice, "B1"))
    assert h.bounty()["scope"] == "Docs errata in the Atlas manual only"


@pytest.mark.parametrize("bad_id", ["", " ", "-lead", "_lead", ".lead", "a" * 65, "bad id", "bad/id", "bad:id", "bad#id", "é"])
def test_invalid_bounty_ids_rejected(h, bad_id):
    h.deposit(h.alice, REWARD * 2)
    with h.vm.expect_revert("Invalid bounty id"):
        call_create(h, bounty_id=bad_id)
    assert h.credit(h.alice) == REWARD * 2
    h.check()


@pytest.mark.parametrize("good_id", ["a", "A1", "x" * 64, "round-1_v2.3"])
def test_valid_bounty_ids_accepted(h, good_id):
    h.deposit(h.alice, REWARD * 2)
    call_create(h, bounty_id=good_id)
    h.bounties.append((h.alice, good_id))
    assert h.bounty(bounty_id=good_id)["bounty_id"] == good_id
    h.check()


@pytest.mark.parametrize("scope", ["", "short scope", "x" * 801, "   " + "y" * 5 + "   "])
def test_invalid_scope_rejected(h, scope):
    h.deposit(h.alice, REWARD * 2)
    with h.vm.expect_revert("Invalid scope"):
        call_create(h, scope=scope)
    assert h.credit(h.alice) == REWARD * 2


@pytest.mark.parametrize("reward", [0, 1, 10**14 - 1, 10**27 + 1])
def test_reward_bounds(h, reward):
    h.deposit(h.alice, 10**28)
    with h.vm.expect_revert("Invalid reward"):
        call_create(h, reward=reward, bond=10**12)
    assert h.credit(h.alice) == 10**28


def test_reward_boundaries_accepted(h):
    h.deposit(h.alice, 10**14 * 2 + 10**27 * 2)
    call_create(h, bounty_id="LOW", reward=10**14, bond=10**12)
    call_create(h, bounty_id="HIGH", reward=10**27, bond=10**27)
    h.bounties.extend([(h.alice, "LOW"), (h.alice, "HIGH")])
    h.check()


@pytest.mark.parametrize("slots", [0, 9, 65535])
def test_slot_bounds(h, slots):
    h.deposit(h.alice, REWARD * 20)
    with h.vm.expect_revert("Invalid slot count"):
        call_create(h, slots=slots)


@pytest.mark.parametrize("slots", [1, 8])
def test_slot_boundaries_accepted(h, slots):
    h.deposit(h.alice, REWARD * slots)
    call_create(h, slots=slots)
    h.bounties.append((h.alice, "B1"))
    assert h.bounty()["escrow"] == REWARD * slots
    h.check()


@pytest.mark.parametrize("bond", [0, 10**12 - 1, REWARD + 1])
def test_bond_bounds(h, bond):
    h.deposit(h.alice, REWARD * 2)
    with h.vm.expect_revert("Invalid bond"):
        call_create(h, bond=bond)


def test_bond_boundaries_accepted(h):
    h.deposit(h.alice, REWARD * 4)
    call_create(h, bounty_id="MINBOND", bond=10**12)
    call_create(h, bounty_id="MAXBOND", bond=REWARD)
    h.bounties.extend([(h.alice, "MINBOND"), (h.alice, "MAXBOND")])
    h.check()


@pytest.mark.parametrize("window", [0, MIN_REVEAL - 1, 7 * DAY + 1])
def test_reveal_window_bounds(h, window):
    h.deposit(h.alice, REWARD * 2)
    with h.vm.expect_revert("Invalid reveal window"):
        call_create(h, reveal_window=window)


@pytest.mark.parametrize("window", [MIN_REVEAL, 7 * DAY])
def test_reveal_window_boundaries_accepted(h, window):
    h.deposit(h.alice, REWARD * 2)
    call_create(h, reveal_window=window, review_by=NOW_TS + 2 * HOUR + window + 2 * DAY)
    h.bounties.append((h.alice, "B1"))


@pytest.mark.parametrize("delta", [-1000, 0, MIN_COMMIT - 1, 60 * DAY + 1])
def test_commit_deadline_bounds(h, delta):
    h.deposit(h.alice, REWARD * 2)
    with h.vm.expect_revert("Invalid commit deadline"):
        call_create(h, commit_by=NOW_TS + delta, review_by=NOW_TS + delta + HOUR + 2 * DAY)


@pytest.mark.parametrize("delta", [MIN_COMMIT, 60 * DAY])
def test_commit_deadline_boundaries_accepted(h, delta):
    h.deposit(h.alice, REWARD * 2)
    call_create(h, commit_by=NOW_TS + delta, review_by=NOW_TS + delta + HOUR + 2 * DAY)
    h.bounties.append((h.alice, "B1"))


def test_review_deadline_must_leave_a_full_adjudication_tail(h):
    h.deposit(h.alice, REWARD * 4)
    commit_by = NOW_TS + 2 * HOUR
    earliest = commit_by + HOUR + MIN_TAIL
    latest = commit_by + HOUR + MAX_TAIL
    for bad in (earliest - 1, latest + 1, commit_by, 0):
        with h.vm.expect_revert("Invalid review deadline"):
            call_create(h, review_by=bad)
    call_create(h, bounty_id="EARLIEST", review_by=earliest)
    call_create(h, bounty_id="LATEST", review_by=latest)
    h.bounties.extend([(h.alice, "EARLIEST"), (h.alice, "LATEST")])
    h.check()


def test_duplicate_id_rejected_per_sponsor_but_namespaces_are_separate(h):
    h.deposit(h.alice, REWARD * 4)
    h.deposit(h.bob, REWARD * 2)
    call_create(h)
    h.bounties.append((h.alice, "B1"))
    with h.vm.expect_revert("Duplicate bounty id"):
        call_create(h)
    call_create(h, who=h.bob)
    h.bounties.append((h.bob, "B1"))
    assert h.bounty(h.alice)["sponsor"].lower() == addr(h.alice)
    assert h.bounty(h.bob)["sponsor"].lower() == addr(h.bob)
    h.check()


def test_insufficient_credit_rejected_without_side_effects(h):
    h.deposit(h.alice, REWARD * 2 - 1)
    with h.vm.expect_revert("Insufficient available credit"):
        call_create(h)
    assert h.credit(h.alice) == REWARD * 2 - 1
    with h.vm.expect_revert("Bounty not found"):
        h.bounty()
    h.check()


def test_credit_of_another_account_cannot_fund_a_bounty(h):
    h.deposit(h.bob, REWARD * 2)
    with h.vm.expect_revert("Insufficient available credit"):
        call_create(h, who=h.alice)
    assert h.credit(h.bob) == REWARD * 2


def test_one_bounty_cannot_reuse_credit_already_locked_by_another(h):
    h.deposit(h.alice, REWARD * 2)
    call_create(h)
    h.bounties.append((h.alice, "B1"))
    with h.vm.expect_revert("Insufficient available credit"):
        call_create(h, bounty_id="B2")
    h.check()


def test_cancel_before_any_commit_returns_the_exact_escrow(h):
    h.deposit(h.alice, REWARD * 2)
    call_create(h)
    h.bounties.append((h.alice, "B1"))
    h.vm.sender = h.alice
    h.c.cancel_bounty("B1")
    bounty = h.bounty()
    assert bounty["status"] == "cancelled" and bounty["escrow"] == 0
    assert bounty["close_reason"] == "cancelled_before_any_commit"
    assert h.credit(h.alice) == REWARD * 2
    h.check()
    with h.vm.expect_revert("cannot be cancelled"):
        h.c.cancel_bounty("B1")
    assert h.credit(h.alice) == REWARD * 2


def test_only_the_sponsor_can_cancel_and_only_their_own_namespace(h):
    h.deposit(h.alice, REWARD * 2)
    call_create(h)
    h.vm.sender = h.bob
    with h.vm.expect_revert("Bounty not found"):
        h.c.cancel_bounty("B1")
    assert h.bounty()["status"] == "open"


def test_sponsor_cannot_cancel_once_any_hunter_has_committed(h):
    h.create_bounty()
    h.commit(h.bob)
    h.vm.sender = h.alice
    with h.vm.expect_revert("cannot be cancelled"):
        h.c.cancel_bounty("B1")
    assert h.bounty()["status"] == "open" and h.bounty()["escrow"] == REWARD * 2
    h.check()


def test_cancelled_bounty_rejects_new_commits(h):
    h.create_bounty()
    h.vm.sender = h.alice
    h.c.cancel_bounty("B1")
    h.deposit(h.bob, BOND)
    sub = h.make_sub(h.bob)
    h.vm.sender = h.bob
    with h.vm.expect_revert("Commit window is closed"):
        h.c.commit_finding(addr(h.alice), "B1", sub.commitment)
    h.check()


def test_cancel_unknown_bounty(h):
    h.vm.sender = h.alice
    with h.vm.expect_revert("Bounty not found"):
        h.c.cancel_bounty("NOPE")
    with h.vm.expect_revert("Invalid bounty id"):
        h.c.cancel_bounty("")
