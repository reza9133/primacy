"""Off-chain helper that builds the Primacy commit-reveal digest.

The digest is a SHA-256 over six length-prefixed UTF-8 fields:

    domain, bounty key, hunter address, salt, title, body

where the domain is the literal "primacy/v1", the bounty key is
"<sponsor address lowercase>:<bounty id>", and the hunter address is lowercase.
Each field is encoded as "<byte length>:<bytes>;". Keep the salt secret until you
reveal; it must be 16 to 64 characters from [A-Za-z0-9_-].
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys

DOMAIN = "primacy/v1"
SALT_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,64}")
ADDRESS_PATTERN = re.compile(r"0x[0-9a-fA-F]{40}")
BOUNTY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
MAX_TITLE = 120
MAX_BODY = 1200


def _field(text: str) -> bytes:
    raw = text.encode("utf-8")
    return str(len(raw)).encode("ascii") + b":" + raw + b";"


def _forbidden_char(code: int) -> bool:
    return (
        code < 32
        or 127 <= code <= 159
        or 0xD800 <= code <= 0xDFFF
        or 0x200B <= code <= 0x200F
        or 0x2028 <= code <= 0x202E
        or 0x2060 <= code <= 0x206F
        or code == 0xFEFF
        or 0xFFF9 <= code <= 0xFFFF
    )


def validate_text(label: str, value: str, limit: int, multiline: bool) -> None:
    """Mirror the contract's exact-text rule. Text that fails here can never be revealed.

    A commitment is a hash of the exact text, and the contract refuses to reveal text with leading or
    trailing whitespace, control characters or invisible formatting characters. Committing to such text
    would forfeit the bond, so this check runs before any commitment is produced.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must not be empty")
    if len(value) > limit:
        raise ValueError(f"{label} is longer than {limit} characters")
    if value != value.strip():
        raise ValueError(f"{label} must not start or end with whitespace")
    for char in value:
        code = ord(char)
        if code in (9, 10):
            if multiline:
                continue
            raise ValueError(f"{label} must be a single line without tabs")
        if _forbidden_char(code):
            raise ValueError(f"{label} contains a forbidden control or invisible character (U+{code:04X})")


def bounty_key(sponsor: str, bounty_id: str) -> str:
    return sponsor.lower() + ":" + bounty_id


def new_salt() -> str:
    """Return a fresh 32-character random salt."""
    return secrets.token_hex(16)


def raw_commitment(sponsor: str, bounty_id: str, hunter: str, salt: str, title: str, body: str) -> str:
    """Digest of the given fields exactly as the contract computes it, with no text validation.

    Prefer :func:`commitment`. This variant exists so tests can commit to text the contract must refuse.
    The salt format is still enforced because the contract's salt rule is part of the commitment format.
    """
    if not SALT_PATTERN.fullmatch(salt):
        raise ValueError("salt must be 16-64 characters from [A-Za-z0-9_-]")
    parts = (DOMAIN, bounty_key(sponsor, bounty_id), hunter.lower(), salt, title, body)
    return "0x" + hashlib.sha256(b"".join(_field(part) for part in parts)).hexdigest()


def commitment(sponsor: str, bounty_id: str, hunter: str, salt: str, title: str, body: str) -> str:
    """Return the 0x-prefixed commitment the contract expects for this finding.

    Refuses text the contract could never reveal, because committing to it would forfeit the bond.
    """
    if not ADDRESS_PATTERN.fullmatch(sponsor):
        raise ValueError("sponsor must be a 0x-prefixed 20-byte hex address")
    if not ADDRESS_PATTERN.fullmatch(hunter):
        raise ValueError("hunter must be a 0x-prefixed 20-byte hex address")
    if not BOUNTY_ID_PATTERN.fullmatch(bounty_id):
        raise ValueError("bounty id must be 1-64 characters from [A-Za-z0-9_.-] and start with a letter or digit")
    validate_text("title", title, MAX_TITLE, False)
    validate_text("body", body, MAX_BODY, True)
    return raw_commitment(sponsor, bounty_id, hunter, salt, title, body)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a Primacy finding commitment.")
    parser.add_argument("--sponsor", required=True, help="sponsor address (0x...)")
    parser.add_argument("--bounty-id", required=True)
    parser.add_argument("--hunter", required=True, help="your address (0x...)")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body-file", required=True, help="UTF-8 file holding the exact body text")
    parser.add_argument("--salt", default=None, help="optional; a random salt is generated if omitted")
    args = parser.parse_args(argv)
    with open(args.body_file, "r", encoding="utf-8", newline="") as handle:
        raw_body = handle.read()
    body = raw_body.replace("\r\n", "\n").strip()
    if body != raw_body:
        sys.stderr.write("note: leading/trailing whitespace was removed from the body; reveal the text printed below\n")
    salt = args.salt or new_salt()
    try:
        digest = commitment(args.sponsor, args.bounty_id, args.hunter, salt, args.title, body)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    json.dump({"commitment": digest, "salt": salt, "title": args.title, "body": body}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
