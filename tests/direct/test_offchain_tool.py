"""The off-chain commit tool must agree with the contract and refuse text the contract would refuse."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from gltest.direct.loader import create_address

from scripts.primacy_commit import commitment, new_salt, raw_commitment, validate_text
from tests.direct.helpers import addr

ROOT = Path(__file__).resolve().parents[2]


def test_tool_digest_is_accepted_by_the_contract(h):
    h.create_bounty()
    title, body, salt = "A precise title", "A precise body with details.\nSecond line.", new_salt()
    digest = commitment(addr(h.alice), "B1", addr(h.bob), salt, title, body)
    h.deposit(h.bob, 10**13)
    h.vm.sender = h.bob
    h.c.commit_finding(addr(h.alice), "B1", digest)
    h.c.reveal_finding(addr(h.alice), "B1", 0, title, body, salt)
    assert h.finding(0)["status"] == "revealed"
    h.check()


def test_digest_is_case_insensitive_for_addresses_and_sensitive_to_every_field():
    base = ("0xAbC0000000000000000000000000000000000001", "B1", "0xDEF0000000000000000000000000000000000002",
            "s" * 16, "title", "body")
    reference = commitment(*base)
    assert commitment(base[0].lower(), *base[1:2], base[2].lower(), *base[3:]) == reference
    for position, replacement in enumerate(["0x" + "1" * 40, "B2", "0x" + "2" * 40, "t" * 16, "title2", "body2"]):
        changed = list(base)
        changed[position] = replacement
        assert commitment(*changed) != reference


def test_field_boundaries_cannot_be_shifted_between_title_and_body():
    a = raw_commitment("0x01", "B1", "0x02", "s" * 16, "ab", "c")
    b = raw_commitment("0x01", "B1", "0x02", "s" * 16, "a", "bc")
    assert a != b


@pytest.mark.parametrize("title,body,fragment", [
    ("", "body", "title must not be empty"),
    (" lead", "body", "title must not start or end"),
    ("trail ", "body", "title must not start or end"),
    ("two\nlines", "body", "single line"),
    ("tab\tinside", "body", "single line"),
    ("t" * 121, "body", "longer than 120"),
    ("title", "", "body must not be empty"),
    ("title", "body\n", "body must not start or end"),
    ("title", "b" * 1201, "longer than 1200"),
    ("title", "bell\x07", "forbidden"),
    ("title", "zero​width", "forbidden"),
    ("title", "bidi‮override", "forbidden"),
    ("title", "bom﻿", "forbidden"),
])
def test_text_the_contract_would_refuse_is_refused_before_any_commitment(title, body, fragment):
    with pytest.raises(ValueError, match=fragment):
        commitment("0x" + "01" * 20, "B1", "0x" + "02" * 20, "s" * 16, title, body)


def test_validation_agrees_with_the_contract_on_the_same_inputs(h):
    h.create_bounty()
    cases = [("title", "ok body"), (" title", "body"), ("title", "body "), ("t\nt", "body"), ("title", "bell\x07x"),
             ("title", "zero​width"), ("t" * 121, "body"), ("title", "b" * 1201), ("title", "line\nbreak ok")]
    for number, (title, body) in enumerate(cases):
        hunter = create_address(f"agreement-hunter-{number}")  # one hunter per case: the per-hunter cap is 4
        h.people.append(hunter)
        h.deposit(hunter, 10**13)
        salt = new_salt()
        digest = raw_commitment(addr(h.alice), "B1", addr(hunter), salt, title, body)
        h.vm.sender = hunter
        index = h.c.commit_finding(addr(h.alice), "B1", digest)
        try:
            validate_text("title", title, 120, False)
            validate_text("body", body, 1200, True)
            tool_accepts = True
        except ValueError:
            tool_accepts = False
        try:
            h.c.reveal_finding(addr(h.alice), "B1", index, title, body, salt)
            contract_accepts = True
        except Exception as exc:  # noqa: BLE001
            assert "Invalid" in str(exc)
            contract_accepts = False
        assert tool_accepts == contract_accepts, (title, body)


def test_bad_salts_are_refused():
    for salt in ("short", "x" * 65, "has space inside!!", "ünïcode-salt-1234567"):
        with pytest.raises(ValueError, match="salt"):
            commitment("0x" + "01" * 20, "B1", "0x" + "02" * 20, salt, "title", "body")


def run_cli(tmp_path, body_bytes, title="Title"):
    body_file = tmp_path / "body.txt"
    body_file.write_bytes(body_bytes)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "primacy_commit.py"), "--sponsor", "0x" + "ab" * 20, "--bounty-id", "B1",
         "--hunter", "0x" + "cd" * 20, "--title", title, "--body-file", str(body_file), "--salt", "s" * 20],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def test_cli_strips_a_trailing_newline_and_prints_the_text_to_reveal(tmp_path):
    result = run_cli(tmp_path, b"Body line one.\nBody line two.\n")
    assert result.returncode == 0 and "removed" in result.stderr
    data = json.loads(result.stdout)
    assert data["body"] == "Body line one.\nBody line two."
    assert data["commitment"] == commitment("0x" + "ab" * 20, "B1", "0x" + "cd" * 20, "s" * 20, "Title", data["body"])


def test_cli_normalizes_windows_line_endings(tmp_path):
    result = run_cli(tmp_path, b"one\r\ntwo\r\n")
    assert result.returncode == 0 and json.loads(result.stdout)["body"] == "one\ntwo"


def test_cli_refuses_unrevealable_text_with_a_clear_error(tmp_path):
    result = run_cli(tmp_path, b"fine body", title=" padded title ")
    assert result.returncode == 2 and "title must not start or end" in result.stderr and result.stdout == ""
    result = run_cli(tmp_path, "zero​width body".encode())
    assert result.returncode == 2 and "forbidden" in result.stderr


@pytest.mark.parametrize("sponsor,bounty_id,hunter,fragment", [
    ("0x01", "B1", "0x" + "02" * 20, "sponsor must be"),
    ("ab" * 20, "B1", "0x" + "02" * 20, "sponsor must be"),
    ("0x" + "0g" * 20, "B1", "0x" + "02" * 20, "sponsor must be"),
    ("0x" + "01" * 20, "B1", "0x" + "02" * 19, "hunter must be"),
    ("0x" + "01" * 20, "B1", "0x" + "02" * 21, "hunter must be"),
    ("0x" + "01" * 20, "", "0x" + "02" * 20, "bounty id must be"),
    ("0x" + "01" * 20, "-bad", "0x" + "02" * 20, "bounty id must be"),
    ("0x" + "01" * 20, "has space", "0x" + "02" * 20, "bounty id must be"),
    ("0x" + "01" * 20, "x" * 65, "0x" + "02" * 20, "bounty id must be"),
])
def test_malformed_addresses_and_ids_are_refused_before_any_commitment(sponsor, bounty_id, hunter, fragment):
    # A commitment over a malformed key could never match, so the bond would be forfeited without a reveal.
    with pytest.raises(ValueError, match=fragment):
        commitment(sponsor, bounty_id, hunter, "s" * 16, "title", "body")


def test_the_cli_refuses_a_malformed_address_with_exit_status_two(tmp_path):
    body_file = tmp_path / "body.txt"
    body_file.write_text("body", encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "primacy_commit.py"), "--sponsor", "0x1234", "--bounty-id", "B1",
         "--hunter", "0x" + "cd" * 20, "--title", "Title", "--body-file", str(body_file)],
        capture_output=True, text=True,
    )
    assert run.returncode == 2
    assert "sponsor must be" in run.stderr
    assert run.stdout.strip() == ""
