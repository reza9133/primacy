import pytest

from tests.direct.helpers import BOND, HOUR, NOW_TS, REWARD, SCOPE, addr, verdict


def test_deposit_credits_only_the_actual_sender_and_accumulates(h):
    h.deposit(h.bob, 5)
    h.deposit(h.bob, 7)
    h.deposit(h.charlie, 11)
    assert h.credit(h.bob) == 12 and h.credit(h.charlie) == 11 and h.credit(h.alice) == 0
    acct = h.check()
    assert acct["total_credits"] == 23 and acct["contract_balance"] == 23


def test_zero_value_deposit_is_rejected(h):
    h.vm.sender = h.bob
    h.vm.value = 0
    with h.vm.expect_revert("Deposit must be positive"):
        h.c.deposit_credit()
    assert h.c.get_accounting()["total_credits"] == 0


def test_withdraw_sends_the_whole_credit_once(h):
    h.deposit(h.bob, 1234)
    h.deposit(h.charlie, 99)
    assert h.withdraw(h.bob) == 1234
    assert h.credit(h.bob) == 0 and h.credit(h.charlie) == 99
    h.vm.sender = h.bob
    with h.vm.expect_revert("No available credit"):
        h.c.withdraw_credit()
    h.check()


def test_withdraw_without_credit_is_rejected_and_credit_is_never_cross_owned(h):
    h.deposit(h.bob, 50)
    h.vm.sender = h.charlie
    with h.vm.expect_revert("No available credit"):
        h.c.withdraw_credit()
    assert h.credit(h.bob) == 50
    h.check()


def test_locked_escrow_and_bonds_cannot_be_withdrawn(h):
    h.create_bounty(slots=2)
    h.vm.sender = h.alice
    with h.vm.expect_revert("No available credit"):
        h.c.withdraw_credit()
    sub = h.commit(h.bob)
    h.vm.sender = h.bob
    with h.vm.expect_revert("No available credit"):
        h.c.withdraw_credit()
    assert h.c.get_accounting()["total_locked"] == REWARD * 2 + BOND
    assert sub.index == 0
    h.check()


def test_spare_credit_beyond_a_bounty_stays_withdrawable(h):
    h.deposit(h.alice, REWARD * 2 + 5)
    h.vm.sender = h.alice
    h.c.create_bounty("B1", SCOPE, REWARD, 2, BOND, NOW_TS + 2 * HOUR, HOUR, NOW_TS + 3 * HOUR + 2 * 86400)
    h.bounties.append((h.alice, "B1"))
    assert h.withdraw(h.alice) == 5
    h.check()


@pytest.mark.parametrize("reward,bond", [(10**14 + 12345, 10**12 + 7), (999_999_999_999_999, 3_333_333_333_333)])
def test_odd_amounts_are_conserved_exactly(h, reward, bond):
    h.create_bounty(slots=3, reward=reward, bond=bond)
    h.submit(h.bob, "pagination")
    h.submit(h.charlie, "color")
    h.adjudicate()
    h.adjudicate(verdict(in_scope="no"))
    assert h.credit(h.bob) == reward + bond and h.credit(h.alice) == bond and h.credit(h.charlie) == 0
    h.check()


def test_maximum_amounts_do_not_overflow_the_ledger(h):
    big = 10**27
    h.create_bounty(slots=8, reward=big, bond=big)
    assert h.bounty()["escrow"] == 8 * big
    h.submit(h.bob, "pagination")
    h.adjudicate()
    assert h.credit(h.bob) == 2 * big
    h.check()


NONPAYABLE = [
    ("create_bounty", lambda h: ("B9", SCOPE, REWARD, 1, BOND, NOW_TS + 2 * HOUR, HOUR, NOW_TS + 3 * HOUR + 2 * 86400)),
    ("cancel_bounty", lambda h: ("B1",)),
    ("close_bounty", lambda h: (addr(h.alice), "B1")),
    ("commit_finding", lambda h: (addr(h.alice), "B1", "0x" + "ab" * 32)),
    ("reveal_finding", lambda h: (addr(h.alice), "B1", 0, "t", "b", "s" * 16)),
    ("void_unrevealed", lambda h: (addr(h.alice), "B1", 0)),
    ("adjudicate", lambda h: (addr(h.alice), "B1")),
    ("withdraw_credit", lambda h: ()),
]


@pytest.mark.adversarial
@pytest.mark.parametrize("method,args", NONPAYABLE, ids=[name for name, _ in NONPAYABLE])
def test_every_nonpayable_write_rejects_attached_value(h, method, args):
    h.create_bounty(slots=2)
    h.deposit(h.bob, 10)
    h.vm.sender = h.alice
    h.vm.value = 1
    with h.vm.expect_revert("does not accept value"):
        getattr(h.c, method)(*args(h))
    h.vm.value = 0
    h.check()


def test_views_have_no_side_effects_and_validate_inputs(h):
    h.create_bounty()
    with h.vm.expect_revert("Invalid credit owner"):
        h.c.get_credit("nonsense")
    with h.vm.expect_revert("Zero credit owner"):
        h.c.get_credit("0x" + "0" * 40)
    with h.vm.expect_revert("Finding not found"):
        h.c.get_finding(addr(h.alice), "B1", 0)
    assert h.c.get_findings(addr(h.alice), "B1") == []
    with h.vm.expect_revert("Bounty not found"):
        h.c.get_bounty(addr(h.bob), "B1")
    h.check()


def test_info_view_reports_the_constants_the_tests_rely_on(h):
    info = h.c.get_info()
    assert info["name"] == "Primacy" and info["version"] == "0.1.0" and info["commitment_domain"] == "primacy/v1"
    assert info["min_reward_wei"] == 10**14 and info["min_bond_wei"] == 10**12
    assert info["max_slots"] == 8 and info["max_findings"] == 32 and info["max_findings_per_hunter"] == 4
    assert info["minimum_confidence"] == 80
    assert info["max_inconclusive_assessments"] == 3 and info["max_operational_failures"] == 6
    assert info["retry_cooldown_seconds"] == 300 and info["max_retry_cooldown_seconds"] == 7200
    assert info["min_commit_window_seconds"] == 600 and info["min_reveal_window_seconds"] == 300
    assert info["min_review_tail_seconds"] == 86400
    assert info["copy_guard_jaccard_percent"] == 90 and info["copy_guard_min_words"] == 12
