"""Password hashing (Argon2 via pwdlib)."""

from __future__ import annotations

from pwdlib import PasswordHash

_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hash.verify(password, password_hash)
    except Exception:  # noqa: BLE001 - unrecognised hash, malformed, etc.
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hash.needs_update(password_hash)
