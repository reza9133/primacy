import hashlib

import pytest
from gltest.direct.loader import create_address

from scripts.primacy_commit import raw_commitment as off_chain_commitment
from tests.direct.helpers import BODIES, BOND, HOUR, NOW_TS, REWARD, TITLES, addr


def raw_commitment(sponsor, bounty_id, hunter, salt, title, body):
    """Independent re-implementation of the documented preimage, used as a golden check."""
    def field(text):
        data = text.encode("utf-8")
        return str(len(data)).encode() + b":" + data + b";"
    parts = ["primacy/v1", sponsor.lower() + ":" + bounty_id, hunter.lower(), salt, title, body]
    return "0x" + hashlib.sha256(b"".join(field(p) for p in parts)).hexdigest()


def test_golden_commitment_vector_matches_the_documented_preimage():
    sponsor = "0x" + "11" * 20
    hunter = "0x" + "22" * 20
    expected = raw_commitment(sponsor, "B1", hunter, "s" * 16, "Title", "Body\nline")
    assert off_chain_commitment(sponsor, "B1", hunter, "s" * 16, "Title", "Body\nline") == expected
    # Frozen vector: any change to the preimage layout must be a deliberate, versioned decision.
    assert expected == "0x" + hashlib.sha256(
        b"10:primacy/v1;45:" + (sponsor + ":B1").encode() + b";42:" + hunter.encode()
        + b";16:" + b"s" * 16 + b";5:Title;9:Body\nline;"
    ).hexdigest()


def test_commitment_helper_rejects_weak_salts():
    for bad in ("", "short", "x" * 65, "has space 123456789", "semi;colon_1234567"):
        with pytest.raises(ValueError):
            off_chain_commitment("0x" + "11" * 20, "B1", "0x" + "22" * 20, bad, "t", "b")


def test_commit_assigns_sequential_indexes_and_locks_exact_bonds(h):
    h.create_bounty(slots=3)
    a = h.commit(h.bob)
    b = h.commit(h.charlie, "retry")
    c = h.commit(h.bob, "timeout")
    assert (a.index, b.index, c.index) == (0, 1, 2)
    bounty = h.bounty()
    assert bounty["finding_count"] == 3 and bounty["cursor"] == 0
    for sub in (a, b, c):
        f = h.finding(sub.index)
        assert f["status"] == "committed" and f["bond_wei"] == BOND and f["bond_state"] == "locked"
        assert f["committed_at"] == NOW_TS and f["reveal_by"] == NOW_TS + HOUR
        assert f["title"] == "" and f["body"] == "" and f["commitment"] == sub.commitment
    assert h.credit(h.bob) == 0 and h.credit(h.charlie) == 0
    acct = h.check()
    assert acct["total_locked"] == REWARD * 3 + BOND * 3


def test_commit_requires_credit_for_the_bond(h):
    h.create_bounty()
    sub = h.make_sub(h.bob)
    h.deposit(h.bob, BOND - 1)
    h.vm.sender = h.bob
    with h.vm.expect_revert("Insufficient available credit"):
        h.c.commit_finding(addr(h.alice), "B1", sub.commitment)
    assert h.bounty()["finding_count"] == 0 and h.credit(h.bob) == BOND - 1
    h.check()


def test_sponsor_cannot_submit_findings_to_their_own_bounty(h):
    h.create_bounty()
    h.deposit(h.alice, BOND)
    sub = h.make_sub(h.alice)
    h.vm.sender = h.alice
    with h.vm.expect_revert("Sponsor cannot submit findings"):
        h.c.commit_finding(addr(h.alice), "B1", sub.commitment)


def test_commit_window_boundary_is_exclusive(h):
    h.create_bounty()
    h.deposit(h.bob, BOND * 2)
    h.warp(NOW_TS + 2 * HOUR - 1)
    sub = h.make_sub(h.bob)
    h.vm.sender = h.bob
    assert h.c.commit_finding(addr(h.alice), "B1", sub.commitment) == 0
    h.warp(NOW_TS + 2 * HOUR)
    with h.vm.expect_revert("Commit window is closed"):
        h.c.commit_finding(addr(h.alice), "B1", sub.commitment)
    assert h.bounty()["finding_count"] == 1
    h.check()


@pytest.mark.parametrize("bad", ["", "0x", "0x1234", "1234" * 16, "0x" + "g" * 64, "0x" + "a" * 63, "0x" + "a" * 65])
def test_malformed_commitments_rejected(h, bad):
    h.create_bounty()
    h.deposit(h.bob, BOND)
    h.vm.sender = h.bob
    with h.vm.expect_revert("Invalid commitment"):
        h.c.commit_finding(addr(h.alice), "B1", bad)
    assert h.credit(h.bob) == BOND


def test_uppercase_commitment_is_normalized_and_still_reveals(h):
    h.create_bounty()
    sub = h.make_sub(h.bob)
    h.deposit(h.bob, BOND)
    h.vm.sender = h.bob
    h.c.commit_finding(addr(h.alice), "B1", "0x" + sub.commitment[2:].upper())
    sub.index = 0
    assert h.finding(0)["commitment"] == sub.commitment
    h.reveal(sub)
    assert h.finding(0)["status"] == "revealed"


def test_commit_to_unknown_bounty_rejected(h):
    h.deposit(h.bob, BOND)
    sub = h.make_sub(h.bob)
    h.vm.sender = h.bob
    with h.vm.expect_revert("Bounty not found"):
        h.c.commit_finding(addr(h.alice), "B1", sub.commitment)


def test_per_hunter_limit(h):
    h.create_bounty(slots=8)
    for i in range(4):
        h.commit(h.bob, "pagination", title=f"Title number {i}", body=f"Body number {i} " * 3)
    h.deposit(h.bob, BOND)
    sub = h.make_sub(h.bob, "retry")
    h.vm.sender = h.bob
    with h.vm.expect_revert("Per-hunter finding limit reached"):
        h.c.commit_finding(addr(h.alice), "B1", sub.commitment)
    other = h.commit(h.charlie, "retry")
    assert other.index == 4
    h.check()


def test_total_finding_limit(h):
    h.create_bounty(slots=8)
    hunters = [create_address(f"hunter-{i}") for i in range(9)]
    h.people.extend(hunters)
    for n in range(32):
        h.commit(hunters[n // 4], title=f"T{n}", body=f"B{n}")
    assert h.bounty()["finding_count"] == 32
    h.deposit(hunters[8], BOND)
    sub = h.make_sub(hunters[8])
    h.vm.sender = hunters[8]
    with h.vm.expect_revert("Finding limit reached"):
        h.c.commit_finding(addr(h.alice), "B1", sub.commitment)
    h.check()


def test_reveal_publishes_text_and_moves_state(h):
    h.create_bounty()
    sub = h.commit(h.bob)
    h.warp(NOW_TS + 30 * 60)
    h.reveal(sub)
    f = h.finding(0)
    assert f["status"] == "revealed" and f["title"] == sub.title and f["body"] == sub.body
    assert f["revealed_at"] == NOW_TS + 30 * 60
    h.check()


@pytest.mark.parametrize("mutate", ["salt", "title", "body", "index_other"])
def test_reveal_must_match_the_commitment_exactly(h, mutate):
    h.create_bounty()
    first = h.commit(h.bob)
    second = h.commit(h.bob, "retry")
    sub = first
    title, body, salt, index = sub.title, sub.body, sub.salt, sub.index
    if mutate == "salt":
        salt = "z" * 16
    elif mutate == "title":
        title = title + "."
    elif mutate == "body":
        body = body + "."
    else:
        index = second.index
    h.vm.sender = h.bob
    with h.vm.expect_revert("Reveal does not match commitment"):
        h.c.reveal_finding(addr(h.alice), "B1", index, title, body, salt)
    assert h.finding(0)["status"] == "committed" and h.finding(1)["status"] == "committed"


def test_only_the_committing_hunter_can_reveal(h):
    h.create_bounty()
    sub = h.commit(h.bob)
    for other in (h.charlie, h.alice, h.dave):
        h.vm.sender = other
        with h.vm.expect_revert("Only the committing hunter may reveal"):
            h.c.reveal_finding(addr(h.alice), "B1", 0, sub.title, sub.body, sub.salt)
    assert h.finding(0)["status"] == "committed"


def test_reveal_window_boundary_is_exclusive(h):
    h.create_bounty()
    sub = h.commit(h.bob)
    h.warp(NOW_TS + HOUR)
    h.vm.sender = h.bob
    with h.vm.expect_revert("Reveal window elapsed"):
        h.c.reveal_finding(addr(h.alice), "B1", 0, sub.title, sub.body, sub.salt)
    h.warp(NOW_TS + HOUR - 1)
    h.reveal(sub)
    assert h.finding(0)["status"] == "revealed"


def test_double_reveal_rejected(h):
    h.create_bounty()
    sub = h.submit(h.bob)
    h.vm.sender = h.bob
    with h.vm.expect_revert("not awaiting reveal"):
        h.c.reveal_finding(addr(h.alice), "B1", 0, sub.title, sub.body, sub.salt)


def test_reveal_unknown_finding_or_bounty(h):
    h.create_bounty()
    h.vm.sender = h.bob
    with h.vm.expect_revert("Finding not found"):
        h.c.reveal_finding(addr(h.alice), "B1", 0, "t", "b", "s" * 16)
    with h.vm.expect_revert("Bounty not found"):
        h.c.reveal_finding(addr(h.alice), "NOPE", 0, "t", "b", "s" * 16)


@pytest.mark.parametrize("salt", ["", "short", "x" * 15, "x" * 65, "bad salt bad salt1", "bad;salt;bad;salt1", "sel\n" + "x" * 16])
def test_invalid_salts_rejected(h, salt):
    h.create_bounty()
    sub = h.commit(h.bob)
    h.vm.sender = h.bob
    with h.vm.expect_revert("Invalid salt"):
        h.c.reveal_finding(addr(h.alice), "B1", 0, sub.title, sub.body, salt)


@pytest.mark.parametrize("title", [
    "", " leading", "trailing ", "line\nbreak", "tab\tinside", "cr\rreturn", "nul\x00char", "bell\x07",
    "zero​width", "bidi‮override", "isolate⁦mark", "bom﻿mark", "sep line", "c1\x85control",
    "x" * 121,
])
def test_invalid_titles_rejected_at_reveal(h, title):
    h.create_bounty()
    sub = h.make_sub(h.bob, title="valid placeholder title")
    h.deposit(h.bob, BOND)
    h.vm.sender = h.bob
    # Build a commitment for the hostile title so only the text rules can reject it.
    digest = off_chain_commitment(addr(h.alice), "B1", addr(h.bob), sub.salt, title, sub.body)
    h.c.commit_finding(addr(h.alice), "B1", digest)
    with h.vm.expect_revert("Invalid title"):
        h.c.reveal_finding(addr(h.alice), "B1", 0, title, sub.body, sub.salt)
    assert h.finding(0)["status"] == "committed"


@pytest.mark.parametrize("body", [
    "", "\nleading newline", "trailing newline\n", "cr\rinside", "nul\x00inside", "zero​inside",
    "bidi‮inside", "y" * 1201,
])
def test_invalid_bodies_rejected_at_reveal(h, body):
    h.create_bounty()
    h.deposit(h.bob, BOND)
    salt = "s" * 16
    digest = off_chain_commitment(addr(h.alice), "B1", addr(h.bob), salt, "A valid title", body)
    h.vm.sender = h.bob
    h.c.commit_finding(addr(h.alice), "B1", digest)
    with h.vm.expect_revert("Invalid body"):
        h.c.reveal_finding(addr(h.alice), "B1", 0, "A valid title", body, salt)


@pytest.mark.parametrize("title,body", [
    ("x" * 120, "y" * 1200),
    ("Café ✓ snowman ☃", "Line one\nLine two\n\tindented line with tab and unicode üñî"),
    ("a", "b"),
    ("emoji \U0001F600 title", "astral \U0001F4A9 body"),
])
def test_valid_unicode_and_boundary_texts_roundtrip_exactly(h, title, body):
    h.create_bounty()
    sub = h.commit(h.bob, title=title, body=body)
    h.reveal(sub)
    f = h.finding(0)
    assert f["title"] == title and f["body"] == body
    h.check()


# ---------------- adversarial: copycats, replay, front-running ----------------


@pytest.mark.adversarial
def test_copied_commitment_hash_is_useless_to_the_copier(h):
    h.create_bounty()
    victim = h.commit(h.bob)
    # Charlie sees Bob's commitment and commits the very same hash.
    h.deposit(h.charlie, BOND)
    h.vm.sender = h.charlie
    assert h.c.commit_finding(addr(h.alice), "B1", victim.commitment) == 1
    # Charlie cannot reveal Bob's text: the hunter address is part of the preimage.
    with h.vm.expect_revert("Reveal does not match commitment"):
        h.c.reveal_finding(addr(h.alice), "B1", 1, victim.title, victim.body, victim.salt)
    # Bob, the real author, keeps first place.
    h.reveal(victim)
    assert h.finding(0)["status"] == "revealed" and h.finding(1)["status"] == "committed"


@pytest.mark.adversarial
def test_commitment_is_bound_to_the_bounty_and_cannot_be_replayed_elsewhere(h):
    h.create_bounty(bounty_id="B1")
    h.create_bounty(bounty_id="B2")
    sub = h.commit(h.bob, bounty_id="B1")
    h.deposit(h.bob, BOND)
    h.vm.sender = h.bob
    h.c.commit_finding(addr(h.alice), "B2", sub.commitment)
    with h.vm.expect_revert("Reveal does not match commitment"):
        h.c.reveal_finding(addr(h.alice), "B2", 0, sub.title, sub.body, sub.salt)


@pytest.mark.adversarial
def test_commitment_is_bound_to_the_sponsor_namespace(h):
    h.create_bounty(sponsor=h.alice, bounty_id="SHARED")
    h.create_bounty(sponsor=h.bob, bounty_id="SHARED")
    sub = h.commit(h.charlie, sponsor=h.alice, bounty_id="SHARED")
    h.deposit(h.charlie, BOND)
    h.vm.sender = h.charlie
    h.c.commit_finding(addr(h.bob), "SHARED", sub.commitment)
    with h.vm.expect_revert("Reveal does not match commitment"):
        h.c.reveal_finding(addr(h.bob), "SHARED", 0, sub.title, sub.body, sub.salt)


@pytest.mark.adversarial
def test_late_copier_who_sees_the_revealed_text_ranks_behind_the_original(h):
    h.create_bounty()
    original = h.submit(h.bob)
    copier = h.submit(h.charlie, title=original.title, body=original.body)
    assert (original.index, copier.index) == (0, 1)
    h.vm.warp("2026-10-01T12:10:00Z")
    assert h.adjudicate() == "distinct"
    h.warp(NOW_TS + 10 * 60)
    # Verbatim copy is stopped by the deterministic guard without any model call.
    h.vm.clear_mocks()
    h.vm.sender = h.dave
    assert h.c.adjudicate(addr(h.alice), "B1") == "duplicate"
    assert h.finding(0)["status"] == "distinct"
    assert h.finding(1)["status"] == "duplicate" and h.finding(1)["duplicate_of"] == 0
    assert h.credit(h.bob) == REWARD + BOND and h.credit(h.charlie) == BOND
    h.check()


@pytest.mark.adversarial
def test_hunter_commit_order_is_independent_of_reveal_order(h):
    h.create_bounty(slots=3)
    early = h.commit(h.bob, "pagination")
    late = h.commit(h.charlie, "retry")
    h.reveal(late)
    # The later commit revealed first, but the earlier commit still holds the head of the queue.
    h.vm.sender = h.dave
    h.set_verdict()
    with h.vm.expect_revert("awaits reveal or voiding"):
        h.c.adjudicate(addr(h.alice), "B1")
    h.reveal(early)
    assert h.adjudicate() == "distinct"
    assert h.finding(0)["status"] == "distinct" and h.finding(1)["status"] == "revealed"
    h.check()
