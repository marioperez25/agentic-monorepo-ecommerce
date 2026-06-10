"""Password hashing/verification with bcrypt.

bcrypt operates on bytes and stores its parameters (cost, salt) inside the
hash string, so we don't need to track them separately. Cost 12 is the
current OWASP recommendation; raise this in the future if you can afford
the latency.
"""

from __future__ import annotations

import bcrypt

_DEFAULT_ROUNDS = 12


def hash_password(plaintext: str) -> str:
    salt = bcrypt.gensalt(rounds=_DEFAULT_ROUNDS)
    return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")


def verify_password(plaintext: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Hash is malformed — treat as a miss rather than crashing.
        return False
